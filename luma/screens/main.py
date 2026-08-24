import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Input, LoadingIndicator, Select, Static,
)

from ..branding import LINK_PLACEHOLDER
from ..config import resolve_output_dir
from ..engine import download as dl
from ..engine.callbacks import EngineCallbacks
from ..engine.constants import DEFAULT_MAX_PARALLEL, DEFAULT_QUALITY, human
from ..engine.errors import LumaError
from ..engine.formats import available_qualities
from ..engine.inputs import (
    expand_playlists,
    gather_inputs,
    split_pasted_text,
)
from ..engine.plan import apply_overrides, compute_plan, default_plan, describe_plan
from ..engine.speedtest import measure_bandwidth
from ..engine.tools import ensure_tools
from ..history import record_results, recent_downloads
from ..locations import DEFAULT_DOWNLOAD_DIR
from ..widgets.brandbar import BrandBar
from ..widgets.download_row import DownloadRow
from ..widgets.sizing import SizeAware

PROBE_AT_ONCE = 4

SORT_OPTIONS = [
    ("Order added", "added"),
    ("Unfinished first", "unfinished"),
    ("Finished first", "finished"),
    ("Furthest along", "progress"),
    ("Name A-Z", "name"),
]


class MainScreen(SizeAware, Screen):
    BINDINGS = [
        Binding("ctrl+s", "open_settings", "Settings", priority=True),
        Binding("ctrl+h", "open_history", "History", priority=True),
        Binding("ctrl+a", "same_for_all", "Same for all", priority=True),
        Binding("ctrl+x", "stop_downloads", "Stop", priority=True),
        Binding("ctrl+l", "clear_finished", "Clear done", priority=True),
        Binding("pageup", "scroll_list_up", "Scroll up", show=False),
        Binding("pagedown", "scroll_list_down", "Scroll down", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rows = {}
        self._queue = []
        self._queue_lock = threading.Lock()
        self._download_active = False
        self._speed_timer = None
        self._sequence = 0
        self._sort_mode = "added"
        self._checking = set()
        self._awaiting = set()
        self._last_choice = None
        self._plan_note = ""

    def compose(self) -> ComposeResult:
        yield BrandBar(id="brand")
        with Vertical(id="main-body"):
            with Horizontal(id="link-row"):
                yield Input(placeholder=LINK_PLACEHOLDER, id="url-input")
                yield Button("Download", variant="primary", id="download-btn")
            with Horizontal(id="list-header"):
                yield Static("", id="queue-note")
                yield Select(SORT_OPTIONS, id="sort-select", allow_blank=False,
                             value="added")
            yield VerticalScroll(id="downloads")
            with Horizontal(id="status-row"):
                yield LoadingIndicator(id="busy")
                yield Static("Getting ready...", id="status-line")
                yield Static("", id="plan-note")
                yield Button("Stop", variant="error", id="stop-btn")
                yield Button("Clear done", id="clear-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.apply_size_classes()
        self.query_one("#stop-btn", Button).display = False
        self.query_one("#clear-btn", Button).display = False
        self.query_one("#list-header").display = False
        self.query_one("#url-input", Input).focus()
        self._show_destination()
        if getattr(self.app, "auto_prepare", True):
            self._set_busy(True)
            self._prepare_worker()
        else:
            self._set_busy(False)
            self._set_status("Ready.")

    def on_screen_resume(self) -> None:
        self._show_destination()
        self.refresh_bindings()

    def _set_busy(self, busy):
        self.query_one("#busy", LoadingIndicator).display = bool(busy)

    def _show_destination(self):
        try:
            self.query_one("#brand", BrandBar).set_note(
                str(self._settings()["output_dir"]))
        except Exception:
            pass

    def check_action(self, action, parameters):
        if action == "stop_downloads":
            return self._download_active
        if action == "clear_finished":
            return any(row.finished for row in self._rows.values())
        if action == "same_for_all":
            return len(self._awaiting) > 1
        return True

    def _settings(self):
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

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sort-select":
            self._sort_mode = str(event.value)
            self._apply_sort()

    def action_stop_downloads(self) -> None:
        if not self._download_active:
            return
        with self._queue_lock:
            waiting = list(self._queue)
            self._queue.clear()
        dl.request_cancel()
        for tag, _, _q in waiting:
            row = self._rows.get(tag)
            if row is not None and not row.finished:
                row.finish(False, "Stopped before it started.")
        self._set_status("Stopping...")
        self._refresh_buttons()

    def action_open_settings(self) -> None:
        self.app.action_open_settings()

    def action_open_history(self) -> None:
        self.app.action_open_history()

    def action_scroll_list_up(self) -> None:
        self.query_one("#downloads", VerticalScroll).scroll_page_up()

    def action_scroll_list_down(self) -> None:
        self.query_one("#downloads", VerticalScroll).scroll_page_down()

    def action_clear_finished(self) -> None:
        removed = 0
        for tag, row in list(self._rows.items()):
            if row.finished:
                row.remove()
                del self._rows[tag]
                removed += 1
        self._after_list_change()
        if removed:
            self.app.notify(
                f"Cleared {removed} finished "
                f"download{'s' if removed != 1 else ''}."
            )
        else:
            self.app.notify("Nothing finished to clear yet.",
                            severity="warning")

    def on_download_row_remove_requested(
        self, event: DownloadRow.RemoveRequested
    ) -> None:
        event.stop()
        row = event.row
        tag = row.tag

        with self._queue_lock:
            still_waiting = [e for e in self._queue if e[0] == tag]
            self._queue[:] = [e for e in self._queue if e[0] != tag]

        being_asked = tag in self._awaiting
        self._awaiting.discard(tag)
        not_started = bool(still_waiting) or being_asked or tag in self._checking

        if not row.finished and not not_started:
            dl.cancel_tag(tag)
            self.app.notify("Stopping that download.")

        row.remove()
        self._rows.pop(tag, None)
        self._after_list_change()
        self._settle_checks()

    def _after_list_change(self):
        self._refresh_buttons()
        self._refresh_queue_note()
        self._renumber_waiting()
        self.query_one("#list-header").display = bool(self._rows)
        self.refresh_bindings()

    def _refresh_buttons(self):
        finished = any(row.finished for row in self._rows.values())
        self.query_one("#stop-btn", Button).display = self._download_active
        self.query_one("#clear-btn", Button).display = (
            bool(finished) and not self._download_active
        )
        self.refresh_bindings()

    def _refresh_queue_note(self):
        with self._queue_lock:
            waiting = len(self._queue)
        note = self.query_one("#queue-note", Static)
        if waiting:
            note.update(f"{waiting} waiting")
        else:
            note.update(f"{len(self._rows)} in the list" if self._rows else "")

    def _sort_key(self, row):
        mode = self._sort_mode
        if mode == "name":
            return (0 if row.title_text else 1, row.title_text.lower(),
                    row.sequence)
        if mode == "progress":
            return (-row.percent, row.sequence)
        if mode == "unfinished":
            return (1 if row.finished else 0, row.sequence)
        if mode == "finished":
            return (0 if row.finished else 1, row.sequence)
        return (row.sequence,)

    def _apply_sort(self):
        holder = self.query_one("#downloads", VerticalScroll)
        rows = [w for w in holder.children if isinstance(w, DownloadRow)]
        if len(rows) < 2:
            return
        for position, row in enumerate(sorted(rows, key=self._sort_key)):
            try:
                holder.move_child(row, before=position)
            except Exception:
                pass

    @work(thread=True, exclusive=True, group="prepare")
    def _prepare_worker(self) -> None:
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
        except Exception:
            ui(self._set_status, "Could not get things ready.")
            ui(self._set_busy, False)
            return

        config = getattr(app, "config", None) or {}
        if not config.get("skip_speedtest", False):
            try:
                app.bandwidth = measure_bandwidth(callbacks)
            except Exception:
                app.bandwidth = None

        ui(self._set_busy, False)
        ui(self._set_status, "Ready.")

    def _known_links(self):
        return {row.url for row in self._rows.values()}

    def _start(self) -> None:
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
        config = getattr(self.app, "config", None) or {}
        if config.get("ask_quality", False):
            self._begin_checks(urls)
            return

        added = self._enqueue(urls)
        if self._download_active:
            self.app.notify(
                f"Added {added} to the queue - "
                f"{'it' if added == 1 else 'they'} will start automatically."
            )
        self._ensure_worker()


    def _begin_checks(self, urls):
        entries = []
        for url in urls:
            self._sequence += 1
            tag = str(self._sequence)
            self._add_row(tag, url)
            self._rows[tag].set_checking()
            entries.append((tag, url))
            self._checking.add(tag)
        self._after_list_change()
        self._set_busy(True)
        self._announce_checking()
        self._probe_worker(entries)
        return len(entries)

    def _announce_checking(self):
        outstanding = len(self._checking)
        if outstanding and not self._download_active:
            self._set_status(
                f"Checking {outstanding} "
                f"link{'s' if outstanding != 1 else ''}..."
            )

    @work(thread=True, group="probe")
    def _probe_worker(self, entries) -> None:
        app = self.app

        def ui(fn, *args):
            try:
                app.call_from_thread(fn, *args)
            except Exception:
                pass

        tools = getattr(app, "tools", None)
        if not tools:
            try:
                tools = ensure_tools()
                app.tools = tools
            except Exception:
                ui(self._probe_failed, entries)
                return

        def look_up(entry):
            try:
                return entry, available_qualities(tools["yt-dlp"], entry[1])
            except Exception:
                return entry, ("", [])

        workers = max(1, min(PROBE_AT_ONCE, len(entries)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(look_up, entry) for entry in entries]
            for future in as_completed(futures):
                try:
                    (tag, url), (title, choices) = future.result()
                except Exception:
                    continue
                ui(self._probe_done, tag, url, title, choices)

    def _probe_failed(self, entries):
        for tag, _url in entries:
            self._checking.discard(tag)
            row = self._rows.get(tag)
            if row is not None and not row.finished:
                row.finish(False, "Could not get things ready.")
        self._settle_checks()

    def _probe_done(self, tag, url, title, choices):
        self._checking.discard(tag)
        row = self._rows.get(tag)
        if row is None:
            self._settle_checks()
            return
        if title:
            row.set_title(title)

        if not choices:
            row.set_detail("Could not read the qualities - "
                           "using your usual setting.")
            self._queue_checked(tag, url, None)
        else:
            self._awaiting.add(tag)
            row.offer_choices(choices)
            self._maybe_focus_choices(row)
        self._settle_checks()

    def _maybe_focus_choices(self, row):
        here = self.focused
        if isinstance(here, Input) and here.value.strip():
            return
        if here is not None and "quality-chip" in here.classes:
            return
        row.focus_choices()

    def on_download_row_quality_chosen(
        self, event: DownloadRow.QualityChosen
    ) -> None:
        event.stop()
        row = event.row
        tag = row.tag
        self._awaiting.discard(tag)
        self._last_choice = str(event.height)
        row.clear_choices()
        row.set_waiting()
        self._queue_checked(tag, row.url, self._last_choice)
        self._focus_next_question()
        self._settle_checks()

    def _focus_next_question(self):
        for row in self._ordered_rows():
            if row.choosing and row.focus_choices():
                return
        self.query_one("#url-input", Input).focus()

    def action_same_for_all(self) -> None:
        if not self._awaiting:
            return
        height = self._last_choice or self._settings()["quality"]
        answered = 0
        for tag in list(self._awaiting):
            row = self._rows.get(tag)
            if row is None:
                self._awaiting.discard(tag)
                continue
            self._awaiting.discard(tag)
            row.clear_choices()
            row.set_waiting()
            self._queue_checked(tag, row.url, str(height))
            answered += 1
        if answered:
            self.app.notify(f"Using {height}p for {answered} more.")
        self.query_one("#url-input", Input).focus()
        self._settle_checks()

    def _ordered_rows(self):
        holder = self.query_one("#downloads", VerticalScroll)
        return [w for w in holder.children if isinstance(w, DownloadRow)]

    def _queue_checked(self, tag, url, quality):
        with self._queue_lock:
            self._queue.append((tag, url, quality))
        self._after_list_change()
        self._ensure_worker()

    def _settle_checks(self):
        self.refresh_bindings()
        if self._checking:
            self._announce_checking()
            return
        if self._awaiting:
            waiting = len(self._awaiting)
            self._set_busy(False)
            if not self._download_active:
                self._set_status(
                    f"{waiting} link{'s' if waiting != 1 else ''} "
                    f"waiting for you to choose a quality."
                )
            return
        self._last_choice = None
        if not self._download_active:
            self._set_busy(False)
            self._set_status("Ready.")

    def _enqueue(self, urls, quality=None):
        for url in urls:
            self._sequence += 1
            tag = str(self._sequence)
            self._add_row(tag, url)
            with self._queue_lock:
                self._queue.append((tag, url, quality))
        self._after_list_change()
        return len(urls)

    def _renumber_waiting(self):
        with self._queue_lock:
            waiting = list(self._queue)
        for position, (tag, _, _q) in enumerate(waiting, 1):
            row = self._rows.get(tag)
            if row is not None:
                row.set_waiting(position)

    def _ensure_worker(self):
        if self._download_active:
            return
        with self._queue_lock:
            empty = not self._queue
        if empty:
            return
        self._download_active = True
        self.query_one("#download-btn", Button).disabled = False
        self._refresh_buttons()
        self._set_busy(True)
        dl.reset_cancel()
        self._start_speed_readout()
        self._queue_worker()

    def _filter_duplicates(self, urls):
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

        config = getattr(self.app, "config", None) or {}
        if queued and not config.get("archive", False):
            try:
                done = {row.get("url") for row in recent_downloads(limit=500)}
            except Exception:
                done = set()
            repeats_of_done = [u for u in queued if u in done]
            if repeats_of_done:
                count = len(repeats_of_done)
                notices.append(
                    f"{count} of these {'were' if count != 1 else 'was'} "
                    f"downloaded before - downloading again."
                )
        return queued, notices

    def _start_speed_readout(self):
        if self._speed_timer is None:
            self._speed_timer = self.set_interval(1.0, self._tick_speed)

    def _stop_speed_readout(self):
        if self._speed_timer is not None:
            self._speed_timer.stop()
            self._speed_timer = None

    def _tick_speed(self):
        if not self._download_active:
            return
        total = sum(row.speed_bytes for row in self._rows.values())
        with self._queue_lock:
            waiting = len(self._queue)
        running = sum(1 for row in self._rows.values()
                      if row.started and not row.finished)
        if total > 0:
            tail = f", {waiting} waiting" if waiting else ""
            self._set_status(
                f"Downloading {running}{tail} - {human(total)}/s altogether"
            )

    def _set_status(self, text):
        self.query_one("#status-line", Static).update(text)

    def _set_plan(self, text):
        self._plan_note = text or ""
        self.query_one("#plan-note", Static).update(self._plan_note)

    def _add_row(self, tag, url):
        row = DownloadRow(tag, url)
        self._sequence = max(self._sequence, int(tag) if tag.isdigit() else 0)
        row.sequence = int(tag) if tag.isdigit() else self._sequence
        self._rows[tag] = row
        self.query_one("#downloads", VerticalScroll).mount(row)

    def _row_title(self, tag, title):
        row = self._rows.get(tag)
        if row is not None:
            row.set_title(title)
            if self._sort_mode == "name":
                self._apply_sort()

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
        self._refresh_queue_note()
        if self._sort_mode in ("unfinished", "finished", "progress"):
            self._apply_sort()

    def _finished(self, ok_count, fail_count, output_dir):
        self._download_active = False
        self._stop_speed_readout()
        self._set_busy(False)
        self.query_one("#download-btn", Button).disabled = False
        self._after_list_change()

        with self._queue_lock:
            left_over = bool(self._queue)
        if left_over and not dl.is_cancelled():
            self._ensure_worker()
            return

        if fail_count and not ok_count:
            self._set_status("Nothing downloaded. See the list above.")
        elif fail_count:
            self._set_status(
                f"Finished - {ok_count} saved, {fail_count} did not work."
            )
        else:
            saved = f"{ok_count} " if ok_count > 1 else ""
            self._set_status(f"All done - {saved}saved.")
        if not self._awaiting:
            self.query_one("#url-input", Input).focus()

    def _take_batch(self, size):
        with self._queue_lock:
            if not self._queue:
                return []
            wanted = self._queue[0][2]
            batch = []
            rest = []
            for entry in self._queue:
                if len(batch) < size and entry[2] == wanted:
                    batch.append(entry)
                else:
                    rest.append(entry)
            self._queue[:] = rest
        return batch

    @work(thread=True, exclusive=True, group="download")
    def _queue_worker(self) -> None:
        app = self.app
        cfg = self._settings()
        saved = failed = 0

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
            tools = getattr(app, "tools", None)
            if not tools:
                ui(self._set_status, "Getting things ready...")
                tools = ensure_tools(callbacks)
                app.tools = tools

            reading = getattr(app, "bandwidth", None)
            plan = None
            plan_for = None

            while not dl.is_cancelled():
                cfg = self._settings()
                batch = self._take_batch(max(1, cfg["max_parallel"]))
                if not batch:
                    break

                ui(self._renumber_waiting)
                batch_quality = batch[0][2] or cfg["quality"]

                expanded = []
                for tag, url, _q in batch:
                    videos = expand_playlists(tools["yt-dlp"], [url], callbacks)
                    if not videos:
                        ui(self._row_finish, tag, False,
                           "Nothing could be found at that link.")
                        continue
                    expanded.append((tag, videos[0]))
                    for extra in videos[1:]:
                        ui(self._enqueue_extra, extra)
                if not expanded:
                    continue

                tags = [t for t, _ in expanded]
                links = [u for _, u in expanded]

                wanted = (cfg["max_parallel"], cfg["conns_per_file"])
                if plan is None or wanted != plan_for:
                    if cfg["run_speedtest"] and reading:
                        single, line, rtt = reading
                        plan = compute_plan(single, line, rtt, len(links),
                                            cfg["max_parallel"])
                    else:
                        plan = default_plan(len(links), cfg["max_parallel"])
                    if cfg["conns_per_file"]:
                        plan = apply_overrides(
                            plan, conns_per_file=cfg["conns_per_file"])
                    plan_for = wanted
                    ui(self._set_plan, "   ".join(describe_plan(plan)))

                ui(self._set_busy, False)
                results = dl.run_downloads(
                    tools, links, plan, cfg["output_dir"], batch_quality,
                    downloader="aria2c", archive=cfg["archive"],
                    callbacks=callbacks, tags=tags,
                )
                saved += sum(1 for r in results if r[1])
                failed += sum(1 for r in results if not r[1])
                self._record_results(results, batch_quality)

            ui(self._finished, saved, failed, cfg["output_dir"])

        except LumaError as exc:
            ui(self._set_status, exc.user_message)
            ui(self._finished, saved, failed, cfg["output_dir"])
        except Exception:
            ui(self._set_status, "Something went wrong. Please try again.")
            ui(self._finished, saved, failed, cfg["output_dir"])

    def _enqueue_extra(self, url):
        if url in self._known_links():
            return
        self._sequence += 1
        tag = str(self._sequence)
        self._add_row(tag, url)
        with self._queue_lock:
            self._queue.append((tag, url, None))
        self._after_list_change()

    def _record_results(self, results, quality=None):
        try:
            record_results(results, quality=quality)
        except Exception:
            pass
