#!/usr/bin/env python3
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.widgets import (
    Footer, Input, Static, Switch,
)
from textual.widgets._footer import FooterKey

from luma.app import LumaApp
from luma.branding import WORDMARK
from luma.config import load_config, save_config
from luma.screens.settings import THEME_CHOICES
from luma.theme import DEFAULT_THEME, THEME_NAMES
from luma.widgets.brandbar import BrandBar
from luma.widgets.download_row import DownloadRow, QualityChip
from luma.widgets.sizing import (
    NARROW_COLUMNS, ROOMY_COLUMNS, SHORT_ROWS, classes_for,
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


def footer_keys(screen):
    try:
        footer = screen.query_one(Footer)
    except Exception:
        return []
    return [str(k.description).lower() for k in footer.query(FooterKey)]


async def test_the_command_palette_is_gone():
    print("\n[the command palette]")
    app = LumaApp(auto_prepare=False)
    check("it is turned off on the app itself",
          LumaApp.ENABLE_COMMAND_PALETTE is False)
    async with app.run_test(size=(100, 30)) as pilot:
        keys = footer_keys(app.screen)
        check("the footer does not offer it",
              not any("palette" in k for k in keys), str(keys))

        before = len(app.screen_stack)
        await pilot.press("ctrl+p")
        await pilot.pause()
        check("the key does nothing",
              len(app.screen_stack) == before, str(app.screen_stack))
        check("and no search box appeared over the app",
              type(app.screen).__name__ == "MainScreen",
              type(app.screen).__name__)


async def test_no_borrowed_header():
    print("\n[the bar across the top]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        check("Luma's own bar is used", bool(screen.query(BrandBar)))
        from textual.widgets import Header
        check("Textual's header, with its icon and clock, is not",
              not screen.query(Header))

        mark = text_of(screen.query_one(".brand-mark", Static))
        check("the name is set across it", mark == WORDMARK, mark)
        check("no icon rides alongside it",
              not any(ch in mark for ch in "⭘🔍🎬▶"), mark)

        note = text_of(screen.query_one(".brand-note", Static))
        check("the other side says where videos go",
              "downloads" in note.lower(), note)

        for key in ("ctrl+s", "ctrl+h"):
            await pilot.press(key)
            await pilot.pause()
            check(f"{key}: that screen has the bar too",
                  bool(app.screen.query(BrandBar)))
            await pilot.press("escape")
            await pilot.pause()


async def test_only_lumas_own_looks_are_offered():
    print("\n[appearance is Luma's, not Textual's]")
    offered = [value for _, value in THEME_CHOICES]
    check("two, and only two", len(offered) == 2, str(offered))
    check("both are Luma's own", set(offered) == set(THEME_NAMES),
          str(offered))
    check("no borrowed palettes are on the list",
          not any(name in offered for name in
                  ("tokyo-night", "nord", "gruvbox", "textual-dark",
                   "textual-light", "catppuccin-mocha")), str(offered))

    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        save_config({"theme": "tokyo-night", "output_dir": td}, cfg)
        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test() as pilot:
            await pilot.pause()
            check("a config naming an old palette falls back to Luma's",
                  app.theme == DEFAULT_THEME, str(app.theme))


async def test_everything_on_the_main_screen_can_be_reached():
    print("\n[the main screen, keyboard only]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 34)) as pilot:
        screen = app.screen
        screen._queue_worker = lambda: None
        holder = screen.query_one("#downloads")
        row = DownloadRow("1", "https://youtu.be/aaa")
        screen._rows["1"] = row
        holder.mount(row)
        await pilot.pause()
        row.set_title("A Test Video")
        row.offer_choices([
            {"height": 720, "label": "720p", "filesize": 105 * 1024 ** 2},
            {"height": 480, "label": "480p", "filesize": 55 * 1024 ** 2},
        ])
        screen._after_list_change()
        await pilot.pause()

        reachable = {w.id or "" for w in screen.focus_chain}
        for needed in ("url-input", "download-btn", "sort-select"):
            check(f"tab reaches {needed}", needed in reachable,
                  str(sorted(reachable)))

        kinds = {type(w).__name__ for w in screen.focus_chain}
        check("the cross on a row is reachable",
              any("row-remove" in (w.classes or set())
                  for w in screen.focus_chain))
        check("so are the qualities on offer",
              "QualityChip" in kinds, str(kinds))

        screen._download_active = True
        screen._refresh_buttons()
        await pilot.pause()
        check("tab reaches stop while something is running",
              "stop-btn" in {w.id or "" for w in screen.focus_chain},
              str(sorted({w.id or "" for w in screen.focus_chain})))

        screen._download_active = False
        row.finish(True, "")
        screen._after_list_change()
        await pilot.pause()
        check("tab reaches clear once something has finished",
              "clear-btn" in {w.id or "" for w in screen.focus_chain},
              str(sorted({w.id or "" for w in screen.focus_chain})))


async def test_tab_goes_right_round_the_main_screen():
    print("\n[tab wraps round]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 34)) as pilot:
        screen = app.screen
        screen._queue_worker = lambda: None
        holder = screen.query_one("#downloads")
        row = DownloadRow("1", "https://youtu.be/aaa")
        screen._rows["1"] = row
        holder.mount(row)
        await pilot.pause()
        row.offer_choices([
            {"height": 720, "label": "720p", "filesize": 105 * 1024 ** 2},
        ])
        screen._after_list_change()
        await pilot.pause()

        chain = list(screen.focus_chain)
        check("there is a chain to walk", len(chain) >= 4, str(len(chain)))

        screen.query_one("#url-input", Input).focus()
        await pilot.pause()
        seen = []
        for _ in range(len(chain)):
            seen.append(app.focused)
            await pilot.press("tab")
            await pilot.pause()
        check("every stop is a different widget",
              len({id(w) for w in seen}) == len(chain),
              f"{len({id(w) for w in seen})} of {len(chain)}")
        check("and tab comes back to where it started",
              app.focused is seen[0], str(app.focused))

        await pilot.press("shift+tab")
        await pilot.pause()
        check("shift+tab goes the other way",
              app.focused is seen[-1], str(app.focused))


async def test_the_commands_work_from_the_link_box():
    print("\n[commands are not swallowed by the link box]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = app.screen
        screen._queue_worker = lambda: None
        box = screen.query_one("#url-input", Input)
        box.focus()
        box.value = "https://youtu.be/keepme"
        screen._download_active = True
        await pilot.pause()

        await pilot.press("ctrl+x")
        await pilot.pause()
        check("ctrl+x stops rather than cutting the text",
              box.value == "https://youtu.be/keepme", box.value)
        check("and it really did stop",
              "stopping" in text_of(
                  screen.query_one("#status-line", Static)).lower(),
              text_of(screen.query_one("#status-line", Static)))

        screen._download_active = False
        holder = screen.query_one("#downloads")
        for index in (1, 2):
            row = DownloadRow(str(index), f"https://youtu.be/{index}")
            screen._rows[str(index)] = row
            holder.mount(row)
            await pilot.pause()
            row.offer_choices([{"height": 480, "label": "480p",
                                "filesize": 55 * 1024 ** 2}])
            screen._awaiting.add(str(index))
        box.focus()
        await pilot.pause()
        await pilot.press("ctrl+a")
        await pilot.pause()
        check("ctrl+a answers everything rather than selecting text",
              screen._awaiting == set(), str(screen._awaiting))
        check("and all of them are queued",
              len(screen._queue) == 2, str(screen._queue))


async def test_settings_can_be_done_without_a_mouse():
    print("\n[settings, keyboard only]")
    with tempfile.TemporaryDirectory() as td:
        cfg = os.path.join(td, "config.json")
        app = LumaApp(config_path=cfg, auto_prepare=False)
        async with app.run_test(size=(100, 34)) as pilot:
            await pilot.press("ctrl+s")
            await pilot.pause()
            screen = app.screen

            reachable = {w.id or "" for w in screen.focus_chain}
            for needed in ("set-folder", "set-folders", "set-quality",
                           "set-ask-quality", "set-parallel", "set-conns",
                           "set-theme", "set-archive", "settings-save",
                           "settings-cancel", "settings-reset"):
                check(f"tab reaches {needed}", needed in reachable,
                      str(sorted(reachable)))

            check("the first field already has the cursor",
                  isinstance(app.focused, Input)
                  and app.focused.id == "set-folder", str(app.focused))

            screen.query_one("#set-ask-quality", Switch).focus()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
        check("a keyboard-only change is saved",
              load_config(cfg)["ask_quality"] is True)


async def test_history_can_be_read_without_a_mouse():
    print("\n[history, keyboard only]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 34)) as pilot:
        await pilot.press("ctrl+h")
        await pilot.pause()
        screen = app.screen
        kinds = {type(w).__name__ for w in screen.focus_chain}
        check("the tables can be reached", "DataTable" in kinds, str(kinds))
        check("so can the way back",
              "history-back" in {w.id or "" for w in screen.focus_chain})
        await pilot.press("escape")
        await pilot.pause()
        check("escape leaves", type(app.screen).__name__ == "MainScreen")


async def test_the_footer_only_offers_what_is_possible():
    print("\n[the footer follows what can be done]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(100, 34)) as pilot:
        screen = app.screen
        screen._queue_worker = lambda: None
        keys = footer_keys(screen)
        check("a quiet screen offers settings, history and quit",
              all(word in " ".join(keys)
                  for word in ("settings", "history", "quit")), str(keys))
        check("stop is not offered with nothing running",
              not any("stop" in k for k in keys), str(keys))
        check("clear is not offered with nothing finished",
              not any("clear" in k for k in keys), str(keys))
        check("'same for all' is not offered with nothing to answer",
              not any("same" in k for k in keys), str(keys))

        screen._download_active = True
        screen.refresh_bindings()
        await pilot.pause()
        await asyncio.sleep(0.15)
        await pilot.pause()
        check("stop appears once something is running",
              any("stop" in k for k in footer_keys(screen)),
              str(footer_keys(screen)))

        screen._download_active = False
        holder = screen.query_one("#downloads")
        for index in (1, 2):
            row = DownloadRow(str(index), f"https://youtu.be/{index}")
            screen._rows[str(index)] = row
            holder.mount(row)
            await pilot.pause()
            row.offer_choices([{"height": 480, "label": "480p",
                                "filesize": 55 * 1024 ** 2}])
            screen._awaiting.add(str(index))
        screen.refresh_bindings()
        await pilot.pause()
        await asyncio.sleep(0.15)
        await pilot.pause()
        check("'same for all' appears once two are asking",
              any("same" in k for k in footer_keys(screen)),
              str(footer_keys(screen)))


def test_the_size_rules_are_sane():
    print("\n[which size is which]")
    check("a small window is narrow",
          classes_for(NARROW_COLUMNS - 1, 40) == {"-narrow"})
    check("a wide one is roomy",
          classes_for(ROOMY_COLUMNS, 40) == {"-roomy"})
    check("an ordinary one is neither",
          classes_for(NARROW_COLUMNS + 5, 40) == set())
    check("a short one says so",
          "-short" in classes_for(100, SHORT_ROWS - 1))
    check("narrow and short can happen at once",
          classes_for(60, 20) == {"-narrow", "-short"})
    check("nothing is both narrow and roomy",
          all(not {"-narrow", "-roomy"} <= classes_for(w, 40)
              for w in range(20, 300, 7)))


async def test_the_screen_carries_its_size():
    print("\n[the window's shape reaches the stylesheet]")
    for width, height, expected in (
        (70, 20, {"-narrow", "-short"}),
        (100, 34, set()),
        (140, 40, {"-roomy"}),
    ):
        app = LumaApp(auto_prepare=False)
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            here = {c for c in app.screen.classes if c.startswith("-")}
            check(f"{width}x{height} is {expected or 'plain'}",
                  here == expected, str(here))

            await pilot.resize_terminal(150, 45)
            await pilot.pause()
            check(f"{width}x{height} -> 150x45 becomes roomy",
                  "-roomy" in app.screen.classes, str(app.screen.classes))


async def test_spacing_actually_changes_with_the_size():
    print("\n[the gutters really move]")
    widths = {}
    for width in (70, 100, 140):
        app = LumaApp(auto_prepare=False)
        async with app.run_test(size=(width, 34)) as pilot:
            await pilot.pause()
            body = app.screen.query_one("#main-body")
            widths[width] = body.styles.padding.left
    check("narrow gets the smallest gutter", widths[70] == 1, str(widths))
    check("ordinary gets more", widths[100] == 2, str(widths))
    check("wide gets the most", widths[140] == 4, str(widths))
    check("they go up, never down",
          widths[70] < widths[100] < widths[140], str(widths))


async def test_the_narrow_window_drops_the_optional_parts():
    print("\n[what a narrow window leaves out]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test(size=(70, 24)) as pilot:
        screen = app.screen
        screen._set_plan("2 at a time   16 connections each")
        await pilot.pause()
        check("the plan note steps aside",
              not screen.query_one("#plan-note").display)
        check("so does the folder in the bar",
              not screen.query_one(".brand-note").display)
        check("but the link box is untouched",
              screen.query_one("#url-input", Input).display)
        check("and so is the status line",
              screen.query_one("#status-line", Static).display)

        await pilot.resize_terminal(120, 34)
        await pilot.pause()
        check("both come back when there is room",
              screen.query_one("#plan-note").display
              and screen.query_one(".brand-note").display)


async def test_a_row_fits_at_every_size():
    print("\n[a row in the list, at every size]")
    for width, height in ((70, 22), (100, 30), (150, 44)):
        app = LumaApp(auto_prepare=False)
        async with app.run_test(size=(width, height)) as pilot:
            screen = app.screen
            holder = screen.query_one("#downloads")
            row = DownloadRow("1", "https://youtu.be/aaa")
            screen._rows["1"] = row
            holder.mount(row)
            await pilot.pause()
            row.set_title("A Video With Quite A Long Name Indeed")
            row.offer_choices([
                {"height": 1080, "label": "1080p",
                 "filesize": 205 * 1024 ** 2},
                {"height": 720, "label": "720p",
                 "filesize": 105 * 1024 ** 2},
                {"height": 480, "label": "480p",
                 "filesize": 55 * 1024 ** 2},
            ])
            await pilot.pause()
            await asyncio.sleep(0.2)

            chips = list(row.query(QualityChip))
            check(f"{width}x{height}: every quality is on screen",
                  all(chip.region.width > 0 for chip in chips),
                  str([(str(c.label), c.region.width) for c in chips]))
            right = max(c.region.right for c in chips)
            check(f"{width}x{height}: including the way out, in full",
                  right <= row.region.right, f"{right} > {row.region.right}")
            check(f"{width}x{height}: the row stays a few lines tall",
                  0 < row.region.height <= 6, str(row.region.height))


async def run_all():
    print("=" * 62)
    print("  Luma shell, keyboard and sizing checks")
    print("=" * 62)
    await test_the_command_palette_is_gone()
    await test_no_borrowed_header()
    await test_only_lumas_own_looks_are_offered()
    await test_everything_on_the_main_screen_can_be_reached()
    await test_tab_goes_right_round_the_main_screen()
    await test_the_commands_work_from_the_link_box()
    await test_settings_can_be_done_without_a_mouse()
    await test_history_can_be_read_without_a_mouse()
    await test_the_footer_only_offers_what_is_possible()
    test_the_size_rules_are_sane()
    await test_the_screen_carries_its_size()
    await test_spacing_actually_changes_with_the_size()
    await test_the_narrow_window_drops_the_optional_parts()
    await test_a_row_fits_at_every_size()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL SHELL, KEYBOARD AND SIZING CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
