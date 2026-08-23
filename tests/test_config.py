#!/usr/bin/env python3
"""
Checks for Luma's settings storage.

The point of these is resilience: a missing, damaged or hand-edited settings
file must never stop Luma from starting, and values off disk must never be
trusted as-is. No interface is involved.

    python tests/test_config.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luma.config import (                                    # noqa: E402
    DEFAULTS, MAX_PARALLEL_LIMIT, describe, load_config,
    normalize, resolve_output_dir, save_config,
)
from luma.engine.constants import ARIA2_MAX_PER_FILE         # noqa: E402
from luma.engine.errors import UnsafePathError               # noqa: E402
from luma.storage import (                                   # noqa: E402
    append_capped, atomic_write_json, read_list, safe_read_json,
)

_failures = []


def check(label, condition, detail=""):
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        _failures.append(label)


def test_storage_survives_damage():
    print("\n[storage survives damage]")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "thing.json")

        check("missing file yields the default",
              safe_read_json(path, {"a": 1}) == {"a": 1})

        check("write reports success", atomic_write_json(path, {"a": 1}))
        check("what was written comes back", safe_read_json(path) == {"a": 1})

        for description, blob in [
            ("garbage bytes", b"\x00\x01\x02not json"),
            ("truncated json", b'{"a": 1'),
            ("empty file", b""),
            ("html error page", b"<html>404</html>"),
        ]:
            with open(path, "wb") as fh:
                fh.write(blob)
            check(f"{description} yields the default",
                  safe_read_json(path, {"fallback": True}) == {"fallback": True})

        check("a good write repairs a damaged file",
              atomic_write_json(path, {"b": 2})
              and safe_read_json(path) == {"b": 2})

        # The previous file must survive a failed write.
        with open(path, "w") as fh:
            json.dump({"keep": "me"}, fh)
        ok = atomic_write_json(path, {"bad": {1, 2, 3}})   # a set is not JSON
        check("unserialisable data is refused", ok is False)
        check("the existing file was left intact",
              safe_read_json(path) == {"keep": "me"})

        # No temp files left lying around.
        leftovers = [f for f in os.listdir(td) if f.endswith(".tmp")]
        check("no temporary files left behind", not leftovers, str(leftovers))


def test_list_helpers():
    print("\n[history-style lists]")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "list.json")
        check("missing list reads as empty", read_list(path) == [])
        for i in range(5):
            append_capped(path, {"n": i}, cap=3)
        items = read_list(path)
        check("list is capped", len(items) == 3, str(len(items)))
        check("newest entry is first", items[0]["n"] == 4, str(items[0]))

        with open(path, "w") as fh:
            fh.write("not a list at all")
        check("damaged list reads as empty", read_list(path) == [])

        atomic_write_json(path, {"not": "a list"})
        check("wrong shape reads as empty", read_list(path) == [])


def test_defaults_and_clamping():
    print("\n[settings are never trusted]")
    cfg = normalize({})
    check("empty settings produce a full set",
          set(cfg) == set(DEFAULTS), str(set(DEFAULTS) - set(cfg)))
    check("not a dict is handled", normalize("nonsense")["quality"]
          == DEFAULTS["quality"])
    check("None is handled", normalize(None)["quality"] == DEFAULTS["quality"])

    wild = normalize({
        "max_parallel": 9999, "conns_per_file": 9999,
        "quality": "8k", "folders": "sideways", "archive": "yes-please",
    })
    check("videos at once is clamped",
          wild["max_parallel"] == MAX_PARALLEL_LIMIT, str(wild["max_parallel"]))
    check("connections are clamped to the engine limit",
          wild["conns_per_file"] == ARIA2_MAX_PER_FILE,
          str(wild["conns_per_file"]))
    check("unknown quality falls back", wild["quality"] == DEFAULTS["quality"])
    check("unknown grouping falls back", wild["folders"] == DEFAULTS["folders"])

    low = normalize({"max_parallel": -5, "conns_per_file": 0})
    check("negative values are raised to a working minimum",
          low["max_parallel"] == 1 and low["conns_per_file"] == 1)

    junk = normalize({"max_parallel": "lots", "conns_per_file": None})
    check("non-numeric values fall back to defaults",
          junk["max_parallel"] == DEFAULTS["max_parallel"]
          and junk["conns_per_file"] == DEFAULTS["conns_per_file"])

    check("every offered quality is accepted",
          all(normalize({"quality": q})["quality"] == q
              for q in ("360", "480", "720", "best")))


def test_dangerous_paths_rejected():
    print("\n[dangerous folders rejected]")
    for bad in ["/etc", "/etc/cron.d", "", "   "]:
        cfg = normalize({"output_dir": bad})
        check(f"{bad!r} falls back to the safe default",
              cfg["output_dir"] == DEFAULTS["output_dir"], cfg["output_dir"])
    with tempfile.TemporaryDirectory() as td:
        cfg = normalize({"output_dir": td})
        check("a normal folder is kept", cfg["output_dir"] == td)


def test_output_folder_resolution():
    print("\n[where files land]")
    with tempfile.TemporaryDirectory() as td:
        flat = resolve_output_dir({"output_dir": td, "folders": "none"})
        check("no grouping uses the folder itself", flat == td, flat)

        dated = resolve_output_dir({"output_dir": td, "folders": "date"})
        check("date grouping makes a dated subfolder",
              dated.startswith(td + os.sep) and os.path.isdir(dated), dated)

        named = resolve_output_dir(
            {"output_dir": td, "folders": "playlist"}, "My Mix")
        check("playlist grouping makes a named subfolder",
              named == os.path.join(td, "My Mix"), named)

        sneaky = resolve_output_dir(
            {"output_dir": td, "folders": "playlist"}, "../../escape")
        check("a hostile playlist name cannot escape",
              sneaky.startswith(td + os.sep), sneaky)

        check("the folder is created", os.path.isdir(sneaky))

        try:
            resolve_output_dir({"output_dir": "/etc", "folders": "none"})
            check("a system folder is refused", False, "it was allowed")
        except UnsafePathError:
            check("a system folder is refused", True)


def test_round_trip():
    print("\n[saving and loading]")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "config.json")
        out = os.path.join(td, "vids")
        os.makedirs(out)

        check("saving succeeds",
              save_config({"output_dir": out, "quality": "720",
                           "max_parallel": 3, "folders": "date"}, path))
        again = load_config(path)
        check("quality persisted", again["quality"] == "720")
        check("folder persisted", again["output_dir"] == out)
        check("grouping persisted", again["folders"] == "date")
        check("videos at once persisted", again["max_parallel"] == 3)

        with open(path, "w") as fh:
            fh.write("}}} broken")
        recovered = load_config(path)
        check("a damaged settings file loads as defaults",
              recovered["quality"] == DEFAULTS["quality"])
        check("and can be saved over cleanly",
              save_config(recovered, path)
              and load_config(path)["quality"] == DEFAULTS["quality"])

        check("missing settings file loads as defaults",
              load_config(os.path.join(td, "nope.json"))["quality"]
              == DEFAULTS["quality"])


def test_plain_language_summary():
    print("\n[plain language]")
    lines = describe(normalize({"quality": "best", "folders": "date"}))
    joined = " ".join(lines).lower()
    check("summary avoids tool names",
          not any(t in joined for t in ("yt-dlp", "aria2c", "ffmpeg")))
    check("summary avoids flag syntax", "--" not in joined)
    check("best quality is spelled out", "best available" in joined, joined)


def main():
    print("=" * 62)
    print("  Luma settings checks")
    print("=" * 62)
    test_storage_survives_damage()
    test_list_helpers()
    test_defaults_and_clamping()
    test_dangerous_paths_rejected()
    test_output_folder_resolution()
    test_round_trip()
    test_plain_language_summary()

    print("\n" + "=" * 62)
    if _failures:
        print(f"  {len(_failures)} CHECK(S) FAILED:")
        for f in _failures:
            print(f"    - {f}")
        return 1
    print("  ALL SETTINGS CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
