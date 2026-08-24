#!/usr/bin/env python3
import asyncio
import os
import stat
import sys
import tempfile
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import Button, Input, Static

from luma.app import LumaApp
from luma.screens import main as main_mod
from luma.widgets.download_row import DownloadRow

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


def text_of(widget):
    for attr in ("content", "renderable"):
        value = getattr(widget, attr, None)
        if value is not None:
            return str(value)
    return str(widget.render())


FAKE = textwrap.dedent('''
    #!@PYTHON@
    import os, sys, time
    mode = os.environ.get("LUMA_FAKE_MODE", "ok")
    out = os.environ.get("LUMA_FAKE_OUT", "/tmp/Fake [dQw4w9WgXcQ].mp4")
    # Match how the real downloader names a part file: "Title [id].f135.mp4"
    stem = os.path.splitext(out)[0]
    print(f"[download] Destination: {stem}.f135.mp4", flush=True)
    for pct, done in ((20, "10MiB"), (55, "29MiB"), (95, "51MiB")):
        print(f"[#ae87 {done}/54MiB({pct}%) CN:16 DL:900KiB ETA:5s]", flush=True)
        time.sleep(0.35)
    if mode == "fail":
        print("ERROR: unable to download video data: connection reset", flush=True)
        sys.exit(1)
    print(f'[Merger] Merging formats into "{out}"', flush=True)
    sys.exit(0)
''')


def make_fake(tmpdir):
    path = os.path.join(tmpdir, "fake_dl.py")
    with open(path, "w") as fh:
        fh.write(FAKE.replace("@PYTHON@", sys.executable).lstrip())
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IREAD)
    return path


def patch_engine(fake_path, tmpdir):
    from luma import history as history_mod

    main_mod.ensure_tools = lambda cb=None: {
        "yt-dlp": fake_path, "aria2c": "aria2c",
        "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe",
    }
    main_mod.measure_bandwidth = lambda cb=None: (50.0, 100.0, 25.0)
    main_mod.expand_playlists = lambda ytdlp, urls, cb=None: list(urls)
    main_mod.record_results = (
        lambda results, quality=None: history_mod.record_results(
            results, quality,
            os.path.join(tmpdir, "history.json"),
            os.path.join(tmpdir, "errors.json"),
        )
    )


async def wait_for_idle(app, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not app.screen._download_active:
            return True
        await asyncio.sleep(0.1)
    return False


async def wait_until(predicate, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


async def test_single_download():
    print("\n[single download]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        patch_engine(fake, td)
        os.environ["LUMA_FAKE_MODE"] = "ok"
        os.environ["LUMA_FAKE_OUT"] = os.path.join(td, "Fake Video [dQw4w9WgXcQ].mp4")

        app = LumaApp(auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._settings = lambda: {
                "output_dir": td, "quality": "480", "max_parallel": 8,
                "conns_per_file": None, "archive": False,
                "run_speedtest": True,
            }
            box = screen.query_one("#url-input", Input)
            box.value = "https://youtu.be/abc"

            screen._start()
            check("the download starts", screen._download_active)
            check("more can still be added while it runs",
                  not screen.query_one("#download-btn", Button).disabled)
            check("link box was cleared", box.value == "")
            await pilot.pause()

            await asyncio.sleep(0.6)
            responsive = False
            try:
                await asyncio.wait_for(pilot.pause(), timeout=3)
                responsive = True
            except asyncio.TimeoutError:
                responsive = False
            check("interface stays responsive during the download", responsive)

            appeared = await wait_until(
                lambda: len(screen.query(DownloadRow)) == 1)
            check("a progress row appeared", appeared,
                  str(len(screen.query(DownloadRow))))

            finished = await wait_for_idle(app)
            check("download finished", finished)
            await pilot.pause()

            row = screen.query(DownloadRow)[0]
            shown = text_of(row.query_one(".row-title", Static))
            check("the row is named after the video, not the link",
                  shown == "Fake Video", shown)
            check("no link is left on display",
                  "youtu.be" not in shown, shown)

            check("button re-enabled afterwards",
                  not screen.query_one("#download-btn", Button).disabled)
            status = text_of(screen.query_one("#status-line", Static))
            check("status reports success", "done" in status.lower(), status)
            row = screen.query(DownloadRow)[0]
            check("row marked as done", row.has_class("-done"))
            detail = text_of(row.query_one(".row-detail", Static))
            check("a finished row shows its link, ready to copy",
                  detail == "https://youtu.be/abc", detail)

            plan = text_of(screen.query_one("#plan-note", Static))
            check("plan panel explains the setup in plain words",
                  "Videos at once" in plan, plan)
            check("plan panel names no tools",
                  not any(t in plan.lower()
                          for t in ("yt-dlp", "aria2c", "ffmpeg")), plan)


async def test_multiple_downloads():
    print("\n[several at once]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        patch_engine(fake, td)
        os.environ["LUMA_FAKE_MODE"] = "ok"
        os.environ["LUMA_FAKE_OUT"] = os.path.join(td, "Fake [CdbHAzNB1n0].mp4")

        app = LumaApp(auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._settings = lambda: {
                "output_dir": td, "quality": "480", "max_parallel": 8,
                "conns_per_file": None, "archive": False,
                "run_speedtest": True,
            }
            screen.query_one("#url-input", Input).value = (
                "https://youtu.be/a https://youtu.be/b https://youtu.be/c"
            )
            await pilot.click("#download-btn")
            await pilot.pause()

            appeared = await wait_until(
                lambda: len(screen.query(DownloadRow)) == 3)
            check("one row per video", appeared,
                  str(len(screen.query(DownloadRow))))

            finished = await wait_for_idle(app)
            check("all finished", finished)
            await pilot.pause()
            done = [r for r in screen.query(DownloadRow) if r.has_class("-done")]
            check("every row completed", len(done) == 3, str(len(done)))


async def test_failure_is_explained():
    print("\n[failure handling]")
    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        patch_engine(fake, td)
        os.environ["LUMA_FAKE_MODE"] = "fail"
        os.environ["LUMA_FAKE_OUT"] = os.path.join(td, "Fake [CdbHAzNB1n0].mp4")

        app = LumaApp(auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._settings = lambda: {
                "output_dir": td, "quality": "480", "max_parallel": 8,
                "conns_per_file": None, "archive": False,
                "run_speedtest": False,
            }
            screen.query_one("#url-input", Input).value = "https://youtu.be/a"
            await pilot.click("#download-btn")
            await pilot.pause()

            finished = await wait_for_idle(app, timeout=90)
            check("failing download completes rather than hanging", finished)
            await pilot.pause()
            row = screen.query(DownloadRow)[0]
            check("row marked as failed", row.has_class("-failed"))
            detail = text_of(row.query_one(".row-detail", Static))
            check("failure explained in plain language",
                  "connection" in detail.lower(), detail)
            check("failure exposes no tool internals",
                  not any(t in detail.lower()
                          for t in ("yt-dlp", "aria2c", "traceback")), detail)
            check("app still usable after a failure",
                  not screen.query_one("#download-btn", Button).disabled)


async def test_bad_link_rejected():
    print("\n[bad links]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        screen.query_one("#url-input", Input).value = "file:///etc/passwd"
        await pilot.click("#download-btn")
        await pilot.pause()
        check("no download started for a non-web link",
              not screen._download_active)
        check("no progress rows created",
              len(screen.query(DownloadRow)) == 0)

        screen.query_one("#url-input", Input).value = ""
        await pilot.click("#download-btn")
        await pilot.pause()
        check("empty box does not start a download", not screen._download_active)


async def test_results_are_recorded():
    print("\n[downloads are recorded]")
    from luma.storage import read_list

    with tempfile.TemporaryDirectory() as td:
        fake = make_fake(td)
        patch_engine(fake, td)
        hist = os.path.join(td, "history.json")
        errs = os.path.join(td, "errors.json")

        target = os.path.join(td, "Recorded Video [ODl-DYTyNyM].mp4")
        with open(target, "wb") as fh:
            fh.write(b"z" * 2048)
        os.environ["LUMA_FAKE_MODE"] = "ok"
        os.environ["LUMA_FAKE_OUT"] = target

        app = LumaApp(auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._settings = lambda: {
                "output_dir": td, "quality": "720", "max_parallel": 8,
                "conns_per_file": None, "archive": False,
                "run_speedtest": False,
            }
            screen.query_one("#url-input", Input).value = "https://youtu.be/zzz"
            await pilot.click("#download-btn")
            await pilot.pause()
            await wait_for_idle(app)
            await pilot.pause()

        rows = read_list(hist)
        check("the finished download was recorded", len(rows) == 1, str(len(rows)))
        if rows:
            check("its title was recorded",
                  rows[0]["title"] == "Recorded Video", rows[0]["title"])
            check("its real file size was recorded",
                  rows[0]["size"] == 2048, str(rows[0]["size"]))
            check("the quality in use was recorded",
                  rows[0]["quality"] == "720", str(rows[0]["quality"]))
        check("no failures were recorded", read_list(errs) == [])

        os.environ["LUMA_FAKE_MODE"] = "fail"
        app = LumaApp(auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._settings = lambda: {
                "output_dir": td, "quality": "720", "max_parallel": 8,
                "conns_per_file": None, "archive": False,
                "run_speedtest": False,
            }
            screen.query_one("#url-input", Input).value = "https://youtu.be/bad"
            await pilot.click("#download-btn")
            await pilot.pause()
            await wait_for_idle(app, timeout=90)
            await pilot.pause()

        errors = read_list(errs)
        check("the failure was recorded", len(errors) == 1, str(len(errors)))
        if errors:
            check("the failure explains itself plainly",
                  "connection" in errors[0]["reason"].lower(),
                  errors[0]["reason"])
        check("the failure did not pollute the download list",
              len(read_list(hist)) == 1, str(len(read_list(hist))))
        os.environ.pop("LUMA_FAKE_MODE", None)
        os.environ.pop("LUMA_FAKE_OUT", None)


async def run_all():
    print("=" * 62)
    print("  Luma download-flow checks")
    print("=" * 62)
    await test_single_download()
    await test_multiple_downloads()
    await test_failure_is_explained()
    await test_bad_link_rejected()
    await test_results_are_recorded()
    os.environ.pop("LUMA_FAKE_MODE", None)
    os.environ.pop("LUMA_FAKE_OUT", None)

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL DOWNLOAD-FLOW CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
