"""
Measuring the user's connection, so the download plan can be calculated
rather than guessed.

Ported unchanged from yt_turbo.py apart from status reporting via callbacks.
"""

import concurrent.futures as futures
import socket
import ssl
import statistics
import threading
import time
import urllib.request

from .callbacks import EngineCallbacks
from .constants import SPEEDTEST_HOST, SPEEDTEST_URL, UA


def _timed_download(nbytes, max_secs, counter=None):
    """Download up to `nbytes` from Cloudflare, but stop after `max_secs`.

    Returns (bytes_read, elapsed_seconds). Adapts to slow links.
    """
    url = SPEEDTEST_URL.format(n=nbytes)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ctx = ssl.create_default_context()
    got = 0
    start = time.time()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            while True:
                chunk = resp.read(1024 * 128)
                if not chunk:
                    break
                got += len(chunk)
                if counter is not None:
                    with counter["lock"]:
                        counter["bytes"] += len(chunk)
                if time.time() - start >= max_secs:
                    break
    except Exception:
        pass
    return got, max(time.time() - start, 1e-6)


def measure_latency(host=SPEEDTEST_HOST, port=443, samples=5):
    """Median TCP-connect RTT in milliseconds (no ICMP needed)."""
    times = []
    for _ in range(samples):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        t0 = time.time()
        try:
            s.connect((host, port))
            times.append((time.time() - t0) * 1000)
        except Exception:
            pass
        finally:
            s.close()
    return statistics.median(times) if times else 40.0


def measure_bandwidth(callbacks=None):
    """Returns (single_mbps, line_mbps, rtt_ms).

    single_mbps : throughput of ONE TCP stream  -> the per-connection ceiling.
    line_mbps   : throughput of MANY parallel streams -> the real line rate.

    The ratio line/single is how many connections it takes to fill the pipe,
    which is what compute_plan() turns into a download plan.
    """
    callbacks = callbacks or EngineCallbacks()

    callbacks.on_status("Checking your connection speed...")
    b, t = _timed_download(25_000_000, max_secs=6)
    single_mbps = b * 8 / t / 1e6

    callbacks.on_status("Checking how many downloads it can handle...")
    n_streams = 8
    counter = {"bytes": 0, "lock": threading.Lock()}
    start = time.time()
    with futures.ThreadPoolExecutor(max_workers=n_streams) as ex:
        jobs = [
            ex.submit(_timed_download, 20_000_000, 6, counter)
            for _ in range(n_streams)
        ]
        for j in jobs:
            j.result()
    elapsed = max(time.time() - start, 1e-6)
    line_mbps = counter["bytes"] * 8 / elapsed / 1e6

    # Parallel should never read as slower than single (measurement noise).
    line_mbps = max(line_mbps, single_mbps)

    rtt = measure_latency()
    return single_mbps, line_mbps, rtt
