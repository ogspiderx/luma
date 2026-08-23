#!/usr/bin/env python3
"""
Automated checks for Luma's engine. No UI involved.

Covers the pure logic (planning maths, parsing, validation, path safety) and
the process machinery (streaming, retry, cancellation, error isolation) by
driving a stand-in downloader that emits real captured yt-dlp/aria2c output.

    python tests/test_engine.py
"""

import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luma.engine import download as dl                      # noqa: E402
from luma.engine.callbacks import EngineCallbacks           # noqa: E402
from luma.engine.errors import InvalidURLError, UnsafePathError  # noqa: E402
from luma.engine.inputs import (                            # noqa: E402
    _is_playlist_like, gather_inputs, validate_url,
)
from luma.engine.paths import safe_join, validate_output_dir  # noqa: E402
from luma.engine.plan import apply_overrides, compute_plan, default_plan  # noqa: E402

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


# --------------------------------------------------------------------------- #
#  A stand-in downloader that replays real tool output.                        #
# --------------------------------------------------------------------------- #

# A stand-in that ignores yt-dlp's real arguments and replays captured output.
# Mode and target come from the environment so it can be dropped in wherever
# the real yt-dlp path would go.
FAKE_SCRIPT = textwrap.dedent('''
    #!@PYTHON@
    import os, sys, time
    mode = os.environ.get("LUMA_FAKE_MODE", "ok")
    out = os.environ.get("LUMA_FAKE_OUT", "/tmp/Fake Video [abc123].mp4")
    print("[youtube] Extracting URL: https://youtu.be/abc123", flush=True)
    print("[info] abc123: Downloading 1 format(s): 135+140", flush=True)
    print(f"[download] Destination: {out}.f135.mp4", flush=True)
    for pct, done in ((25, "13MiB"), (60, "32MiB"), (90, "49MiB")):
        print(f"[#ae8705 {done}/54MiB({pct}%) CN:16 DL:712KiB ETA:7s]", flush=True)
        time.sleep(0.05)
    if mode == "fail":
        print("ERROR: unable to download video data: connection reset", flush=True)
        sys.exit(1)
    if mode == "private":
        print("ERROR: Private video. Sign in if you have been granted access.", flush=True)
        sys.exit(1)
    if mode == "hang":
        time.sleep(60)
    print(f'[Merger] Merging formats into "{out}"', flush=True)
    print("[download] 100% of 54MiB", flush=True)
    sys.exit(0)
''')


def make_fake(tmpdir, name="fake_dl.py"):
    """Write an executable stand-in downloader that ignores its arguments."""
    path = os.path.join(tmpdir, name)
    with open(path, "w") as fh:
        fh.write(FAKE_SCRIPT.replace("@PYTHON@", sys.executable).lstrip())
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IREAD)
    return path


def fake_tools(fake_path):
    """A tools dict whose downloader is the stand-in."""
    return {"yt-dlp": fake_path, "aria2c": "aria2c",
            "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}


def collector():
    """An EngineCallbacks that records everything, for assertions."""
    rec = {"status": [], "progress": [], "done": [], "start": []}
    return rec, EngineCallbacks(
        on_status=lambda m: rec["status"].append(m),
        on_video_status=lambda t, m: rec["status"].append(m),
        on_video_progress=lambda t, p: rec["progress"].append(p),
        on_video_start=lambda t, u: rec["start"].append(u),
        on_video_done=lambda t, u, ok, r, f: rec["done"].append((ok, r, f)),
    )


# --------------------------------------------------------------------------- #

def test_plan_maths():
    print("\n[planning maths]")
    p = compute_plan(5.6, 5.6, 46, 29, 8)
    check("slow line still uses max connections", p["conns_per_file"] == 16)
    check("fragments track connections",
          p["concurrent_fragments"] == p["conns_per_file"])
    fast = compute_plan(12, 200, 30, 50, 8)
    check("fast line fans out to several videos", fast["parallel_files"] > 1)
    check("total sockets stay within the cap",
          fast["parallel_files"] * fast["conns_per_file"] <= 64,
          f"{fast['parallel_files']}x{fast['conns_per_file']}")
    check("never more parallel than URLs",
          compute_plan(12, 200, 30, 2, 8)["parallel_files"] <= 2)
    dead = compute_plan(0.0, 0.0, 40, 5, 8)
    check("a failed speed test degrades safely, not to zero",
          dead["parallel_files"] >= 1 and dead["conns_per_file"] == 16)
    d = default_plan(10, 8)
    check("default plan is conservative", d["parallel_files"] <= 4)
    o = apply_overrides(compute_plan(50, 50, 20, 10, 8),
                        conns_per_file=999, parallel_files=99, num_urls=10)
    check("overrides are clamped, not trusted",
          o["conns_per_file"] == 16 and o["parallel_files"] == 10,
          f"{o['conns_per_file']}/{o['parallel_files']}")


def test_progress_parsing():
    print("\n[progress parsing]")
    a = dl.parse_progress("[#ae8705 49MiB/54MiB(90%) CN:4 DL:712KiB ETA:7s]")
    check("aria2c line parsed", a and a["percent"] == 90.0 and a["connections"] == 4)
    y = dl.parse_progress("[download]  85.0% of 54.00MiB at 700.00KiB/s ETA 00:19")
    check("yt-dlp line parsed", y and y["percent"] == 85.0)
    check("non-progress line ignored",
          dl.parse_progress('[Merger] Merging formats into "x.mp4"') is None)
    check("summary noise ignored",
          dl.parse_progress("*** Download Progress Summary ***") is None)


def test_user_facing_text():
    print("\n[user-facing text]")
    noisy = [
        "[youtube] Extracting URL: https://x",
        "*** Download Progress Summary as of Sun ***",
        "FILE: /tmp/x.part",
        "===========================",
    ]
    check("tool chatter stays hidden",
          all(dl._milestone(n) is None for n in noisy))
    shown = [dl._milestone("[Merger] Merging formats into \"a.mp4\""),
             dl._milestone("[download] Destination: /tmp/My Video.mp4"),
             dl._milestone("ERROR: Private video. Sign in")]
    check("milestones are shown", all(s for s in shown))
    joined = " ".join(s for s in shown if s).lower()
    check("no tool names leak to the user",
          not any(t in joined for t in ("yt-dlp", "aria2c", "ffmpeg")))
    check("private video explained plainly",
          "private" in dl._friendly_error("ERROR: Private video. Sign in").lower())
    check("network error explained plainly",
          "connection" in dl._friendly_error("SSL/TLS handshake failure").lower())


def test_url_validation():
    print("\n[url validation]")
    for bad in ["file:///etc/passwd", "javascript:alert(1)", "ftp://h/f",
                "not a url", "", "   "]:
        try:
            validate_url(bad)
            check(f"rejects {bad!r}", False, "was accepted")
        except InvalidURLError:
            check(f"rejects {bad!r}", True)
    check("accepts a youtube link",
          validate_url("https://youtu.be/abc") == "https://youtu.be/abc")
    try:
        validate_url("https://vimeo.com/1")
        check("rejects non-YouTube host", False)
    except InvalidURLError:
        check("rejects non-YouTube host", True)
    check("watch?v with &list= is a single video",
          not _is_playlist_like("https://www.youtube.com/watch?v=a&list=RDa"))
    check("real playlist is expandable",
          _is_playlist_like("https://www.youtube.com/playlist?list=PL1"))

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "urls.txt")
        with open(p, "w") as fh:
            fh.write("# comment\nhttps://youtu.be/aaa\nfile:///etc/passwd\n\n")
        urls, rejected = gather_inputs([p])
        check("batch file keeps good links", urls == ["https://youtu.be/aaa"])
        check("batch file reports bad links", len(rejected) == 1)


def test_path_safety():
    print("\n[path safety]")
    base = "/tmp/luma_base"
    for attempt in ["../../etc", "..", "/etc/passwd", "a/../../b"]:
        got = safe_join(base, attempt)
        check(f"contains {attempt!r}",
              got == base or got.startswith(base + os.sep), got)
    for bad in ["/etc", "/etc/cron.d", ""]:
        try:
            validate_output_dir(bad)
            check(f"rejects system dir {bad!r}", False, "accepted")
        except UnsafePathError:
            check(f"rejects system dir {bad!r}", True)
    check("accepts a normal folder",
          validate_output_dir("/tmp/luma_out") == "/tmp/luma_out")


def test_command_building():
    print("\n[command building]")
    tools = {"yt-dlp": "yt-dlp", "aria2c": "aria2c",
             "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}
    plan = compute_plan(5, 5, 40, 1, 8)
    cmd = dl.build_cmd(tools, "https://youtu.be/x", plan, "/tmp/o", "480")
    check("command is an argument list, never a shell string",
          isinstance(cmd, list) and all(isinstance(a, str) for a in cmd))
    check("480 caps height", "height<=480" in cmd[2])
    check("720 caps height",
          "height<=720" in dl.build_cmd(tools, "u", plan, "/tmp/o", "720")[2])
    check("best has no height cap",
          "height" not in dl.build_cmd(tools, "u", plan, "/tmp/o", "best")[2])
    joined = " ".join(cmd)
    check("uses 16 connections", "-x16" in joined)
    check("resume enabled", "continue=true" in joined)
    check("url is the final argument", cmd[-1] == "https://youtu.be/x")


def test_streaming_and_retry():
    print("\n[streaming, retry, isolation]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        tools = fake_tools(fake)
        plan = compute_plan(5, 5, 40, 1, 8)
        target = os.path.join(td, "Fake Video [abc123].mp4")
        os.environ["LUMA_FAKE_OUT"] = target

        # --- success path, through the real build_cmd ---
        os.environ["LUMA_FAKE_MODE"] = "ok"
        dl.reset_cancel()
        rec, cb = collector()
        cmd = dl.build_cmd(tools, "https://youtu.be/abc", plan, td, "480")
        rc, reason, path = dl._stream_download(cmd, "1/1", cb)
        check("successful run returns rc 0", rc == 0, f"rc={rc} {reason}")
        check("progress reached the callbacks", len(rec["progress"]) >= 1)
        check("final merged path captured", path == target, str(path))
        # Updates are deliberately throttled to ~4/sec so a fast download
        # cannot flood the UI, so not every emitted line arrives.
        first = rec["progress"][0]
        check("percent parsed from real aria2c output",
              first["percent"] == 25.0, str(first["percent"]))
        check("connection count parsed", first["connections"] == 16)
        check("progress updates are throttled, not flooded",
              len(rec["progress"]) < 3, str(len(rec["progress"])))
        check("milestones surfaced to the user", len(rec["status"]) >= 1)

        # --- failure is translated, not raw ---
        os.environ["LUMA_FAKE_MODE"] = "fail"
        dl.reset_cancel()
        rec, cb = collector()
        rc, reason, _ = dl._stream_download(cmd, "1/1", cb)
        check("failing run returns non-zero", rc != 0)
        check("failure reason is plain language",
              "connection" in reason.lower(), reason)
        check("reason exposes no tool internals",
              "traceback" not in reason.lower()
              and "yt-dlp" not in reason.lower())

        # --- a private video is explained, not dumped ---
        os.environ["LUMA_FAKE_MODE"] = "private"
        dl.reset_cancel()
        _, cb = collector()
        _, reason, _ = dl._stream_download(cmd, "1/1", cb)
        check("private video explained plainly",
              "private" in reason.lower(), reason)

        # --- retry loop retries with backoff, then gives up ---
        os.environ["LUMA_FAKE_MODE"] = "fail"
        dl.reset_cancel()
        rec, cb = collector()
        t0 = time.time()
        _, ok, reason, _ = dl.download_one(
            tools, "https://youtu.be/abc", plan, td,
            "480", "aria2c", False, 1, 1, cb)
        elapsed = time.time() - t0
        check("gives up after exhausting retries", ok is False)
        retried = [s for s in rec["status"] if "retry" in s.lower()]
        check("retried MAX_ATTEMPTS-1 times",
              len(retried) == dl.MAX_ATTEMPTS - 1, str(len(retried)))
        check("backoff actually waited (2+4+6s)", elapsed >= 11, f"{elapsed:.1f}s")
        check("reported failure once finished", len(rec["done"]) == 1)

        # --- success reports the file path for the history log ---
        os.environ["LUMA_FAKE_MODE"] = "ok"
        dl.reset_cancel()
        rec, cb = collector()
        _, ok, _, fp = dl.download_one(
            tools, "https://youtu.be/abc", plan, td,
            "480", "aria2c", False, 1, 1, cb)
        check("succeeds on first try", ok is True)
        check("file path returned for history", fp == target, str(fp))

        # --- error isolation: a failing item never sinks the batch ---
        os.environ["LUMA_FAKE_MODE"] = "fail"
        dl.reset_cancel()
        rec, cb = collector()
        results = dl.run_downloads(
            tools, ["https://youtu.be/a", "https://youtu.be/b"],
            {"parallel_files": 2, "conns_per_file": 16,
             "concurrent_fragments": 16},
            td, "480", "aria2c", False, cb)
        check("every item returns a result", len(results) == 2)
        check("failures are reported, not raised",
              all(r[1] is False for r in results))
        check("batch completed despite failures",
              all(len(r) == 4 for r in results))
        os.environ.pop("LUMA_FAKE_MODE", None)
        os.environ.pop("LUMA_FAKE_OUT", None)


def test_cancellation():
    print("\n[cancellation - no orphaned processes]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        os.environ["LUMA_FAKE_MODE"] = "hang"   # stays alive until terminated
        dl.reset_cancel()
        rec, cb = collector()
        result = {}

        def run():
            result["rc"] = dl._stream_download([fake], "1/1", cb)

        th = threading.Thread(target=run, daemon=True)
        th.start()
        time.sleep(1.0)
        with dl._procs_lock:
            live = len(dl._active_procs)
        check("child process was registered while running", live >= 1, str(live))

        dl.terminate_all(timeout=5)
        th.join(timeout=10)
        check("stream returned after cancel", "rc" in result)
        with dl._procs_lock:
            remaining = len(dl._active_procs)
        check("no child processes left behind", remaining == 0, str(remaining))
        check("cancelled run is reported as stopped, not crashed",
              result.get("rc", (None,))[0] in (130, 0, -15, 143),
              str(result.get("rc")))
        dl.reset_cancel()
        os.environ.pop("LUMA_FAKE_MODE", None)


def main():
    print("=" * 62)
    print("  Luma engine checks")
    print("=" * 62)
    test_plan_maths()
    test_progress_parsing()
    test_user_facing_text()
    test_url_validation()
    test_path_safety()
    test_command_building()
    test_streaming_and_retry()
    test_cancellation()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL ENGINE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
