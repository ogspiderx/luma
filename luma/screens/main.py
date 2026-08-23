"""Luma's main screen: paste a link, start a download, watch it happen."""

import os

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Header, Input, LoadingIndicator, Static,
)

from ..engine import download as dl
from ..engine.callbacks import EngineCallbacks
from ..engine.constants import DEFAULT_MAX_PARALLEL, DEFAULT_QUALITY
from ..engine.errors import LumaError
from ..engine.inputs import (
    expand_playlists,
    gather_inputs,
    split_pasted_text,
)
from ..engine.plan import compute_plan, default_plan, describe_plan
from ..engine.speedtest import measure_bandwidth
from ..engine.tools import ensure_tools
from ..config import resolve_output_dir
from ..history import record_results
from ..locations import DEFAULT_DOWNLOAD_DIR
from ..widgets.download_row import DownloadRow


class MainScreen(Screen):
    """The screen the user lands on."""

    BINDINGS = [
        Binding("ctrl+s", "open_settings", "Settings"),
        Binding("ctrl+h", "open_history", "History"),
        Binding("ctrl+x", "stop_downloads", "Stop"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rows = {}
        self._download_active = False

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
            with Horizontal(id="status-row"):
                yield LoadingIndicator(id="busy")
                yield Static("Ready.", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        # The spinner only exists while Luma is actually busy.
        self.query_one("#busy", LoadingIndicator).display = False
        self.query_one("#url-input", Input).focus()

    def _set_busy(self, busy):
        """Show or hide the spinner. Nothing animates when idle."""
        self.query_one("#busy", LoadingIndicator).display = bool(busy)

    # -- settings the download runs with ---------------------------------
    def _settings(self):
        """Where downloads go and how they run, taken from the user's settings.

        The download folder is resolved through the settings layer so the
        folder-grouping choice is honoured and the location is checked before
        anything is written to it.
        """
        config = getattr(self.app, "config", None) or {}
        try:
            output_dir = resolve_output_dir(config)
        except LumaError:
            # Fall back to the built-in folder rather than refusing to run.
            output_dir = DEFAULT_DOWNLOAD_DIR
        return {
            "output_dir": output_dir,
            "quality": config.get("quality") or DEFAULT_QUALITY,
            "max_parallel": config.get("max_parallel") or DEFAULT_MAX_PARALLEL,
            "conns_per_file": config.get("conns_per_file"),
            "archive": bool(config.get("archive", False)),
            "run_speedtest": not config.get("skip_speedtest", False),
        }

    # -- user actions ----------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "download-btn":
            self._start()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "url-input":
            self._start()

    def action_stop_downloads(self) -> None:
        if self._download_active:
            dl.request_cancel()
            self._set_status("Stopping...")

    def action_open_settings(self) -> None:
        self.app.action_open_settings()

    def action_open_history(self) -> None:
        self.app.action_open_history()

    def _start(self) -> None:
        if self._download_active:
            self.app.notify("A download is already running.",
                            severity="warning")
            return

        box = self.query_one("#url-input", Input)
        text = box.value.strip()
        if not text:
            self.app.notify("Paste a YouTube link first.", severity="warning")
            box.focus()
            return

        urls, rejected = gather_inputs(split_pasted_text(text))
        for _, reason in rejected:
            self.app.notify(reason, severity="error")
        if not urls:
            return

        box.value = ""
        self._clear_rows()
        self._download_active = True
        self.query_one("#download-btn", Button).disabled = True
        self._set_busy(True)
        dl.reset_cancel()
        self._download_worker(urls)

    # -- UI updates (always called on the UI thread) ---------------------
    def _set_status(self, text):
        self.query_one("#status-line", Static).update(text)

    def _set_plan(self, text):
        self.query_one("#plan-panel", Static).update(text)

    def _clear_rows(self):
        self._rows.clear()
        self.query_one("#downloads", VerticalScroll).remove_children()

    def _add_row(self, tag, label):
        row = DownloadRow(tag, label)
        self._rows[tag] = row
        self.query_one("#downloads", VerticalScroll).mount(row)

    def _row_progress(self, tag, parsed):
        row = self._rows.get(tag)
        if row is not None:
            row.set_progress(parsed)

    def _row_detail(self, tag, text):
        row = self._rows.get(tag)
        if row is not None:
            row.set_detail(text)

    def _row_finish(self, tag, ok, message):
        row = self._rows.get(tag)
        if row is not None:
            row.finish(ok, message)

    def _finished(self, ok_count, fail_count, output_dir):
        self._download_active = False
        self._set_busy(False)
        self.query_one("#download-btn", Button).disabled = False
        if fail_count and not ok_count:
            self._set_status("Nothing downloaded. See the messages above.")
        elif fail_count:
            self._set_status(
                f"Finished: {ok_count} saved, {fail_count} did not work. "
                f"Saved in {output_dir}"
            )
        else:
            self._set_status(f"All done. Saved in {output_dir}")
        self.query_one("#url-input", Input).focus()

    # -- the worker ------------------------------------------------------
    @work(thread=True, exclusive=True, group="download")
    def _download_worker(self, urls) -> None:
        """Run the whole download on a background thread.

        The engine blocks, so it must not run on the UI thread. Every update
        is marshalled back with call_from_thread.
        """
        app = self.app
        cfg = self._settings()

        def ui(fn, *args):
            try:
                app.call_from_thread(fn, *args)
            except Exception:
                pass  # app is shutting down

        callbacks = EngineCallbacks(
            on_status=lambda m: ui(self._set_status, m),
            on_tool_progress=lambda desc, got, total: ui(
                self._set_status,
                f"Getting things ready - {desc} "
                f"({got * 100 // total if total else 0}%)",
            ),
            on_video_status=lambda tag, m: ui(self._row_detail, tag, m),
            on_video_progress=lambda tag, p: ui(self._row_progress, tag, p),
            on_video_done=lambda tag, url, ok, reason, path: ui(
                self._row_finish, tag, ok,
                ("Saved: " + os.path.basename(path)) if ok and path
                else ("Saved." if ok else reason),
            ),
        )

        try:
            ui(self._set_status, "Getting things ready...")
            tools = ensure_tools(callbacks)

            ui(self._set_status, "Checking the link...")
            videos = expand_playlists(tools["yt-dlp"], urls, callbacks)
            if not videos:
                ui(self._set_status, "Nothing to download.")
                ui(self._finished, 0, 0, cfg["output_dir"])
                return

            total = len(videos)
            for i, url in enumerate(videos, 1):
                ui(self._add_row, f"{i}/{total}", f"{i}. {url}")

            if cfg["run_speedtest"]:
                single, line, rtt = measure_bandwidth(callbacks)
                plan = compute_plan(single, line, rtt, total,
                                    cfg["max_parallel"])
            else:
                plan = default_plan(total, cfg["max_parallel"])

            if cfg["conns_per_file"]:
                from ..engine.plan import apply_overrides
                plan = apply_overrides(
                    plan, conns_per_file=cfg["conns_per_file"],
                    num_urls=total,
                )

            ui(self._set_plan, "   ".join(describe_plan(plan)))
            ui(self._set_status,
               f"Downloading {total} video{'s' if total > 1 else ''}...")
            # The progress bars take over as the sign of life from here, so
            # the spinner stops rather than adding motion beside them.
            ui(self._set_busy, False)

            results = dl.run_downloads(
                tools, videos, plan, cfg["output_dir"], cfg["quality"],
                downloader="aria2c", archive=cfg["archive"],
                callbacks=callbacks,
            )

            ok = sum(1 for r in results if r[1])
            self._record_results(results, cfg["quality"])
            ui(self._finished, ok, len(results) - ok, cfg["output_dir"])

        except LumaError as exc:
            ui(self._set_status, exc.user_message)
            ui(self._finished, 0, 0, cfg["output_dir"])
        except Exception:                                   # noqa: BLE001
            ui(self._set_status,
               "Something went wrong. Please try again.")
            ui(self._finished, 0, 0, cfg["output_dir"])

    def _record_results(self, results, quality=None):
        """Write the outcome of each video to the history and error records.

        `quality` is the setting the run actually used, so the record matches
        what was downloaded. Recording must never be able to sink a download
        that already worked, so any problem here is swallowed.
        """
        try:
            record_results(results, quality=quality)
        except Exception:                              # noqa: BLE001
            pass
