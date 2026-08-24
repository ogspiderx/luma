import os
import sys

_DOWNLOADS_FOLDER_ID = "{374DE290-123F-4565-9164-39C4925E467B}"


def _frozen():
    return bool(getattr(sys, "frozen", False))


def app_dir():
    if _frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = app_dir()

INSTALLED_MARKER = os.path.join(APP_DIR, ".installed_app")


def is_installed_build():
    return _frozen() and os.path.exists(INSTALLED_MARKER)


def _local_appdata():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return base
    return os.path.join(os.path.expanduser("~"), ".local", "share")


def _known_folder_path(guid):
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        rfid = GUID()
        ctypes.windll.ole32.CLSIDFromString(
            ctypes.c_wchar_p(guid), ctypes.byref(rfid)
        )
        path_ptr = ctypes.c_wchar_p()
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(rfid), 0, 0, ctypes.byref(path_ptr)
        )
        if result != 0 or not path_ptr.value:
            return None
        value = path_ptr.value
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)
        return value
    except Exception:
        return None


def downloads_folder():
    found = _known_folder_path(_DOWNLOADS_FOLDER_ID)
    if found and os.path.isdir(found):
        return found
    return os.path.join(os.path.expanduser("~"), "Downloads")


if is_installed_build():
    STATE_DIR = os.path.join(_local_appdata(), "Luma")
    DEFAULT_DOWNLOAD_DIR = downloads_folder()
else:
    STATE_DIR = APP_DIR
    DEFAULT_DOWNLOAD_DIR = os.path.join(APP_DIR, "downloads")

CONFIG_PATH = os.path.join(STATE_DIR, "config.json")
HISTORY_PATH = os.path.join(STATE_DIR, "history.json")
ERRORS_PATH = os.path.join(STATE_DIR, "errors.json")

LOG_DIR = os.path.join(STATE_DIR, "logs")
CRASH_LOG = os.path.join(LOG_DIR, "crash.log")

BIN_DIR = os.path.join(STATE_DIR, "bin")


def ensure_log_dir():
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass
    return LOG_DIR
