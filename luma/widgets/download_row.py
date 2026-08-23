"""One row per video being downloaded."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import ProgressBar, Static

#: How long the bar takes to glide to a new value. Short enough to still feel
#: like live progress, long enough to remove the stepping.
FILL_SECONDS = 0.3

#: How long a finished row stays highlighted before settling.
HIGHLIGHT_SECONDS = 1.2


class DownloadRow(Widget):
    """Shows a single video's title, progress bar and current state."""

    def __init__(self, tag, label, **kwargs):
        super().__init__(**kwargs)
        self._tag = tag
        self._label = label
        self._finished = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._label, classes="row-title")
            yield ProgressBar(
                total=100, show_eta=False, show_percentage=True,
            )
            yield Static("Waiting...", classes="row-detail")

    # -- updates ---------------------------------------------------------
    def set_title(self, text):
        self._label = text
        self.query_one(".row-title", Static).update(text)

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
