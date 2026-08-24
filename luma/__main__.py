import datetime
import os
import sys
import traceback

from . import APP_NAME
from .locations import CRASH_LOG, ensure_log_dir


MAX_LOG_BYTES = 256 * 1024
KEEP_LOG_BYTES = 64 * 1024


def _trim_log():
    try:
        if os.path.getsize(CRASH_LOG) <= MAX_LOG_BYTES:
            return
        with open(CRASH_LOG, "rb") as fh:
            fh.seek(-KEEP_LOG_BYTES, os.SEEK_END)
            tail = fh.read()
        with open(CRASH_LOG, "wb") as fh:
            fh.write(b"[earlier entries removed]\n")
            fh.write(tail)
    except OSError:
        pass


def _record_crash(exc):
    try:
        ensure_log_dir()
        _trim_log()
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(CRASH_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"\n{'=' * 60}\n{stamp}\n{'=' * 60}\n")
            traceback.print_exception(
                type(exc), exc, exc.__traceback__, file=fh
            )
        return CRASH_LOG
    except Exception:
        return None


def _shutdown_downloads():
    try:
        from .engine.download import terminate_all
        terminate_all()
    except Exception:
        pass


def main():
    try:
        from .app import LumaApp
        LumaApp().run()
        return 0
    except KeyboardInterrupt:
        _shutdown_downloads()
        return 130
    except Exception as exc:
        _shutdown_downloads()
        path = _record_crash(exc)
        print(f"\n{APP_NAME} ran into an unexpected problem and had to stop.")
        if path:
            print(f"Details were saved to:\n  {path}")
        print("Starting Luma again usually clears it.")
        return 1
    finally:
        _shutdown_downloads()


if __name__ == "__main__":
    sys.exit(main())
