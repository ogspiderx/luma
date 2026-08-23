"""
Luma's entry point.

Anything that escapes the application is written to a crash log rather than
spilling a traceback over the user's terminal, and any running downloads are
shut down so no child processes are left behind.
"""

import datetime
import sys
import traceback

from . import APP_NAME
from .locations import CRASH_LOG, ensure_log_dir


def _record_crash(exc):
    """Append a crash to the log. Returns the log path, or None if it failed."""
    try:
        ensure_log_dir()
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
    """Never leave orphaned downloader processes behind."""
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
    except Exception as exc:                      # noqa: BLE001
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
