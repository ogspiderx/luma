"""Settings screen.

Phase 2 stub: reachable and closable, so the screen stack and the test harness
can be proven before any real settings exist.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class SettingsScreen(Screen):
    """Where the user changes how Luma behaves."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="settings-body"):
            yield Static("Settings", id="settings-title")
            yield Static("Nothing to change yet.", id="settings-placeholder")
            yield Button("Back", id="settings-back")
        yield Footer()

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-back":
            self.dismiss()
