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
from ..locations import BIN_DIR


def _download(url, dest, desc, callbacks):
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


# Away from Windows the three tools come from the system, not from us -- the
# releases Luma fetches are Windows binaries. Asking for them one at a time
# meant a person installed one, restarted Luma, and was told about the next:
# three rounds to reach a working app. They are all named at once instead, in
# the form the distribution actually wants, since the command is aria2c but
# the package that carries it is called aria2.
_SYSTEM_PACKAGES = {
    "yt-dlp": "yt-dlp",
    "aria2c": "aria2",
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffmpeg",
}

_INSTALLERS = (
    ("pacman", "sudo pacman -S --needed {packages}"),
    ("apt", "sudo apt install {packages}"),
    ("dnf", "sudo dnf install {packages}"),
    ("zypper", "sudo zypper install {packages}"),
    ("apk", "sudo apk add {packages}"),
    ("brew", "brew install {packages}"),
)


def _install_command(tools_missing):
    packages = sorted({_SYSTEM_PACKAGES.get(t, t) for t in tools_missing})
    for manager, template in _INSTALLERS:
        if _which(manager):
            return template.format(packages=" ".join(packages))
    return None


def _missing_system_tools():
    missing = []
    for command in ("yt-dlp", "aria2c", "ffmpeg", "ffprobe"):
        if _which(command) or os.path.exists(os.path.join(BIN_DIR, command)):
            continue
        missing.append(command)
    return missing


def _require_system_tools():
    missing = _missing_system_tools()
    if not missing:
        return
    names = ", ".join(missing)
    one = len(missing) == 1
    command = _install_command(missing)
    if command:
        raise ToolInstallError(
            f"Luma needs {names}, which {'is' if one else 'are'} not "
            f"installed. Install {'it' if one else 'them'} with:  {command}  "
            f"- then start Luma again."
        )
    raise ToolInstallError(
        f"Luma needs {names}, which {'is' if one else 'are'} not installed. "
        f"Please install {'it' if one else 'them'} with your system's package "
        f"manager, then start Luma again."
    )


def _require_windows(tool):
    raise ToolInstallError(
        f"{tool} is not installed, and it can only be installed automatically "
        f"on Windows. Please install {tool} using your system's package "
        f"manager, then start Luma again."
    )


def ensure_tools(callbacks=None):
    callbacks = callbacks or EngineCallbacks()
    os.makedirs(BIN_DIR, exist_ok=True)
    is_windows = os.name == "nt"
    exe = ".exe" if is_windows else ""

    if not is_windows:
        _require_system_tools()

    tools = {}

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

    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

    _maybe_update_ytdlp(
        tools["yt-dlp"],
        local_managed=os.path.dirname(tools["yt-dlp"]) == BIN_DIR,
        callbacks=callbacks,
    )

    return tools


_update_checked = False


def reset_update_state():
    global _update_checked
    _update_checked = False


def _maybe_update_ytdlp(path, local_managed, callbacks):
    global _update_checked
    if not local_managed or _update_checked:
        return
    _update_checked = True
    try:
        callbacks.on_status("Checking for updates...")
        subprocess.run(
            [path, "-U"],
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
