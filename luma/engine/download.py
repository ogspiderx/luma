"""
The download engine: build the command, run it, parse its output, retry it.

Ported from yt_turbo.py. The structure of _stream_download (Popen + line loop
+ tail deque) and the retry/backoff in download_one are deliberately unchanged;
only the reporting is different -- prints became callbacks.

Every child process is registered while it runs so the app can shut them all
down cleanly on quit instead of leaving orphans behind.
"""

import collections
import concurrent.futures as futures
import os
import re
import subprocess
import threading
import time

from .callbacks import EngineCallbacks
from .constants import MAX_ATTEMPTS
from .paths import title_from_filename

# --------------------------------------------------------------------------- #
#  Child-process registry -- so quitting never leaves orphans running.         #
# --------------------------------------------------------------------------- #

_active_procs = set()
_procs_lock = threading.Lock()

#: Set to request that all in-flight downloads stop as soon as they can.
_cancel_event = threading.Event()

#: Individual downloads asked to stop, by tag, so one can be dropped without
#: disturbing the others.
_cancelled_tags = set()


def cancel_tag(tag):
    """Ask one download to stop, leaving the rest running."""
    with _procs_lock:
        _cancelled_tags.add(tag)


def is_tag_cancelled(tag):
    with _procs_lock:
        return tag in _cancelled_tags


def _register(proc):
    with _procs_lock:
        _active_procs.add(proc)


def _unregister(proc):
    with _procs_lock:
        _active_procs.discard(proc)


def request_cancel():
    """Ask every running download to stop."""
    _cancel_event.set()


def reset_cancel():
    """Clear any cancel requests before starting new work."""
    _cancel_event.clear()
    with _procs_lock:
        _cancelled_tags.clear()


def is_cancelled():
    return _cancel_event.is_set()


def terminate_all(timeout=5):
    """Stop every child process this engine started. Safe to call twice."""
    _cancel_event.set()
    with _procs_lock:
        procs = list(_active_procs)
    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass
    deadline = time.time() + timeout
    for proc in procs:
        try:
            remaining = max(0.1, deadline - time.time())
            proc.wait(timeout=remaining)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    with _procs_lock:
        _active_procs.clear()


# --------------------------------------------------------------------------- #
#  Command construction                                                        #
# --------------------------------------------------------------------------- #

def build_cmd(tools, url, plan, output_dir, quality, downloader="aria2c",
              archive=False):
    """Build the yt-dlp argument list. Always a list -- never a shell string."""
    # Sound first, then picture. The streams are fetched in the order named
    # here, and sound is much the smaller of the two, so putting it first
    # gets one part of the video finished quickly and each stream gets the
    # whole connection to itself rather than sharing it.
    if str(quality).lower() == "best":
        fmt = "ba+bv*/b/best"
    else:
        q = int(quality)
        fmt = (f"ba+bv*[height<={q}]/"
               f"b[height<={q}]/"
               f"bv*[height<={q}]/best")

    out_tmpl = os.path.join(output_dir, "%(title).150B [%(id)s].%(ext)s")

    cmd = [
        tools["yt-dlp"],
        "-f", fmt,
        "-S", "res,ext:mp4:m4a,codec:h264",   # prefer mp4/h264 near the cap
        "--merge-output-format", "mp4",
        "--ffmpeg-location", os.path.dirname(tools["ffmpeg"]),
        "-o", out_tmpl,
        "--no-playlist",                       # already expanded ourselves
        "--concurrent-fragments", str(plan["concurrent_fragments"]),
        "--retries", "10",
        "--fragment-retries", "10",
        "--file-access-retries", "5",
        "--retry-sleep", "2",
        "--throttled-rate", "100K",            # re-extract if YouTube throttles
        "--no-mtime",
        "--newline",                           # clean progress when parallel
        "--no-warnings",
    ]

    if downloader == "aria2c":
        aria_args = (
            f"-x{plan['conns_per_file']} "
            f"-s{plan['conns_per_file']} "
            f"-k1M --min-split-size=1M "
            f"--max-connection-per-server={plan['conns_per_file']} "
            f"--file-allocation=none --continue=true "
            f"--max-tries=10 --retry-wait=3 --max-file-not-found=3 "
            f"--connect-timeout=15 --timeout=30 "
            f"--console-log-level=warn --summary-interval=1"
        )
        cmd += ["--downloader", "aria2c", "--downloader-args",
                f"aria2c:{aria_args}"]

    if archive:
        cmd += ["--download-archive", os.path.join(output_dir, "archive.txt")]

    cmd.append(url)
    return cmd


# --------------------------------------------------------------------------- #
#  Output parsing                                                              #
# --------------------------------------------------------------------------- #

# aria2c compact line: [#a1b2c3 46MiB/54MiB(85%) CN:4 DL:698KiB ETA:11s]
# The leading id matters: aria2c prints one of these per download it has in
# flight, so without it several concurrent pieces look like one thrashing file.
_ARIA_RE = re.compile(
    r"\[#(\w+)\s+([\d.]+[KMGTP]?i?B)/([\d.]+[KMGTP]?i?B)\((\d+)%\)"
    r"\s+CN:(\d+)\s+DL:([\d.]+[KMGTP]?i?B)(?:\s+ETA:(\S+?))?\]")
# yt-dlp native: [download]  85.0% of 54.00MiB at 700.00KiB/s ETA 00:19
_YTDL_RE = re.compile(
    r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+[KMGTP]?i?B)"
    r"(?:\s+at\s+([\d.]+[KMGTP]?i?B/s))?(?:\s+ETA\s+(\S+))?")


#: "40MiB", "54.2MB", "900KiB" -> bytes.
_SIZE = re.compile(r"([\d.]+)\s*([KMGT]?)i?B", re.IGNORECASE)
_SCALE = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def size_to_bytes(text):
    """Turn a size like '54MiB' into bytes, or 0 when it cannot be read."""
    match = _SIZE.search(text or "")
    if not match:
        return 0
    try:
        return int(float(match.group(1)) * _SCALE.get(match.group(2).upper(), 1))
    except ValueError:
        return 0


#: A sane countdown: "19s", "1m30s", "00:19", "1:02:03".
_ETA_OK = re.compile(r"^\d+(?:[hms]\d*)*$|^\d+(?::\d{2}){1,2}$", re.IGNORECASE)


def _clean_eta(text):
    """Return a trustworthy time-remaining string, or nothing.

    The tools occasionally emit a negative or nonsensical estimate while they
    are still working one out. Showing nothing beats showing "-1s".
    """
    value = (text or "").strip()
    if not value or value.startswith("-") or value.lower() in ("unknown", "n/a"):
        return ""
    if not _ETA_OK.match(value):
        return ""
    # A countdown of a day or more is a guess, not information.
    if re.match(r"^\d+:\d{2}:\d{2}$", value) and int(value.split(":")[0]) >= 24:
        return ""
    return value


def parse_progress(line):
    """Parse a progress line into a dict, or None if it isn't one.

    This describes one *stream*. A video at 480p is delivered as two of them
    (picture and sound), so these numbers are combined into whole-video
    figures by _overall() before they reach the interface.
    """
    m = _ARIA_RE.search(line)
    if m:
        gid, done, tot, pct, cn, spd, eta = m.groups()
        return {
            "id": gid,
            "percent": float(pct),
            "done": done,
            "total": tot,
            "done_bytes": size_to_bytes(done),
            "total_bytes": size_to_bytes(tot),
            "speed": f"{spd}/s",
            "eta": _clean_eta(eta),
            "connections": int(cn),
        }
    m = _YTDL_RE.search(line)
    if m:
        pct, tot, spd, eta = m.groups()
        total_bytes = size_to_bytes(tot)
        return {
            "id": "download",
            "percent": float(pct),
            "done": "",
            "total": tot,
            "done_bytes": int(total_bytes * float(pct) / 100.0),
            "total_bytes": total_bytes,
            "speed": spd or "",
            "eta": _clean_eta(eta),
            "connections": None,
        }
    return None


def _friendly_error(text):
    """Translate a raw tool error into something a normal person can act on."""
    low = text.lower()
    if "private video" in low or "sign in" in low:
        return "This video is private."
    if "video unavailable" in low or "removed" in low:
        return "This video is unavailable or has been removed."
    if "age" in low and "restrict" in low:
        return "This video is age-restricted."
    if "copyright" in low:
        return "This video was blocked for copyright reasons."
    if "not available in your country" in low or "geo" in low:
        return "This video is not available in your country."
    if ("network" in low or "timed out" in low or "connection" in low
            or "handshake" in low or "resolve" in low):
        return "The connection dropped. Check your internet and try again."
    if "no space" in low or "disk" in low:
        return "Your disk is full."
    if "unsupported url" in low or "is not a valid url" in low:
        return "That link is not supported."
    return "The download did not finish."


def _milestone(line):
    """Friendly one-off status text for an interesting line, else None."""
    s = line.strip()
    if s.startswith("[download] Destination:"):
        path = s.split("Destination:", 1)[1].strip()
        name = re.split(r"[\\/]", path)[-1]
        return "Saving: " + name
    if s.startswith("[Merger]"):
        return "Combining video and audio..."
    if s.startswith("[ExtractAudio]"):
        return "Extracting audio..."
    if "has already been downloaded" in s:
        return "Already downloaded - skipping."
    if s.startswith("[info]") and "format" in s:
        return "Picking the best quality..."
    low = s.lower()
    if s.startswith("ERROR") or "error:" in low:
        return _friendly_error(s)
    return None   # tool chatter and summary noise -> hidden


_DEST_RE = re.compile(r"\[download\] Destination:\s*(.+)$")
_MERGE_RE = re.compile(r'\[Merger\] Merging formats into "(.+)"')
_ALREADY_RE = re.compile(r"\[download\]\s*(.+?)\s+has already been downloaded")


def _track_filepath(line, state):
    """Remember where the finished file ended up, for the history log."""
    m = _MERGE_RE.search(line)
    if m:
        state["filepath"] = m.group(1).strip()
        return
    m = _ALREADY_RE.search(line)
    if m:
        state["filepath"] = m.group(1).strip()
        return
    m = _DEST_RE.search(line)
    if m and not state.get("filepath"):
        state["destination"] = m.group(1).strip()


#: "[info] abc: Downloading 1 format(s): 135+140" -> two streams.
_FORMATS_RE = re.compile(r"Downloading\s+\d+\s+format\(s\):\s*([\w+]+)")

#: ".f135." in a filename marks one stream of a video built from several.
_FORMAT_MARKER = re.compile(r"\.f\d+\.")

#: Sound-only containers, so a stream can be named for what it carries.
_AUDIO_EXTENSIONS = (".m4a", ".opus", ".ogg", ".oga", ".mp3", ".aac", ".wav")


def _stream_kind(path):
    """Say whether a stream is the sound or the picture, from its filename."""
    name = re.split(r"[\\/]", str(path or "").strip())[-1].lower()
    if not name:
        return ""
    if name.endswith(_AUDIO_EXTENSIONS):
        return "Sound"
    if _FORMAT_MARKER.search(name):
        return "Picture"
    return ""      # a single combined file is just "the video"


def _track_streams(line, state):
    """Follow which of a video's streams is being fetched.

    A video is usually delivered as a picture stream followed by a sound
    stream. Each reports its own size and percentage, so without this the
    figures appear to jump backwards when the second one starts.

    Only a new destination begins a stream. Merging is not a download, so it
    must not advance the count.
    """
    m = _FORMATS_RE.search(line)
    if m:
        declared = max(1, len(m.group(1).split("+")))
        state["streams_total"] = max(declared, state.get("streams_total", 1))
        return

    dest = _DEST_RE.search(line)
    if not dest:
        return

    # A name like "Title [id].f135.mp4" is a single stream of a video that
    # will be assembled from several, so a second one is coming even if it was
    # never announced. Knowing that up front avoids the bar reaching the end
    # and then having to come back.
    if _FORMAT_MARKER.search(dest.group(1)):
        state["streams_total"] = max(2, state.get("streams_total", 1))
    state["stream_kind"] = _stream_kind(dest.group(1))

    if state.get("stream_started"):
        # Bank the stream that just finished so its bytes keep counting.
        pieces = state.get("pieces") or {}
        state["done_base"] = (state.get("done_base", 0)
                              + sum(t for _, t in pieces.values()))
        state["stream_index"] = state.get("stream_index", 0) + 1
    state["stream_started"] = True
    state["pieces"] = {}

    # If more streams turn up than were announced, believe what is happening
    # rather than the announcement -- this is what kept the bar past its end.
    needed = state.get("stream_index", 0) + 1
    if needed > state.get("streams_total", 1):
        state["streams_total"] = needed
        state["percent_seen"] = 0.0    # the scale changed; let it re-settle


def _overall(state, parsed):
    """Turn stream readings into figures for the whole video.

    aria2c reports each piece it has in flight separately, so the pieces are
    summed rather than treated as competing views of the same file. The result
    is clamped and cannot run past the end.
    """
    streams = max(1, state.get("streams_total", 1))
    index = max(0, min(state.get("stream_index", 0), streams - 1))

    # Remember this piece and add up everything in flight for this stream.
    pieces = state.setdefault("pieces", {})
    pieces[parsed.get("id") or "download"] = (
        parsed["done_bytes"], parsed["total_bytes"],
    )
    stream_done = sum(d for d, _ in pieces.values())
    stream_total = sum(t for _, t in pieces.values())

    if len(pieces) == 1 and parsed["percent"]:
        # One piece in flight: its own percentage is exact, where the sizes it
        # prints are rounded for display and drift by a percent or so.
        fraction = parsed["percent"] / 100.0
    elif stream_total > 0:
        fraction = stream_done / stream_total
    elif parsed["percent"]:
        fraction = parsed["percent"] / 100.0
    else:
        fraction = 0.0
    fraction = max(0.0, min(1.0, fraction))

    percent = (index + fraction) / streams * 100.0
    percent = max(0.0, min(100.0, percent))
    # Resist small backwards steps without letting the bar seize up: a genuine
    # move of more than a couple of percent is believed.
    previous = state.get("percent_seen", 0.0)
    if percent < previous - 2.0:
        state["percent_seen"] = percent
    else:
        percent = max(percent, previous)
        state["percent_seen"] = percent

    base_done = state.get("done_base", 0)
    done_bytes = base_done + stream_done
    total_bytes = base_done + stream_total
    total_bytes = max(total_bytes, done_bytes, state.get("total_seen", 0))
    state["total_seen"] = total_bytes

    return {
        "percent": percent,
        "done_bytes": done_bytes,
        "total_bytes": total_bytes,
        "speed": parsed["speed"],
        "eta": parsed["eta"],
        "connections": parsed["connections"],
        "stream": index + 1,
        "streams": streams,
        "kind": state.get("stream_kind", ""),
    }


def _track_title(state, tag, callbacks):
    """Report the video's title the first time it can be read off the file."""
    if state.get("title_sent"):
        return
    title = title_from_filename(
        state.get("filepath") or state.get("destination")
    )
    if title:
        state["title_sent"] = True
        state["title"] = title
        callbacks.on_video_title(tag, title)


# --------------------------------------------------------------------------- #
#  Running one download                                                        #
# --------------------------------------------------------------------------- #

def _stream_download(cmd, tag, callbacks):
    """Run one yt-dlp invocation. Returns (rc, reason, filepath)."""
    tail = collections.deque(maxlen=25)   # recent output, for error reports
    last_progress = 0.0
    state = {}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        return 1, f"Could not start the download ({exc}).", None

    _register(proc)
    try:
        for raw in proc.stdout:
            if _cancel_event.is_set() or is_tag_cancelled(tag):
                proc.terminate()
                break

            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            tail.append(line)
            _track_streams(line, state)
            _track_filepath(line, state)
            _track_title(state, tag, callbacks)

            parsed = parse_progress(line)
            if parsed is not None:
                parsed = _overall(state, parsed)
                now = time.time()
                if now - last_progress >= 0.25:   # throttle UI updates
                    last_progress = now
                    callbacks.on_video_progress(tag, parsed)
                continue

            note = _milestone(line)
            if note is not None and note != state.get("last_note"):
                # Saying the same thing twice in a row reads as being stuck.
                state["last_note"] = note
                callbacks.on_video_status(tag, note)

        proc.wait()
    finally:
        _unregister(proc)

    filepath = state.get("filepath") or state.get("destination")

    if _cancel_event.is_set() or is_tag_cancelled(tag):
        return 130, "Stopped.", filepath
    if proc.returncode == 0:
        return 0, "", filepath

    raw_reason = next(
        (ln for ln in reversed(tail) if "ERROR" in ln or "error" in ln.lower()),
        None,
    )
    reason = _friendly_error(raw_reason or "")
    return proc.returncode, reason, filepath


def download_one(tools, url, plan, output_dir, quality, downloader, archive,
                 index, total, callbacks, tag=None):
    """Download one video, retrying transient failures. Resumes each attempt."""
    tag = tag if tag is not None else f"{index}/{total}"
    callbacks.on_video_start(tag, url)
    cmd = build_cmd(tools, url, plan, output_dir, quality, downloader, archive)

    reason, filepath = "", None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if _cancel_event.is_set() or is_tag_cancelled(tag):
            callbacks.on_video_done(tag, url, False, "Stopped.", None)
            return (url, False, "Stopped.", None)

        rc, reason, filepath = _stream_download(cmd, tag, callbacks)
        if rc == 0:
            callbacks.on_video_done(tag, url, True, "", filepath)
            return (url, True, "", filepath)
        if rc == 130:                      # cancelled, don't retry
            callbacks.on_video_done(tag, url, False, "Stopped.", filepath)
            return (url, False, "Stopped.", filepath)

        if attempt < MAX_ATTEMPTS:
            wait = min(2 * attempt, 8)
            callbacks.on_video_status(
                tag, f"Hit a problem - retrying in {wait}s "
                     f"(try {attempt + 1} of {MAX_ATTEMPTS})..."
            )
            # Sleep in slices so a cancel is noticed promptly.
            for _ in range(int(wait * 4)):
                if _cancel_event.is_set() or is_tag_cancelled(tag):
                    break
                time.sleep(0.25)

    callbacks.on_video_done(tag, url, False, reason, filepath)
    return (url, False, reason, filepath)


def run_downloads(tools, urls, plan, output_dir, quality, downloader="aria2c",
                  archive=False, callbacks=None, tags=None):
    """Download every URL, fanning out to plan['parallel_files'] at a time.

    One failure never stops the others. Returns a list of
    (url, ok, reason, filepath) tuples.

    `tags` optionally names each download, so a caller that is already showing
    a numbered list can keep its own numbering instead of restarting at one.
    """
    callbacks = callbacks or EngineCallbacks()
    os.makedirs(output_dir, exist_ok=True)

    total = len(urls)
    results = []
    workers = max(1, min(plan["parallel_files"], total))

    with futures.ThreadPoolExecutor(max_workers=workers) as ex:
        jobs = {
            ex.submit(
                download_one, tools, url, plan, output_dir, quality,
                downloader, archive, i + 1, total, callbacks,
                tags[i] if tags and i < len(tags) else None,
            ): url
            for i, url in enumerate(urls)
        }
        for fut in futures.as_completed(jobs):
            url = jobs[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                # Error isolation: a crash in one item must not sink the batch.
                results.append((url, False, f"Unexpected problem ({exc}).", None))
    return results
