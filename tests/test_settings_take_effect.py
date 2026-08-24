#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import Input, Select, Static

from luma.app import LumaApp
from luma.engine import download as dl

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


def bar_note(app):
    return text_of(app.screen.query_one(".brand-note", Static))


async def change_folder(app, pilot, folder):
    await pilot.press("ctrl+s")
    await pilot.pause()
    app.screen.query_one("#set-folder", Input).value = folder
    await pilot.click("#settings-save")
    await pilot.pause()
    await pilot.pause()


async def test_a_new_folder_is_used_and_shown():
    print("\n[changing where downloads go]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        chosen = os.path.join(td, "My Videos")
        os.makedirs(chosen)

        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test(size=(100, 34)) as pilot:
            before = bar_note(app)
            check("the bar starts on the default folder",
                  "downloads" in before, before)

            await change_folder(app, pilot, chosen)

            check("the setting is saved to disk",
                  json.load(open(cfg))["output_dir"] == chosen)
            check("the app is holding the new folder",
                  app.config["output_dir"] == chosen,
                  str(app.config["output_dir"]))
            check("downloads would go to the new folder",
                  app.screen._settings()["output_dir"] == chosen,
                  str(app.screen._settings()["output_dir"]))
            check("and the bar says so",
                  bar_note(app) == chosen, bar_note(app))


async def test_the_folder_scheme_shows_too():
    print("\n[a folder per day]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        chosen = os.path.join(td, "Videos")
        os.makedirs(chosen)
        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test(size=(100, 34)) as pilot:
            await change_folder(app, pilot, chosen)

            await pilot.press("ctrl+s")
            await pilot.pause()
            app.screen.query_one("#set-folders", Select).value = "date"
            await pilot.click("#settings-save")
            await pilot.pause()
            await pilot.pause()

            import datetime
            today = datetime.date.today().isoformat()
            note = bar_note(app)
            check("the bar shows the dated folder that will be used",
                  note.startswith(chosen) and today in note, note)
            check("and that folder exists", os.path.isdir(note), note)


async def test_a_change_reaches_a_run_already_going():
    print("\n[changing settings part-way through a run]")
    with tempfile.TemporaryDirectory() as td:
        first = os.path.join(td, "first")
        second = os.path.join(td, "second")
        os.makedirs(first)
        os.makedirs(second)

        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test(size=(100, 34)) as pilot:
            screen = app.screen
            app.config["output_dir"] = first
            seen = []

            def fake_run(tools, links, plan, output_dir, quality, **kwargs):
                seen.append(output_dir)
                if len(seen) == 1:
                    app.config["output_dir"] = second
                return [(url, True, "", None) for url in links]

            from luma.screens import main as main_mod
            real_run = dl.run_downloads
            real_expand = main_mod.expand_playlists
            main_mod.expand_playlists = lambda ytdlp, urls, cb=None: list(urls)
            dl.run_downloads = fake_run
            app.tools = {"yt-dlp": "yt-dlp", "aria2c": "aria2c"}
            screen._record_results = lambda *a, **k: None
            app.config["max_parallel"] = 1
            try:
                screen._enqueue(["https://youtu.be/aaa", "https://youtu.be/bbb"])
                screen._ensure_worker()
                for _ in range(200):
                    if len(seen) >= 2:
                        break
                    await pilot.pause()
                    await asyncio.sleep(0.02)
            finally:
                dl.run_downloads = real_run
                main_mod.expand_playlists = real_expand

            check("both videos were downloaded", len(seen) == 2, str(seen))
            check("the first went to the folder set at the time",
                  seen and seen[0] == first, str(seen))
            check("the second went to the folder set part-way through",
                  len(seen) > 1 and seen[1] == second, str(seen))


async def test_nothing_queued_at_the_end_is_stranded():
    print("\n[a link queued as a run winds down]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test(size=(100, 34)) as pilot:
            screen = app.screen
            runs = []

            def fake_worker():
                runs.append(True)

            screen._queue_worker = fake_worker
            screen._enqueue(["https://youtu.be/aaa"])
            screen._ensure_worker()
            check("the worker started once", len(runs) == 1, str(runs))

            screen._enqueue(["https://youtu.be/bbb"])
            check("a second worker is not started", len(runs) == 1, str(runs))
            check("but the link is on the queue",
                  len(screen._queue) == 2, str(screen._queue))

            screen._finished(1, 0, td)
            await pilot.pause()
            check("finishing picks the waiting link back up",
                  len(runs) == 2, str(runs))
            check("and Luma still counts as running",
                  screen._download_active, str(screen._download_active))


async def test_an_empty_queue_finishes_normally():
    print("\n[a run that really is over]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test(size=(100, 34)) as pilot:
            screen = app.screen
            runs = []
            screen._queue_worker = lambda: runs.append(True)
            screen._download_active = True

            screen._finished(2, 0, td)
            await pilot.pause()
            check("no further worker is started", runs == [], str(runs))
            check("Luma goes idle", not screen._download_active)
            status = text_of(screen.query_one("#status-line", Static))
            check("and says it is done", "done" in status.lower(), status)


async def run_all():
    print("=" * 62)
    print("  Luma settings-take-effect checks")
    print("=" * 62)
    await test_a_new_folder_is_used_and_shown()
    await test_the_folder_scheme_shows_too()
    await test_a_change_reaches_a_run_already_going()
    await test_nothing_queued_at_the_end_is_stranded()
    await test_an_empty_queue_finishes_normally()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL SETTINGS-TAKE-EFFECT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
