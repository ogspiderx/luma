#!/usr/bin/env sh
# Luma, on Linux. Double-click it, or run ./run.sh from a terminal.
set -eu

cd "$(dirname "$0")"

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done

if [ -z "$PY" ]; then
    echo
    echo "  Luma needs Python 3, and it is not installed yet."
    if command -v pacman >/dev/null 2>&1; then
        echo "      sudo pacman -S --needed python"
    else
        echo "      Install python3 with your package manager, then run this again."
    fi
    echo
    exit 1
fi

# Arch and most current distributions mark the system Python as externally
# managed, so installing into it is refused outright. A virtual environment
# beside Luma keeps its one dependency to itself and needs no permissions.
VENV=".venv"
if [ ! -x "$VENV/bin/python" ]; then
    echo
    echo "  Setting up Luma for the first time. This happens once."
    echo
    if ! "$PY" -m venv "$VENV"; then
        echo "  Could not create the environment Luma runs in."
        if command -v pacman >/dev/null 2>&1; then
            echo "      sudo pacman -S --needed python"
        fi
        exit 1
    fi
    "$VENV/bin/python" -m pip install --quiet --upgrade pip || true
    if ! "$VENV/bin/python" -m pip install --quiet -r requirements.txt; then
        echo
        echo "  Setup did not finish. Check your internet connection and run"
        echo "  this file again."
        echo
        rm -rf "$VENV"
        exit 1
    fi
    echo "  Ready."
fi

# The download tools come from the distribution here: the copies Luma fetches
# for itself are Windows binaries and are no use on Linux.
missing=""
for tool in yt-dlp aria2c ffmpeg; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done

if [ -n "$missing" ]; then
    echo
    echo "  Luma still needs:$missing"
    if command -v pacman >/dev/null 2>&1; then
        echo "      sudo pacman -S --needed yt-dlp aria2 ffmpeg"
    elif command -v apt >/dev/null 2>&1; then
        echo "      sudo apt install yt-dlp aria2 ffmpeg"
    elif command -v dnf >/dev/null 2>&1; then
        echo "      sudo dnf install yt-dlp aria2 ffmpeg"
    fi
    echo
    echo "  Luma will start anyway and say the same thing on screen."
    echo
fi

exec "$VENV/bin/python" -m luma "$@"
