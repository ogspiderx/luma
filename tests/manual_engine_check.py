#!/usr/bin/env python3
"""
Throwaway CLI harness that exercises Luma's engine with no UI involved.

This exists to prove the engine works before any terminal-UI code is written,
so that later bugs are provably UI bugs rather than engine bugs. It is a
development aid, not a product surface.

    python tests/manual_engine_check.py <youtube-url> [more urls...]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luma.engine.callbacks import EngineCallbacks          # noqa: E402
from luma.engine.constants import DEFAULT_MAX_PARALLEL, human  # noqa: E402
from luma.engine.download import run_downloads             # noqa: E402
from luma.engine.errors import LumaError                   # noqa: E402
from luma.engine.inputs import expand_playlists, gather_inputs  # noqa: E402
from luma.engine.plan import compute_plan, describe_plan   # noqa: E402
from luma.engine.speedtest import measure_bandwidth        # noqa: E402
from luma.engine.tools import ensure_tools                 # noqa: E402


def make_callbacks():
    def on_status(msg):
        print(f"[status] {msg}", flush=True)

    def on_tool_progress(desc, got, total):
        if total:
            print(f"\r[tool] {desc}: {got * 100 / total:5.1f}% "
                  f"({human(got)}/{human(total)})", end="", flush=True)
        else:
            print(f"\r[tool] {desc}: {human(got)}", end="", flush=True)

    def on_video_start(tag, url):
        print(f"[{tag}] START {url}", flush=True)

    def on_video_status(tag, msg):
        print(f"[{tag}] {msg}", flush=True)

    def on_video_progress(tag, p):
        eta = f" ETA {p['eta']}" if p["eta"] else ""
        conns = f" CN:{p['connections']}" if p["connections"] else ""
        print(f"\r[{tag}] {p['percent']:5.1f}%  {p['total']}  "
              f"@ {p['speed']}{conns}{eta}   ", end="", flush=True)

    def on_video_done(tag, url, ok, reason, filepath):
        print()
        if ok:
            print(f"[{tag}] DONE -> {filepath}", flush=True)
        else:
            print(f"[{tag}] FAILED -> {reason}", flush=True)

    return EngineCallbacks(
        on_status=on_status,
        on_tool_progress=on_tool_progress,
        on_video_start=on_video_start,
        on_video_status=on_video_status,
        on_video_progress=on_video_progress,
        on_video_done=on_video_done,
    )


def main(argv):
    if not argv:
        print(__doc__)
        return 1

    cb = make_callbacks()
    out_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "downloads")

    urls, rejected = gather_inputs(argv)
    for text, reason in rejected:
        print(f"[rejected] {text!r}: {reason}")
    if not urls:
        print("Nothing valid to download.")
        return 1

    try:
        tools = ensure_tools(cb)
    except LumaError as exc:
        print(f"[x] {exc.user_message}")
        return 1
    print(f"[tools] {tools}")

    urls = expand_playlists(tools["yt-dlp"], urls, cb)
    print(f"[queue] {len(urls)} video(s)")

    single, line, rtt = measure_bandwidth(cb)
    plan = compute_plan(single, line, rtt, len(urls), DEFAULT_MAX_PARALLEL)
    for row in describe_plan(plan):
        print(f"[plan] {row}")

    results = run_downloads(tools, urls, plan, out_dir, quality="480",
                            callbacks=cb)

    ok = [r for r in results if r[1]]
    bad = [r for r in results if not r[1]]
    print(f"\n== {len(ok)} succeeded, {len(bad)} failed -> {out_dir}")
    for url, _, reason, _ in bad:
        print(f"   {url}: {reason}")
    return 0 if not bad else 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        from luma.engine.download import terminate_all
        terminate_all()
        print("\nCancelled.")
        sys.exit(130)
