import asyncio
import os
import sys


async def wait_for(pilot, predicate, timeout=5.0):
    """Let the app settle until `predicate` holds, or the time runs out.

    A click or keypress only posts a message; the handler that acts on it
    runs when that message is dispatched, which may be several turns of the
    event loop later -- more so when one handler posts another, as a chip
    press does. A single pause() covers that often enough on Linux to look
    reliable and not often enough on Windows, so the outcome is waited for
    rather than assumed.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await pilot.pause()
        await asyncio.sleep(0.02)
    return predicate()

_WINDOWS_ROOT_VARS = (
    "WINDIR", "ProgramFiles", "ProgramFiles(x86)", "ProgramData",
)


def a_forbidden_directory():
    if os.name == "nt":
        for var in _WINDOWS_ROOT_VARS:
            value = os.environ.get(var)
            if value and os.path.isdir(value):
                return value
        return r"C:\Windows"
    return "/etc"


def a_forbidden_subdirectory():
    base = a_forbidden_directory()
    if os.name == "nt":
        candidate = os.path.join(base, "System32")
        return candidate if os.path.isdir(candidate) else base
    return "/etc/cron.d"


def forbidden_directories():
    if os.name == "nt":
        found = []
        for var in _WINDOWS_ROOT_VARS:
            value = os.environ.get(var)
            if value and os.path.isdir(value):
                found.append(value)
        return found or [a_forbidden_directory()]
    return ["/etc", "/bin", "/usr/bin", "/boot", "/proc", "/sys"]


def an_unwritable_path(root):
    blocker = os.path.join(root, "blocked_by_a_file")
    open(blocker, "w").close()
    return os.path.join(blocker, "sub", "history.json")


def write_stub_script(directory, python_body, name="stub_script"):
    script = os.path.join(directory, name + ".py")
    with open(script, "w") as fh:
        fh.write(python_body)
    return [sys.executable, script]


class fake_downloader:
    """Swap the real download tool for a Python stub, for the duration.

    The stub replaces argv[0] of whatever build_cmd produces, so every
    other argument -- and the whole path below build_cmd: streaming,
    parsing, retries, cancellation, the callbacks -- is exercised for
    real. build_cmd's own output is asserted directly, without running
    anything, by test_command_building.

    Replacing argv[0] rather than pointing the tool at an executable
    script is deliberate. A tool path has to be launchable on its own,
    and on Windows that means a .bat, which CreateProcess runs through
    cmd.exe. cmd re-parses the command line, and build_cmd's format
    argument (ba+bv*[height<=480]/...) carries a `<` with no spaces
    around it, so it arrives unquoted and cmd reads it as input
    redirection. Going through sys.executable keeps every argument away
    from a shell on both platforms.
    """

    def __init__(self, download_module, directory, python_body,
                 name="fake_dl"):
        self._module = download_module
        self.command = write_stub_script(directory, python_body, name)

    def __enter__(self):
        self._real_build_cmd = self._module.build_cmd
        stub = self.command

        def build_cmd(*args, **kwargs):
            return stub + self._real_build_cmd(*args, **kwargs)[1:]

        self._module.build_cmd = build_cmd
        return self

    def __exit__(self, *_exc):
        self._module.build_cmd = self._real_build_cmd
