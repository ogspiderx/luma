#!/usr/bin/env python3
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import DataTable, Static

from luma.app import LumaApp
from luma.history import record_failure, record_success
from luma.screens.history import HistoryScreen
from luma.screens.main import MainScreen

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


def cells(table):
    out = []
    for row_key in table.rows:
        out.append([str(c) for c in table.get_row(row_key)])
    return out


def seed(td):
    hist = os.path.join(td, "history.json")
    errs = os.path.join(td, "errors.json")
    video = os.path.join(td, "Holiday Clip [dQw4w9WgXcQ].mp4")
    with open(video, "wb") as fh:
        fh.write(b"v" * (3 * 1024 * 1024))
    record_success("https://youtu.be/aaa", video, "480", hist)
    record_success("https://youtu.be/bbb", os.path.join(td, "Song [CdbHAzNB1n0].mp4"),
                   "best", hist)
    record_failure("https://youtu.be/ccc", "This video is private.", errs)
    record_failure("https://youtu.be/ddd", "The connection dropped.", errs)
    return hist, errs


async def test_shows_what_is_on_disk():
    print("\n[shows what is on disk]")
    with tempfile.TemporaryDirectory() as td:
        hist, errs = seed(td)
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            check("history screen opened",
                  isinstance(app.screen, HistoryScreen))

            table = app.screen.query_one("#history-table", DataTable)
            rows = cells(table)
            check("both downloads listed", len(rows) == 2, str(len(rows)))
            check("newest download first",
                  rows[0][0] == "Song", str(rows[0]))
            check("title shown without the video id",
                  rows[1][0] == "Holiday Clip", str(rows[1]))
            check("size shown readably", "MB" in rows[1][2], rows[1][2])
            check("time shown readably", "Today" in rows[1][1], rows[1][1])
            check("quality shown with a p", rows[1][3] == "480p", rows[1][3])
            check("best quality spelled out", rows[0][3] == "Best", rows[0][3])

            errors = app.screen.query_one("#errors-table", DataTable)
            erows = cells(errors)
            check("both problems listed", len(erows) == 2, str(len(erows)))
            check("problem explains itself",
                  "private" in erows[1][1].lower(), erows[1][1])
            check("problem keeps the link",
                  "youtu.be/ccc" in erows[1][0], erows[1][0])


async def test_downloads_and_problems_stay_apart():
    print("\n[downloads and problems stay apart]")
    with tempfile.TemporaryDirectory() as td:
        hist, errs = seed(td)
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            downloads = " ".join(
                " ".join(r) for r in
                cells(app.screen.query_one("#history-table", DataTable))
            )
            problems = " ".join(
                " ".join(r) for r in
                cells(app.screen.query_one("#errors-table", DataTable))
            )
            check("failures are not in the downloads list",
                  "private" not in downloads.lower(), downloads)
            check("downloads are not in the problems list",
                  "Holiday Clip" not in problems, problems)


async def test_empty_state():
    print("\n[nothing recorded yet]")
    with tempfile.TemporaryDirectory() as td:
        hist = os.path.join(td, "history.json")
        errs = os.path.join(td, "errors.json")
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            screen = app.screen
            check("downloads table is empty",
                  len(cells(screen.query_one("#history-table", DataTable))) == 0)
            note = text_of(screen.query_one("#history-empty", Static))
            check("says so in plain words", "nothing" in note.lower(), note)
            enote = text_of(screen.query_one("#errors-empty", Static))
            check("problems tab says so too",
                  "no problems" in enote.lower(), enote)


async def test_damaged_records_do_not_crash():
    print("\n[damaged records]")
    with tempfile.TemporaryDirectory() as td:
        hist = os.path.join(td, "history.json")
        errs = os.path.join(td, "errors.json")
        with open(hist, "w") as fh:
            fh.write("{{{ not json at all")
        with open(errs, "w") as fh:
            fh.write("")
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            check("screen still opens",
                  isinstance(app.screen, HistoryScreen))
            check("shows an empty list rather than failing",
                  len(cells(app.screen.query_one("#history-table",
                                                 DataTable))) == 0)


async def test_reads_fresh_each_time():
    print("\n[reads fresh from disk]")
    with tempfile.TemporaryDirectory() as td:
        hist, errs = seed(td)
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            before = len(cells(app.screen.query_one("#history-table",
                                                    DataTable)))
            await pilot.press("escape")
            await pilot.pause()

            record_success("https://youtu.be/eee",
                           os.path.join(td, "Later [nY0FYp8y4Lo].mp4"), "720", hist)

            await pilot.press("ctrl+h")
            await pilot.pause()
            after = cells(app.screen.query_one("#history-table", DataTable))
            check("reopening picks up the new entry",
                  len(after) == before + 1, f"{before} -> {len(after)}")
            check("the new entry is at the top",
                  after[0][0] == "Later", str(after[0]))


async def test_leaving_the_screen():
    print("\n[leaving the screen]")
    with tempfile.TemporaryDirectory() as td:
        hist, errs = seed(td)
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            await pilot.click("#history-back")
            await pilot.pause()
            check("back button returns to main",
                  isinstance(app.screen, MainScreen), type(app.screen).__name__)

            await pilot.press("ctrl+h")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            check("escape returns to main",
                  isinstance(app.screen, MainScreen), type(app.screen).__name__)


async def test_plain_language():
    print("\n[plain language]")
    with tempfile.TemporaryDirectory() as td:
        hist, errs = seed(td)
        app = LumaApp(history_path=hist, errors_path=errs, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+h")
            await pilot.pause()
            screen = app.screen
            blob = " ".join(text_of(w) for w in screen.query(Static))
            for row in cells(screen.query_one("#history-table", DataTable)):
                blob += " " + " ".join(row)
            for row in cells(screen.query_one("#errors-table", DataTable)):
                blob += " " + " ".join(row)
            blob = blob.lower()
            for jargon in ("yt-dlp", "aria2c", "ffmpeg", "traceback", "json"):
                check(f"no {jargon!r} on screen", jargon not in blob)


async def run_all():
    print("=" * 62)
    print("  Luma history-screen checks")
    print("=" * 62)
    await test_shows_what_is_on_disk()
    await test_downloads_and_problems_stay_apart()
    await test_empty_state()
    await test_damaged_records_do_not_crash()
    await test_reads_fresh_each_time()
    await test_leaving_the_screen()
    await test_plain_language()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL HISTORY-SCREEN CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
