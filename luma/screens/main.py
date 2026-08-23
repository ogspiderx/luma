"""Luma's main screen: paste a link, start a download, watch it happen."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static


class MainScreen(Screen):
    """The screen the user lands on."""

    BINDINGS = [
        Binding("ctrl+s", "open_settings", "Settings"),
        Binding("ctrl+h", "open_history", "History"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main-body"):
            yield Static("Paste a YouTube link to get started.", id="tagline")
            with Horizontal(id="link-row"):
                yield Input(
                    placeholder="https://youtube.com/watch?v=...",
                    id="url-input",
                )
                yield Button("Download", variant="primary", id="download-btn")
            yield Static("", id="plan-panel")
            yield VerticalScroll(id="downloads")
            yield Static("Ready.", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#url-input", Input).focus()

    # -- actions ---------------------------------------------------------
    def action_open_settings(self) -> None:
        self.app.action_open_settings()

    def action_open_history(self) -> None:
        self.app.action_open_history()
