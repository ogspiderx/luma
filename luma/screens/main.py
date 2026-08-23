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

from ..config import resolve_output_dir
from ..engine import download as dl
from ..engine.callbacks import EngineCallbacks
from ..engine.constants import DEFAULT_MAX_PARALLEL, DEFAULT_QUALITY, human
from ..engine.errors import LumaError
from ..engine.inputs import (
    expand_playlists,
    gather_inputs,
    split_pasted_text,
)
from ..engine.plan import compute_plan, default_plan, describe_plan
from ..engine.speedtest import measure_bandwidth
from ..engine.tools import ensure_tools
from ..history import record_results, recent_downloads
from ..locations import DEFAULT_DOWNLOAD_DIR
from ..widgets.download_row import DownloadRow


class MainScreen(Screen):
    """The screen the user lands on."""

    BINDINGS = [
        Binding("ctrl+s", "open_settings", "Settings"),
        Binding("ctrl+h", "open_history", "History"),
        Binding("ctrl+x", "stop_downloads", "Stop"),
        Binding("ctrl+l", "clear_finished", "Clear done"),
        Binding("pageup", "scroll_list_up", "Scroll up", show=False),
        Binding("pagedown", "scroll_list_down", "Scroll down", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rows = {}
        self._download_active = False
        self._speed_timer = None

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
                yield Static("Getting ready...", id="status-line")
                yield Button("Stop", variant="error", id="stop-btn")
                yield Button("Clear done", id="clear-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#stop-btn", Button).display = False
        self.query_one("#clear-btn", Button).display = False
        self.query_one("#url-input", Input).focus()
        # Tools, the update check and the speed reading are all done once,
        # here, rather than in front of every download.
        if getattr(self.app, "auto_prepare", True):
            self._set_busy(True)
            self._prepare_worker()
        else:
            self._set_busy(False)
            self._set_status("Ready.")

    def _set_busy(self, busy):
        """Show or hide the spinner. Nothing animates when idle."""
        self.query_one("#busy", LoadingIndicator).display = bool(busy)

    # -- settings the download runs with ---------------------------------
    def _settings(self):
        """Where downloads go and how they run, taken from the user's settings."""
        config = getattr(self.app, "config", None) or {}
        try:
            output_dir = resolve_output_dir(config)
        except LumaError:
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
        elif event.button.id == "stop-btn":
            self.action_stop_downloads()
        elif event.button.id == "clear-btn":
            self.action_clear_finished()

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

    def action_scroll_list_up(self) -> None:
        self.query_one("#downloads", VerticalScroll).scroll_page_up()

    def action_scroll_list_down(self) -> None:
        self.query_one("#downloads", VerticalScroll).scroll_page_down()

    def action_clear_finished(self) -> None:
        """Take finished downloads out of the list, leaving active ones."""
        removed = 0
        for tag, row in list(self._rows.items()):
            if row.finished:
                row.remove()
                del self._rows[tag]
                removed += 1
        self._refresh_buttons()
        if removed:
            self.app.notify(
                f"Cleared {removed} finished "
                f"download{'s' if removed != 1 else ''}."
            )
        else:
            self.app.notify("Nothing finished to clear yet.",
                            severity="warning")

    def _refresh_buttons(self):
        """Stop is offered while running; Clear only when there is idle work."""
        finished = any(row.finished for row in self._rows.values())
        self.query_one("#stop-btn", Button).display = self._download_active
        self.query_one("#clear-btn", Button).display = (
            bool(finished) and not self._download_active
        )

    # -- one-time preparation --------------------------------------------
    @work(thread=True, exclusive=True, group="prepare")
    def _prepare_worker(self) -> None:
        """Set up the tools and read the connection speed, once at startup."""
        app = self.app

        def ui(fn, *args):
            try:
                app.call_from_thread(fn, *args)
            except Exception:
                pass

        callbacks = EngineCallbacks(
            on_status=lambda m: ui(self._set_status, m),
            on_tool_progress=lambda desc, got, total: ui(
                self._set_status,
                f"Getting things ready - {desc} "
                f"({got * 100 // total if total else 0}%)",
            ),
        )
        try:
            app.tools = ensure_tools(callbacks)
        except LumaError as exc:
            ui(self._set_status, exc.user_message)
            ui(self._set_busy, False)
            return
        except Exception:                              # noqa: BLE001
            ui(self._set_status, "Could not get things ready.")
            ui(self._set_busy, False)
            return

        config = getattr(app, "config", None) or {}
        if not config.get("skip_speedtest", False):
            try:
                app.bandwidth = measure_bandwidth(callbacks)
            except Exception:                          # noqa: BLE001
                app.bandwidth = None

        ui(self._set_busy, False)
        ui(self._set_status, "Ready.")

    # -- starting a download ---------------------------------------------
    def _known_links(self):
        """Links already in the list, so the same one is not queued twice."""
        return {row.url for row in self._rows.values()}

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

        urls, notices = self._filter_duplicates(urls)
        for notice in notices:
            self.app.notify(notice, severity="warning")
        if not urls:
            if not rejected and not notices:
                self.app.notify("Nothing to download.", severity="warning")
            return

        box.value = ""
        self._download_active = True
        self.query_one("#download-btn", Button).disabled = True
        self._refresh_buttons()      # Stop becomes available straight away
        self._set_busy(True)
        dl.reset_cancel()
        self._start_speed_readout()
        self._download_worker(urls)

    def _filter_duplicates(self, urls):
        """Drop links already queued or already downloaded, and say so."""
        notices = []
        seen, unique = set(), []
        repeats = 0
        for url in urls:
            if url in seen:
                repeats += 1
                continue
            seen.add(url)
            unique.append(url)
        if repeats:
            notices.append(
                f"Ignored {repeats} repeated "
                f"link{'s' if repeats != 1 else ''} in what you pasted."
            )

        already_listed = self._known_links()
        queued = [u for u in unique if u not in already_listed]
        skipped = len(unique) - len(queued)
        if skipped:
            notices.append(
                f"{skipped} link{'s are' if skipped != 1 else ' is'} already "
                f"in the list below."
            )

        # Only worth mentioning when Luma would not skip them itself.
        config = getattr(self.app, "config", None) or {}
        if queued and not config.get("archive", False):
            try:
                done = {row.get("url") for row in recent_downloads(limit=500)}
            except Exception:                          # noqa: BLE001
                done = set()
            repeats_of_done = [u for u in queued if u in done]
            if repeats_of_done:
                count = len(repeats_of_done)
                notices.append(
                    f"{count} of these {'were' if count != 1 else 'was'} "
                    f"downloaded before - downloading again."
                )
        return queued, notices

    # -- live overall speed ----------------------------------------------
    def _start_speed_readout(self):
        if self._speed_timer is None:
            self._speed_timer = self.set_interval(1.0, self._tick_speed)

    def _stop_speed_readout(self):
        if self._speed_timer is not None:
            self._speed_timer.stop()
            self._speed_timer = None

    def _tick_speed(self):
        """Report the real combined rate, measured from the downloads."""
        if not self._download_active:
            return
        total = sum(row.speed_bytes for row in self._rows.values())
        active = sum(1 for row in self._rows.values() if not row.finished)
        if total > 0:
            self._set_status(
                f"Downloading {active} of {len(self._rows)} - "
                f"{human(total)}/s altogether"
            )

    # -- UI updates (always called on the UI thread) ---------------------
    def _set_status(self, text):
        self.query_one("#status-line", Static).update(text)

    def _set_plan(self, text):
        self.query_one("#plan-panel", Static).update(text)

    def _add_row(self, tag, url):
        row = DownloadRow(tag, url)
        self._rows[tag] = row
        self.query_one("#downloads", VerticalScroll).mount(row)

    def _row_title(self, tag, title):
        row = self._rows.get(tag)
        if row is not None:
            row.set_title(title)

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
        self._refresh_buttons()

    def _finished(self, ok_count, fail_count, output_dir):
        self._download_active = False
        self._stop_speed_readout()
        self._set_busy(False)
        self.query_one("#download-btn", Button).disabled = False
        self._refresh_buttons()
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
        """Run the whole download on a background thread."""
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
            on_video_title=lambda tag, title: ui(self._row_title, tag, title),
            on_video_status=lambda tag, m: ui(self._row_detail, tag, m),
            on_video_progress=lambda tag, p: ui(self._row_progress, tag, p),
            on_video_done=lambda tag, url, ok, reason, path: ui(
                self._row_finish, tag, ok,
                ("Saved: " + os.path.basename(path)) if ok and path
                else ("Saved." if ok else reason),
            ),
        )

        try:
            # Prepared once at startup; only fall back if that had not
            # finished yet or did not succeed.
            tools = getattr(app, "tools", None)
            if not tools:
                ui(self._set_status, "Getting things ready...")
                tools = ensure_tools(callbacks)
                app.tools = tools

            ui(self._set_status, "Checking the link...")
            videos = expand_playlists(tools["yt-dlp"], urls, callbacks)
            if not videos:
                ui(self._set_status, "Nothing to download.")
                ui(self._finished, 0, 0, cfg["output_dir"])
                return

            # Number rows from what is already listed, so a second batch
            # continues the count instead of restarting it.
            offset = len(self._rows)
            total = len(videos)
            tags = []
            for i, url in enumerate(videos, 1):
                tag = f"{offset + i}"
                tags.append(tag)
                ui(self._add_row, tag, url)

            # The connection was read once at startup; reuse that rather than
            # spending seconds on it before every download.
            reading = getattr(app, "bandwidth", None)
            if cfg["run_speedtest"] and reading:
                single, line, rtt = reading
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
            ui(self._set_busy, False)

            results = dl.run_downloads(
                tools, videos, plan, cfg["output_dir"], cfg["quality"],
                downloader="aria2c", archive=cfg["archive"],
                callbacks=callbacks, tags=tags,
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
        """Write the outcome of each video to the history and error records."""
        try:
            record_results(results, quality=quality)
        except Exception:                              # noqa: BLE001
            pass
