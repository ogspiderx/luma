"""
Where Luma keeps its files.

Luma is portable: everything it creates lives beside the application folder,
so moving or deleting that folder takes all of its state with it. Nothing is
written to system locations.
"""

import os

#: The Luma project folder (the one containing the `luma` package).
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_PATH = os.path.join(APP_DIR, "config.json")
HISTORY_PATH = os.path.join(APP_DIR, "history.json")
ERRORS_PATH = os.path.join(APP_DIR, "errors.json")

LOG_DIR = os.path.join(APP_DIR, "logs")
CRASH_LOG = os.path.join(LOG_DIR, "crash.log")

#: Where downloads go unless the user picks somewhere else in Settings.
DEFAULT_DOWNLOAD_DIR = os.path.join(APP_DIR, "downloads")


def ensure_log_dir():
    """Create the log folder if it isn't there yet. Never raises."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass
    return LOG_DIR
