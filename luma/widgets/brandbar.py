from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from ..branding import WORDMARK


class BrandBar(Widget):
    def __init__(self, note="", **kwargs):
        super().__init__(**kwargs)
        self._note = note

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(WORDMARK, classes="brand-mark")
            yield Static(self._note, classes="brand-note")

    def set_note(self, text):
        self._note = text or ""
        try:
            self.query_one(".brand-note", Static).update(self._note)
        except Exception:
            pass
