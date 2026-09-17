"""Build the public feature page from ``plans.md``.

    python tools/feature_page.py feature-grid.html

The page existed before this script did, and its footer claimed the codes,
titles, sizes and releases were read from the plan. They were not -- they were
transcribed by hand, and after two releases the page said 45 items shipped when
the number was 47. A claim a page makes about itself has to be enforced by
something, so here is the something.

What comes from the plan: every item's **code**, **title**, **size**, which
**release** it belongs to, and whether it is **shipped** (a struck item in the
roadmap table). What does not: the one-line blurbs below, which are written for
a reader who has never seen the plan -- the plan's own prose is a spec, and a
spec is not a description. The test in ``tests/test_feature_page.py`` asserts
every item in the plan has one, so an item cannot be added without a sentence
that explains it.

The layout is the instrument's: 61 features on a 64-pad grid, coloured with the
program's own pad meanings -- green for a filled slot, amber for sounding now,
blue for another sample's bar.
"""

from __future__ import annotations

import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "plans.md"
CHANGELOG = ROOT / "CHANGELOG.md"

#: Pads on the Push's grid, which is what the page is laid out as.
PADS = 64

#: How far off shipping an unshipped item is, by the release it sits in.  The
#: nearest open release is what is being built now; everything past it is queued.
STATES = ("now", "next", "later")

SIZE_WORDS = {"S": "small", "M": "medium", "L": "large"}

# A sentence per item, for a reader who has never opened plans.md.  The plan's
# own text is a specification; this is a description.  Keyed by the plan's code,
# and a missing key is a test failure rather than a blank line on the page.
BLURBS = {
    "CC-01":
        "Hold a filled pad to hear it without leaving the library or changing "
        "anything.",
    "CC-03":
        "Anything you cannot undo asks twice, and says what it is about to destroy.",
    "CC-04": "Powering on puts you back in the project, bank and slot you left.",
    "CC-05":
        "Every button lights when you press it, so a dead one is obvious "
        "immediately.",
    "CC-06":
        "A faint ruler on the empty bars, so you can count phrases without "
        "counting pads.",
    "CC-10":
        "A mark on screen when there is something unsaved, and a word when it has "
        "been written.",
    "CC-14":
        "Pull the USB out and the music keeps playing; plug it back in and the grid "
        "relights itself.",
    "CC-15":
        "Drive the whole program from a terminal, with no Push and no audio device.",
    "CC-16":
        "Ask the program what it can and cannot see, and get a one-line fix beside "
        "anything missing.",
    "F-01":
        "The audio callback never waits on a lock, so a slow screen redraw can "
        "never become an audible dropout.",
    "F-02":
        "Every mode in its own file behind one small interface, instead of one file "
        "that knew about all of them.",
    "F-03":
        "Pages layer instead of replacing each other, so leaving the editor puts "
        "you back where you were.",
    "F-04":
        "Every edit is reversible, sixty-four deep, and one sweep of an encoder is "
        "one step rather than forty.",
    "F-05":
        "Three-millisecond fades on every voice, so starting, stopping and stealing "
        "a note never clicks.",
    "F-09":
        "A take remembers the tempo it was cut at, so one that no longer fits its "
        "bars says so instead of drifting.",
    "CC-02":
        "Stop means stop; Shift+Stop finishes the bar; two Stops disarm whatever "
        "was armed.",
    "CC-07": "The playhead is visible on every page that has bars, not just one.",
    "CC-09":
        "Measures your input latency by playing a click and listening for it, then "
        "remembers the number.",
    "CC-11":
        "Hold one bar and press another to fill everything between them in one "
        "gesture.",
    "CC-12":
        "Double-tap a bar to lay the take across the next four, spaced by its own "
        "length.",
    "F-06":
        "Settings that persist, with defaults, a file and the command line "
        "resolving in a stated order.",
    "F-07":
        "A live input meter across the top of the surface, and monitoring you can "
        "switch without feedback.",
    "NF-03":
        "Trim, fade, pitch, gain, reverse and normalise a take, non-destructively, "
        "until you commit it.",
    "NF-04":
        "Play parts in by hand, quantized to the bar, and have what you played "
        "written into the arrangement.",
    "NF-10":
        "Pads respond to how hard you hit them, per sample, so a part can breathe "
        "instead of being flat.",
    "NH-01":
        "Eight mixer strips at a time, with the pads as vertical meters and a solo "
        "that does not destroy your mutes.",
    "NH-04":
        "Overdub another pass onto the same take, sound on sound, and peel the last "
        "layer back off.",
    "NH-07":
        "Tap a tempo with your hand, and nudge it by a tenth of a BPM to match a "
        "record.",
    "NH-08":
        "Fit an off-grid take to its bars in one press, or leave it as it is — "
        "your call, not ours.",
    "CC-08":
        "Bar, beat and tempo large along the bottom of the screen, readable from "
        "across a room.",
    "CC-13":
        "A dimmer library, because sixty-four pads at full brightness is glare "
        "rather than information.",
    "CC-17":
        "Name a slot from a word list on the pads, because there is no keyboard on "
        "a Push.",
    "CC-18":
        "Tag a slot with one of eight colours, so a full library is readable at a "
        "glance.",
    "NF-01":
        "The whole arrangement as a heat map: each pad eight bars by eight slots, "
        "press to zoom in.",
    "NF-05":
        "Render the song to a WAV, or one WAV per slot, with no hardware and no "
        "audio device.",
    "NF-06":
        "Switch songs from the pads, without a terminal and without restarting the "
        "audio.",
    "NF-07":
        "256 sample slots in four banks. A bank is only a view, so everything in "
        "every bank still plays.",
    "NF-11":
        "Four pages of 64 bars — 256 bars, about eight minutes, playing "
        "consecutively.",
    "NH-03":
        "Count-in length, pre-roll, click sound and level, and a click on its own "
        "output pair.",
    "NH-05":
        "Copy a slot, move it, or duplicate a block of bars with the gap between "
        "two presses setting its length.",
    "NH-06":
        "Eight snapshots of the whole arrangement: store one, recall it with a "
        "single press, A/B two choruses.",
    "F-08":
        "A guided probe that walks a real Push 2 and writes down what it actually "
        "does, control by control.",
    "NF-02":
        "How a sample ends — play it out, loop it, gate it to its bar, or "
        "retrigger — plus choke groups.",
    "NF-08":
        "Bring in audio you already own, resampled to the session rate and never "
        "time-stretched to fit.",
    "NF-09":
        "Follow or send MIDI clock, so the sampler plays in time with a drum "
        "machine or another laptop.",
    "NH-02":
        "Swing where sub-beat time exists, and a per-sample nudge behind the bar "
        "line, which is groove on a bar grid.",
    "NH-11":
        "More than one output pair, and a cue bus you can hear without the audience "
        "hearing it.",
    "NH-12":
        "A page on your phone showing what the sampler is doing, for when the Push "
        "is out of reach.",
    "CC-19":
        "Pick two samples and they trade places — audio, arrangement, name, "
        "colour and all.",
    "CC-20":
        "The mode you are in, large at the top of the screen, including what it is "
        "layered over.",
    "NF-12":
        "A view whose only job is playback: the library grid, each pad flashing as "
        "its sample fires.",
    "IN-01":
        "One recording becomes sixty-four playable pieces, laid across the pads at "
        "its own transients.",
    "IN-02":
        "The program listens to what you recorded and tells you what it heard "
        "— pitch, tempo, what it is.",
    "IN-03":
        "Trigger patterns generated to fit what is already there, as a starting "
        "point rather than an answer.",
    "IN-04":
        "Colours the library by which of your loops fit with the one you are on, "
        "and offers a transpose for one that does not.",
    "IN-05":
        "Extra bars a part plays on only every Nth pass, and one button that "
        "freezes however many passes you want as audio.",
    "IN-06":
        "Several recordings of one part on one pad: flip between them, or let the "
        "song cycle them as it goes.",
    "IN-07":
        "The count-in fills a ring round the grid, the right-hand column pulses on "
        "the beat, and the touch strip scrubs the song.",
    "IN-08":
        "Shows you where your timing actually sits, bar by bar, without telling you "
        "off about it.",
    "IN-09":
        "Trim a take without stopping it: tap when you hear the point, then home in "
        "on it with the knobs while a short loop plays it back to you.",
    "NH-09":
        "Make an old take fit a new tempo without re-cutting it: stretch it and "
        "keep the pitch, or resample it and let the pitch move.",
    "NH-10":
        "Per-bar chance and an every-Nth-pass rule, so a loop plays a little "
        "differently each time round.",
}


@dataclass(frozen=True)
class Item:
    code: str
    title: str
    size: str
    train: str
    shipped: bool
    state: str
    pad: int

    @property
    def blurb(self) -> str:
        return BLURBS[self.code]


@dataclass(frozen=True)
class Train:
    version: str
    name: str
    theme: str
    codes: tuple
    complete: bool


def _plain(markdown: str) -> str:
    """Markdown emphasis off a short heading or cell, leaving the words."""
    text = re.sub(r"~~|\*\*|`|†", "", markdown)
    text = re.sub(r"\s*←.*$", "", text)       # "← in progress"
    return text.strip()


def read_trains(plan: str) -> list:
    """The roadmap table: which release each item is in, and whether it shipped.

    The table is the only place the plan states an *order*, which is what the
    page needs -- the item sections are grouped by category instead.
    """
    trains = []
    # The in-progress release is not struck through, so the row cannot be
    # matched on the `~~` -- only on a version number in the first cell.
    for row in re.findall(r"^\| ((?:~~)?\*\*v\d+\.\d+ .+?)\|\s*$", plan, re.M):
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) < 3:
            continue
        heading, theme, contents = cells[0], cells[1], cells[2]
        label = _plain(heading)
        version, _, name = label.partition(" — ")
        codes = tuple(
            (code, bool(struck))
            for struck, code in re.findall(r"(~~)?`([A-Z]+-\d+)`", contents)
        )
        trains.append(Train(version.strip(), name.strip(), _plain(theme), codes,
                            complete="**complete**" in contents))
    return trains


def read_titles(plan: str) -> dict:
    """code -> (title, size), from each item's own section heading."""
    found = {}
    for code, title, size in re.findall(
        r"^### ([A-Z]+-\d+) — (.+?) `size: ([SML])`\s*$", plan, re.M
    ):
        found[code] = (_plain(title), size)
    return found


def read_plan(path: Path = PLAN) -> tuple:
    plan = path.read_text()
    trains = read_trains(plan)
    titles = read_titles(plan)
    # The nearest release with anything open is what is being built now.
    open_trains = [t.version for t in trains if not t.complete]
    items, pad = [], 0
    for train in trains:
        for code, shipped in train.codes:
            title, size = titles.get(code, (code, "M"))
            if shipped:
                state = "shipped"
            else:
                rank = open_trains.index(train.version) if train.version in open_trains else 2
                state = STATES[min(rank, len(STATES) - 1)]
            items.append(Item(code, title, size, train.version, shipped, state, pad))
            pad += 1
    return trains, items


def newest_code(items: list, path: Path = CHANGELOG) -> str:
    """The most recently shipped item, for the panel to open on.

    From the changelog rather than the roadmap table: the table groups items by
    release and says nothing about *when* inside one, so reading the last struck
    entry there opened the page on whichever item happened to be written down
    last -- which was not the newest.  The changelog is in the order things
    actually happened.
    """
    shipped = {item.code for item in items if item.shipped}
    if path.exists():
        for code in re.findall(r"^#{2,3} .*?\(`([A-Z]+-\d+)`\)", path.read_text(), re.M):
            if code in shipped:
                return code
    return next(iter(shipped), items[0].code)


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _item_row(item: Item) -> str:
    chip = "shipped" if item.shipped else "open"
    word = "shipped" if item.shipped else "open"
    return f"""      <li class="item {item.state}" data-pad="{item.pad}">
        <button type="button" class="item-btn" data-pad="{item.pad}">
          <span class="ident"><span class="code">{_esc(item.code)}</span>\
<span class="size">{SIZE_WORDS[item.size]}</span></span>
          <span class="body"><span class="name">{_esc(item.title)}</span>
          <span class="blurb">{_esc(item.blurb)}</span></span>
          <span class="tags"><span class="chip {chip}">{word}</span></span>
        </button>
      </li>"""


def _train_section(train: Train, items: list) -> str:
    mine = [item for item in items if item.train == train.version]
    done = sum(1 for item in mine if item.shipped)
    rows = "\n".join(_item_row(item) for item in mine)
    return f"""  <section class="train" aria-labelledby="t-{train.version}">
    <header class="train-head">
      <h3 id="t-{train.version}"><span class="ver">{train.version}</span> \
{_esc(train.name)}</h3>
      <p class="train-blurb">{_esc(train.theme)}</p>
      <p class="train-count"><b>{done}</b> of {len(mine)} shipped</p>
    </header>
    <ul class="items">
{rows}
    </ul>
  </section>"""


#: One legend row per pad colour, keyed by the state it marks.  Only the states
#: actually on the grid are listed: with nothing left to ship, three rows
#: explaining "being built" and "waiting its turn" describe no pad on the page.
LEGEND_ROWS = {
    "shipped": ("--shipped", "Shipped and in use.",
                "Green is a filled slot on the real grid too."),
    "now": ("--now", "Being built now.", "Amber means sounding right now."),
    "next": ("--next", "Specified, waiting its turn.",
             "Blue is another sample&#8217;s bar."),
    "later": ("--later", "Later &#8212; the ideas nobody else has.", ""),
}


def _legend(states: set, blank: int) -> str:
    rows = []
    for state, (token, headline, note) in LEGEND_ROWS.items():
        if state not in states:
            continue
        tail = f' <span class="note">{note}</span>' if note else ""
        rows.append(
            f'        <p class="legend-row">'
            f'<span class="swatch" style="background:var({token})"></span>\n'
            f"          <span><b>{headline}</b>{tail}</span></p>"
        )
    if blank > 0:
        rows.append(
            '        <p class="legend-row">'
            '<span class="swatch" style="background:var(--pad-off)"></span>\n'
            '          <span><b>Blank.</b> <span class="note">An empty slot, as '
            "the library shows one.</span></span></p>"
        )
    return "\n".join(rows)


def _words(number: int) -> str:
    names = {
        61: "Sixty-one", 62: "Sixty-two", 63: "Sixty-three", 64: "Sixty-four",
        60: "Sixty", 59: "Fifty-nine", 58: "Fifty-eight",
    }
    return names.get(number, str(number))


def build(tests: int, version: str) -> str:
    """The whole page, as one HTML string."""
    trains, items = read_plan()
    missing = [item.code for item in items if item.code not in BLURBS]
    if missing:
        raise SystemExit(f"no blurb for: {', '.join(missing)} (add one in BLURBS)")
    shipped = sum(1 for item in items if item.shipped)
    blank = PADS - len(items)
    # "or will" is a promise, and with nothing left to ship it is a stale one.
    latest = next((t.version for t in trains if not t.complete), "")
    complete = [t.version for t in trains if t.complete]
    # Every release done is a state the page has to be able to say.  Without
    # this it read "v2.0 complete, v2.0 in progress", which a test caught.
    if latest:
        progress = (f"<b>{complete[-1]}</b> complete, <b>{latest}</b> in progress"
                    if complete else f"<b>{latest}</b> in progress")
    else:
        progress = f"<b>{complete[-1]}</b> complete" if complete else "in progress"
    payload = json.dumps([
        {
            "pad": item.pad, "code": item.code, "title": item.title,
            "blurb": item.blurb, "state": item.state, "size": item.size,
            "train": item.train, "shipped": item.shipped,
        }
        for item in items
    ], ensure_ascii=True)
    # The newest decision, so the first look lands on something rather than an
    # empty panel.
    newest = newest_code(items)
    sections = "\n".join(_train_section(train, items) for train in trains)
    return TEMPLATE.format(
        headline=(f"{_words(len(items))} things it does"
                  if shipped == len(items)
                  else f"{_words(len(items))} things it does, or will"),
        shipped=shipped,
        planned=len(items) - shipped,
        tests=f"{tests:,}",
        progress=progress,
        total=len(items),
        blank=blank,
        legend=_legend({item.state for item in items}, blank),
        grid_label=f"{len(items)} features laid out on a {PADS}-pad grid",
        counts=f"{len(items)} features &#183; {PADS} pads &#183; {blank} blank",
        sections=sections,
        payload=payload,
        newest=newest,
        version=version,
        style=STYLE,
    )


STYLE = """
:root {
  /* The palette is the program's own pad colours, carrying the program's own
     meanings: green is a filled slot, amber is sounding right now, blue is
     another sample on this bar, yellow is a take that no longer fits. */
  --ground: #f3f3f0;
  --panel: #ffffff;
  --panel-2: #eaeae7;
  --edge: #d8d8d2;
  --ink: #17181c;
  --ink-2: #4b4f5c;
  --muted: #6b6f7e;
  --shipped: #0f8a3d;
  --now: #bf5a00;
  --next: #1f4fd6;
  --later: #787d8e;
  --caveat: #866900;
  --pad-off: #dcdcd8;
  --focus: #1f4fd6;
  --shadow: 0 1px 2px rgba(20, 22, 26, .07);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #14151a;
    --panel: #1b1d23;
    --panel-2: #23252d;
    --edge: #2e313a;
    --ink: #e9eaee;
    --ink-2: #b6bac6;
    --muted: #8b90a0;
    --shipped: #00c853;
    --now: #ff8200;
    --next: #4d7dff;
    --later: #6f7484;
    --caveat: #ffd600;
    --pad-off: #23252c;
    --focus: #7aa2ff;
    --shadow: 0 1px 0 rgba(255, 255, 255, .03);
  }
}
:root[data-theme="dark"] {
  --ground: #14151a;
  --panel: #1b1d23;
  --panel-2: #23252d;
  --edge: #2e313a;
  --ink: #e9eaee;
  --ink-2: #b6bac6;
  --muted: #8b90a0;
  --shipped: #00c853;
  --now: #ff8200;
  --next: #4d7dff;
  --later: #6f7484;
  --caveat: #ffd600;
  --pad-off: #23252c;
  --focus: #7aa2ff;
  --shadow: 0 1px 0 rgba(255, 255, 255, .03);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  padding-block: 40px 72px;
  padding-left: 20px;
  padding-right: 20px;
  background: var(--ground);
  color: var(--ink);
  font: 400 16px/1.55 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1120px; margin: 0 auto; display: flex; flex-direction: column; gap: 46px; }
h1, h2, h3 { font-family: Archivo, ui-sans-serif, system-ui, sans-serif; text-wrap: balance; margin: 0; }
h1 { font-size: clamp(30px, 5.2vw, 46px); font-weight: 700; letter-spacing: -.022em; line-height: 1.05; }
h2 { font-size: 12.5px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--muted); }
h3 { font-size: 19px; font-weight: 600; letter-spacing: -.012em; }
p { margin: 0; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 3px; }
code { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: .92em; }

.kicker {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--muted);
}
.masthead { display: flex; flex-direction: column; gap: 14px; }
.lede { max-width: 64ch; color: var(--ink-2); font-size: 17px; }
.facts {
  display: flex; flex-wrap: wrap; gap: 6px 22px; margin-top: 2px;
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 13px;
  color: var(--muted); font-variant-numeric: tabular-nums;
}
.facts b { color: var(--ink); font-weight: 500; }

/* The grid is the instrument's grid: every feature a pad, the rest blank. */
.board { display: grid; grid-template-columns: minmax(0, 336px) minmax(0, 1fr); gap: 34px; align-items: start; }
.grid {
  display: grid; grid-template-columns: repeat(8, 1fr); gap: 6px;
  padding: 14px; background: var(--panel); border: 1px solid var(--edge);
  border-radius: 6px; box-shadow: var(--shadow);
}
.pad {
  aspect-ratio: 1 / 1; max-width: 100%; border: 0; padding: 0; cursor: pointer;
  border-radius: 3px; background: var(--pad-off); position: relative;
  transition: transform .08s ease;
}
.pad[data-state="shipped"] { background: var(--shipped); }
.pad[data-state="now"] { background: var(--now); }
.pad[data-state="next"] { background: var(--next); }
.pad[data-state="later"] { background: var(--later); }
.pad[data-blank] { cursor: default; }
.pad:not([data-blank]):hover { transform: scale(1.1); }
.pad[aria-pressed="true"] { box-shadow: 0 0 0 2px var(--panel), 0 0 0 4px var(--ink); z-index: 2; }
@media (prefers-reduced-motion: reduce) { .pad { transition: none; } }

.readout { display: flex; flex-direction: column; gap: 20px; }
.card {
  background: var(--panel); border: 1px solid var(--edge); border-radius: 6px;
  padding: 22px; display: flex; flex-direction: column; gap: 11px; box-shadow: var(--shadow);
}
.card-top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 14px; }
.card .code {
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 13px;
  letter-spacing: .06em; color: var(--muted);
}
.card h3 { font-size: 25px; letter-spacing: -.016em; flex: 1 1 100%; }
.card .blurb { color: var(--ink-2); max-width: 58ch; }
.meta {
  display: flex; flex-wrap: wrap; gap: 6px 18px; padding-top: 5px;
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 12.5px; color: var(--muted);
}
.meta b { color: var(--ink); font-weight: 500; }

.legend { display: flex; flex-direction: column; gap: 9px; }
.legend-row { display: flex; gap: 11px; align-items: flex-start; font-size: 14px; color: var(--ink-2); }
.swatch { width: 13px; height: 13px; border-radius: 2px; flex: 0 0 auto; margin-top: 5px; }
.legend b { color: var(--ink); font-weight: 500; }
.legend .note { color: var(--muted); }

.trains { display: flex; flex-direction: column; gap: 40px; }
.train-head {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px;
  padding-bottom: 12px; border-bottom: 1px solid var(--edge);
}
.ver { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 15px; color: var(--muted); }
.train-blurb { color: var(--ink-2); font-size: 15px; flex: 1 1 auto; }
.train-count {
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 13px;
  color: var(--muted); font-variant-numeric: tabular-nums;
}
.train-count b { color: var(--ink); font-weight: 500; }
.items {
  list-style: none; margin: 0; padding: 0;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 0 36px;
}
.item-btn {
  width: 100%; text-align: left; background: none; border: 0; cursor: pointer;
  display: grid; grid-template-columns: 62px minmax(0, 1fr) auto; gap: 16px;
  align-items: start; padding: 13px 10px 13px 4px;
  border-bottom: 1px solid var(--edge); color: inherit; font: inherit;
}
.item-btn:hover { background: var(--panel-2); }
.item .ident {
  display: flex; flex-direction: column; gap: 2px; padding-top: 2px;
  font-family: "IBM Plex Mono", ui-monospace, monospace; color: var(--muted);
}
.item .code { font-size: 12.5px; }
.item .size { font-size: 11px; }
.item .body { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.item .name { font-weight: 500; }
.item .blurb { color: var(--muted); font-size: 14px; }
.tags { padding-top: 1px; }
.chip {
  font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11px;
  letter-spacing: .05em; text-transform: uppercase; padding: 2px 7px;
  border-radius: 2px; border: 1px solid currentColor; white-space: nowrap;
}
.chip.shipped { color: var(--shipped); }
.chip.open { color: var(--muted); }
.size { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11.5px; color: var(--muted); }
.item[data-selected] .item-btn { background: var(--panel-2); }

/* The caveat is load-bearing, so it is marked rather than tucked away. */
.caveat {
  border: 1px solid var(--edge); border-left: 3px solid var(--caveat);
  border-radius: 4px; padding: 19px 21px; background: var(--panel);
  display: flex; flex-direction: column; gap: 9px;
}
.caveat h2 { color: var(--caveat); }
.caveat p { color: var(--ink-2); max-width: 70ch; font-size: 15px; }
footer { color: var(--muted); font-size: 13.5px; display: flex; flex-direction: column; gap: 5px; }

@media (max-width: 880px) {
  .board { grid-template-columns: minmax(0, 1fr); }
  .items { grid-template-columns: minmax(0, 1fr); }
}
"""


TEMPLATE = """<title>push2sampler Feature Grid</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap">
<style>{style}</style>

<div class="wrap">
  <header class="masthead">
    <p class="kicker">Standalone sampler for the Ableton Push 2</p>
    <h1>{headline}</h1>
    <p class="lede">
      No Ableton Live involved: the program drives the Push 2 directly over MIDI and does its
      own recording, mixing and bar-accurate playback. 256 samples across 256 bars &#8212; about
      eight minutes of music &#8212; all of it reached from an 8&#215;8 grid of pads and the
      buttons around it.
    </p>
    <p class="facts">
      <span><b>{shipped}</b> shipped</span>
      <span><b>{planned}</b> planned</span>
      <span><b>{tests}</b> tests passing</span>
      <span>{progress}</span>
    </p>
  </header>

  <section class="board" aria-label="Every feature as a pad">
    <div>
      <div class="grid" id="grid" role="group" aria-label="{grid_label}"></div>
      <p class="facts" style="margin-top:12px"><span>{counts}</span></p>
    </div>

    <div class="readout">
      <article class="card">
        <div class="card-top">
          <span class="code" id="card-code"></span>
          <h3 id="card-title"></h3>
        </div>
        <p class="blurb" id="card-blurb"></p>
        <p class="meta" id="card-meta" aria-live="polite"></p>
      </article>

      <div class="legend">
        <h2>Pad colours</h2>
{legend}
      </div>
    </div>
  </section>

  <section class="trains" aria-label="Features by release">
{sections}
  </section>

  <section class="caveat">
    <h2>One thing to know before you trust it</h2>
    <p>
      Most hardware facts in this program &#8212; the control change behind each button, what a
      palette colour looks like, how the colour display is fed &#8212; came from Ableton&#8217;s
      <i>Push 2 MIDI and Display Interface</i> document rather than from a device.
    </p>
    <p>
      It has now run on a real Push 2, and the first session corrected four of those facts before
      a single note was recorded: there was no <code>User</code> button to press, the surface
      reports on the <i>Live</i> port rather than the User port in both directions, and two of the
      program&#8217;s own diagnostics turned out to be wrong about what they were measuring. MIDI
      clock sync tracks to 0.3&#8239;ms &#8212; against a synthetic sender, never yet against real
      gear. Ableton Link is a seam with nothing behind it, and says so rather than pretending.
    </p>
    <p>
      The colour display has since rendered too, and that cost two more corrections: one byte of
      the XOR shaping mask was transposed, which showed as a gold striped background with blue
      text, and nothing measured text width, so status lines ran off the right-hand edge. Both are
      fixed. Ten hardware facts have been corrected this way in total &#8212; and every one of them
      was a thing the test suite was perfectly happy with.
    </p>
  </section>

  <footer>
    <p>Generated by <code>tools/feature_page.py</code> from <code>plans.md</code>: the code, title,
      size, release and shipped state of every item are read from the plan, so this page cannot
      drift from it. The one-line descriptions are written for this page; a plan item without one
      fails a test.</p>
    <p>Press any pad, or any row, to read what it is. Version {version}.</p>
  </footer>
</div>

<script>
const ITEMS = {payload};
const SIZES = {{S: "small", M: "medium", L: "large"}};
const STATE_WORD = {{shipped: "shipped", now: "building now", next: "specified", later: "later"}};
const PADS = 64;
const byPad = new Map(ITEMS.map(i => [i.pad, i]));
const grid = document.getElementById("grid");

for (let n = 0; n < PADS; n++) {{
  const item = byPad.get(n);
  const pad = document.createElement("button");
  pad.type = "button";
  pad.className = "pad";
  pad.dataset.pad = String(n);
  if (item) {{
    pad.dataset.state = item.state;
    pad.setAttribute("aria-pressed", "false");
    pad.setAttribute("aria-label", item.code + ": " + item.title);
    pad.title = item.code + " — " + item.title;
  }} else {{
    pad.dataset.blank = "";
    pad.disabled = true;
    pad.setAttribute("aria-label", "empty slot");
  }}
  grid.appendChild(pad);
}}

const elCode = document.getElementById("card-code");
const elTitle = document.getElementById("card-title");
const elBlurb = document.getElementById("card-blurb");
const elMeta = document.getElementById("card-meta");

function select(padIndex) {{
  const item = byPad.get(padIndex);
  if (!item) return;
  elCode.textContent = item.code;
  elTitle.textContent = item.title;
  elBlurb.textContent = item.blurb;
  elMeta.textContent = "";
  const bits = [
    ["release", item.train],
    ["status", STATE_WORD[item.state]],
    ["size", SIZES[item.size]],
    ["pad", (padIndex + 1) + " of " + PADS]
  ];
  for (const [label, value] of bits) {{
    const span = document.createElement("span");
    span.append(label + " ");
    const b = document.createElement("b");
    b.textContent = value;
    span.append(b);
    elMeta.append(span);
  }}
  for (const pad of grid.children) {{
    if (pad.dataset.blank === undefined) {{
      pad.setAttribute("aria-pressed", pad.dataset.pad === String(padIndex) ? "true" : "false");
    }}
  }}
  for (const row of document.querySelectorAll(".item")) {{
    if (row.dataset.pad === String(padIndex)) row.dataset.selected = "";
    else delete row.dataset.selected;
  }}
}}

grid.addEventListener("click", event => {{
  const pad = event.target.closest(".pad");
  if (pad && pad.dataset.blank === undefined) select(Number(pad.dataset.pad));
}});
document.addEventListener("click", event => {{
  const btn = event.target.closest(".item-btn");
  if (btn) select(Number(btn.dataset.pad));
}});

// Open on the newest item, so the first look lands on what was most recently
// decided rather than on an empty panel.
const newest = ITEMS.find(i => i.code === "{newest}") || ITEMS[0];
select(newest.pad);
</script>
"""


def main(argv: list) -> int:
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    out = Path(argv[1])
    tests = int(argv[2]) if len(argv) > 2 else _count_tests()
    from push2sampler import __version__

    out.write_text(build(tests, __version__))
    _trains, items = read_plan()
    shipped = sum(1 for item in items if item.shipped)
    print(f"{out}: {len(items)} items, {shipped} shipped, {tests} tests")
    return 0


def _count_tests() -> int:
    """Collect the suite rather than guess at the number the page prints."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    match = re.search(r"^(\d+) tests? collected", result.stdout, re.M)
    if not match:
        raise SystemExit("could not count the tests; pass the number as argv[2]")
    return int(match.group(1))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main(sys.argv))
