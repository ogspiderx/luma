"""
Tuning constants and pinned tool URLs for Luma's download engine.

These values are ported verbatim from the proven CLI tool (yt_turbo.py).
Do not change them without a measured reason -- the concurrency maths in
plan.py is calibrated against them.
"""

# --------------------------------------------------------------------------- #
#  Pinned, no-admin portable Windows builds of the tools we shell out to.      #
# --------------------------------------------------------------------------- #

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
ARIA2_URL = ("https://github.com/aria2/aria2/releases/download/"
             "release-1.37.0/aria2-1.37.0-win-64bit-build1.zip")
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
              "latest/ffmpeg-master-latest-win64-gpl.zip")

# Cloudflare's public speed-test endpoint. Returns `bytes` of throwaway data.
SPEEDTEST_URL = "https://speed.cloudflare.com/__down?bytes={n}"
SPEEDTEST_HOST = "speed.cloudflare.com"

# --------------------------------------------------------------------------- #
#  Concurrency limits                                                          #
# --------------------------------------------------------------------------- #

MAX_TOTAL_CONNECTIONS = 64   # total sockets we are willing to open at once
ARIA2_MAX_PER_FILE = 16      # aria2c's per-server connection ceiling
DEFAULT_MAX_PARALLEL = 8     # default cap on simultaneous video downloads
MAX_ATTEMPTS = 4             # tries per video before giving up (resumes each time)

# Rough ceiling for what ONE YouTube video stream delivers once YouTube's
# per-connection throttling kicks in. This is deliberately well below a raw
# TCP stream's speed -- it is why parallel *videos* (not just parallel
# connections) are what fill a fast line on a playlist.
YT_PER_VIDEO_MBPS_CAP = 35.0

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Quality options offered in Settings. "best" means "no height cap".
QUALITY_CHOICES = ("360", "480", "720", "best")
DEFAULT_QUALITY = "480"


def human(n):
    """Format a byte count as a short human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
