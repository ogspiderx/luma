"""Asking which quality to use, when the person has chosen to be asked."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, Switch


class QualityScreen(ModalScreen):
    """Offers the qualities a link is actually available in.

    Dismisses with {"height": "720", "apply_all": False}, or None if the
    person skipped this link.

    When there are more links behind this one it says so, and offers to use
    the same answer for all of them -- otherwise a pasted list of thirty
    videos would mean thirty questions.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Skip"),
    ]

    def __init__(self, title, choices, remaining=0, **kwargs):
        super().__init__(**kwargs)
        self._title = title or "this video"
        self._choices = choices or []
        self._remaining = max(0, int(remaining or 0))

    def compose(self) -> ComposeResult:
        with Vertical(id="quality-box"):
            yield Static("Choose a quality", id="quality-heading")
            yield Static(self._title, id="quality-title")
            if self._remaining:
                more = self._remaining
                yield Static(
                    f"{more} more link{'s' if more != 1 else ''} after this "
                    f"one.",
                    id="quality-count",
                )
            with VerticalScroll(id="quality-options"):
                for index, choice in enumerate(self._choices):
                    yield Button(
                        self._describe(choice),
                        id=f"quality-{choice['height']}",
                        variant="primary" if index == 0 else "default",
                        classes="quality-option",
                    )
            if self._remaining:
                with Horizontal(id="quality-rest"):
                    yield Switch(value=False, id="quality-apply-all")
                    yield Label("Use my answer for the rest as well")
            with Horizontal(id="quality-actions"):
                yield Button("Skip this one", id="quality-cancel")

    @staticmethod
    def _describe(choice):
        note = choice.get("note")
        return f"{choice['label']}   {note}" if note else choice["label"]

    def on_mount(self) -> None:
        first = self.query(".quality-option")
        if first:
            first[0].focus()

    def _apply_all(self):
        """Whether the answer should stand for the links still to come."""
        try:
            return bool(self.query_one("#quality-apply-all", Switch).value)
        except Exception:                              # noqa: BLE001
            return False                               # not offered this time

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "quality-cancel":
            self.dismiss(None)
            return
        if event.button.id and event.button.id.startswith("quality-"):
            self.dismiss({
                "height": event.button.id.split("-", 1)[1],
                "apply_all": self._apply_all(),
            })
