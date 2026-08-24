# Luma

A friendly YouTube downloader. Paste a link, press Enter, get the video.

Luma runs in a window on your desktop and is built to be quick — it opens many
connections at once and works out how many downloads your internet can handle,
rather than trickling one file at a time.

---

## Getting started

1. **Double-click `run.bat`.**
2. Paste a YouTube link into the box.
3. Press **Enter**.

Luma opens maximised in its own window. **F11** makes it full screen. If you
would rather have no tabs or title bar at all, start it with `run.bat --bare` —
though note that leaves nothing to grab if you want to move the window.

That is the whole thing. Your videos appear in the **`downloads`** folder next
to Luma.

### The first time you open it

The first run takes a couple of minutes and you only go through it once:

- If Python is not on your computer, Luma offers to install it. Say yes, then
  close the window and open Luma again.
- Luma then downloads the three tools it uses to fetch and combine video. One
  of them is large, so give it a moment. You will see it happening.

After that, Luma starts in a second or two.

---

## Using Luma

| What you want | How |
|---|---|
| Download a video | Paste the link, press Enter |
| Download several | Paste several links separated by spaces |
| Download a playlist | Paste the playlist link |
| Remove one from the list | Press the **✕** beside it |
| Stop everything | **Ctrl + X** |
| Clear finished ones | **Ctrl + L** |
| Change how Luma works | **Ctrl + S** |
| See what you've downloaded | **Ctrl + H** |
| Close Luma | **Ctrl + Q** |

The keys along the bottom change with what you can actually do — Stop only
appears while something is running, so there is never a row of dead options.

While a download runs you'll see a bar for each video with its size, speed and
how long is left. Finished videos turn green; ones that didn't work turn red
and say why.

### Without a mouse

Everything can be done from the keyboard. **Tab** moves forward through the
screen and **Shift + Tab** back, wrapping round, so nothing needs clicking.
Where a row is asking which quality to use, **←** and **→** move between the
qualities and **Enter** picks one.

---

## Settings

Press **Ctrl + S**. Everything is changeable here — you never need to edit any
files.

**Save downloads to** — where your videos go. Anywhere you like, as long as
it isn't a system folder.

**Organise downloads** — all in one folder, a folder for each day, or a folder
for each playlist.

**Video quality** — 360p, 480p, 720p, or the best available. Higher quality
means bigger files and longer downloads. 480p is a good balance and is the
default.

**Ask me which quality, for every link** — with this on, Luma looks up what
each link is actually available in and asks you to pick, showing roughly how
big each one would be.

The question appears **in the row for that video**, not over the whole screen,
so nothing is blocked while you decide: other videos carry on downloading, you
can keep pasting links, and several questions can sit open at once. Your links
appear in the list the moment you paste them and are checked several at a time.
As soon as you answer one, that video starts — you don't wait for the rest.

If you paste a lot at once, press **Ctrl + A** to use your last answer for
every question still open. A link Luma cannot read quietly uses your usual
setting instead.

**Videos at once** — how many download simultaneously. More is usually faster
on a quick connection, but not always.

**Connections per video** — how many pieces each video is fetched in. This is
the main reason Luma is fast. 16 is the maximum and the default; lower it only
if your connection struggles.

**Appearance** — Luma Night (ink and gold) is the default; Luma Day is the
same idea for a bright room. There are two, deliberately: the interface is
built around one colour meaning one thing, and a scheme borrowed from
somewhere else undoes that.

**Skip videos I've already downloaded** — leave this on and Luma won't fetch
the same video twice.

If you type something Luma can't use, it says so and won't save until it's
fixed, so you can't accidentally break your setup.

---

## History

Press **Ctrl + H** to see everything you've downloaded — what, when, how big,
what quality — and a separate tab listing anything that didn't work, with the
reason in plain words.

---

## What Luma puts on your computer

Everything lives in this folder. Nothing is installed elsewhere, and nothing is
sent anywhere.

| | |
|---|---|
| `downloads` | Your videos |
| `bin` | The download tools Luma fetched on first run |
| `logs` | Notes about anything that went wrong |
| `config.json` | Your settings (change these in Settings, not here) |
| `history.json` | What you've downloaded |
| `errors.json` | What didn't work |

To remove Luma completely, delete this folder.

---

## If something goes wrong

**A video says it didn't work.** The reason is shown on screen and in History.
Private, removed and region-blocked videos can't be downloaded by anything.

**Downloads are slow.** Check your connection first. If it's fine, open
Settings and make sure *Connections per video* is 16. Trying 2 or 3 *Videos at
once* can also help on a fast connection.

**It stopped partway.** Luma retries a few times on its own. If it still
doesn't work, paste the link again and it picks up where it left off rather
than starting over. Stopping a download yourself is treated as final, so the
half-finished pieces are cleared away and that one begins afresh next time.

**There are odd `.part` and `.aria2` files in my downloads folder.** There
shouldn't be — Luma clears them away as each video finishes or is stopped.
The only ones that stay are for a download that failed and could still be
resumed. Anything left over from an older version is safe to delete.

**Luma won't start, or closes immediately.** Look in the `logs` folder — the
newest entry says what happened. Deleting `config.json` resets Luma to its
defaults and fixes most start-up problems.

**Nothing downloads at all, and it worked before.** YouTube changes often.
Luma updates its own downloader on start-up, so simply opening it again usually
fixes this.

---

## Good to know

- Luma is for videos you're allowed to download. Please respect the rights of
  the people who made them.
- Only YouTube is supported at the moment.
- Luma never opens or plays what it downloads — the files are just saved for
  you.
- Luma needs Windows and an internet connection. Nothing else.
- Luma resizes with its window. Make it narrow and the optional details step
  aside; make it wide and everything gets more room.

Technical notes about how Luma protects you are in `SECURITY.md`.

---

## Making it your own

Luma's name and colours live in one file, `luma/branding.py`. Change the name,
the wordmark and the ten colours in it and the whole interface follows — the
bar across the top, both themes, and every accent. Nothing else in the code
hard-codes a colour or the product name.
