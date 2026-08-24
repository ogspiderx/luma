"""
Finding out what a link is actually available in.

Used when the person has asked to choose the quality themselves: rather than
offering a fixed list and failing later, Luma asks the site what it has and
offers only that.
"""

import json
import subprocess

from .callbacks import EngineCallbacks

#: Heights worth naming, largest first. Anything taller is called by its number.
_LABELS = {
    2160: "4K",
    1440: "1440p",
    1080: "1080p",
    720: "720p",
    480: "480p",
    360: "360p",
    240: "240p",
    144: "144p",
}


def describe_height(height):
    """A friendly name for a video height."""
    try:
        value = int(height)
    except (TypeError, ValueError):
        return "Unknown"
    return _LABELS.get(value, f"{value}p")


def size_note(bytes_estimate):
    """Roughly how big, for the chooser. Empty when it cannot be told."""
    if not bytes_estimate:
        return ""
    value = float(bytes_estimate)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"about {value:.0f} {unit}" if unit in ("B", "KB") \
                else f"about {value:.1f} {unit}"
        value /= 1024
    return ""


def available_qualities(ytdlp, url, callbacks=None, timeout=90):
    """Ask the site what this link can be downloaded in.

    Returns (title, choices) where each choice is
    {height, label, note, filesize} sorted best first. On any failure the
    choices come back empty and the caller should fall back to its setting
    rather than treating it as an error.
    """
    callbacks = callbacks or EngineCallbacks()
    callbacks.on_status("Checking what qualities are available...")

    cmd = [ytdlp, "--no-playlist", "--no-warnings", "-J", url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout)
        if out.returncode != 0 or not out.stdout.strip():
            return "", []
        info = json.loads(out.stdout)
    except Exception:                                  # noqa: BLE001
        return "", []

    title = info.get("title") or ""
    formats = info.get("formats")
    if not isinstance(formats, list):
        return title, []

    # Keep the best-looking option at each height, measured by file size so
    # the estimate shown to the person is the one they would actually get.
    best_at = {}
    for entry in formats:
        if not isinstance(entry, dict):
            continue
        if entry.get("vcodec") in (None, "none"):
            continue                                   # sound only
        height = entry.get("height")
        if not height:
            continue
        size = (entry.get("filesize") or entry.get("filesize_approx") or 0)
        current = best_at.get(height)
        if current is None or size > current:
            best_at[height] = size

    # Sound is fetched alongside the picture, so add a rough allowance to the
    # estimate rather than quoting only half of what will be downloaded.
    audio_size = 0
    for entry in formats:
        if not isinstance(entry, dict):
            continue
        if entry.get("acodec") in (None, "none"):
            continue
        if entry.get("vcodec") not in (None, "none"):
            continue
        audio_size = max(
            audio_size,
            entry.get("filesize") or entry.get("filesize_approx") or 0,
        )

    choices = []
    for height in sorted(best_at, reverse=True):
        size = best_at[height]
        total = (size + audio_size) if size else 0
        choices.append({
            "height": height,
            "label": describe_height(height),
            "note": size_note(total),
            "filesize": total,
        })
    return title, choices
