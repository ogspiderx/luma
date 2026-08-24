#!/usr/bin/env python3
"""
Checks for Luma's own palette and for being asked which quality to use.

    python tests/test_appearance_and_quality.py
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import (                                     # noqa: E402
    Button, Input, ProgressBar, Select, Static, Switch,
)

from luma.widgets.download_row import DownloadRow, QualityChip  # noqa: E402

from luma.app import LumaApp                                    # noqa: E402
from luma.config import DEFAULTS, load_config, normalize, save_config  # noqa: E402
from luma.engine import formats as formats_mod                   # noqa: E402
from luma.engine.formats import (                                # noqa: E402
    available_qualities, describe_height, size_note,
)
from luma.screens.settings import THEME_CHOICES                  # noqa: E402
from luma.theme import DEFAULT_THEME, THEMES                     # noqa: E402

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


# --------------------------------------------------------------------------- #
#  Luma's own colours                                                         #
# --------------------------------------------------------------------------- #

def test_themes_are_well_formed():
    print("\n[Luma's own palette]")
    check("there is a night and a day version", len(THEMES) == 2)
    names = [t.name for t in THEMES]
    check("night is the one it opens with", DEFAULT_THEME == "luma-night",
          DEFAULT_THEME)
    check("both are named", set(names) == {"luma-night", "luma-day"}, str(names))

    for theme in THEMES:
        every = [theme.background, theme.foreground, theme.primary,
                 theme.accent, theme.secondary, theme.success,
                 theme.warning, theme.error, theme.surface, theme.panel]
        check(f"{theme.name}: every colour is set", all(every), str(every))
        check(f"{theme.name}: colours are real hex values",
              all(c.startswith("#") and len(c) == 7 for c in every),
              str([c for c in every if not (c.startswith('#')
                                            and len(c) == 7)]))
        check(f"{theme.name}: the light is distinct from the background",
              theme.accent.lower() != theme.background.lower())

    night = [t for t in THEMES if t.name == "luma-night"][0]
    day = [t for t in THEMES if t.name == "luma-day"][0]
    check("night is a dark theme", night.dark is True)
    check("day is a light theme", day.dark is False)
    check("they do not share a background",
          night.background.lower() != day.background.lower())


async def test_theme_is_applied_and_offered():
    print("\n[the palette reaches the app]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test() as pilot:
            check("a fresh start uses Luma's own colours",
                  app.theme == "luma-night", str(app.theme))
            registered = app.available_themes
            check("night is registered with Textual",
                  "luma-night" in registered, str(list(registered)[:6]))
            check("day is registered too", "luma-day" in registered)

            await pilot.press("ctrl+s")
            await pilot.pause()
            chooser = app.screen.query_one("#set-theme", Select)
            chooser.value = "luma-day"
            await pilot.pause()
            await pilot.click("#settings-save")
            await pilot.pause()
            check("switching to day takes effect at once",
                  app.theme == "luma-day", str(app.theme))
        check("and it is remembered",
              load_config(cfg)["theme"] == "luma-day")

    offered = [value for _, value in THEME_CHOICES]
    check("both are offered in Settings",
          "luma-night" in offered and "luma-day" in offered, str(offered))
    check("Luma's own come first",
          offered[0].startswith("luma"), str(offered[:2]))
    labels = " ".join(label for label, _ in THEME_CHOICES).lower()
    check("the names read as names, not codes",
          "textual-dark" not in labels and "catppuccin" not in labels, labels)


# --------------------------------------------------------------------------- #
#  finding out what a link offers                                             #
# --------------------------------------------------------------------------- #

FAKE_INFO = {
    "title": "A Test Video",
    "formats": [
        {"height": 1080, "vcodec": "avc1", "acodec": "none",
         "filesize": 200 * 1024 ** 2},
        {"height": 720, "vcodec": "avc1", "acodec": "none",
         "filesize": 100 * 1024 ** 2},
        {"height": 480, "vcodec": "avc1", "acodec": "none",
         "filesize_approx": 50 * 1024 ** 2},
        {"height": 480, "vcodec": "vp9", "acodec": "none",
         "filesize": 40 * 1024 ** 2},
        {"height": None, "vcodec": "none", "acodec": "mp4a",
         "filesize": 5 * 1024 ** 2},
        {"height": 360, "vcodec": "avc1", "acodec": "mp4a",
         "filesize": 30 * 1024 ** 2},
    ],
}


def run_with_fake(stdout, returncode=0):
    class Result:
        pass
    Result.stdout = stdout
    Result.returncode = returncode
    Result.stderr = ""
    real = formats_mod.subprocess.run
    formats_mod.subprocess.run = lambda *a, **k: Result
    try:
        return available_qualities("yt-dlp", "https://youtu.be/a")
    finally:
        formats_mod.subprocess.run = real


def test_reading_what_is_available():
    print("\n[reading what a link offers]")
    title, choices = run_with_fake(json.dumps(FAKE_INFO))
    check("the title comes back", title == "A Test Video", title)
    heights = [c["height"] for c in choices]
    check("every video height is offered once",
          heights == [1080, 720, 480, 360], str(heights))
    check("the best is first", heights[0] == 1080)
    check("sound-only entries are not offered",
          all(h for h in heights), str(heights))

    labels = [c["label"] for c in choices]
    check("heights are named readably",
          labels == ["1080p", "720p", "480p", "360p"], str(labels))
    check("a very tall one gets a friendly name",
          describe_height(2160) == "4K", describe_height(2160))
    check("an unusual height still gets a name",
          describe_height(900) == "900p", describe_height(900))
    check("nonsense does not crash", describe_height(None) == "Unknown")

    top = choices[0]
    check("the size allows for the sound as well",
          "205" in top["note"] or "205.0 MB" in top["note"], top["note"])
    check("sizes read plainly", "about" in top["note"], top["note"])
    check("no size is handled", size_note(0) == "")


def test_failures_come_back_empty():
    print("\n[a link that cannot be read]")
    title, choices = run_with_fake("", returncode=1)
    check("a failed lookup offers nothing", choices == [], str(choices))
    title, choices = run_with_fake("{{{ not json")
    check("unreadable output offers nothing", choices == [], str(choices))
    title, choices = run_with_fake(json.dumps({"title": "x"}))
    check("no formats offers nothing", choices == [], str(choices))
    title, choices = run_with_fake(
        json.dumps({"title": "x", "formats": [
            {"vcodec": "none", "acodec": "mp4a", "filesize": 1},
        ]}))
    check("sound only offers nothing", choices == [], str(choices))


# --------------------------------------------------------------------------- #
#  being asked                                                                #
# --------------------------------------------------------------------------- #

def test_the_setting_exists():
    print("\n[the setting]")
    check("it is off unless asked for", DEFAULTS["ask_quality"] is False)
    check("it survives being set", normalize({"ask_quality": True})["ask_quality"]
          is True)
    check("nonsense becomes a plain yes or no",
          normalize({"ask_quality": "yes"})["ask_quality"] is True)


async def test_the_switch_is_wired():
    print("\n[the switch in Settings]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            switch = app.screen.query_one("#set-ask-quality", Switch)
            check("it starts off", switch.value is False)
            switch.value = True
            await pilot.pause()
            await pilot.click("#settings-save")
            await pilot.pause()
        check("turning it on is remembered",
              load_config(cfg)["ask_quality"] is True)


async def test_the_chooser_lives_in_the_row():
    print("\n[the chooser sits in the row it belongs to]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(90, 30)) as pilot:
        app.screen._queue_worker = lambda: None
        holder = app.screen.query_one("#downloads")
        row = DownloadRow("1", "https://youtu.be/aaa")
        app.screen._rows["1"] = row
        holder.mount(row)
        await pilot.pause()
        row.set_title("A Test Video")

        check("nothing is asked until there is something to ask",
              not row.choosing)

        row.offer_choices([
            {"height": 1080, "label": "1080p", "note": "about 205.0 MB",
             "filesize": 205 * 1024 ** 2},
            {"height": 720, "label": "720p", "note": "about 105.0 MB",
             "filesize": 105 * 1024 ** 2},
            {"height": 480, "label": "480p", "note": "about 55.0 MB",
             "filesize": 55 * 1024 ** 2},
        ])
        await pilot.pause()

        check("the row knows it is asking", row.choosing)
        check("nothing was pushed over the whole screen",
              app.screen is app.screen_stack[-1]
              and type(app.screen).__name__ == "MainScreen",
              type(app.screen).__name__)
        check("the row is still the one named",
              text_of(row.query_one(".row-title", Static)) == "A Test Video")

        chips = list(row.query(QualityChip))
        check("one chip per quality, plus a way out",
              len(chips) == 4, str([str(c.label) for c in chips]))
        check("each chip says its size",
              "205MB" in str(chips[0].label), str(chips[0].label))
        check("sizes are short enough for a chip",
              len(str(chips[0].label)) <= 14, str(chips[0].label))
        check("the last one skips the link",
              str(chips[-1].label) == "Skip" and chips[-1].height_value == "",
              str(chips[-1].label))
        check("the bar is out of the way while asking",
              not row.query_one(ProgressBar).display)

        await pilot.click(chips[1])
        await pilot.pause()
        with app.screen._queue_lock:
            queued = list(app.screen._queue)
        check("clicking a chip queues that link at that quality",
              queued == [("1", "https://youtu.be/aaa", "720")], str(queued))
        check("and the question is taken away", not row.choosing)


async def test_the_chooser_works_from_the_keyboard():
    print("\n[answering with the keyboard alone]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(90, 30)) as pilot:
        app.screen._queue_worker = lambda: None
        holder = app.screen.query_one("#downloads")
        row = DownloadRow("1", "https://youtu.be/aaa")
        app.screen._rows["1"] = row
        holder.mount(row)
        await pilot.pause()
        row.offer_choices([
            {"height": 1080, "label": "1080p", "note": ""},
            {"height": 720, "label": "720p", "note": ""},
            {"height": 480, "label": "480p", "note": ""},
        ])
        await pilot.pause()

        check("the first quality can be reached", row.focus_choices())
        await pilot.pause()
        chips = list(row.query(QualityChip))
        check("and holds the cursor", app.focused is chips[0],
              str(app.focused))

        await pilot.press("right")
        await pilot.pause()
        check("right moves along", app.focused is chips[1], str(app.focused))
        await pilot.press("left", "left")
        await pilot.pause()
        check("left goes back, and wraps at the end",
              app.focused is chips[-1], str(app.focused))

        await pilot.press("right")
        await pilot.pause()
        check("and wraps round the other way",
              app.focused is chips[0], str(app.focused))

        await pilot.press("enter")
        await pilot.pause()
        with app.screen._queue_lock:
            queued = list(app.screen._queue)
        check("enter answers with what is under the cursor",
              queued and queued[0][2] == "1080", str(queued))
        check("and the cursor goes back to the link box",
              isinstance(app.focused, Input), str(app.focused))


async def test_skipping_from_the_row():
    print("\n[skipping from the row]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(90, 30)) as pilot:
        app.screen._queue_worker = lambda: None
        holder = app.screen.query_one("#downloads")
        row = DownloadRow("1", "https://youtu.be/aaa")
        app.screen._rows["1"] = row
        holder.mount(row)
        await pilot.pause()
        row.offer_choices([{"height": 480, "label": "480p", "note": ""}])
        await pilot.pause()

        chips = list(row.query(QualityChip))
        await pilot.click(chips[-1])
        await pilot.pause()
        check("the row is taken out of the list",
              row not in holder.children, str(list(holder.children)))
        with app.screen._queue_lock:
            queued = list(app.screen._queue)
        check("and nothing is queued for it", queued == [], str(queued))


async def test_the_question_goes_away_when_answered():
    print("\n[the question clears]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(90, 30)) as pilot:
        app.screen._queue_worker = lambda: None
        holder = app.screen.query_one("#downloads")
        row = DownloadRow("1", "https://youtu.be/aaa")
        app.screen._rows["1"] = row
        holder.mount(row)
        await pilot.pause()
        row.offer_choices([{"height": 480, "label": "480p", "note": ""}])
        await pilot.pause()

        row.clear_choices()
        await pilot.pause()
        check("the chips are gone", not list(row.query(QualityChip)))
        check("and the row no longer counts as asking", not row.choosing)
        check("the bar is back", row.query_one(ProgressBar).display)

        # Progress arriving on its own takes the question away too, so a
        # download that starts anyway never leaves a stale question behind.
        row.offer_choices([{"height": 480, "label": "480p", "note": ""}])
        await pilot.pause()
        row.set_progress({"percent": 10.0})
        await pilot.pause()
        check("progress clears any question still showing", not row.choosing)


async def test_a_chosen_quality_is_carried_through():
    print("\n[a chosen quality reaches the download]")
    with tempfile.TemporaryDirectory() as td:
        app = LumaApp(config_path=os.path.join(td, "config.json"),
                      auto_prepare=False)
        async with app.run_test() as pilot:
            screen = app.screen
            screen._queue_worker = lambda: None

            screen._enqueue(["https://youtu.be/aaa"], quality="720")
            screen._enqueue(["https://youtu.be/bbb"])          # uses setting
            await pilot.pause()

            with screen._queue_lock:
                entries = list(screen._queue)
            check("the chosen quality is kept with the link",
                  entries[0][2] == "720", str(entries[0]))
            check("one without a choice keeps none",
                  entries[1][2] is None, str(entries[1]))

            first = screen._take_batch(8)
            check("a batch only groups one quality together",
                  len(first) == 1 and first[0][2] == "720", str(first))
            second = screen._take_batch(8)
            check("the next batch takes the other",
                  len(second) == 1 and second[0][2] is None, str(second))


async def run_all():
    print("=" * 62)
    print("  Luma appearance and quality-choice checks")
    print("=" * 62)
    test_themes_are_well_formed()
    await test_theme_is_applied_and_offered()
    test_reading_what_is_available()
    test_failures_come_back_empty()
    test_the_setting_exists()
    await test_the_switch_is_wired()
    await test_the_chooser_lives_in_the_row()
    await test_the_chooser_works_from_the_keyboard()
    await test_skipping_from_the_row()
    await test_the_question_goes_away_when_answered()
    await test_a_chosen_quality_is_carried_through()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL APPEARANCE AND QUALITY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
