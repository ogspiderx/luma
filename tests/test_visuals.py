#!/usr/bin/env python3
"""
Checks for Luma's appearance and its motion.

Luma allows animation in exactly three places, each tied to something the user
is waiting on. These checks confirm those three work, that nothing else moves,
and that the layout holds up in both a light and a dark theme.

    python tests/test_visuals.py
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import (                            # noqa: E402
    Button, Input, LoadingIndicator, ProgressBar, Static,
)

from luma.app import LumaApp                             # noqa: E402
from luma.widgets.download_row import (                  # noqa: E402
    HIGHLIGHT_SECONDS, DownloadRow,
)

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


# --------------------------------------------------------------------------- #
#  1. the spinner                                                             #
# --------------------------------------------------------------------------- #

async def test_spinner_only_while_busy():
    print("\n[1. spinner - only while preparing]")
    app = LumaApp()
    async with app.run_test() as pilot:
        screen = app.screen
        spinner = screen.query_one("#busy", LoadingIndicator)
        check("hidden when the app is idle", spinner.display is False)

        screen._set_busy(True)
        await pilot.pause()
        check("shown once work starts", spinner.display is True)

        screen._set_busy(False)
        await pilot.pause()
        check("hidden again when work ends", spinner.display is False)


# --------------------------------------------------------------------------- #
#  2. the progress bar                                                        #
# --------------------------------------------------------------------------- #

async def test_progress_bar_glides():
    print("\n[2. progress bar - glides rather than jumps]")
    app = LumaApp()
    async with app.run_test() as pilot:
        holder = app.screen.query_one("#downloads")
        row = DownloadRow("1/1", "Test video")
        holder.mount(row)
        await pilot.pause()

        bar = row.query_one(ProgressBar)
        row.set_progress({"percent": 0.0, "total": "10MB", "speed": "1MB/s",
                          "eta": "5s", "connections": 16})
        await asyncio.sleep(0.35)

        row.set_progress({"percent": 90.0, "total": "10MB", "speed": "1MB/s",
                          "eta": "1s", "connections": 16})
        await asyncio.sleep(0.12)
        midway = float(bar.progress)
        await asyncio.sleep(0.45)
        settled = float(bar.progress)

        check("partway through the move mid-animation",
              0.0 < midway < 90.0, f"{midway:.1f}")
        check("arrives exactly on the real value",
              abs(settled - 90.0) < 0.5, f"{settled:.1f}")

        detail = row.query_one(".row-detail", Static)
        text = str(getattr(detail, "content", ""))
        check("detail line reads plainly",
              "1MB/s" in text and "left" in text, text)


# --------------------------------------------------------------------------- #
#  3. the completion highlight                                                #
# --------------------------------------------------------------------------- #

async def test_completion_highlight_is_one_shot():
    print("\n[3. completion highlight - one shot, then settles]")
    app = LumaApp()
    async with app.run_test() as pilot:
        holder = app.screen.query_one("#downloads")
        row = DownloadRow("1/1", "Test video")
        holder.mount(row)
        await pilot.pause()

        row.finish(True, "Saved: Test video.mp4")
        await pilot.pause()
        check("highlight appears the moment it lands",
              row.has_class("-just-finished"))
        check("row is marked as done", row.has_class("-done"))
        check("bar is filled to the end",
              float(row.query_one(ProgressBar).progress) == 100.0)

        await asyncio.sleep(HIGHLIGHT_SECONDS + 0.4)
        check("highlight clears itself afterwards",
              not row.has_class("-just-finished"))
        check("done state remains", row.has_class("-done"))

        failed = DownloadRow("2/2", "Bad video")
        holder.mount(failed)
        await pilot.pause()
        failed.finish(False, "This video is private.")
        await pilot.pause()
        check("a failed row is marked failed", failed.has_class("-failed"))
        check("a failed row is not marked done", not failed.has_class("-done"))


# --------------------------------------------------------------------------- #
#  nothing else moves                                                         #
# --------------------------------------------------------------------------- #

def count_running_animations(app):
    """How many animations the app currently has in flight."""
    animator = app.animator
    for attr in ("_animations", "_scheduled"):
        value = getattr(animator, attr, None)
        if isinstance(value, dict):
            return len(value)
    return 0


async def test_idle_screens_are_still():
    print("\n[nothing else moves]")
    app = LumaApp()
    async with app.run_test() as pilot:
        await asyncio.sleep(0.3)
        check("main screen is still when idle",
              count_running_animations(app) == 0,
              str(count_running_animations(app)))
        check("no spinner running on the main screen",
              app.screen.query_one("#busy", LoadingIndicator).display is False)

        await pilot.press("ctrl+s")
        await pilot.pause()
        await asyncio.sleep(0.3)
        check("settings screen is still",
              count_running_animations(app) == 0,
              str(count_running_animations(app)))
        check("no spinner on the settings screen",
              len(app.screen.query(LoadingIndicator)) == 0)

        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("ctrl+h")
        await pilot.pause()
        await asyncio.sleep(0.3)
        check("history screen is still",
              count_running_animations(app) == 0,
              str(count_running_animations(app)))
        check("no spinner on the history screen",
              len(app.screen.query(LoadingIndicator)) == 0)


# --------------------------------------------------------------------------- #
#  themes                                                                     #
# --------------------------------------------------------------------------- #

async def test_layout_holds_in_both_themes():
    print("\n[light and dark]")
    for theme in ("textual-dark", "textual-light"):
        with tempfile.TemporaryDirectory() as td:
            cfg = os.path.join(td, "config.json")
            from luma.config import save_config
            save_config({"theme": theme, "output_dir": td}, cfg)

            app = LumaApp(config_path=cfg)
            async with app.run_test() as pilot:
                await pilot.pause()
                check(f"{theme}: applied", app.theme == theme, str(app.theme))
                check(f"{theme}: link box present",
                      app.screen.query_one("#url-input", Input) is not None)
                check(f"{theme}: download button present",
                      app.screen.query_one("#download-btn", Button) is not None)

                holder = app.screen.query_one("#downloads")
                row = DownloadRow("1/1", "Colour check")
                holder.mount(row)
                await pilot.pause()
                row.finish(True, "Saved.")
                await pilot.pause()
                check(f"{theme}: a finished row renders",
                      row.has_class("-done"))

                await pilot.press("ctrl+s")
                await pilot.pause()
                check(f"{theme}: settings render",
                      app.screen.query_one("#set-folder", Input) is not None)


async def test_rows_stack_compactly():
    """Several downloads must fit on screen together.

    Guards against a row claiming all remaining space, which lets the first
    download fill the pane and pushes every other one out of sight.
    """
    print("\n[rows stack compactly]")
    app = LumaApp()
    async with app.run_test(size=(84, 34)) as pilot:
        holder = app.screen.query_one("#downloads")
        rows = []
        for i in range(3):
            row = DownloadRow(f"{i + 1}/3", f"Video number {i + 1}")
            holder.mount(row)
            rows.append(row)
            await pilot.pause()
        await asyncio.sleep(0.3)

        heights = [r.region.height for r in rows]
        check("each row is only as tall as its contents",
              all(0 < h <= 6 for h in heights), str(heights))
        check("all three rows are on screen at once",
              all(r.region.y < 34 for r in rows),
              str([r.region.y for r in rows]))
        check("rows do not overlap",
              rows[0].region.y < rows[1].region.y < rows[2].region.y,
              str([r.region.y for r in rows]))


async def test_feedback_is_actually_on_screen():
    """Text a user needs to read must occupy real space, not just exist.

    Guards against styling that hides a populated element: checking a widget's
    text is not enough, since a hidden widget still holds its text.
    """
    print("\n[feedback is really visible]")
    app = LumaApp()
    async with app.run_test(size=(88, 26)) as pilot:
        screen = app.screen
        screen._set_plan("Your speed: 5.6 Mbps   Videos at once: 1")
        await pilot.pause()
        panel = screen.query_one("#plan-panel", Static)
        check("the plan panel takes up space once filled",
              panel.display and panel.region.height > 0,
              f"display={panel.display} h={panel.region.height}")

        await pilot.press("ctrl+s")
        await pilot.pause()
        settings = app.screen
        settings.query_one("#set-folder", Input).value = "/etc"
        await pilot.pause()
        settings._save()
        await pilot.pause()

        error = settings.query_one("#folder-error", Static)
        check("a validation error is visible, not just stored",
              error.display and error.region.height > 0,
              f"display={error.display} h={error.region.height}")
        message = settings.query_one("#settings-message", Static)
        check("the 'nothing was saved' notice is visible",
              message.display and message.region.height > 0,
              f"display={message.display} h={message.region.height}")

        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("ctrl+h")
        await pilot.pause()
        note = app.screen.query_one("#history-empty", Static)
        check("the empty-history note is visible",
              note.display and note.region.height > 0,
              f"display={note.display} h={note.region.height}")


async def run_all():
    print("=" * 62)
    print("  Luma appearance and motion checks")
    print("=" * 62)
    await test_spinner_only_while_busy()
    await test_progress_bar_glides()
    await test_completion_highlight_is_one_shot()
    await test_idle_screens_are_still()
    await test_rows_stack_compactly()
    await test_feedback_is_actually_on_screen()
    await test_layout_holds_in_both_themes()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL APPEARANCE AND MOTION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
