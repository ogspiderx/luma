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
from .theme import DEFAULT_THEME, THEME_NAMES

FOLDER_CHOICES = ("none", "date", "playlist")

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
    if not isinstance(raw, dict):
        raw = {}

    cfg = dict(DEFAULTS)

    candidate = raw.get("output_dir") or DEFAULTS["output_dir"]
    try:
        cfg["output_dir"] = validate_output_dir(candidate)
    except UnsafePathError:
        cfg["output_dir"] = DEFAULTS["output_dir"]

    folders = str(raw.get("folders", DEFAULTS["folders"])).lower()
    cfg["folders"] = folders if folders in FOLDER_CHOICES else DEFAULTS["folders"]

    quality = str(raw.get("quality", DEFAULTS["quality"])).lower()
    cfg["quality"] = quality if quality in QUALITY_CHOICES else DEFAULTS["quality"]

    theme = raw.get("theme")
    cfg["theme"] = theme if theme in THEME_NAMES else DEFAULTS["theme"]

    cfg["max_parallel"] = _clamp(
        _as_int(raw.get("max_parallel"), DEFAULTS["max_parallel"]),
        1, MAX_PARALLEL_LIMIT,
    )
    cfg["conns_per_file"] = _clamp(
        _as_int(raw.get("conns_per_file"), DEFAULTS["conns_per_file"]),
        1, ARIA2_MAX_PER_FILE,
    )

    cfg["archive"] = bool(raw.get("archive", DEFAULTS["archive"]))
    cfg["skip_speedtest"] = bool(
        raw.get("skip_speedtest", DEFAULTS["skip_speedtest"])
    )
    cfg["ask_quality"] = bool(raw.get("ask_quality", DEFAULTS["ask_quality"]))
    return cfg


def load_config(path=CONFIG_PATH):
    return normalize(safe_read_json(path, default={}))


def save_config(config, path=CONFIG_PATH):
    return atomic_write_json(path, normalize(config))


def resolve_output_dir(config, playlist_name=None):
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
