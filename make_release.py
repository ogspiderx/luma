#!/usr/bin/env python3
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")

SKIP_DIRS = {
    "__pycache__", "bin", "downloads", "logs", "dist", ".git", ".pytest_cache",
}

SKIP_FILES = {
    ".installed", "config.json", "history.json", "errors.json",
}

SKIP_SUFFIXES = (".pyc", ".pyo", ".part", ".aria2", ".zip")

INCLUDE_TOP = {
    "luma", "run.bat", "requirements.txt", "README.md", "SECURITY.md",
}


def wanted(path):
    parts = path.split(os.sep)
    if parts[0] not in INCLUDE_TOP:
        return False
    if any(part in SKIP_DIRS for part in parts):
        return False
    if parts[-1] in SKIP_FILES:
        return False
    return not parts[-1].endswith(SKIP_SUFFIXES)


def collect():
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
        from luma import __version__ as version
    except Exception:
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
