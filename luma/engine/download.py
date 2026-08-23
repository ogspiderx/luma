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

# --------------------------------------------------------------------------- #
#  Child-process registry -- so quitting never leaves orphans running.         #
# --------------------------------------------------------------------------- #

_active_procs = set()
_procs_lock = threading.Lock()

#: Set to request that all in-flight downloads stop as soon as they can.
_cancel_event = threading.Event()


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
    """Clear a previous cancel request before starting new work."""
    _cancel_event.clear()


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
    if str(quality).lower() == "best":
        fmt = "bv*+ba/b/best"
    else:
        q = int(quality)
        fmt = (f"bv*[height<={q}]+ba/"
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
_ARIA_RE = re.compile(
    r"\[#\w+\s+([\d.]+[KMGTP]?i?B)/([\d.]+[KMGTP]?i?B)\((\d+)%\)"
    r"\s+CN:(\d+)\s+DL:([\d.]+[KMGTP]?i?B)(?:\s+ETA:(\S+?))?\]")
# yt-dlp native: [download]  85.0% of 54.00MiB at 700.00KiB/s ETA 00:19
_YTDL_RE = re.compile(
    r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+[KMGTP]?i?B)"
    r"(?:\s+at\s+([\d.]+[KMGTP]?i?B/s))?(?:\s+ETA\s+(\S+))?")


def parse_progress(line):
    """Parse a progress line into a dict, or None if it isn't one.

    Returns {percent, done, total, speed, eta, connections} -- the structured
    form the UI needs. Uses the same patterns as the proven CLI tool.
    """
    m = _ARIA_RE.search(line)
    if m:
        done, tot, pct, cn, spd, eta = m.groups()
        return {
            "percent": float(pct),
            "done": done,
            "total": tot,
            "speed": f"{spd}/s",
            "eta": eta or "",
            "connections": int(cn),
        }
    m = _YTDL_RE.search(line)
    if m:
        pct, tot, spd, eta = m.groups()
        return {
            "percent": float(pct),
            "done": "",
            "total": tot,
            "speed": spd or "",
            "eta": eta or "",
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
            if _cancel_event.is_set():
                proc.terminate()
                break

            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            tail.append(line)
            _track_filepath(line, state)

            parsed = parse_progress(line)
            if parsed is not None:
                now = time.time()
                if now - last_progress >= 0.25:   # throttle UI updates
                    last_progress = now
                    callbacks.on_video_progress(tag, parsed)
                continue

            note = _milestone(line)
            if note is not None:
                callbacks.on_video_status(tag, note)

        proc.wait()
    finally:
        _unregister(proc)

    filepath = state.get("filepath") or state.get("destination")

    if _cancel_event.is_set():
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
                 index, total, callbacks):
    """Download one video, retrying transient failures. Resumes each attempt."""
    tag = f"{index}/{total}"
    callbacks.on_video_start(tag, url)
    cmd = build_cmd(tools, url, plan, output_dir, quality, downloader, archive)

    reason, filepath = "", None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if _cancel_event.is_set():
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
                if _cancel_event.is_set():
                    break
                time.sleep(0.25)

    callbacks.on_video_done(tag, url, False, reason, filepath)
    return (url, False, reason, filepath)


def run_downloads(tools, urls, plan, output_dir, quality, downloader="aria2c",
                  archive=False, callbacks=None):
    """Download every URL, fanning out to plan['parallel_files'] at a time.

    One failure never stops the others. Returns a list of
    (url, ok, reason, filepath) tuples.
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
