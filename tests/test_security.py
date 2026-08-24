#!/usr/bin/env python3
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import support

from textual.widgets import Input, Static

from luma.app import LumaApp
from luma.config import load_config, normalize, resolve_output_dir
from luma.engine import download as dl
from luma.engine.callbacks import EngineCallbacks
from luma.engine.errors import InvalidURLError, UnsafePathError
from luma.engine.inputs import gather_inputs, validate_url
from luma.engine.paths import safe_join
from luma.history import recent_downloads, recent_failures
from luma.storage import safe_read_json

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


def test_no_shell_execution():
    print("\n[1. commands are never handed to a shell]")
    sources = []
    for folder, _, files in os.walk(os.path.join(ROOT, "luma")):
        if "__pycache__" in folder:
            continue
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as fh:
                    sources.append((path, fh.read()))

    check("some source was scanned", len(sources) > 5, str(len(sources)))
    for pattern, label in [
        (r"shell\s*=\s*True", "shell=True"),
        (r"\bos\.system\(", "os.system"),
        (r"\bos\.popen\(", "os.popen"),
        (r"\beval\(", "eval"),
        (r"\bexec\(", "exec"),
    ]:
        hits = [p for p, s in sources if re.search(pattern, s)]
        check(f"no {label} anywhere", not hits, str(hits))

    bad = []
    for path, src in sources:
        for match in re.finditer(r"subprocess\.(run|Popen|call)\(\s*([^\s,)]+)",
                                 src):
            first = match.group(2)
            if first.startswith(('"', "'")):
                bad.append(f"{path}: {match.group(0)}")
    check("every command is built as an argument list", not bad, str(bad))


def test_hostile_links_refused():
    print("\n[2. hostile links are refused]")
    hostile = [
        "file:///etc/passwd",
        "file://C:/Windows/System32/config/SAM",
        "javascript:alert(document.cookie)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://example.com/x",
        "gopher://example.com",
        "\\\\server\\share\\file",
        "$(whoami)",
        "`id`",
        "--config-location=/tmp/evil",
        "-o/tmp/pwned",
    ]
    for url in hostile:
        try:
            validate_url(url)
            check(f"refuses {url[:38]!r}", False, "it was accepted")
        except InvalidURLError:
            check(f"refuses {url[:38]!r}", True)

    urls, rejected = gather_inputs(
        ["https://youtu.be/good", "file:///etc/passwd", "javascript:x"]
    )
    check("a good link still works alongside hostile ones",
          urls == ["https://youtu.be/good"], str(urls))
    check("the hostile ones are reported", len(rejected) == 2, str(rejected))


def test_argument_injection_cannot_reach_the_tool():
    print("\n[3. a link cannot smuggle in extra options]")
    for sneaky in ["--exec=rm -rf /", "-o /etc/passwd", "--paths=/etc"]:
        try:
            validate_url(sneaky)
            check(f"refuses {sneaky!r}", False, "accepted")
        except InvalidURLError:
            check(f"refuses {sneaky!r}", True)

    tools = {"yt-dlp": "yt-dlp", "aria2c": "aria2c",
             "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}
    plan = {"conns_per_file": 16, "concurrent_fragments": 16}
    url = "https://youtu.be/abc?x=1&y=2"
    cmd = dl.build_cmd(tools, url, plan, "/tmp/out", "480")
    check("the link is the last argument and stays intact",
          cmd[-1] == url, cmd[-1])
    check("the link appears exactly once",
          sum(1 for a in cmd if a == url) == 1)

    with tempfile.TemporaryDirectory() as td:
        canary = os.path.join(td, "canary.txt")
        with open(canary, "w") as fh:
            fh.write("untouched")
        evil = f"https://youtube.com/watch?v=x; rm -f {canary}"
        real_tools = dict(tools, **{"yt-dlp": sys.executable})
        cmd = dl.build_cmd(real_tools, evil, plan, td, "480")
        check("a link with shell characters stays one argument",
              cmd[-1] == evil, cmd[-1])
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        check("the shell command inside the link never executed",
              os.path.exists(canary)
              and open(canary).read() == "untouched")


def test_hostile_folders_contained():
    print("\n[4. hostile folders are contained]")
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "luma_audit_base")
        os.makedirs(base)
        for attempt in ["../../etc", "../../../root/.ssh", "/etc/passwd",
                        "..\\..\\Windows", "a/../../b", "~/.bashrc",
                        "$HOME/.ssh/id_rsa", "....//....//etc"]:
            result = safe_join(base, attempt)
            inside = result == base or result.startswith(base + os.sep)
            check(f"contains {attempt[:26]!r}", inside, result)

    for danger in support.forbidden_directories():
        cfg = normalize({"output_dir": danger})
        check(f"refuses {danger} as a download folder",
              cfg["output_dir"] != danger, cfg["output_dir"])

    try:
        resolve_output_dir({"output_dir": support.a_forbidden_directory(),
                            "folders": "none"})
        check("refuses to resolve into a system folder", False, "allowed")
    except UnsafePathError:
        check("refuses to resolve into a system folder", True)

    with tempfile.TemporaryDirectory() as td:
        sneaky = resolve_output_dir(
            {"output_dir": td, "folders": "playlist"}, "../../escape")
        check("a hostile playlist name cannot escape",
              sneaky.startswith(td + os.sep), sneaky)


def test_damaged_files_survived():
    print("\n[5. damaged files never stop the app]")
    payloads = {
        "garbage": b"\x00\xff\xfe binary junk",
        "truncated": b'[{"a": 1',
        "empty": b"",
        "html": b"<html><body>500</body></html>",
        "huge-nesting": b"[" * 500,
        "wrong-type": b'"just a string"',
    }
    with tempfile.TemporaryDirectory() as td:
        for name, blob in payloads.items():
            cfg = os.path.join(td, f"config-{name}.json")
            hist = os.path.join(td, f"history-{name}.json")
            errs = os.path.join(td, f"errors-{name}.json")
            for path in (cfg, hist, errs):
                with open(path, "wb") as fh:
                    fh.write(blob)

            ok = True
            try:
                settings = load_config(cfg)
                ok = bool(settings.get("quality"))
                recent_downloads(path=hist)
                recent_failures(path=errs)
                safe_read_json(cfg, {})
            except Exception as exc:
                ok = False
                print(f"        raised: {exc!r}")
            check(f"{name} content is absorbed", ok)


async def test_damaged_files_still_let_the_app_start():
    print("\n[6. the app still starts on damaged files]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        hist = os.path.join(td, "history.json")
        errs = os.path.join(td, "errors.json")
        for path in (cfg, hist, errs):
            with open(path, "w") as fh:
                fh.write("{{{{ not json at all")

        app = LumaApp(config_path=cfg, history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            check("the app starts", app.screen is not None)
            check("settings fell back to something usable",
                  bool(app.config.get("quality")), str(app.config))
            await pilot.press("ctrl+h")
            await pilot.pause()
            check("the history screen opens on damaged records",
                  app.screen is not None)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            check("the settings screen opens on a damaged config",
                  app.screen.query_one("#set-folder", Input) is not None)


FAKE = textwrap.dedent('''
    import os, sys, time
    print("[download] Destination: /tmp/x.mp4", flush=True)
    for i in range(600):
        print(f"[#ae87 {i}MiB/600MiB({i//6}%) CN:16 DL:900KiB ETA:60s]", flush=True)
        time.sleep(0.2)
    sys.exit(0)
''')


def make_fake(tmpdir):
    return support.write_stub_script(tmpdir, FAKE.lstrip(), "slow_dl")


def _descendants_posix():
    try:
        out = subprocess.run(
            ["ps", "-o", "pid=,command=", "--ppid", str(os.getpid())],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return []
    return [ln for ln in out.splitlines() if "slow_dl" in ln]


def _descendants_windows():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process "
             f"-Filter \"ParentProcessId={os.getpid()}\" | "
             "Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except Exception:
        return []
    return [ln for ln in out.splitlines() if "slow_dl" in ln]


def _descendants():
    if os.name == "nt":
        return _descendants_windows()
    return _descendants_posix()


def test_quitting_leaves_no_orphans():
    print("\n[7. quitting leaves nothing running]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        dl.reset_cancel()
        done = threading.Event()

        def run():
            dl._stream_download(fake, "1/1", EngineCallbacks())
            done.set()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        time.sleep(1.2)

        with dl._procs_lock:
            running = len(dl._active_procs)
        check("the downloader is running before we quit", running >= 1,
              str(running))
        check("the system can see it", len(_descendants()) >= 1,
              str(_descendants()))

        dl.terminate_all(timeout=5)
        done.wait(timeout=10)
        time.sleep(0.6)

        with dl._procs_lock:
            left = len(dl._active_procs)
        check("nothing is left in the registry", left == 0, str(left))
        check("no downloader process survives", not _descendants(),
              str(_descendants()))
        dl.reset_cancel()


def test_interrupted_download_recovers():
    print("\n[8. an interrupted download is handled, not fatal]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        dl.reset_cancel()
        result = {}

        def run():
            result["out"] = dl._stream_download(fake, "1/1",
                                                EngineCallbacks())

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        time.sleep(1.0)
        dl.terminate_all(timeout=5)
        thread.join(timeout=10)

        check("the engine returned rather than hanging", "out" in result)
        if "out" in result:
            rc, reason, _ = result["out"]
            check("it reports a stop, not a crash", rc != 0, str(rc))
            check("the reason is short and readable",
                  isinstance(reason, str) and len(reason) < 120, repr(reason))
            check("the reason leaks no internals",
                  not any(t in reason.lower()
                          for t in ("traceback", "yt-dlp", "aria2c")), reason)
        dl.reset_cancel()


def test_crash_handler_catches_everything():
    print("\n[9. an unexpected failure is logged, not dumped]")
    with tempfile.TemporaryDirectory() as td:
        script = os.path.join(td, "boom.py")
        with open(script, "w") as fh:
            fh.write(textwrap.dedent(f'''
                import sys
                sys.path.insert(0, {ROOT!r})
                import luma.locations as loc
                loc.LOG_DIR = {td!r}
                loc.CRASH_LOG = {os.path.join(td, "crash.log")!r}
                import luma.__main__ as m
                m.CRASH_LOG = loc.CRASH_LOG
                import luma.app as appmod
                class Boom:
                    def __init__(self): pass
                    def run(self): raise RuntimeError("secret internal detail")
                appmod.LumaApp = Boom
                sys.exit(m.main())
            ''').lstrip())
        proc = subprocess.run([sys.executable, script], capture_output=True,
                              text=True, timeout=60)
        output = proc.stdout + proc.stderr
        check("it exits with a failure code", proc.returncode != 0,
              str(proc.returncode))
        check("no traceback reaches the terminal",
              "Traceback" not in output, output[:200])
        check("the user gets a plain explanation",
              "unexpected problem" in output.lower(), output[:200])
        log = os.path.join(td, "crash.log")
        check("the detail is written to a log", os.path.exists(log))
        if os.path.exists(log):
            with open(log) as fh:
                body = fh.read()
            check("the log holds the real traceback",
                  "Traceback" in body and "secret internal detail" in body)


async def test_nothing_technical_reaches_the_user():
    print("\n[10. the user never sees internals]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen.query_one("#url-input", Input).value = "file:///etc/passwd"
            await pilot.click("#download-btn")
            await pilot.pause()

            blob = " ".join(
                str(getattr(w, "content", "")) for w in screen.query(Static)
            ).lower()
            for leak in ("traceback", "yt-dlp", "aria2c", "ffmpeg",
                         "subprocess", "exception", "stderr"):
                check(f"no {leak!r} on screen", leak not in blob)
            check("no download was started for a hostile link",
                  not screen._download_active)


def test_no_auto_open():
    print("\n[11. downloaded files are never opened for the user]")
    hits = []
    for folder, _, files in os.walk(os.path.join(ROOT, "luma")):
        if "__pycache__" in folder:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            for pattern in (r"os\.startfile", r"xdg-open", r"webbrowser\.",
                            r"os\.exec", r"\bopen_file\("):
                if re.search(pattern, src):
                    hits.append(f"{path}: {pattern}")
    check("nothing launches a downloaded file", not hits, str(hits))


async def run_all():
    print("=" * 62)
    print("  Luma security and robustness audit")
    print("=" * 62)
    test_no_shell_execution()
    test_hostile_links_refused()
    test_argument_injection_cannot_reach_the_tool()
    test_hostile_folders_contained()
    test_damaged_files_survived()
    await test_damaged_files_still_let_the_app_start()
    test_quitting_leaves_no_orphans()
    test_interrupted_download_recovers()
    test_crash_handler_catches_everything()
    await test_nothing_technical_reaches_the_user()
    test_no_auto_open()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL SECURITY AND ROBUSTNESS CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
