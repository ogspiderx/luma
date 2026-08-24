"""
Luma's settings: what they are, what they default to, and how they are kept
sane.

Values coming off disk are never trusted. Everything is checked and clamped on
load, so a hand-edited or damaged config file degrades to something workable
instead of breaking the app.
"""

import os

from .engine.constants import (
    ARIA2_MAX_PER_FILE,
    DEFAULT_MAX_PARALLEL,
    DEFAULT_QUALITY,
    QUALITY_CHOICES,
)
from .engine.errors import UnsafePathError
from .engine.paths import ensure_dir, safe_join, validate_output_dir
from .locations import CONFIG_PATH, DEFAULT_DOWNLOAD_DIR
from .storage import atomic_write_json, safe_read_json
from .theme import DEFAULT_THEME

#: How finished files are grouped inside the download folder.
FOLDER_CHOICES = ("none", "date", "playlist")

#: Upper bound offered for simultaneous videos.
MAX_PARALLEL_LIMIT = 12

DEFAULTS = {
    "output_dir": DEFAULT_DOWNLOAD_DIR,
    "folders": "none",
    "quality": DEFAULT_QUALITY,
    "ask_quality": False,
    "max_parallel": DEFAULT_MAX_PARALLEL,
    "conns_per_file": ARIA2_MAX_PER_FILE,
    "theme": DEFAULT_THEME,
    "archive": True,
    "skip_speedtest": False,
}


def _as_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clamp(value, low, high):
    return max(low, min(high, value))


def normalize(raw):
    """Turn whatever came off disk into a complete, safe settings dict."""
    if not isinstance(raw, dict):
        raw = {}

    cfg = dict(DEFAULTS)

    # -- download folder: must be usable, else fall back to the default ----
    candidate = raw.get("output_dir") or DEFAULTS["output_dir"]
    try:
        cfg["output_dir"] = validate_output_dir(candidate)
    except UnsafePathError:
        cfg["output_dir"] = DEFAULTS["output_dir"]

    # -- simple choices ----------------------------------------------------
    folders = str(raw.get("folders", DEFAULTS["folders"])).lower()
    cfg["folders"] = folders if folders in FOLDER_CHOICES else DEFAULTS["folders"]

    quality = str(raw.get("quality", DEFAULTS["quality"])).lower()
    cfg["quality"] = quality if quality in QUALITY_CHOICES else DEFAULTS["quality"]

    theme = raw.get("theme")
    cfg["theme"] = theme if isinstance(theme, str) and theme else DEFAULTS["theme"]

    # -- numbers: clamped into a range that cannot hurt the machine --------
    cfg["max_parallel"] = _clamp(
        _as_int(raw.get("max_parallel"), DEFAULTS["max_parallel"]),
        1, MAX_PARALLEL_LIMIT,
    )
    cfg["conns_per_file"] = _clamp(
        _as_int(raw.get("conns_per_file"), DEFAULTS["conns_per_file"]),
        1, ARIA2_MAX_PER_FILE,
    )

    # -- switches ----------------------------------------------------------
    cfg["archive"] = bool(raw.get("archive", DEFAULTS["archive"]))
    cfg["skip_speedtest"] = bool(
        raw.get("skip_speedtest", DEFAULTS["skip_speedtest"])
    )
    cfg["ask_quality"] = bool(raw.get("ask_quality", DEFAULTS["ask_quality"]))
    return cfg


def load_config(path=CONFIG_PATH):
    """Load settings, falling back to defaults for anything missing or broken."""
    return normalize(safe_read_json(path, default={}))


def save_config(config, path=CONFIG_PATH):
    """Write settings back to disk. Returns True on success."""
    return atomic_write_json(path, normalize(config))


def resolve_output_dir(config, playlist_name=None):
    """Work out the folder this download should actually land in.

    Honours the folder-grouping setting, keeps the result inside the chosen
    download folder, and creates it. Raises UnsafePathError if the location
    cannot be used.
    """
    base = validate_output_dir(config.get("output_dir")
                               or DEFAULTS["output_dir"])
    scheme = config.get("folders", "none")

    if scheme == "date":
        import datetime
        target = safe_join(base, datetime.date.today().isoformat())
    elif scheme == "playlist" and playlist_name:
        target = safe_join(base, playlist_name)
    else:
        target = base

    return ensure_dir(target)


def describe(config):
    """Plain-language summary of the current settings, for display."""
    quality = config["quality"]
    quality_text = "Best available" if quality == "best" else f"{quality}p"
    folders = {
        "none": "All in one folder",
        "date": "A folder per day",
        "playlist": "A folder per playlist",
    }.get(config["folders"], "All in one folder")
    return [
        f"Save to: {config['output_dir']}",
        f"Quality: {quality_text}",
        f"Organise: {folders}",
        f"Videos at once: {config['max_parallel']}",
    ]
