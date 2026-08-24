import os
import re

from .errors import UnsafePathError

_ILLEGAL_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_FORBIDDEN_ROOTS = (
    "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/boot", "/dev",
    "/proc", "/sys",
)


def sanitize_filename(name, limit=120):
    cleaned = _ILLEGAL_FILENAME.sub("", name or "").strip().rstrip(". ")
    return (cleaned or "download")[:limit]


_ID_SUFFIX = re.compile(r"\s*\[[A-Za-z0-9_-]{11}\]$")
_FORMAT_SUFFIX = re.compile(r"\.f\d+$")


def title_from_filename(path):
    if not path:
        return ""
    name = re.split(r"[\\/]", str(path).strip())[-1]
    name = os.path.splitext(name)[0]
    name = _FORMAT_SUFFIX.sub("", name)
    name = _ID_SUFFIX.sub("", name)
    return name.strip()


def expand(path):
    expanded = os.path.expandvars(os.path.expanduser(str(path or "").strip()))
    return os.path.abspath(expanded)


def safe_join(base, *parts):
    base_abs = expand(base)
    safe_parts = [sanitize_filename(p) for p in parts if str(p).strip()]
    candidate = os.path.abspath(os.path.join(base_abs, *safe_parts))

    if not (candidate == base_abs
            or candidate.startswith(base_abs + os.sep)):
        raise UnsafePathError(
            "That folder location is not allowed. Please choose a different "
            "folder in Settings."
        )
    return candidate


def validate_output_dir(path):
    raw = str(path or "").strip()
    if not raw:
        raise UnsafePathError("Please choose a folder to save downloads in.")

    resolved = expand(raw)

    lowered = resolved.lower() if os.name == "nt" else resolved
    for root in _FORBIDDEN_ROOTS:
        if lowered == root or lowered.startswith(root + os.sep):
            raise UnsafePathError(
                "That is a system folder. Please choose somewhere like your "
                "Videos or Downloads folder instead."
            )

    probe = resolved
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    if not os.path.isdir(probe):
        raise UnsafePathError("That folder location does not exist.")
    if not os.access(probe, os.W_OK):
        raise UnsafePathError(
            "Luma does not have permission to save files there."
        )
    return resolved


def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise UnsafePathError(
            f"Could not create that folder ({exc.strerror or exc})."
        ) from exc
    return path
