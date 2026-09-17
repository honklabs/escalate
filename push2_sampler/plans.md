# push2sampler — product plan

Status: **55 of the 61 items below are shipped** — every train up to and
including `v1.5`, and four of the ten `v2.0` ideas. Three of those shipped
in part or in a different shape, and each says so in its own note: `CC-13`
shipped only the half that needs no unverified hardware, `NF-09` shipped MIDI
clock and left Link a seam, and `NH-02` shipped as two features because the one
it specified was a no-op. Every shipped item carries a status note saying what
was built and where it deviated from this plan and why.

An earlier version of this line claimed "v1.1 shipped and most of v1.2" while
seven of `v1.1`'s own items were still open — a reminder to count against
[§4](#4-release-trains) rather than against the feeling of progress.

The current release is **1.5.0**, covering the `v1.4` and `v1.5` trains. Tags
would be scoped to this subdirectory (`push2sampler-v1.5`) because the
repository belongs to another project, but **none has been pushed** — these
credentials can push branches and not tag refs, so `__init__.py` and
[`CHANGELOG.md`](CHANGELOG.md) are the record.

User documentation for everything shipped is in [`docs/`](docs/README.md) —
tutorial, reference, cheat sheet, troubleshooting, simulator guide — and
[`CHANGELOG.md`](CHANGELOG.md) is the release record. This document is the
backlog and the rules of engagement for the rest of the way to v2.0.

---

## 0. How to read this document

Every work item has a stable ID (`F-01`, `NF-03`, …). An item is written so that
**one implementer can pick it up with no further context than this file plus the
code**. Each item states:

| Field | Meaning |
| --- | --- |
| **Problem** | the user-visible gap; why we are doing it |
| **Spec** | the behaviour to build, precisely enough to test |
| **Surface** | pads, buttons, encoders, display (skip if none) |
| **Code** | files and functions to touch |
| **Tests** | what must be added to `tests/` |
| **Done when** | acceptance criteria |
| **Deps** | items that must land first, and items it collides with |
| **Size** | S ≈ half a day, M ≈ 1–2 days, L ≈ 3–5 days, XL ≈ needs splitting |

Read §3 before writing any code. It contains the conventions that keep parallel
work from colliding — particularly §3.5 (button allocation) and §3.8 (file
contention).

---

## 1. Product thesis, principles, non-goals

**Thesis.** A Push 2 plus a microphone should be a complete instrument. You
capture a loop, say where it plays in a 64-bar song, and build the whole
arrangement with your hands on the grid — no laptop screen, no DAW, no mouse.
The laptop is a power supply and a disk.

**Principles.**

1. **The grid is the document.** If a thing exists in the song, you can see it
   and touch it on the 8×8 grid. New features earn their place by being legible
   as 64 lights.
2. **No mode you can get lost in.** Every mode exits to the Sample Library with
   one press. State is always visible on the display.
3. **Timing is sacred.** Recording and playback are frame-accurate against the
   bar grid. No feature may make the audio callback slower or less predictable.
4. **Never lose a take.** Autosave, undo, and crash-safe project writes come
   before polish.
5. **Works without the optional parts.** MIDI stack, PortAudio, pyusb, Pillow,
   soundfile are each optional at import time. `--sim` must always run the whole
   program with none of them.
6. **One-press depth.** Shift-layers and long-presses are fine; three-key
   chords are not.

**Non-goals (say no to these).** Ableton Live integration or Link-less clock
slaving to Live's transport; plugin/VST hosting; a desktop GUI as the primary
interface; cloud accounts or sharing; Push 1 support; MPE/per-pad pitch;
unbounded song length. Push 3 standalone support is explicitly out of scope
until §12.Q3 is answered.

---

## 2. Where we are today

**Every foundation item is shipped** (`F-01`-`F-09`), and the `v1.1`, `v1.2` and
`v1.3` trains are complete, plus `NF-03`, `NF-04`,
`NF-05`, `NF-10`, `CC-01` and `CC-06`. Each carries a status note in its own
section below. ~7,700 lines, 298 tests, `ruff` clean, no hardware needed to
test.

`F-08` shipped the *tool* -- `--selftest` walks a real Push 2 and writes a
report -- but the human half is still outstanding: nobody has run it yet. Until
they do, every hardware constant remains an educated guess and the README's
"Confirmed against real hardware" table reads "not yet" all the way down. That
report is the highest-value thing anyone can hand this project.

That finishes **v1.2**. Next is v1.3's pair: `NF-01` (song page) and `NF-07`
(banks), which both rewrite how slots and bars are addressed -- one owner, in
that order, or they will collide. `NH-01` (mixer) is the easy independent one if
something smaller is wanted first.

```
push2sampler/
  constants.py  pad/note geometry, button CC map, encoder decode
  colors.py     private palette (indices 64–75) + simulator glyphs
  push2.py      MIDI transport, PushBase/Push2/SimPush, translate_midi()
  audio.py      Transport, Engine (_process), Voice, ScheduledSample, recorder
  project.py    Sample, Project, build_schedule(), save()/load()
  modes/        base (the mode contract), library, record, sample, settings,
                perform
  history.py    undoable commands + the undo/redo journal
  settings.py   the settings table: defaults, validation, labels, persistence
  selftest.py   the guided hardware probe and its report
  render.py     offline bouncing: the whole mix, or one stem per slot
  edits.py      non-destructive trim/fade/pitch/reverse/normalise
  app.py        App: event dispatch, LED render loop, autosave
  display.py    optional 960×160 screen over USB bulk
  sim.py        terminal simulator REPL
  cli.py        argparse entry point
  wavio.py      float32/int16 WAV IO + linear resample
```

**Known debt, all of it deliberate and all of it scheduled below:**

- Samples are immutable once recorded: no trim, gain staging is one number
  (`NF-03`).
- No time-stretch: a take from another tempo is detected and can be padded or
  trimmed, but not stretched in pitch-preserving fashion (`NH-09`).
- Tempo changes do not move recorded audio, so an old take drifts against a new
  tempo. It is now *detected* and repairable by padding/trimming (`F-09`);
  pitch-preserving stretching is still open (`NH-09`).
- Nothing has run against a real Push 2 yet. `--selftest` exists to fix that
  (`F-08`); the display's framing is now pinned byte for byte by unit tests, but
  only a human with the device can confirm it looks right.
- The song is exactly 64 bars, one page, one bank of 64 slots (`NF-07`, `NF-11`).

---

## 3. Working agreements for implementers

### 3.1 Repo layout

All work lives under `push2_sampler/`. The rest of the repository belongs to
another project — **do not touch anything outside this directory.** Run
everything from `push2_sampler/`:

```
python -m pytest -q          # must be green before and after your change
ruff check .                 # must be clean
python -m push2sampler --sim --bpm 240 --samplerate 8000 /tmp/demo   # manual check
```

### 3.2 The mode contract

A mode subclasses `modes.Mode` and implements only what it needs:

```python
on_enter() / on_exit()
on_pad(index, pressed, velocity) -> bool      # True = consumed
on_button(cc, pressed) -> bool                # False = falls through to App._global_button
on_encoder(cc, delta) -> bool
on_engine_event(event: tuple) -> None
render_pads(pads: list[int]) -> None          # 64 palette indices, index 0 = top-left
render_buttons(buttons: dict[int, int]) -> None
status_lines() -> list[str]                   # display, first line is the title
```

Rules: modes never touch MIDI or the stream directly; they mutate
`self.project` and call `self.app.rebuild_schedule()` / `save_soon()` /
`notify()`. Rendering must be **pure and cheap** — it runs 30×/second and must
not allocate audio buffers or hit the disk.

### 3.3 The engine contract

`Engine._process()` is the only realtime code. Treat it as a hot path:

- No Python object allocation per frame, no dict lookups in inner loops, no
  logging, no disk, no `print`.
- Work in numpy whole-array operations on slices of the pre-allocated output.
- Anything the UI needs to read back is published as a plain attribute
  assignment (`self.sounding = (...)`) — atomic reference swap, never a
  mutate-in-place the UI could observe half-done.
- Anything the UI wants to change goes through a public setter that takes
  `self._lock` (today) or posts a command (after `F-01`).
- New engine events are tuples `("name", *payload)` pushed to `self.events`
  and consumed by `App.tick()` → `mode.on_engine_event()`.

If your feature needs new per-bar data, extend `ScheduledSample` — it is the
contract between `Project.build_schedule()` and the mixer — rather than reaching
back into `Project` from the callback.

### 3.4 LED and palette rules

- Pads are addressed by palette index; the program uploads its own palette at
  startup (`Push2.program_palette`). **New colours are added to
  `colors.PALETTE` using indices 76+** and must also get a `SIM_GLYPHS` letter,
  or the simulator prints `?`.
- Never send MIDI from a mode. `PushBase.set_pad/set_button` already dedupe, so
  render the full state every frame and let the diff handle the wire.
- Semantic colour language, keep it consistent:
  white = available/neutral, green = content, dim green = content muted,
  amber = sounding now, red = recording/destructive, blue = "belongs to
  something else", yellow = armed modifier.
- Anything that flashes uses `App.blink` (a shared 2 Hz square) so the whole
  surface blinks in phase.

### 3.5 Button and encoder allocation registry

**Claim your controls here in your PR.** Two features silently binding the same
CC is the most likely merge conflict in this project.

| Control | CC | Status |
| --- | --- | --- |
| Play | 85 | **taken** — transport · `Shift`+`Play` opens perform mode |
| Record | 86 | **taken** — take/re-record · `Shift`+`Record` bounces |
| Stop | 29 | **taken** — stop / cancel / back out · `Shift`+`Stop` stops at the bar line · double-tap disarms everything |
| Session | 51 | **taken** — back to library |
| Note | 50 | **taken** — alias of Session |
| ◀ Left | 44 | **taken** — alias of Session |
| ▲ / ▼ | 46 / 47 | **taken** — prev/next filled slot · mixer row · settings page |
| Mute | 60 | **taken** — per-sample audible toggle / library mute-arm |
| Delete | 118 | **taken** — delete-arm |
| Metronome | 9 | **taken** — click |
| Repeat | 56 | **taken** — `NF-11`: loop scope (page / song / off) |
| Shift | 49 | **taken** — modifier |
| Setup | 30 | **taken** — settings page · `Shift`+`Setup` saves the project |
| Tempo encoder | 14 | **taken** — BPM (±1, ±10 with `Shift`, ±0.1 holding `Tap Tempo`) |
| Track encoder 1 | 71 | **taken** — take length / sample gain |
| Undo | 119 | **taken** — undo · `Shift`+`Undo` redo |
| Display row top | 102–109 | **taken** — input level meter (`F-07`) |
| Display row bottom 1 | 20 | **taken** — Sample page: fit an off-grid take |
| Duplicate | 88 | **taken** — `NH-05`: library copies a slot, sample page copies a block of bars |
| Clip | 113 | **taken** — `NF-01`: the song overview · again to zoom out |
| Device | 110 | **taken** — Sample page: editor · `Shift`+`Device` applies |
| Browse | 111 | **taken** — `NF-06`: the project browser |
| Page ◀ / ▶ | 62 / 63 | **taken** — `NF-07`: bank · `Shift`: `NF-11` song page · Song page: move the zoom |
| Fixed Length | 90 | **taken** — Perform: quantize amount |
| Accent | 57 | **taken** — Sample page: velocity response on/off |
| Scale | 58 | reserved → `IN-04` (key/pitch tools) |
| Automate | 89 | reserved → `IN-03` (generative fills) |
| Convert | 35 | reserved → `IN-01` (slice a take) |
| Tap Tempo | 3 | **taken** — `NH-07`: four taps set the tempo · held, it makes the tempo encoder ±0.1 |
| Master | 28 | free — `NH-01` used the master *encoder*, not this button |
| Add Track | 53 | free |
| Select | 48 | **taken** — `CC-17`/`CC-18`: name and colour a slot |
| Layout | 31 | free |
| User | 59 | free — spec value, and F-08 finding 1 found no such button on the panel; do not bind it |
| Octave ▲▼ | 55 / 54 | free |
| ▶ Right | 45 | free |
| Display row bottom | 20–27 | **taken per mode** — Library: `NH-06` scenes · Mixer: mute · Settings/Editor/Tag/Browser: their own |
| Swing encoder | 15 | reserved → `NH-02` |
| Mix | 112 | **taken** — `NH-01`: the mixer page |
| Solo | 61 | **taken** — `NH-01`: arms solo on the mixer page |
| New | 87 | **taken** — `NH-04`: overdub a layer · `Shift`+`New` removes one |
| Master encoder | 79 | **taken** — `NH-01`: master gain |
| Track encoders 2–8 | 72–78 | **taken on the settings page** (one per setting); elsewhere reserved → `NH-01` mixer, `NF-03` editor params |

The eight display-row buttons are the escape hatch: a mode that needs more
controls should claim them contextually and label them in `status_lines()`
rather than burning a global button.

### 3.6 Testing requirements

No item is done without tests that run **with only numpy installed**. Use the
three harnesses that already exist:

1. **Offline engine** — `Engine(backend="offline")` plus
   `engine.process_offline(frames, indata)` renders synchronously, so timing
   assertions are exact. Pattern it on `tests/test_audio.py`; use `SR = 8000`
   to keep renders fast.
2. **Simulated surface** — the `rig` fixture in `tests/test_flow.py` wires
   `SimPush` + offline `Engine` + `App`, and `pump(app)` delivers events and
   re-renders LEDs. Assert on `push.pad_leds[i] == colors.X.index` — that is how
   we test UI.
3. **Scripted simulator** — pipe commands into
   `python -m push2sampler --sim` for an end-to-end smoke check (real threads,
   real wall-clock transport). Good for a final manual sanity pass; not a
   substitute for (1) and (2).

Any feature touching `_process` must add an assertion that proves the frame at
which something happens, not merely that it happened.

### 3.7 Definition of done

- [ ] `python -m pytest -q` green; new tests cover the acceptance criteria.
- [ ] `ruff check .` clean.
- [ ] Works in `--sim` with no MIDI/PortAudio/pyusb/Pillow installed.
- [ ] New buttons/encoders claimed in the §3.5 table in the same PR.
- [ ] New colours added to `colors.PALETTE` **and** `colors.SIM_GLYPHS`.
- [ ] `README.md` key map and workflow updated if the surface changed.
- [ ] `docs/` updated if the surface changed: the control tables in
      `docs/reference.md` and `docs/cheatsheet.md`, a step in
      `docs/getting-started.md` if it is a feature a new user should meet, and a
      row in `docs/troubleshooting.md` for any new way it can go wrong.
      Pad colours appear in three places there; grep for the colour name.
- [ ] Project-format changes are backward compatible: old `project.json` loads,
      with `FORMAT_VERSION` bumped and a migration in `Project.load`.
- [ ] Nothing outside `push2_sampler/` modified.

### 3.8 File contention map

Items are grouped by the file they rewrite. **Within a group, work is serial —
one owner at a time.** Across groups, fan out freely.

| Group | Files | Items |
| --- | --- | --- |
| **A — engine hot path** | `audio.py` | `F-01`, `F-05`, `NF-02`, `NF-04`, `NF-09`, `NH-02`, `NH-09`, `IN-05` |
| **B — mode shell** | `app.py`, `modes/__init__.py` | `F-02`, `F-03`, `F-04`, `CC-04`, `CC-05` |
| **C — data model** | `project.py`, `wavio.py` | `F-09`, `NF-03`, `NF-07`, `NF-11`, `NH-05`, `NH-06` |
| **D — new modes** | one new file each under `modes/` | `NF-01`, `NF-03`, `NF-06`, `NH-01`, `F-06` |
| **E — surface/IO** | `push2.py`, `display.py`, `constants.py` | `F-07`, `F-08`, `CC-13`, `CC-14`, `CC-20` |
| **F — offline/DSP** | new `analysis.py`, `render.py` | `NF-05`, `IN-01`, `IN-02`, `IN-04` |
| **G — CLI/sim** | `cli.py`, `sim.py` | `CC-09`, `CC-15`, `CC-16` |

`F-02` (split `modes.py`) must land before group D fans out — that is the whole
point of doing it first.

### 3.9 Dispatch template for a sub-agent

```
Implement <ID> from push2_sampler/plans.md.

Read, in order: push2_sampler/plans.md §3 (all of it) and the item's own
section; push2_sampler/README.md; the files named in the item's "Code" field.

Work only inside push2_sampler/. Follow §3.7 Definition of done — including
tests that run with numpy alone, ruff clean, and claiming any button you bind
in the §3.5 table.

Do not start items other than <ID>. If the item turns out to need a change in
a file owned by another group per §3.8, stop and report rather than editing it.

Report: what you changed, test output, and anything in plans.md that turned out
to be wrong.
```

---

## 4. Release trains

Every one of the 62 items below is scheduled here. Creature comforts are
deliberately spread across the trains: each release should contain something
that makes the instrument nicer to touch, not only bigger.

| Release | Theme | Contents |
| --- | --- | --- |
| ~~**v1.1 — Trustworthy**~~ | it never bites you | **complete** — ~~`F-01`~~ ~~`F-02`~~ ~~`F-03`~~ ~~`F-04`~~ ~~`F-05`~~ ~~`F-09`~~ ~~`CC-01`~~ ~~`CC-03`~~ ~~`CC-04`~~ ~~`CC-05`~~ ~~`CC-06`~~ ~~`CC-10`~~ ~~`CC-14`~~ ~~`CC-15`~~ ~~`CC-16`~~ |
| ~~**v1.2 — Playable**~~ | recording and arranging feel good | **complete** — ~~`F-06`~~ ~~`F-07`~~ ~~`NF-03`~~ ~~`NF-04`~~ ~~`NF-10`~~ ~~`NH-01`~~ ~~`NH-04`~~ ~~`NH-07`~~ ~~`NH-08`~~ ~~`CC-02`~~ ~~`CC-07`~~ ~~`CC-09`~~ ~~`CC-11`~~ ~~`CC-12`~~ |
| ~~**v1.3 — A whole song**~~ | bigger than 64 bars, and it leaves the box | **complete** — ~~`NF-05`~~ ~~`NH-05`~~ ~~`NF-01`~~ ~~`NF-06`~~ ~~`NF-07`~~ ~~`NF-11`~~ ~~`NH-03`~~ ~~`NH-06`~~ ~~`CC-08`~~ ~~`CC-13`~~† ~~`CC-17`~~ ~~`CC-18`~~ |
| ~~**v1.4 — Plays with others**~~ | sync, import, and a verified surface | **complete** — ~~`F-08`~~ ~~`NF-02`~~ ~~`NF-08`~~ ~~`NF-09`~~ ~~`NH-02`~~† ~~`NH-11`~~ ~~`NH-12`~~ |
| ~~**v1.5 — Watch it play**~~ | the song as a performance, not an edit | **complete** — ~~`NF-12`~~ ~~`CC-19`~~ ~~`CC-20`~~ |
| ~~**v2.0 — Instrument**~~ | the ideas nobody else has | **complete** — ~~`IN-01`~~ ~~`IN-02`~~† ~~`IN-03`~~ ~~`IN-04`~~† ~~`IN-05`~~† ~~`IN-06`~~† ~~`IN-07`~~† ~~`IN-08`~~ ~~`NH-09`~~† ~~`NH-10`~~† |
| ~~**v2.1 — Editing by ear**~~ | you decide with your ears, not with a number | **complete** — ~~`IN-09`~~ |

A struck item is shipped. `F-08` is struck because the *tool* is shipped; the
human pass with a real Push 2 in hand is the one open thing this project cannot
do for itself.

† `CC-13` shipped its dimmer-library half only. Its global-brightness SysEx
needs a command byte verified against Ableton's manual, which cannot be done
here, so it waits for `F-08` — see the item.

† `IN-02` shipped its analysis and info page; its **arrangement hint** waits
for `IN-03`, which needs the same propose-then-accept mechanic — building it
twice would be the wrong order. Its role vocabulary is also five rather than
the six the spec named, because six is not separable by these features. See
the item.

† `NH-02` shipped as swing **and** a per-sample nudge. Swing as specified (8th
notes) cannot act on a bar-addressed arrangement at all, so swing went where
sub-beat time actually exists — live triggering — and the nudge is the bar-grid
equivalent. See the item for the reasoning; it is the one place in this plan
where the spec was judged wrong rather than incomplete.

† `IN-05` shipped, and three quarters of it was already there: "every 4th pass,
double the hats" needed **no engine change at all**, because an extra trigger
that fires only on every 4th pass *is* a trigger with `NH-10`'s `every_n` of 4.
Its variation is stored as concrete bars you can look at rather than a rule you
have to trust. See the item.

† `IN-07` shipped its count-in ring, its beat pulse and its strip handling, but
**the strip itself remains unverified**: that it speaks pitch bend at all comes
from Ableton's document, `--selftest` has never been completed, and no hand has
ever touched it. Everything downstream is built to be inert rather than wrong if
that turns out to be false. It also needed a new `Engine.seek`, because `stop`
rewinds to bar 1 by design and every scrub landed there. See the item.

† `NH-09` shipped both stretch modes, but its "worker" is a stepped job like the
bounce -- the plan's worry ("must not be started from the audio callback") is
met more simply by there being no worker. Its similarity search had to be
vectorised rather than merely written, and the plan's "dominant frequency
unchanged" assertion is only valid for a single note. See the item.

† `IN-04` shipped its overlay and its transpose, but not from a key: naming a
tonic is measurably the unreliable half (a Cmaj7 reads "E minor"), so the
colours come from pitch-class content and the key is shown labelled a guess.
Its green/yellow/red mapping also had to stop using the circle of fifths, on
which C major and its own relative minor sit three steps apart. See the item.

† `IN-06` shipped its alternates, but the spec's `list[Take]` replacement of
the audio buffer became a `layers`-shaped list with an invariant, and its
top-row take selector had to move to an encoder — the top row *is* bars 1-8 of
the arrangement. Its "per a setting" became two visible gestures. See the item.

† `NH-10` shipped its probability and `every_n`, but not with the spec's
"per-pass seeded RNG" — a stateful generator is only reproducible if you always
play from the same place, which defeats the one thing the spec asked of it. It
is a **pure function** of position instead. And the spec's brightness-shows-
probability display had to become a flash, because brightness already means
velocity. See the item.

---

## 5. P0 · Foundations

Prerequisite engineering, not wishlist features. These unblock everything else,
so they go first even though only `F-05`, `F-06` and `F-07` are visible to a
user.

### F-01 — Lock-free audio command queue and xrun reporting `size: M`

**Status: shipped.** No lock remains in `audio.py`. The UI thread allocates (a
take buffer, a `Voice`), publishes an immutable `Intent`, and posts one command
tuple; the callback applies it at the top of the next block and clears the
intent only if the UI has not replaced it since.

Two deviations worth knowing. First, the spec said a posted command "is not
observed until the next block", which would have broken every
`engine.play(); assert engine.is_playing` read: instead the getters prefer the
pending `Intent`, so UI reads stay synchronous while the *audio* effect is
deferred. Second, `Stats` carries `callback_ms` and `callback_ms_max` rather
than a p95 (a histogram in the callback is not worth it; the max is what
catches a budget breach). `engine.transport` is now callback-owned — read
tempo through `engine.bpm` / `frames_per_beat` / `frames_per_bar` /
`song_frames`, which are intent-aware. One test assertion moved onto those.

The promised benchmark test is **not** included: a wall-clock budget assertion
is flaky in CI. `stats.callback_ms_max` is the hook for measuring it by hand.

**Problem.** `Engine._sd_callback` takes an `RLock` that the UI thread also
holds while building schedules. Under PortAudio that is a priority inversion:
a UI hiccup becomes an audible dropout. We also ignore PortAudio's `status`
flags, so dropouts are invisible.

**Spec.** Single-writer/single-reader command queue (`queue.SimpleQueue` of
small tuples) drained at the top of `_process`. Public setters (`play`, `stop`,
`arm_record`, `cancel_record`, `preview`, `set_bpm`) post commands instead of
mutating shared state under a lock; the lock is deleted. `set_schedule` keeps
its atomic-reference swap (already safe). Add `Engine.stats` published as a
frozen dataclass snapshot: `xruns`, `peak_out`, `callback_ms_p95`,
`voices_active`. Raise an `("xrun", count)` event when PortAudio reports
input/output overflow or underflow.

**Surface.** When `stats.xruns` increases, `App` shows `"audio dropout"` via
`notify()`. Display row shows peak level once `F-07` lands.

**Code.** `audio.py` (`Engine.__init__`, all public setters, `_process`,
`_sd_callback`), `app.py` (`tick` surfaces the event).

**Tests.** Commands posted before a render take effect at the first frame of
that render; a command posted mid-render is not observed until the next one;
`stats.xruns` increments when `_sd_callback` is handed a status with overflow.
Keep every existing `test_audio.py` assertion passing unchanged — that suite is
the regression net for this refactor.

**Done when.** No `threading.RLock` remains in `audio.py`, all 72 existing tests
pass untouched, and an xrun surfaces as an event.

**Deps.** None. **Land first** — group A is blocked behind it.

### F-02 — Split `modes.py` into a package `size: S`

**Status: shipped.** `modes/` now holds `base.py` (the `Mode` contract plus
`COUNT_IN_BEATS`), `library.py`, `record.py`, `sample.py`, and an `__init__.py`
that re-exports the public names. `base.Mode` also gained an `on_tick()` hook,
called once per event-loop pass, for modes that need a clock (`CC-01` uses it);
it is the sanctioned place for time-based state changes, since rendering must
stay a pure function of state.

**Problem.** 417 lines, three modes, and every future mode in one file. Group D
cannot fan out without conflicts.

**Spec.** `modes/` package: `base.py` (`Mode`, `COUNT_IN_BEATS`),
`library.py`, `record.py`, `sample.py`, and `__init__.py` re-exporting the
public names so `from .modes import LibraryMode` keeps working. No behaviour
change, no test changes beyond imports.

**Code.** `modes.py` → `modes/`; `app.py` imports.

**Tests.** Existing suite passes with zero assertion edits.

**Done when.** `git diff` shows pure moves plus an `__init__.py`; one new mode
can be added as one new file.

**Deps.** Blocks group D. Do immediately after `F-01`.

### F-03 — Mode stack with transient overlays `size: S`

**Status: shipped**, held back until `F-06` gave it a first real caller rather
than landing unused. `App.mode` is now the top of `_modes`, `push_mode` /
`pop_mode` open and close overlays, `goto_library` unwinds the whole stack, and
`Session`/`Stop` pop one layer before heading home. Depth is capped at 4.

**Problem.** `App.set_mode` is flat, so a mode opened from somewhere cannot
return to where it came from. Settings, editor, browser and mixer all need
"open over, then go back".

**Spec.** `App.push_mode(mode)` / `App.pop_mode()` with a stack whose root is
always `LibraryMode`. `goto_library()` clears to the root. Overlay modes set
`transient = True`; Stop/Session pops one level instead of jumping to the root.
The stack is capped at 4 to prevent lostness (principle 2).

**Code.** `app.py`, `modes/base.py`.

**Tests.** Push two overlays, pop returns through them in order; `goto_library`
from depth 3 lands at the root and calls `on_exit` on each unwound mode;
depth cap refuses a fifth push.

**Deps.** `F-02`. Blocks `F-06`, `NF-03`, `NF-06`, `NH-01`.

### F-04 — Undo/redo journal `size: M`

**Status: shipped** in `history.py`, with all seven command types from the spec.
Every mutation in the modes now goes through `app.do(Command)`; nothing writes
`Sample` fields directly. Added beyond the spec: commands can `merge`, so a
gain or tempo sweep from an encoder is one undo step instead of one per click,
and `Sample.set_trigger` now owns the bar-range validation that `toggle` used
to hold, so commands validate too. Undoing a recording returns to the library
when it empties the page you were on.

**Problem.** `Delete` + pad destroys a take with no recourse; a mis-toggled bar
has no undo. The Undo button is dark. This violates principle 4.

**Spec.** A `project.History` of reversible commands — `ToggleTrigger`,
`SetEnabled`, `SetGain`, `PutSample` (keeps the replaced audio), `DeleteSample`,
`SetBpm`, `ClearTriggers`. Every mutation in the modes goes through
`app.do(Command)` instead of touching `Sample` directly. Depth 64, in memory
only (not persisted). `Undo` = undo, `Shift`+`Undo` = redo.

**Surface.** `Undo` (CC 119) lit dim when there is something to undo, off when
not. `notify()` names what was undone: `"undo: bar 12 off"`.

**Code.** new `project_history.py` (or `project.py` if it stays under ~80
lines), `modes/*.py` mutation sites, `app.py` (`do`, `undo`, `redo`, button
binding).

**Tests.** Each command type round-trips (do → undo → state identical,
including audio identity for `PutSample`); 70 operations keep only the last 64;
redo stack clears on a new action; undoing a delete restores triggers, mute and
gain.

**Done when.** Every destructive action in the app is undoable, and deleting a
sample then undoing yields a byte-identical buffer.

**Deps.** `F-02`. Collides with every group B/C item — land early.

### F-05 — Voice envelopes and declicking `size: S`

**Status: shipped**, ahead of `F-01` — there was no contention to avoid with a
single implementer, but `F-01` will have to carry the envelope state across its
refactor. Three deviations from the spec below: the release fade is 10 ms for
both Stop and voice stealing (the spec asked for 5 ms on a steal, which is not
worth a second window); the voice bound is now `MAX_VOICES` *sounding* plus
`MAX_RELEASING` fading out, because a stolen voice has to stay in the mix while
it fades; and eight existing assertions that sampled frame 0 of a buffer moved
to a frame clear of the new fades (`tests/test_audio.py` documents why at each
one).

**Problem.** Voices start and stop at full amplitude. Every take boundary
clicks, voice stealing pops, and `Stop` cuts hard. This is the single most
audible quality problem in v1.0.

**Spec.** Per-voice 3 ms raised-cosine fade-in and fade-out, applied at voice
start, at natural end, and on a forced stop. `Engine.stop()` and mode changes
release voices over 10 ms instead of clearing the list. Voice stealing fades
the stolen voice over 5 ms rather than dropping it mid-cycle. Fade windows are
precomputed once in `__init__`, never per voice.

**Code.** `audio.py` (`Voice` gains `fade_in_left`/`releasing`, `_mix`,
`stop`, `_add_voice`).

**Tests.** First frame of a voice is near zero and reaches unity within 3 ms;
the last 3 ms ramp to zero; after `stop()` the output decays to silence over
≤10 ms with no sample-to-sample step greater than a threshold; a 97th voice
fades the oldest rather than truncating it.

**Deps.** `F-01`. Blocks `NF-05` (bounce quality).

### F-06 — On-device settings page and settings file `size: M`

**Status: shipped.** `settings.py` holds one `Spec` table that supplies the
defaults, the validation *and* the labels and step sizes the page renders with,
so a new setting is one entry rather than edits in four files. Precedence is
defaults -> file -> command line, with command-line values applied as overrides
that are never written back. A malformed file falls back to defaults with a
warning; an out-of-range value is repaired silently.

`SettingsMode` is the first overlay: `Setup` opens and closes it, the pads stay
dark on purpose, and each of the eight buttons under the display owns one
setting with the encoder above it. `Engine.restart_stream` reopens the stream
for device and block-size changes, and on failure restores the old settings,
reopens what was working, and raises an `audio_error` event.

Two deviations. LED brightness is **not** here: the brightness SysEx belongs to
`CC-13` and is unverified, and a knob that does nothing is worse than no knob.
And the page does not describe a failed device change itself -- the engine's
event names the actual problem, which beats anything the UI could invent, so
there is one message per failure rather than two.

**Problem.** Sample rate, devices, latency compensation and count-in length are
CLI-only. A standalone instrument cannot require a terminal to change its
headphone output.

**Spec.** `~/.config/push2sampler/settings.json` (override with
`--settings PATH`) holding audio device names, samplerate, blocksize, channel
counts, `rec_latency_ms`, `count_in_beats`, `monitor_gain`, LED brightness,
autosave delay. CLI flags override the file for one run; the settings page
writes the file. A `SettingsMode` overlay (`Setup` button, unshifted) puts one
parameter per display-row-bottom button and edits it with the encoder above it.
Audio-device changes restart the stream in place and report failure without
killing the app.

**Surface.** `Setup` (CC 30) opens/closes; display rows 20–27 select the
parameter; track encoders 71–78 change values; pads show nothing (all off) so
it is unmistakably a settings screen.

**Code.** new `settings.py`, new `modes/settings.py`, `cli.py` (merge order:
defaults → file → flags), `audio.py` (`Engine.restart_stream`).

**Tests.** Merge order precedence; a bad settings file falls back to defaults
with a warning rather than crashing; changing count-in through the mode changes
the next take's count-in; `restart_stream` failure leaves the old stream running
and raises an event.

**Deps.** `F-03`.

### F-07 — Input metering and monitoring toggle `size: S`

**Status: shipped.** `Stats` carries `input_peak` (with a slow fall-back so a
meter is readable) and `input_rms`; `Engine.input_clipped` latches and
`take_clipped()` reads-and-clears it, which the app turns into a 1.5 s warning
rather than a one-frame flash. Monitoring is the three states from the spec,
cycled with `Shift`+`Metronome`, metered on the eight buttons above the display
and on the status line.

One deviation: the default is **off**, not `auto`. Switching on input->output
routing during an upgrade can physically howl on a speaker setup, and no default
is safe for unknown hardware, so the safe one ships and `--monitor auto` is one
flag (or one button) away.

**Problem.** You cannot see whether the mic is live or clipping until after a
take is ruined, and monitoring is a CLI gain with a feedback footgun.

**Spec.** `Engine` publishes `input_peak` and `input_rms` (decaying, computed
once per block, ~8 numpy ops — safe in the callback) plus a sticky `clipped`
flag reset on read. Monitoring becomes a runtime toggle with three states:
off / on / auto (on in Record mode only, the default). Display shows a
horizontal meter; the top display-row buttons show a coarse LED meter so it is
visible without the screen.

**Surface.** `Shift`+`Metronome` cycles the monitor state. The `Record` button
LED turns solid red when input is clipping.

**Code.** `audio.py` (meter in `_process`, `monitor_state`), `app.py`
(meter → `status_lines`, button LED), `modes/record.py`.

**Tests.** A known-amplitude input yields the expected peak within tolerance;
`clipped` latches on a >1.0 sample and clears on read; `auto` monitoring is
silent in Library mode and audible in Record mode.

**Deps.** `F-01`.

### F-08 — Hardware verification pass and display test harness `size: M`

**Status: the tool is shipped; the human pass is still open.**

`--selftest` (`selftest.py`) walks nine checks: MIDI ports, grid orientation,
the notes the corner pads send, velocity and aftertouch, every palette colour,
35 buttons, four encoders including which way is clockwise, the touch strip, and
the display. Each check records believed-vs-observed, and the run writes
`hardware-report.json` plus a markdown version whose first table is exactly the
list of corrections to make. It is built so one person at the device can do it
alone: press what it names, answer what it asks, Enter skips, `q` quits and
still saves.

`PushBase.capture_raw` was added for it -- a tap that keeps untranslated
messages -- so the probe learns what the device really sends instead of trusting
`translate_midi`. The probe itself is unit-tested by scripting the answers and
the messages (including a flipped grid, a button on the wrong CC and an inverted
encoder), and `tests/test_display.py` pins the frame header, the 327,680-byte
payload, BGR565 packing and the XOR shaping against a fake USB device.

Still open, and only a person with hardware can close it: actually running it,
then correcting `constants.py` and filling in the README table.

**Findings so far** — the first feedback from a real device, logged here as it
arrives:

| # | What was claimed | What the device says | Done |
| --- | --- | --- | --- |
| 1 | Docs told the user to press a `User` button before starting | No such button found on the panel | Docs corrected. The claim was never a code requirement: `Push2.open` picks a port *by name* and sends no mode change, so nothing has to be pressed. `Btn.USER = 59` stays in the map (spec value, unverified, deliberately unbound) and the probe now labels it as possibly absent |
| 2 | Port names `Ableton Push 2 Live Port` / `Ableton Push 2 User Port` | Exactly that, in both directions — and `_pick` chose the User port | **Confirmed.** README table row filled in |
| 3 | The grid lights when we send note-ons | Nothing lit at all; the probe's first check could not be answered | **Open.** `--led-test` (`ledtest.py`) was written to find out which layer is at fault, since "dark" has at least five indistinguishable causes |
| 4 | The palette was the likely culprit | **Not the palette.** `--led-test` reported nothing in *either* direction: no input from any pad, no light from factory indices, none from ours, no button LEDs, no channel. The ports still opened without error | **Open.** Rules out `program_palette`, `index_to_note`, the colour map and the channel in one go — none of them can matter when no traffic passes at all. `--midi-probe` (`midiprobe.py`) was written to measure rather than ask |
| 5 | The surface reports on the **User** port | **No.** Input arrives only on the **Live** port (465 messages by callback, 262 by polling); the User port sent nothing at all. Output reached the device. The Push routes its controls to whichever port matches its mode | **Fixed.** `Push2` now opens *every* Push input port, so the program works in either mode without being told which — only one port sends, so listening to both costs nothing. `--midi-port live\|user` pins either direction. README table row corrected from "assumed User" |
| 8 | Output on the User port reaches the device (the probe's one "yes") | **No.** With input fixed, a normal run still showed nothing: the surface is on the **Live** port in *both* directions. The probe's single "did anything light" question had been asked after blasting both ports, so its yes was unattributable — the fix for that landed too late to help | **Fixed.** Output now *follows the input port*: input is the only signal for which port the device is on, so when a message arrives on a port we are not sending to, output moves there and the surface repaints. `--midi-port` disables the following, since an explicit choice should not be second-guessed. Startup also prints the ports it opened |
| 7 | — | `--midi-probe` left the pads and buttons lit after it finished | **Fixed.** Mine, not the device's: the probe lit everything to ask about it and never turned it off, and the port was closed before the question so nothing could. It now blanks each port after that port's question is answered. Exposed a real gap behind it — `clear()` only turns off LEDs the *current process* lit, so a crash or an early Ctrl-C left the surface lit with nothing able to reach it. `PushBase.all_off` sends an explicit off to every pad and every known button CC, `open()` uses it, and `--lights-off` does it on its own |
| 6 | — | `pyusb` is installed but has no `libusb` underneath (`No backend available`), so the bus check reports nothing either way | **Noted, not fatal.** It is also why the colour display cannot work on this machine: `brew install libusb`. `--midi-probe` now names this separately rather than letting it read as "the Push is not on the bus" |
| 9 | The colour display's framing, packing and XOR shaping, pinned byte-for-byte by unit tests | **The display renders** — first time it has ever been seen to. But the background was **gold with vertical striping** and the text **blue**, from a photograph | **Fixed.** `XOR_PATTERN[0]` was `0xE7F3` — the two bytes of `0xFFE7F3E7`'s low word `0xF3E7` transposed. Both colours are predicted exactly by that: alternate columns cancelled the panel's mask and the rest did not. Now derived from `XOR_MASK32 = 0xFFE7F3E7` rather than typed. The test that should have caught it asserted `pixel ^ XOR_PATTERN[0]` — comparing the constant under test to itself — so it passed on any value at all; the assertions are literal now, plus one that pins the mask against the documented number and one that a black frame shapes back to black |
| 10 | Status lines fit the display | **No.** `0 muted`, `song page  0` and `hold: audit` all ran off the right-hand edge mid-word, in the same photograph | **Fixed.** Nothing measured anything: `draw()` drew each string at x=12 and let PIL clip. `display.fit(text, measure, limit)` binary-searches the longest prefix that fits with an ellipsis on it, and the banner, the text lines and the big readout all go through it. `measure` is a callable so the function is testable without Pillow, which is optional and absent here |

Findings 9 and 10 are the most uncomfortable pair in the list, because both were
in code that had tests, and the tests were the reason nobody looked.

Finding 9's test read `assert words[0] == expected_pixel ^ XOR_PATTERN[0]`. That
is not an assertion about the mask; it is an assertion that XOR is XOR, and it
would have passed for every one of the 65,536 values the constant could have
held. **A test that names the constant under test on both sides of the equals
sign tests nothing.** Write the expected value as a literal, even — especially —
when the literal is ugly, and state it in bytes as well when the failure mode is
a byte order. Finding 10's code had no test at all, for a subtler reason: the
drawing path needs Pillow, Pillow is optional and not installed here, so the
whole of `draw()` was unreachable from the suite and its one test asserted only
that it raises `ImportError`. **An optional dependency at the bottom of a
function makes everything above it untestable.** The fix was to lift the part
with the logic — measure, search, truncate — out into a pure function that takes
the measuring as an argument, and now the suite covers it.

The diagnosis is worth recording too, because the photograph could have led to a
week of guessing at channel order. The background was gold and the text blue,
which reads as "the colours are wrong" — but the *background was drawn black*,
and black is `0x0000`: every channel zero. No permutation of three zero channels
produces gold. So a channel-order error was ruled out by arithmetic before
anything was changed, leaving the mask as the only candidate; from there the
predicted colours for a transposed low word, (165,130,16) on odd columns and
black on even, match the striping in the photograph exactly. **Compute what the
suspected bug predicts and compare it to the evidence** — it is much cheaper
than changing a constant and asking for another photograph.

Finding 1 is one shape to expect: a **documentation** assumption built on a spec
value, where the code was indifferent all along. Check that distinction before
changing anything — the correction is often to prose, not to `constants.py`.

Finding 8 is the cost of finding 4's tooling bug: the unattributable "yes"
sent us on to fix input while leaving output pointed at a port that was never
answering. Two lessons, both cheap to apply next time. **A diagnostic question
must be scoped to one variable** — asking "did anything light?" after exercising
two ports measures nothing, and the fix arrived one round too late to help.
And **asymmetric signals need asymmetric handling**: input carries its own
source port, output carries nothing, so the only sound design is to derive the
output port from the input rather than picking one and hoping. That is what
`follow_input` does.

Also worth noting: `App` never printed which ports it opened, so two rounds were
spent unable to see the most basic fact about the run. Startup now says.

Finding 7 is a reminder that **LED state lives in the device, not in the
program**. Every `set_pad` is a message the Push remembers after we exit, so any
tool that lights something owns turning it off — and the dedupe cache that makes
a 30 Hz refresh cheap is precisely what makes a fresh process unable to clean up
after the last one. `all_off` exists for that seam. Anything added that lights
the surface outside the normal render loop needs the same treatment.

Finding 5 is the one that was worth all of it, and it is the most interesting
correction in the project so far: the program had a *hidden assumption it never
stated*. Choosing the User port by name was written and documented as a
preference — coexist with Live, prefer the port meant for third parties — when
it was in fact a hard requirement that the device does not always satisfy. The
fix is not a better guess about which port to use; it is to stop guessing and
read both. That generalises: where a device offers two of something and the
cost of watching both is nil, watch both.

It is also the second time this class of thing has bitten, after finding 1. Both
were assumptions *about the device's mode* that our own code had quietly built a
dependency on while the docs described it as optional. Worth auditing the rest of
`push2.py` for the same shape.

Finding 4 is the useful kind of negative result: one run eliminated four
candidate causes at once, because none of them can matter when no traffic passes
in either direction. It also reset the order of the diagnostics — an
*interactive* tool is the wrong instrument once "what do you see?" is answered
"nothing", so `--midi-probe` asks almost nothing and instead reports the mido
backend, USB-bus presence via `pyusb` (independent of MIDI), input read by both
callback and polling, and both ports in both directions. It is written to
suspect this program as readily as the device: a callback that stays silent
while polling works is named as a bug in `push2.py`.

Finding 3 is the other kind, and the more expensive one. The probe was built to ask
"is this control on the CC we think?", which presumes the LEDs work; when they
do not, every one of its nine checks returns the same unanswerable silence. A
verification tool needs to establish its own preconditions before it starts
asking questions that depend on them — hence `--led-test` running *before*
`--selftest`, and `--selftest` now saying so when the first check comes back
dark. Worth remembering for `IN-07` and anything else built on the display.

**Problem.** `display.py`, `Push2.program_palette`, the button CC map and the
`sounddevice` callback have never been exercised against a real Push 2 in this
repo. The port names, palette SysEx and the 16-byte display frame header come
from the Push 2 MIDI and Display Interface spec, not from observation.

**Spec.** (a) A `--selftest` command that, with hardware attached, walks the
grid, lights every palette colour, prints every received CC so the map can be
confirmed, and draws a display test card. (b) A `FakeUsb` device object so
`Push2Display.draw_image` can be unit-tested: assert the frame header, the
327,680-byte payload size, BGR565 packing of known pixels and the
0xFFE7F3E7 XOR shaping. (c) A documented checklist in `README.md` of what was
confirmed on which firmware. (d) Fix whatever the real device disagrees with.

**Code.** `cli.py`, `display.py`, `push2.py`, new `tests/test_display.py`.

**Tests.** Byte-level assertions against `FakeUsb`; `open_display()` returns
`None` (never raises) when pyusb, Pillow, or the device is missing.

**Done when.** A human has run `--selftest` on a real Push 2 and the checklist
is filled in, or the item is explicitly deferred with the untested surface
listed in the README.

**Deps.** None. Needs hardware access — see §12.Q1.

### F-09 — Make bar-length and audio-length agree `size: S`

**Status: shipped.** Takes record `source_bpm` and `source_samplerate`;
`Project.length_error`/`mismatched` ask the one question that matters -- does
this audio still fill its declared bars at the project's tempo -- which catches
both a tempo change and audio that was never bar-aligned. Flagged slots are
yellow in the library, their page explains the error in bars and names the
tempo it was cut at, and the first button under the display repairs it
(undoable, via a `RepairLength` command that also clears `audio_saved` so the
WAV is rewritten). `FORMAT_VERSION` is 2; format-1 takes infer their provenance
from the project tempo so existing songs do not open covered in warnings.

Deviation: `bars` stays stored rather than being derived from audio length,
with `Sample.bars_at()` exposing the measured figure instead. Deriving it would
silently rewrite the arrangement's idea of a loop's length; flagging the
disagreement and letting the player decide is the better trade.

This turned up honest-to-goodness test debt: several fixtures fabricated
"1 bar" samples out of 10 frames, which is exactly the lie this item catches.
They now build real-length takes through a `take()` helper.

**Problem.** `Sample.bars` is metadata; `Sample.audio` is the truth. Loading a
project recorded at another tempo, or an imported WAV, can leave a "2 bar"
sample whose audio is 3.7 bars. Everything downstream (bounce, stretch,
slicing) needs one source of truth.

**Spec.** Store `source_samplerate` and `source_bpm` on each `Sample` and derive
`bars` from audio length and the recording tempo. Add
`Sample.expected_frames(transport)` and a `length_mismatch` property. On load,
if the mismatch exceeds 1 %, keep the audio and flag the sample; a flagged
sample shows a yellow pad in the library and an explanation in the display.
Provide `Project.repair()` to pad or trim to the exact bar length on request.

**Code.** `project.py`, `modes/library.py` (flag colour), `wavio.py` if needed.

**Tests.** A sample recorded at 120 and loaded at 140 is flagged, not silently
wrong; `repair()` makes the length exact; `FORMAT_VERSION` bump loads v1 files
by inferring `source_bpm` from the project tempo.

**Deps.** None. Blocks `NH-09`, `NF-05`, `IN-01`.

---

## 6. New features

Substantial, user-visible capability. These are the reasons someone picks this
up instead of a hardware looper.

### NF-01 — Song page: see all 64 bars × all samples at once `size: L`

**Status: shipped.**  `modes/song.py`.  Density ramp reuses the existing palette
as the spec asked (off / dim blue / blue / amber / white at 0 / 1 / 2-3 / 4-7 /
8+), and the playhead brightens its whole column one rung rather than drawing
over it, so the density stays readable underneath.  Zoom maps (col,row) to
(bar, slot) through the same `app.bar_at` window the sample page uses, so a
zoomed toggle and a sample-page toggle are the identical `ToggleTrigger`.

Two additions the spec did not ask for and the page wanted: `Delete` clears a
whole cell (eight bars of eight slots), and the overview counts only the
visible page and bank -- with 256 bars and 256 slots an "everything" heat map
would be four pads per cell and unreadable.

**Problem.** The arrangement is only visible one sample at a time. You cannot
see the shape of the song, find the empty bars, or spot bar 33 being bare.

**Spec.** A `SongMode` showing the arrangement as an 8×8 heat map: **columns are
8-bar sections** (column 0 = bars 1–8 … column 7 = bars 57–64), **rows are slot
banks of 8** (row 0 = slots 1–8 …). Each pad's colour encodes density: off = no
triggers in that cell, dim blue 1, blue 2–3, amber 4–7, white 8+. The playhead
column is outlined by brightening the whole column one step. Pressing a pad
zooms into that cell: the grid becomes the 8 bars × 8 slots of that cell, where
each pad directly toggles "slot S plays on bar B". `Page ◀/▶` moves the zoom,
`Clip` toggles overview/zoom, `Session` exits.

**Surface.** `Clip` (CC 113). New palette entries may be needed for the density
ramp — reuse existing blue/amber/white rather than adding four new ones.

**Code.** new `modes/song.py`, `app.py` binding; read-only against
`Project` plus existing toggle paths via `app.do()` (`F-04`).

**Tests.** Density colours for 0/1/3/5/9 triggers in a cell; zoom maps
(col,row) → (bar, slot) correctly for all 64 cells; toggling in zoom mutates
the same `Sample.triggers` the sample page does; playhead column brightening
at bar 17.

**Done when.** A song with 12 samples is legible at a glance and editable
without leaving the page.

**Deps.** `F-02`, `F-03`, `F-04`. Pairs with `NF-11`.

### NF-02 — Per-sample playback behaviour `size: M`

**Status: shipped.** `Sample.play_mode` and `Sample.choke_group` ride through
`ScheduledSample` into `Voice`, and every ending is decided at a bar line --
which the engine already splits every block at, so a gate's release starts on
the exact frame of the line whatever the block size is. `_end_voices` runs
*before* `_start_scheduled` on each line, because otherwise a retrigger or a
choke cuts the voice it has just started. A renewed loop is one voice rather
than two: `_start_scheduled` skips a loop whose slot is already sounding.

Deviations, all small and all forced:

- **Button layout.** The plan wanted display-row buttons 1-4 for the modes and
  5-8 for the group. Button 1 is already the off-grid repair, and eight groups
  plus "off" do not fit in four buttons -- so the modes sit on 2-5 and the group
  cycles on 8, where the display names the value.
- **A slot never chokes its own voices.** The plan did not say either way.
  Choking its own would make `one_shot` inside a group behave exactly like
  `retrigger` with no way to ask for anything else, so the group's business is
  with *other* samples and a sample's business with itself is `play_mode`.
- **The loop seam keeps its fades.** A looping voice wraps through the buffer's
  own 3 ms head and tail fades, so the seam is a small dip rather than the click
  a hard splice gives. `test_the_loop_seam_is_a_fade_not_a_gap` measures it and
  bounds it at two fades, which is also what would catch the wrapping fill
  breaking and leaving the rest of a block silent.

One thing fell out of building it: the mixer needed a second fill path. A loop
point that lands mid-segment would otherwise leave the remainder of the segment
silent, so `_mix_looping` continues from the top of the buffer. For an on-grid
take the loop point *is* a bar line and the segment is already cut there, so the
general path only earns its keep on trimmed or odd-length takes -- but those are
exactly what the editor produces.

**Problem.** Every sample is a one-shot that plays to its end. Real looping
instruments need gates, loops and chokes — a 4-bar pad that should stop when
the next chord arrives currently bleeds over it.

**Spec.** `Sample.play_mode` ∈ `{one_shot, loop, gate, retrigger}` and
`Sample.choke_group` ∈ `{None, 1..8}`.
- `one_shot` — today's behaviour.
- `loop` — repeats until a bar where the sample is not triggered, then fades
  (uses `F-05`'s release).
- `gate` — stops at the end of the bar it started in, regardless of audio
  length.
- `retrigger` — a new trigger on a bar cuts the previous voice of the same slot.
Samples sharing a choke group cut each other. `ScheduledSample` carries the mode
and group; `Engine` grows a per-group "currently sounding voice" map. Bar-end
stops are scheduled at segment boundaries — never by polling.

**Surface.** On the sample page, display-row-bottom buttons 20–23 select the
play mode, 24–27 select the choke group; both shown in `status_lines`.

**Code.** `audio.py` (`ScheduledSample`, `_fire_boundaries`, `_mix`),
`project.py`, `modes/sample.py`.

**Tests.** A loop sample triggered on bars 0–1 plays continuously across the
boundary and releases during bar 2; a gate sample shorter than a bar is
unaffected and a longer one is cut at the bar line; retrigger leaves exactly one
voice for that slot; two samples in choke group 1 never sound together.

**Deps.** `F-01`, `F-05`.

### NF-03 — Sample editor `size: L`

**Status: shipped.** `edits.py` holds a frozen `Edits` (trim in/out, fades,
pitch, reverse, normalise) and renders it on the way to the mixer, in a fixed
order that is documented because it matters. `Sample.effective_audio()` caches
the result and hands back the recording *by identity* when there are no edits,
so the editor costs nothing until it is used. `SampleEditMode` gives each of the
eight encoders one parameter with the button under it resetting or toggling it,
draws the take across the 64 pads by loudness with the trimmed parts in dim red,
and auditions from a pressed pad. `Shift`+`Device` commits destructively as one
undo step.

Deviations: gain sits on the encoder row although it is a `Sample` field rather
than an `Edits` one, because from the player's side it is the same kind of
knob. The waveform is drawn on the **pads** and as a one-line text envelope
rather than as a picture on the colour display -- it works with or without a
screen, which at the time this shipped had never been verified. The screen has
since rendered (`F-08` findings 9 and 10), so a real drawing is now a question
worth asking rather than a bet on unproven hardware.

Two things fell out of building it. A trimmed take is genuinely shorter than its
bars, so `F-09` flags it as off-grid -- correct, and worth knowing before someone
reports it as a bug. And `Edits.from_dict` now coerces **per field**: the first
version stored whatever was in the JSON, so one bad value in a hand-edited
project file would have crashed inside the renderer rather than at load.

**Problem.** A take is take-it-or-leave-it. A great loop with 40 ms of silence
at the front, or 3 dB too quiet, has to be re-recorded.

**Spec.** A `SampleEditMode` overlay (`Device` button from a sample page) with
non-destructive edits stored on the `Sample` and applied at load/schedule time:
`trim_start`, `trim_end` (frames), `gain`, `reverse`, `fade_in_ms`,
`fade_out_ms`, `pitch_semitones` (−12…+12 via `wavio.resample`, length
changes), `normalize` (computes a gain, does not rewrite audio). Encoders
71–78 map one-to-one onto those parameters with the names on the display.
`Shift`+`Device` applies the edits destructively (with `F-04` undo).
The display draws the waveform with trim handles and the bar grid overlaid.

**Surface.** `Device` (CC 110). Pads: top row = zoom/scrub positions, rows 2–8
off. Keep it encoder-driven, not pad-driven.

**Code.** new `modes/sample_edit.py`, `project.py` (edit fields + an
`effective_audio()` that caches the rendered result and invalidates on change),
`display.py` (waveform drawing), `wavio.py` (reverse/fade/normalize helpers).

**Tests.** Each edit independently, then composed, against known buffers;
`effective_audio()` caches (second call returns the same object) and
invalidates on parameter change; a pitched-up sample is shorter by the right
ratio; edits survive save/load; the scheduler sees the edited audio.

**Deps.** `F-03`, `F-04`, `F-09`. Wants `F-08` for the display half.

### NF-04 — Live quantized triggering and arrangement overdub `size: L`

**Status: shipped.** `Engine.trigger()` schedules a voice on a future frame, the
callback computes the grid line (so it is exact however late the pad was hit),
and `_segment_limit` will not step over a pending start. `PerformMode` is a
transient overlay on `Shift`+`Play`; `Fixed Length` cycles quantize;
`next_grid_bar()` tells the mode which bar a hit will land in, which is what gets
written.

Three deviations. Quantize is expressed **in beats** (0/1/2/4) rather than
fractions of a bar -- the same four choices, simpler arithmetic, and it survives
a change of time signature. Erase uses the existing armed `Delete` rather than a
held one, because `Delete` is already a latch everywhere else in this program.
And erasing **starts at the next bar line** rather than the bar already playing:
the first version wiped a bar that was nine-tenths over, which felt like erasing
the past. Velocity still does nothing here; that is `NF-10`, and perform mode is
what makes it the obvious next feature.

**Problem.** The only way to arrange is to toggle bars while stopped. You cannot
play the song in, which is how people actually write.

**Spec.** A `PerformMode`: with the transport running, pads fire their slot
immediately, quantized to the next grid unit (off / ¼ / ½ / 1 bar, chosen with
`Fixed Length`). When `Record` is held or armed, each fired trigger is *written*
into the arrangement at the quantized bar — overdubbing the 64-bar grid live,
with the loop repeating. `Delete` held while the transport runs erases triggers
in the bars it passes over (classic "erase while looping"). Pads show slot state
(green filled, amber sounding) like the library, so `PerformMode` is the library
with live behaviour.

**Surface.** Reached by holding `Shift` and pressing `Play`, or a display-row
button from the library. `Fixed Length` (CC 90) cycles quantization, shown on
the display.

**Code.** new `modes/perform.py`, `audio.py` (`Engine.trigger_now(slot, quantize)`
posting a command that schedules the voice at the next grid frame),
`app.py`.

**Tests.** With quantize = 1 bar, a trigger posted mid-bar sounds at the next
bar's exact first frame; with quantize = off it sounds in the same block;
record-arm writes exactly one trigger per fired pad at the quantized bar;
erase removes only triggers in the bars the playhead crossed while held.

**Deps.** `F-01`, `F-04`. Strong pairing with `NF-10` (velocity → gain).

### NF-05 — Bounce the song and export stems `size: M`

**Status: shipped.** `render.py` renders on a throwaway offline engine, so a
bounce never disturbs the live one. `BounceJob` renders a chunk at a time and is
stepped by the event loop, which keeps the surface responsive **without threads
or locks** -- rendering is numpy, so a two-minute song takes a second or two
spread over a handful of frames, and the pads show it as one progress bar.
`--bounce` and `--stems` need no MIDI, no PortAudio and no hardware at all.
Stems sum back to the mix exactly, which is the property worth testing.

**Problem.** Nothing leaves the box. Work done here cannot be shared, finished
elsewhere, or even listened to away from the device.

**Spec.** `Project.render(engine_like, bars=None, tail=True)` drives
`process_offline` faster than real time to produce a float32 mix of the whole
song, including tails past bar 64 until voices are silent. CLI:
`--bounce out.wav` (render and exit, no hardware needed) and `--stems DIR`
(one WAV per slot, mixed at its own triggers with the same timing). On-device:
`Shift`+`Record` from the library bounces to `<project>/bounces/<timestamp>.wav`,
with progress on the display and the pads filling as a progress bar.

**Code.** new `render.py`, `cli.py`, `modes/library.py`, `project.py`.

**Tests.** A one-bar DC sample triggered on bars 0 and 2 bounces to a file whose
non-silent regions are exactly those bars; stems sum (within float tolerance)
to the mix; tail rendering captures a sample that overruns bar 64; muted samples
are excluded from the mix but still exported as stems; bouncing requires neither
PortAudio nor MIDI.

**Deps.** `F-05` (declick, or the bounce has the clicks baked in), `F-09`.

### NF-06 — Project browser on the device `size: M`

**Status: shipped.**  `ProjectSummary.read` parses one `project.json` and
nothing else, so the browser draws 64 projects without loading a single WAV --
which is the whole reason `scan()` is separate from `load()`.  A project whose
manifest will not parse is still *listed*, honestly empty, rather than hidden:
it is a directory someone made.

`App.open_project` saves the outgoing project, stops the transport, and swaps
the `Project` with the audio stream untouched, as specified -- reopening the
device would click and might not reopen at all.  The undo journal is cleared on
the way, because it described the other song.

Deviations: the root is the folder the current project lives in rather than a
configurable setting (one less thing to set, and it is where you already are),
and rename is not built -- `duplicate` plus a name from the date and a word
covers what rename was for, and a second word-picker page for directory names
would be a lot of surface for very little.  Delete is hold-to-confirm because
it is the one action in the program undo cannot reach.

**Problem.** One project per CLI invocation. Switching songs means quitting to a
terminal.

**Spec.** `BrowserMode` (`Browse` button) listing project directories under a
configurable root (default `~/push2sampler/`). Pads = projects, 64 per page,
coloured by "has audio" (green) / "empty" (white); display names the highlighted
project, its tempo, sample count and date. Actions on display-row buttons: open,
new, duplicate, rename (from a preset word list — no text entry on pads), delete
(hold to confirm). Opening saves the current project first, stops the transport,
and swaps the `Project` in place without restarting the audio stream.

**Code.** new `modes/browser.py`, `app.py` (`App.open_project(path)`),
`project.py` (`Project.scan(root)` returning lightweight summaries without
loading audio).

**Tests.** `scan()` on a directory of three projects reads metadata without
loading WAVs; `open_project` saves the outgoing project, rebuilds the schedule
and resets modes to the library; duplicate produces an independent copy
(changing the copy does not touch the original).

**Deps.** `F-03`, `F-06`.

### NF-07 — Four banks of 64 slots `size: M`

**Status: shipped**, with the model kept flatter than the spec offered.  Rather
than `list[list[...]]` or a `(bank, slot)` key, `Project.slots` is one list of
256 and **slot identity stays a single integer** -- `bank = slot //
BANK_SLOTS`.  Every undo command, velocity map, schedule entry, stem filename
and mixer strip therefore kept working unchanged; a tuple key would have touched
all of them.  The grid is a *window*: `App.slot_at` / `App.pad_of_slot` are the
only code that knows which bank is showing.

`Page ◀/▶` switches bank and a quarter-second full-grid flash says you moved.
`Shift`+`Page` had to go to `NF-11`'s song page -- the two items both claimed it
-- so "jump to the first/last used bank" is **not built**; it was a convenience
and the page switch is not.

**Problem.** 64 samples is a limit you reach in an afternoon; a kit alone can
eat 16.

**Spec.** Four banks (A–D) of 64 slots = 256 samples. `Page ◀/▶` switches bank,
`Shift`+`Page` jumps to the first/last used bank. Bank letter and fill count on
the display; a one-shot full-grid colour flash on switch so you always know
where you are. The song schedule spans all banks — a bank is a *view*, not a
song section. `Project.slots` becomes `list[list[Sample | None]]` or a dict keyed
`(bank, slot)`; `build_schedule` walks all banks.

**Code.** `project.py` (model + format version + migration), `modes/library.py`,
`modes/sample.py` (slot identity becomes `(bank, slot)`), `app.py`.

**Tests.** A v1 project loads into bank A; triggers in bank C play in the
schedule; slot identity round-trips through save/load; `first_empty()` crosses
bank boundaries; the library renders bank B independently of bank A.

**Deps.** `F-04`, `F-09`. Collides with `NF-11` in `project.py` — sequence them.

### NF-08 — Import samples from disk `size: M`

**Status: shipped.** `importer.py` holds the part with no UI in it -- `probe`
(a header read, so drawing a folder does not load gigabytes, the same reason
`Project.scan` reads `project.json` rather than the takes), `listing`,
`bars_for` and `make_sample` -- and `modes/import_browser.py` draws it on the
pads. `Shift`+`Browse` opens it; `--import FILE [--slot N]` does the same with
no hardware at all.

It refuses two things on purpose, and both refusals are the feature:

- **No stretching.** A 3.5-bar file goes in at 3.5 bars and is flagged off-grid
  by `F-09`'s existing machinery, with the same one-button repair. Silently
  time-stretching someone's audio to fit a grid it was never on would be
  unrecoverable, and nobody asked for it.
- **No pretending about formats.** `.wav` through the standard library always;
  everything else only with `soundfile`, and without it the pad is still listed
  and says `needs soundfile for .flac files -- pip install soundfile` when
  highlighted, rather than failing when pressed.

Deviations: the browser is one page of 64 and says how many entries it left out,
rather than paging -- paging needs somewhere to put a page number and nothing
else on this surface has one yet. The shared list/paging helper the plan wanted
factored out of `modes/browser.py` was **not** built: the two browsers turned
out to share almost nothing but "64 pads, highlight then act", and a helper
abstracting that would have been longer than either.

Two bugs it introduced and had to have fixed before it shipped:

- **`App.import_target` had a dead branch.** It preferred "the slot you are
  looking at" when empty -- but `goto_sample` sends an empty slot back to the
  library, so a sample page only ever shows a *filled* slot and the branch could
  never fire. Removed rather than kept as a comforting no-op.
- **The first press on the top-left pad acted instead of highlighting**, because
  `selected` defaulted to 0. Every other pad took two presses, and the action can
  be an import, so the inconsistency was also the dangerous direction.
  `selected` starts at `None` now, and a test pins it.

And one already-known bug repeated itself: `_go` notified the directory name
straight after `refresh` notified "nothing to import", burying the useful
message behind the useless one -- exactly what hid the auto-normalise note
behind a page change in `v1.2`. There is now one `_announce` that says whichever
is true.

**Problem.** You can only use what you record. Drum hits, one-shots and stems
you already own are unreachable.

**Spec.** `Shift`+`Browse` opens an import browser over a configured samples
root: directories as pads (white), audio files as pads (blue), display shows the
highlighted file name, length and rate. Pressing assigns the file to the first
empty slot (or a chosen slot), resampling to the session rate and computing
`bars` from the session tempo, flagging a mismatch per `F-09` rather than
stretching. Supports `.wav`; `.flac`/`.aiff`/`.mp3` only when `soundfile` is
present, with a clear message when it is not. CLI equivalent:
`--import FILE --slot N`.

**Code.** new `modes/import_browser.py`, `wavio.py` (format probing),
`project.py`, `cli.py`.

**Tests.** Import at a different rate resamples and reports the right bar count;
a 3.5-bar file is flagged not stretched; a missing codec produces a message, not
a traceback; import is undoable.

**Deps.** `F-09`, `NF-06` (shares the browser widget — build the list/paging
helper once, in `modes/browser.py`).

### NF-09 — MIDI clock and Ableton Link sync `size: L`

**Status: MIDI clock shipped; Link is a seam only.** `clock.py` holds the role
interface, the PLL, the master emitter and the Link stub. `clock_role` and
`clock_port` in settings, `--clock` and `--clock-port` for one run.

**The plan's own advice was the most valuable line in it.** "Prototype the PLL
in a throwaway script before touching `audio.py`" -- done, and the throwaway
caught four things that would each have been a bad day in `audio.py`:

1. **Comparing against a quantised position.** Reading our position on the UI
   tick means comparing against something rounded to 1/24 beat: 21 ms at 120
   BPM, so ±1 ms was arithmetically impossible. Phase is now compared *at tick
   arrival*, where the sender's position is exactly `n / 24`.
2. **Mixing an additive integral with a multiplicative proportional term**,
   which leaves a standing tempo offset -- a 120 BPM source settled at 122.
   Both corrections are multiplicative now, so both vanish at zero error.
3. **An integral not scaled by the tick interval**, which made the loop half as
   fast at half the tempo and left 3.6 ms of error at 60 BPM.
4. **No model of actuation delay.** The prototype applied tempo instantly; the
   real loop can only act on the 30 Hz UI pass. That is a 33 ms delay the
   prototype could not see, and it is why the first real measurement was 7.8 ms
   rather than the predicted 0.2 -- a reminder that a prototype validates the
   maths, not the plumbing.

A fifth bug was in the real code and only the real rig could find it: `poll`
carried each tick's own index and then compared against the *latest* tick count,
overstating the sender's position for every tick but the last in a drained
batch. It showed up as a constant 15 mbeat offset the integrator could not
remove, because it was not an error the loop could act on.

Measured over 32 bars against a synthetic sender: **0.28 ms** steady at 120,
0.28 ms from a cold start at the wrong tempo, 0.23 ms after a 2:1 cold start,
1.25 ms through a ±3 % wobble, 3.6 ms with 1 ms of arrival jitter, and never a
backwards step in the music.

**The engine needed one change, and it was a bug fix rather than a feature.**
Position is kept in frames and a beat is `60/bpm*rate` frames, so changing the
tempo *reinterpreted* the same frame count: 64000 frames was bar 4 at 120 BPM
and bar 8 at 240. Doubling the tempo teleported the playhead four bars forward
with no audio in between -- so tapping a tempo mid-song moved where you were in
it, and nudging ±0.1 BPM at bar 200 moved you by a fifth of a bar. `set_bpm`
now preserves the musical position. This was not a sync bug; sync merely made
it impossible to ignore, because a control loop whose actuator instantly moves
the thing it measures -- by an amount proportional to how far into the song you
are -- cannot be tuned at all.

Deviations:

- **Link is a seam, not a feature**, and says so. The lazy import and the
  absent-safe fallback are real and tested; nothing behind the import has ever
  run, because the native library has not been available in any environment
  this code has been in. `--clock link` reports `link unavailable` and leaves
  you on the internal clock.
- **No `frames_per_beat` PLL.** The plan wanted the loop to adjust
  `frames_per_beat` gradually; it adjusts `bpm`, which *is* `frames_per_beat`
  by another name and goes through the one setter that already refuses mid-take
  and already clamps. The engine's transport was not touched.
- **The master emits from a thread watching the engine position**, not from the
  callback (which would allocate and do IO) and not from the wall clock (which
  would drift from the audio device). One millisecond of poll granularity.
- **No sync offset calibration.** A constant offset between arrival and audio
  is a real thing that real gear will show, and the loop locks to whatever it
  measures. Noted in troubleshooting rather than guessed at; it wants a real
  device on the other end before a control is added for it.

**Still unverified, and honestly so:** neither role has been run against real
gear. The numbers above are real measurements of real code driven by a
simulation. This is the same class of risk as `F-08`, and it wants the same
treatment -- a human, a drum machine, and a report.

**Problem.** The sampler is an island. It cannot play in time with a drum
machine, a modular setup, or a friend's laptop.

**Spec.** Three clock roles, chosen in settings: `internal` (today), `midi_slave`
(follow MIDI clock + start/stop/song-position on a selectable input port), and
`midi_master` (emit 24 ppqn clock, start/stop, and song position). Slaving drives
the transport from a phase-locked loop that smooths jitter and adjusts
`frames_per_beat` gradually — never by jumping `_pos`. Ableton Link behind an
optional `LinkClock` that imports `link` lazily and is absent-safe.

**Code.** new `clock.py` (role interface + PLL), `audio.py` (transport accepts an
external tempo/phase source), `push2.py` (a second MIDI port for clock, separate
from the surface), `settings.py`.

**Tests.** A synthetic 24 ppqn stream at 120 BPM drives the transport to within
±1 ms over 32 bars; a ±3 % tempo wobble is smoothed without the playhead
jumping backwards; song-position-pointer seeks to the right bar; master mode
emits exactly 24 clocks per beat; Link absence leaves internal clock working.

**Deps.** `F-01`. Highest-risk item in the plan — prototype the PLL in a
throwaway script before touching `audio.py`.

### NF-10 — Velocity and pressure `size: S`

**Status: shipped** (velocity; aftertouch is still unused, and the probe will
say whether it even arrives). `Accent` turns velocity response on per sample,
off by default so every existing project plays exactly as before. In perform
mode a hit's level is scaled by how hard it was, and a hit written into the
arrangement keeps its velocity, so a played-in part keeps its dynamics. The
sample page shows that as three greens.

**Deviation: `triggers` stays a `set`**, with a parallel
`velocities: dict[bar, int]` holding only the bars that were *not* played flat
out. The item called for turning `triggers` into a dict, which would have
rewritten every consumer and ~20 test assertions for no user-visible gain. The
invariant (velocity keys are a subset of triggers) lives in one place,
`Sample.set_trigger`, which discards a velocity when its bar is turned off --
so the two cannot drift. A missing entry means full, which is also what makes
the format change backward compatible.

This is why the `triggers`-type collision warned about in `NF-01`, `NF-07`,
`NH-05` and `NH-06` no longer exists: there is no type change.

**Problem.** `PadEvent.velocity` is captured and discarded. A drum pad that
ignores how hard you hit it is not an instrument.

**Spec.** `Sample.velocity_sensitivity` (0…1, default 0 so v1 projects are
unchanged). In `PerformMode` (`NF-04`) a trigger's gain is
`gain × (1 − s + s × (v/127))`. Triggers written into the arrangement store
their velocity (`triggers` becomes `dict[int, int]` — bar → velocity, with
127 default), so a recorded performance keeps its dynamics. On the sample page,
a trigger's pad brightness reflects its velocity (dim green → bright green).
`Accent` toggles sensitivity for the selected sample.

**Code.** `project.py` (`triggers` type change + migration — touches every
consumer), `audio.py` (`ScheduledSample.gain` already exists; per-trigger gain),
`modes/sample.py`, `modes/perform.py`.

**Tests.** Migration of a set-based v1 `triggers` to the dict form; a velocity-64
trigger at sensitivity 1.0 is ~half amplitude; sensitivity 0 ignores velocity
exactly; pad brightness buckets.

**Deps.** `F-09`, `NF-04`. The `triggers` type change collides with `NF-01`,
`NF-07`, `NH-05`, `NH-06` — do it **before** them or accept the merge cost.

### NF-11 — Song pages beyond 64 bars `size: M`

**Status: shipped.**  `Sample.triggers` keys are absolute bars 0-255 exactly as
the spec predicted, so the model really did barely change; the pads became a
window via `App.bar_at`.

`audio.py` gained a **loop range** in place of "song length": `Engine.loop_range`
is written as one tuple, because two separate ints could be read torn into a
start past its own end.  `Repeat` cycles page / song / off, `end_frames` is the
one boundary `_wrap_song` and `_segment_limit` respect, and the wrap carries the
overshoot across so looping does not quantise the playhead to a block boundary
once per pass.  `Play` starts at the loop start, which with a page loop is the
page you are working on.

A trigger past the last page is dropped on load with a warning on the display,
as specified -- and so is a slot outside the library, which the spec did not
mention but the same file can contain.

One consequence worth its own line: **a bounce now renders to the last bar in
use**, not to the nominal song length.  Four pages are available and most songs
use one, so the old behaviour would have put two minutes of silence on the end
of every export.

**Problem.** 64 bars is about two minutes. Songs are longer.

**Spec.** Four song pages (A–D) of 64 bars = 256 bars, playing consecutively,
with a per-page loop toggle so you can loop one page while working. The pads
always show one page; `Shift`+`Page ◀/▶` changes it. `Project.song_bars` becomes
`64 × page_count`; `Sample.triggers` keys become absolute bar numbers (0…255) so
the model barely changes. The song page indicator and the loop range are on the
display. `Repeat` cycles loop scope: page / whole song / off.

**Code.** `project.py` (page count, format version), `audio.py` (loop range
instead of "song length"), `modes/sample.py`, `modes/song.py`, `app.py`.

**Tests.** Loop range honours page bounds; a sample triggered at bar 200 plays;
the playhead wraps at the loop range not the song end; v1 projects load as a
single page; a trigger beyond the last page is dropped on load with a warning.

**Deps.** `NF-01`, `NF-07` (both touch the same model — strict sequencing).

---

## 7. Nice to have

Valuable, not load-bearing. Each is independently shippable.

### NF-12 — Master playback mode `size: M`

**Status: shipped.** `Shift`+`Session` opens `modes/master.py`: the library
grid, honouring the current bank, with each pad flashing white as its sample
fires and falling back to the slot's own colour. Delete, Mute and Duplicate are
inert and say so. The display counts how many slots fired in the bar you are in.

The engine gained the one thing it was missing, exactly as the item predicted:
`Engine.fired`, the slots that *started* a voice in the last block, published
per block beside `sounding`. Recorded in `_add_voice` rather than in
`_start_scheduled`, so a sample fired by hand in perform mode or auditioned
from the library flashes too -- every attack goes through that one door.

Deviations:

- **The flash is timed in the mode, not off `App.blink`.** The item asked for
  blink so the surface stays on one heartbeat, but blink is a 2 Hz square wave
  and cannot express steps inside 180 ms. It is still no new machinery: a dict
  of timestamps read on the render pass, no timer and no thread.
- **The flash is white, not a brighter slot colour.** The palette has
  brightness steps for white and green only; the eight user colours have no dim
  variants, so white is the one flash that reads the same against every resting
  colour. Two steps rather than the three the item guessed at.
- **It replaces the page rather than layering.** A transient would make
  `Session` mean "back to the editor", which is the opposite of what it should
  mean on a page you settle into.

One bug, found by its own tests: `_firing` was cleared *after* `_apply_commands`,
so an attack from a queued command -- an audition, a pad played in perform mode
-- was thrown away in the same block it happened.


**Problem.** There is nowhere to just *watch the song play*. The library grid
shows what exists, a sample page shows where one take plays, and the song page
(`NF-01`) shows the arrangement as a heat map — but none of them is the view you
want while the whole thing runs and you are listening rather than editing. You
currently have to pick a sample page and watch one row of the truth.

**Idea.** A mode whose whole job is playback: the **library grid**, all 64
slots where they always are, and each pad **flashes as its sample fires**. One
glance tells you what is sounding, what is about to come in, and which slots are
silent through this section. It is the arrangement seen from the samples' side
rather than the bars' side.

**Spec.**

- New `modes/master.py`, `MasterMode`, reached by `Shift`+`Session` (free —
  `Session` alone is "back", and this is the one page you do not go "back"
  from). `Session` leaves, like everywhere else.
- The grid is the library's, honouring the current **bank** so all four banks'
  worth is reachable with `Page ◀/▶`. A slot's own colour (`CC-18`) is its
  resting colour, dimmed.
- **The flash is the feature, so it has to be right.** A pad goes to full
  brightness on the frame its sample is *triggered*, and decays back to its
  resting colour over a fixed time rather than staying lit for the sample's
  whole length — a 4-bar pad that stayed bright for four bars would tell you
  nothing, and 64 pads at full brightness is the glare `CC-13` exists to avoid.
  Suggested 180 ms of decay in three steps (bright → on → dim → resting), which
  at 120 BPM reads as a clear hit on every 8th note without smearing.
- Decay is driven from `App.blink`'s existing clock rather than a new timer, so
  the whole surface stays on one heartbeat.
- `Engine.sounding` already reports which slots have a live voice, and
  `slot_peaks` already reports their levels. Neither is a *trigger* signal: a
  sample sounding for four bars is in `sounding` for all of it. **The engine
  needs a "fired this block" set** — cheap, since `_start_scheduled` already
  knows — published the same way `sounding` is.
- Transport controls work as everywhere (`Play`, `Stop`, `Shift`+`Stop`), and
  `Delete`/`Mute`/`Duplicate` are deliberately **not** armed here: this is the
  one page where a stray press should do nothing destructive. Pressing a filled
  pad auditions it (`CC-01`'s gesture) rather than opening its page.
- The display names it and shows the bar, the loop scope, and how many slots
  fired in the last bar — a number that tells you whether a section is as busy
  as it feels.

**Code.** `audio.py` (a `fired` set published per block, alongside `sounding`),
`app.py` (`open_master`, `Shift`+`Session` dispatch), new `modes/master.py`,
`sim.py` (a name for the gesture — see `CC-15`'s standing rule).

**Tests.** A slot triggered on bar 1 flashes on bar 1 and has decayed by bar 2;
a 4-bar sample flashes once rather than staying lit; two samples on the same bar
both flash; the resting colour is the slot's own colour dimmed; nothing
destructive is reachable from the mode; the bank window moves with `Page ◀/▶`;
`fired` is empty in a block with no bar line in it.

**Deps.** `NF-02` (the engine already distinguishes starting from sounding),
`CC-18` (slot colours), `NF-07` (banks). Wants `CC-13`'s dim library so the
flash has somewhere to flash *from*.

**Open question for the first hardware session.** Whether 180 ms reads as a
flash or a flicker is a thing to judge with eyes, not tests. Make the decay
length a constant with a comment, and expect to change it once.

### NH-01 — Mixer page `size: M`

**Status: shipped.**  `Mix` opens `modes/mixer.py`: eight strips at a time, an
encoder of gain and a mute button each, the `Master` encoder on
`project.master_gain` (applied in the final clip stage), and the pads as eight
vertical meters fed by a new `Engine.slot_peaks` -- callback-written,
UI-read, the same single-writer arrangement as `sounding`.

`Solo` arms, then a button under the display solos that strip; pressing `Solo`
again clears it.  Soloing is `Project.soloed` plus `Project.audible()`, kept well
away from `Sample.enabled`, so soloing and un-soloing cannot destroy the mute
state you set by hand -- which is the entire point of a solo button.  Solo is a
listening decision, so it is not on the undo stack; master gain is.

Deviation: rows are chosen with up/down **or by pressing any pad in a column**,
which makes the grid navigable without hunting for the arrows.

Eight track encoders set the gain of the eight slots in the current row, with
the eight display-row-bottom buttons muting them and `Solo` soloing one. `Mix`
(CC 112) opens it; `Master` encoder (79) is a new master gain applied in
`_mix`'s final clip stage. Pads show a per-slot level meter as a vertical bar
(pad row = level), which reuses the `sounding` data plus a new per-slot peak
published by the engine. **Code:** new `modes/mixer.py`, `audio.py`
(per-slot peak, master gain), `project.py` (`master_gain`). **Tests:** encoder →
gain → schedule; solo mutes everything else without destroying mute state;
master gain scales the mix; meters decay. **Deps:** `F-03`, `F-01`.

### NH-02 — Swing and groove `size: S`

The swing encoder (CC 15) delays every second 8th note by 0–60 % of an 8th.
Implemented as a phase offset applied when computing a trigger's start frame —
never by moving the transport, or recording alignment breaks. Per-sample
`groove_enabled` so drums can swing while pads do not. **Code:** `audio.py`
(`_fire_boundaries` start-frame offset), `project.py`, `modes/sample.py`.
**Tests:** at 50 % swing the second 8th's trigger frame is exactly
`fpb × (1 + 0.5)/2` later; swing does not shift bar-aligned triggers; recording
is unaffected while swing is non-zero. **Deps:** `F-01`, `NF-02`.

**Status: shipped as two halves, because the spec as written was a no-op.**
This item was flagged for a decision three times and never answered, so the
product call was made here: read the plan's own test list again --- "swing does
not shift bar-aligned triggers". *Every* trigger in this program is
bar-aligned. In a bar-addressed sequencer that line does not describe an edge
case, it describes the whole feature doing nothing. There are no 8th notes in
the arrangement to swing.

So the item ships as the two things it was actually reaching for:

1. **Swing, where sub-beat time exists.** `QUANTIZE_BEATS` gained `0.25` and
   `0.5` (`1/16 bar` and `1/8 bar`), and `Engine.swing` pushes the **odd** grid
   lines late by 0--66 % of the division. At a half-beat grid the downbeats stay
   put and the eighths between them move, which is what swing is. On the swing
   encoder (CC 15, previously unbound), per song, one undo step.
2. **A per-sample nudge**, which is what groove means when your grid is bars:
   `Sample.nudge_ms`, 0--120 ms, on encoder 2 of a sample page. A clap laid
   20 ms behind the kick stops sounding like a machine. Format 9, one undo step,
   and it affects playback and bounces because it is a property of the song
   rather than a monitoring choice.

Four decisions inside that:

- **Swing is a no-op at a whole beat or coarser**, and a no-op on an already
  late hit. Pushing every other beat back is not a groove, it is a wrong tempo;
  and making a late hit later is the opposite of quantizing.
- **Both places say whether swing is reaching them.** The encoder's message
  names perform mode, and the perform page reads either `swing 30%` or
  `(swing needs a sub-beat quantize)`. A knob that appears to do nothing is
  worse than no knob, and this one does nothing in five of its six positions.
- **The nudge is late only.** Starting *before* a bar line needs the engine to
  know about that line before it arrives --- lookahead across loop wraps, page
  boundaries and tempo changes --- for a control that is relative anyway:
  laying everything else back is how you push one thing forward. At the 240 BPM
  clamp a bar is still a full second, so 120 ms can never spill past its own
  bar line, which is what makes the deferred start safe with no wrap handling
  at all. There is a test asserting exactly that.
- **A nudge defers the whole decision, not just the audio.** `_pending` now
  holds either a `Voice` or a `(ScheduledSample, bar)` pair, and a nudged entry
  resolves its play mode and choke group when it *sounds*. Deciding at the bar
  line would cut a retriggered voice up to 120 ms before its replacement began
  --- an audible hole where a retrigger should be seamless. `_start_scheduled`
  now defers; `_start_now` is the old body.

**The plan's own numbers were right about the mechanism** --- a phase offset on
the start frame, never a move of the transport --- and that part went in exactly
as specified. Recording is untouched in both halves: swing offsets a live
trigger's start, and a nudge is applied on the way to the speakers like the
edits are, so neither can change where a take was captured.

**Per-sample `groove_enabled` was not built.** With swing confined to live
triggering, "which samples swing" is answered by which pad you are hitting, and
a per-sample flag for a feature that only applies while your finger is on the
pad would be a setting with nowhere to matter. The per-sample control that
*does* matter is the nudge, and it is per sample by construction.

### NH-03 — Metronome and count-in options `size: S`

**Status: shipped**, including the separate click output the spec called for:
`Voice` gained a `channel`, and `_mix_routed` adds a routed voice into its own
pair only -- so with `click out` set to channel 3 on a four-output interface the
main mix, and anything bounced from it, is click-free while a cue pair has it.

Count-in stays a **range** 0-16 rather than the spec's closed 0/1/2/4/8 list: a
closed `choices` list is exactly what silently swallowed `--samplerate 8000`
earlier in this project, and 3 is a real count-in in 3/4.  Pre-roll plays the
song for N bars before the count-in; only the count-in beats click, so the
run-up is the song rather than a longer countdown.

Count-in length (0/1/2/4/8 beats), pre-roll (start the loop N bars before the
take), click sound (sine/tick/cowbell), click level, click-only-while-recording,
and an optional separate click output channel pair. All in settings (`F-06`)
plus `Shift`+`Metronome` for the level. **Code:** `audio.py` (`make_click`
variants, click routing), `settings.py`, `modes/settings.py`. **Tests:** each
count-in length produces that many clicks before frame 0; click routing keeps
the main mix click-free when a separate pair is configured. **Deps:** `F-06`.

### NH-04 — Overdub onto an existing sample `size: M`

**Status: shipped.**  No engine change was needed: `arm_record(sample.bars)`
already records exactly the take's length into a buffer, so the layer arrives
the right size and the app sums it.  `New` on a sample page arms it and the page
stays put, so you watch the arrangement while overdubbing; `Shift`+`New` peels
the last layer off.

`Sample.layers` holds the individual passes with `audio` as their sum, and the
first overdub promotes the existing recording to layer 1 so a take never
silently loses the ability to be peeled back.  Anything that replaces `audio`
with something that is no longer that sum -- applying edits, fitting an off-grid
take -- calls `flatten()`, so the invariant cannot go stale.

Layers are persisted as their own WAVs (`slot_00_L1.wav`, format version 5),
because "individually removable" that stops working after a reload is not the
feature.  Missing layer files are tolerated: the take keeps playing as the
summed audio, it just cannot be peeled back.

`New` (CC 87) on a sample page starts a layering take: the existing sample plays
while you record, and the new audio is summed into it (sound-on-sound), with the
pre-layer audio kept for undo. Layer count shown on the display; `Shift`+`New`
removes the last layer. **Code:** `audio.py` (record mode that mixes into an
existing buffer, or returns the new layer for the app to sum), `project.py`
(`layers: list[np.ndarray]` so layers stay individually removable),
`modes/sample.py`. **Tests:** two layers of known DC sum exactly; removing a
layer restores the previous buffer bit-exactly; layer lengths are clamped to the
sample's bar length. **Deps:** `F-04`, `F-09`.

### NH-05 — Copy, paste, duplicate `size: S`

**Status: shipped.**  `Duplicate` *arms* rather than being held, for consistency
with `Delete` and `Mute` (and because the simulator can then reach it).  In the
library it copies a slot to the next empty one, wrapping; the copy shares the
original's audio array, which is safe because every edit path rebinds
`sample.audio` rather than writing into it.  On a sample page the two presses are
the block's start and its destination, and the **gap between them is the block
length** -- the plan's "bars A…A+n" left `n` undefined, and inferring it from the
gap needs no extra control and matches the common musical gesture (bar 1 then bar
5 duplicates bars 1-4 onto 5-8).  `Shift` on the second press moves.  Both land as
one `SetBars`, so a whole block is one undo step.

`Duplicate` (CC 88) held + a pad copies that slot (audio shared copy-on-write,
arrangement copied) to the next empty slot. On a sample page, `Duplicate` + bar
A then bar B copies the trigger pattern of bars A…A+n to B. Shift-variants move
instead of copy. **Code:** `modes/library.py`, `modes/sample.py`, `project.py`
(`copy_slot`, `copy_bar_range`). **Tests:** duplicated slot is independent after
an edit; bar-range copy handles wrap at bar 64 by clipping; all operations
undoable. **Deps:** `F-04`.

### NH-06 — Scenes / arrangement snapshots `size: M`

**Status: shipped**, on the display row **below** rather than above: that row is
the input meter (`F-07`), and a level meter you cannot see is a worse trade than
a scene button one row down.

The spec's "swap the schedule at the next bar, not mid-bar" needed **no engine
change**, which is worth recording rather than quietly skipping: triggers are
only ever read at bar lines, and a voice already sounding owns its buffer, so
replacing the schedule mid-bar can neither cut a voice nor take effect early.
A recall is one undo step, and it restores a snapshot of what it replaced.

A scene carries the enable map and the trigger sets only.  Audio, gain, edits
and layers belong to the *take*, not the arrangement, and a scene that silently
re-pitched your samples would be a trap.  Slots recorded since a snapshot are
left alone rather than emptied -- a scene is a variation, not a rollback.

Eight snapshots of the whole enable-map (which samples are audible and their
trigger sets), stored in the project and recalled instantly for A/B comparison
or live variation. `Shift` + top display-row button stores, unshifted recalls,
with a morph-free instant switch at the next bar boundary. **Code:**
`project.py` (`scenes: list[SceneSnapshot]`), `modes/library.py`, `audio.py`
(swap schedule at the next bar, not mid-bar). **Tests:** store → change → recall
restores exactly; recall during playback takes effect on the next bar line and
never mid-voice; snapshots survive save/load. **Deps:** `F-04`, `NF-07` if banks
land first.

### NH-07 — Tap tempo and tempo nudge `size: S`

**Status: shipped**, with one deviation: the fine nudge is **hold `Tap Tempo` +
tempo encoder**, not `◀/▶`.  The arrows are already the alias of `Session`
("back"), and `Page ◀/▶` is reserved for `NF-07`/`NF-11`; hanging the nudge off
the tempo button keeps both free and puts the gesture on the control it is about.
Holding `Tap` discards the tap series so the held press is not read as a tap.
`format_bpm` now lives in `project.py` and is used by both the transport readout
and the undo label, because a 0.1 nudge that the display rounds away is a knob
that appears to do nothing.

`Tap Tempo` (CC 3): four taps set the BPM from the median inter-tap interval,
outliers rejected, tempo refused while recording (as today). `Shift`+`Tap`
resets. Nudge: `Shift` + tempo encoder already does ±10; add `◀/▶` for ±0.1 for
beat-matching. **Code:** `app.py`, `audio.py` (`set_bpm` already clamps).
**Tests:** taps at a known interval yield the right BPM within 0.5; an outlier
tap is ignored; tapping during a take is refused. **Deps:** none.

### NH-08 — Auto-trim and auto-normalize on record `size: S`

**Status: shipped.**  `analysis.py` holds `first_transient`, `shift_left`,
`normalize` and `fade_edges`; three settings, all off by default.

The shift **pads the end to keep the length**, which the spec did not say but
`F-09` requires: a take is an exact number of bars, and returning something
shorter would flag the slot as off the grid the moment it landed.  The onset
threshold is relative to the take's own first 10 ms, because "silence" means
something different on a condenser in a live room than on a direct input, and
nothing found within the 100 ms of slack means do nothing rather than guess.

A bug the tests caught: the processing note was posted *before* `goto_sample`,
whose own announcement immediately buried it -- so a normalised take said
nothing, which is exactly the silent processing the code comments warn against.

Optional post-take processing: detect the first transient and shift the take so
it starts on the grid (up to 100 ms of slack), normalize to −1 dBFS, and
(optionally) apply a 2 ms fade at both ends. All three are settings, default
off, and all are undoable since the raw take is kept until the next take.
**Code:** new `analysis.py` (`first_transient(buf, sr)`), `modes/record.py`,
`settings.py`. **Tests:** a take with 30 ms of leading silence is shifted by
exactly that; a take starting with a transient is untouched; normalize hits the
target peak; the raw take is recoverable. **Deps:** `F-09`.

### NH-09 — Tempo-follow time stretch `size: L`

When the project tempo changes, samples recorded at the old tempo fall out of
sync. Implement WSOLA-style stretching (pure numpy, quality over speed — it runs
offline, not in the callback) with per-sample `stretch_mode` ∈
`{off, resample, wsola}`. `resample` changes pitch and is instant; `wsola`
preserves pitch and is computed once per tempo change with progress on the
display. **Code:** new `dsp.py`, `project.py` (`source_bpm` from `F-09`,
cached stretched audio), `app.py` (recompute off the audio thread, in a worker).
**Tests:** stretching by 1.5× yields a buffer 1.5× long whose dominant frequency
is unchanged (FFT assertion) for `wsola` and scaled for `resample`; cache
invalidation on tempo change; the audio callback never sees a half-written
buffer. **Deps:** `F-09`. The stretching worker must not be started from the
audio callback.

**Status: shipped.** A new `dsp.py` with `resample`, `wsola`, `stretch` and
`StretchJob`; `Sample.stretch_mode`, format version 12, `Project.playable_audio`
and `pending_stretches`; `SetStretchMode` on the undo stack and button 6 on a
sample page. 83 tests in `tests/test_stretch.py`. Five prototype rounds.

**There is no worker, which is how the plan's warning is met.** "The stretching
worker must not be started from the audio callback" is answered more simply by
there being no thread at all: `StretchJob` is stepped from the frame loop
exactly as `BounceJob` already was. The callback cannot see a half-written
buffer because a stretch is computed into a fresh array and *then* rebound in
one assignment, and the schedule is rebuilt once, from finished arrays.

**The plan's own test assertion is only valid for one note.** "The dominant
frequency is unchanged" is right for a tone and meaningless for a chord, whose
three near-equal partials make `argmax` pick whichever is momentarily loudest.
The chord is checked partial by partial instead, and each survives at 0.92–1.00
of full strength at every rate tested.

Four findings, each now a test:

1. **Every stretch ended in a click.** Running out of input left the tail
   silent: a 2-second tone at 1.5× finished with 615 frames of nothing and a
   0.488 step into them, against a source whose worst step is 0.063. The read
   position is clamped to the last whole frame, so running out reuses the final
   frames instead.
2. **Normalised cross-correlation — the textbook choice — was measured and
   rejected.** 4× slower and *worse* on a chord (0.953 against 0.957).
3. **The search had to be vectorised, not merely tidied.** As a Python loop over
   candidates a 30-second take took 2.2 s; as one `np.correlate` call it takes
   0.33 s, bit-for-bit identical.
4. **The search runs on the channel sum.** Searching per channel picks different
   offsets left and right and smears the stereo image — a worse artefact than
   the one being fixed. There is a test that both channels come back identical.

Two decisions the plan did not reach. **A stretching slot is no longer flagged
off-grid**, because the length is being handled and the yellow pad would be
telling you to fix something already fixed — a tempo change too large to absorb
is still flagged, because then it genuinely is not. And **`IN-02` chooses which
mode to offer first**: percussion gets `resample`, because a break played faster
*is* pitched up and that is a sound records have been made of, and because
measurement says percussion is exactly what WSOLA is worst at (0.78–0.83
spectral similarity against 0.96–1.00 for a chord).

### NH-10 — Per-trigger probability and follow actions `size: M`

Each trigger gets a `probability` (0–100 %, default 100) and each sample an
optional `every_n` ("play only on the 2nd pass of the loop"). Makes a short
arrangement feel long. Pad brightness shows probability; `Shift`+encoder 2 sets
it for the selected bar. Randomness uses a per-pass seeded RNG so a pass is
reproducible for bounce. **Code:** `project.py` (trigger becomes a small record —
coordinate with `NF-10`'s dict change), `audio.py` (`_fire_boundaries` rolls
from a seeded RNG held on the engine), `modes/sample.py`. **Tests:** p=0 never
fires, p=100 always; with a fixed seed a 64-bar pass is reproducible;
`every_n=2` fires on passes 2, 4, 6. **Deps:** `NF-10` (shared trigger record).

**Status: shipped.** `Sample.probabilities` (a bar→percent dict, absent means
certain) and `Sample.every_n`, format version 10, `Project.chance_seed`,
`SetProbability` / `SetEveryN` / `SetChanceSeed` on the undo stack, and
`Shift`+encoders 2/3/4 on a sample page. All four of the plan's tests pass with
its numbers, in `tests/test_chance.py` (45 tests).

**The plan's "per-pass seeded RNG" would not have been reproducible.** A
generator advanced once per trigger gives bar 40 a different answer depending on
how many triggers preceded it — so dropping in at bar 17 instead of playing from
the top changes everything after it, and what you bounce is not what you heard.
Shipped instead as `roll(seed, pass, bar, slot)`, a SplitMix64-style **pure
function** with no state to diverge. Verified uniform (24.3 % / 49.2 % / 74.7 %
measured for p=25/50/75 over 8192 rolls) and verified to give identical output
whether playback starts at bar 1, starts at bar 17, or is rendered offline.

**And a test found that `every_n` was silently absent from bounces.** A bounce
renders **linearly**, start to end, once — so it never loops, so a pass counter
incremented on the loop wrap stayed at 1 for ever. A sample set to *every 2nd
pass* was therefore in the arrangement you heard and **not in the file at all**.
Two fixes: the pass is now *derived from the position* when there is no loop to
wrap, and `render.passes_needed` returns the lowest common multiple of every
audible triggered sample's `every_n` (capped at `MAX_PASSES = 8`) so a bounce
covers a whole cycle, with the schedule tiled across it. Muted samples are
excluded from that LCM — a muted *every 5th pass* sample must not quintuple your
file length. A test now asserts the bars you hear are bar-for-bar the bars that
land in the file.

Three decisions the plan did not reach:

1. **An uncertain bar flashes; it does not dim.** The plan said "pad brightness
   shows probability", but brightness on a sample page already means *recorded
   velocity* (`NF-10`), so a quiet hit at 100 % and a loud hit at 40 % would be
   the same pixel. Flashing is the only channel left, and it reads as
   "sometimes" rather than "quiet".
2. **The dice are per project, not per sample.** The point of a seed is that the
   whole arrangement varies *together* and repeatably — a kick that drops and a
   snare that answers it must agree about which pass this is. It is editable at
   all (`Shift`+encoder 4, 0–63) because otherwise the seed is 0 for ever and a
   probabilistic song has exactly one variation in it.
3. **`Shift`+encoder 2 asks for a bar rather than picking one.** "The selected
   bar" had no referent on a page of 64 pads, so it means the bar you last
   pressed, and with none pressed the page says
   `press a bar first, then Shift + encoder 2`. Silently editing whichever bar
   happened to be first is worse than asking.

The minimum probability is **5 %**, not 0: a 0 % bar is a bar that does not
play, which the pad already expresses by being off, and leaving it reachable by
encoder would give two different-looking ways to say the same thing. The floor
also means turning the encoder all the way down never makes a bar disappear from
the grid.

Only the pass counter, not probability, drives the `· pass N` suffix on the
transport readout — a pass number on a song that has no pass cycle is a number
with nothing to say.

### NH-11 — Multiple output pairs and a cue bus `size: M`

Route a slot to output pair 1/2 or 3/4, and send the metronome to the cue pair
so the click stays out of the mix. Needs `out_channels` > 2 and a per-slot
`output` field; `_mix` writes into the right column slice. **Code:** `audio.py`,
`project.py`, `modes/mixer.py`, `settings.py`. **Tests:** a slot routed to 3/4 is
silent on 1/2 and present on 3/4; with a 2-channel device, routing falls back to
1/2 with a warning. **Deps:** `NH-01`.

**Status: shipped.** Per-slot `Sample.output` (a pair index, 0 = main), format
version 8, `SetOutput` on the undo stack, `Shift` + a mixer strip button to
cycle, and `pair_first_channel`/`pair_label` in `constants.py` so the pair→channel
arithmetic lives in one place. The click already had its own `click_channel`
from `F-07`, so the cue half of this item was done before it started.

**The plan said `_mix` "writes into the right column slice" and that was the
whole bug.** The existing mixer wrote a mono take into *every* output channel,
which is correct on a stereo device and catastrophic on a four-output one: the
main mix would appear on the cue pair, so routing a kick to 3/4 would give you
the kick *and everything else*. The main mix is the **first pair**, not every
channel the device has. `Engine.main_width` (`min(2, out_channels)`) now bounds
it, in the one-shot path, the looping path and `_monitor`.

Three decisions the plan did not reach:

1. **A routed slot leaves the main mix entirely** rather than being copied to
   both. Doubling it would make routing a send, and what the item is for is a
   cue: hearing one thing on its own.
2. **So it is excluded from a bounce**, by filtering the schedule in
   `BounceJob._schedule` rather than trusting the engine's fallback — a bounce
   is what comes out of the main outputs, and a cue pair is by definition not
   that. Its *stem* keeps it: a stem is what the slot played, and where you were
   listening does not change that. Writing this up turned out to correct a
   pre-existing doc claim that muted slots are "still exported as stems" — they
   are, as silence, because `build_schedule` drops them. Both facts are now in
   `docs/reference.md` with tests behind them.
3. **Cycling stops at the pairs the stream really opened**, asked of
   `Engine.out_channels` rather than the settings: a device configured for eight
   channels that would only open two has two. Offering a choice that does
   nothing is worse than not offering it, so a two-channel device says "nowhere
   to route slot 5 to" instead. A pair that has *become* unavailable (a project
   made on an 8-out interface, opened on a laptop) still falls back to the main
   mix and is flagged `!` with a plain explanation — the same fallback rule
   `click_channel` uses.

### NH-12 — Remote monitor page `size: M`

An optional local HTTP page (stdlib `http.server`, no dependency) on
`--monitor-port 8765` showing the live grid, transport and meters, updating via
server-sent events. Useful for teaching, streaming overlays, and debugging the
surface without hardware. Read-only — it must never accept commands, and it must
bind to localhost by default. **Code:** new `monitor_http.py`, `app.py` (publish
a snapshot dict), `cli.py`. **Tests:** snapshot serialization matches the LED
state; the server thread shuts down cleanly with the app; disabled by default.
**Deps:** none.

**Status: shipped**, to the plan, including both of its refusals. `monitor_http.py`
holds the server, the page and the one snapshot everybody reads; `App.monitor_page`,
`monitor_snapshot()` and `_publish_monitor()` are its whole footprint in the app.
`monitor_port` (0 = off, the default) and `monitor_host` in settings,
`--monitor-port [N]` and `--monitor-host` for one run.

Four decisions the plan left open:

1. **The snapshot mirrors the frame `render()` drew**, kept in `_drawn_pads` and
   `_drawn_buttons`, rather than asking the modes to render a second time. Two
   renders could disagree, and a monitor that disagrees with the instrument is
   worse than no monitor.
2. **Nobody watching costs nothing.** `Monitor.wanted` is false with no stream
   open and no recent `/snapshot.json`, and the app skips building the snapshot
   entirely — a monitor left enabled and unopened is one attribute read per
   frame. Published at 10 Hz, not the LEDs' 30: the page is not a meter.
3. **No lock anywhere**, in keeping with the engine. The render thread stores a
   finished dict into one attribute; readers hold that reference while they
   serialise it. The dict is built fresh each time and never mutated, so there
   is no window in which a reader sees half of one frame and half of the next.
4. **Buttons are named, not numbered** (`BUTTON_NAMES`, `button_name`) — `cc85`
   tells a reader nothing. The two rows flanking the display have no names on
   the hardware, so they are `top1`..`top8` and `bot1`..`bot8`.

**Two things the first run found**, neither of them in the plan:

- **`/snapshot.json` was permanently empty.** A script polling the JSON never
  opens a stream, so `wanted` was never true and nothing was ever published to
  read. Fetching it now counts as watching for five seconds. An endpoint that
  is always empty is not an endpoint.
- **Dim pads were invisible.** The page carries the palette's own RGB, and
  `#242424` on a lit screen is nothing like a white LED at 14 % in a dark room.
  Rather than falsify the colour there is a **brighten dim pads** checkbox
  (a CSS filter, remembered per browser): off by default, so what you see is
  what the Push is told.

**It also produced `tests/test_docs.py`**, which is not a feature but is the
most reusable thing in the item. Writing NH-12's docs meant renumbering the
tutorial, which had accumulated two `Step 11b`s and two `Step 11c`s from four
rounds of insertion — and that broke a link nobody would have clicked for
months. The test now walks every markdown file in the project: every in-page
anchor resolves, every relative link resolves (including its anchor), no two
headings share a slug, and the tutorial's steps are `1..n` exactly once each.
It found three more dead or ambiguous anchors on its first run, all pre-existing.

Getting its slug function right needed care: github-slugger turns **each** space
into its own hyphen and does not collapse runs, so a heading with an em dash
(`Clock — playing with other gear`) anchors as `clock--playing-with-other-gear`.
Collapsing them would have had the test call working links dead, which is the
failure mode that makes people delete a test.

---

## 8. Innovative

Ideas that make this more than a looper. Each needs a spike before it gets a
final spec — budget a day of prototyping inside the item.

### IN-01 — Slice a take across the pads `size: L`

**Idea.** Record eight bars of drumming in one pass, press `Convert`, and get
eight one-bar samples spread across eight pads — or slice at detected transients
to get one pad per hit. One take becomes a kit.

**Spec.** `Convert` (CC 35) on a sample page opens a slice overlay with three
modes: **bars** (n equal slices), **beats**, **transients** (onset detection with
a sensitivity encoder, max 64 slices). The display shows the waveform with slice
markers; pads preview each slice; `Convert` again commits, writing the slices to
the next free slots (or a chosen destination row) and optionally replacing the
original. Onsets come from a spectral-flux novelty curve with adaptive
thresholding, implemented in `analysis.py` with numpy only.

**Code.** new `analysis.py` (`onsets(buf, sr) -> list[int]`), new
`modes/slice.py`, `project.py` (bulk `put` of n samples as one undoable
command).

**Tests.** A click train at known positions yields onsets within ±5 ms; equal
slicing of 8 bars produces 8 buffers of exactly `frames_per_bar`; committing is
one undo step; no free slots produces a clear refusal.

**Deps.** `F-04`, `F-09`, `NF-03` (shares the waveform display widget).

**Status: shipped.** `analysis.onsets` (added alongside NH-08's existing
post-take helpers in the same module), `modes/slice.py`, and `SliceTake` in
`history.py` for the bulk write. `Convert` on a sample page opens it; `Convert`
again commits; `Shift`+`Convert` consumes the original.

**"Budget a day of prototyping inside the item" was the most valuable line in
this section, exactly as it was for `NF-09`.** Five rounds against synthetic
signals with *chosen* onset frames, so every claim below is a measurement:

1. **Onsets landed 10-15 ms early.** The reported position was the analysis
   window's *start*, and a 1024-sample window can begin long before the hit
   inside it. The acceptance test was +/-5 ms, so the first version could not
   have passed at any setting. Fixed by refining the frame index against the
   signal.
2. **Refining on energy *level* found the previous hit's tail.** "Where does
   this neighbourhood first reach a quarter of its peak" is right for a hit in
   silence and wrong the moment hits overlap: 1 of 8 matched on sustained
   material. An onset is where energy goes *up*; a decaying tail is going down.
3. **A constant 440 Hz tone produced 59 onsets.** A sine that is not
   bin-centred leaks, the leakage wobbles frame to frame, and dividing the flux
   curve by its own maximum turns that wobble into full-scale signal. Fixed by
   a peak-to-median structure gate; measured, a held tone is about 3.6 and a
   drum take over 30.
4. **A global prominence floor changed nothing** on any of eleven signals, and
   was deleted rather than kept as a knob that does not turn.
5. **The sharpness test is what makes the sensitivity encoder mean anything**
   on sustained material. Without it the slice count was identical at every
   setting.

A sixth thing the prototype nearly hid: at the strictest sensitivity the
sustained-material *count* came out exactly right, which looked like success
until the positions were checked -- it was two misses cancelling two extras.
Counting is not matching, and the test suite matches.

**Measured, at the default sensitivity:** a 16th-note drum pattern is 31 of 31
within 0.7 ms; the same at a fifth the level is identical; a ghost note at a
tenth the level survives at every sensitivity; two hits 50 ms apart are two;
silence, white noise and a held tone all yield nothing. **Overlapping sustained
notes are approximate** -- extra cuts in the decay -- and no threshold work
moved that, because the tail of a sustained note genuinely looks like a small
attack. **bars** and **beats** are the answer to it: a choice of three, not a
better curve.

Five decisions the spec left open:

1. **The original is kept by default**, `Shift`+`Convert` consumes it. The
   slices share the source's audio, the source is what you re-slice from at
   another sensitivity, and the pad you pressed `Convert` on is where your
   hands expect it to still be.
2. **A slice is one bar whatever its real length.** A slice is a hit, not a bar
   of music; giving each its true length would have `F-09`'s off-grid check
   flag all sixteen of them yellow.
3. **Slices carry the sound and not the arrangement** -- gain, colour, play
   mode, choke group, output pair and nudge, but no triggers. Where the source
   played is not where its pieces play, and a kit that arrived pre-arranged
   would be a mess to undo by hand.
4. **Destinations are searched from the slot after the source**, wrapping, so a
   kit lands next to the take it came from rather than at slot 1. Too few free
   slots is a refusal with the numbers in it rather than a partial write.
5. **A one-bar take opens on beats**, because opening on bars would land you on
   a page that can only refuse.

**The destination row the spec offered was not built.** Choosing where a kit
lands is a second gesture on a page whose whole job is choosing *cuts*, and
"the slots after this one" is right nearly always -- `Duplicate` already moves
a slot afterwards if it is not.

### IN-02 — Listening assistant `size: L`

**Idea.** The instrument has heard everything you played. It should be able to
tell you something useful about it — entirely locally, no network, no model
weights: just DSP.

**Spec.** `analysis.py` computes, per sample: detected tempo and confidence,
onset density, spectral centroid (bright/dark), loudness, dominant pitch and a
best-guess key, and a "rhythmic role" guess (kick/snare/hat/bass/pad/vocal) from
band energy and onset pattern. Surfaced three ways: a per-sample info page on
the display; automatic name suggestions (feeds `CC-17`); and an `Arrange` hint
that proposes bars for a new sample based on what already occupies them (e.g.
"this looks like a hat — bars 9–16 and 25–32 are thin"). Hints are *proposals*:
they light a pattern in flashing yellow and require a press to accept.

**Code.** `analysis.py`, new `modes/info.py`, `modes/sample.py`.

**Tests.** Synthesized kick/hat/sine test signals classify correctly; detected
tempo of a loop built at 120 BPM reads 120 ± 2; proposals never mutate the
project without an explicit accept.

**Deps.** `F-09`, `IN-01` (shares `analysis.py`).

**Status: shipped, with the role vocabulary cut from six to five and the
arrangement hint deliberately deferred.** `analysis.describe` returns a
`Description` (role, confidence, pitch and note, tempo and confidence, onset
count and density, centroid, bands, loudness, sustain); `modes/info.py` is the
page, on `Layout` from a sample page; its button 1 accepts a suggested name
through the existing `SetName`.

**Six rounds of prototyping, and the first finding was a product decision
rather than a bug.**

`kick / snare / hat / bass / pad / vocal` **is not separable by band energy and
envelope.** A synthesised snare classified as a hat at 0.85 confidence, because
nothing in those features tells a noise burst with a 200 Hz body from one
without; `pad` versus `vocal` is the same problem from the other end. So the
vocabulary is what the measurements can defend — `low drum`, `bright drum`,
`drum`, `bass`, `tone`, `noise` — and the honest cost, recorded in a test as
expected behaviour, is that a snare reads as a bright drum. A label the
instrument cannot stand behind is worse than a coarser one it can, and this
project has said that about the display, the palette and the clock already.

Five more, each a measurement:

1. **Autocorrelation on a chord finds the GCD period.** A 220/277/330 chord
   came back as 55 Hz, which made every pad look like a bass. Replaced by
   matching against a harmonic series.
2. **White noise classified as a hat, 0.92 confident.** Band energy alone
   cannot separate them — both are mostly high. What does is that a struck
   sound decays and noise does not, and the feature was already being computed.
3. **Periodicity is not pitch confidence.** A kick every half second is 0.95
   periodic *at the hit rate*, and duly reported a 1200 Hz "pitch" — the top of
   the search range.
4. **Scoring harmonicity as the mean harmonic strength inverted the measure.**
   A pure sine has energy in harmonic 1 only, so its mean was max/8: it scored
   0.13 while white noise, with all eight bands equally full, scored 0.54.
   Tones became noise and noise became tones. The fraction-of-energy measure
   was right all along; its sub-octave bias needed a separate "the fundamental
   must be present" guard, not a different measure.
5. **Note names were wrong until the peak was interpolated.** Pitch landed
   within one FFT bin, but one bin at 110 Hz is 10% and a semitone is 5.95%.
   Parabolic interpolation brings the worst error to 1.1%. And the note-naming
   helper itself was an octave low — 440 Hz returned "A3" — caught only because
   the test named the notes it expected rather than checking that a string came
   back.

**Two decisions about tempo, which the spec asked for in one line.**

The acceptance test (`120 BPM reads 120 ± 2`) passes on material with crisp
attacks: measured across 90/120/140/170 BPM at one, two and four hits per beat,
every reading is within 0.4 BPM. On material whose attacks are *smeared* — a
synthesised kick whose body sweeps downward for 150 ms — it reads 20 to 80 BPM
out, and a coarser minimum onset gap does not help: measured at 30, 60 and
100 ms it was wrong at all three. The confidence was honest throughout
(0.00–0.24 against 0.98–1.00), so **below a threshold no tempo is reported at
all.** "No clear tempo" beats "about 98 BPM (loose)" when the answer is 120.

And tempo has an **unresolvable octave ambiguity** from onsets alone: 90 BPM in
eighths and 180 in quarters are the same recording, and measured, the eighths
read 180 at full confidence. Resolving it properly needs a model of where the
strong beats fall, which is a great deal of machinery for a line on an info
page. Instead `describe` takes an optional `reference_bpm` and the page passes
the session's tempo — the one piece of context a *sampler* has that a general
analyser does not.

**The arrangement hint was not built, and this is the reason.** A proposal that
lights a pattern in flashing yellow and waits for a press is exactly the
mechanic `IN-03`'s pattern mode needs, and building it twice — once for hints,
once for patterns — would be the wrong order. The propose-then-accept *shape*
is already set by this page's name button, which is the smallest honest version
of it. When `IN-03` lands, the hint is a second producer feeding the same
preview-and-commit path.

**It also corrected a doc claim.** `docs/simulator.md` said "recording captures
silence" in two places. It does not: with no audio device the engine feeds
itself a 220 Hz stand-in tone, deliberately, so that a simulated take is not
silent and every downstream page does not look broken. The info page is what
exposed it — it reported a clean A3 from a simulated recording.

### IN-03 — Generative trigger patterns `size: M`

**Idea.** Instead of tapping 16 bars by hand, turn an encoder until the pattern
is right.

**Spec.** On a sample page, `Automate` (CC 89) enters pattern mode: encoder 1 =
density (0–64 triggers), 2 = rotation, 3 = algorithm (euclidean / every-n /
random-with-seed / mirror-of-another-slot), 4 = seed. The grid previews the
generated pattern live in flashing green; `Automate` again commits it as one
undoable change; `Session` discards. Patterns are deterministic functions of
(density, rotation, algorithm, seed) so the same settings always reproduce the
same 64 bars.

**Code.** new `patterns.py` (pure functions → `set[int]`), `modes/sample.py`.

**Tests.** Euclidean (density 4, 64 bars) matches the canonical Bjorklund
output; rotation is a cyclic shift; the same seed reproduces the same pattern;
commit is one undo step and preview mutates nothing.

**Deps.** `F-04`.

**Status: shipped, with a fifth encoder the spec did not ask for and the page
is useless without.** `patterns.py` holds the pure functions (`bjorklund`,
`euclidean`, `every_n`, `random_bars`, `rotate`, `tile`, `generate`);
`modes/pattern.py` is the page; committing goes through the existing `SetBars`,
which already snapshots what it replaces.

**The missing control.** Built to spec, the density encoder spreads its hits
over the whole 64-bar page — and three bars over 64 is one hit every twenty-one
bars, which is not a rhythm, it is a rounding error with a downbeat. A pattern
is **short and repeats**. Encoder 5 sets its length and `tile` fills the page
with it, so three over eight becomes the tresillo eight times, which is what
turning a density encoder is supposed to give you:

```
density 3, length 64   x....................x..........
density 3, length 8    x..x..x.x..x..x.x..x..x.x..x..x.
```

Density and rotation are counted *within* the length and are clamped when it
shrinks — a density of 12 inside a length of 4 would silently mean "every bar"
and make the encoder look broken. `mirror` ignores the length: tiling someone
else's rhythm would be inventing a pattern rather than answering one.

**Getting the canonical table right was the interesting part, and the moral is
about testing rather than about rhythm.** The plan's test says "matches the
canonical Bjorklund output", which is only a test if the canonical output is
written down — so twenty-one entries from Toussaint's *The Euclidean Algorithm
Generates Traditional Musical Rhythms* went into the test file, the ones that
name E(3,8) as the Cuban tresillo and E(5,8) as the cinquillo.

Eighteen matched a plain Bjorklund implementation immediately. The three that
did not — E(3,4), E(5,6), E(7,8) — are all the case of exactly **one rest**,
where the grouping loop ends before it can interleave and the rest lands last
rather than second. Both forms are the same maximally even set, rotated, but
the table is the reference, so that case is explicit.

Fixing it then contradicted a twenty-first entry: E(2,3), written down from
memory as `xx.`. **That entry was the error, not the code.** The single-rest
family puts its rest second throughout, and an independent derivation — a hit
at step `i` iff `floor(i*k/n)` differs from `floor((i-1)*k/n)` — also gives
`x.x`. Two derivations agreeing against one recollection is the right way
round, and the lesson went into the tests as *properties* rather than more
examples: for every length up to 64, the gaps between consecutive hits never
differ by more than one step, the hit count is exact, and a pattern with hits
starts on one. A published example is a spot check.

Four decisions the spec left open:

1. **Committing replaces rather than adds.** Adding would make the preview a
   lie — you would see sixteen bars and get eighteen — and replacing is what
   makes the encoders explorable, because you can turn density back down and
   arrive where you started.
2. **It touches only the page you are looking at.** Patterning page A must not
   silently rewrite page D, and the preview only covers 64 bars anyway.
3. **The pads do not edit.** A hand-made toggle inside a generated pattern
   would be wiped by the next encoder click, so a press says what the grid is
   for instead of losing the work quietly.
4. **The preview flashes.** Steady green would be indistinguishable from bars
   that are actually stored, and the entire point of the page is that nothing
   is stored yet. Bars about to be cleared show dim red.

**`IN-02`'s arrangement hint is now unblocked**, and this is the page it feeds:
the preview-and-commit path, the flashing preview and the dim-red replacement
warning are all here, so a hint becomes a fifth algorithm — "what the rest of
the song leaves thin" — rather than a second mechanic. Left for its own item
rather than bolted on here.

### IN-04 — Harmonic awareness `size: M`

**Idea.** Tell the player which of their loops actually fit together.

**Spec.** Using `IN-02`'s pitch/key detection, `Scale` (CC 58) overlays the
library with harmonic compatibility relative to the selected sample: green =
same key, yellow = relative/dominant, red = clashing, white = unpitched
(percussion). A per-sample `transpose` (from `NF-03`'s pitch) can be suggested
to bring a clashing loop into key ("+2 semitones to match"). One press accepts.

**Code.** `analysis.py` (key detection via chroma), `modes/library.py`,
`modes/sample_edit.py`.

**Tests.** Synthesized C-major and A-minor loops read as compatible; C and F#
as clashing; percussive noise reads as unpitched; a suggested transpose applied
twice is idempotent.

**Deps.** `IN-02`, `NF-03`.

**Status: shipped.** `analysis.chroma` / `pitch_classes` / `clash` / `harmony` /
`fit` / `suggest_transpose`, a new `modes/harmony.py` on `Scale` (CC 58, which
the plan named and which was free), and the transpose accepted onto `NF-03`'s
`pitch_semitones` so it is non-destructive and one undo step. All four of the
plan's tests pass, in `tests/test_harmony.py` (51 tests). Eight prototype rounds;
the findings are why the shape differs from the spec.

**The plan's "key detection via chroma" put the unreliable half in charge.**
Naming a *tonic* from pitch-class weights is a guess about emphasis: measured, a
held Cmaj7 comes back `E minor` (correctly — those four notes sit in E minor
too) and a C triad with twelve harmonics does the same, while the chroma
underneath was right on all ten signals. So the colours are computed from
pitch-class content and the key is shown *labelled a guess*.
`test_the_key_name_is_wrong_on_a_seventh_chord` pins the failure rather than
hiding it.

**And the spec's green/yellow/red mapping was built on the wrong distance.**
"Green = same key, yellow = relative/dominant" implies the circle of fifths, but
C major and A minor are the **same seven notes** while sitting three fifths
apart, and C major and C minor sit zero apart sharing four. Shared content is
the measure; measured clash values are 0.028 (itself), 0.026 (A minor), 0.041
(the dominant), 0.135 (D major), 0.505 (E flat), 0.524 (the tritone), and the
two thresholds sit in the gaps rather than having been picked. A test asserts
the table, so moving a constant without re-measuring fails.

Four things the plan did not reach:

1. **The measure is asymmetric.** A three-note pad inside a seven-note
   progression fits; the progression laid over the pad introduces four notes the
   pad never plays. "Does adding this to what I have selected work" is a
   directed question, and a symmetric metric would answer a different one.
2. **Saying "that's a drum" needs two gates.** A kick reads `low drum` but its
   chroma is peaked enough (0.077) to pass a flatness test; white noise
   sometimes reads `tone` but is flat (0.008). Each catches what the other
   misses — and a seven-note melody at 0.106 sits close enough to the kick that
   flatness alone was never going to separate them.
3. **The analysis band starts at 90 Hz, not 60.** At 60 a C-G-C bass figure in
   octave 1 read as *clashing with its own key*, which is the one mistake this
   page must not make: the window is over a semitone wide down there and the
   note smears into classes it never played. 130 fixed nothing further and cost
   an octave-3 bass its "fits". The residue — the bottom octave can only reach
   "close" — is in `docs/reference.md` and held by a test.
4. **Ties in the transpose go to the smaller move.** A C# triad against C major
   was first told to go up four semitones, which lands on F and genuinely fits;
   down one is as good and is what a hand expects.

**A bug worth recording: the page lied after an undo.** The first version
measured each slot once and cached it per slot, so accepting a transpose and
pressing Undo left the page holding the *transposed* reading and still saying
"fits" about audio restored to clashing. A page cannot see an undo — it does not
go through a mode — so the reading is keyed on the audio itself, which also fixes
the same staleness arriving from a re-record, an overdub, or an edit applied on
the editor page. The lesson is the one `CC-13` and `NH-10` both taught: a cache
keyed on identity rather than on content is a cache that will eventually
disagree with the thing it describes.

`Scale` is also bound in the library, opening against the first filled slot,
because the library has no notion of a selected one — and `Shift` + a pad inside
the page re-references it, which is cheaper than arming a pick outside and
spending a press on it.

### IN-05 — Living song mode `size: L`

**Idea.** The 64-bar grid as a score that never plays the same way twice, then a
single button that freezes one performance as audio.

**Spec.** Combines `NH-10` (probability) and `IN-03` (patterns) into a `Living`
toggle per project: triggers with probability, per-pass variation rules
("every 4th pass, double the hats"), and deterministic seeding per pass. The
display shows the pass number and what is about to change. `Shift`+`Record`
bounces a chosen number of passes, consuming the same RNG stream so the bounce
is exactly what you heard.

**Code.** `audio.py` (pass counter, per-pass seed), `render.py`, `project.py`
(variation rules), new `modes/living.py`.

**Tests.** Two renders with the same seed are bit-identical; different seeds
differ; the live transport and a bounce of the same pass range produce identical
audio (the key property — it is what makes this trustworthy).

**Status: shipped**, and the re-scope below was right: almost all of it existed
already. `Sample.variation_bars` / `variation_every`, format version 13,
`SetVariation` on the undo stack, and a new `modes/living.py` on
`Shift`+`Clip`. 44 tests in `tests/test_living.py`, including the plan's "key
property".

**The variation rule needed no engine change whatsoever.** "Every 4th pass,
double the hats" reads as new machinery and is not: an extra trigger that fires
only on every 4th pass **is** a trigger with `NH-10`'s `every_n` of 4. So a
variation is a second set of bars scheduled with that divisor, and it inherited
reproducibility, correct bouncing and a readable grid from work already done.
`passes_needed` grew a third clause and that was the whole of `render.py`'s
involvement.

**A variation is concrete bars, not a rule.** The spec's "per-pass variation
rules" implies something evaluated at playback; storing the bars instead means
you can *look* at what the variation will do, edit one of them by hand, and see
it on a grid. A rule you have to trust is a worse instrument than a pattern you
can read.

**A variation is arithmetic, and the dice deliberately cannot move it.** "Every
4th pass" is a divisor; rolling for it would make the fill arrive at
unpredictable times, which is not what the words say. There is a test asserting
the seed changes nothing — because it is easy to expect the opposite given how
much of this item came from `NH-10`.

Three decisions the plan did not reach:

1. **The fill goes in the gaps, not over the span.** The first version spread
   `IN-03`'s euclidean pattern across the span the sample occupies, which for
   hats on bars 1, 3, 5, 7 put the new bars on top of the old ones and then
   subtracted them away to nothing. The free bars inside the part are listed
   first and the pattern chooses among *those* — which is also what "double it"
   means. A solid block with no gaps is filled past its end instead.
2. **The grid flashes only on the pass immediately before.** Flashing whenever
   the variation merely was not due made "about to change" and "eventually" the
   same pixel, which is the one thing the plan explicitly asked the display for.
3. **A freeze chooses its own length.** `Shift`+`Record` here renders the number
   of passes an encoder says, not `passes_needed`'s: that function answers "how
   long before the song repeats", and what a person wants from a freeze is "give
   me four times round". Those need not be the same number, so `BounceJob` grew
   an explicit `passes`.

**Deps.** `NF-05`, `NH-10`, `IN-03`. **All three were shipped first, which is
why this was three quarters built when it started.** `NH-10` already delivered the pass
counter, the deterministic per-position seed, `· pass N` on the display, and the
bounce-covers-a-whole-pass-cycle property this item lists as "the key property —
it is what makes this trustworthy" (`tests/test_chance.py` asserts the bars you
hear are the bars in the file). What is genuinely left is the **variation
rules** — "every 4th pass, double the hats" is a statement about a *pattern*,
not a probability, and `IN-03`'s generator is what would have to evaluate it —
plus the `Living` toggle, a display of what is *about* to change, and choosing
how many passes `Shift`+`Record` bounces rather than deriving it from the LCM.
Re-scope before starting: this is now `size: M`.

### IN-06 — Take comping and round-robin alternates `size: M`

**Idea.** Keep every pass you recorded on one pad. Flip between them, or let the
song cycle through them so a loop breathes.

**Spec.** `Sample.takes: list[Take]` instead of a single buffer. Recording into a
filled slot adds a take (not replaces, per a setting). A slot's `take_mode` ∈
`{fixed, cycle, random}` picks which take plays on each trigger. Pads on the
sample page's top row select the active take; the display shows take count and
which one sounded last.

**Code.** `project.py` (takes list + migration + per-take WAV files),
`audio.py` (take choice at trigger time from a seeded RNG), `modes/sample.py`.

**Tests.** Three takes cycle in order across three passes; `random` with a fixed
seed is reproducible; v1 single-buffer projects migrate to a one-take list;
deleting a take keeps the others intact.

**Deps.** `F-04`, `NH-04`.

**Status: shipped.** `Sample.takes` / `active_take` / `take_mode`, format
version 11 with one WAV per take, `Shift`+`Record` to add one, encoder 3 to pick
and encoder 4 (or button 7) to choose the mode, `AddTake` / `RemoveTake` /
`SetActiveTake` / `SetTakeMode` on the undo stack. All four of the plan's tests
pass, in `tests/test_takes.py` (75 tests).

**The `random` mode needed a dice stream of its own, and the reason is a bug
rather than tidiness.** "Did this bar play?" is `roll(...) < chance`, so on a
60 % bar every trigger you hear has a roll below 0.6 — reusing that number to
index three takes puts all of them in the first two thirds and the **third take
never sounds at all**. Measured 55.8 / 44.2 / 0.0 on the shared stream and
33.2 / 33.3 / 33.5 once the seed is salted with `_TAKE_SALT`. The measurement is
a test.

**And a `cycle` slot is a pass divisor, exactly like `NH-10`'s `every_n`.** Three
takes mean the song does not repeat until pass three, so a one-pass bounce would
write take 1 and silently discard the other two — the same bug `NH-10` had,
arriving through a different door. `passes_needed` now counts cycling take
counts alongside the `every_n` divisors. `random` is deliberately not a divisor:
it never repeats, so there is no cycle to cover.

Four decisions the plan did not reach, two of them corrections to it:

1. **`takes` is shaped like `layers`, not "instead of a single buffer".** The
   spec's replacement would have invalidated every other field's relationship
   to `audio`. The list is empty for an ordinary slot, and when it is not,
   `audio is takes[active_take]` — one invariant in one method. `set_takes`
   collapses a one-element list back to empty, because "one alternate" and "no
   alternates" are the same state and two representations of one state is how
   invariants rot.
2. **The top row cannot select the take.** The spec put the selection on "pads
   on the sample page's top row", which *are* bars 1–8 of the arrangement —
   using them would silently cost you eight bars. Encoder 3 instead, and it
   installs the take as it turns, so the one you see is the one a pad press and
   `Play` both give you.
3. **Two gestures, not a setting.** "Recording into a filled slot adds a take
   (not replaces, per a setting)" would make `Record` mean different things on
   different days: you would press it expecting a fresh take and quietly collect
   eight. `Record` replaces, `Shift`+`Record` adds, and the record page's title
   says which.
4. **`cycle` advances per pass, `random` per trigger.** Both readings of "picks
   which take plays on each trigger" are useful and they are different features:
   one take holding a whole pass is a loop that breathes across repeats, a take
   per hit is a part that never quite repeats. The plan's own test ("three takes
   cycle in order across three passes") settles which mode is which.

**Alternates and layers never coexist.** Overdubs sum, alternates replace, and
both cannot describe one pad — so `add_take` flattens the layer breakdown,
`Shift`+`New` says so rather than peeling the wrong one, and overdubbing a slot
with alternates overdubs the *selected* one. Nothing audible is lost either way,
since `audio` is the layers' sum. Because alternates are alternates of one
*part*, `apply_edits` and `repair` act on every take, and an alternate is locked
to the original's length; each of those has a test.

Take removal shares button 7 with the mode cycle (`Shift` to remove) because
`Delete` was already "clear all bars" and `Shift`+`Delete` already "delete the
sample" — this is the fourth time an item's natural chord was already taken, and
the second time `Shift` + an existing button was the answer.

### IN-07 — The grid as a clock, the strip as a scrubber `size: S`

**Idea.** Use the hardware nobody else uses. The touch strip is dead weight
today (`translate_midi` drops `pitchwheel`), and the grid is idle during a
count-in.

**Spec.** (a) Count-in takes over the whole grid: a ring of pads fills
clockwise, one pad per 16th, so you can feel the downbeat coming without
looking at a number. (b) The touch strip scrubs the transport when stopped
(position = bar) and acts as a loop-range selector when held with `Shift`.
(c) While playing, the rightmost column pulses on the beat in every mode as an
ambient metronome.

**Code.** `push2.py` (decode `pitchwheel` into a `StripEvent`), `modes/base.py`
(shared beat-pulse overlay), `modes/record.py` (count-in ring), `app.py`.

**Tests.** Strip value 0 → bar 1, max → bar 64, monotonic in between; the
count-in ring lights exactly 16 pads per bar; the pulse overlay never overwrites
a mode's own pad when they collide (mode wins).

**Deps.** `F-08` (strip CC behaviour needs hardware confirmation).

**Status: shipped, with its one dependency still open.** All three parts are
built and tested: `StripEvent` decoded from pitch bend in `push2.py`, a
`count_in_sixteenths` on the engine feeding a count-in ring round the border of
the grid, `App._beat_pulse` as a shared overlay, and `App._strip` scrubbing when
stopped or picking a loop range with `Shift`. 31 tests in `tests/test_strip.py`.

**The strip has still never been touched.** That it speaks pitch bend at all is
Ableton's document's claim, not a measurement; `--selftest` has a step for it
and has never been completed. So the decoding is tested against the *claim*, and
everything downstream is written to be inert rather than wrong if the claim is
false — a strip that sends something else simply never reaches `App._strip`, and
nothing else in the program depends on it. This item is struck because the work
is done, not because the hardware is confirmed.

**It needed a new engine verb, which a test found.** Scrubbing was written as
`play(bar)` then `stop()`, and every scrub landed on bar 1 — because `stop`
rewinds to the top *by design*, being the "back to the start" gesture.
`Engine.seek` is the missing third thing: a position change on a transport that
stays stopped. It refuses while running or recording, because moving the
playhead under a take is never what anybody meant.

Three decisions the plan did not reach:

1. **The pre-roll flashes the ring rather than filling it.** Nothing is being
   counted during the run-up, and a ring that started filling then would arrive
   at the top a bar early — worse than not starting.
2. **The next sixteenth is shown dim before it lands**, so the downbeat is
   visible arriving rather than only once it has arrived. The point of a ring
   over a number is that you do not have to read it.
3. **The pulse only paints pads the mode left off.** The plan asked that the
   mode win a collision; doing it by checking for `OFF` rather than by keeping a
   list of claimed pads means every mode, including ones not yet written, gets
   it right without knowing the overlay exists.

### IN-08 — Timing coach `size: M`

**Idea.** The recorder already knows where the grid is and what you played. It
can show you how tight you are — something no hardware looper does.

**Spec.** After a take, `analysis.py` compares detected onsets against the beat
grid and reports mean offset (are you early or late?), standard deviation
(consistency) and a per-beat scatter on the display. A `coach` setting shows
this after every take; `Shift`+`Device` recalls it for any sample. Purely
informational — never auto-quantizes.

**Code.** `analysis.py` (`timing_report(buf, transport)`), `modes/record.py`,
`display.py` (scatter plot).

**Tests.** A synthetic take with onsets 20 ms late reports +20 ms ± 2; a
perfectly aligned take reports ~0; a take with no onsets reports "no onsets
detected" rather than dividing by zero.

**Deps.** `IN-01` (onset detection), `F-08` (display).

**Status: shipped.** `analysis.timing_report` and a `Timing` record;
`modes/info.py` gained a second view on button 2; `modes/record.py` reports
after a take when the new `coach` setting asks, and `--coach` turns it on for a
run. Purely informational throughout, as the spec insists: nothing here
quantizes anything.

**The chord the spec asked for was taken.** `Shift`+`Device` is already "apply
the edits to the recording for good" — a *destructive* action — and putting an
informational readout on the same chord would be a poor trade even if it were
free. The timing view lives instead on the page that already answers "tell me
about this take", as a second view rather than a second page: button 2 switches
between the spectrogram and the scatter.

**Two facts, not one verdict.** The first version conflated consistency and
placement and produced `very tight: 20ms late`, which is two statements wearing
one label. Playing *consistently* 20 ms behind the beat is a **groove** —
plenty of great drummers do exactly that — while being 5 ms out at random is
the thing to practise. So the report says `very even (±3ms), 20ms behind the
beat`: `evenness` from the spread, `placement` from the mean, separately.

**The grid is inferred, not assumed**, and this is the part the spec left
implicit. Measuring a sixteenth-note pattern against quarter notes reports
every other hit as 125 ms late at 120 BPM — which is not a timing error, it is
the wrong question. So beats, eighths and sixteenths are all tried and the one
the playing fits is kept and named, because "you played sixteenths" is itself
worth knowing. Nothing finer: below a sixteenth the lines sit closer together
than human timing error, so every take would "fit" and the report would mean
nothing.

**A finer grid has to earn it twice, and the second rule came from a test.**
Requiring only a better spread was not enough: seven hits on the beat and one
90 ms late chose a sixteenth grid — 90 ms is near a sixteenth at 120 BPM — and
the report then described that 90 ms error as 35 ms. **A coach understating
your error is the one direction it must not fail in.** So `GRID_OCCUPANCY` also
requires a quarter of the hits to land on lines the coarser grid does not have:
a finer grid is warranted when the *playing* is on it, not when a stray hit
happens to fit. Genuine syncopation — every hit on an off-beat eighth — still
reads as eighths, and there is a test for each direction.

The scatter draws its centre line even with nothing to plot, because a scatter
with no axis cannot be read, and clamps a wild hit to the edge rather than
rescaling the plot around it — one bad hit must not squash the other seven into
the middle row.

`coach` is **off by default**, like the other post-take options: being told how
tight you are is useful when you asked for it and discouraging when you did
not.

---

### IN-09 — Trim by ear `size: M`

**Problem.** `NF-03` gave trim to two encoders, in milliseconds, against a
64-pad picture of the take. That is fine for *adjusting* a trim and hopeless
for *finding* one. Finding the start of a loop means turning a knob, listening,
turning it back, listening again — and between two listens the sound is gone, so
you are comparing what you hear against a memory of what you heard. Nobody
edits audio that way if a machine will loop it for them.

**Idea.** Never stop the sound. The take plays; you **tap when you hear the
point**; the program then loops a very short window around that point so the
decision becomes a *comparison* rather than a recollection, and the knobs move
the point while you keep listening. Accept it and the take plays on, so you can
mark the end the same way.

One button runs the whole thing, and it always means the same thing: **"that's
it."** While you are hunting, that means *here is the point*. While you are
tuning, it means *the point is right, move on*.

**Spec.** `Select` on the sample editor opens it, and `Select` is the button
that then drives all four stages:

| stage | what you hear | a press does | a pad does | the knobs do |
| --- | --- | --- | --- | --- |
| 1 · hunting the start | the whole take, looping | marks the start **here** | marks the start **here** | — |
| 2 · tuning the start | a short loop **from** the start | accepts it → 3 | — | move the point |
| 3 · hunting the end | from the start onward, looping | marks the end **here** | marks the end **here** | — |
| 4 · tuning the end | a short loop **up to** the end | accepts it → done | — | move the point |

- **A pad marks the point as well as the button**, in both hunting stages. The
  user asked for the pad and the pad is the better gesture: your hand is already
  over the grid, and a pad is a percussion surface, so tapping in time with what
  you hear is more accurate than reaching for a button at the edge. The button
  does it too, so the whole flow can be driven one-handed from one key. In a
  hunting stage *any* pad means "now" — the grid is a picture of the take at
  that moment, not a set of 64 destinations, and a pad that meant "jump here"
  in one stage and "now" in another would make the grid unreadable.
- **The window is asymmetric, and that is the point of it.** For a start the
  window runs *forward* from the point, so what you hear at the seam is the
  attack. For an end it runs *back* to the point, so what you hear at the seam
  is the cut. In each case the edge you are judging is the one the loop puts
  under your ear.
- **Fade the edge you are not judging.** A raw window looped in place clicks at
  the seam. So a start window is faded at its *tail* and left sharp at the head;
  an end window is faded at its *head* and left sharp at the tail. The seam is
  then smooth at the far end and honest at the end you care about — and if a
  start lands mid-sustain, the seam clicks, which is the truth and worth
  hearing.
- **Encoder 1 coarse (20 ms), encoder 2 fine (1 ms), encoder 3 the window
  length** (40–1000 ms). Two knobs because one knob with a good step size for
  hunting is a bad one for the last millisecond, and window length because
  40 ms is right for a snare and 600 ms for a vocal entry.
- **Button 1 under the display snaps to the nearest transient.** `IN-01` already
  finds them for slicing, so this is a lookup, and it is the single biggest help
  with the thing the stage exists for.
- **The grid magnifies while tuning.** In a hunting stage the 64 pads are the
  take with a playhead running across them. In a tuning stage they are a
  *zoomed* view, about four windows wide, centred on the point — so the grid
  answers "what am I about to cut" at the resolution the knobs are working at.
- **It commits as `Edits`, in one undo step.** Nothing destructive: the result
  is `trim_start_ms` and `trim_end_ms`, which is what the editor's own encoders
  write, so the editor's picture and `Shift`+`Device` keep working unchanged.
  `Delete` at any stage abandons the whole thing.

**Code.** `audio.py` (an *audition* voice: a looping preview on a negative slot
so the scheduler's gate and loop-renewal logic pass it by, plus its playback
position published once a block the way `sounding` already is),
`modes/trim.py` (the state machine), `history.py` (`SetTrim`, both trims as one
step), `modes/sample_edit.py` (the `Select` binding), `waveform.py` (the
envelope drawing `sample_edit` and `slice` had each copied).

**Tests.** The four stages advance on the button and nowhere else; a pad marks
the point in a hunting stage and is ignored in a tuning stage; the start window
runs forward and the end window backward; the faded edge is the one *not* being
judged and the judged edge is untouched; the point captured is the playhead the
engine published, not a guess from wall-clock time; coarse and fine steps differ
and both clamp inside the take; the end can never cross the start; the commit is
one undo step and restores both trims together; `Delete` leaves the sample
exactly as it was; the audition voice survives a bar line with the transport
running, and is released on exit.

**Shipped.** Four bugs are worth recording, because all four were in the same
place — **the audition voice's lifetime and its position** — and none of them
was visible to a test that drove the page on its own. They only appear when
something *else* touches the engine, which is exactly the seam a new kind of
voice introduces.

1. **`Stop` silenced the page for good.** `Engine._stop_now` calls
   `_release_all()` with no `samples_only`, so it takes negative slots too —
   and nothing was putting the audition back. The page went quiet mid-decision
   with its published playhead frozen, so the *next tap marked frame 0* and
   wrote a wrong trim. Arming a take and voice stealing had the same effect.
   The negative slot was the right call for the scheduler (a bar line must not
   gate an audition) but it is not a general exemption, and treating it as one
   was the mistake. The engine now publishes `auditioning`, and the page
   re-posts when it stops being true — with a latch, so a freshly posted
   audition that has not reached a callback yet is not mistaken for a stopped
   one and re-posted every tick forever.
2. **Four buttons could bury the page while it was still making sound.**
   `Mix`, `Clip`, `Browse` and `Setup` reach `App._global_button`, which opens
   their pages with `push_mode` — and **`push_mode` does not call `on_exit` on
   the mode it covers**. Trim's `on_exit` was the only thing stopping the
   audition, and its `on_tick` no longer ran, so the loop played on forever
   under a mixer. An allowlist of those four would go stale the next time a
   page is added, so the page now *claims* every button it does not use: while
   it owns your ears it owns the surface, and says so.
3. **Replacing an audition clicked when the outgoing loop was near the end of
   its buffer.** `_mix`'s looping branch required `releasing is None`, so a
   released loop took the linear path and was dropped the moment `pos` reached
   the buffer end — truncating the 10 ms release to whatever level the ramp had
   got to. With a 40 ms window that is about a quarter of every encoder tick.
   A release now wraps like anything else. This was **not** an `IN-09` bug: any
   looping sample released at a bar line had the same edge, and had had it
   since `NF-02`.
4. **The published playhead was a block ahead of the speaker.** `voice.pos` was
   read *after* the block was mixed, so it named audio that had been rendered
   and not yet heard. Every tap therefore landed late — **in the same direction
   as human reaction time**, so two errors that should be independent added
   instead. It is now the position at the *start* of the rendered block. The
   device's own output buffer is still unaccounted for; correcting for that
   wants the number `CC-09` measures, and is worth doing if anyone reports
   tapping consistently late.

The lesson that generalises: **a new kind of voice is a new lifetime, and the
existing code is full of things that end voices without knowing yours exists.**
Publishing "is it still running" and healing from the answer is cheaper and
more honest than auditing every caller of `_release_all`.

---

## 9. Small creature comforts

Small, high-gratitude changes. Ideal first tasks, and most are independent.

### CC-01 — Hold to audition `size: S`

**Status: shipped.** `Engine.preview` also gained a `slot` argument so an
auditioned pad lights amber like any other sounding sample.
Holding any filled library pad for >400 ms previews it and does **not** enter
the sample page on release; a short press still navigates. Replaces the
`Shift`+pad preview as the natural gesture (keep `Shift`+pad working).
**Code:** `modes/library.py` (track press timestamps; `app.py` already delivers
press and release events separately). **Tests:** a 100 ms press navigates; a
500 ms press previews and stays in the library.

### CC-02 — Stop semantics `size: S`

**Status: shipped**, except the "release all voices" half, which was already
true: `stop` has always called `_release_all()`, so nothing rings after a stop.
A second `Stop` within 500 ms therefore does the part that was missing -- it
disarms delete/mute/duplicate, the "get me out of here" gesture.  `Shift`+`Stop`
defers to the next bar line via a `stop_at_bar` command; `Intent` gained a
`stop_at_bar` field so `engine.stop_pending` reads true immediately on the UI
thread, the same trick the other transport getters use.  The deferred stop fires
in `_fire_boundaries` *before* the new bar is scheduled, so the bar it lands on
never starts.  Starting playback or arming a take cancels it.
First `Stop` stops and returns to bar 1 (today). A second `Stop` within 500 ms
also releases all sounding voices immediately and clears any armed modifier.
`Shift`+`Stop` stops at the end of the current bar instead of instantly.
**Code:** `app.py`, `audio.py` (`stop(at_bar_end=False)`). **Tests:** deferred
stop happens on the bar line, not the next block.

### CC-03 — Destructive actions confirm `size: S`

**Status: shipped.**  The arm lapses after 3 s, read as a property rather than
expired on a timer so nothing can observe it as armed past the deadline whatever
order the event loop runs in.  Only `Delete` lapses: `Mute` and `Duplicate` are
modes you stay in, while this one destroys takes.  A slot that plays nowhere
deletes straight away -- there is nothing to regret -- and one that plays
somewhere names the cost and waits for a second press on the same pad.  Applied
to `Shift`+`Delete` on the sample page too, via the same `App.confirm_delete`.
`Delete`-armed pads already blink red; add a 3-second arm timeout, and require
the second press within it. Deleting a sample that is used in the arrangement
names the cost: `"slot 7 plays on 12 bars — press again"`. **Code:** `app.py`,
`modes/library.py`. **Tests:** arm expires after 3 s; the warning counts bars.

### CC-04 — Remember where you were `size: S`

**Status: shipped**, as a `ui` section in `settings.json` rather than entries in
`SPECS`: these are a bookmark, not settings anyone edits, and the settings page
is built from `SPECS`.  Restores project, page, slot, loop and metronome.  Only
the library and a sample page are restorable -- coming back up inside a record
arm or a bounce would be hostile -- and a slot deleted since simply lands you at
home.  Bank/page from the original spec do not exist yet (`NF-07`, `NF-11`).

A bug the tests caught: the first version inferred each field's type from its
default, and two defaults are `None`, so **anything** was accepted for them --
including a string where a slot number goes.  `UI_TYPES` now states the types,
and `_ui_ok` excludes `bool` from `int` in both directions.
Persist last-open project, last mode, selected slot, bank/page, loop and
metronome state in `settings.json`; restore on launch so powering on resumes
the session. **Code:** `settings.py`, `app.py` (`snapshot_ui_state`/`restore`).
**Tests:** round-trip through save/load; a stale slot reference (sample deleted)
falls back to the library instead of crashing. **Deps:** `F-06`.

### CC-05 — Press feedback on every button `size: S`

**Status: shipped.**  80 ms, applied in `App.render` as an overlay over whatever
the mode asked for.  Flashed buttons **are** recorded in `_rendered_buttons`,
which is what the spec's "must not leak" actually requires: a cc left out of
that set is never sent `BTN_OFF` and stays lit for good.
Any button press briefly brightens its LED (80 ms) even if the mode ignores it,
so the surface always feels alive and dead buttons are obvious. Implemented in
`App.render` as a short-lived overlay, not in each mode. **Code:** `app.py`.
**Tests:** LED returns to the mode's value after the flash; the flash never
leaks into `_rendered_buttons` bookkeeping.

### CC-06 — Bar-grid legibility `size: S`

**Status: shipped.** Added palette entry 75 (`WHITE_MID`, glyph `m`).
On the sample page, empty bars on a 4-bar boundary (bars 1, 5, 9, …) render
`WHITE_DIM` instead of off, so you can count phrases without counting pads.
Bars 1, 17, 33, 49 (16-bar sections) get a slightly brighter tint. **Code:**
`modes/sample.py`. **Tests:** exact colours at bars 0/4/16 when empty; a
triggered bar still wins over the grid tint.

### CC-07 — Playhead everywhere `size: S`

**Status: shipped.**  `Project.slots_at_bar(bar)` (named for what it returns)
feeds a one-bar look-ahead in the library: a slot that comes in next bar renders
`AMBER_DIM`.  Suppressed when stopped, for muted samples, and past the last bar
when the loop is off -- there is no next bar to look ahead to.
Show the playhead in the library too: during playback, the pad of the slot
whose bar is currently sounding already goes amber — add a dim amber "about to
play next bar" hint so you can see what is coming. **Code:** `modes/library.py`,
`project.py` (`samples_at_bar(bar)`). **Tests:** at bar 4 with a trigger on bar
5, that slot renders `AMBER_DIM`.

### CC-08 — Big transport readout `size: S`

**Status: shipped.**  `App.transport_readout()` is the structured variant the
spec asked for -- `BAR 17C · 3 · 124 BPM` -- and `Push2Display.draw` takes it as
a second argument and draws it large along the bottom, giving up one of the five
text lines for it.  Beats count from 1 because that is how anyone counts them
out loud.  On a machine with no scalable font the big line is merely the same
size as the rest rather than absent.
The display's last line becomes a large, glanceable `BAR 17 · 1.3 · 124 BPM`
(bar, beat.subdivision, tempo) in a bigger font, with the rest of the lines
above it. Readable from across a room. **Code:** `display.py` (second font
size), `app.py` (`status_lines` gains a structured variant). **Tests:** the
formatted string at known positions; `status_lines` keeps working when the
display is absent.

### CC-09 — Latency calibration wizard `size: M`

**Status: shipped**, and deliberately *not* through `Engine`: what is being
measured is the round trip through the audio device, so the less of our own code
sits in the path the more honest the number is.  `calibrate.py` drives an
injected `playrec` (one duplex call, `sounddevice.playrec` in production), and
the tests hand it a synthetic delayed loopback, with and without noise.

Detection is cross-correlation rather than a threshold crossing: a click that
went out of a speaker and came back through a microphone is smeared and
coloured, and its shape survives that far better than its amplitude.  Five
rounds, median, and a refusal above 250 ms -- past that it is a room reflection,
not latency.
`--calibrate` plays a click out and measures when it returns on the input
(loopback cable or speaker+mic), then writes `rec_latency_ms` into settings.
Reports the measured figure and refuses to write an absurd one (>250 ms).
**Code:** `cli.py`, new `calibrate.py`, `settings.py`. **Tests:** with a
synthetic delayed-loopback engine the measured latency matches the injected
delay within one block. **Deps:** `F-06`.

### CC-10 — Save indicator `size: S`

**Status: shipped.**  A `*` on the transport line while anything is unsaved
(`App.unsaved` covers both a dirty project and a pending autosave), `saved` when
the autosave actually writes, and the reason on screen when it cannot.  A failed
save clears the pending write rather than retrying every tick -- a read-only
disk does not heal in 30 ms, and one message beats a hundred.  The silent
`print` on shutdown is gone.
A small dot on the display when there are unsaved changes, a brief `"saved"`
toast when autosave fires, and a one-line message if saving fails (disk full,
read-only) instead of the current silent `print` on shutdown. **Code:**
`app.py`, `project.py`. **Tests:** dirty flag drives the indicator; a save
failure raises a user-visible message and does not crash the loop.

### CC-11 — Paint a range of bars `size: S`

**Status: shipped.**  The held pad's own press decides the direction, so holding
an empty bar paints on and holding a playing one paints off.  One `SetBars` for
the range; the anchor's own toggle stays a separate step, which is why taking a
painted range back is two undos.
On the sample page, hold one pad and press another: every bar between them
toggles to the state of the first press (paint on / paint off). Uses the
press/release events the surface already sends. **Code:** `modes/sample.py`
(track held pads). **Tests:** hold bar 4, press bar 12 → bars 4–12 on; holding
an already-on bar paints off; one undo step for the whole range. **Deps:**
`F-04`.

### CC-12 — Double-tap a bar to fill the phrase `size: S`

**Status: shipped.**  0.35 s window.  Which way it goes is decided by whether the
first tap left the bar playing, so "double-tap empty to fill, double-tap full to
clear" falls out of the toggle that already happened rather than needing its own
rule.  Clipped at bar 64.
Double-tapping an empty bar fills the sample's own length across the following
4 bars (e.g. a 1-bar loop fills bars N…N+3); on a filled bar it clears the
phrase. Makes "just play it for four bars" one gesture. **Code:**
`modes/sample.py`. **Tests:** double-tap on bar 8 of a 1-bar sample sets bars
8–11; a 2-bar sample sets bars 8 and 10. **Deps:** `F-04`.

### CC-13 — Global brightness and a dimmer library `size: S`

**Status: half shipped, deliberately.**  Blank library slots now render
`WHITE_DIM` behind a `dim library` setting, and the brightest white is reserved
for the playhead -- the glare half of the problem, and the half that can be
verified.

The **global brightness SysEx is not built.**  The item says to verify the
command byte against Ableton's manual first; there is no manual and no device
here, so writing a byte and then unit-testing my own guess of it would prove
nothing and could do something else entirely on real hardware.  Same call, and
the same reason, as the LED brightness omission in `F-06`.  It belongs with the
`F-08` hardware pass.
64 white pads at full brightness is glare and current draw. Add a brightness
setting (applied via the Push 2 global LED brightness SysEx — **verify the
command byte against the Push 2 MIDI and Display Interface manual before
implementing**) and switch blank library slots to `WHITE_DIM` with the brightest
white reserved for the playhead. **Code:** `push2.py`, `colors.py`,
`modes/library.py`, `settings.py`. **Tests:** blank slots render `WHITE_DIM`;
the SysEx payload matches the documented form; brightness changes survive a
reconnect. **Deps:** `F-06`; README and `test_flow.py` colour assertions must be
updated together.

### CC-14 — Survive a USB unplug `size: S`

**Status: shipped.**  Writes are wrapped in `PushBase`, so one failure marks the
surface offline and queues a `SurfaceOffline` event on the same queue the app
already drains -- a failed write is news about the surface just as much as a
button press is.  `App._supervise_surface` retries `reopen()` every 2 s, which
re-picks the ports, re-uploads the palette and re-renders everything.

The subtle part is the LED cache: the dedupe in `set_pad` is what makes a 30 Hz
refresh cheap, but a reconnected Push has dark LEDs, so a stale cache would
leave most of the grid black.  `invalidate_leds` sets a sentinel that no palette
index can equal, and it runs on the *failure* too -- the lost write had already
updated the cache, and leaving it would mean that pad never being resent.
If the MIDI port disappears, keep the audio engine running, poll for the device
every 2 s, and on reconnect re-open the port, re-upload the palette and
re-render all LEDs. Never lose the project because a cable moved. **Code:**
`push2.py` (`reopen`, error detection in the callback), `app.py` (supervision in
`tick`). **Tests:** a `SimPush` that raises on write transitions the app to
"surface offline" and recovers when writes succeed again; the transport keeps
running throughout.

### CC-15 — Better simulator `size: S`

**Status: shipped.**  `--script FILE` (plus `--quiet` for CI), `--until-idle`,
`macro NAME cmd; cmd`, `?`, and ANSI colour that switches itself off when stdout
is not a terminal or `NO_COLOR` is set.

`--until-idle` needed rethinking after it was built: read literally it fires at
the first idle moment, which during a script is right after the first take, so
it cut every script off at line four.  It now applies once the script has run
out -- "do not quit while sound is still playing" -- bounded, because a looping
transport never goes idle on its own.
`--script FILE` runs a command file and exits (for CI demos), `--until-idle`
exits when the transport stops, a `macro` command for repeated sequences, colour
output via ANSI so the grid looks like the hardware, and `?` prints the command
list. **Code:** `sim.py`, `cli.py`. **Tests:** a script file drives a full
record→arrange→play flow and exits non-interactively with status 0.

### CC-16 — `doctor`, `--version`, better help `size: S`

**Status: shipped.**  `doctor` works as the positional word or `--doctor`, prints
a state, subject, detail and one-line fix per row, and **always exits 0**:
"everything is missing" is a diagnosis, not a crash.  `--version` and three
worked examples in `--help` as specified.
`python -m push2sampler doctor` prints: Python and package versions, whether
mido/rtmidi/sounddevice/soundfile/pyusb/Pillow are importable, MIDI ports found,
audio devices found, default samplerate, and writable project root — each with a
one-line fix when missing. `--version` prints `__version__`. `--help` gains
three worked examples. **Code:** `cli.py`. **Tests:** `doctor` exits 0 with
everything missing and still prints every row.

### CC-17 — Slot names without a keyboard `size: S`

**Status: shipped.**  `names.py` holds eight categories of eight words; `Select`
on a sample page opens `modes/tag.py`, where the top seven rows are words and
the bottom row is `CC-18`'s colours -- one page for a slot's whole identity,
which is how you actually think about it.

The pads show seven categories at once rather than one: with eight words per
category and seven rows available, showing one would waste six rows and hide the
obvious neighbours.  A second `kick` names itself `kick 2`, because two slots
called the same thing is not a name.
Name a sample by picking from a curated word list (kick, snare, hat, clap, bass,
chord, pad, lead, vox, fx, riser, noise, …) with the display-row buttons paging
through categories, plus an auto-suggestion from `IN-02` when available. Names
show on the display and in `project.json` (already supported). **Code:**
`modes/sample.py`, new `names.py`. **Tests:** picking a name sets
`Sample.name`, persists, and is undoable.

### CC-18 — Colour-code slots `size: S`

**Status: shipped**, as the bottom row of the `CC-17` namer rather than
`Shift`+a top display-row button -- that row is the input meter.  Eight colours
at palette indices 77-83 plus green as "no colour", so tagging is additive and
an untagged library looks exactly as it did.  Pressing a slot's current colour
clears it, so the picker is a toggle rather than a one-way door.  Muted, armed
and sounding states still win over the tag, since those are what you need to see
while playing.
`Shift` + a top display-row button assigns one of eight user colours to the
selected slot; the library renders filled slots in their colour (keeping dim for
muted, amber for sounding) so a 64-slot library becomes readable at a glance.
**Code:** `colors.py` (eight user colours at indices 76–83), `project.py`
(`Sample.color`), `modes/library.py`. **Tests:** colour persists; muted and
sounding states still override; unset colour falls back to green.

---


### CC-19 — Swap two samples `size: S`

**Status: shipped.** `Shift`+`Duplicate` arms it; the filled pads flash cyan,
the pad you pick holds white, the second press exchanges them. `Project.
swap_slots` moves the contents and rewrites each `Sample.slot`, and `SwapSlots`
in `history.py` is the one command whose `revert` is its own `apply`.

Decisions the item left open, settled by writing them:

- **A chord, not a third state of the Duplicate button.** Cycling
  copy -> move -> swap would turn "move" -- currently a Shift on the *second*
  press -- into a mode, changing a gesture that already works.
- **Cyan against dark, not against the duplicate gesture's dim blue.** A test
  caught these looking identical for half of every blink. Going dark also means
  only the slots you can actually pick are lit, which is the question the
  gesture asks.

It also uncovered a real bug it had to fix first: **`copy_slot` silently dropped
four fields.** Colour tags (`CC-18`), overdub layers (`NH-04`), play modes and
choke groups (`NF-02`) each arrived in a different release and none of them
updated the copier, so `Duplicate` quietly lost all four. Fixed, and guarded:
`Project.NOT_COPIED` names the fields a copy deliberately skips, and a test
walks `dataclasses.fields(Sample)` asserting every field is in one list or the
other -- so the next one cannot be forgotten.


**Problem.** `Duplicate` copies a slot and `Shift`+`Duplicate` moves it, but
there is no way to **exchange** two. Getting the kick and the snare the wrong
way round currently takes three gestures and a spare slot — move A somewhere
empty, move B to A, move the spare to B — and if the library is full there is
nowhere to put the spare at all.

**Idea.** Pick two pads; they trade places. Arrangement, audio, name, colour,
gain, edits, play mode, choke group — the whole slot, both ways.

**Spec.**

- `Shift`+`Duplicate` already means "move" *during* a duplicate gesture. Swap
  is its own arming instead: hold **Duplicate** and press **Select** to arm
  swap (or a second press of `Duplicate` cycles `copy → move → swap → off`,
  which is fewer things to remember and shows in the display). Decide this by
  writing both lines in the display and seeing which reads better; the plan does
  not get to settle it from here.
- Armed, the grid flashes; the first pad pressed lights steadily as "A"; the
  second performs the swap. `Duplicate` again cancels, as it does now.
- **Both slots keep their slot number**, which is the whole point: a slot number
  is identity everywhere else in this program — the schedule, the velocity map,
  the WAV filename, every undo entry — so the swap moves *contents*, and each
  `Sample.slot` is rewritten to match its new home. `Project.copy_slot` already
  does that rewriting for a copy; swap needs the same care in both directions.
- One `SwapSlots` command in `history.py`, so it is one undo step. Reverting is
  applying it again, which makes it the rare command whose `revert` can just
  call `apply` — worth a comment saying so rather than looking like a mistake.
- Swapping with an **empty** slot is legal and is exactly a move; say so in the
  display rather than refusing, since the gesture is the same to the hands.
- A sounding voice keeps its own buffer (`NH-06`'s finding), so a swap while
  playing does not cut anything. The *next* bar line picks up the new
  arrangement. Worth a test: that is the behaviour, not an accident.

**Code.** `project.py` (`swap_slots`), `history.py` (`SwapSlots`),
`modes/library.py` (the arming and the two presses), `app.py` (arm state beside
`duplicate_armed`), `sim.py` (a name).

**Tests.** Every field of both samples ends up in the other slot, `Sample.slot`
included; the arrangement follows; one undo restores both; undo twice and redo
twice land in the same place; swapping a filled slot with an empty one empties
the first; swapping a slot with itself is a no-op that does not consume an undo
step; audio files are rewritten so a save/load round-trip keeps the swap.

**Deps.** `NF-04` (the duplicate gesture it shares arming with).

### CC-20 — The mode you are in, on the big display `size: S`

**Status: shipped.** `Push2Display.draw` gained a third region: a banner along
the top, from a new `Mode.title` that defaults to the mode's own name upper-cased
so nothing has to opt in. A transient reads `SETUP  over SLOT 7`. Red while a
take records, amber while something destructive is armed, white otherwise --
and only where the words already say the same thing.

Deviations: the banner costs one of the four text lines rather than fitting
alongside them, which 160 pixels makes unavoidable; and there is no
`Mode.title`-less fallback to parsing a status line, because a status line is
prose that changes with state and a banner has to be the same words in the same
place to be glanceable at all.

**Verified, at last, and it found two bugs the tests had not.** The colour
display renders on real hardware: the banner, the text lines and the big
readout all appear where this item put them. The first photograph of it also
showed a gold striped background with blue text and status lines cut off at the
right-hand edge — `F-08` findings 9 and 10, a transposed byte in the XOR mask
and no measurement of text width, both now fixed. What is *still* unconfirmed is
narrow and specific: with the mask right the background should be black, and
because black cannot reveal a channel-order mistake, the text hue is the only
remaining evidence about whether the BGR565 packing is also correct. Nothing in
this program is visible *only* on the display.


**Problem.** The display's five text lines are dense, and the mode you are in is
implied by what they say rather than stated. When you look up mid-take, "which
page am I on" is the question you actually have, and answering it means reading
a line of prose. `CC-08` gave the bottom of the screen to bar/beat/tempo
because those are the glanceable facts; the mode belongs in that same category
and did not get in.

**Idea.** Put the mode name where it cannot be missed: large, at the top, always
the same place, always the same words.

**Spec.**

- `Push2Display.draw` takes a third piece: a **mode banner** drawn large along
  the **top**, with the existing text lines between it and `CC-08`'s bottom
  readout. The mode name comes from the mode itself, not from parsing its first
  status line — `Mode.name` exists and is already unique, so it wants a
  `Mode.title` beside it for the human-facing form (`SAMPLE 7 "kick"`,
  `RECORD 2 BARS`, `IMPORT`, `MIXER`, `MASTER`).
- **A transient overlay says so.** Perform mode, the settings page and the
  editor are pushed *on top of* another mode (`App._modes`), and knowing you
  will come back to a sample page is exactly what people get wrong — the
  banner should read `SETUP · over SAMPLE 7`, so leaving it is not a surprise.
  That is the same confusion the simulator guide already warns about in prose.
- Colour carries state cheaply where it is unambiguous: red while recording,
  amber while armed for something destructive, white otherwise. **Only** those
  three, and only where the word already says the same thing — colour as
  emphasis, never as the sole carrier, because a display that has never been
  verified is a bad place to put information that exists nowhere else.
- Vertical space is the real constraint: 160 px, currently one big line at the
  bottom plus four text lines. A banner costs one of those four. Check whether
  the modes that use five lines still read with three; where they do not, the
  fix is shorter status lines, not a smaller banner.
- Degrade the same way `CC-08` does: with no scalable font available the banner
  is the same size as the rest rather than absent.

**Code.** `display.py` (a third region and a third font size), `modes/base.py`
(`Mode.title`, defaulting to `name.upper()` so no mode has to opt in),
`app.py` (`mode_banner()`, including the `over …` form for a transient), every
mode that wants a better title than its name.

**Tests.** The banner string for each mode at known state, including the
transient `over` form; a mode with no explicit title falls back to its name
upper-cased; the recording colour is chosen on `rec_state` rather than on the
text; `draw` still works given only lines, so anything holding a display keeps
working; the banner is absent from `status_lines` so the terminal simulator does
not print it twice.

**Deps.** `CC-08` (the display's second font and region), `F-07` (the display
itself).

**Worth stating plainly** (written before the display had ever rendered, kept
because the caution was right and the reason it was right is now on record):
everything in `display.py` was pinned byte-for-byte by unit tests against a fake
USB device and was still unproven end to end. It has since rendered on real
hardware, and the very first photograph showed two defects the tests had
passed over — `F-08` findings 9 and 10. The banner was not among them, so this
item's own design survived contact; but the rule it states holds regardless. Do
not let the display be the reason a mode's state is only visible there.

## 9b. This plan is read by a program

`tools/feature_page.py` builds the public feature page **from this file**. It
reads the roadmap table in section 4 for each item's release and whether it has
shipped (the `~~`strikethrough`~~`), and each item's own `### CODE — Title
\`size: X\`` heading for its title and size. So two conventions in this document
are now load-bearing rather than cosmetic:

1. **An item is shipped when its code is struck through in the roadmap table**,
   and nowhere else. Writing "Status: shipped" in the item's own section without
   striking the table entry leaves the page saying it is unbuilt.
2. **Every item has exactly one `### CODE — Title `size: X`` heading.** Change
   the shape of that line and the page loses the title.

A `†` after a table entry is a footnote marker and is stripped; `← in progress`
on a release is likewise a note to a human reader and not part of its name.

The one thing the page needs that this plan does not give it is a **one-line
description** of each feature, written for somebody who has never opened this
file — a spec is not a description. Those live in the script's `BLURBS`, and a
new plan item with no blurb fails a test rather than rendering a blank line.

This existed because the page said it was generated from the plan and was not:
the numbers had been transcribed by hand, and two releases later it claimed 45
items shipped when the number was 47, with six shipped items still coloured as
unbuilt. **A claim a document makes about itself has to be enforced by
something.**

## 10. Dependency graph and fan-out waves

Read this as "X unblocks the items listed under it". An item with two parents
needs both.

```
F-01  engine queue      unblocks  F-05, F-07, NF-04, NF-09, NH-01
F-02  modes package     unblocks  F-03, F-04  (and all of group D)
F-03  mode stack        unblocks  F-06, NF-03, NF-06, NH-01
F-04  undo              unblocks  NF-01, NF-04, NH-04, NH-05, NH-06,
                                  IN-01, IN-03, IN-06, CC-11, CC-12
F-05  declick           unblocks  NF-02, NF-05
F-06  settings          unblocks  NH-03, CC-04, CC-09, CC-13
F-08  hardware pass     unblocks  IN-07, the display half of NF-03/IN-08
F-09  length truth      unblocks  NF-05, NF-08, NF-10, NH-08, NH-09, IN-01

NF-03 sample editor     unblocks  IN-01, IN-04 (shares the waveform widget)
NF-04 perform mode      unblocks  NF-10
NF-10 velocity          unblocks  NH-10
NF-01 song page     ┐
NF-07 banks         ├── all three rewrite the Project model: one owner,
NF-11 song pages    ┘   in the order NF-10 → NF-07 → NF-01 → NF-11
NF-05 bounce        ┐
NH-10 probability   ├── together with IN-03 these are IN-05's parents
IN-03 patterns      ┘
NF-06 browser           unblocks  NF-08 (shares the list/paging widget)
NH-01 mixer             unblocks  NH-11
IN-01 slicing           unblocks  IN-02, IN-08
IN-02 analysis          unblocks  IN-04, and feeds CC-17
NH-04 overdub           unblocks  IN-06

No parents (start any time): NH-07, NH-12, CC-01, CC-02, CC-03, CC-05,
CC-06, CC-07, CC-08, CC-10, CC-14, CC-15, CC-16, CC-17, CC-18
```

**Wave 1 (parallel, 3 implementers).** `F-01` (owner of group A) · `F-02`→`F-03`
→`F-04` (owner of group B, strictly serial) · any three of the independent
creature comforts (`CC-15`, `CC-16`, `CC-03`).

**Wave 2 (parallel, 4–5).** `F-05` · `F-06`→`F-07` · `F-09` · `CC-01`/`CC-05`/
`CC-06`/`CC-07`/`CC-10` · `F-08` if hardware is available.

**Wave 3 (parallel, 4).** `NF-03` · `NF-04` · `NH-01` · `NH-05`+`CC-11`+`CC-12`
(one owner, all in `modes/sample.py`).

**Wave 4 (parallel, 4).** `NF-01`→`NF-11` and `NF-07` (one owner — both rewrite
the `Project` model) · `NF-05` · `NF-06`→`NF-08` · `NF-02`+`NH-02`.

**Wave 5.** The innovative block, each behind a one-day spike: `IN-01`→`IN-02`
→`IN-04`/`IN-08`, `IN-03`, `IN-06`, `NF-09`, `NH-09`, `IN-05` last since it
composes several others.

**Rule for every wave:** one item per implementer, one owner per contention
group from §3.8, and rebase on `main` before opening a PR.

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| No Push 2 hardware in CI or in this environment | Button CCs, palette SysEx, display protocol and the strip may be wrong | `F-08` selftest + a README checklist of what is confirmed; keep `--sim` authoritative for logic; never let a hardware assumption into a unit test |
| Python in the audio callback | Dropouts under load as features pile into `_mix` | `F-01` stats and xrun events make regressions visible; budget: `_process` under 20 % of a block's wall time at 48 kHz/256; add a benchmark test that fails over budget |
| Feature creep in `audio.py` | The one file everything needs becomes unreviewable | §3.8 single-owner rule; push logic into `project.build_schedule` (offline) rather than the callback wherever the decision can be made per bar instead of per frame |
| Project format churn across `NF-07`, `NF-10`, `NF-11`, `IN-06` | Users lose songs | One migration path, `FORMAT_VERSION` bumped once per change, a loader test per version, and an archived fixture project per version in `tests/fixtures/` |
| Ableton Link / MIDI clock complexity (`NF-09`) | Weeks lost to jitter | Spike first in a standalone script with a synthetic clock; ship `midi_slave` before `midi_master` before Link; accept "internal only" as a valid outcome |
| The innovative block drifts into novelty | Effort spent on things nobody uses | Each `IN` item must state the one gesture it replaces; if it does not remove work from the musician, cut it |
| Latency compensation is manual | Takes land late, users blame the instrument | `CC-09` calibration wizard, and show the compensation figure on the record screen so it is never a silent setting |
| Settings validation silently substituting defaults | A flag appears to do nothing; `--samplerate 8000` was thrown away for a week | Fixed: the CLI now reports any value it could not use. Prefer ranges over closed `choices` lists unless the set really is closed |

---

## 12. Open questions (need a human decision)

- **Q1 — Hardware access.** A Push 2 is expected. `--selftest` is built and
  waiting; what this project needs back is a `hardware-report.json` from it, plus
  the firmware version. Until then every hardware-facing constant stays
  "believed correct, unverified".
- **Q2 — Primary use.** Is this a studio sketchpad (favour `NF-03`, `NF-05`,
  `NF-06`) or a live instrument (favour `NF-04`, `NH-06`, `IN-05`)? The v1.2/v1.3
  ordering flips depending on the answer. Current plan assumes sketchpad first.
- **Q3 — Push 3.** Push 3 standalone runs a Linux host and could run this
  natively. Worth targeting, or stay Push 2 + laptop?
- **Q4 — Sync.** Is playing alongside other gear (`NF-09`) a must-have, or is
  this a self-contained box? It is the single largest item here.
- **Q5 — Song length.** Is 256 bars (`NF-11`) enough, or do we need arbitrary
  length with sections? Arbitrary length breaks "the grid is the document".
- **Q6 — Dependencies.** May we add `soundfile`, `numpy`-only DSP aside, or must
  everything stay stdlib + numpy? `NH-09` (WSOLA) and `IN-02` (analysis) are much
  cheaper with `scipy`.
