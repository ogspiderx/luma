import datetime
import os

from .engine.paths import title_from_filename
from .locations import ERRORS_PATH, HISTORY_PATH
from .storage import append_capped, read_list

HISTORY_CAP = 2000
ERRORS_CAP = 500


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _title_from_path(path):
    return title_from_filename(path) or "Unknown video"


def _size_of(path):
    try:
        return os.path.getsize(path)
    except (OSError, TypeError):
        return None


def record_success(url, filepath, quality=None, path=HISTORY_PATH):
    try:
        return append_capped(path, {
            "title": _title_from_path(filepath),
            "url": url,
            "when": _now(),
            "file": filepath or "",
            "size": _size_of(filepath),
            "quality": quality,
        }, cap=HISTORY_CAP)
    except Exception:
        return False


def record_failure(url, reason, path=ERRORS_PATH):
    try:
        return append_capped(path, {
            "url": url,
            "reason": reason or "The download did not finish.",
            "when": _now(),
        }, cap=ERRORS_CAP)
    except Exception:
        return False


def record_results(results, quality=None, history_path=HISTORY_PATH,
                   errors_path=ERRORS_PATH):
    saved = failed = 0
    for item in results:
        try:
            url, ok, reason, filepath = item
        except (TypeError, ValueError):
            continue
        if ok:
            record_success(url, filepath, quality, history_path)
            saved += 1
        else:
            record_failure(url, reason, errors_path)
            failed += 1
    return saved, failed


def recent_downloads(limit=200, path=HISTORY_PATH):
    return read_list(path, limit=limit)


def recent_failures(limit=200, path=ERRORS_PATH):
    return read_list(path, limit=limit)


def human_size(size):
    if not isinstance(size, (int, float)) or size <= 0:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


def human_when(stamp):
    try:
        moment = datetime.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or "-"
    today = datetime.date.today()
    if moment.date() == today:
        return f"Today {moment.strftime('%H:%M')}"
    if (today - moment.date()).days == 1:
        return f"Yesterday {moment.strftime('%H:%M')}"
    return moment.strftime("%d %b %Y %H:%M")
