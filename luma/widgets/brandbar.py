"""The bar across the top of every screen."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static

from ..branding import WORDMARK


class BrandBar(Widget):
    """The name on the left, one useful fact on the right.

    Textual's own Header is not used: it carries a command-palette icon and
    a clock, neither of which Luma has any use for, and it cannot be told to
    drop them. One line, no decoration, nothing that does nothing.
    """

    def __init__(self, note="", **kwargs):
        super().__init__(**kwargs)
        self._note = note

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(WORDMARK, classes="brand-mark")
            yield Static(self._note, classes="brand-note")

    def set_note(self, text):
        """Replace the fact on the right. Safe before the bar is drawn."""
        self._note = text or ""
        try:
            self.query_one(".brand-note", Static).update(self._note)
        except Exception:                              # noqa: BLE001
            pass    # not composed yet; compose() will use the stored text
