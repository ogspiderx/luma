"""The Luma application shell."""

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
    """Luma: a friendly YouTube downloader for the terminal."""

    CSS_PATH = "luma.tcss"
    TITLE = APP_NAME
    SUB_TITLE = f"v{__version__}"

    #: Off deliberately. The palette is a developer's tool -- a searchable
    #: list of every command and every theme Textual knows -- and offering it
    #: to someone who wants to download a video means a key that does nothing
    #: they need, an icon in the corner, and a way to end up in a colour
    #: scheme that is not Luma's. Settings covers everything that is theirs
    #: to change.
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
        #: Whether to set up the tools and read the connection on startup.
        #: Turned off by tests, which supply their own stand-ins.
        self.auto_prepare = auto_prepare
        #: Filled in once by the startup preparation, then reused.
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

    # -- settings --------------------------------------------------------
    def apply_theme(self) -> None:
        """Use the saved theme, falling back if it is not one of Luma's.

        Only Luma's own two are offered, so a config naming anything else --
        an older version's borrowed palette, or a hand-edited file -- lands
        on the default rather than a look the app was never designed in.
        """
        wanted = self.config.get("theme")
        if wanted not in THEME_NAMES:
            wanted = DEFAULT_THEME
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
