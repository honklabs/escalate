# push2sampler — product plan

Status: v1.0 shipped (see `README.md`). This document is the backlog and the
rules of engagement for building v1.1 → v2.0.

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

**Every foundation item is now shipped**: `F-01` through `F-09`, plus `CC-01`
and `CC-06`. Each carries a status note in its own section below. ~5,200 lines,
173 tests, `ruff` clean, no hardware needed to test.

That closes v1.1 and the front half of v1.2. Next: `NF-03` (sample editor) and
`NF-04` (live quantized triggering) are the two items that most change what the
instrument can do, and both are now unblocked. `F-08` (hardware verification)
goes to the top of the list the moment a Push 2 is available -- see §12.Q1.

```
push2sampler/
  constants.py  pad/note geometry, button CC map, encoder decode
  colors.py     private palette (indices 64–75) + simulator glyphs
  push2.py      MIDI transport, PushBase/Push2/SimPush, translate_midi()
  audio.py      Transport, Engine (_process), Voice, ScheduledSample, recorder
  project.py    Sample, Project, build_schedule(), save()/load()
  modes/        base (the mode contract), library, record, sample, settings
  history.py    undoable commands + the undo/redo journal
  settings.py   the settings table: defaults, validation, labels, persistence
  app.py        App: event dispatch, LED render loop, autosave
  display.py    optional 960×160 screen over USB bulk
  sim.py        terminal simulator REPL
  cli.py        argparse entry point
  wavio.py      float32/int16 WAV IO + linear resample
```

**Known debt, all of it deliberate and all of it scheduled below:**

- Samples are immutable once recorded: no trim, gain staging is one number
  (`NF-03`).
- Pad velocity is captured in `PadEvent` and thrown away (`NF-10`).
- Tempo changes do not move recorded audio, so an old take drifts against a new
  tempo. It is now *detected* and repairable by padding/trimming (`F-09`);
  pitch-preserving stretching is still open (`NH-09`).
- `display.py` and the `sounddevice` callback have never run against hardware
  in CI or in this repo's history (`F-08`).
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
| Play | 85 | **taken** — transport |
| Record | 86 | **taken** — take/re-record |
| Stop | 29 | **taken** — stop / cancel / back out |
| Session | 51 | **taken** — back to library |
| Note | 50 | **taken** — alias of Session |
| ◀ Left | 44 | **taken** — alias of Session |
| ▲ / ▼ | 46 / 47 | **taken** — prev/next filled slot |
| Mute | 60 | **taken** — per-sample audible toggle / library mute-arm |
| Delete | 118 | **taken** — delete-arm |
| Metronome | 9 | **taken** — click |
| Repeat | 56 | **taken** — loop |
| Shift | 49 | **taken** — modifier |
| Setup | 30 | **taken** — settings page · `Shift`+`Setup` saves the project |
| Tempo encoder | 14 | **taken** — BPM |
| Track encoder 1 | 71 | **taken** — take length / sample gain |
| Undo | 119 | **taken** — undo · `Shift`+`Undo` redo |
| Display row top | 102–109 | **taken** — input level meter (`F-07`) |
| Display row bottom 1 | 20 | **taken** — Sample page: fit an off-grid take |
| Solo | 61 | reserved → `NH-01` |
| Duplicate | 88 | reserved → `NH-05` |
| New | 87 | reserved → `NH-04` (new layer / punch-in) |
| Clip | 113 | reserved → `NF-01` (Song page) |
| Device | 110 | reserved → `NF-03` (Sample editor) |
| Mix | 112 | reserved → `NH-01` (Mixer page) |
| Browse | 111 | reserved → `NF-06`/`NF-08` (projects, import) |
| Page ◀ / ▶ | 62 / 63 | reserved → `NF-07` banks, `NF-11` song pages |
| Fixed Length | 90 | reserved → `NF-04` (quantize amount) |
| Accent | 57 | reserved → `NF-10` (velocity sensitivity on/off) |
| Scale | 58 | reserved → `IN-04` (key/pitch tools) |
| Automate | 89 | reserved → `IN-03` (generative fills) |
| Convert | 35 | reserved → `IN-01` (slice a take) |
| Tap Tempo | 3 | reserved → `NH-07` |
| Master | 28 | reserved → `NH-01` master volume |
| Add Track | 53 | free |
| Select | 48 | free |
| Layout | 31 | free |
| User | 59 | free — leave free, users press it to switch Push modes |
| Octave ▲▼ | 55 / 54 | free |
| ▶ Right | 45 | free |
| Display row bottom | 21–27 | free — 7 contextual buttons, claim per mode |
| Swing encoder | 15 | reserved → `NH-02` |
| Track encoders 2–8 | 72–78 | **taken on the settings page** (one per setting); elsewhere reserved → `NH-01` mixer, `NF-03` editor params |
| Master encoder | 79 | reserved → `NH-01` master volume |

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
| **E — surface/IO** | `push2.py`, `display.py`, `constants.py` | `F-07`, `F-08`, `CC-13`, `CC-14` |
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

Every one of the 58 items below is scheduled here. Creature comforts are
deliberately spread across all five trains: each release should contain
something that makes the instrument nicer to touch, not only bigger.

| Release | Theme | Contents |
| --- | --- | --- |
| **v1.1 — Trustworthy** | it never bites you | `F-01` `F-02` `F-03` `F-04` `F-05` `F-09` `CC-01` `CC-03` `CC-04` `CC-05` `CC-06` `CC-10` `CC-14` `CC-15` `CC-16` |
| **v1.2 — Playable** | recording and arranging feel good | `F-06` `F-07` `NF-03` `NF-04` `NF-10` `NH-01` `NH-04` `NH-07` `NH-08` `CC-02` `CC-07` `CC-09` `CC-11` `CC-12` |
| **v1.3 — A whole song** | bigger than 64 bars, and it leaves the box | `NF-01` `NF-05` `NF-06` `NF-07` `NF-11` `NH-03` `NH-05` `NH-06` `CC-08` `CC-13` `CC-17` `CC-18` |
| **v1.4 — Plays with others** | sync, import, and a verified surface | `F-08` `NF-02` `NF-08` `NF-09` `NH-02` `NH-11` `NH-12` |
| **v2.0 — Instrument** | the ideas nobody else has | `IN-01` `IN-02` `IN-03` `IN-04` `IN-05` `IN-06` `IN-07` `IN-08` `NH-09` `NH-10` |

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

### NH-01 — Mixer page `size: M`

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

### NH-03 — Metronome and count-in options `size: S`

Count-in length (0/1/2/4/8 beats), pre-roll (start the loop N bars before the
take), click sound (sine/tick/cowbell), click level, click-only-while-recording,
and an optional separate click output channel pair. All in settings (`F-06`)
plus `Shift`+`Metronome` for the level. **Code:** `audio.py` (`make_click`
variants, click routing), `settings.py`, `modes/settings.py`. **Tests:** each
count-in length produces that many clicks before frame 0; click routing keeps
the main mix click-free when a separate pair is configured. **Deps:** `F-06`.

### NH-04 — Overdub onto an existing sample `size: M`

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

`Duplicate` (CC 88) held + a pad copies that slot (audio shared copy-on-write,
arrangement copied) to the next empty slot. On a sample page, `Duplicate` + bar
A then bar B copies the trigger pattern of bars A…A+n to B. Shift-variants move
instead of copy. **Code:** `modes/library.py`, `modes/sample.py`, `project.py`
(`copy_slot`, `copy_bar_range`). **Tests:** duplicated slot is independent after
an edit; bar-range copy handles wrap at bar 64 by clipping; all operations
undoable. **Deps:** `F-04`.

### NH-06 — Scenes / arrangement snapshots `size: M`

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

`Tap Tempo` (CC 3): four taps set the BPM from the median inter-tap interval,
outliers rejected, tempo refused while recording (as today). `Shift`+`Tap`
resets. Nudge: `Shift` + tempo encoder already does ±10; add `◀/▶` for ±0.1 for
beat-matching. **Code:** `app.py`, `audio.py` (`set_bpm` already clamps).
**Tests:** taps at a known interval yield the right BPM within 0.5; an outlier
tap is ignored; tapping during a take is refused. **Deps:** none.

### NH-08 — Auto-trim and auto-normalize on record `size: S`

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

### NH-11 — Multiple output pairs and a cue bus `size: M`

Route a slot to output pair 1/2 or 3/4, and send the metronome to the cue pair
so the click stays out of the mix. Needs `out_channels` > 2 and a per-slot
`output` field; `_mix` writes into the right column slice. **Code:** `audio.py`,
`project.py`, `modes/mixer.py`, `settings.py`. **Tests:** a slot routed to 3/4 is
silent on 1/2 and present on 3/4; with a 2-channel device, routing falls back to
1/2 with a warning. **Deps:** `NH-01`.

### NH-12 — Remote monitor page `size: M`

An optional local HTTP page (stdlib `http.server`, no dependency) on
`--monitor-port 8765` showing the live grid, transport and meters, updating via
server-sent events. Useful for teaching, streaming overlays, and debugging the
surface without hardware. Read-only — it must never accept commands, and it must
bind to localhost by default. **Code:** new `monitor_http.py`, `app.py` (publish
a snapshot dict), `cli.py`. **Tests:** snapshot serialization matches the LED
state; the server thread shuts down cleanly with the app; disabled by default.
**Deps:** none.

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

**Deps.** `NF-05`, `NH-10`, `IN-03`.

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
First `Stop` stops and returns to bar 1 (today). A second `Stop` within 500 ms
also releases all sounding voices immediately and clears any armed modifier.
`Shift`+`Stop` stops at the end of the current bar instead of instantly.
**Code:** `app.py`, `audio.py` (`stop(at_bar_end=False)`). **Tests:** deferred
stop happens on the bar line, not the next block.

### CC-03 — Destructive actions confirm `size: S`
`Delete`-armed pads already blink red; add a 3-second arm timeout, and require
the second press within it. Deleting a sample that is used in the arrangement
names the cost: `"slot 7 plays on 12 bars — press again"`. **Code:** `app.py`,
`modes/library.py`. **Tests:** arm expires after 3 s; the warning counts bars.

### CC-04 — Remember where you were `size: S`
Persist last-open project, last mode, selected slot, bank/page, loop and
metronome state in `settings.json`; restore on launch so powering on resumes
the session. **Code:** `settings.py`, `app.py` (`snapshot_ui_state`/`restore`).
**Tests:** round-trip through save/load; a stale slot reference (sample deleted)
falls back to the library instead of crashing. **Deps:** `F-06`.

### CC-05 — Press feedback on every button `size: S`
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
Show the playhead in the library too: during playback, the pad of the slot
whose bar is currently sounding already goes amber — add a dim amber "about to
play next bar" hint so you can see what is coming. **Code:** `modes/library.py`,
`project.py` (`samples_at_bar(bar)`). **Tests:** at bar 4 with a trigger on bar
5, that slot renders `AMBER_DIM`.

### CC-08 — Big transport readout `size: S`
The display's last line becomes a large, glanceable `BAR 17 · 1.3 · 124 BPM`
(bar, beat.subdivision, tempo) in a bigger font, with the rest of the lines
above it. Readable from across a room. **Code:** `display.py` (second font
size), `app.py` (`status_lines` gains a structured variant). **Tests:** the
formatted string at known positions; `status_lines` keeps working when the
display is absent.

### CC-09 — Latency calibration wizard `size: M`
`--calibrate` plays a click out and measures when it returns on the input
(loopback cable or speaker+mic), then writes `rec_latency_ms` into settings.
Reports the measured figure and refuses to write an absurd one (>250 ms).
**Code:** `cli.py`, new `calibrate.py`, `settings.py`. **Tests:** with a
synthetic delayed-loopback engine the measured latency matches the injected
delay within one block. **Deps:** `F-06`.

### CC-10 — Save indicator `size: S`
A small dot on the display when there are unsaved changes, a brief `"saved"`
toast when autosave fires, and a one-line message if saving fails (disk full,
read-only) instead of the current silent `print` on shutdown. **Code:**
`app.py`, `project.py`. **Tests:** dirty flag drives the indicator; a save
failure raises a user-visible message and does not crash the loop.

### CC-11 — Paint a range of bars `size: S`
On the sample page, hold one pad and press another: every bar between them
toggles to the state of the first press (paint on / paint off). Uses the
press/release events the surface already sends. **Code:** `modes/sample.py`
(track held pads). **Tests:** hold bar 4, press bar 12 → bars 4–12 on; holding
an already-on bar paints off; one undo step for the whole range. **Deps:**
`F-04`.

### CC-12 — Double-tap a bar to fill the phrase `size: S`
Double-tapping an empty bar fills the sample's own length across the following
4 bars (e.g. a 1-bar loop fills bars N…N+3); on a filled bar it clears the
phrase. Makes "just play it for four bars" one gesture. **Code:**
`modes/sample.py`. **Tests:** double-tap on bar 8 of a 1-bar sample sets bars
8–11; a 2-bar sample sets bars 8 and 10. **Deps:** `F-04`.

### CC-13 — Global brightness and a dimmer library `size: S`
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
If the MIDI port disappears, keep the audio engine running, poll for the device
every 2 s, and on reconnect re-open the port, re-upload the palette and
re-render all LEDs. Never lose the project because a cable moved. **Code:**
`push2.py` (`reopen`, error detection in the callback), `app.py` (supervision in
`tick`). **Tests:** a `SimPush` that raises on write transitions the app to
"surface offline" and recovers when writes succeed again; the transport keeps
running throughout.

### CC-15 — Better simulator `size: S`
`--script FILE` runs a command file and exits (for CI demos), `--until-idle`
exits when the transport stops, a `macro` command for repeated sequences, colour
output via ANSI so the grid looks like the hardware, and `?` prints the command
list. **Code:** `sim.py`, `cli.py`. **Tests:** a script file drives a full
record→arrange→play flow and exits non-interactively with status 0.

### CC-16 — `doctor`, `--version`, better help `size: S`
`python -m push2sampler doctor` prints: Python and package versions, whether
mido/rtmidi/sounddevice/soundfile/pyusb/Pillow are importable, MIDI ports found,
audio devices found, default samplerate, and writable project root — each with a
one-line fix when missing. `--version` prints `__version__`. `--help` gains
three worked examples. **Code:** `cli.py`. **Tests:** `doctor` exits 0 with
everything missing and still prints every row.

### CC-17 — Slot names without a keyboard `size: S`
Name a sample by picking from a curated word list (kick, snare, hat, clap, bass,
chord, pad, lead, vox, fx, riser, noise, …) with the display-row buttons paging
through categories, plus an auto-suggestion from `IN-02` when available. Names
show on the display and in `project.json` (already supported). **Code:**
`modes/sample.py`, new `names.py`. **Tests:** picking a name sets
`Sample.name`, persists, and is undoable.

### CC-18 — Colour-code slots `size: S`
`Shift` + a top display-row button assigns one of eight user colours to the
selected slot; the library renders filled slots in their colour (keeping dim for
muted, amber for sounding) so a 64-slot library becomes readable at a glance.
**Code:** `colors.py` (eight user colours at indices 76–83), `project.py`
(`Sample.color`), `modes/library.py`. **Tests:** colour persists; muted and
sounding states still override; unset colour falls back to green.

---

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

---

## 12. Open questions (need a human decision)

- **Q1 — Hardware access.** Is there a Push 2 available to run `F-08` against,
  and on which firmware? Until answered, every hardware-facing constant is
  "believed correct, unverified", and `F-08` stays at the top of the list.
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
