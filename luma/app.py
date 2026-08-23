"""The Luma application shell."""

from textual.app import App
from textual.binding import Binding

from . import APP_NAME, __version__
from .screens.history import HistoryScreen
from .screens.main import MainScreen
from .screens.settings import SettingsScreen


class LumaApp(App):
    """Luma: a friendly YouTube downloader for the terminal."""

    CSS_PATH = "luma.tcss"
    TITLE = APP_NAME
    SUB_TITLE = f"v{__version__}"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    # -- actions shared by the screens -----------------------------------
    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_open_history(self) -> None:
        self.push_screen(HistoryScreen())
