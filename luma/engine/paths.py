"""
Path handling that refuses to write outside where it is supposed to.

Any folder that originates from user input passes through here before it is
used as a download target.
"""

import os
import re

from .errors import UnsafePathError

#: Characters Windows forbids in a filename, plus control characters.
_ILLEGAL_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Directories we refuse to write into even if the user asks.
_FORBIDDEN_ROOTS = (
    "/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/boot", "/dev",
    "/proc", "/sys",
)


def sanitize_filename(name, limit=120):
    """Make a string safe to use as a single filename component."""
    cleaned = _ILLEGAL_FILENAME.sub("", name or "").strip().rstrip(". ")
    return (cleaned or "download")[:limit]


def expand(path):
    """Expand ~ and environment variables, then make the path absolute."""
    expanded = os.path.expandvars(os.path.expanduser(str(path or "").strip()))
    return os.path.abspath(expanded)


def safe_join(base, *parts):
    """Join `parts` onto `base`, refusing anything that escapes `base`.

    Raises UnsafePathError if the result would land outside `base`.
    """
    base_abs = expand(base)
    # Each part is reduced to a safe single component -- this is what stops
    # "../.." or an absolute path from being smuggled in through a setting.
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
    """Check a user-chosen download folder is somewhere sane and writable.

    Returns the resolved absolute path, or raises UnsafePathError.
    """
    raw = str(path or "").strip()
    if not raw:
        raise UnsafePathError("Please choose a folder to save downloads in.")

    resolved = expand(raw)

    # Refuse system directories outright.
    lowered = resolved.lower() if os.name == "nt" else resolved
    for root in _FORBIDDEN_ROOTS:
        if lowered == root or lowered.startswith(root + os.sep):
            raise UnsafePathError(
                "That is a system folder. Please choose somewhere like your "
                "Videos or Downloads folder instead."
            )

    # The folder itself need not exist yet, but its nearest existing parent
    # has to be a real, writable directory.
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
    """Create `path` if needed and return it. Raises UnsafePathError on failure."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise UnsafePathError(
            f"Could not create that folder ({exc.strerror or exc})."
        ) from exc
    return path
