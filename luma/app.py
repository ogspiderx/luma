"""The Luma application shell."""

from textual.app import App
from textual.binding import Binding

from . import APP_NAME, __version__
from .config import load_config, save_config
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

    def __init__(self, config_path=None, history_path=None, errors_path=None,
                 **kwargs):
        super().__init__(**kwargs)
        self._config_path = config_path
        self._history_path = history_path
        self._errors_path = errors_path
        self.config = {}

    def on_mount(self) -> None:
        self.config = (
            load_config(self._config_path) if self._config_path
            else load_config()
        )
        self.apply_theme()
        self.push_screen(MainScreen())

    # -- settings --------------------------------------------------------
    def apply_theme(self) -> None:
        """Use the saved theme, ignoring it if it is not one Textual knows."""
        wanted = self.config.get("theme")
        if not wanted:
            return
        try:
            self.theme = wanted
        except Exception:                              # noqa: BLE001
            pass   # an unknown theme name should never stop the app

    def update_config(self, new_config) -> bool:
        """Persist new settings and apply anything that takes effect at once."""
        saved = (
            save_config(new_config, self._config_path) if self._config_path
            else save_config(new_config)
        )
        self.config = (
            load_config(self._config_path) if self._config_path
            else load_config()
        )
        self.apply_theme()
        return saved

    # -- actions shared by the screens -----------------------------------
    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_open_history(self) -> None:
        self.push_screen(HistoryScreen(
            history_path=self._history_path,
            errors_path=self._errors_path,
        ))
