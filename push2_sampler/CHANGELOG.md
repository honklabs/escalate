# Changelog

Releases of `push2sampler`, the Push 2 sampler in this directory. Tags are
scoped (`push2sampler-v1.0`) because the repository belongs to another project
and its version namespace is left alone.

Item codes (`CC-03`, `NH-01`, …) are the work items in [`plans.md`](plans.md),
where each one carries a note on what was built and where it departed from the
plan.

---

## Unreleased

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
