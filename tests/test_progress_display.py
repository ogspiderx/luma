#!/usr/bin/env python3
"""
Checks for what a download looks like while it runs.

A video at 480p arrives as two streams, picture then sound, each reporting its
own size and percentage. These checks hold the combined figures to the one
rule that matters: they only ever move forwards.

Also covers the Stop and Clear controls, and that the tools and speed reading
are prepared once at startup rather than before every download.

    python tests/test_progress_display.py
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.containers import VerticalScroll               # noqa: E402
from textual.widgets import Button, Input, Static           # noqa: E402

from luma.app import LumaApp                                # noqa: E402
from luma.engine.download import (                          # noqa: E402
    _overall, _track_filepath, _track_streams, parse_progress, size_to_bytes,
)
from luma.widgets.download_row import DownloadRow           # noqa: E402

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


#: A realistic transcript: picture stream, then sound stream.
TWO_STREAM = [
    "[info] abc: Downloading 1 format(s): 135+140",
    "[download] Destination: /d/Clip [dQw4w9WgXcQ].f135.mp4",
    "[#a1 5MiB/50MiB(10%) CN:16 DL:900KiB ETA:50s]",
    "[#a1 25MiB/50MiB(50%) CN:16 DL:900KiB ETA:28s]",
    "[#a1 45MiB/50MiB(90%) CN:16 DL:900KiB ETA:6s]",
    "[#a1 50MiB/50MiB(100%) CN:16 DL:900KiB ETA:0s]",
    "[download] Destination: /d/Clip [dQw4w9WgXcQ].f140.m4a",
    "[#b2 1MiB/6MiB(16%) CN:16 DL:800KiB ETA:6s]",
    "[#b2 3MiB/6MiB(50%) CN:16 DL:800KiB ETA:3s]",
    "[#b2 6MiB/6MiB(100%) CN:16 DL:800KiB ETA:0s]",
]


def replay(lines):
    """Feed a transcript through the engine's parsing, collecting readings."""
    state, readings = {}, []
    for line in lines:
        _track_streams(line, state)
        _track_filepath(line, state)
        parsed = parse_progress(line)
        if parsed is not None:
            readings.append(_overall(state, parsed))
    return readings


def test_sizes_parse():
    print("\n[sizes are read correctly]")
    check("mebibytes", size_to_bytes("54MiB") == 54 * 1024 ** 2)
    check("kibibytes", size_to_bytes("900KiB") == 900 * 1024)
    check("decimals", size_to_bytes("1.5MiB") == int(1.5 * 1024 ** 2))
    check("nothing readable is zero", size_to_bytes("") == 0)
    check("nonsense is zero", size_to_bytes("lots") == 0)


def test_progress_only_moves_forwards():
    print("\n[progress never goes backwards]")
    readings = replay(TWO_STREAM)
    percents = [r["percent"] for r in readings]
    check("every reading was captured", len(percents) == 7, str(len(percents)))
    check("the percentage only ever rises",
          all(b >= a for a, b in zip(percents, percents[1:])), str(percents))
    check("it starts low", percents[0] < 10, str(percents[0]))
    check("it ends at the top", percents[-1] == 100.0, str(percents[-1]))
    check("the first stream tops out halfway, not at the end",
          percents[3] == 50.0, str(percents[3]))
    check("the second stream carries on from there",
          percents[4] > 50.0, str(percents[4]))


def test_sizes_only_grow():
    print("\n[sizes never shrink]")
    readings = replay(TWO_STREAM)
    done = [r["done_bytes"] for r in readings]
    total = [r["total_bytes"] for r in readings]
    check("downloaded amount only rises",
          all(b >= a for a, b in zip(done, done[1:])),
          str([f"{d/1048576:.0f}" for d in done]))
    check("the total never shrinks",
          all(b >= a for a, b in zip(total, total[1:])),
          str([f"{t/1048576:.0f}" for t in total]))
    check("the final total covers both streams",
          total[-1] == 56 * 1024 ** 2, str(total[-1] / 1048576))
    check("everything was downloaded", done[-1] == total[-1])


def test_single_stream_still_works():
    print("\n[a single-stream video still behaves]")
    readings = replay([
        "[info] abc: Downloading 1 format(s): 18",
        "[download] Destination: /d/Clip [dQw4w9WgXcQ].mp4",
        "[#a1 5MiB/20MiB(25%) CN:16 DL:900KiB ETA:16s]",
        "[#a1 20MiB/20MiB(100%) CN:16 DL:900KiB ETA:0s]",
    ])
    check("a quarter of one stream is a quarter overall",
          readings[0]["percent"] == 25.0, str(readings[0]["percent"]))
    check("it still reaches the top",
          readings[-1]["percent"] == 100.0, str(readings[-1]["percent"]))


async def test_row_detail_while_downloading():
    print("\n[what the row says while downloading]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        holder = app.screen.query_one("#downloads", VerticalScroll)
        row = DownloadRow("1", "https://youtu.be/dQw4w9WgXcQ")
        holder.mount(row)
        await pilot.pause()

        row.set_title("Some Video")
        row.set_progress({
            "percent": 45.0,
            "done_bytes": 25 * 1024 ** 2,
            "total_bytes": 56 * 1024 ** 2,
            "speed": "900KiB/s", "eta": "28s", "connections": 16,
        })
        await pilot.pause()

        detail = text_of(row.query_one(".row-detail", Static))
        check("the speed is shown", "900KiB/s" in detail, detail)
        check("how much of how much is shown",
              "25.0 MB" in detail and "56.0 MB" in detail, detail)
        check("time remaining is shown", "28s left" in detail, detail)
        check("the title stays above, not in the detail",
              "Some Video" not in detail, detail)

        title = text_of(row.query_one(".row-title", Static))
        check("the title is on its own line above", title == "Some Video", title)


async def test_row_detail_when_finished():
    print("\n[what the row says once finished]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        holder = app.screen.query_one("#downloads", VerticalScroll)
        url = "https://youtu.be/dQw4w9WgXcQ"
        row = DownloadRow("1", url)
        holder.mount(row)
        await pilot.pause()
        row.set_title("Some Video")
        row.finish(True, "Saved: Some Video.mp4")
        await pilot.pause()

        detail = text_of(row.query_one(".row-detail", Static))
        check("a finished row shows its link", detail == url, detail)
        check("the title is still above",
              text_of(row.query_one(".row-title", Static)) == "Some Video")

        failed = DownloadRow("2", "https://youtu.be/CdbHAzNB1n0")
        holder.mount(failed)
        await pilot.pause()
        failed.finish(False, "This video is private.")
        await pilot.pause()
        detail = text_of(failed.query_one(".row-detail", Static))
        check("a failed row explains itself instead",
              "private" in detail.lower(), detail)


async def test_stop_and_clear_visibility():
    print("\n[Stop shows while running, Clear when idle]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        stop = screen.query_one("#stop-btn", Button)
        clear = screen.query_one("#clear-btn", Button)

        check("Stop is hidden before anything starts", stop.display is False)
        check("Clear is hidden before anything starts", clear.display is False)

        # Pretend a download is running.
        screen._download_active = True
        screen._refresh_buttons()
        await pilot.pause()
        check("Stop appears while running", stop.display is True)
        check("Clear stays hidden while running", clear.display is False)

        # A row finishes, but the batch is still going.
        holder = screen.query_one("#downloads", VerticalScroll)
        row = DownloadRow("1", "https://youtu.be/a")
        holder.mount(row)
        screen._rows["1"] = row
        await pilot.pause()
        row.finish(True, "Saved.")
        screen._refresh_buttons()
        await pilot.pause()
        check("Clear still waits until the batch is over",
              clear.display is False)
        check("Stop is still offered", stop.display is True)

        # The batch ends.
        screen._download_active = False
        screen._refresh_buttons()
        await pilot.pause()
        check("Stop disappears when nothing is running", stop.display is False)
        check("Clear appears now there is something to clear",
              clear.display is True)


async def test_stop_button_cancels():
    print("\n[the Stop button actually stops]")
    app = LumaApp(auto_prepare=False)
    async with app.run_test() as pilot:
        screen = app.screen
        from luma.engine import download as dl
        dl.reset_cancel()
        screen._download_active = True
        screen._refresh_buttons()
        await pilot.pause()

        await pilot.click("#stop-btn")
        await pilot.pause()
        check("a stop was requested", dl.is_cancelled())
        status = text_of(screen.query_one("#status-line", Static))
        check("the user is told it is stopping",
              "stopping" in status.lower(), status)
        dl.reset_cancel()
        screen._download_active = False


async def test_preparation_happens_once():
    print("\n[setting up happens at startup, not every download]")
    from luma.screens import main as main_mod

    calls = {"tools": 0, "speed": 0}
    real_tools = main_mod.ensure_tools
    real_speed = main_mod.measure_bandwidth

    def counting_tools(cb=None):
        calls["tools"] += 1
        return {"yt-dlp": "/bin/true", "aria2c": "aria2c",
                "ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}

    def counting_speed(cb=None):
        calls["speed"] += 1
        return (50.0, 100.0, 25.0)

    main_mod.ensure_tools = counting_tools
    main_mod.measure_bandwidth = counting_speed
    main_mod.expand_playlists = lambda y, u, cb=None: list(u)
    main_mod.record_results = lambda results, quality=None: None
    try:
        with tempfile.TemporaryDirectory() as td:
            app = LumaApp(config_path=os.path.join(td, "config.json"))
            async with app.run_test() as pilot:
                # Wait for the startup preparation to settle.
                for _ in range(100):
                    if app.tools and app.bandwidth:
                        break
                    await asyncio.sleep(0.05)
                check("the tools were set up at startup", calls["tools"] == 1,
                      str(calls["tools"]))
                check("the connection was read at startup",
                      calls["speed"] == 1, str(calls["speed"]))
                check("both were remembered on the app",
                      app.tools is not None and app.bandwidth is not None)

                screen = app.screen
                screen._settings = lambda: {
                    "output_dir": td, "quality": "480", "max_parallel": 8,
                    "conns_per_file": None, "archive": False,
                    "run_speedtest": True,
                }
                # Two downloads in a row must not repeat either step.
                for link in ("https://youtu.be/aaaaaaaaaaa",
                             "https://youtu.be/bbbbbbbbbbb"):
                    screen.query_one("#url-input", Input).value = link
                    screen._start()
                    for _ in range(200):
                        if not screen._download_active:
                            break
                        await asyncio.sleep(0.05)
                    await pilot.pause()

                check("the tools were not set up again",
                      calls["tools"] == 1, str(calls["tools"]))
                check("the connection was not measured again",
                      calls["speed"] == 1, str(calls["speed"]))
    finally:
        main_mod.ensure_tools = real_tools
        main_mod.measure_bandwidth = real_speed


def test_update_check_runs_once():
    print("\n[the update check runs once per session]")
    from luma.engine import tools as tools_mod

    tools_mod.reset_update_state()
    calls = []
    real_run = tools_mod.subprocess.run

    class Fake:
        returncode = 0

    def counting(cmd, *a, **kw):
        calls.append(cmd)
        return Fake()

    tools_mod.subprocess.run = counting
    try:
        from luma.engine.callbacks import EngineCallbacks
        cb = EngineCallbacks()
        for _ in range(3):
            tools_mod._maybe_update_ytdlp("/fake/yt-dlp", True, cb)
        check("checked exactly once despite three attempts",
              len(calls) == 1, str(len(calls)))
    finally:
        tools_mod.subprocess.run = real_run
        tools_mod.reset_update_state()


def test_blocked_speedtest_is_not_retried():
    print("\n[a blocked speed test is not retried all session]")
    from luma.engine import speedtest as st

    st.reset_speedtest_state()
    calls = []
    real_timed = st._timed_download
    real_latency = st.measure_latency

    st._timed_download = lambda *a, **kw: (calls.append(1), (0, 1.0))[1]
    st.measure_latency = lambda *a, **kw: 40.0
    try:
        first = st.measure_bandwidth()
        after_first = len(calls)
        second = st.measure_bandwidth()
        check("an unreachable host gives up after one attempt",
              after_first == 1, str(after_first))
        check("and is not tried again", len(calls) == after_first,
              str(len(calls)))
        check("no speed is claimed", first[1] == 0.0 and second[1] == 0.0)
        check("it is remembered as unavailable", st.speedtest_unavailable())
    finally:
        st._timed_download = real_timed
        st.measure_latency = real_latency
        st.reset_speedtest_state()


def test_never_runs_past_the_end():
    """The bar reached several hundred percent and then seized up.

    It happened when the streams were not announced up front: each new stream
    pushed the count higher than the scale it was being divided by.
    """
    print("\n[the bar cannot run past the end]")

    # No "format(s)" line at all -- the shape that misbehaved.
    unannounced = [
        "[download] Destination: /d/C [dQw4w9WgXcQ].f135.mp4",
        "[#a1 25MiB/50MiB(50%) CN:16 DL:900KiB ETA:28s]",
        "[#a1 50MiB/50MiB(100%) CN:16 DL:900KiB ETA:0s]",
        "[download] Destination: /d/C [dQw4w9WgXcQ].f140.m4a",
        "[#b2 3MiB/6MiB(50%) CN:16 DL:800KiB ETA:3s]",
        "[#b2 6MiB/6MiB(100%) CN:16 DL:800KiB ETA:0s]",
    ]
    percents = [r["percent"] for r in replay(unannounced)]
    check("nothing above 100", all(p <= 100.0 for p in percents), str(percents))
    check("nothing below 0", all(p >= 0.0 for p in percents), str(percents))
    check("a second stream is expected from the filename alone",
          percents[1] <= 50.0, str(percents))
    check("it still only moves forwards",
          all(b >= a for a, b in zip(percents, percents[1:])), str(percents))
    check("and it does reach the end", percents[-1] == 100.0, str(percents[-1]))

    # Far more streams than announced, which is what inflated the scale.
    lines = ["[info] a: Downloading 1 format(s): 135"]
    for n in range(5):
        lines.append(f"[download] Destination: /d/C [dQw4w9WgXcQ].f{130 + n}.mp4")
        lines.append(f"[#s{n} 10MiB/10MiB(100%) CN:8 DL:900KiB ETA:0s]")
    many = [r["percent"] for r in replay(lines)]
    check("five unannounced streams stay within range",
          all(0.0 <= p <= 100.0 for p in many), str(many))
    check("merging does not count as another stream",
          replay(lines + ['[Merger] Merging formats into "/d/C.mp4"'])[-1]
          ["percent"] <= 100.0)


def test_concurrent_pieces_are_added_up():
    """aria2c reports each piece separately; they must not fight each other."""
    print("\n[concurrent pieces are summed, not swapped]")
    readings = replay([
        "[info] a: Downloading 1 format(s): 135",
        "[download] Destination: /d/C [dQw4w9WgXcQ].mp4",
        "[#p1 5MiB/25MiB(20%) CN:8 DL:500KiB ETA:40s]",
        "[#p2 2MiB/25MiB(8%) CN:8 DL:400KiB ETA:57s]",
        "[#p1 15MiB/25MiB(60%) CN:8 DL:500KiB ETA:20s]",
        "[#p2 20MiB/25MiB(80%) CN:8 DL:400KiB ETA:12s]",
    ])
    totals = [r["total_bytes"] for r in readings]
    check("the total covers both pieces once both are seen",
          totals[-1] == 50 * 1024 ** 2, str(totals[-1] / 1048576))
    check("the total does not shrink back",
          all(b >= a for a, b in zip(totals, totals[1:])),
          str([t // 1048576 for t in totals]))
    check("the finished amount adds both pieces",
          readings[-1]["done_bytes"] == 35 * 1024 ** 2,
          str(readings[-1]["done_bytes"] / 1048576))
    check("percentages stay sane",
          all(0.0 <= r["percent"] <= 100.0 for r in readings),
          str([round(r["percent"], 1) for r in readings]))


def test_time_remaining_is_trustworthy():
    """A countdown that reads '-1s' is worse than no countdown."""
    print("\n[time remaining is only shown when believable]")
    from luma.engine.download import _clean_eta

    for bad, why in [("-1s", "negative"), ("-00:05", "negative clock"),
                     ("99:00:00", "days away"), ("unknown", "unknown"),
                     ("", "empty"), ("??", "nonsense")]:
        check(f"drops {bad!r} ({why})", _clean_eta(bad) == "", _clean_eta(bad))
    for good in ("19s", "1m30s", "00:19", "1:02:03"):
        check(f"keeps {good!r}", _clean_eta(good) == good, _clean_eta(good))

    parsed = parse_progress("[#a1 5MiB/50MiB(10%) CN:16 DL:900KiB ETA:-3s]")
    check("a negative estimate never leaves the engine",
          parsed["eta"] == "", repr(parsed["eta"]))


def test_the_same_message_is_not_repeated():
    """'Picking the best quality' appeared over and over."""
    print("\n[a message is not repeated back to back]")
    from luma.engine.callbacks import EngineCallbacks
    from luma.engine.download import _milestone

    said = []
    cb = EngineCallbacks(on_video_status=lambda tag, m: said.append(m))
    state = {}
    lines = [
        "[info] a: Downloading 1 format(s): 135+140",
        "[info] b: Downloading 1 format(s): 135+140",
        "[info] c: Downloading 1 format(s): 135+140",
        '[Merger] Merging formats into "/d/C.mp4"',
        "[info] d: Downloading 1 format(s): 135+140",
    ]
    for line in lines:
        note = _milestone(line)
        if note is not None and note != state.get("last_note"):
            state["last_note"] = note
            cb.on_video_status("1", note)

    check("three in a row collapse into one",
          said[:2] == ["Picking the best quality...",
                       "Combining video and audio..."], str(said))
    check("a different message still gets through",
          "Combining video and audio..." in said, str(said))
    check("nothing is ever said twice in succession",
          all(a != b for a, b in zip(said, said[1:])), str(said))
    check("but it may be said again later, after something else",
          said == ["Picking the best quality...",
                   "Combining video and audio...",
                   "Picking the best quality..."], str(said))


async def run_all():
    print("=" * 62)
    print("  Luma progress-display and controls checks")
    print("=" * 62)
    test_never_runs_past_the_end()
    test_concurrent_pieces_are_added_up()
    test_time_remaining_is_trustworthy()
    test_the_same_message_is_not_repeated()
    test_sizes_parse()
    test_progress_only_moves_forwards()
    test_sizes_only_grow()
    test_single_stream_still_works()
    await test_row_detail_while_downloading()
    await test_row_detail_when_finished()
    await test_stop_and_clear_visibility()
    await test_stop_button_cancels()
    await test_preparation_happens_once()
    test_update_check_runs_once()
    test_blocked_speedtest_is_not_retried()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL PROGRESS-DISPLAY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
