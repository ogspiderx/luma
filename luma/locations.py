import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(APP_DIR, "config.json")
HISTORY_PATH = os.path.join(APP_DIR, "history.json")
ERRORS_PATH = os.path.join(APP_DIR, "errors.json")

LOG_DIR = os.path.join(APP_DIR, "logs")
CRASH_LOG = os.path.join(LOG_DIR, "crash.log")

DEFAULT_DOWNLOAD_DIR = os.path.join(APP_DIR, "downloads")


def ensure_log_dir():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass
    return LOG_DIR
