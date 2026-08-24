"""Asking which quality to use, when the person has chosen to be asked."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class QualityScreen(ModalScreen):
    """Offers the qualities a link is actually available in.

    Dismisses with the chosen height as a string ("720"), or None if the
    person backed out.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, title, choices, **kwargs):
        super().__init__(**kwargs)
        self._title = title or "this video"
        self._choices = choices or []

    def compose(self) -> ComposeResult:
        with Vertical(id="quality-box"):
            yield Static("Choose a quality", id="quality-heading")
            yield Static(self._title, id="quality-title")
            with VerticalScroll(id="quality-options"):
                for index, choice in enumerate(self._choices):
                    yield Button(
                        self._describe(choice),
                        id=f"quality-{choice['height']}",
                        variant="primary" if index == 0 else "default",
                        classes="quality-option",
                    )
            with Horizontal(id="quality-actions"):
                yield Button("Cancel", id="quality-cancel")

    @staticmethod
    def _describe(choice):
        note = choice.get("note")
        return f"{choice['label']}   {note}" if note else choice["label"]

    def on_mount(self) -> None:
        first = self.query(".quality-option")
        if first:
            first[0].focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "quality-cancel":
            self.dismiss(None)
            return
        if event.button.id and event.button.id.startswith("quality-"):
            self.dismiss(event.button.id.split("-", 1)[1])
