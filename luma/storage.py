import json
import os
import tempfile
import threading

_write_lock = threading.Lock()


def safe_read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return default
    except Exception:
        return default
    return data if data is not None else default


def atomic_write_json(path, data):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        return False

    tmp_name = None
    with _write_lock:
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=os.path.basename(path) + ".", suffix=".tmp",
                dir=directory,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
            return True
        except (OSError, TypeError, ValueError):
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            return False


def read_list(path, limit=None):
    data = safe_read_json(path, default=[])
    if not isinstance(data, list):
        return []
    clean = [item for item in data if isinstance(item, dict)]
    return clean[:limit] if limit else clean


def append_capped(path, record, cap=2000):
    items = read_list(path)
    items.insert(0, record)
    if len(items) > cap:
        items = items[:cap]
    return atomic_write_json(path, items)
