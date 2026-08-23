"""One row per video being downloaded."""

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import ProgressBar, Static

#: How long the bar takes to glide to a new value. Short enough to still feel
#: like live progress, long enough to remove the stepping.
FILL_SECONDS = 0.3

#: How long a finished row stays highlighted before settling.
HIGHLIGHT_SECONDS = 1.2

#: "712KiB/s" and friends -> bytes per second, for adding rates together.
_RATE = re.compile(r"([\d.]+)\s*([KMGT]?)i?B/s", re.IGNORECASE)
_SCALE = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def rate_to_bytes(text):
    """Turn a speed like '712KiB/s' into bytes per second, or 0."""
    match = _RATE.search(text or "")
    if not match:
        return 0.0
    try:
        return float(match.group(1)) * _SCALE.get(match.group(2).upper(), 1)
    except ValueError:
        return 0.0


class DownloadRow(Widget):
    """Shows a single video's title, progress bar and current state."""

    def __init__(self, tag, url, **kwargs):
        super().__init__(**kwargs)
        self._tag = tag
        self.url = url
        self._title = ""
        self._finished = False
        self._speed_bytes = 0.0

    # -- what the row is about -------------------------------------------
    @property
    def display_title(self):
        """The title if it is known yet, otherwise something honest."""
        return self._title or "Getting details..."

    @property
    def finished(self):
        return self._finished

    @property
    def speed_bytes(self):
        """Current rate in bytes per second; zero once finished."""
        return 0.0 if self._finished else self._speed_bytes

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.display_title, classes="row-title")
            yield ProgressBar(
                total=100, show_eta=False, show_percentage=True,
            )
            yield Static("Waiting...", classes="row-detail")

    # -- updates ---------------------------------------------------------
    def set_title(self, title):
        """Replace the placeholder with the video's real title."""
        if not title:
            return
        self._title = title
        self.query_one(".row-title", Static).update(title)

    def set_detail(self, text):
        self.query_one(".row-detail", Static).update(text)

    def set_progress(self, parsed):
        """Apply a parsed progress dict from the engine."""
        if self._finished:
            return
        bar = self.query_one(ProgressBar)
        # Glide to the new value instead of jumping, so the bar reads as
        # motion rather than a series of steps.
        bar.animate("progress", value=float(parsed["percent"]),
                    duration=FILL_SECONDS)

        self._speed_bytes = rate_to_bytes(parsed.get("speed"))

        bits = []
        if parsed.get("total"):
            bits.append(str(parsed["total"]))
        if parsed.get("speed"):
            bits.append(f"at {parsed['speed']}")
        if parsed.get("eta"):
            bits.append(f"{parsed['eta']} left")
        self.set_detail("  ".join(bits) if bits else "Downloading...")

    def finish(self, ok, message):
        """Mark the row finished; further progress updates are ignored."""
        self._finished = True
        self._speed_bytes = 0.0
        bar = self.query_one(ProgressBar)
        if ok:
            bar.update(progress=100)
        self.add_class("-done" if ok else "-failed")
        self.set_detail(message)

        # A brief highlight to catch the eye, then settle back. One shot --
        # nothing here keeps animating.
        self.add_class("-just-finished")
        self.set_timer(
            HIGHLIGHT_SECONDS,
            lambda: self.remove_class("-just-finished"),
        )
