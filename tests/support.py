import os
import stat
import sys

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


def write_stub_tool(directory, python_body, name="stub_tool"):
    if os.name == "nt":
        script = os.path.join(directory, name + ".py")
        with open(script, "w") as fh:
            fh.write(python_body)
        launcher = os.path.join(directory, name + ".bat")
        with open(launcher, "w") as fh:
            fh.write(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n')
        return launcher

    script = os.path.join(directory, name + ".py")
    with open(script, "w") as fh:
        fh.write(f"#!{sys.executable}\n" + python_body)
    os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC | stat.S_IREAD)
    return script
