#!/usr/bin/env python3
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.containers import VerticalScroll
from textual.widgets import Button, Input, Static

from luma.app import LumaApp
from luma.engine.paths import title_from_filename
from luma.engine.plan import compute_plan, describe_plan
from luma.widgets.download_row import (
    DownloadRow, rate_to_bytes,
)

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


def notifications(app):
    try:
        return [str(n.message) for n in app._notifications]
    except Exception:
        return []


def test_title_read_from_filename():
    print("\n[1. the title is recovered from the file being written]")
    cases = [
        ("/d/Suno Chanda Episode #1 HUM TV [ODl-DYTyNyM].f135.mp4",
         "Suno Chanda Episode #1 HUM TV"),
        ("/d/Songs that keep you awake [CdbHAzNB1n0].mp4",
         "Songs that keep you awake"),
        (r"C:\Users\A\d\My Video [Qwm6BSGrOq0].f140.m4a", "My Video"),
    ]
    for path, expected in cases:
        check(f"reads {expected!r}", title_from_filename(path) == expected,
              title_from_filename(path))
    check("copes with no path", title_from_filename(None) == "")


async def test_row_shows_title_once_known():
    print("\n[1b. the row swaps the link for the title]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        holder = app.screen.query_one("#downloads", VerticalScroll)
        url = "https://youtu.be/Qwm6BSGrOq0?list=RDQwm6BSGrOq0"
        row = DownloadRow("1", url)
        holder.mount(row)
        await pilot.pause()

        title_widget = row.query_one(".row-title", Static)
        shown = text_of(title_widget)
        check("starts with something honest, not the raw link",
              url not in shown and shown.strip() != "", shown)

        row.set_title("Songs that keep you awake")
        await pilot.pause()
        shown = text_of(title_widget)
        check("shows the real title once known",
              shown == "Songs that keep you awake", shown)
        check("the link is no longer displayed", url not in shown, shown)
        check("but the row still knows its link", row.url == url)


async def test_duplicate_warnings():
    print("\n[2. duplicates are pointed out]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"), auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen

            urls, notices = screen._filter_duplicates(
                ["https://youtu.be/aaa", "https://youtu.be/aaa",
                 "https://youtu.be/bbb"]
            )
            check("repeats are dropped", urls == ["https://youtu.be/aaa",
                                                  "https://youtu.be/bbb"],
                  str(urls))
            check("and the user is told", any("repeat" in n.lower()
                                              for n in notices), str(notices))

            holder = screen.query_one("#downloads", VerticalScroll)
            holder.mount(DownloadRow("1", "https://youtu.be/aaa"))
            screen._rows["1"] = holder.children[-1]
            await pilot.pause()

            urls, notices = screen._filter_duplicates(
                ["https://youtu.be/aaa", "https://youtu.be/ccc"]
            )
            check("a link already listed is not queued again",
                  urls == ["https://youtu.be/ccc"], str(urls))
            check("and that is explained",
                  any("already in the list" in n.lower() for n in notices),
                  str(notices))

            urls, notices = screen._filter_duplicates(["https://youtu.be/aaa"])
            check("everything filtered leaves nothing queued", urls == [])
            check("with a reason given", len(notices) >= 1, str(notices))


async def test_duplicate_paste_does_not_start_a_download():
    print("\n[2b. pasting an already-listed link starts nothing]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"), auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            holder = screen.query_one("#downloads", VerticalScroll)
            row = DownloadRow("1", "https://youtu.be/aaa")
            holder.mount(row)
            screen._rows["1"] = row
            await pilot.pause()

            screen.query_one("#url-input", Input).value = "https://youtu.be/aaa"
            screen._start()
            await pilot.pause()
            check("no download was started", not screen._download_active)
            check("no second row was added",
                  len(screen.query(DownloadRow)) == 1,
                  str(len(screen.query(DownloadRow))))
            check("the user was warned",
                  any("already" in n.lower() for n in notifications(app)),
                  str(notifications(app)))


async def test_clear_finished():
    print("\n[3. finished downloads can be cleared away]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        holder = screen.query_one("#downloads", VerticalScroll)

        clear = screen.query_one("#clear-btn", Button)
        check("the clear button is hidden while nothing is finished",
              clear.display is False)

        for i, state in enumerate(["done", "failed", "running"], 1):
            row = DownloadRow(str(i), f"https://youtu.be/{i}")
            holder.mount(row)
            screen._rows[str(i)] = row
            await pilot.pause()
            if state == "done":
                row.finish(True, "Saved.")
            elif state == "failed":
                row.finish(False, "This video is private.")
        screen._refresh_buttons()
        await pilot.pause()

        check("the clear button appears once something has finished",
              clear.display is True)
        check("three rows to begin with",
              len(screen.query(DownloadRow)) == 3)

        screen.action_clear_finished()
        await pilot.pause()

        left = screen.query(DownloadRow)
        check("finished and failed rows are removed", len(left) == 1,
              str(len(left)))
        check("the unfinished one stays", left[0].url == "https://youtu.be/3",
              left[0].url)
        check("the bookkeeping matches the screen",
              set(screen._rows) == {"3"}, str(set(screen._rows)))
        check("the clear button hides again", clear.display is False)

        screen.action_clear_finished()
        await pilot.pause()
        check("clearing with nothing finished says so",
              any("nothing finished" in n.lower()
                  for n in notifications(app)), str(notifications(app)))


async def test_clear_by_keyboard_and_button():
    print("\n[3b. clearing works by key and by button]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        holder = screen.query_one("#downloads", VerticalScroll)
        row = DownloadRow("1", "https://youtu.be/a")
        holder.mount(row)
        screen._rows["1"] = row
        await pilot.pause()
        row.finish(True, "Saved.")
        screen._refresh_buttons()
        await pilot.pause()

        await pilot.press("ctrl+l")
        await pilot.pause()
        check("ctrl+l clears finished downloads",
              len(screen.query(DownloadRow)) == 0)

        row = DownloadRow("2", "https://youtu.be/b")
        holder.mount(row)
        screen._rows["2"] = row
        await pilot.pause()
        row.finish(True, "Saved.")
        screen._refresh_buttons()
        await pilot.pause()
        await pilot.click("#clear-btn")
        await pilot.pause()
        check("the button clears them too",
              len(screen.query(DownloadRow)) == 0)


async def test_long_list_scrolls():
    print("\n[4. a long list can be scrolled]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(84, 24)) as pilot:
        screen = app.screen
        holder = screen.query_one("#downloads", VerticalScroll)
        for i in range(12):
            row = DownloadRow(str(i), f"https://youtu.be/{i}")
            holder.mount(row)
            screen._rows[str(i)] = row
        await pilot.pause()
        await asyncio.sleep(0.3)

        check("the list holds every row", len(screen.query(DownloadRow)) == 12)
        check("there is more content than fits",
              holder.max_scroll_y > 0, str(holder.max_scroll_y))
        check("the list can take focus for scrolling", holder.can_focus)

        start = holder.scroll_offset.y
        await pilot.press("pagedown")
        await pilot.pause()
        await asyncio.sleep(0.4)
        scrolled = holder.scroll_offset.y
        check("page down moves down the list", scrolled > start,
              f"{start} -> {scrolled}")

        await pilot.press("pageup")
        await pilot.pause()
        await asyncio.sleep(0.4)
        check("page up moves back", holder.scroll_offset.y < scrolled,
              f"{scrolled} -> {holder.scroll_offset.y}")


def test_unmeasurable_speed_is_not_shown():
    print("\n[5. an unmeasured speed is omitted, not shown as zero]")
    blocked = compute_plan(0.0, 0.0, 40, 3, 8)
    lines = describe_plan(blocked)
    joined = " ".join(lines)
    check("no bogus zero speed is displayed",
          "0.0 Mbps" not in joined, joined)
    check("no speed line at all when there is no reading",
          not any("your speed" in ln.lower() for ln in lines), joined)
    check("the rest of the plan is still shown",
          any("Videos at once" in ln for ln in lines), joined)
    check("connections are still shown",
          any("Connections per video" in ln for ln in lines), joined)

    measured = describe_plan(compute_plan(20.0, 50.0, 30, 3, 8))
    check("a real reading is shown",
          any("50.0 Mbps" in ln for ln in measured), str(measured))


def test_rate_parsing_for_the_total():
    print("\n[5b. rates add up for the overall figure]")
    check("kibibytes", rate_to_bytes("712KiB/s") == 712 * 1024)
    check("mebibytes", rate_to_bytes("1.5MiB/s") == 1.5 * 1024 ** 2)
    check("plain bytes", rate_to_bytes("900B/s") == 900)
    check("nothing parseable is zero", rate_to_bytes("") == 0.0)
    check("nonsense is zero", rate_to_bytes("fast!") == 0.0)


async def test_overall_speed_comes_from_real_downloads():
    print("\n[5c. the overall figure is measured, not guessed]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        holder = screen.query_one("#downloads", VerticalScroll)
        for i in range(2):
            row = DownloadRow(str(i), f"https://youtu.be/{i}")
            holder.mount(row)
            screen._rows[str(i)] = row
            await pilot.pause()
            row.set_progress({"percent": 40, "total": "50MiB",
                              "speed": "500KiB/s", "eta": "20s",
                              "connections": 16})
        await pilot.pause()

        total = sum(r.speed_bytes for r in screen._rows.values())
        check("the two rates add up", total == 1000 * 1024, str(total))

        screen._download_active = True
        screen._tick_speed()
        await pilot.pause()
        status = text_of(screen.query_one("#status-line", Static))
        check("the combined rate is displayed",
              "altogether" in status, status)
        check("it names a real figure", "KB/s" in status or "MB/s" in status,
              status)

        screen._rows["0"].finish(True, "Saved.")
        await pilot.pause()
        check("a finished row stops counting toward the total",
              screen._rows["0"].speed_bytes == 0.0)
        screen._download_active = False


async def run_all():
    print("=" * 62)
    print("  Luma download-list checks")
    print("=" * 62)
    test_title_read_from_filename()
    await test_row_shows_title_once_known()
    await test_duplicate_warnings()
    await test_duplicate_paste_does_not_start_a_download()
    await test_clear_finished()
    await test_clear_by_keyboard_and_button()
    await test_long_list_scrolls()
    test_unmeasurable_speed_is_not_shown()
    test_rate_parsing_for_the_total()
    await test_overall_speed_comes_from_real_downloads()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL DOWNLOAD-LIST CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
