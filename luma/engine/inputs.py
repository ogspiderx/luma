"""
Turning whatever the user pasted into a clean list of video URLs.

Adds a strict scheme allowlist on top of the ported logic: only http/https
URLs are ever accepted, and validation happens before a URL reaches yt-dlp or
is written to any file on disk.
"""

import os
import re
import subprocess
from urllib.parse import urlparse

from .callbacks import EngineCallbacks
from .errors import InvalidURLError

#: The only URL schemes Luma will ever hand to an external tool.
ALLOWED_SCHEMES = ("http", "https")

#: Hosts Luma understands. This version is YouTube-only by design.
_YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
)


def is_valid_url(url):
    """True if `url` is a syntactically valid http(s) URL."""
    try:
        parsed = urlparse(url.strip())
    except (ValueError, AttributeError):
        return False
    return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.netloc)


def is_youtube_url(url):
    """True if `url` points at a host Luma supports."""
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except (ValueError, AttributeError):
        return False
    return host in _YOUTUBE_HOSTS


def validate_url(url):
    """Return a cleaned URL, or raise InvalidURLError with a readable reason."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise InvalidURLError("Please paste a link first.")
    if not is_valid_url(cleaned):
        raise InvalidURLError(
            "That does not look like a web link. Links should start with "
            "http:// or https://"
        )
    if not is_youtube_url(cleaned):
        raise InvalidURLError(
            "Luma only supports YouTube links at the moment."
        )
    return cleaned


def gather_inputs(raw_inputs):
    """Split each item into either a URL or the lines of a .txt file.

    Invalid entries are skipped rather than aborting the batch; the caller
    gets back only URLs that passed validation, plus the rejects.

    Returns (urls, rejected) where `rejected` is a list of (text, reason).
    """
    urls, rejected = [], []
    for item in raw_inputs:
        candidates = []
        if os.path.isfile(item):
            try:
                with open(item, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            candidates.append(line)
            except OSError as exc:
                rejected.append((item, f"Could not read that file ({exc})."))
                continue
        else:
            candidates.append(item.strip())

        for candidate in candidates:
            try:
                urls.append(validate_url(candidate))
            except InvalidURLError as exc:
                rejected.append((candidate, exc.user_message))
    return urls, rejected


def split_pasted_text(text):
    """Split a pasted blob into individual candidate links."""
    return [part for part in re.split(r"[\s,]+", text or "") if part]


def _is_playlist_like(url):
    """True only for URLs that should be expanded into many videos.

    A plain watch/youtu.be link is treated as a single video even if it carries
    a `list=` autoplay/mix parameter, so we never balloon into a radio mix.
    """
    u = url.lower()
    if "/playlist" in u:
        return True
    for marker in ("/channel/", "/@", "/c/", "/user/"):
        if marker in u:
            return True
    return False


def expand_playlists(ytdlp, urls, callbacks=None):
    """Turn playlist / channel URLs into individual video URLs.

    Plain single-video links pass straight through untouched -- the downloader
    gets --no-playlist, so a `?list=RD...` autoplay tail is ignored and only
    that one video is fetched.
    """
    callbacks = callbacks or EngineCallbacks()
    flat = []
    seen = set()

    def add(u):
        if u and u not in seen and is_valid_url(u):
            seen.add(u)
            flat.append(u)

    for url in urls:
        # Plain video link -> no need to call yt-dlp; use it as-is.
        if not _is_playlist_like(url):
            add(url)
            continue

        # Real playlist / channel -> enumerate its videos.
        callbacks.on_status("Reading playlist...")
        cmd = [
            ytdlp, "--flat-playlist", "--no-warnings", "--yes-playlist",
            "--print", "%(url)s", url,
        ]
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180
            )
            lines = [
                ln.strip() for ln in out.stdout.splitlines()
                if ln.strip() and ln.strip().upper() != "NA"
            ]
            if lines:
                for ln in lines:
                    add(ln)
            else:
                callbacks.on_status("That playlist looked empty.")
                add(url)
        except Exception:
            callbacks.on_status("Could not read that playlist; trying it as a "
                                "single video.")
            add(url)
    return flat
