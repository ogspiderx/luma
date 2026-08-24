import re

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, ProgressBar, Static

from ..engine.constants import human

FILL_SECONDS = 0.3

HIGHLIGHT_SECONDS = 1.2

_RATE = re.compile(r"([\d.]+)\s*([KMGT]?)i?B/s", re.IGNORECASE)
_SCALE = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}


def _compact_size(size_bytes):
    if not size_bytes:
        return ""
    value = float(size_bytes)
    for unit in ("KB", "MB", "GB"):
        value /= 1024
        if value < 1024 or unit == "GB":
            return f"{value:.1f}{unit}" if value < 10 else f"{value:.0f}{unit}"
    return ""


def rate_to_bytes(text):
    match = _RATE.search(text or "")
    if not match:
        return 0.0
    try:
        return float(match.group(1)) * _SCALE.get(match.group(2).upper(), 1)
    except ValueError:
        return 0.0


class QualityChip(Button):
    BINDINGS = [
        Binding("left", "chip_previous", "Previous", show=False),
        Binding("right", "chip_next", "Next", show=False),
    ]

    def __init__(self, label, height, **kwargs):
        super().__init__(label, **kwargs)
        self.height_value = height

    def _row_chips(self):
        parent = self.parent
        if parent is None:
            return [self]
        chips = [w for w in parent.children if isinstance(w, QualityChip)]
        return chips or [self]

    def _step(self, delta):
        chips = self._row_chips()
        try:
            here = chips.index(self)
        except ValueError:
            return
        chips[(here + delta) % len(chips)].focus()

    def action_chip_previous(self) -> None:
        self._step(-1)

    def action_chip_next(self) -> None:
        self._step(1)


class DownloadRow(Widget):
    class RemoveRequested(Message):
        def __init__(self, row):
            super().__init__()
            self.row = row

    class QualityChosen(Message):
        def __init__(self, row, height):
            super().__init__()
            self.row = row
            self.height = height

    def __init__(self, tag, url, **kwargs):
        super().__init__(**kwargs)
        self._tag = tag
        self.url = url
        self._title = ""
        self._finished = False
        self._ok = False
        self._started = False
        self._speed_bytes = 0.0
        self._percent = 0.0
        self._detail = "Waiting..."
        self.sequence = 0
        self._choices = []

    @property
    def tag(self):
        return self._tag

    @property
    def display_title(self):
        return self._title or "Getting details..."

    @property
    def title_text(self):
        return self._title or ""

    @property
    def finished(self):
        return self._finished

    @property
    def succeeded(self):
        return self._finished and self._ok

    @property
    def started(self):
        return self._started

    @property
    def choosing(self):
        return bool(self._choices)

    @property
    def percent(self):
        return 100.0 if self.succeeded else self._percent

    @property
    def speed_bytes(self):
        return 0.0 if self._finished else self._speed_bytes

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="row-main"):
                yield Static(self.display_title, classes="row-title")
                yield ProgressBar(
                    total=100, show_eta=False, show_percentage=True,
                )
                yield Static(self._detail, classes="row-detail")
            yield Button("✕", classes="row-remove", tooltip="Remove")

    def _bar(self):
        try:
            return self.query_one(ProgressBar)
        except Exception:
            return None

    def _write(self, selector, text):
        try:
            self.query_one(selector, Static).update(text)
        except Exception:
            pass

    def set_title(self, title):
        if not title:
            return
        self._title = title
        self._write(".row-title", title)

    def set_detail(self, text):
        self._detail = text
        self._write(".row-detail", text)

    def set_waiting(self, position=None):
        if self._finished or self._started or self._choices:
            return
        if position == 1:
            self.set_detail("Next up")
        elif position:
            self.set_detail(f"Waiting - number {position} in the queue")
        else:
            self.set_detail("Waiting...")

    def set_checking(self):
        self.set_detail("Checking what it comes in...")

    def offer_choices(self, choices):
        self._choices = list(choices or [])
        if not self._choices:
            return
        self.add_class("-choosing")
        self.set_detail("Which quality?")
        try:
            holder = self.query_one(".row-main")
        except Exception:
            return
        strip = Horizontal(classes="row-choices")
        holder.mount(strip)
        strip.mount_all([
            QualityChip(self._chip_label(choice), str(choice["height"]),
                        classes="quality-chip")
            for choice in self._choices
        ] + [QualityChip("Skip", "", classes="quality-chip -skip")])

    @staticmethod
    def _chip_label(choice):
        size = _compact_size(choice.get("filesize") or 0)
        return f"{choice['label']} {size}".strip() if size else choice["label"]

    def clear_choices(self):
        self._choices = []
        self.remove_class("-choosing")
        for strip in self.query(".row-choices"):
            strip.remove()

    def focus_choices(self):
        chips = list(self.query(QualityChip))
        if chips:
            chips[0].focus()
            return True
        return False

    def set_progress(self, parsed):
        if self._finished:
            return
        if self._choices:
            self.clear_choices()
        self._started = True
        percent = max(0.0, min(100.0, float(parsed.get("percent") or 0.0)))
        self._percent = percent
        bar = self._bar()
        if bar is not None:
            bar.animate("progress", value=percent, duration=FILL_SECONDS)

        self._speed_bytes = rate_to_bytes(parsed.get("speed"))
        self.set_detail(self._describe(parsed))

    @staticmethod
    def _describe(parsed):
        bits = []
        kind = parsed.get("kind")
        if kind:
            bits.append(kind)
        if parsed.get("speed"):
            bits.append(str(parsed["speed"]))

        done = parsed.get("done_bytes") or 0
        total = parsed.get("total_bytes") or 0
        if total:
            bits.append(f"{human(done)} of {human(total)}")
        elif done:
            bits.append(human(done))

        eta = parsed.get("eta")
        if eta and eta not in ("0s", "00:00"):
            bits.append(f"{eta} left")
        return "   ".join(bits) if bits else "Starting..."

    def finish(self, ok, message):
        self.clear_choices()
        self._finished = True
        self._ok = bool(ok)
        self._started = True
        self._speed_bytes = 0.0
        bar = self._bar()
        if ok:
            self._percent = 100.0
            if bar is not None:
                bar.update(progress=100)
        self.add_class("-done" if ok else "-failed")
        self.set_detail(self.url if ok else (message or "Did not finish."))

        self.add_class("-just-finished")
        self.set_timer(
            HIGHLIGHT_SECONDS,
            lambda: self.remove_class("-just-finished"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button
        if isinstance(button, QualityChip):
            event.stop()
            if button.height_value:
                self.post_message(self.QualityChosen(self, button.height_value))
            else:
                self.post_message(self.RemoveRequested(self))
            return
        if "row-remove" in button.classes:
            event.stop()
            self.post_message(self.RemoveRequested(self))
