YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
ARIA2_URL = ("https://github.com/aria2/aria2/releases/download/"
             "release-1.37.0/aria2-1.37.0-win-64bit-build1.zip")
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
              "latest/ffmpeg-master-latest-win64-gpl.zip")

SPEEDTEST_URL = "https://speed.cloudflare.com/__down?bytes={n}"
SPEEDTEST_HOST = "speed.cloudflare.com"


MAX_TOTAL_CONNECTIONS = 64
ARIA2_MAX_PER_FILE = 16
DEFAULT_MAX_PARALLEL = 8
MAX_ATTEMPTS = 4

YT_PER_VIDEO_MBPS_CAP = 35.0

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

QUALITY_CHOICES = ("360", "480", "720", "best")
DEFAULT_QUALITY = "480"


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
