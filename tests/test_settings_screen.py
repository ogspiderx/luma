#!/usr/bin/env python3
"""
Checks for the Settings screen.

The promise being tested is that a normal person can change every setting from
inside Luma, that bad input is refused rather than saved, and that choices
survive a restart.

    python tests/test_settings_screen.py
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import Button, Input, Select, Static, Switch  # noqa: E402

from luma.app import LumaApp                                  # noqa: E402
from luma.config import DEFAULTS, load_config, save_config     # noqa: E402
from luma.screens.main import MainScreen                       # noqa: E402
from luma.screens.settings import SettingsScreen               # noqa: E402

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


async def open_settings(pilot, app):
    await pilot.press("ctrl+s")
    await pilot.pause()
    return app.screen


async def test_shows_current_settings():
    print("\n[shows current settings]")
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "config.json")
        out = os.path.join(td, "vids")
        os.makedirs(out)
        save_config({"output_dir": out, "quality": "720", "max_parallel": 3,
                     "folders": "date", "conns_per_file": 8}, cfg_path)

        app = LumaApp(config_path=cfg_path, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            check("settings screen opened",
                  isinstance(screen, SettingsScreen))
            check("folder is shown",
                  screen.query_one("#set-folder", Input).value == out)
            check("quality is shown",
                  screen.query_one("#set-quality", Select).value == "720")
            check("grouping is shown",
                  screen.query_one("#set-folders", Select).value == "date")
            check("videos at once is shown",
                  screen.query_one("#set-parallel", Input).value == "3")
            check("connections are shown",
                  screen.query_one("#set-conns", Input).value == "8")


async def test_saving_persists():
    print("\n[saving persists]")
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "config.json")
        out = os.path.join(td, "movies")
        os.makedirs(out)

        app = LumaApp(config_path=cfg_path, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            screen.query_one("#set-folder", Input).value = out
            screen.query_one("#set-quality", Select).value = "720"
            screen.query_one("#set-parallel", Input).value = "5"
            screen.query_one("#set-conns", Input).value = "12"
            screen.query_one("#set-folders", Select).value = "date"
            screen.query_one("#set-archive", Switch).value = False
            await pilot.pause()
            await pilot.click("#settings-save")
            await pilot.pause()

            check("returns to the main screen after saving",
                  isinstance(app.screen, MainScreen), type(app.screen).__name__)
            check("app config updated in place",
                  app.config["quality"] == "720", str(app.config["quality"]))

        # A fresh app must see the same values -- this is the real test.
        reloaded = load_config(cfg_path)
        check("quality survived a restart", reloaded["quality"] == "720")
        check("folder survived a restart", reloaded["output_dir"] == out)
        check("videos at once survived a restart", reloaded["max_parallel"] == 5)
        check("connections survived a restart", reloaded["conns_per_file"] == 12)
        check("grouping survived a restart", reloaded["folders"] == "date")
        check("switch survived a restart", reloaded["archive"] is False)


async def test_bad_input_is_refused():
    print("\n[bad input is refused, not saved]")
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "config.json")
        good = os.path.join(td, "good")
        os.makedirs(good)
        save_config({"output_dir": good, "quality": "480"}, cfg_path)

        app = LumaApp(config_path=cfg_path, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)

            # A system folder must be refused.
            screen.query_one("#set-folder", Input).value = "/etc"
            await pilot.pause()
            await pilot.click("#settings-save")
            await pilot.pause()
            check("stays on settings when the folder is bad",
                  isinstance(app.screen, SettingsScreen))
            err = text_of(screen.query_one("#folder-error", Static))
            check("explains the folder problem", len(err) > 0, err)
            check("marks the bad box",
                  screen.query_one("#set-folder", Input).has_class("-invalid"))
            msg = text_of(screen.query_one("#settings-message", Static))
            check("says nothing was saved", "not saved" in msg.lower()
                  or "nothing was saved" in msg.lower(), msg)

            # Out-of-range numbers must be refused too.
            screen.query_one("#set-folder", Input).value = good
            screen.query_one("#set-parallel", Input).value = "9999"
            screen.query_one("#set-conns", Input).value = "0"
            await pilot.pause()
            # Space the clicks out: two clicks in the same spot in quick
            # succession read as a double-click, as they would in any terminal.
            await asyncio.sleep(0.5)
            await pilot.click("#settings-save")
            await pilot.pause()
            check("stays on settings when numbers are out of range",
                  isinstance(app.screen, SettingsScreen))
            check("explains the videos-at-once problem",
                  len(text_of(screen.query_one("#parallel-error", Static))) > 0)
            check("explains the connections problem",
                  len(text_of(screen.query_one("#conns-error", Static))) > 0)

        check("nothing bad reached the settings file",
              load_config(cfg_path)["output_dir"] == good
              and load_config(cfg_path)["quality"] == "480")


async def test_cancel_discards():
    print("\n[cancel discards]")
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "config.json")
        save_config({"quality": "480"}, cfg_path)
        app = LumaApp(config_path=cfg_path, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            screen.query_one("#set-quality", Select).value = "720"
            await pilot.pause()
            await pilot.click("#settings-cancel")
            await pilot.pause()
            check("cancel returns to main",
                  isinstance(app.screen, MainScreen))
        check("the change was discarded",
              load_config(cfg_path)["quality"] == "480")


async def test_reset_to_defaults():
    print("\n[reset to defaults]")
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "config.json")
        save_config({"quality": "720", "max_parallel": 9}, cfg_path)
        app = LumaApp(config_path=cfg_path, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await pilot.click("#settings-reset")
            await pilot.pause()
            check("fields show the defaults again",
                  screen.query_one("#set-quality", Select).value
                  == DEFAULTS["quality"])
            check("reset alone does not save",
                  load_config(cfg_path)["quality"] == "720")


async def test_theme_applies():
    print("\n[appearance]")
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "config.json")
        app = LumaApp(config_path=cfg_path, auto_prepare=False)
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            screen.query_one("#set-theme", Select).value = "luma-day"
            await pilot.pause()
            await pilot.click("#settings-save")
            await pilot.pause()
            check("theme applied immediately",
                  app.theme == "luma-day", str(app.theme))
        check("theme survived a restart",
              load_config(cfg_path)["theme"] == "luma-day")


async def test_language_is_plain():
    print("\n[plain language]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = await open_settings(pilot, app)
        words = " ".join(
            text_of(w) for w in screen.query(Static)
        ).lower()
        labels = " ".join(
            str(getattr(w, "label", "")) for w in screen.query(Button)
        ).lower()
        blob = words + " " + labels
        for jargon in ("yt-dlp", "aria2c", "ffmpeg", "--", "argv", "json"):
            check(f"no {jargon!r} on screen", jargon not in blob)


async def run_all():
    print("=" * 62)
    print("  Luma settings-screen checks")
    print("=" * 62)
    await test_shows_current_settings()
    await test_saving_persists()
    await test_bad_input_is_refused()
    await test_cancel_discards()
    await test_reset_to_defaults()
    await test_theme_applies()
    await test_language_is_plain()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL SETTINGS-SCREEN CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
