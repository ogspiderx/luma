"""History: what Luma downloaded, and what it could not."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import (
    Button, DataTable, Footer, Static, TabbedContent, TabPane,
)

from ..widgets.brandbar import BrandBar
from ..widgets.sizing import SizeAware
from ..history import (
    human_size, human_when, recent_downloads, recent_failures,
)


class HistoryScreen(SizeAware, Screen):
    """Past downloads and anything that went wrong, read fresh from disk."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, history_path=None, errors_path=None, **kwargs):
        super().__init__(**kwargs)
        self._history_path = history_path
        self._errors_path = errors_path

    def compose(self) -> ComposeResult:
        yield BrandBar(id="brand")
        yield Static("History", id="history-title")
        with TabbedContent(id="history-tabs"):
            with TabPane("Downloads", id="tab-downloads"):
                yield DataTable(id="history-table", cursor_type="row",
                                zebra_stripes=True)
                yield Static("", id="history-empty", classes="empty-note")
            with TabPane("Problems", id="tab-problems"):
                yield DataTable(id="errors-table", cursor_type="row",
                                zebra_stripes=True)
                yield Static("", id="errors-empty", classes="empty-note")
        yield Button("Back", id="history-back")
        yield Footer()

    def on_mount(self) -> None:
        self.apply_size_classes()
        self.query_one("#history-table", DataTable).add_columns(
            "What", "When", "Size", "Quality"
        )
        self.query_one("#errors-table", DataTable).add_columns(
            "Link", "What happened", "When"
        )
        self._load()

    # -- loading ---------------------------------------------------------
    def _load(self) -> None:
        """Read both records from disk each time, so the screen is never stale."""
        downloads = (
            recent_downloads(path=self._history_path) if self._history_path
            else recent_downloads()
        )
        failures = (
            recent_failures(path=self._errors_path) if self._errors_path
            else recent_failures()
        )

        table = self.query_one("#history-table", DataTable)
        table.clear()
        for row in downloads:
            quality = row.get("quality") or "-"
            if quality not in ("-", "best"):
                quality = f"{quality}p"
            elif quality == "best":
                quality = "Best"
            table.add_row(
                row.get("title") or "Unknown video",
                human_when(row.get("when")),
                human_size(row.get("size")),
                quality,
            )
        self.query_one("#history-empty", Static).update(
            "" if downloads else "Nothing downloaded yet."
        )

        errors = self.query_one("#errors-table", DataTable)
        errors.clear()
        for row in failures:
            errors.add_row(
                row.get("url") or "-",
                row.get("reason") or "The download did not finish.",
                human_when(row.get("when")),
            )
        self.query_one("#errors-empty", Static).update(
            "" if failures else "No problems recorded."
        )

    # -- actions ---------------------------------------------------------
    def action_refresh(self) -> None:
        self._load()

    def action_close(self) -> None:
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "history-back":
            self.dismiss()
