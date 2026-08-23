"""One row per video being downloaded."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import ProgressBar, Static


class DownloadRow(Widget):
    """Shows a single video's title, progress bar and current state."""

    DEFAULT_CSS = """
    DownloadRow {
        height: auto;
        margin-bottom: 1;
    }
    DownloadRow .row-title {
        text-overflow: ellipsis;
    }
    DownloadRow .row-detail {
        color: $text-muted;
    }
    DownloadRow ProgressBar {
        width: 1fr;
    }
    DownloadRow.-done .row-title {
        color: $success;
    }
    DownloadRow.-failed .row-title {
        color: $error;
    }
    """

    def __init__(self, tag, label, **kwargs):
        super().__init__(**kwargs)
        self._tag = tag
        self._label = label
        self._finished = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._label, classes="row-title")
            with Horizontal():
                yield ProgressBar(
                    total=100, show_eta=False, show_percentage=True
                )
            yield Static("Starting...", classes="row-detail")

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
        bar.update(progress=parsed["percent"])

        bits = []
        if parsed.get("total"):
            bits.append(f"{parsed['total']}")
        if parsed.get("speed"):
            bits.append(f"at {parsed['speed']}")
        if parsed.get("eta"):
            bits.append(f"{parsed['eta']} left")
        self.set_detail("  ".join(bits) if bits else "Downloading...")

    def finish(self, ok, message):
        """Mark the row finished; further progress updates are ignored."""
        self._finished = True
        bar = self.query_one(ProgressBar)
        bar.update(progress=100 if ok else bar.progress)
        self.add_class("-done" if ok else "-failed")
        self.set_detail(message)
