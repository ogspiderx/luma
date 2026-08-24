# Luma — security notes

Luma runs external download tools and writes files to disk on behalf of
whatever link is pasted into it. This page records what is done about that,
and what was checked.

Every claim below is covered by an automated audit, `tests/test_security.py`,
which ships with the source rather than with the packaged release.

---

## What Luma guards against

### Commands are never handed to a shell

Every external tool is started with an argument list. There is no
`shell=True`, no `os.system`, no shell string anywhere in the codebase.

This matters because a link is untrusted input that ends up as an argument. A
link containing something like `; rm -f somefile` is passed to the downloader
as one literal argument and nothing interprets it.

> **Checked:** the whole package is scanned for `shell=True`, `os.system`,
> `os.popen`, `eval` and `exec`; every `subprocess` call site is confirmed to
> receive a list rather than a string. A link containing a shell command is
> then run for real against a canary file, and the canary is confirmed
> untouched.

### Only real web links are accepted

A link must parse as `http` or `https` and point at a host Luma supports.
Everything else is refused before it reaches any tool or is written anywhere.

Refused: `file://`, `javascript:`, `data:`, `ftp://`, `gopher://`, UNC paths,
bare shell fragments such as `` `id` `` or `$(whoami)`, and anything shaped
like a command-line option (`--exec=...`, `-o /etc/passwd`) which would
otherwise be appended to the command as an argument.

> **Checked:** each of the above is confirmed refused, and a valid link mixed
> in with hostile ones is confirmed to still work while the hostile ones are
> reported.

### Folders cannot escape where they are meant to be

Any folder that comes from a person is resolved to an absolute path and
checked. System directories (`/etc`, `/bin`, `/boot`, `/proc`, `/sys`, and
similar) are refused outright and fall back to the default download folder.

Names used to build subfolders — including a playlist's title, which comes
from the internet — are reduced to a single safe filename component, so a
playlist called `../../escape` produces a subfolder rather than a way out.

> **Checked:** traversal attempts of several shapes are confirmed contained
> inside the intended folder, system directories are confirmed refused, and a
> hostile playlist name is confirmed unable to escape.

### A damaged file never stops the app

Settings, history and error records are read defensively: a missing,
truncated, empty, or garbled file yields a safe default rather than raising.
Nothing read from disk is trusted — numbers are clamped to workable ranges and
unknown values fall back.

Writes are atomic. Data goes to a temporary file and is then moved into place,
so an interruption cannot leave a half-written file, and a write that cannot
be completed leaves the previous file intact.

> **Checked:** binary junk, truncated JSON, an empty file, an HTML error page,
> deeply nested brackets and a wrong-typed value are each written into all
> three files, and the app is confirmed to start, load usable settings, and
> open both the history and settings screens.

### Quitting leaves nothing running

Every download process is registered while it runs. On quit — including
Ctrl+C and an unexpected failure — they are all terminated, and killed if they
do not stop.

> **Checked:** a long-running download is started, confirmed visible to the
> operating system, then stopped; both Luma's registry and the process list are
> confirmed empty afterwards.

### Failures are explained, not dumped

Tool output is translated into plain language before it reaches the screen. A
private video, a region block, a dropped connection and a full disk each get a
sentence a person can act on. Raw tool output, tool names and tracebacks are
never shown.

If something unexpected escapes entirely, it is written to `logs/crash.log`
and the user sees a short message instead of a traceback.

> **Checked:** the screen is scanned for `traceback`, `yt-dlp`, `aria2c`,
> `ffmpeg`, `subprocess`, `exception` and `stderr` after a hostile link is
> submitted. A crash is then forced in a real subprocess: the terminal is
> confirmed free of any traceback while the log is confirmed to contain it.

### Downloaded files are never opened

Luma downloads files and stops there. Nothing opens, launches or executes what
was downloaded — a downloaded file is not necessarily what it claims to be, and
that decision belongs to the person, not the app.

> **Checked:** the codebase is scanned for `os.startfile`, `xdg-open`,
> `webbrowser`, and `os.exec`.

---

## Deliberate limits

- **Luma only supports YouTube.** Other sites are refused rather than
  attempted, so the surface stays small.
- **Luma downloads only what is publicly reachable.** It has no facility for
  bypassing payment, sign-in or copy protection.
- **Nothing is sent anywhere.** There is no telemetry and no account. The only
  outbound connections are to the video host and, briefly, a speed-test
  endpoint used to decide how many downloads to run at once.
- **Everything stays in the app folder.** Settings, records, logs and
  downloads all live beside the application. Deleting the folder removes
  everything Luma created.

## Running the audit

From a source checkout:

```
python tests/test_security.py
```

Re-run it after any change to how links are handled, how folders are built, or
how the download tools are started.
