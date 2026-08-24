"""One row per video in the download list."""

import re

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, ProgressBar, Static

from ..engine.constants import human

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
    """Shows one video's title, progress and current state."""

    class RemoveRequested(Message):
        """The person asked for this row to go away."""

        def __init__(self, row):
            super().__init__()
            self.row = row

    def __init__(self, tag, url, **kwargs):
        super().__init__(**kwargs)
        self._tag = tag
        self.url = url
        self._title = ""
        self._finished = False
        self._ok = False
        self._started = False
        self._speed_bytes = 0.0
        self._percent = 0.0
        #: Kept so the row can be told things before it is drawn.
        self._detail = "Waiting..."
        #: Position in the list, so "order added" can be restored.
        self.sequence = 0

    # -- what the row is about -------------------------------------------
    @property
    def tag(self):
        return self._tag

    @property
    def display_title(self):
        """The title if it is known yet, otherwise something honest."""
        return self._title or "Getting details..."

    @property
    def title_text(self):
        """Title for sorting: empty until known, so it sorts predictably."""
        return self._title or ""

    @property
    def finished(self):
        return self._finished

    @property
    def succeeded(self):
        return self._finished and self._ok

    @property
    def started(self):
        """True once this row has had any progress at all."""
        return self._started

    @property
    def percent(self):
        return 100.0 if self.succeeded else self._percent

    @property
    def speed_bytes(self):
        """Current rate in bytes per second; zero once finished."""
        return 0.0 if self._finished else self._speed_bytes

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="row-main"):
                yield Static(self.display_title, classes="row-title")
                yield ProgressBar(
                    total=100, show_eta=False, show_percentage=True,
                )
                yield Static(self._detail, classes="row-detail")
            yield Button("✕", classes="row-remove", tooltip="Remove")

    # -- updates ---------------------------------------------------------
    def _bar(self):
        """The progress bar, or None if the row has not been drawn yet."""
        try:
            return self.query_one(ProgressBar)
        except Exception:                              # noqa: BLE001
            return None

    def _write(self, selector, text):
        """Update a child if it exists yet.

        A row can be told things between being created and being drawn, so
        the text is kept and used by compose() when that happens.
        """
        try:
            self.query_one(selector, Static).update(text)
        except Exception:                              # noqa: BLE001
            pass    # not composed yet; compose() will pick up the stored text

    def set_title(self, title):
        """Replace the placeholder with the video's real title."""
        if not title:
            return
        self._title = title
        self._write(".row-title", title)

    def set_detail(self, text):
        self._detail = text
        self._write(".row-detail", text)

    def set_waiting(self, position=None):
        """Mark this row as queued behind others."""
        if self._finished or self._started:
            return
        if position:
            self.set_detail(f"Waiting - number {position} in the queue")
        else:
            self.set_detail("Waiting...")

    def set_progress(self, parsed):
        """Apply a progress reading covering the whole video."""
        if self._finished:
            return
        self._started = True
        # Clamp here as well as in the engine: a bar that reads past 100%
        # destroys trust in everything else on screen.
        percent = max(0.0, min(100.0, float(parsed.get("percent") or 0.0)))
        self._percent = percent
        bar = self._bar()
        if bar is not None:
            # Glide to the new value instead of jumping, so the bar reads as
            # motion rather than a series of steps.
            bar.animate("progress", value=percent, duration=FILL_SECONDS)

        self._speed_bytes = rate_to_bytes(parsed.get("speed"))
        self.set_detail(self._describe(parsed))

    @staticmethod
    def _describe(parsed):
        """Which part is arriving, how fast, how much of how much, and left."""
        bits = []
        kind = parsed.get("kind")
        if kind:
            bits.append(kind)
        if parsed.get("speed"):
            bits.append(str(parsed["speed"]))

        done = parsed.get("done_bytes") or 0
        total = parsed.get("total_bytes") or 0
        if total:
            bits.append(f"{human(done)} of {human(total)}")
        elif done:
            bits.append(human(done))

        eta = parsed.get("eta")
        if eta and eta not in ("0s", "00:00"):
            bits.append(f"{eta} left")
        return "   ".join(bits) if bits else "Starting..."

    def finish(self, ok, message):
        """Mark the row finished; further progress updates are ignored.

        A finished row shows its link, so it can be copied or opened again;
        the running figures are no longer meaningful once it is done.
        """
        self._finished = True
        self._ok = bool(ok)
        self._started = True
        self._speed_bytes = 0.0
        bar = self._bar()
        if ok:
            self._percent = 100.0
            if bar is not None:
                bar.update(progress=100)
        self.add_class("-done" if ok else "-failed")
        self.set_detail(self.url if ok else (message or "Did not finish."))

        # A brief highlight to catch the eye, then settle back. One shot --
        # nothing here keeps animating.
        self.add_class("-just-finished")
        self.set_timer(
            HIGHLIGHT_SECONDS,
            lambda: self.remove_class("-just-finished"),
        )

    # -- removing --------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if "row-remove" in event.button.classes:
            event.stop()
            self.post_message(self.RemoveRequested(self))
