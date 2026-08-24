from textual.app import App
from textual.binding import Binding

from . import APP_NAME, __version__
from .config import load_config, save_config
from .screens.history import HistoryScreen
from .screens.main import MainScreen
from .screens.settings import SettingsScreen
from .theme import DEFAULT_THEME, THEME_NAMES
from .theme import register as register_themes


class LumaApp(App):
    CSS_PATH = "luma.tcss"
    TITLE = APP_NAME
    SUB_TITLE = f"v{__version__}"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(self, config_path=None, history_path=None, errors_path=None,
                 auto_prepare=True, **kwargs):
        super().__init__(**kwargs)
        self._config_path = config_path
        self._history_path = history_path
        self._errors_path = errors_path
        self.auto_prepare = auto_prepare
        self.tools = None
        self.bandwidth = None
        self.config = {}

    def on_mount(self) -> None:
        register_themes(self)
        self.config = (
            load_config(self._config_path) if self._config_path
            else load_config()
        )
        self.apply_theme()
        self.push_screen(MainScreen())

    def apply_theme(self) -> None:
        wanted = self.config.get("theme")
        if wanted not in THEME_NAMES:
            wanted = DEFAULT_THEME
        try:
            self.theme = wanted
        except Exception:
            pass

    def update_config(self, new_config) -> bool:
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

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_open_history(self) -> None:
        self.push_screen(HistoryScreen(
            history_path=self._history_path,
            errors_path=self._errors_path,
        ))
