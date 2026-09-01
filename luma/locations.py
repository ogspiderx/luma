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


def _xdg_home(variable, *fallback):
    base = os.environ.get(variable)
    if base and os.path.isabs(base):
        return base
    return os.path.join(os.path.expanduser("~"), *fallback)


def _local_appdata():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return base
        return os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return _xdg_home("XDG_DATA_HOME", ".local", "share")


def _xdg_download_dir():
    """Where this desktop actually keeps downloads.

    KDE and GNOME both record it here, and both translate the folder name,
    so a German Plasma install downloads to Downloads only by coincidence.
    """
    path = os.path.join(_xdg_home("XDG_CONFIG_HOME", ".config"),
                        "user-dirs.dirs")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line.startswith("XDG_DOWNLOAD_DIR"):
                    continue
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                value = value.replace("$HOME", os.path.expanduser("~"))
                if value:
                    return os.path.abspath(value)
    except (OSError, IndexError, UnicodeDecodeError):
        pass
    return None


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
    if os.name == "nt":
        found = _known_folder_path(_DOWNLOADS_FOLDER_ID)
    else:
        found = _xdg_download_dir()
    if found and os.path.isdir(found):
        return found
    return os.path.join(os.path.expanduser("~"), "Downloads")


def _beside_the_app():
    """Can a portable copy keep its things next to itself?

    On Windows it always can. On Linux the same files may have been put
    somewhere deliberately read-only -- /opt, or /usr/share from a package --
    and then nothing beside the app is writable and the profile is the only
    sensible home.
    """
    return os.path.isdir(APP_DIR) and os.access(APP_DIR, os.W_OK)


def _state_dir():
    override = os.environ.get("LUMA_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if is_installed_build() or not _beside_the_app():
        return os.path.join(_local_appdata(), "Luma")
    return APP_DIR


STATE_DIR = _state_dir()

if STATE_DIR == APP_DIR:
    DEFAULT_DOWNLOAD_DIR = os.path.join(APP_DIR, "downloads")
else:
    DEFAULT_DOWNLOAD_DIR = downloads_folder()

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
