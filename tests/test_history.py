#!/usr/bin/env python3
"""
Checks for the download and failure records.

The two files are kept separate on purpose, and recording must never be able
to break a download that already succeeded.

    python tests/test_history.py
"""

import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luma.history import (                                    # noqa: E402
    ERRORS_CAP, HISTORY_CAP, human_size, human_when,
    record_failure, record_results, record_success,
    recent_downloads, recent_failures,
)
from luma.storage import read_list                            # noqa: E402

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


def test_successes_recorded():
    print("\n[downloads are recorded]")
    with tempfile.TemporaryDirectory() as td:
        hist = os.path.join(td, "history.json")
        video = os.path.join(td, "Cat Video [dQw4w9WgXcQ].mp4")
        with open(video, "wb") as fh:
            fh.write(b"x" * 4096)

        check("recording succeeds",
              record_success("https://youtu.be/abc123", video, "480", hist))
        rows = recent_downloads(path=hist)
        check("one entry written", len(rows) == 1, str(len(rows)))
        row = rows[0]
        check("title is readable, without the video id",
              row["title"] == "Cat Video", row["title"])
        check("link stored", row["url"] == "https://youtu.be/abc123")
        check("file path stored", row["file"] == video)
        check("size measured from the real file", row["size"] == 4096,
              str(row["size"]))
        check("quality stored", row["quality"] == "480")
        check("timestamp stored", bool(row["when"]))

        record_success("https://youtu.be/second", video, "720", hist)
        check("newest entry comes first",
              recent_downloads(path=hist)[0]["url"] == "https://youtu.be/second")


def test_failures_recorded_separately():
    print("\n[failures are kept apart]")
    with tempfile.TemporaryDirectory() as td:
        hist = os.path.join(td, "history.json")
        errs = os.path.join(td, "errors.json")

        record_success("https://youtu.be/ok", os.path.join(td, "A [CdbHAzNB1n0].mp4"),
                       "480", hist)
        record_failure("https://youtu.be/bad", "This video is private.", errs)

        check("history holds only the success", len(read_list(hist)) == 1)
        check("errors hold only the failure", len(read_list(errs)) == 1)
        failure = recent_failures(path=errs)[0]
        check("failure keeps the link",
              failure["url"] == "https://youtu.be/bad")
        check("failure keeps a plain-language reason",
              failure["reason"] == "This video is private.")
        check("failure is timestamped", bool(failure["when"]))
        joined = " ".join(str(v) for v in failure.values()).lower()
        check("failure exposes no tool names",
              not any(t in joined for t in ("yt-dlp", "aria2c", "ffmpeg")))

        record_failure("https://youtu.be/x", "", errs)
        check("a missing reason still gets something readable",
              len(recent_failures(path=errs)[0]["reason"]) > 0)


def test_batch_recording():
    print("\n[a whole batch at once]")
    with tempfile.TemporaryDirectory() as td:
        hist = os.path.join(td, "history.json")
        errs = os.path.join(td, "errors.json")
        good = os.path.join(td, "Good [ODl-DYTyNyM].mp4")
        with open(good, "wb") as fh:
            fh.write(b"y" * 100)

        results = [
            ("https://youtu.be/1", True, "", good),
            ("https://youtu.be/2", False, "This video is private.", None),
            ("https://youtu.be/3", True, "", good),
            ("https://youtu.be/4", False, "The connection dropped.", None),
        ]
        saved, failed = record_results(results, "480", hist, errs)
        check("counts the successes", saved == 2, str(saved))
        check("counts the failures", failed == 2, str(failed))
        check("history has both successes", len(read_list(hist)) == 2)
        check("errors have both failures", len(read_list(errs)) == 2)

        # A malformed row must not stop the rest being recorded.
        saved, failed = record_results(
            [("https://youtu.be/5", True, "", good), ("broken",)], "480",
            hist, errs)
        check("a malformed row is skipped, not fatal", saved == 1, str(saved))
        check("the good row still landed", len(read_list(hist)) == 3)


def test_records_are_capped():
    print("\n[records cannot grow forever]")
    with tempfile.TemporaryDirectory() as td:
        errs = os.path.join(td, "errors.json")
        for i in range(ERRORS_CAP + 25):
            record_failure(f"https://youtu.be/{i}", "nope", errs)
        rows = read_list(errs)
        check("failure list is capped", len(rows) == ERRORS_CAP, str(len(rows)))
        check("the newest failure is kept",
              rows[0]["url"].endswith(str(ERRORS_CAP + 24)), rows[0]["url"])


def test_recording_never_raises():
    print("\n[recording never breaks a download]")
    # /etc/hostname is a file, so it can never act as a parent directory.
    # This stays unwritable even when the tests happen to run as root.
    unwritable = "/etc/hostname/sub/history.json"
    check("an unwritable location returns False instead of raising",
          record_success("https://youtu.be/x", "/tmp/a.mp4", "480",
                         unwritable) is False)
    check("same for failures",
          record_failure("https://youtu.be/x", "nope", unwritable) is False)

    with tempfile.TemporaryDirectory() as td:
        hist = os.path.join(td, "history.json")
        check("a missing file is fine to read", recent_downloads(path=hist) == [])
        with open(hist, "w") as fh:
            fh.write("{{{ not json")
        check("a damaged history reads as empty",
              recent_downloads(path=hist) == [])
        check("and can still be written to",
              record_success("https://youtu.be/x", os.path.join(td, "B [wOLLUrf-ESI].mp4"),
                             "480", hist))
        check("the repaired file reads back",
              len(recent_downloads(path=hist)) == 1)


def test_display_helpers():
    print("\n[readable for a person]")
    check("bytes shown plainly", human_size(4096) == "4.0 KB", human_size(4096))
    check("megabytes shown plainly",
          human_size(5 * 1024 * 1024) == "5.0 MB",
          human_size(5 * 1024 * 1024))
    check("unknown size shows a dash", human_size(None) == "-")
    check("zero size shows a dash", human_size(0) == "-")

    now = datetime.datetime.now().isoformat(timespec="seconds")
    check("today is labelled", human_when(now).startswith("Today"),
          human_when(now))
    yesterday = (datetime.datetime.now()
                 - datetime.timedelta(days=1)).isoformat(timespec="seconds")
    check("yesterday is labelled", human_when(yesterday).startswith("Yesterday"),
          human_when(yesterday))
    check("a damaged timestamp does not crash", human_when("nonsense") == "nonsense")
    check("a missing timestamp does not crash", human_when(None) == "-")


def main():
    print("=" * 62)
    print("  Luma record-keeping checks")
    print("=" * 62)
    test_successes_recorded()
    test_failures_recorded_separately()
    test_batch_recording()
    test_records_are_capped()
    test_recording_never_raises()
    test_display_helpers()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL RECORD-KEEPING CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
