#!/usr/bin/env python3
"""
Build the portable Luma release: a folder and a zip containing the source,
the launcher and the documentation -- and nothing personal.

    python make_release.py

The result lands in dist/. Anything created by running Luma (downloaded tools,
downloaded videos, settings, records, logs) is deliberately left out, so the
archive is the same whether or not Luma has ever been used here.
"""

import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

#: Folders never included: either runtime state or personal data.
SKIP_DIRS = {
    "__pycache__", "bin", "downloads", "logs", "dist", ".git", ".pytest_cache",
}

#: Files never included, for the same reason.
SKIP_FILES = {
    ".installed", "config.json", "history.json", "errors.json",
}

SKIP_SUFFIXES = (".pyc", ".pyo", ".part", ".aria2", ".zip")

#: Everything a working copy needs.
INCLUDE_TOP = {
    "luma", "tests", "run.bat", "requirements.txt", "README.md",
    "SECURITY.md", ".gitignore", "make_release.py",
}


def wanted(path):
    """True if `path` (relative to ROOT) belongs in the release."""
    parts = path.split(os.sep)
    if parts[0] not in INCLUDE_TOP:
        return False
    if any(part in SKIP_DIRS for part in parts):
        return False
    if parts[-1] in SKIP_FILES:
        return False
    return not parts[-1].endswith(SKIP_SUFFIXES)


def collect():
    """Every file that belongs in the release, relative to ROOT."""
    found = []
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, ROOT)
            if wanted(rel):
                found.append(rel)
    return sorted(found)


def main():
    version = "0.1.0"
    sys.path.insert(0, ROOT)
    try:
        from luma import __version__ as version           # noqa: F811
    except Exception:                                      # noqa: BLE001
        pass

    name = f"Luma-{version}"
    staging = os.path.join(DIST, name)

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(staging)

    files = collect()
    for rel in files:
        target = os.path.join(staging, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), target)

    archive = os.path.join(DIST, f"{name}.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(os.path.join(staging, rel), os.path.join(name, rel))

    size = os.path.getsize(archive)
    print(f"{len(files)} files")
    print(f"folder : {staging}")
    print(f"archive: {archive}  ({size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
