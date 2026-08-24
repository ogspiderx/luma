from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Input, Label, Select, Static, Switch,
)

from ..branding import DAY_LABEL, NIGHT_LABEL
from ..config import (
    DEFAULTS, FOLDER_CHOICES, MAX_PARALLEL_LIMIT, load_config, normalize,
)
from ..engine.constants import ARIA2_MAX_PER_FILE
from ..engine.errors import UnsafePathError
from ..engine.paths import validate_output_dir
from ..theme import DEFAULT_THEME, LUMA_DAY, LUMA_NIGHT
from ..widgets.brandbar import BrandBar
from ..widgets.sizing import SizeAware

THEME_CHOICES = [
    (NIGHT_LABEL, LUMA_NIGHT.name),
    (DAY_LABEL, LUMA_DAY.name),
]

QUALITY_LABELS = [
    ("360p - smallest files", "360"),
    ("480p - good balance", "480"),
    ("720p - sharper, bigger files", "720"),
    ("Best available", "best"),
]

FOLDER_LABELS = [
    ("All in one folder", "none"),
    ("A folder for each day", "date"),
    ("A folder for each playlist", "playlist"),
]


class SettingsScreen(SizeAware, Screen):
    BINDINGS = [
        Binding("escape", "close", "Back"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._config = {}

    def compose(self) -> ComposeResult:
        yield BrandBar(id="brand")
        yield Static("Settings", id="settings-title")
        with VerticalScroll(id="settings-body"):
            with Vertical(classes="setting"):
                yield Label("Save downloads to")
                yield Input(id="set-folder", placeholder="Choose a folder")
                yield Static("", id="folder-error", classes="field-error")

            with Vertical(classes="setting"):
                yield Label("Organise downloads")
                yield Select(FOLDER_LABELS, id="set-folders",
                             allow_blank=False)

            with Vertical(classes="setting"):
                yield Label("Video quality")
                yield Select(QUALITY_LABELS, id="set-quality",
                             allow_blank=False)

            with Horizontal(classes="setting setting-switch"):
                yield Switch(id="set-ask-quality")
                yield Label("Ask me which quality, for every link")

            with Vertical(classes="setting"):
                yield Label(f"Videos at once (1-{MAX_PARALLEL_LIMIT})")
                yield Input(id="set-parallel", type="integer")
                yield Static("", id="parallel-error", classes="field-error")

            with Vertical(classes="setting"):
                yield Label(
                    f"Connections per video (1-{ARIA2_MAX_PER_FILE}) - "
                    f"higher is usually faster"
                )
                yield Input(id="set-conns", type="integer")
                yield Static("", id="conns-error", classes="field-error")

            with Vertical(classes="setting"):
                yield Label("Appearance")
                yield Select(THEME_CHOICES, id="set-theme", allow_blank=False)

            with Horizontal(classes="setting setting-switch"):
                yield Switch(id="set-archive")
                yield Label("Skip videos I've already downloaded")

        yield Static("", id="settings-message")
        with Horizontal(id="settings-actions"):
            yield Button("Save", variant="primary", id="settings-save")
            yield Button("Cancel", id="settings-cancel")
            yield Button("Reset to defaults", id="settings-reset")
        yield Footer()

    def on_mount(self) -> None:
        self.apply_size_classes()
        self._config = dict(getattr(self.app, "config", None) or load_config())
        self._fill(self._config)
        self.query_one("#set-folder", Input).focus()

    def _fill(self, cfg):
        self.query_one("#set-folder", Input).value = str(cfg["output_dir"])
        self.query_one("#set-parallel", Input).value = str(cfg["max_parallel"])
        self.query_one("#set-conns", Input).value = str(cfg["conns_per_file"])
        self.query_one("#set-archive", Switch).value = bool(cfg["archive"])
        self.query_one("#set-ask-quality", Switch).value = bool(
            cfg.get("ask_quality", False)
        )

        self._set_select("#set-folders", cfg["folders"], FOLDER_CHOICES[0])
        self._set_select("#set-quality", cfg["quality"], "480")
        known = [v for _, v in THEME_CHOICES]
        self._set_select("#set-theme", cfg["theme"],
                         DEFAULT_THEME if cfg["theme"] not in known
                         else cfg["theme"])
        self._clear_errors()

    def _set_select(self, selector, value, fallback):
        widget = self.query_one(selector, Select)
        try:
            widget.value = value
        except Exception:
            widget.value = fallback

    def _clear_errors(self):
        for field in ("#folder-error", "#parallel-error", "#conns-error"):
            self.query_one(field, Static).update("")
        for field in ("#set-folder", "#set-parallel", "#set-conns"):
            self.query_one(field, Input).remove_class("-invalid")
        self.query_one("#settings-message", Static).update("")

    def _collect(self):
        errors = {}

        folder_raw = self.query_one("#set-folder", Input).value.strip()
        try:
            folder = validate_output_dir(folder_raw)
        except UnsafePathError as exc:
            folder = None
            errors["folder"] = exc.user_message

        parallel_raw = self.query_one("#set-parallel", Input).value.strip()
        try:
            parallel = int(parallel_raw)
            if not 1 <= parallel <= MAX_PARALLEL_LIMIT:
                raise ValueError
        except ValueError:
            parallel = None
            errors["parallel"] = (
                f"Enter a whole number from 1 to {MAX_PARALLEL_LIMIT}."
            )

        conns_raw = self.query_one("#set-conns", Input).value.strip()
        try:
            conns = int(conns_raw)
            if not 1 <= conns <= ARIA2_MAX_PER_FILE:
                raise ValueError
        except ValueError:
            conns = None
            errors["conns"] = (
                f"Enter a whole number from 1 to {ARIA2_MAX_PER_FILE}."
            )

        config = dict(self._config)
        config.update({
            "output_dir": folder,
            "folders": self.query_one("#set-folders", Select).value,
            "quality": self.query_one("#set-quality", Select).value,
            "max_parallel": parallel,
            "conns_per_file": conns,
            "theme": self.query_one("#set-theme", Select).value,
            "archive": self.query_one("#set-archive", Switch).value,
            "ask_quality": self.query_one("#set-ask-quality", Switch).value,
        })
        return config, errors

    def action_save(self) -> None:
        self._save()

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save":
            self._save()
        elif event.button.id == "settings-cancel":
            self.dismiss()
        elif event.button.id == "settings-reset":
            self._fill(normalize(dict(DEFAULTS)))
            self.query_one("#settings-message", Static).update(
                "Defaults restored - choose Save to keep them."
            )

    def _save(self) -> None:
        self._clear_errors()
        config, errors = self._collect()

        if errors:
            for field, message in errors.items():
                self.query_one(f"#{field}-error", Static).update(message)
                self.query_one(f"#set-{field}", Input).add_class("-invalid")
            self.query_one("#settings-message", Static).update(
                "Nothing was saved - please fix the highlighted boxes."
            )
            return

        if self.app.update_config(config):
            self._config = dict(self.app.config)
            self.app.notify("Settings saved.")
            self.dismiss()
        else:
            self.query_one("#settings-message", Static).update(
                "Luma could not save your settings. Check the folder is "
                "writable and try again."
            )
