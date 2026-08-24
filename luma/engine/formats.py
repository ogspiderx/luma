import json
import subprocess

from .callbacks import EngineCallbacks

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
    try:
        value = int(height)
    except (TypeError, ValueError):
        return "Unknown"
    return _LABELS.get(value, f"{value}p")


def size_note(bytes_estimate):
    if not bytes_estimate:
        return ""
    value = float(bytes_estimate)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"about {value:.0f} {unit}" if unit in ("B", "KB") \
                else f"about {value:.1f} {unit}"
        value /= 1024
    return ""


def available_qualities(ytdlp, url, callbacks=None, timeout=45):
    callbacks = callbacks or EngineCallbacks()
    callbacks.on_status("Checking what qualities are available...")

    cmd = [ytdlp, "--no-playlist", "--no-warnings",
           "--socket-timeout", "15", "--extractor-retries", "1",
           "-J", url]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout)
        if out.returncode != 0 or not out.stdout.strip():
            return "", []
        info = json.loads(out.stdout)
    except Exception:
        return "", []

    title = info.get("title") or ""
    formats = info.get("formats")
    if not isinstance(formats, list):
        return title, []

    best_at = {}
    for entry in formats:
        if not isinstance(entry, dict):
            continue
        if entry.get("vcodec") in (None, "none"):
            continue
        height = entry.get("height")
        if not height:
            continue
        size = (entry.get("filesize") or entry.get("filesize_approx") or 0)
        current = best_at.get(height)
        if current is None or size > current:
            best_at[height] = size

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
