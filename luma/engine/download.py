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


_active_procs = set()
_procs_lock = threading.Lock()

_cancel_event = threading.Event()

_cancelled_tags = set()


def cancel_tag(tag):
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
    _cancel_event.set()


def reset_cancel():
    _cancel_event.clear()
    with _procs_lock:
        _cancelled_tags.clear()


def is_cancelled():
    return _cancel_event.is_set()


def terminate_all(timeout=5):
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


_LEFTOVERS = (".part", ".aria2", ".ytdl", ".temp")


def _video_id(text):
    match = re.search(r"\[([A-Za-z0-9_-]{11})\]", str(text or ""))
    if match:
        return match.group(1)
    match = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})",
                      str(text or ""))
    return match.group(1) if match else ""


def clean_partials(output_dir, marker=None):
    video_id = _video_id(marker) if marker else ""
    removed = 0
    try:
        names = os.listdir(output_dir)
    except OSError:
        return 0

    for name in names:
        if not (name.endswith(_LEFTOVERS) or ".part-Frag" in name):
            continue
        if video_id and video_id not in name:
            continue
        try:
            os.remove(os.path.join(output_dir, name))
            removed += 1
        except OSError:
            pass
    return removed


# Televisions, car stereos and cheap media players are far fussier than a
# computer is. They want H.264 video and AAC audio, and they want the video
# track first -- given the audio track first, many of them play the picture
# in silence. Each step below gives up one of those wishes, so a video that
# exists in nothing else still downloads.
def _format_chain(quality):
    cap = "" if str(quality).lower() == "best" else f"[height<={int(quality)}]"
    return "/".join((
        f"bv*[vcodec^=avc1]{cap}+ba[acodec^=mp4a]",
        f"bv*{cap}+ba[acodec^=mp4a]",
        f"bv*{cap}+ba",
        f"b{cap}",
        "best",
    ))


def build_cmd(tools, url, plan, output_dir, quality, downloader="aria2c",
              archive=False):
    fmt = _format_chain(quality)

    out_tmpl = os.path.join(output_dir, "%(title).150B [%(id)s].%(ext)s")

    cmd = [
        tools["yt-dlp"],
        "-f", fmt,
        "-S", "res,ext:mp4:m4a,codec:h264:aac",
        "--merge-output-format", "mp4",
        "--ffmpeg-location", os.path.dirname(tools["ffmpeg"]),
        "-o", out_tmpl,
        "--no-playlist",
        "--concurrent-fragments", str(plan["concurrent_fragments"]),
        "--retries", "10",
        "--fragment-retries", "10",
        "--file-access-retries", "5",
        "--retry-sleep", "2",
        "--throttled-rate", "100K",
        "--no-mtime",
        "--newline",
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


_ARIA_RE = re.compile(
    r"\[#(\w+)\s+([\d.]+[KMGTP]?i?B)/([\d.]+[KMGTP]?i?B)\((\d+)%\)"
    r"\s+CN:(\d+)\s+DL:([\d.]+[KMGTP]?i?B)(?:\s+ETA:(\S+?))?\]")
_YTDL_RE = re.compile(
    r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+[KMGTP]?i?B)"
    r"(?:\s+at\s+([\d.]+[KMGTP]?i?B/s))?(?:\s+ETA\s+(\S+))?")


_SIZE = re.compile(r"([\d.]+)\s*([KMGT]?)i?B", re.IGNORECASE)
_SCALE = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def size_to_bytes(text):
    match = _SIZE.search(text or "")
    if not match:
        return 0
    try:
        return int(float(match.group(1)) * _SCALE.get(match.group(2).upper(), 1))
    except ValueError:
        return 0


_ETA_OK = re.compile(r"^\d+(?:[hms]\d*)*$|^\d+(?::\d{2}){1,2}$", re.IGNORECASE)


def _clean_eta(text):
    value = (text or "").strip()
    if not value or value.startswith("-") or value.lower() in ("unknown", "n/a"):
        return ""
    if not _ETA_OK.match(value):
        return ""
    if re.match(r"^\d+:\d{2}:\d{2}$", value) and int(value.split(":")[0]) >= 24:
        return ""
    return value


def parse_progress(line):
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
    return None


_DEST_RE = re.compile(r"\[download\] Destination:\s*(.+)$")
_MERGE_RE = re.compile(r'\[Merger\] Merging formats into "(.+)"')
_ALREADY_RE = re.compile(r"\[download\]\s*(.+?)\s+has already been downloaded")


def _track_filepath(line, state):
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


_FORMATS_RE = re.compile(r"Downloading\s+\d+\s+format\(s\):\s*([\w+]+)")

_FORMAT_MARKER = re.compile(r"\.f\d+\.")

_AUDIO_EXTENSIONS = (".m4a", ".opus", ".ogg", ".oga", ".mp3", ".aac", ".wav")


def _stream_kind(path):
    name = re.split(r"[\\/]", str(path or "").strip())[-1].lower()
    if not name:
        return ""
    if name.endswith(_AUDIO_EXTENSIONS):
        return "Sound"
    if _FORMAT_MARKER.search(name):
        return "Picture"
    return ""


def _track_streams(line, state):
    m = _FORMATS_RE.search(line)
    if m:
        declared = max(1, len(m.group(1).split("+")))
        state["streams_total"] = max(declared, state.get("streams_total", 1))
        return

    dest = _DEST_RE.search(line)
    if not dest:
        return

    if _FORMAT_MARKER.search(dest.group(1)):
        state["streams_total"] = max(2, state.get("streams_total", 1))
    state["stream_kind"] = _stream_kind(dest.group(1))

    if state.get("stream_started"):
        pieces = state.get("pieces") or {}
        state["done_base"] = (state.get("done_base", 0)
                              + sum(t for _, t in pieces.values()))
        state["stream_index"] = state.get("stream_index", 0) + 1
    state["stream_started"] = True
    state["pieces"] = {}

    needed = state.get("stream_index", 0) + 1
    if needed > state.get("streams_total", 1):
        state["streams_total"] = needed
        state["percent_seen"] = 0.0


def _overall(state, parsed):
    streams = max(1, state.get("streams_total", 1))
    index = max(0, min(state.get("stream_index", 0), streams - 1))

    pieces = state.setdefault("pieces", {})
    pieces[parsed.get("id") or "download"] = (
        parsed["done_bytes"], parsed["total_bytes"],
    )
    stream_done = sum(d for d, _ in pieces.values())
    stream_total = sum(t for _, t in pieces.values())

    if len(pieces) == 1 and parsed["percent"]:
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
    if state.get("title_sent"):
        return
    title = title_from_filename(
        state.get("filepath") or state.get("destination")
    )
    if title:
        state["title_sent"] = True
        state["title"] = title
        callbacks.on_video_title(tag, title)


def _stream_download(cmd, tag, callbacks):
    tail = collections.deque(maxlen=25)
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
                if now - last_progress >= 0.25:
                    last_progress = now
                    callbacks.on_video_progress(tag, parsed)
                continue

            note = _milestone(line)
            if note is not None and note != state.get("last_note"):
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
    tag = tag if tag is not None else f"{index}/{total}"
    callbacks.on_video_start(tag, url)
    cmd = build_cmd(tools, url, plan, output_dir, quality, downloader, archive)

    reason, filepath = "", None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if _cancel_event.is_set() or is_tag_cancelled(tag):
            clean_partials(output_dir, url)
            callbacks.on_video_done(tag, url, False, "Stopped.", None)
            return (url, False, "Stopped.", None)

        rc, reason, filepath = _stream_download(cmd, tag, callbacks)
        if rc == 0:
            clean_partials(output_dir, filepath or url)
            callbacks.on_video_done(tag, url, True, "", filepath)
            return (url, True, "", filepath)
        if rc == 130:
            clean_partials(output_dir, filepath or url)
            callbacks.on_video_done(tag, url, False, "Stopped.", filepath)
            return (url, False, "Stopped.", filepath)

        if attempt < MAX_ATTEMPTS:
            wait = min(2 * attempt, 8)
            callbacks.on_video_status(
                tag, f"Hit a problem - retrying in {wait}s "
                     f"(try {attempt + 1} of {MAX_ATTEMPTS})..."
            )
            for _ in range(int(wait * 4)):
                if _cancel_event.is_set() or is_tag_cancelled(tag):
                    break
                time.sleep(0.25)

    callbacks.on_video_done(tag, url, False, reason, filepath)
    return (url, False, reason, filepath)


def run_downloads(tools, urls, plan, output_dir, quality, downloader="aria2c",
                  archive=False, callbacks=None, tags=None):
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
                results.append((url, False, f"Unexpected problem ({exc}).", None))
    return results
