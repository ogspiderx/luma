"""
Locating (and on Windows, installing) the external tools Luma shells out to.

Ported from yt_turbo.py's dependency management. Behaviour is unchanged except
that progress is reported through callbacks instead of printed, and a missing
tool on a non-Windows machine raises ToolInstallError instead of SystemExit.
"""

import os
import shutil
import ssl
import subprocess
import time
import urllib.request
import zipfile

from .callbacks import EngineCallbacks
from .constants import ARIA2_URL, FFMPEG_URL, UA, YTDLP_URL
from .errors import ToolInstallError

#: Where portable Windows binaries get installed, alongside the app.
BIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"
)


def _download(url, dest, desc, callbacks):
    """Stream a URL to disk, reporting progress through callbacks."""
    callbacks.on_status(f"Downloading {desc}...")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        last = 0.0
        tmp = dest + ".part"
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                now = time.time()
                if now - last > 0.25:
                    last = now
                    callbacks.on_tool_progress(desc, got, total)
    callbacks.on_tool_progress(desc, got, total)
    os.replace(tmp, dest)


def _extract_members(zip_path, wanted, dest_dir):
    """Pull specific file basenames out of a zip into dest_dir (flat)."""
    found = {}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            base = os.path.basename(member)
            if base.lower() in wanted:
                target = os.path.join(dest_dir, base)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                found[base.lower()] = target
    return found


def _which(name):
    return shutil.which(name)


def _require_windows(tool):
    """Raise a catchable, user-readable error instead of killing the process."""
    raise ToolInstallError(
        f"{tool} is not installed, and it can only be installed automatically "
        f"on Windows. Please install {tool} using your system's package "
        f"manager, then start Luma again."
    )


def ensure_tools(callbacks=None):
    """Return {'yt-dlp':path, 'aria2c':path, 'ffmpeg':path, 'ffprobe':path}.

    Uses copies already on PATH when present; otherwise downloads portable
    win64 builds into ./bin. Also prepends ./bin to PATH for this process.

    Raises ToolInstallError if a tool is missing and cannot be installed.
    """
    callbacks = callbacks or EngineCallbacks()
    os.makedirs(BIN_DIR, exist_ok=True)
    is_windows = os.name == "nt"
    exe = ".exe" if is_windows else ""

    tools = {}

    # ---- yt-dlp -----------------------------------------------------------
    p = _which("yt-dlp") or _which("yt-dlp.exe")
    local = os.path.join(BIN_DIR, f"yt-dlp{exe}")
    if p:
        tools["yt-dlp"] = p
    elif os.path.exists(local):
        tools["yt-dlp"] = local
    else:
        if not is_windows:
            _require_windows("yt-dlp")
        _download(YTDLP_URL, local, "the video downloader", callbacks)
        tools["yt-dlp"] = local

    # ---- aria2c -----------------------------------------------------------
    p = _which("aria2c") or _which("aria2c.exe")
    local = os.path.join(BIN_DIR, f"aria2c{exe}")
    if p:
        tools["aria2c"] = p
    elif os.path.exists(local):
        tools["aria2c"] = local
    else:
        if not is_windows:
            _require_windows("aria2c")
        zpath = os.path.join(BIN_DIR, "aria2.zip")
        _download(ARIA2_URL, zpath, "the speed booster", callbacks)
        got = _extract_members(zpath, {"aria2c.exe"}, BIN_DIR)
        os.remove(zpath)
        if "aria2c.exe" not in got:
            raise ToolInstallError(
                "The speed booster download was incomplete. Please check your "
                "internet connection and start Luma again."
            )
        tools["aria2c"] = got["aria2c.exe"]

    # ---- ffmpeg + ffprobe -------------------------------------------------
    ff = _which("ffmpeg") or _which("ffmpeg.exe")
    fp = _which("ffprobe") or _which("ffprobe.exe")
    local_ff = os.path.join(BIN_DIR, f"ffmpeg{exe}")
    local_fp = os.path.join(BIN_DIR, f"ffprobe{exe}")
    if ff and fp:
        tools["ffmpeg"], tools["ffprobe"] = ff, fp
    elif os.path.exists(local_ff) and os.path.exists(local_fp):
        tools["ffmpeg"], tools["ffprobe"] = local_ff, local_fp
    else:
        if not is_windows:
            _require_windows("ffmpeg")
        zpath = os.path.join(BIN_DIR, "ffmpeg.zip")
        _download(FFMPEG_URL, zpath, "the video merger (this one is large)",
                  callbacks)
        got = _extract_members(zpath, {"ffmpeg.exe", "ffprobe.exe"}, BIN_DIR)
        os.remove(zpath)
        if "ffmpeg.exe" not in got or "ffprobe.exe" not in got:
            raise ToolInstallError(
                "The video merger download was incomplete. Please check your "
                "internet connection and start Luma again."
            )
        tools["ffmpeg"], tools["ffprobe"] = got["ffmpeg.exe"], got["ffprobe.exe"]

    # Make the local bin visible to child processes too.
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

    # Keep yt-dlp fresh -- YouTube breaks it often; a stale copy = failures.
    _maybe_update_ytdlp(
        tools["yt-dlp"],
        local_managed=os.path.dirname(tools["yt-dlp"]) == BIN_DIR,
        callbacks=callbacks,
    )

    return tools


def _maybe_update_ytdlp(path, local_managed, callbacks):
    """Best-effort self-update of the yt-dlp we manage (portable exe)."""
    if not local_managed:
        return
    try:
        callbacks.on_status("Checking for updates...")
        subprocess.run(
            [path, "-U"],
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # not fatal
