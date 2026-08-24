#!/usr/bin/env python3
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.containers import VerticalScroll
from textual.widgets import Button, Input, Select, Static

from luma.app import LumaApp
from luma.engine import download as dl
from luma.engine.download import _stream_kind, build_cmd
from luma.engine.plan import compute_plan
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


def rows_of(screen):
    holder = screen.query_one("#downloads", VerticalScroll)
    return [w for w in holder.children if isinstance(w, DownloadRow)]


def notifications(app):
    try:
        return [str(n.message) for n in app._notifications]
    except Exception:
        return []


def test_sound_is_fetched_first():
    print("\n[sound is fetched before picture]")
    tools = {"yt-dlp": "yt-dlp", "aria2c": "aria2c",
             "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}
    plan = compute_plan(10, 20, 30, 1, 8)
    fmt = build_cmd(tools, "https://youtu.be/a", plan, "/tmp/o", "480")[2]
    check("sound is named before picture in the request",
          fmt.index("ba") < fmt.index("bv*"), fmt)
    check("the height cap is still applied", "height<=480" in fmt, fmt)

    best = build_cmd(tools, "https://youtu.be/a", plan, "/tmp/o", "best")[2]
    check("same at best quality", best.index("ba") < best.index("bv*"), best)


def test_each_part_is_named():
    print("\n[each part is named]")
    check("an m4a is the sound",
          _stream_kind("/d/Clip [dQw4w9WgXcQ].f140.m4a") == "Sound")
    check("an opus is the sound",
          _stream_kind("/d/Clip [dQw4w9WgXcQ].f251.opus") == "Sound")
    check("an mp4 with a format marker is the picture",
          _stream_kind("/d/Clip [dQw4w9WgXcQ].f135.mp4") == "Picture")
    check("a plain file is neither, it is just the video",
          _stream_kind("/d/Clip [dQw4w9WgXcQ].mp4") == "")
    check("nothing at all is handled", _stream_kind(None) == "")


async def test_row_shows_which_part():
    print("\n[the row says which part is arriving]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        holder = app.screen.query_one("#downloads", VerticalScroll)
        row = DownloadRow("1", "https://youtu.be/dQw4w9WgXcQ")
        holder.mount(row)
        await pilot.pause()

        row.set_progress({"percent": 30.0, "done_bytes": 2 * 1024 ** 2,
                          "total_bytes": 6 * 1024 ** 2, "speed": "800KiB/s",
                          "eta": "5s", "connections": 16, "kind": "Sound"})
        await pilot.pause()
        detail = text_of(row.query_one(".row-detail", Static))
        check("it says Sound while the sound arrives",
              detail.startswith("Sound"), detail)

        row.set_progress({"percent": 70.0, "done_bytes": 30 * 1024 ** 2,
                          "total_bytes": 56 * 1024 ** 2, "speed": "900KiB/s",
                          "eta": "20s", "connections": 16, "kind": "Picture"})
        await pilot.pause()
        detail = text_of(row.query_one(".row-detail", Static))
        check("it says Picture once the picture starts",
              detail.startswith("Picture"), detail)
        check("the figures are still there",
              "30.0 MB of 56.0 MB" in detail, detail)


async def test_more_can_be_added_while_running():
    print("\n[more can be added while something is running]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None

            screen.query_one("#url-input", Input).value = "https://youtu.be/aaa"
            screen._start()
            await pilot.pause()
            check("the first link is listed", len(rows_of(screen)) == 1)
            check("the Download button stays available",
                  not screen.query_one("#download-btn", Button).disabled)

            screen.query_one("#url-input", Input).value = (
                "https://youtu.be/bbb https://youtu.be/ccc"
            )
            screen._start()
            await pilot.pause()
            check("more links join the list", len(rows_of(screen)) == 3,
                  str(len(rows_of(screen))))
            with screen._queue_lock:
                check("and they are all queued", len(screen._queue) == 3,
                      str(len(screen._queue)))

            note = text_of(screen.query_one("#queue-note", Static))
            check("the list says how many are waiting", "waiting" in note, note)

            waiting = rows_of(screen)[1]
            check("a queued row says it is waiting",
                  "waiting" in text_of(
                      waiting.query_one(".row-detail", Static)).lower(),
                  text_of(waiting.query_one(".row-detail", Static)))


async def test_queue_is_worked_through_one_at_a_time():
    print("\n[the queue is worked through, one at a time]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            taken = []

            def fake_batch_run(*args, **kwargs):
                tags = list(kwargs.get("tags") or [])
                urls = list(kwargs.get("urls", args[1]))
                callbacks = kwargs.get("callbacks")
                taken.append(tags)
                results = []
                for i, url in enumerate(urls):
                    path = f"/d/V{i} [dQw4w9WgXcQ].mp4"
                    results.append((url, True, "", path))
                    if callbacks and i < len(tags):
                        callbacks.on_video_done(tags[i], url, True, "", path)
                return results

            screen._settings = lambda: {
                "output_dir": td, "quality": "480", "max_parallel": 1,
                "conns_per_file": None, "archive": False,
                "run_speedtest": False,
            }
            import luma.screens.main as main_mod
            main_mod.ensure_tools = lambda cb=None: {"yt-dlp": "/bin/true",
                                                     "aria2c": "a",
                                                     "ffmpeg": "/usr/bin/ffmpeg",
                                                     "ffprobe": "/usr/bin/ffprobe"}
            main_mod.expand_playlists = lambda y, u, cb=None: list(u)
            main_mod.record_results = lambda r, quality=None: None
            real_run = dl.run_downloads
            dl.run_downloads = fake_batch_run
            try:
                screen.query_one("#url-input", Input).value = (
                    "https://youtu.be/aaa https://youtu.be/bbb "
                    "https://youtu.be/ccc"
                )
                screen._start()
                for _ in range(200):
                    if not screen._download_active:
                        break
                    await asyncio.sleep(0.05)
                await pilot.pause()
            finally:
                dl.run_downloads = real_run

            check("with one at a time, three batches were run",
                  len(taken) == 3, str(taken))
            check("each batch held a single video",
                  all(len(b) == 1 for b in taken), str(taken))
            check("they ran in the order they were added",
                  taken == [["1"], ["2"], ["3"]], str(taken))
            with screen._queue_lock:
                check("the queue is empty afterwards", not screen._queue)
            check("everything is marked finished",
                  all(r.finished for r in rows_of(screen)))


async def test_cross_removes_a_waiting_row():
    print("\n[the cross takes a waiting row out of the queue]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            screen.query_one("#url-input", Input).value = (
                "https://youtu.be/aaa https://youtu.be/bbb"
            )
            screen._start()
            await pilot.pause()
            check("two are listed", len(rows_of(screen)) == 2)

            second = rows_of(screen)[1]
            second.post_message(DownloadRow.RemoveRequested(second))
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()

            check("the row is gone", len(rows_of(screen)) == 1,
                  str(len(rows_of(screen))))
            check("the one left is the other link",
                  rows_of(screen)[0].url == "https://youtu.be/aaa")
            with screen._queue_lock:
                check("it was taken off the queue too",
                      len(screen._queue) == 1, str(screen._queue))
            check("the bookkeeping matches", set(screen._rows) == {"1"},
                  str(set(screen._rows)))


async def test_cross_stops_a_running_row():
    print("\n[the cross stops a running row without touching the rest]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        dl.reset_cancel()
        holder = screen.query_one("#downloads", VerticalScroll)
        for i in (1, 2):
            row = DownloadRow(str(i), f"https://youtu.be/{i}")
            holder.mount(row)
            screen._rows[str(i)] = row
            await pilot.pause()
            row.set_progress({"percent": 40.0, "done_bytes": 1,
                              "total_bytes": 2, "speed": "1KiB/s",
                              "eta": "1s", "connections": 8, "kind": ""})
        await pilot.pause()

        first = screen._rows["1"]
        first.post_message(DownloadRow.RemoveRequested(first))
        await pilot.pause()
        await asyncio.sleep(0.1)
        await pilot.pause()

        check("that one was asked to stop", dl.is_tag_cancelled("1"))
        check("the other was not", not dl.is_tag_cancelled("2"))
        check("everything else keeps going", not dl.is_cancelled())
        check("the row is gone from the list", len(rows_of(screen)) == 1)
        dl.reset_cancel()


async def build_list(screen, pilot):
    holder = screen.query_one("#downloads", VerticalScroll)
    spec = [("1", "Banana", "done", 100.0),
            ("2", "Apple", "running", 40.0),
            ("3", "Cherry", "failed", 10.0)]
    for tag, title, state, pct in spec:
        row = DownloadRow(tag, f"https://youtu.be/{tag}")
        row.sequence = int(tag)
        holder.mount(row)
        screen._rows[tag] = row
        await pilot.pause()
        row.set_title(title)
        if state == "running":
            row.set_progress({"percent": pct, "done_bytes": 1,
                              "total_bytes": 2, "speed": "1KiB/s",
                              "eta": "1s", "connections": 8, "kind": ""})
        elif state == "done":
            row.finish(True, "")
        else:
            row.set_progress({"percent": pct, "done_bytes": 1,
                              "total_bytes": 2, "speed": "1KiB/s",
                              "eta": "1s", "connections": 8, "kind": ""})
            row.finish(False, "This video is private.")
    await pilot.pause()


async def test_sorting():
    print("\n[the list can be arranged]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        await build_list(screen, pilot)

        def order():
            return [r.tag for r in rows_of(screen)]

        check("it starts in the order added", order() == ["1", "2", "3"],
              str(order()))

        screen._sort_mode = "name"
        screen._apply_sort()
        await pilot.pause()
        check("by name puts Apple, Banana, Cherry",
              order() == ["2", "1", "3"], str(order()))

        screen._sort_mode = "unfinished"
        screen._apply_sort()
        await pilot.pause()
        check("unfinished first puts the running one on top",
              order()[0] == "2", str(order()))

        screen._sort_mode = "finished"
        screen._apply_sort()
        await pilot.pause()
        check("finished first puts the running one last",
              order()[-1] == "2", str(order()))

        screen._sort_mode = "progress"
        screen._apply_sort()
        await pilot.pause()
        check("furthest along puts the finished one on top",
              order()[0] == "1", str(order()))

        screen._sort_mode = "added"
        screen._apply_sort()
        await pilot.pause()
        check("and it can go back to the order added",
              order() == ["1", "2", "3"], str(order()))


async def test_sort_control_is_wired():
    print("\n[the sorting control works]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        header = screen.query_one("#list-header")
        check("the control is hidden while the list is empty",
              header.display is False)

        await build_list(screen, pilot)
        screen._after_list_change()
        await pilot.pause()
        check("it appears once there is a list", header.display is True)

        chooser = screen.query_one("#sort-select", Select)
        chooser.value = "name"
        await pilot.pause()
        check("choosing a different order rearranges the list",
              [r.tag for r in rows_of(screen)] == ["2", "1", "3"],
              str([r.tag for r in rows_of(screen)]))
        check("the screen remembers the choice", screen._sort_mode == "name")

        every = [value for _, value in
                 __import__("luma.screens.main", fromlist=["x"]).SORT_OPTIONS]
        for mode in every:
            screen._sort_mode = mode
            screen._apply_sort()
            await pilot.pause()
            check(f"'{mode}' keeps every row", len(rows_of(screen)) == 3,
                  str(len(rows_of(screen))))


async def test_queue_positions_stay_correct():
    print("\n[queue positions keep up with the list]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None

            def detail(row):
                return text_of(row.query_one(".row-detail", Static))

            def positions():
                return [detail(r) for r in rows_of(screen)]

            screen.query_one("#url-input", Input).value = (
                "https://youtu.be/aaa https://youtu.be/bbb https://youtu.be/ccc"
            )
            screen._start()
            await pilot.pause()
            check("the first says it is next",
                  positions()[0] == "Next up", str(positions()))
            check("the rest are numbered in order",
                  "2" in positions()[1] and "3" in positions()[2],
                  str(positions()))

            screen.query_one("#url-input", Input).value = "https://youtu.be/ddd"
            screen._start()
            await pilot.pause()
            check("a new arrival goes on the end",
                  "4" in positions()[3], str(positions()))
            check("the earlier places are unchanged",
                  positions()[0] == "Next up" and "2" in positions()[1],
                  str(positions()))

            note = text_of(screen.query_one("#queue-note", Static))
            check("the count says four are waiting", "4 waiting" in note, note)

            first = rows_of(screen)[0]
            first.post_message(DownloadRow.RemoveRequested(first))
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()

            check("three are left", len(rows_of(screen)) == 3,
                  str(len(rows_of(screen))))
            check("the one behind it is now next",
                  positions()[0] == "Next up", str(positions()))
            check("and the others moved up too",
                  "2" in positions()[1] and "3" in positions()[2],
                  str(positions()))
            note = text_of(screen.query_one("#queue-note", Static))
            check("the count came down to three", "3 waiting" in note, note)

            middle = rows_of(screen)[1]
            middle.post_message(DownloadRow.RemoveRequested(middle))
            await pilot.pause()
            await asyncio.sleep(0.1)
            await pilot.pause()

            check("two are left", len(rows_of(screen)) == 2,
                  str(len(rows_of(screen))))
            check("the first is still next", positions()[0] == "Next up",
                  str(positions()))
            check("the one after the gap became number two",
                  "2" in positions()[1], str(positions()))
            check("no stale number is left behind",
                  "3" not in " ".join(positions()), str(positions()))


async def test_positions_update_when_clearing():
    print("\n[clearing does not strand the numbering]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None
            screen.query_one("#url-input", Input).value = (
                "https://youtu.be/aaa https://youtu.be/bbb"
            )
            screen._start()
            await pilot.pause()

            holder = screen.query_one("#downloads", VerticalScroll)
            done = DownloadRow("99", "https://youtu.be/zzz")
            done.sequence = 0
            holder.mount(done)
            screen._rows["99"] = done
            await pilot.pause()
            done.finish(True, "")
            screen._after_list_change()
            await pilot.pause()

            screen.action_clear_finished()
            await pilot.pause()

            remaining = rows_of(screen)
            check("the finished row went", len(remaining) == 2,
                  str(len(remaining)))
            details = [text_of(r.query_one(".row-detail", Static))
                       for r in remaining]
            check("the waiting rows are still numbered from one",
                  details[0] == "Next up" and "2" in details[1], str(details))


async def run_all():
    print("=" * 62)
    print("  Luma queue, sorting and row-removal checks")
    print("=" * 62)
    await test_queue_positions_stay_correct()
    await test_positions_update_when_clearing()
    test_sound_is_fetched_first()
    test_each_part_is_named()
    await test_row_shows_which_part()
    await test_more_can_be_added_while_running()
    await test_queue_is_worked_through_one_at_a_time()
    await test_cross_removes_a_waiting_row()
    await test_cross_stops_a_running_row()
    await test_sorting()
    await test_sort_control_is_wired()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL QUEUE AND SORTING CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
