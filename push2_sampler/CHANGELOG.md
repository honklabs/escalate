# Changelog

Releases of `push2sampler`, the Push 2 sampler in this directory. Tags are
scoped (`push2sampler-v1.0`) because the repository belongs to another project
and its version namespace is left alone.

Item codes (`CC-03`, `NH-01`, …) are the work items in [`plans.md`](plans.md),
where each one carries a note on what was built and where it departed from the
plan.

---

## Unreleased

### Send a slot to its own output pair (`NH-11`)

With more than two output channels, **Shift** + a mixer strip button walks that
slot through `main` (1/2), `3/4`, `5/6`, `7/8` and back. A kick on 3/4 is a kick
on its own in a pair of headphones while the main outputs carry the rest — which
is what a cue bus is for. Per slot, saved with the project (format 8; every
older format still loads), one undo step, and the mixer's third line lists
whatever is routed and nothing when nothing is.

It only offers the pairs the **open stream** really has, asked of the engine
rather than the settings: a device configured for eight channels that would only
open two has two, and a two-channel device says `only 2 output channels -
nowhere to route slot 5 to` instead of offering a choice that does nothing. A
pair that has *become* unavailable — a project made on an eight-output interface
and opened on a laptop — falls back to the main mix rather than into silence,
flagged `!` and explained in words, the same rule `click_channel` has followed
since v1.2.

#### The main mix was every channel, not the first pair

The bug this item existed to expose. `_mix` wrote a mono take into **every**
output channel: correct on a stereo device, and exactly wrong the moment there
are four, because the whole main mix would then appear on the cue pair too. You
would route a kick to 3/4 and hear the kick *and everything else*. The main mix
is the first pair; `Engine.main_width` now bounds it, in the one-shot path, the
looping path and the input monitor.

#### A routed slot is out of the bounce, and in its stem

A bounce is what comes out of the main outputs, and a cue pair is by definition
not that — so `BounceJob` drops routed slots from the mix rather than letting the
engine's fallback carry them into the file with no way to tell. Its **stem**
keeps the full audio: a stem is what the slot played, and where you were
listening does not change that.

Writing that down corrected a claim that had been in the reference since v1.3:
muted slots were documented as "still exported as stems", and they are — as
silence, because `build_schedule` drops them before a stem is rendered. Both
behaviours are right (a mute says the take does not belong in the song; a route
says only that you are listening elsewhere), and both now have a test and a
table in `docs/reference.md` instead of one sentence that was half true.

### v1.5 — Watch it play

Three features you asked for, and one bug they uncovered.

#### Master playback mode (`NF-12`)

`Shift`+`Session` opens the page whose only job is playback: the library grid,
all 64 slots where they always are, **each pad flashing white as its sample
fires** before falling back to the slot's own colour. One glance says what is
carrying a section and what is sitting out — which no editing page shows.

The flash marks the **attack**, not the duration. `Engine.sounding` is true for
as long as a voice lives, so a 4-bar pad would hold its pad lit for four bars
and say nothing; the engine now publishes `fired` — the slots that *started* a
voice in the last block — recorded in `_add_voice` so a sample played by hand in
perform mode or auditioned from the library flashes too.

Delete, Mute and Duplicate are inert here and say so: this is the page where you
are listening rather than deciding. The display counts how many slots fired in
the bar you are in.

Its own tests caught a bug in it: `_firing` was cleared *after* commands were
applied, so an attack from a queued command was thrown away in the same block it
happened.

#### Swap two samples (`CC-19`)

`Shift`+`Duplicate` arms a swap. The filled pads flash cyan, the pad you pick
holds white, the second press exchanges them — audio, bars, velocities, name,
colour, gain, play mode, choke group and edits. The slot *numbers* stay put,
because a slot number is identity everywhere else in this program. Picking an
empty slot second is a move, and is allowed. One undo step, and the rare command
whose undo is itself applied again.

`Duplicate` alone is unchanged. Swap is a separate chord rather than a third
state of the button: cycling copy → move → swap would turn "move" into a mode
and change a gesture that already works.

#### Duplicate was silently losing four fields

Found while building the swap. `copy_slot` never carried a slot's **colour tag**,
its **overdub layers**, its **play mode** or its **choke group** — three
features, each added in a different release, and none of them updated the
copier. So `Duplicate` quietly dropped all four.

Fixed, and guarded against the next one: `Project.NOT_COPIED` names the fields a
copy deliberately skips, and a test walks every field of `Sample` asserting it is
in one list or the other.

#### The mode you are in, on the big display (`CC-20`)

The display gained a third region: a large banner along the top saying which
page you are on — `LIBRARY A`, `SLOT 7 "kick"`, `RECORD 4 BARS`. It comes from
the mode itself rather than from parsing a status line, because a banner has to
be the same words in the same place to be glanceable.

A layered page says so: **`SETUP  over SLOT 7`**. Forgetting that perform mode,
the settings page and the editor open *on top of* what you were doing is the
single most common confusion about this program, and now the screen says it.

Red while a take records, amber while something destructive is armed — and only
where the words already say the same thing. The colour display has still never
rendered on real hardware, so nothing in this program is visible only there.

### A tempo change no longer moves the playhead

A bug, found while building the clock and worth its own entry because it has
been there all along. Position is kept in frames and a beat is `60/bpm*rate`
frames, so changing the tempo silently *reinterpreted* the same frame count:
64000 frames was bar 4 at 120 BPM and bar 8 at 240.

So doubling the tempo teleported the playhead four bars forward with no audio
in between — tapping a tempo mid-song moved where you were in it, and a ±0.1
BPM nudge at bar 200 moved you by a fifth of a bar. `set_bpm` now preserves the
musical position, in the published intent as well as in the callback, so a
tempo change means only what it says.

Sync did not cause this; it made it impossible to ignore. A control loop whose
actuator instantly moves the thing it measures — by an amount proportional to
how far into the song you are — cannot be tuned at all.

### Follow or send MIDI clock (`NF-09`)

`--clock midi_slave` follows another device's clock, start/stop/continue and
song position. `--clock midi_master` sends 24 ppqn, start/stop and a song
position on each seek. `--clock-port NAME` picks the port, which is **separate
from the Push's own** — the thing sending clock is rarely the thing you are
pressing. `clock_role` and `clock_port` make it stick.

Two decisions carry the feature:

- **The playhead is never moved to correct phase.** A jump would stutter and
  could go backwards, cutting every sounding voice. Only the tempo is nudged.
  The engine's transport needed no changes: the slave calls the same setter a
  hand does, which already refuses mid-take and already clamps.
- **Phase is compared at tick arrival**, where the sender is at exactly
  `n / 24` beats. Comparing on our own 30 Hz refresh would mean reading a
  position quantised to 1/24 beat — 21 ms at 120 BPM, so the 1 ms target was
  arithmetically unreachable that way.

Measured over 32 bars against a synthetic sender: **0.28 ms** steady at 120
BPM, 0.28 ms from a cold start at the wrong tempo, 0.23 ms after a 2:1 cold
start, 1.25 ms through a ±3 % wobble, 3.6 ms with a millisecond of arrival
jitter — and never a backwards step in the music.

Three refusals: a tick gap under 2 ms is a broken sender and is refused rather
than clamped (a clamped 1250 BPM would look like a deliberate 240 and claim a
lock that is not real); a silence over a second unlocks rather than
freewheeling, and re-seeds outright on the next tick; and an incoming tempo is
still ignored mid-take.

**Prototyping first, as the plan insisted, paid for itself.** The throwaway
caught four wrong turns before any of this existed: comparing against a
quantised position, mixing an additive integral with a multiplicative
proportional term (120 BPM settling at 122), an integral not scaled by the tick
interval (half as fast at half the tempo), and — by omission — no model of
actuation delay, which is why the first real measurement was 7.8 ms rather than
the predicted 0.2. A fifth bug only the real rig could find: `poll` compared
every tick in a drained batch against the *latest* tick count instead of its
own, which read as a constant 15 mbeat offset the integrator could not remove.

**Not verified against real gear.** Both roles have only ever seen a synthetic
sender. The numbers are real measurements of real code driven by a simulation —
the same class of risk as `F-08`, and it wants the same treatment.

**Ableton Link is a seam, not a feature.** The lazy import and absent-safe
fallback are real; nothing behind the import has run, because the native
library has never been available here. `--clock link` says `link unavailable`
and leaves you on the internal clock rather than pretending.

### Import audio from disk (`NF-08`)

You could only use what you recorded. `Shift`+`Browse` now opens a file browser
on the pads — white folders, blue audio files — and `--import FILE [--slot N]`
does the same from a terminal with no hardware at all.

One press highlights an entry and the display names it, with length, rate and
channels; a second press opens the folder or imports the file into the first
empty slot, resampled to the session rate.

The two refusals are the feature:

- **It never stretches.** A 3.5-bar file goes in at 3.5 bars and is flagged
  off-grid by the machinery that already flags a take recorded at another tempo
  — same one-button repair on its sample page, and leaving it alone is the right
  answer for a one-shot hit. Silently time-stretching someone's audio to fit a
  grid it was never on would be unrecoverable.
- **It is honest about formats.** `.wav` always; `.flac`, `.aiff`, `.mp3` and
  friends only with `soundfile`. Without it those files are still listed, and
  highlighting one says `needs soundfile for .flac files -- pip install
  soundfile` rather than failing when you press it.

Imports never land over a take, and each is one undo step — with redo putting
back the very sample the import built rather than re-reading a file that may
have moved. New `samples_root` setting (and `--samples-root`) for where the
browser starts; it defaults to the folder your project lives in.

Three bugs found while building it, all fixed before it shipped:

- **`import_target` had a branch that could never run**, preferring "the slot
  you are looking at" when a sample page only ever shows a filled slot. Removed
  rather than left as a comforting no-op.
- **The first press on the top-left pad imported** instead of highlighting,
  because the selection defaulted to index 0 while every other pad needed two
  presses. The inconsistency was also the dangerous direction.
- **A "nothing to import" message was buried** by the folder name notified
  immediately after it — the same burying that hid the auto-normalise note
  behind a page change in v1.2. One `_announce` now says whichever is true.

`Spec.coerce` also gained a `str` guard: `str(None)` was storing the literal
text `"None"`, the same shape of bug as the swallowed `--samplerate` — a
coercion that succeeds at producing nonsense.

### Play modes and choke groups (`NF-02`)

A sample used to play to the end of its recording no matter what else happened.
Right for a drum hit; wrong for anything sustained — trigger a 4-bar chord on
bar 1 and again on bar 3 and the first played straight over the second. Each
sample now has a **play mode**, on buttons 2–5 below the display:

| Mode | Ends when |
| --- | --- |
| `one shot` | the recording runs out (the original behaviour) |
| `loop` | a bar arrives it is *not* triggered on — one trigger holds a section |
| `gate` | the bar it started in ends, however long the audio |
| `retrig` | a new trigger arrives; it cuts the previous voice instead of layering |

Button 8 cycles a **choke group** (1–8): samples in a group cut each other, the
way a closed hat silences an open one. Both are per sample, saved with the
project (format 7, and every older format still loads), and one undo step each.

Three things worth knowing about where the decision is made:

- **Ends happen at bar lines, never by polling.** The engine already splits
  every block at each bar line, so a gate's release begins on the exact frame of
  the line whatever the audio block size is — pinned by a test across three
  block sizes.
- **Ends run before starts.** Voices finishing on a line are released before
  anything new is scheduled onto it, or a retrigger would cut the voice it had
  just started.
- **A slot never chokes itself.** Otherwise `one shot` in a group would
  silently behave like `retrig`, with no way to ask for anything else.

The mixer gained a second fill path for it: a loop point that lands mid-segment
would leave the rest of that segment silent, so a looping voice continues from
the top of its buffer. The seam keeps the 3 ms fades every take has, so it dips
rather than clicks — measured and bounded by a test, which is also what would
catch the wrapping fill breaking.


### Output follows the surface (`F-08` finding 8)

With input fixed, a normal run *still* showed nothing: this device is on the
**Live** port in both directions, not just for input. The earlier "did anything
light?" yes had been asked after blasting both ports, so it never meant what it
appeared to.

- **Output now follows the input port.** Input is the only signal for which port
  the device is actually using — output has none — so when a message arrives on
  a port we are not sending to, output moves there, the palette is re-uploaded
  and the surface repaints. No flag needed, and it works whichever mode the
  Push is in.
- `--midi-port` turns the following **off**: an explicit choice should not be
  second-guessed.
- A failed switch keeps the port already open, so following can never leave
  things worse than not following.
- **Startup now prints the ports it opened.** Two rounds of this were spent
  unable to see the most basic fact about the run.

### Stuck LEDs after a diagnostic (`F-08` finding 7)

`--midi-probe` left the pads and buttons lit when it finished. Mine, not the
device's: it lights everything in order to ask about it, and never turned any
of it off — and it closed each port *before* asking, so nothing could have.

- **The probe blanks each port** after that port's question is answered, so you
  still see the lights while answering.
- Behind it was a real gap. LED state lives in the *device*, so it outlives the
  process that set it, and `clear()` only turns off LEDs the current process lit
  — which in a fresh process is none of them. A crash or a Ctrl-C therefore
  left a lit surface that nothing could reach. **`PushBase.all_off`** sends an
  explicit off to every pad and every button control change in the map, and
  **`open()` now uses it**, so starting the program always gives a clean
  surface.
- **New `--lights-off`** blanks the surface and exits, for when you want the
  Push dark without opening a project.
- `ALL_BUTTON_CCS` in `constants.py` derives from `Btn` plus both display rows,
  with a test asserting every named button is in it — so a control added later
  cannot be left un-blankable.

### The surface was on the other port (`F-08` findings 5 and 6)

`--midi-probe` found it. Input arrives **only on the Live port** — 465 messages
by callback and 262 by polling — while the User port sent nothing at all.
Output reached the device. A Push 2 routes its controls to whichever port
matches the mode it is in, and this one is not in the mode we assumed.

This was a hidden assumption, not a bug in the usual sense. Preferring the port
named "User" was written and documented as a *preference* — coexist with Live,
use the port meant for third parties — when it was really a hard requirement
that the device does not always satisfy.

- **`Push2` now opens every Push input port**, not just the preferred one. Only
  one of them sends, so listening to both costs nothing, and the program works
  in either mode without being told which. One port that will not open no
  longer stops the other. `listen_all=False` restores the old behaviour.
- **New `--midi-port NAME`** forces the port whose name contains `NAME`
  (`live`, `user`, or any substring) in both directions. This is the half a
  listener cannot infer — which port the *lights* should go to.
- **Fixed a bug in `--midi-probe` itself:** it blasted every output port and
  then asked "did anything light?" once, at the end. That answer cannot say
  *which* port lit, which was the entire thing the stage existed to establish.
  It now asks per port and records the answer against that port.
- `--midi-probe` gained the verdict for this case, naming the sending port, the
  silent one, and the exact flag to run with.
- **pyusb without libusb is now named as its own finding.** `No backend
  available` means pyusb can see nothing at all, which says nothing about the
  Push — and previously risked reading as "the device is not on the bus". It is
  also why the colour display cannot work on that machine (`brew install
  libusb`). Reported as a note, separate from the verdict.
- README's hardware table: the port *names* are confirmed; "which port carries
  the surface" is now recorded as **wrong** — assumed User, actually Live.

### `--midi-probe`: measure, don't ask (`F-08` finding 4)

`--led-test` came back negative on every stage: no input from any pad, no light
from factory palette indices, none from ours, no button LEDs, nothing on any
channel — while the ports still opened without error. A useful negative result,
since it eliminates `program_palette`, `index_to_note`, the colour map and the
channel in one run: none of them can matter when no traffic passes either way.

It also means an interactive tool is now the wrong instrument. Once "what do
you see?" is answered "nothing", the remaining questions have to be answered by
the machine.

- **New `--midi-probe`** (`midiprobe.py`) asks almost nothing and reports:
  which **mido backend** is loaded (the program is written against
  `python-rtmidi`; anything else invalidates every other reading); whether the
  Push is **on the USB bus** at all via `pyusb`, independently of MIDI, which
  separates a cable, power or stale-port problem from a MIDI-layer one; input
  read **both by callback and by polling**; **both** Push ports in **both**
  directions; and every exception rather than swallowing it. Writes
  `midi-report.json`.
- It is written to suspect **us** as readily as the device. `Push2` reads input
  via a callback, so a callback that stays silent while polling on the same
  port works is reported as a bug in `push2.py` — in those words — rather than
  as a hardware fault. Likewise, if the *Live* port answers when the User port
  does not, that is stated as a finding about the device.
- Fixed a substring trap in that tool before it shipped: `"rtmidi" in
  "mido.backends.portmidi"` is **true** (`po`**`rtmidi`**), so the obvious
  backend check waved through the one backend it existed to catch. Now an exact
  match against `RTMIDI_BACKENDS`, with a test that asserts the trap and both
  directions of the check. Same family as the `--samplerate` bug: a loose
  comparison that silently accepts the wrong input.

### `--led-test`: why are the pads dark? (`F-08` finding 3)

First time on real hardware, the probe's opening check — one pad lit, which
corner is it? — had no answer, because nothing lit at all. Every later check
asks a question that presumes working LEDs, so the whole probe was about to
return the same silence nine times.

- **New `--led-test`** (`ledtest.py`) isolates the layers instead of assuming
  them: does the Push send *us* anything, do the pads light from a **factory**
  palette index (no SysEx), do they light from **our** uploaded block (SysEx),
  do the button LEDs light, and is it the MIDI channel. It prints a verdict
  naming the layer at fault and writes `led-report.json`.
- The interesting outcome is factory lighting and ours not: every colour in
  `colors.py` is a private palette index of 64 or above, so a SysEx upload that
  does not take means the program paints into entries the device left black —
  with no error anywhere.
- **`--selftest` now stops guessing when the grid is dark.** Answering "none" to
  the orientation check is recorded as "no LED output at all" rather than
  "`index_to_note` needs flipping", and points at `--led-test`.
- `Push2.open(program_palette=False)` — the diagnostic has to see the pads
  before the palette is touched, or a broken upload stays invisible.
- `PushBase.send_pad_raw(index, value, channel)` bypasses the LED dedupe cache
  and can use a channel other than the static one. Nothing on the render path
  uses it.
- **`program_palette` moved to `PushBase`** as a no-op. It existed only on
  `Push2`, so calling it polymorphically raised `AttributeError` — which
  `ledtest` caught and reported as "the device refused the SysEx". Found by its
  own tests, and exactly the failure mode the tool is meant to distinguish.
- New wire-format tests pin what actually goes out: the palette entry's 7-bit
  component split, the static channel on a normal pad write, and the explicit
  channel on a raw one. They supply a fake `mido`, since it is optional and not
  installed in CI.

Confirmed on the device in passing: the port names are `Ableton Push 2 Live
Port` and `Ableton Push 2 User Port` in both directions, and `_pick` chose the
User port — one row of the README's hardware table filled in.

### First hardware feedback (`F-08` finding 1)

- **Removed the "press the Push's `User` button" instruction.** It was wrong.
  `Push2.open` picks the User *port* by name and sends no mode change, so the
  program never needed anything pressed on the device — and on a real Push 2 the
  button the docs named could not be found on the panel. `README.md`,
  `docs/getting-started.md`, `docs/troubleshooting.md` and the `doctor` hint now
  point at the two things that do take the surface away (Ableton Live running,
  bus power) and at `--list-ports`.
- **`--list-ports` guidance for ALSA names.** On Linux the ports often come
  through as `Ableton Push 2 MIDI 1` / `MIDI 2` with no "User" anywhere, in
  which case `_pick` falls through to the first match — documented in
  troubleshooting rather than left to be discovered.
- **The probe no longer implies every button it names exists.** `--selftest`
  labels `User` as possibly absent and says up front that a name missing from
  your panel is itself a finding.
- `Btn.USER = 59` is unchanged and still unbound: a spec value we have no
  reason to trust and no reason to use.

---

## v1.3 — A whole song

Completes the `v1.3` **A whole song** train: 42 of the 58 planned items are
shipped. The instrument stopped being a sketchpad — it now holds a whole song and
can leave the box without a terminal.

### Four times bigger

- **Four banks of 64 samples** (`NF-07`) — 256 in all. `Page ◀/▶` switches bank
  and the grid flashes so you see that you moved. A bank is a *view*, not a song
  section: everything in every bank plays.
- **Four song pages of 64 bars** (`NF-11`) — 256 bars, about eight minutes,
  playing consecutively. `Shift`+`Page ◀/▶` moves the window. **`Repeat` now
  cycles what the loop covers**: this page, the whole song, or off — so you can
  work on one page while the rest waits.

Slot and bar identity stayed a single number through all of that, which is why
every take, velocity, edit and undo step from an older project still works.

### Seeing it

- **A song overview** (`NF-01`). `Clip` turns the grid into a heat map of the
  whole arrangement — each pad is eight bars by eight slots, coloured by how
  much is happening in it, with the playing column brightened. Press a pad to
  zoom in, and each pad is then one bar of one slot, toggling the same triggers
  the sample page does. It is how you notice that bar 33 is bare, or that the
  second half is just the first half again.
- **A readout you can read from across the room** (`CC-08`). The display's
  bottom line is now large: `BAR 17C · 3 · 124 BPM`.
- **A dimmer library** (`CC-13`). Blank pads are dim, so the brightest white
  means the playhead rather than "nothing here". Sixty-four pads at full white
  was glare.

### Finding it again

- **Names, without a keyboard** (`CC-17`). `Select` on a sample page opens a
  word list — eight categories of eight, from `kick` to `vinyl`. A second kick
  names itself `kick 2`.
- **Colours** (`CC-18`). The bottom row of the same page tags a slot with one of
  eight colours, so a full library is readable at a glance. Untagged slots look
  exactly as they did.
- **A project browser** (`NF-06`). `Browse` lists the songs on disk as pads:
  open, create, duplicate, or hold to delete. Opening one saves what you were
  working on and swaps it in **without restarting the audio stream**, so the
  change is silent rather than a gap. It reads only each `project.json`, never
  the audio, so 64 projects draw instantly.

### Playing it

- **Eight scenes** (`NH-06`). The row of buttons below the display stores and
  recalls snapshots of the whole arrangement — `Shift` to store, a press to
  recall — for A/B comparison or live variation. A scene carries what is audible
  and where it plays, never the audio or the gain, and it is one undo step.
- **The metronome you actually want** (`NH-03`). Count-in length, a pre-roll that
  plays the song for a few bars before the take, three click sounds, click level,
  click-only-while-recording, and **a separate click output** — with that set, the
  main mix and everything bounced from it is click-free while a cue pair has it.

### Also

- A bounce now renders **to the last bar in use** rather than to the nominal
  song length. With four pages available and most songs using one, the old
  behaviour would have put two minutes of silence on the end of every export.
- The project format is **version 6**, adding pages, scenes and slot colours.
  Versions 1–5 load unchanged: a project from before pages opens as one page.
- A trigger past the last page, or a slot outside the library, is dropped on load
  **with a warning on the display** rather than kept as a silent surprise.
- The settings page has a third scroll page for the click options.

### What did not ship

**`CC-13`'s global brightness SysEx.** The item says to verify the command byte
against Ableton's manual first. There is no manual and no device here, so
writing a byte and unit-testing my own guess of it would prove nothing and could
do something else entirely on real hardware. The dimmer library — the half that
can be verified — shipped; the rest waits for the hardware pass.

**`NF-07`'s "jump to the first/last used bank".** It and `NF-11`'s song-page
switch both claimed `Shift`+`Page`. The page switch won; the jump was a
convenience.

**`NF-06`'s rename.** `duplicate` plus an automatic date-and-word name covers
what it was for, and a second word-picker for directory names is a lot of
surface for very little.

### Bugs found by using it

- **`count_in_beats` came within one commit of repeating a bug this project had
  already recorded.** `NH-03` lists the count-in lengths as 0/1/2/4/8 and I made
  it a closed `choices` list — which is exactly what silently swallowed
  `--samplerate 8000` in v1.0. Reverted to a range; 3 is a real count-in in 3/4.
- **The new buttons were unreachable in the simulator again** — `Page ◀/▶`,
  `Clip`, `Browse` and `Select` had no names there, so half the release could not
  be driven without hardware. Caught mid-release this time rather than at the
  end, and the simulator guide now says to add the name in the same change.
- **A click's waveform crosses any threshold dozens of times**, so my first
  count-in test counted oscillations rather than clicks and reported 199 clicks
  for a four-beat count-in. It now counts bursts separated by real silence.

**565 tests**, `ruff` clean, `numpy` the only hard requirement.

---

## v1.2 — Playable

Completes the `v1.1` **Trustworthy** and `v1.2` **Playable** trains: 32 of the
58 planned items are now shipped.

### It no longer bites you (v1.1)

- **Deleting something you are using asks twice** (`CC-03`). A slot that plays
  nowhere deletes on one press — there is nothing to regret. One that plays
  somewhere says `slot 7 plays on 12 bars - press again`, because the bar count
  is the fact that decides whether you meant it. `Delete` also disarms itself
  after three seconds, so a stray press cannot lie in wait.
- **It resumes where you left off** (`CC-04`). Project, page, selected slot,
  loop and metronome are remembered, so starting with no arguments picks up the
  session you were in. Only the library and a sample page are restored — coming
  back up inside a record arm would be hostile — and a slot deleted since lands
  you at home instead.
- **Every button press lights its own LED** (`CC-05`), for 80 ms, whether or not
  the current mode does anything with it. A dead button is now obvious.
- **You can tell whether your work is saved** (`CC-10`). A `*` on the transport
  line while anything is unsaved, `saved` when the autosave writes, and the
  actual reason on screen when it cannot — instead of a `print` into a terminal
  nobody is looking at.
- **A moved cable no longer costs a take** (`CC-14`). A failed write marks the
  surface offline, the display says so, the **audio keeps running**, and the
  program retries every two seconds — re-picking the ports, re-uploading the
  palette and relighting the whole grid when the Push comes back.
- **The simulator can be scripted** (`CC-15`). `--script FILE` runs a command
  file and exits with a status, `--quiet` suits CI, `--until-idle` waits for the
  sound to finish, `macro NAME cmd; cmd` names a sequence, `?` prints the
  commands, and the grid comes out in colour when a terminal is watching.
- **`doctor`** (`CC-16`). `python -m push2sampler doctor` prints what is
  installed, which MIDI ports and audio devices it can see, whether it can write
  where you are, and a one-line fix for each thing that is missing. It always
  exits 0: "everything is missing" is a diagnosis, not a crash. Plus
  `--version`, and three worked examples in `--help`.

### Recording and arranging feel good (v1.2)

- **A mixer** (`NH-01`). `Mix` turns the grid into eight vertical level meters —
  one per slot in the current row — with an encoder of gain and a mute button
  per strip, `Solo`, and a master gain on the master encoder. Soloing never
  touches the mute state you set by hand, which is the whole point of a solo
  button; un-soloing gives you back exactly the mix you had.
- **Overdubbing** (`NH-04`). `New` on a sample page records another pass on top
  of the take, sound-on-sound, while the page stays put so you can watch the
  arrangement. Layers are kept individually, so `Shift`+`New` peels the last one
  off — and they survive a save, because "individually removable" that stops
  working after a reload is not the feature.
- **Optional post-take processing** (`NH-08`). Auto-trim to the first transient,
  auto-normalise, and a 2 ms fade at both ends. All three off by default: a take
  should be what you played until you ask for something else. The trim pads the
  end so the take stays exactly its number of bars.
- **`--calibrate`** (`CC-09`). Plays a click, listens for it coming back over a
  loopback cable or a microphone, and writes the measured input latency. Five
  rounds and a median, so one cough does not set your timing; it refuses
  anything over 250 ms, which is a room reflection rather than latency.

### Also

- The settings page **scrolls** with up/down, now that there are more settings
  than there are buttons under the display.
- The project format is **version 5**, adding overdub layers and the master
  gain. Versions 1–4 load unchanged.
- `--script`, `--until-idle`, `--quiet`, `--doctor`, `--calibrate` and
  `--version` are new on the command line; the project argument now defaults to
  the last project you had open.

### Bugs found by using it

Each of these was found by running the thing, not by reading it:

- **The remembered-session bookmark accepted a string where a slot number
  goes.** Field types were inferred from their defaults, and two of those
  defaults are `None`, which accepts anything. Types are now stated.
- **A normalised take said nothing about it.** The note was posted just before
  the page change, whose own announcement immediately buried it — the exact
  silent processing the code comments warn against.
- **`--until-idle` cut every script off at line four.** Read literally it fires
  at the first idle moment, which during a script is right after the first take.
  It now applies once the script has run out.
- **The three new buttons were unreachable in the simulator.** `New`, `Mix` and
  `Solo` had no names there, so two of this release's features could not be
  driven without hardware — against this project's own rule that `--sim` stays
  authoritative for logic.

**459 tests**, `ruff` clean, `numpy` the only hard requirement.

---

## v1.0 — The workflow, end to end, documented

A Push 2 and a microphone as a standalone instrument. Record loops, say where
each one plays across a 64-bar song, arrange with your hands on the grid. No
Ableton Live, no DAW, no mouse.

- **Library** of 64 slots; **record mode** with a bar-length selection and a
  count-in; a **sample page** where the 64 pads are the 64 bars of the song,
  with overlapping playback, per-sample mute and gain, and velocity.
- **Non-destructive editing**: trim, fades, pitch, reverse, normalise, applied
  on the way to the mixer and foldable into the recording when you are sure.
- **Perform mode**: pads fire quantised to the bar, `Record` writes what you
  play into the arrangement, `Delete` erases as the playhead passes.
- **Arranging gestures**: paint a range, double-tap to fill a phrase, duplicate
  a block of bars or a whole slot.
- **Tap tempo** with a 0.1 BPM fine nudge, a bar-end stop, and a one-bar
  look-ahead in the library.
- **Undo**, 64 deep, over everything destructive.
- **Bouncing** to a mix or to stems, faster than real time, without blocking the
  surface.
- **On-device settings** and a settings file, with a command line that reports
  any value it had to refuse.
- A **guided hardware probe** (`--selftest`) and a **terminal simulator**
  (`--sim`) that runs the entire program with no hardware at all.
- **Full user documentation** in [`docs/`](docs/README.md).

### Bugs found by using it

- `--samplerate 8000` was **silently discarded** — the setting had a closed
  `choices` list, so a valid request became the default with no message.
- `Edits.from_dict` stored unvalidated values, so a string in a project file
  crashed inside the renderer.
- A 0.1 BPM nudge was invisible: the readout and the undo label both rounded to
  whole numbers, making the gesture look like a knob that does nothing.
- Perform-mode erase wiped the bar that was already playing.

---

## Not yet verified, in any release

**No Push 2 has ever been attached to this program.** Every hardware constant —
MIDI port names, the control change behind each button, the palette SysEx, the
display protocol — comes from Ableton's *Push 2 MIDI and Display Interface*
document rather than from observation.

```
python -m push2sampler --selftest
```

walks a real device and writes `hardware-report.json`. The "Needs correcting"
table at the top of the markdown it produces is the whole fix list, and it is
the one thing this project cannot produce for itself.
