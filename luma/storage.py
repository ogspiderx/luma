"""
Reading and writing Luma's JSON files without ever losing them.

Two rules hold everywhere Luma touches disk:

* A write is atomic. Data goes to a temporary file first and is then moved
  into place, so an interruption mid-write leaves the previous file intact
  rather than a half-written one.
* A read never raises. A missing, empty, truncated or garbled file yields the
  caller's default, because a corrupt settings file must not stop the app from
  starting.
"""

import json
import os
import tempfile
import threading

#: Serialising writes keeps two threads from interleaving on the same file.
_write_lock = threading.Lock()


def safe_read_json(path, default=None):
    """Return the parsed contents of `path`, or `default` if anything is wrong."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return default
    except Exception:                                  # noqa: BLE001
        return default
    return data if data is not None else default


def atomic_write_json(path, data):
    """Write `data` to `path` atomically. Returns True on success."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        return False

    tmp_name = None
    with _write_lock:
        try:
            # Write to a temp file in the same directory so the final move is
            # a rename on the same filesystem, which is atomic.
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
    """Read a JSON list, tolerating any corruption. Newest entries first."""
    data = safe_read_json(path, default=[])
    if not isinstance(data, list):
        return []
    clean = [item for item in data if isinstance(item, dict)]
    return clean[:limit] if limit else clean


def append_capped(path, record, cap=2000):
    """Prepend `record` to the list in `path`, keeping at most `cap` entries."""
    items = read_list(path)
    items.insert(0, record)
    if len(items) > cap:
        items = items[:cap]
    return atomic_write_json(path, items)
