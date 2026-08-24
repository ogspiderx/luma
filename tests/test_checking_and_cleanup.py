#!/usr/bin/env python3
import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luma.app import LumaApp
from luma.engine import download as dl
from luma.screens import main as main_mod
from luma.widgets.download_row import QualityChip

_failures = []

FAKE_TOOLS = {"yt-dlp": "yt-dlp", "aria2c": "aria2c", "ffmpeg": "ffmpeg"}

TWO_CHOICES = [
    {"height": 720, "label": "720p", "note": "about 105.0 MB",
     "filesize": 105 * 1024 ** 2},
    {"height": 480, "label": "480p", "note": "about 55.0 MB",
     "filesize": 55 * 1024 ** 2},
]


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


def link(n):
    return f"https://youtu.be/{'abcdefghij' + str(n)}"


async def settled(screen, pilot, timeout=8.0):
    deadline = time.monotonic() + timeout
    while screen._checking and time.monotonic() < deadline:
        await pilot.pause()
        await asyncio.sleep(0.02)
    await pilot.pause()


def fake_lookup(delay=0.0, choices=None, title="A Test Video"):
    def lookup(_ytdlp, _url, *args, **kwargs):
        if delay:
            time.sleep(delay)
        return title, list(choices or [])
    return lookup


class patched:
    def __init__(self, lookup):
        self._lookup = lookup

    def __enter__(self):
        self._real = main_mod.available_qualities
        main_mod.available_qualities = self._lookup

    def __exit__(self, *_exc):
        main_mod.available_qualities = self._real


async def prepared_app(td):
    app = LumaApp(config_path=os.path.join(td, "config.json"),
                  auto_prepare=False)
    app.tools = FAKE_TOOLS
    return app


def configure(app, **values):
    app.config.update(values)


async def test_rows_appear_straight_away():
    print("\n[the links are listed at once]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            with patched(fake_lookup(delay=0.4)):
                urls = [link(i) for i in range(3)]
                screen._begin_checks(urls)
                check("every link is in the list immediately",
                      len(screen._rows) == 3, str(len(screen._rows)))
                check("none of them is on the download queue yet",
                      screen._queue == [], str(screen._queue))
                check("each is marked as being checked",
                      all(t in screen._checking for t in screen._rows),
                      str(screen._checking))

                await pilot.pause()
                row = list(screen._rows.values())[0]
                check("and says so on screen",
                      "Checking" in row._detail, row._detail)
                await settled(screen, pilot)


async def test_more_can_be_added_while_checking():
    print("\n[more links can be added while the first are being checked]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            with patched(fake_lookup(delay=0.4)):
                screen._begin_checks([link(1), link(2)])
                await pilot.pause()
                check("the first pair is being checked",
                      len(screen._checking) == 2, str(screen._checking))

                screen._begin_checks([link(3)])
                check("a third can be added mid-check",
                      len(screen._rows) == 3, str(len(screen._rows)))
                check("and joins the ones being checked",
                      len(screen._checking) == 3, str(screen._checking))
                await settled(screen, pilot)


async def test_the_setting_turns_checking_on():
    print("\n[the setting decides whether links are checked at all]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            box = screen.query_one("#url-input")

            with patched(fake_lookup(choices=TWO_CHOICES)):
                box.value = link(1)
                screen._start()
                await pilot.pause()
                check("with the setting off, the link is queued as it is",
                      len(screen._queue) == 1 and not screen._checking,
                      str(screen._queue))

                configure(app, ask_quality=True)
                box.value = link(2)
                screen._start()
                check("with it on, the link is checked first",
                      len(screen._checking) == 1, str(screen._checking))
                await settled(screen, pilot)
                check("and ends up being asked about",
                      len(screen._awaiting) == 1, str(screen._awaiting))


async def test_lookups_run_side_by_side():
    print("\n[several links are checked at the same time]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            each = 0.3
            count = main_mod.PROBE_AT_ONCE
            with patched(fake_lookup(delay=each, choices=[])):
                started = time.monotonic()
                screen._begin_checks([link(i) for i in range(count)])
                await settled(screen, pilot)
                elapsed = time.monotonic() - started

            one_at_a_time = each * count
            check(f"{count} links take about as long as one, not {count} "
                  f"(took {elapsed:.2f}s)",
                  elapsed < one_at_a_time * 0.7, f"{elapsed:.2f}s")
            check("all of them ended up on the queue",
                  len(screen._queue) == count, str(screen._queue))
            check("an unreadable link falls back to the usual setting",
                  all(entry[2] is None for entry in screen._queue),
                  str(screen._queue))


def chips_of(row):
    return list(row.query(QualityChip))


async def test_choosing_starts_it_without_waiting_for_the_rest():
    print("\n[answering one starts it, the rest carry on]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test(size=(90, 30)) as pilot:
            screen = app.screen
            started = []
            screen._queue_worker = lambda: started.append(True)

            with patched(fake_lookup(choices=TWO_CHOICES)):
                screen._begin_checks([link(1), link(2), link(3)])
                await settled(screen, pilot)

                check("nothing took over the whole screen",
                      type(app.screen).__name__ == "MainScreen",
                      type(app.screen).__name__)
                check("every row is asking for itself",
                      len(screen._awaiting) == 3, str(screen._awaiting))
                check("all three questions are visible at once",
                      all(row.choosing for row in screen._rows.values()))
                check("the cursor is already on the first one",
                      isinstance(app.focused, QualityChip), str(app.focused))

                first = screen._rows[sorted(screen._rows)[0]]
                await pilot.click(chips_of(first)[0])
                await pilot.pause()

                check("the answered link is queued at that quality",
                      len(screen._queue) == 1
                      and screen._queue[0][2] == "720", str(screen._queue))
                check("downloading begins before the rest are answered",
                      started, "the queue worker was not started")
                check("two questions are still open",
                      len(screen._awaiting) == 2, str(screen._awaiting))
                check("and the cursor moved to the next one",
                      isinstance(app.focused, QualityChip), str(app.focused))


async def test_one_answer_can_cover_the_rest():
    print("\n[one answer for all of them]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test(size=(90, 30)) as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None

            with patched(fake_lookup(choices=TWO_CHOICES)):
                screen._begin_checks([link(i) for i in range(5)])
                await settled(screen, pilot)

                check("'same for all' is offered while several are asking",
                      screen.check_action("same_for_all", ()) is True)

                first = screen._rows[sorted(screen._rows, key=int)[0]]
                await pilot.click(chips_of(first)[1])
                await pilot.pause()
                check("one is answered", len(screen._awaiting) == 4,
                      str(screen._awaiting))

                await pilot.press("ctrl+a")
                await pilot.pause()

                check("nothing is left asking", screen._awaiting == set(),
                      str(screen._awaiting))
                check("all five are queued", len(screen._queue) == 5,
                      str(len(screen._queue)))
                check("every one at the quality that was picked",
                      all(entry[2] == "480" for entry in screen._queue),
                      str(screen._queue))
                check("and it is no longer offered",
                      screen.check_action("same_for_all", ()) is False)
                check("the answer does not carry over to a later paste",
                      screen._last_choice is None, str(screen._last_choice))


async def test_same_for_all_falls_back_to_the_setting():
    print("\n[same for all, without picking one first]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test(size=(90, 30)) as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            configure(app, quality="360")
            with patched(fake_lookup(choices=TWO_CHOICES)):
                screen._begin_checks([link(1), link(2)])
                await settled(screen, pilot)

                await pilot.press("ctrl+a")
                await pilot.pause()
                check("the usual setting is used when nothing was picked",
                      all(entry[2] == "360" for entry in screen._queue),
                      str(screen._queue))


async def test_skipping_takes_the_row_away():
    print("\n[skipping a link]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test(size=(90, 30)) as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            with patched(fake_lookup(choices=TWO_CHOICES)):
                screen._begin_checks([link(1)])
                await settled(screen, pilot)
                row = list(screen._rows.values())[0]
                await pilot.click(chips_of(row)[-1])
                await pilot.pause()
                check("the row goes with it", screen._rows == {},
                      str(screen._rows))
                check("and nothing is queued", screen._queue == [],
                      str(screen._queue))
                check("Luma is ready again",
                      not screen._checking and not screen._awaiting)


async def test_a_question_never_steals_the_keyboard():
    print("\n[a question arriving mid-typing]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test(size=(90, 30)) as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            box = screen.query_one("#url-input")
            with patched(fake_lookup(delay=0.25, choices=TWO_CHOICES)):
                screen._begin_checks([link(1)])
                await pilot.pause()
                box.focus()
                box.value = "https://youtu.be/half-typed"
                await pilot.pause()
                await settled(screen, pilot)
                check("the cursor stays in the box being typed in",
                      app.focused is box, str(app.focused))
                check("but the question is there to answer",
                      len(screen._awaiting) == 1, str(screen._awaiting))


async def test_a_row_removed_mid_check_is_forgotten():
    print("\n[taking a link out while it is being checked]")
    with tempfile.TemporaryDirectory() as td:
        app = await prepared_app(td)
        async with app.run_test(size=(90, 30)) as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            with patched(fake_lookup(delay=0.3, choices=TWO_CHOICES)):
                screen._begin_checks([link(1), link(2)])
                await pilot.pause()

                gone = list(screen._rows.values())[0]
                screen.on_download_row_remove_requested(
                    gone.RemoveRequested(gone))
                await pilot.pause()
                check("it is out of the list at once",
                      len(screen._rows) == 1, str(len(screen._rows)))
                check("removing a link being checked stops nothing running",
                      not dl.is_tag_cancelled(gone.tag))

                await settled(screen, pilot)
                check("its answer is discarded when it arrives",
                      gone.tag not in screen._awaiting
                      and all(e[0] != gone.tag for e in screen._queue),
                      str(screen._awaiting))


def test_leftovers_are_cleared():
    print("\n[half-finished files are cleared away]")
    with tempfile.TemporaryDirectory() as td:
        names = [
            "Song [dQw4w9WgXcQ].f140.m4a.part",
            "Song [dQw4w9WgXcQ].f140.m4a.aria2",
            "Song [dQw4w9WgXcQ].f135.mp4.part-Frag1",
            "Song [dQw4w9WgXcQ].mp4",
            "Other [CdbHAzNB1n0].f135.mp4.part",
        ]
        for name in names:
            open(os.path.join(td, name), "w").close()

        removed = dl.clean_partials(td, "Song [dQw4w9WgXcQ].mp4")
        left = sorted(os.listdir(td))
        check("only that video's pieces go", removed == 3, str(removed))
        check("the finished file stays",
              "Song [dQw4w9WgXcQ].mp4" in left, str(left))
        check("another video's pieces are left alone",
              "Other [CdbHAzNB1n0].f135.mp4.part" in left, str(left))
        check("nothing else remains", len(left) == 2, str(left))


def test_leftovers_can_be_found_from_a_link():
    print("\n[the video is recognised from its link too]")
    with tempfile.TemporaryDirectory() as td:
        for name in ["A [dQw4w9WgXcQ].f140.m4a.part",
                     "B [CdbHAzNB1n0].f140.m4a.part"]:
            open(os.path.join(td, name), "w").close()
        removed = dl.clean_partials(td, "https://youtu.be/dQw4w9WgXcQ")
        left = sorted(os.listdir(td))
        check("the id is read out of the link", removed == 1, str(removed))
        check("the other video is untouched",
              left == ["B [CdbHAzNB1n0].f140.m4a.part"], str(left))

        removed = dl.clean_partials(td, "https://youtube.com/watch?v=CdbHAzNB1n0")
        check("a full link works as well", removed == 1, str(removed))
        check("the folder is clear now", os.listdir(td) == [],
              str(os.listdir(td)))


def test_clearing_is_safe_when_there_is_nothing_to_clear():
    print("\n[nothing to clear]")
    with tempfile.TemporaryDirectory() as td:
        check("an empty folder is fine", dl.clean_partials(td) == 0)
        open(os.path.join(td, "Kept.mp4"), "w").close()
        check("finished files are never touched",
              dl.clean_partials(td) == 0
              and os.listdir(td) == ["Kept.mp4"], str(os.listdir(td)))
    check("a folder that is not there is fine",
          dl.clean_partials(os.path.join(td, "gone")) == 0)


def test_clearing_everything_when_no_video_is_named():
    print("\n[clearing the lot]")
    with tempfile.TemporaryDirectory() as td:
        for name in ["A [dQw4w9WgXcQ].f140.m4a.part",
                     "B [CdbHAzNB1n0].mp4.ytdl",
                     "C.temp", "D.mp4"]:
            open(os.path.join(td, name), "w").close()
        removed = dl.clean_partials(td)
        check("every leftover goes", removed == 3, str(removed))
        check("the finished file stays", os.listdir(td) == ["D.mp4"],
              str(os.listdir(td)))


async def run_all():
    print("=" * 62)
    print("  Luma link-checking and clean-up checks")
    print("=" * 62)
    await test_rows_appear_straight_away()
    await test_more_can_be_added_while_checking()
    await test_the_setting_turns_checking_on()
    await test_lookups_run_side_by_side()
    await test_choosing_starts_it_without_waiting_for_the_rest()
    await test_one_answer_can_cover_the_rest()
    await test_same_for_all_falls_back_to_the_setting()
    await test_skipping_takes_the_row_away()
    await test_a_question_never_steals_the_keyboard()
    await test_a_row_removed_mid_check_is_forgotten()
    test_leftovers_are_cleared()
    test_leftovers_can_be_found_from_a_link()
    test_clearing_is_safe_when_there_is_nothing_to_clear()
    test_clearing_everything_when_no_video_is_named()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL CHECKING AND CLEAN-UP CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
