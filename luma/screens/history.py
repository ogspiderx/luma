"""History screen.

Phase 2 stub: reachable and closable. It gets its real contents once downloads
are being recorded.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class HistoryScreen(Screen):
    """Past downloads and anything that went wrong."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="history-body"):
            yield Static("History", id="history-title")
            yield Static("No downloads yet.", id="history-placeholder")
            yield Button("Back", id="history-back")
        yield Footer()

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "history-back":
            self.dismiss()
