# Luma — Master Build Plan

**Audience:** the Claude Code session that will build Luma in this repository.
**Status of this document:** it is the spec *and* the work order. Follow it top to bottom, one phase at a time.

---

## 0. How to use this document

This project is deliberately broken into small phases because the failure mode
we are designing against is *doing too much at once and shipping something
half-finished*. The phase boundaries are not suggestions.

**The working loop, every single time:**

1. Read the phase. Read only that phase.
2. Build exactly what it asks for.
3. Run its **Acceptance criteria** — every item, for real, not by inspection.
4. Report back: what you built, the actual output of each acceptance check, and
   pass/fail per item.
5. Only after that, start the next phase.

**Do not:**

- Bundle two phases into one work session.
- Pre-implement a later phase's feature "while I'm already in this file."
- Leave a phase at "mostly working" and move on.
- Mark an acceptance criterion passed because the code *looks* right. Run it.

If a phase turns out to be wrong, too large, or blocked, **stop and say so**
rather than improvising a different scope. Adjusting the plan is allowed;
silently drifting from it is not.

---

## 1. What Luma is

A YouTube downloader with a real terminal user interface, built for people who
are **not** comfortable with a command line.

The user should be able to: open Luma, paste a link, press a button, watch a
progress bar, and find their video in a folder. That is the whole product. Every
decision below serves that sentence.

**Explicitly in scope for this version:**

- YouTube only (single videos and playlists).
- A Textual TUI with a main screen, a settings screen, and a history/errors viewer.
- Persistent config, download history, and an error log.
- Portable distribution: a folder + a launcher script, zipped.

**Explicitly out of scope for this version — do not build these:**

- Other sites (no generic "any URL" support, even though yt-dlp could).
- A compiled `.exe` (no PyInstaller, no Nuitka).
- Auto-update, telemetry, or any network call Luma makes on its own behalf.
- Account login, cookies, or age-restricted/private video handling.
- Audio-only extraction, format conversion, subtitle burning, or post-processing
  beyond what the ported engine already does.

---

## 2. Cross-cutting rules

These apply to **every** phase. They are stated here once and referenced by
number later; they will not be re-explained.

### R1 — Textual docs freshness (non-negotiable)

Textual is the least-familiar library in this project and its API has changed
across releases. **Before writing any Textual code in a phase, fetch the current
official documentation for the parts you are about to use.** Do not write
Textual code from memory.

At minimum, fetch docs for the areas each phase touches:

| Area | When you need it |
|---|---|
| App, Screen, `compose()`, widget mounting | Phase 2 |
| Workers — `@work`, thread workers, cancellation | Phase 3 |
| `App.call_from_thread`, `post_message` thread-safety | Phase 3 |
| Testing — `App.run_test()`, `Pilot` | Phase 2 onward |
| Widget reference — `ProgressBar`, `DataTable`, `Input`, `Select`, `Switch`, `RadioSet`, `Button`, `Log`/`RichLog` | Phases 2, 5, 7 |
| TCSS (Textual CSS) | Phase 8 |
| Themes / `App.theme` | Phases 5, 8 |
| Animation (`animate()`, transitions) | Phase 8 |

Docs live at `https://textual.textualize.io/`. If that host is unreachable from
your environment, the same content is in the repo at
`https://github.com/Textualize/textual` under `docs/guide/` — fetch the raw
markdown, and read `src/textual/` directly when you need to confirm an exact
signature.

**Verified facts as of writing this plan** (still re-check, but these are known
good — latest Textual is **8.2.8**, requires **Python ≥3.9**):

- `from textual import work` — the decorator is exported from the package root,
  **not** from `textual.work`.
- `from textual.worker import get_current_worker` — call inside a thread worker
  to get its `Worker`, then check `worker.is_cancelled`.
- `App.call_from_thread(fn, *args)` — required for touching UI from a thread.
  `post_message()` is the other thread-safe option.
- Textual raises if you apply `@work` to a non-async function without `thread=True`.
- `App.run_test()` is an **async context manager** yielding a `Pilot`; tests must
  be `async`. Pilot has `press()`, `click()`, `pause()`, `hover()`.
- Built-in theme names include `textual-dark`, `textual-light`, `nord`,
  `gruvbox`, `dracula`, `tokyo-night`, `monokai`, `solarized-light`,
  `solarized-dark`, `catppuccin-mocha`, `flexoki`.

### R2 — Stop-and-verify gate

See §0. One phase, then verify, then report, then stop.

### R3 — Reuse, don't reinvent (porting fidelity)

Luma's download engine is a **port of already-proven code**, not a fresh
implementation. See Phase 0 for how to obtain it.

When porting, treat these as frozen — copy them, do not "improve" them:

- The bandwidth/connection math in `compute_plan()`.
- The progress-parsing regexes `_ARIA_RE` and `_YTDL_RE`.
- The retry/backoff formula.
- The constants `MAX_ATTEMPTS`, `MAX_TOTAL_CONNECTIONS`, `ARIA2_MAX_PER_FILE`,
  `DEFAULT_MAX_PARALLEL`, `YT_PER_VIDEO_MBPS_CAP`.
- Per-item error isolation: one video failing must never abort the batch.

You may change *how results are reported* (print → callback). You may not change
*what the engine decides*. If you believe a ported value is wrong, say so in your
phase report and leave it alone.

### R4 — Security checklist

Applied continuously, audited formally in Phase 9:

1. **No shell.** Every subprocess call uses an argument list. Never
   `shell=True`, never string interpolation into a command.
2. **URL allowlist.** Parse the URL; accept only `http`/`https` schemes and only
   YouTube hosts. Reject everything else with a plain-language message before it
   reaches yt-dlp.
3. **Path containment.** Resolve the final output path and verify it stays inside
   the configured download folder. Sanitize any title-derived path segment.
4. **Safe JSON I/O.** Atomic writes (temp file + replace). A missing or corrupt
   JSON file degrades to a safe default; it never crashes Luma and never silently
   destroys the other files.
5. **No auto-open.** Luma never launches a downloaded file or a file manager.
6. **Crash containment.** A top-level handler writes the traceback to a log file
   and shows the user a calm message. Stack traces never hit the TUI.
7. **Clean child processes.** Quitting Luma, or cancelling a download, must not
   leave orphaned `yt-dlp`/`aria2c` processes.

### R5 — Non-technical user framing

Every string the user can see must be readable by someone who has never opened a
terminal before.

- No jargon: no "stderr", "exit code 1", "HTTP 403", "regex", "subprocess".
- No flags or file paths presented as instructions.
- No stack traces, ever.
- Errors say what happened and what to try: *"Couldn't reach YouTube. Check your
  internet connection and try again."*
- **The Settings screen is the only sanctioned way to change Luma's behaviour.**
  Never write a message, README line, or comment that tells the user to edit a
  JSON file by hand.

### R6 — Verification method

Every phase that touches the TUI is verified primarily by an **automated Textual
test** using `App.run_test()` and `Pilot`, plus **one manual run-through** to
confirm it actually feels right. Tests live in `tests/` and must pass with a
plain `pytest` run. Non-UI phases are verified by their own runnable checks.

Add `pytest` and `pytest-asyncio` as dev dependencies in Phase 2.

### R7 — Scope discipline

YouTube only. No `.exe`. Windows is the **end user's** platform, but development
and testing happen wherever this session runs — the tool-resolution code prefers
`shutil.which()` before falling back to downloading Windows binaries, so the
engine is testable on Linux. Keep it that way; do not add Windows-only calls to
the core engine.

### R8 — Repository layout

Build toward this. Create directories as the phases need them, not upfront.

```
luma/
  __init__.py
  app.py                 # Textual App, top-level crash handler
  config.py              # config.json schema, load/save, defaults, validation
  history.py             # history.json + errors.json append/read
  storage.py             # atomic JSON read/write primitives
  paths.py               # app data dir, output dir resolution, path containment
  engine/
    __init__.py
    tools.py             # ensure_tools(), ToolInstallError
    plan.py              # compute_plan(), plan summary
    download.py          # run_downloads(), download_one(), _stream_download()
    progress.py          # _ARIA_RE, _YTDL_RE, progress event types
    urls.py              # URL validation / allowlist
  screens/
    __init__.py
    main.py
    settings.py
    history.py
  luma.tcss
tests/
  test_*.py
requirements.txt
run.bat
README.md
```

---

## Phase 0 — Inputs and inventory

**Goal:** know what you are porting *from* before you port anything.

Luma's engine is a port of a working CLI tool, `yt_turbo.py`, built in an earlier
session. **That file is not in this repository yet.**

**Do this first:**

1. Check for the reference source. Look for `yt_turbo.py`, or a `reference/`
   directory, anywhere in the repo.
2. **If it is present:** read it end to end. Produce a short inventory — every
   function, its signature, what it prints, where it touches the filesystem or
   spawns a process, and the actual values of the five frozen constants in R3.
   This inventory is your porting checklist for Phase 1.
3. **If it is absent:** stop and ask the user to add it (dropping the file into
   `reference/yt_turbo.py` and committing is enough). Do not start Phase 1 by
   guessing at the engine.

**Only if the user confirms the file cannot be supplied** do you fall back to
building the engine from the behavioural spec in Phase 1. In that case, the five
constants become *your* decisions — pick sensible values, and label them in code
as newly chosen rather than ported, so nobody later mistakes them for tuned ones.

**Acceptance criteria**

- [ ] You have stated clearly whether the reference file is present.
- [ ] If present: an inventory of its functions and the real values of the five
      frozen constants is in your phase report.
- [ ] If absent: you have asked for it and stopped, rather than improvising.

---

## Phase 1 — Engine port and standalone verification (no UI)

**Goal:** a working, importable download engine with **zero Textual code**. Prove
a real video downloads end to end before any interface exists.

This phase exists because debugging a download problem *through* a TUI is
miserable. Get the engine right while it is still a plain Python module.

**Port into `luma/engine/`** (per R8), obeying R3:

- `ensure_tools()` → `engine/tools.py`
- `compute_plan()` and the plan summary → `engine/plan.py`
- `run_downloads()`, `download_one()`, `_stream_download()` → `engine/download.py`
- `_ARIA_RE`, `_YTDL_RE` → `engine/progress.py`

**Three deliberate changes during the port:**

1. **Printing becomes callbacks.** The engine must not call `print()`. Replace
   every user-facing print with a call to an injected callback. Define a small
   set of event objects (dataclasses are fine) in `engine/progress.py` — e.g.
   `ProgressEvent(video_id, title, percent, speed, eta)`, `StatusEvent(message)`,
   `CompletedEvent(video_id, path)`, `FailedEvent(video_id, reason)` — and have
   `run_downloads()` accept an `on_event` callable. The engine stays
   UI-agnostic; it does not know Textual exists.
   - `print_plan()` becomes a function returning a **dict/dataclass** describing
     the plan. Formatting is the UI's job.
2. **`_abort_non_windows()` becomes catchable.** Its current behaviour — kill the
   process — is fatal inside a TUI. Replace it with a `ToolInstallError`
   exception carrying a plain-language message (R5). Nothing in `luma/engine/`
   may call `sys.exit()` or `os._exit()`.
3. **URL validation is added** in `engine/urls.py`, implementing R4.2. Write
   `validate_youtube_url(url) -> str` that returns a normalized URL or raises a
   `InvalidURLError` with a user-safe message. Accept `http`/`https` only, and
   only YouTube hosts (`youtube.com`, `www.youtube.com`, `m.youtube.com`,
   `music.youtube.com`, `youtu.be`). Reject `file:`, `ftp:`, `javascript:`,
   `data:`, bare paths, and lookalike hosts such as `youtube.com.evil.tld`.

Also add a **basic** output-path guard now (R4.3) — resolve the path, confirm it
is inside the intended folder. The full configurable version arrives in Phase 4;
here a hardcoded downloads folder is fine.

**Write a throwaway CLI harness** — `scripts/engine_check.py` — that takes a URL,
wires `on_event` to `print()`, and runs the engine. This is a scaffold for
verifying Phase 1, not a product feature. It may stay in the repo as a debugging
aid, but nothing in `luma/` may import it.

**Guardrails:** no Textual, no config file, no history file, no settings — none
of those exist yet.

**Acceptance criteria**

- [ ] `python scripts/engine_check.py <a real YouTube URL>` downloads an actual
      video to disk. Report the filename and byte size.
- [ ] The same harness against a **playlist** downloads multiple videos, and a
      single failing item does not stop the rest (R3).
- [ ] `grep -rn "print(" luma/engine/` returns nothing.
- [ ] `grep -rn "sys.exit\|os._exit" luma/engine/` returns nothing.
- [ ] `grep -rn "shell=True" luma/` returns nothing (R4.1).
- [ ] `validate_youtube_url()` rejects, with a friendly message and no traceback:
      `file:///etc/passwd`, `javascript:alert(1)`, `ftp://x/y`,
      `https://youtube.com.evil.tld/watch?v=x`, `not a url at all`.
- [ ] The five frozen constants match the reference values (quote them).

---

## Phase 2 — Minimal Textual app shell and test harness

**Goal:** the smallest possible Textual app that runs, quits cleanly, and is
already under automated test. **It downloads nothing.**

Apply **R1** before writing any code here.

**Build:**

- `luma/app.py` — a `LumaApp` with a `Header`, a `Footer`, and key bindings for
  quit and for opening settings.
- `luma/screens/main.py` — an `Input` for the URL, a **disabled or no-op**
  "Download" button, and an empty log/status panel.
- `luma/screens/settings.py` — a stub screen: a title, a "Back" button, nothing
  else. It must be reachable and dismissible.
- A minimal `luma/luma.tcss` so styling has a home from the start. Real design
  is Phase 8.
- **Top-level crash handler** (R4.6): wrap the app run so any unhandled exception
  is written with its traceback to a log file in the app data directory, while
  the user sees a short calm message. Verify it by deliberately raising inside an
  event handler, confirming the log file, then removing the deliberate raise.
- `requirements.txt` with `textual`; dev deps `pytest` and `pytest-asyncio`.

**Write the first tests** (R6) — these prove the *test harness itself* works,
which is what makes every later phase verifiable:

- App starts and mounts without error.
- Typing into the URL input updates its value (`pilot.press(...)`).
- The settings key binding pushes the settings screen; "Back" pops it.

**Guardrails:** the Download button must do nothing. No engine import in
`luma/app.py` or the screens yet. Resist wiring it "since it's right there."

**Acceptance criteria**

- [ ] `python -m luma` opens the TUI and `q` exits cleanly to a normal prompt
      (no traceback, no mangled terminal).
- [ ] `pytest` passes, with at least the three tests above.
- [ ] The crash handler was demonstrated: show the log file contents from your
      deliberate test raise, and confirm the deliberate raise is now removed.
- [ ] `grep -rn "engine" luma/app.py luma/screens/` returns nothing.

---

## Phase 3 — Live download wiring via workers

**Goal:** the Download button really downloads, with live per-video progress in
the TUI.

Apply **R1** for workers and thread-safety before writing code.

**The threading model — read this carefully:**

The engine is **synchronous, blocking, subprocess-driven** code. Do **not**
rewrite it as asyncio. Run it unchanged inside a thread worker:

```python
from textual import work
from textual.worker import get_current_worker

@work(thread=True, exclusive=True)
def _run_download(self, url: str) -> None:
    worker = get_current_worker()
    def on_event(event):
        if worker.is_cancelled:
            raise DownloadCancelled()
        self.call_from_thread(self._handle_event, event)
    run_downloads(url, on_event=on_event)
```

Rules that follow from this:

- **Never** touch a widget or set a reactive directly from the worker thread.
  Everything goes through `call_from_thread()` or `post_message()`.
- The engine's `on_event` callback is the cancellation checkpoint — that is how
  a blocking download becomes interruptible.
- On quit or cancel, cancel the worker **and terminate child processes** (R4.7).
  A cancelled Python thread does not kill a running `aria2c`; you must do it.

**UI work:**

- A per-video progress row: title, a `ProgressBar`, percent, speed, ETA — driven
  by the events defined in Phase 1.
- A plan summary panel rendered from the Phase 1 plan dict.
- The status panel shows friendly progress messages (R5).
- Failures render as calm rows, not tracebacks; the batch continues (R3).

**Guardrails:** settings are **not** wired. Use hardcoded defaults (a fixed
downloads folder, a fixed quality, ported default connection counts). Config
arrives in Phase 4. Do not write history files yet — Phase 6.

**Acceptance criteria**

- [ ] Pasting a real URL and pressing Download produces a finished video file on
      disk, with the progress bar having visibly advanced.
- [ ] A playlist shows multiple rows updating; one bad item shows a friendly
      failure row while the others finish.
- [ ] Pressing quit **during** an active download exits cleanly, and
      `ps aux | grep -E "aria2c|yt-dlp"` shows **no** orphaned processes.
- [ ] A `Pilot` test drives the input + button and asserts the UI reaches a
      completed state (point it at a short video, or a fake engine — but at least
      one acceptance run must use the real engine).
- [ ] Deliberately break the network mid-download; the app shows a friendly
      message and stays usable. No traceback on screen.

---

## Phase 4 — Config system and output-path resolution

**Goal:** persistent, validated settings — with **no settings UI yet**.

Separating storage from its screen means you can prove the dangerous parts (file
corruption, bad values, path traversal) without fighting widgets.

**Build:**

- `luma/storage.py` — atomic JSON primitives (R4.4). Write to a temp file in the
  same directory, then `os.replace()`. `read_json(path, default)` returns
  `default` on missing **or** corrupt file, never raising.
- `luma/config.py` — the `config.json` schema, defaults, load, save, validate:

  | Key | Type | Default | Notes |
  |---|---|---|---|
  | `download_folder` | str | OS downloads dir | Must resolve to a writable dir |
  | `quality` | str | `"best"` | One of `360`, `480`, `720`, `best` |
  | `subfolder_scheme` | str | `"none"` | `none` / `by_playlist` / `by_date` |
  | `max_parallel` | int | ported default | Clamp to ported max |
  | `connections_per_file` | int | ported default | Clamp to ported max |
  | `theme` | str | `"textual-dark"` | A valid Textual theme name |

  Every value is **clamped or rejected** on load. An out-of-range integer becomes
  the default; an unknown enum becomes the default; an unwritable folder falls
  back to the OS downloads dir. A bad config never crashes Luma.

- `luma/paths.py` — the app data directory, plus `resolve_output_dir(config, video_meta)`
  implementing R4.3 fully: apply the subfolder scheme, sanitize every
  title-derived segment (strip separators, `..`, control characters, reserved
  Windows names, trailing dots/spaces), resolve, and **assert containment** within
  `download_folder`. Raise rather than write outside it.

**Guardrails:** no Settings screen. No UI changes at all. Phase 3's hardcoded
defaults may now read from config, but nothing user-facing changes yet.

**Acceptance criteria**

- [ ] `pytest` covers, and passes: missing `config.json` → defaults written;
      truncated/garbage `config.json` → defaults, no exception; out-of-range
      `max_parallel` → clamped; unknown `quality` → default; unknown theme → default.
- [ ] A traversal test: a video title of `../../../../evil` resolves **inside**
      `download_folder` or raises — never outside. Assert on the resolved path.
- [ ] Atomicity test: a write interrupted before `os.replace()` leaves the
      original file intact.
- [ ] All three subfolder schemes produce the expected directory, verified by test.

---

## Phase 5 — Settings screen

**Goal:** every value from Phase 4 is editable in the TUI. **This is the phase
that makes R5's promise true** — after it, no user ever needs to see a JSON file.

Apply **R1** for the widget reference and themes.

**Build** — one control per config key:

- `download_folder` — an `Input`, validated on save (exists / creatable / writable).
- **`quality` — a `Select` or `RadioSet` offering 360p / 480p / 720p / Best available.**
  This is a required control; the quality is not locked to a fixed value.
- `subfolder_scheme` — `Select`: "All in one folder" / "A folder per playlist" /
  "A folder per date".
- `max_parallel`, `connections_per_file` — `Input`s with numeric validation,
  clamped to the ported maximums, with the limit stated in plain words.
- `theme` — `Select` over Textual's built-in themes, bound to `App.theme` so the
  change is visible **immediately** on selection.
- **Save** and **Cancel** buttons. Save writes via Phase 4's validated path;
  Cancel discards and restores the previous values, including a previewed theme.

**Validation is inline and blocking:** an invalid field shows a friendly message
next to it (R5) and Save does not proceed. Never save a bad value and silently
correct it later.

Label everything in user language: "Where to save videos", not `download_folder`.

**Acceptance criteria**

- [ ] A `Pilot` test: open settings, change quality to 720p, save, reopen — 720p
      is still selected. Confirm `config.json` on disk changed.
- [ ] A `Pilot` test: enter an invalid folder path, press Save — an inline error
      shows, the screen stays open, and `config.json` is **unchanged**.
- [ ] Changing the theme restyles the app immediately; Cancel reverts it.
- [ ] Manual: set quality to 480p, download a video, and confirm from the file
      that the setting was actually applied.
- [ ] Every Phase 4 config key has a working control. List them against the table.

---

## Phase 6 — History and errors persistence

**Goal:** Luma remembers what it downloaded and what went wrong. **No viewer UI
yet.**

**Two files, kept strictly separate** — do not merge them, and do not put
failures in `history.json`:

- `history.json` — successful downloads. Per record: timestamp, video title,
  source URL, final file path, quality used, file size.
- `errors.json` — failures. Per record: timestamp, video title (if known),
  source URL, the friendly reason shown to the user, and a short technical
  detail for diagnosis.

**Build `luma/history.py`** on top of `luma/storage.py` (R4.4), with
`append_history(record)` and `append_error(record)`. Requirements:

- Appends are atomic and never lose the existing list.
- A corrupt `history.json` does **not** prevent errors being logged, and vice
  versa — they degrade independently.
- Both files cap their length (keep the most recent N, e.g. 500) so they cannot
  grow without bound.

**Wire it into the engine's real outcome branches** — the actual success and
failure paths in `download_one()`, not a guess at where they are. A download that
fails after retries writes exactly one error record, not one per attempt.

`resolve_output_dir()` from Phase 4 is now used for real, so recorded paths are
the true final paths.

**Guardrails:** no history screen. Verify by reading the JSON files directly.

**Acceptance criteria**

- [ ] Download a real video; `history.json` gains exactly one correct record.
      Show it.
- [ ] Force a failure (invalid video ID); `errors.json` gains exactly **one**
      record and `history.json` is untouched. Show both.
- [ ] Corrupt `history.json` by hand, then download — the app still runs, still
      logs errors, and recovers history to a valid state.
- [ ] A test proves the cap: append N+10 records, confirm N remain and that the
      newest survived.

---

## Phase 7 — History and errors viewer screen

**Goal:** the user can see their downloads and failures without leaving Luma.

Apply **R1** for `DataTable`.

**Build** `luma/screens/history.py`: a read-only screen, reachable by a key
binding and shown in the footer. Two views — Downloads and Problems — as tabs or
a toggle. Use `DataTable` with readable columns (When / Video / Quality / Size;
When / Video / What happened).

- **Read fresh from disk each time the screen opens.** Do not cache.
- Empty state is a friendly sentence, not a blank grid: *"No downloads yet."*
- Timestamps in a human format, not raw ISO.
- Long titles truncate rather than break the layout.

**Guardrails — keep it plain.** No search, no sorting, no filtering, no
pagination, no "clear history" button, no export, no row actions, no opening the
downloaded file (R4.5). If you find yourself adding a feature not listed here,
stop.

**Acceptance criteria**

- [ ] A `Pilot` test opens the screen, asserts the table row count matches the
      records on disk, and closes it.
- [ ] Manual: with both files populated, both views render correctly.
- [ ] With both files absent, the screen opens and shows friendly empty states —
      no crash.
- [ ] Download a new video while Luma stays open, reopen the screen — the new row
      is there (proves the fresh read).

---

## Phase 8 — Visual polish, theming and purposeful animation

**Goal:** Luma looks finished and calm. This is the phase where restraint matters
most.

Apply **R1** for TCSS, themes, and animation.

**Styling:**

- Move all styling into `luma/luma.tcss`. No inline style strings left in Python.
- Use **theme variables** (`$surface`, `$primary`, `$text`, …) rather than
  hardcoded colours, so every built-in theme from Phase 5 looks correct.
- Consistent spacing and alignment across the three screens; the footer always
  shows the keys available on the current screen.
- Verify against at least one light theme and one dark theme.

**Animation — exactly three touchpoints. No others.**

1. **Resolve spinner** — while yt-dlp is fetching video info and there is no
   percentage yet. It stops the moment real progress arrives.
2. **Progress bar fill** — smooth interpolation between progress events so the
   bar glides instead of jumping.
3. **Completion highlight** — a one-shot flash on a row when its download
   finishes, which settles and stops.

Every one of these communicates state. Anything decorative — animated borders,
pulsing titles, transition effects between screens, spinners on idle screens — is
bloat. Do not add it.

**Acceptance criteria**

- [ ] `grep -rn "styles\." luma/` shows no leftover inline styling (bar any
      genuinely dynamic case, which you should name and justify).
- [ ] Screenshots or a described run in a light theme and a dark theme, both legible.
- [ ] **Idle CPU check:** leave Luma open on each screen with no download running
      for 30 seconds and record CPU usage (`top`/`ps`). It must be effectively
      zero. A UI that animates while idle fails this phase.
- [ ] Exactly three animations exist. Name them and their file/line.
- [ ] Existing tests still pass — styling changed, behaviour did not.

---

## Phase 9 — Security and robustness audit

**Goal:** deliberately attack Luma, fix what breaks, and write down the result.

This is a **structured adversarial pass**, not a re-read of the code. Run each
case, record actual observed behaviour, and fix every gap you find.

**The matrix — run all of it:**

| # | Case | Required behaviour |
|---|---|---|
| 1 | `file:///etc/passwd` in the URL box | Friendly rejection, no filesystem access |
| 2 | `javascript:alert(1)`, `data:text/html,x`, `ftp://host/f` | Friendly rejection |
| 3 | `https://youtube.com.evil.tld/watch?v=x` | Rejected — host allowlist, not substring match |
| 4 | A URL containing shell metacharacters (`;`, `&&`, backticks, `$( )`) | Passed as a single argument; nothing executes (R4.1) |
| 5 | Video title with `../`, `/`, `\`, null bytes, or a reserved Windows name | File lands inside the download folder; name sanitized |
| 6 | `download_folder` set to a path outside the user's home | Either honoured safely or refused — never a traversal write |
| 7 | Corrupt `config.json` only | App starts with defaults; history and errors intact |
| 8 | Corrupt `history.json` only | App runs; errors still log; history recovers |
| 9 | Corrupt `errors.json` only | App runs; history still logs |
| 10 | All three corrupt at once | App starts, usable, no traceback |
| 11 | Read-only download folder | Friendly message before downloading, not a crash mid-way |
| 12 | Disk full during a download | Friendly failure, error logged, app stays alive |
| 13 | Network killed mid-download | Retries per the ported policy, then a friendly failure |
| 14 | Quit during an active download | Clean exit, **no orphaned `yt-dlp`/`aria2c`** (R4.7) |
| 15 | Kill Luma with SIGKILL mid-download | No corrupt JSON files on next start (R4.4) |
| 16 | Unhandled exception in an event handler | Caught, logged to file, calm message (R4.6) |
| 17 | Two downloads started in quick succession | `exclusive=True` behaves predictably; no interleaved corruption |
| 18 | Search the codebase for any auto-open of files | None exists (R4.5) |

**Then write `SECURITY.md`** — short and factual: what was tested, what the
result was, what was fixed, and the known limitations you are shipping with
(e.g. "Luma trusts yt-dlp to fetch content; it does not sandbox it").

**Acceptance criteria**

- [ ] All 18 cases executed with **observed** results recorded — not predicted.
- [ ] Every gap found is fixed, with a test added where a test is possible.
- [ ] `SECURITY.md` exists and matches what you actually ran.
- [ ] Full `pytest` run green.

---

## Phase 10 — Packaging: portable source distribution

**Goal:** a non-technical Windows user can unzip a folder, double-click one file,
and use Luma.

**Build:**

- **`requirements.txt`** — pinned versions of `textual` and anything else runtime
  code imports. Dev-only tools (`pytest`, `pytest-asyncio`) go in a separate
  `requirements-dev.txt`, not the shipped file.

- **`run.bat`** — the launcher, extending the pattern from the earlier project:
  1. Detect Python. If missing, print a plain-language message and offer the
     `winget` install command — do not attempt a silent install.
  2. Create/reuse a local virtual environment.
  3. `pip install -r requirements.txt` (quietly; show progress on first run).
  4. Launch Luma.
  5. **`pause` on exit**, so a user who double-clicks can read any message
     instead of watching the window vanish.
  6. Every message it prints obeys R5.

- **`README.md`** — written for the end user, not for developers. Cover: what
  Luma does, how to start it (double-click `run.bat`), how to download a video,
  where videos are saved, how to change settings **in the app**, and what to do
  when something fails. No flags, no Python instructions, no JSON editing (R5).

- **The zip** — assemble the portable folder and produce the archive. Exclude
  `.git/`, `tests/`, `scripts/`, `__pycache__/`, any local venv, and any personal
  `config.json`/`history.json`/`errors.json`. Ship no personal data.

**Guardrails:** no PyInstaller, no `.exe`, no installer, no auto-update, no code
signing (R7).

**Acceptance criteria**

- [ ] Unzip the archive into a **clean directory** and launch it there. It must
      work with no reference to the development checkout.
- [ ] List the archive contents and confirm no `.git/`, no caches, no personal
      JSON files.
- [ ] `run.bat` handles the Python-missing case gracefully — verify by
      inspection with the exact message quoted, if you cannot test on Windows.
- [ ] The README is readable start to finish by someone who has never used a
      terminal. Re-read it against R5 and quote any line you had to fix.
- [ ] A first-run walkthrough from the unzipped copy: paste a URL, download,
      change a setting, view history. All four work.

---

## Definition of done

Luma is finished when all of the following hold:

1. Every phase 1–10 has been completed and its acceptance criteria verified with
   real output.
2. `pytest` is green.
3. A clean unzip runs, downloads a real video, and saves it where the settings say.
4. Nothing in the user-visible surface violates R5 — no jargon, no tracebacks, no
   "edit this file" instructions.
5. `SECURITY.md` reflects tests that were actually run.
6. The five frozen constants and the engine's decision logic are unchanged from
   the reference (R3).

## If you get stuck

- **A phase is too big** — say so and propose a split. Do not half-build it.
- **A cross-cutting rule conflicts with a phase instruction** — the rule wins;
  flag the conflict.
- **The Textual API differs from this document** — the live docs win (R1). Note
  the difference in your phase report so this plan can be corrected.
- **You want to add something not in the plan** — don't. Propose it, finish the
  phase, let the user decide.
