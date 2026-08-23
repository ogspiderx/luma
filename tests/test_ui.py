#!/usr/bin/env python3
"""
Automated checks for Luma's terminal interface, driven headlessly by Textual's
Pilot. These run without a real terminal, so they are the repeatable proof the
UI works; looking at it by eye is a supplement, not a substitute.

    python tests/test_ui.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import Button, Input, Static      # noqa: E402

from luma.app import LumaApp                           # noqa: E402
from luma.screens.history import HistoryScreen         # noqa: E402
from luma.screens.main import MainScreen               # noqa: E402
from luma.screens.settings import SettingsScreen       # noqa: E402

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


async def test_boots_and_shows_chrome():
    print("\n[app boots]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        check("main screen is on top",
              isinstance(app.screen, MainScreen), type(app.screen).__name__)
        check("link box is present", app.screen.query(Input))
        check("download button is present",
              app.screen.query_one("#download-btn", Button) is not None)
        check("status line is present",
              app.screen.query_one("#status-line", Static) is not None)
        check("link box has focus on arrival",
              isinstance(app.focused, Input))
        await pilot.pause()


async def test_settings_opens_and_closes():
    print("\n[settings screen]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        depth = len(app.screen_stack)
        await pilot.press("ctrl+s")
        await pilot.pause()
        check("settings opened via keyboard",
              isinstance(app.screen, SettingsScreen), type(app.screen).__name__)
        check("screen stack grew", len(app.screen_stack) == depth + 1)

        await pilot.press("escape")
        await pilot.pause()
        check("escape returns to main",
              isinstance(app.screen, MainScreen), type(app.screen).__name__)
        check("screen stack unwound", len(app.screen_stack) == depth)


async def test_settings_back_button():
    print("\n[leaving settings by button]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.click("#settings-cancel")
        await pilot.pause()
        check("cancel button returns to main",
              isinstance(app.screen, MainScreen), type(app.screen).__name__)


async def test_history_opens_and_closes():
    print("\n[history screen]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+h")
        await pilot.pause()
        check("history opened via keyboard",
              isinstance(app.screen, HistoryScreen), type(app.screen).__name__)
        await pilot.press("escape")
        await pilot.pause()
        check("escape returns to main",
              isinstance(app.screen, MainScreen), type(app.screen).__name__)


async def test_typing_a_link():
    print("\n[typing]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        box = app.screen.query_one("#url-input", Input)
        box.focus()
        await pilot.pause()
        await pilot.press(*"https://youtu.be/abc")
        await pilot.pause()
        check("typed text lands in the link box",
              box.value == "https://youtu.be/abc", box.value)


async def run_all():
    print("=" * 62)
    print("  Luma interface checks")
    print("=" * 62)
    await test_boots_and_shows_chrome()
    await test_settings_opens_and_closes()
    await test_settings_back_button()
    await test_history_opens_and_closes()
    await test_typing_a_link()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL INTERFACE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
