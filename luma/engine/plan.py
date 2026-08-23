"""
Turning a measured connection into a concrete download plan.

The maths here is ported verbatim from yt_turbo.py and is calibrated against
the constants in constants.py. Do not adjust it casually -- it is the reason
Luma saturates a connection instead of trickling.
"""

import math

from .constants import (
    ARIA2_MAX_PER_FILE,
    MAX_TOTAL_CONNECTIONS,
    YT_PER_VIDEO_MBPS_CAP,
)


def compute_plan(single_mbps, line_mbps, rtt_ms, num_urls, max_parallel):
    """Decide (parallel_files, conns_per_file, concurrent_fragments).

    Two independent levers, each grounded in how the network actually behaves:

    A) connections-per-video -- beats YouTube's PER-CONNECTION throttle.
       A single stream tops out (server cap + TCP's own ceiling of
       congestion_window / RTT). Opening more connections to the same video
       multiplies throughput, with useful returns up to aria2c's 16-per-server
       limit. The speed test cannot see YouTube's per-connection cap, so it is
       not allowed to limit this -- we always open the maximum.

    B) parallel videos -- fills the LINE on a playlist/batch.
       Each YouTube video is throttled to about
       per_video = min(single, YT_PER_VIDEO_MBPS_CAP), so it takes about
       line / per_video videos running at once to saturate the pipe.

    A global cap (MAX_TOTAL_CONNECTIONS) keeps the total socket count polite,
    trimming parallel videos first if A x B would exceed it.
    """
    single = max(single_mbps, 0.1)
    line = max(line_mbps, single)

    # --- justification numbers (shown to the user) ---------------------
    ratio_conns = math.ceil(line / single)
    bdp_bytes = (line * 1e6 / 8.0) * (rtt_ms / 1000.0)
    window = 256 * 1024  # ~256 KB effective per-stream window (TCP w/ scaling)
    bdp_conns = max(1, math.ceil(bdp_bytes / window))
    budget = max(4, min(max(ratio_conns, bdp_conns), MAX_TOTAL_CONNECTIONS))

    # --- lever A: connections per video --------------------------------
    conns_per_file = ARIA2_MAX_PER_FILE

    # --- lever B: how many throttled videos it takes to fill the line --
    per_video = min(single, YT_PER_VIDEO_MBPS_CAP)
    videos_to_fill = max(1, math.ceil(line / per_video))
    parallel_files = min(videos_to_fill, max_parallel, max(1, num_urls))

    # --- keep total open sockets sane (trim parallelism first) ---------
    while (parallel_files > 1
           and parallel_files * conns_per_file > MAX_TOTAL_CONNECTIONS):
        parallel_files -= 1

    concurrent_fragments = conns_per_file  # DASH fragments in flight per video

    return {
        "single_mbps": single_mbps,
        "line_mbps": line_mbps,
        "rtt_ms": rtt_ms,
        "bdp_bytes": bdp_bytes,
        "ratio_conns": ratio_conns,
        "bdp_conns": bdp_conns,
        "budget": budget,
        "per_video_mbps": per_video,
        "videos_to_fill": videos_to_fill,
        "parallel_files": parallel_files,
        "conns_per_file": conns_per_file,
        "concurrent_fragments": concurrent_fragments,
    }


def default_plan(num_urls, max_parallel):
    """Used when the speed test is skipped or fails."""
    parallel = min(max(1, num_urls), max_parallel, 4)
    return {
        "single_mbps": None,
        "line_mbps": None,
        "rtt_ms": None,
        "bdp_bytes": None,
        "ratio_conns": None,
        "bdp_conns": None,
        "per_video_mbps": None,
        "videos_to_fill": None,
        "budget": parallel * ARIA2_MAX_PER_FILE,
        "parallel_files": parallel,
        "conns_per_file": ARIA2_MAX_PER_FILE,
        "concurrent_fragments": ARIA2_MAX_PER_FILE,
    }


def apply_overrides(plan, conns_per_file=None, parallel_files=None,
                    num_urls=None):
    """Clamp-and-apply explicit user settings on top of a computed plan."""
    if conns_per_file:
        c = max(1, min(ARIA2_MAX_PER_FILE, int(conns_per_file)))
        plan["conns_per_file"] = c
        plan["concurrent_fragments"] = c
    if parallel_files:
        p = max(1, int(parallel_files))
        if num_urls:
            p = min(p, max(1, num_urls))
        plan["parallel_files"] = p
    return plan


def describe_plan(plan):
    """Plain-language summary lines for the UI. No jargon, no flag names."""
    lines = []
    if plan.get("line_mbps") is not None:
        lines.append(f"Your speed: {plan['line_mbps']:.1f} Mbps")
    lines.append(f"Videos at once: {plan['parallel_files']}")
    lines.append(f"Connections per video: {plan['conns_per_file']}")
    return lines
