#!/usr/bin/env python3
"""
    python tests/test_packaging_paths.py
"""

import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import luma.locations as locations                                # noqa: E402
from luma.engine.paths import _forbidden_roots, validate_output_dir  # noqa: E402
from luma.engine.errors import UnsafePathError                    # noqa: E402

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


class as_frozen:
    def __init__(self, exe_path, installed=True):
        self._exe = exe_path
        self._installed = installed

    def __enter__(self):
        self._had_frozen = hasattr(sys, "frozen")
        self._old_frozen = getattr(sys, "frozen", None)
        self._old_exe = sys.executable
        sys.frozen = True
        sys.executable = self._exe
        if self._installed:
            marker = os.path.join(os.path.dirname(self._exe), ".installed_app")
            open(marker, "w").close()
        importlib.reload(locations)
        return locations

    def __exit__(self, *_exc):
        if self._had_frozen:
            sys.frozen = self._old_frozen
        else:
            del sys.frozen
        sys.executable = self._old_exe
        importlib.reload(locations)


def test_dev_mode_is_unchanged():
    print("\n[running from source]")
    check("not treated as installed", not locations.is_installed_build())
    check("state lives beside the package",
          locations.STATE_DIR == locations.APP_DIR, locations.STATE_DIR)
    check("downloads defaults beside the app",
          locations.DEFAULT_DOWNLOAD_DIR
          == os.path.join(locations.APP_DIR, "downloads"),
          locations.DEFAULT_DOWNLOAD_DIR)


def test_a_portable_frozen_build_stays_portable():
    print("\n[a frozen build with no installer marker]")
    with tempfile.TemporaryDirectory() as td:
        exe = os.path.join(td, "Luma.exe")
        open(exe, "w").close()
        with as_frozen(exe, installed=False) as mod:
            check("frozen alone does not count as installed",
                  not mod.is_installed_build())
            check("everything still lives beside the executable",
                  mod.STATE_DIR == td, mod.STATE_DIR)
            check("including the default download folder",
                  mod.DEFAULT_DOWNLOAD_DIR == os.path.join(td, "downloads"),
                  mod.DEFAULT_DOWNLOAD_DIR)


def test_an_installed_build_uses_appdata_and_downloads():
    print("\n[a build with the installer's marker present]")
    with tempfile.TemporaryDirectory() as td:
        exe = os.path.join(td, "Luma.exe")
        open(exe, "w").close()
        with as_frozen(exe, installed=True) as mod:
            check("counts as installed", mod.is_installed_build())
            check("state does not live beside the executable",
                  mod.STATE_DIR != td, mod.STATE_DIR)
            check("nor does the default download folder",
                  mod.DEFAULT_DOWNLOAD_DIR != os.path.join(td, "downloads"),
                  mod.DEFAULT_DOWNLOAD_DIR)
            check("the tool cache follows the state folder",
                  mod.BIN_DIR == os.path.join(mod.STATE_DIR, "bin"),
                  mod.BIN_DIR)
            for attr in ("CONFIG_PATH", "HISTORY_PATH", "ERRORS_PATH",
                        "CRASH_LOG"):
                path = getattr(mod, attr)
                check(f"{attr} sits under the state folder",
                      path.startswith(mod.STATE_DIR), path)


def test_the_marker_alone_does_nothing_unfrozen():
    print("\n[the marker file without being frozen]")
    with tempfile.TemporaryDirectory() as td:
        open(os.path.join(td, ".installed_app"), "w").close()
        check("a marker lying around does not matter to a dev run",
              not locations.is_installed_build())


def test_windows_system_roots_are_refused():
    """The literal env values must survive into the denylist somewhere.

    `expand()` runs each one through `os.path.abspath`, which mangles a
    backslash path on this POSIX sandbox (there is no such thing as `C:\\`
    here) rather than leaving it alone the way it would on real Windows.
    A substring check is what is actually true on both platforms; the exact
    end-to-end behaviour is confirmed for real further down, on Windows.
    """
    print("\n[Windows system folders are on the denylist]")
    old = {}
    fake = {
        "WINDIR": r"C:\Windows",
        "ProgramFiles": r"C:\Program Files",
        "ProgramFiles(x86)": r"C:\Program Files (x86)",
        "ProgramData": r"C:\ProgramData",
    }
    for key, value in fake.items():
        old[key] = os.environ.get(key)
        os.environ[key] = value
    try:
        roots = _forbidden_roots()
        for value in fake.values():
            check(f"{value} is in the denylist",
                  any(value in r for r in roots), str(roots))
        check("posix system folders are still covered too",
              "/etc" in roots, str(roots))
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_windows_roots_are_absent_without_the_env_vars():
    print("\n[no false positives when the variables are unset]")
    old = {}
    names = ("WINDIR", "SystemRoot", "ProgramFiles", "ProgramFiles(x86)",
             "ProgramW6432", "ProgramData")
    for key in names:
        old[key] = os.environ.pop(key, None)
    try:
        roots = _forbidden_roots()
        check("nothing Windows-shaped sneaks in",
              roots == list(roots) and not any("Program" in r or "Windows" in r
                                                for r in roots),
              str(roots))
    finally:
        for key, value in old.items():
            if value is not None:
                os.environ[key] = value


def test_a_real_looking_windows_path_is_rejected_end_to_end():
    print("\n[end to end, if this were run on Windows]")
    if sys.platform != "win32":
        print("  SKIP  (this check only means anything on a real Windows host)")
        return
    for bad in (os.environ.get("WINDIR", r"C:\Windows"),
                os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                             "System32"),
                os.environ.get("ProgramFiles", r"C:\Program Files")):
        try:
            validate_output_dir(bad)
            check(f"{bad} is refused", False, "was accepted")
        except UnsafePathError:
            check(f"{bad} is refused", True)


def run_all():
    print("=" * 62)
    print("  Luma packaging path checks")
    print("=" * 62)
    test_dev_mode_is_unchanged()
    test_a_portable_frozen_build_stays_portable()
    test_an_installed_build_uses_appdata_and_downloads()
    test_the_marker_alone_does_nothing_unfrozen()
    test_windows_system_roots_are_refused()
    test_windows_roots_are_absent_without_the_env_vars()
    test_a_real_looking_windows_path_is_rejected_end_to_end()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL PACKAGING PATH CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())
