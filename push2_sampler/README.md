# push2sampler

A Python program that turns an **Ableton Push 2** into a standalone sampler and
song sketchpad: **256 samples over 256 bars**, about eight minutes of music. No
Ableton Live involved -- the program talks to the Push 2 directly over its User
MIDI port, and does its own recording, mixing and bar-accurate playback.

```
pip install -r requirements.txt
python -m push2sampler my-song           # with a Push 2 plugged in
python -m push2sampler --sim my-song     # no hardware: terminal simulator
```

## Documentation

| | |
| --- | --- |
| **[docs/getting-started.md](docs/getting-started.md)** | A tutorial: unplugged Push 2 to a finished, bounced song, using every feature. Start here. |
| **[docs/reference.md](docs/reference.md)** | Every mode, control, colour, setting, file format and command-line option. |
| **[docs/cheatsheet.md](docs/cheatsheet.md)** | One page to print and keep next to the Push. |
| **[docs/troubleshooting.md](docs/troubleshooting.md)** | Symptom → cause → fix. |
| **[docs/simulator.md](docs/simulator.md)** | Driving the whole program from a terminal, with no hardware. |
| **[CHANGELOG.md](CHANGELOG.md)** | What shipped in each release, and the bugs each one turned up. |

The rest of this file is a summary for people working on the code;
[docs/](docs/README.md) is for people using it.

## When you first plug the Push 2 in

Ask the program what it can see:

```
python -m push2sampler doctor
```

One row per thing that matters -- Python, each optional package, the MIDI ports
and audio devices it can find, whether it can write where you are -- each with a
one-line fix when it is missing. It always exits 0: "everything is missing" is a
diagnosis, not a crash.

Then run the hardware probe before anything else:

```
python -m push2sampler --selftest
```

It walks through every hardware guess this program makes -- port names, the note
each pad sends, what each palette colour looks like, the control change behind
every button, encoder direction, the touch strip, the display -- and writes down
what your Push 2 *actually* does. Press or turn what it names; type an answer
when it asks a question; Enter skips a step and `q` quits early and still saves.

It takes a few minutes and leaves `hardware-report.json` plus a readable
`hardware-report.md` in the current directory. Commit those (or paste the
markdown): the `Needs correcting` table at the top of the markdown is everything
needed to fix whatever turns out to be wrong.

Why this exists: **every hardware constant in this program came from Ableton's
Push 2 MIDI and Display Interface document, not from a device.** The maps are in
one table in `constants.py`, and until the probe has run they are educated
guesses.

## The workflow

### 1. Sample Library

All 64 pads are sample slots -- one **bank** of the four. `Page ◀/▶` switches
bank and the grid flashes so you know you moved; a bank is a *view*, so
everything in every bank plays regardless of which one you are looking at.

| Pad | Meaning |
| --- | --- |
| dim white | blank slot |
| **green** | filled slot |
| dim green | filled, but muted (you won't hear it) |
| amber | that sample is sounding right now |
| dim amber | it comes in on the **next** bar |
| yellow | filled, but the take no longer fits its bars — see below |

* Press a **blank** pad → **Record mode** for that slot.
* **Tap** a **filled** pad → that sample's own **Sample page**.
* **Hold** a filled pad (about half a second) → audition it instead, without
  leaving the library. The pad turns amber while it plays. `Shift` + a filled
  pad does the same thing immediately.
* **Duplicate** then a pad copies that slot to the next empty one, arrangement
  and all; `Shift` on the pad press moves it instead. The copy shares the
  original's audio until either one's edits are applied, so duplicating a long
  take is free.
* The eight buttons **below the display** are scenes: `Shift` stores the whole
  arrangement in one, a plain press recalls it. For A/B-ing two versions of a
  chorus, or switching between them live.
* `Shift`+`Browse` opens an **import browser**: a file browser on the pads,
  white for folders and blue for audio. One press highlights and describes, a
  second imports into the first empty slot, resampling to the session rate. It
  never lands over a take and it never *stretches* -- audio that is not a whole
  number of bars is flagged off-grid at its real length, with the same one-button
  repair as a take recorded at another tempo. `--import FILE [--slot N]` does the
  same from a terminal.

### 2. Record mode

The pads show the length of the take **in bars**: white = included, off = not.
The selection always starts at the top-left pad, so pressing a pad simply means
"record up to and including this bar" — top-left is 1 bar, the end of the first
row is 8 bars, the bottom-right pad is 64 bars.

Press **Record**: you get a **four-beat count-in** (click on every beat, accent
on the downbeat), then recording begins exactly on the downbeat and runs for
precisely the number of bars you selected. While it records, the selected pads
fill in red behind the playhead. When the last bar ends, recording stops, the
take is stored in the slot, and its **Sample page** opens.

The rest of the song plays during the count-in and the take, so you can record
in time with what is already there (`--no-play-while-recording` turns that off).
`Stop` cancels a take in progress.

### 3. Sample page

The 64 pads are now **64 bars of the song** -- one of four pages, moved with
`Shift`+`Page ◀/▶`. `Repeat` cycles what the loop covers: this page, the whole
song, or off.

Press a pad to enable or disable this sample on that bar:

| Pad | Meaning |
| --- | --- |
| green | this sample plays here |
| two dimmer greens | plays here, but softer -- see velocity below |
| dim blue | some *other* sample plays here |
| faint white | an empty bar that starts a 4-bar phrase |
| brighter white | an empty bar that starts a 16-bar section |
| white | the playhead, while the song is playing |
| amber | the playhead, on a bar where this sample plays |
| flashing blue | the first bar of a block being duplicated |

The two faint tints are a ruler: they fall on columns 1 and 5 of every row, with
the brighter mark every other row, so you can count phrases without counting
pads.

Samples may overlap freely — a 4-bar sample triggered on bars 0 and 2 will
simply play over itself, and other samples layer on top.

Three gestures arrange blocks rather than single bars: **hold one pad and press
another** paints every bar between them (on or off, whichever the held pad's own
press produced); **double-tap** an empty bar lays the take across the next four
bars, spaced by its own length, and double-tapping a playing bar clears those
four; **Duplicate** then the start of a block then where it goes copies it, with
the gap between the two presses deciding how long the block is. Each is one undo
step however many bars it wrote.

* **Play mode** decides how the sample *ends*, on buttons 2-5 below the display:
  `one shot` plays to the end of the recording (the original behaviour);
  `loop` repeats until a bar where it is not triggered, so one take can hold a
  section without a trigger on every bar; `gate` stops at the end of the bar it
  started in, which is what a 4-bar pad needs when the next chord arrives; and
  `retrig` cuts the previous voice of that slot instead of layering. Button 8
  cycles a **choke group** (1-8): samples in a group cut each other, the way a
  closed hat cuts an open one. A sample never chokes itself -- that is
  `retrig`'s job, and conflating the two would make `one shot` in a group
  silently behave like `retrig`.
* **Record** re-records the take into the same slot, keeping its arrangement.
* **Mute** decides whether you hear *this* sample while designing the song —
  this is the per-sample enable/disable.
* **Delete** then any pad clears every bar for this sample;
  `Shift` + **Delete** deletes the sample and returns to the library.
  Both are undoable, as is everything else below.
* The first track encoder sets this sample's gain.
* **Accent** decides whether this sample responds to how hard you hit a pad.
  With it off (the default) every bar plays at the sample's own level, which is
  what a take toggled in by hand should do. With it on, the green of each bar
  shows how hard it was played.

Then **Session** (or the left arrow) takes you back to the library, where you
repeat the whole process with the next sample.

### Takes that fall off the grid

A take is recorded as an exact number of bars at the tempo of the moment, and it
remembers that tempo. Change the song's tempo and the audio no longer fills
those bars — a two-bar loop cut at 240 BPM is 1.83 bars at 220. Rather than
drift silently, the slot turns **yellow** in the library, and its page says so:

```
OFF GRID: 1.83 bars at 220 BPM (recorded at 240) - button 1 below to fit
```

The first button under the display pads or trims the take to fit exactly (and
it is undoable). Nothing is done behind your back: the audio is left alone
until you ask. Pitch-preserving stretching is a later item.

### Undo

`Undo` takes back the last 64 edits and `Shift`+`Undo` puts them back: a
deleted take returns with its audio and its arrangement, a cleared arrangement
returns with its bars, a tempo nudge returns to the old tempo. A sweep of an
encoder is one undo step, not forty. The journal is in memory only — it is a
safety net for your hands, not project history.

### 3b. Overdubbing

`New` on a sample page records another pass **on top of** the take rather than
replacing it: the count-in runs, the song plays, the take plays wherever it is
arranged, and what you play is summed in. The page stays put, so you watch the
arrangement rather than a recording screen.

Layers are kept individually, so `Shift`+`New` peels the last one off -- as many
times as you like, back to the original recording, which is never removable. The
display counts them. Both directions are one undo step, and the layers are saved
as their own WAVs so a pass can still be taken off tomorrow.

Applying edits or fitting an off-grid take collapses the layers into one: both
replace the audio with something that is no longer their sum, so the breakdown
would be a lie. The sound does not change.

### 3c. The mixer

`Mix` turns the grid into eight vertical level meters -- one per slot in the
current row -- with an encoder of gain and a mute button per strip, `Solo`, and a
master gain on the master encoder. Row by row rather than all 64 at once, because
there are only eight encoders and a fader you cannot see the value of is worse
than no fader. `Up`/`Down`, or pressing any pad, moves rows.

**Solo is stored separately from mute**, so soloing and then un-soloing gives
back exactly the mix you had -- which is the whole point of a solo button. Solo
is not undoable (it is a listening decision, not an edit); master gain is, and it
is saved with the project.

### 3d. Naming and colouring a slot

`Select` on a sample page. The top seven rows of pads are words -- eight
categories of eight, drums through field recordings -- and the bottom row is
eight colours. A library of `S01`..`S64` is unfindable; `kick` in orange is not.
A second `kick` names itself `kick 2`. Both are undoable and both persist.

### 3e. The song overview

`Clip`. The whole arrangement at once, as a heat map: each pad is eight bars by
eight slots, coloured by how much happens in it, with the playing column
brightened. Press a pad to zoom in and each pad is one bar of one slot, toggling
the same triggers the sample page does.

It cannot be one pad per bar per slot -- that is 4096 cells on 64 pads -- and a
density map is the honest compromise: you see the shape of the song, then zoom
for the detail.

### 3f. The project browser

`Browse`. The songs on disk as pads: open, create, duplicate, or hold to delete.
Opening one saves what you were working on, stops the transport, and swaps the
project **without restarting the audio stream**, so the change is silent. Only
each `project.json` is read -- never the audio -- so sixty-four projects draw
instantly.

### 4. Perform mode -- play the song in

`Shift`+`Play` starts the loop and turns the grid back into the sample library,
except now the pads **fire**: a press plays that sample, quantised to the next
grid line so it lands in time even when your hand does not. `Fixed Length`
cycles the quantize amount (off, 1/4 bar, 1/2 bar, 1 bar).

Press `Record` and what you play is also **written into the arrangement**, at
the bar it sounded in -- so you can build the song by playing it, pass after
pass, instead of toggling bars. `Delete` does the opposite: while it is armed,
bars are wiped as the playhead crosses them, starting from the next bar line.
Everything you play in or erase is one undo step.

`Session` goes back to the library.

### 5. The sample editor

`Device` on a sample page opens the editor. Each encoder above the display owns
one parameter, and the button under it resets that parameter (or toggles it,
where it is a switch):

| | | | |
| --- | --- | --- | --- |
| trim in | trim out | fade in | fade out |
| pitch (±12) | gain | reverse | normalise |

The grid becomes the take: 64 pads, one per slice, lit by how loud that slice
is, with the parts you are trimming away in dim red. Press a pad to hear the
take from that point. The display carries a one-line picture of the waveform and
the edited length.

**Nothing here touches the recording.** Edits are stored beside the audio and
applied on the way to the mixer, so you can change them for as long as you like,
undo any of them, and still have the original take. `Shift`+`Device` folds them
in for good when you are sure — and even that is one undo step.

A trimmed take is shorter than its bars, so it will show up as off-grid
(yellow in the library). That is not a bug: the loop really is shorter now, and
you either meant it or you repair it.

### 6. Bouncing

`Shift`+`Record` in the library renders the whole song to
`<project>/bounces/<timestamp>.wav`. The grid becomes one progress bar while it
works -- the render happens a chunk at a time inside the event loop, so the
surface stays live and you can keep playing. It runs far faster than real time.

From a terminal, with no hardware and no audio device needed at all:

```
python -m push2sampler --bounce song.wav my-song     # the whole mix
python -m push2sampler --stems stems/ my-song        # one WAV per slot
```

Stems sum back to the mix exactly, and both keep the tails of samples that
overrun the last bar.

### Settings

`Setup` opens the settings page and closes it again. The pads stay dark, because
nothing on this page should feel like it edits your song; instead each of the
eight buttons under the display owns one setting, the encoder above it adjusts
the value, and pressing the button cycles it:

| | | |
| --- | --- | --- |
| count-in beats | monitoring | monitor gain |
| record latency | play while recording | autosave delay |
| input device | audio block size | |

Changes take effect immediately and are written to
`~/.config/push2sampler/settings.json` when the page closes (`--settings PATH`
puts it elsewhere, `--no-settings` ignores it). Picking a device that will not
open is not fatal: the old one is kept and the display says what went wrong.

Settings come from three places, each overriding the last: the built-in
defaults, then that file, then this command line. Command-line values steer one
run without being written back.

Sample rate and channel counts stay on the command line, since changing them
means resampling every take that is already loaded.

## Key map

| Control | Action |
| --- | --- |
| 8x8 pads | slot / take length / song bar, depending on the mode |
| hold a pad | Library: audition the sample instead of opening its page |
| hold a pad, press another | Sample page: paint every bar between them |
| double-tap a pad | Sample page: fill or clear the 4-bar phrase from there |
| `Shift`+`Play` | open/close perform mode and start the loop |
| `Shift`+`Record` | Library: bounce the song to a file |
| `Accent` | Sample page: velocity response on/off |
| `Device` | Sample page: open the editor · `Shift`+`Device` applies its edits |
| `Fixed Length` | Perform: quantize amount |
| `Play` | start or stop the song from bar 1 |
| `Stop` | stop; in Record mode cancel the take, then back out to the library |
| `Shift`+`Stop` | stop at the end of the current bar (`ENDING` on the display) |
| `Stop` twice quickly | stop, and disarm whatever was armed |
| `Record` | Library: record into the first free slot · Record mode: go · Sample page: re-record |
| `Session`, `Note`, `◀` | back to the Sample Library |
| `Mute` | Sample page: hear / don't hear this sample |
| `Duplicate` | arm duplicate: Library copies a slot, Sample page copies a block of bars |
| `New` | Sample page: overdub another pass -- `Shift`+`New` removes the last layer |
| `Mix` | open/close the mixer: eight strips of gain, mute, solo and meters |
| `Solo` | Mixer: arm solo (press again to clear it) |
| Master encoder | Mixer: gain on the whole mix |
| `Delete` | arm delete (then press a pad) · `Shift`+`Delete` on a sample page deletes it |
| `Undo` | take back the last edit · `Shift`+`Undo` redoes it |
| `Metronome` | click on/off · `Shift`+`Metronome` cycles input monitoring |
| button 1 below the display | Sample page: fit an off-grid take to its bars |
| the 8 buttons above the display | input level meter |
| `Repeat` | loop scope: this page / the whole song / off |
| `Page ◀` / `Page ▶` | bank A-D · `Shift`+`Page` moves the song page instead |
| `Clip` | the song overview -- again to zoom out, then to leave |
| `Browse` | the project browser |
| `Select` | Sample page: name and colour this slot |
| buttons below the display | Library: the eight scenes (`Shift` stores) |
| `▲` / `▼` | Sample page: jump to the previous / next filled slot |
| `Tap Tempo` | four taps set the tempo · `Shift`+`Tap` discards them |
| Tempo encoder | BPM (hold `Shift` for ±10, hold `Tap Tempo` for ±0.1) |
| Track encoder 1 | Record mode: take length · Sample page: gain |
| `Setup` | open/close the settings page · `Shift`+`Setup` saves the project |

## Timing and recording

The engine runs one duplex audio stream and keeps the transport position in
frames. A block is split at every beat, bar, loop point and end-of-take, so a
sample always starts on the exact frame of its bar rather than on an audio
block boundary. Takes are exactly `bars x 4 beats` long at the current tempo,
which is why the tempo is locked while a take runs.

Every voice gets a 3 ms fade at each end, and anything cut short — `Stop`, a
new take, or the 97th simultaneous voice — fades out over 10 ms instead of
stopping dead, so loop boundaries and stops do not click.

### Hearing the input

`Shift`+`Metronome` cycles monitoring: **off**, **auto** (only while a take
runs, which is when you need to hear yourself), **on**. It ships **off**,
because on speakers rather than headphones it feeds back; `--monitor auto`
starts there instead. The eight buttons above the display are an input meter,
and a clipped input says `CLIP` and turns the `Record` button bright red.

Only the audio callback writes transport state. The UI thread allocates up
front, publishes what it is asking for, and posts a command the callback
applies at the top of the next block — it never takes a lock, so a slow UI pass
cannot turn into a dropout. When PortAudio does report one, the display says
so rather than letting it pass silently.

If your interface has noticeable input latency, `--rec-latency-ms 12` trims
that much from the front of each take (it records a little extra and slides the
window), so recorded audio lines up with the grid instead of arriving late.

## Project format

A project is a directory, written whenever something changes and on exit:

```
my-song/
  project.json        tempo, and per slot: length in bars, trigger bars, how
                      hard each was played, mute, gain, the non-destructive
                      edits, and the tempo/rate the take was recorded at
  bounces/*.wav       whatever you have bounced
  samples/slot_00.wav one file per filled slot
```

WAVs are float32 when `soundfile` is installed, otherwise 16-bit PCM via the
standard library. Projects are reloaded at startup, resampling if the file rate
differs from the session rate.

## Terminal simulator

`--sim` runs the complete program — modes, transport, recorder — against a fake
control surface, printing the pad grid as letters after every command. Useful
for trying the workflow, and for demos without hardware. `hold` and `rel` take
a pad index or a button name, so gestures that need something held down (painting
a range of bars, `Tap Tempo` + the tempo encoder) work here too:

```
$ python -m push2sampler --sim --bpm 240 my-song
p 0            # press pad 0: slot 1 is blank, so this opens Record mode
p 1            # two bars
b record       # four-beat count-in, then a two-bar take
wait 3
p 0            # the take landed; play it on bar 1
p 9            # ...and bar 10
b session      # back to the library
```

`p N` presses a pad (or `p col,row`), `b NAME` presses a button (or just
`NAME`, including `b1`..`b8` for the row under the display), `shift on/off`,
`t ±N` turns the tempo encoder, `k ±N` the first track encoder or `k 3 ±N` the
third, `wait S` lets the transport run, `q` quits.

## Hardware notes

* The program prefers the **Push 2 User port** for output, so it coexists with
  anything on the Live port, and it **listens on every Push port** for input.
  That is not belt-and-braces: a Push 2 routes its surface to whichever port
  matches the mode it is in, and on a device in Live mode the User port carries
  no input at all (observed -- `F-08` finding 5). Listening to both costs
  nothing, since only one of them sends, and it means the program works without
  being told which mode the device is in. `--midi-port live|user` pins it.
* It never sends a mode change, so no button has to be pressed on the Push
  first. If the pads don't respond, see
  [troubleshooting](docs/troubleshooting.md#pads-and-buttons-do-nothing-but-the-lights-work-or-vice-versa).
* It can **follow or send MIDI clock** (`--clock midi_slave|midi_master`,
  `--clock-port NAME`) on a port of its own, separate from the surface.
  Following never moves the playhead -- only the tempo is nudged, and phase is
  compared at tick arrival where the sender's position is exact. Measured
  against a synthetic sender: 0.3 ms over 32 bars. Never measured against real
  gear. Ableton Link is a lazy-import seam that reports itself unavailable.
* Pad colours are addressed by palette index, and the factory palette is not
  stable across firmware, so the program uploads its own palette entries (64+)
  over SysEx at startup.
* The colour display is optional: with `pyusb` and `Pillow` installed it shows
  the current mode, tempo and bar; without them (or with `--no-display`)
  everything else works unchanged.

If the pads stay dark, `--led-test` finds out which layer is at fault -- does
the Push answer us at all, do the pads light from a factory palette index, do
they light from the private block we upload, do the buttons light, is it the
channel. It writes `led-report.json`. Worth running before `--selftest`, whose
questions all assume the LEDs already work.

If `--led-test` reports nothing in either direction, `--midi-probe` stops
asking and starts measuring: which mido backend is loaded, whether `pyusb` can
see the Push on the bus independently of MIDI, input read by both callback and
polling (a callback-only failure is a bug in `push2.py`, and it says so), and
both ports in both directions. Writes `midi-report.json`.

### Confirmed against real hardware

| what | source | confirmed on a device |
| --- | --- | --- |
| pad notes 36-99, bottom-left first | spec | not yet |
| button control changes | spec | not yet |
| palette SysEx (set entry + reapply) | spec | not yet |
| encoder relative values | spec | not yet |
| touch strip as pitchwheel | spec | not yet |
| display frame header and BGR565 packing | spec, unit-tested byte for byte | not yet |
| User/Live port naming | spec | **yes** -- `Ableton Push 2 Live Port` and `Ableton Push 2 User Port`, both directions |
| Which port carries the surface | assumed User | **no** -- on a device in Live mode, input arrives only on the *Live* port |

`--selftest` fills this in. Until then, treat every row as a guess that the
program is built to be corrected on.

## Tests

```
python -m pytest tests -q
```

565 tests cover the grid/MIDI mapping, the transport and mixer (bar-accurate
triggering, overlap, looping, declicking envelopes, latency compensation, exact
take lengths, command deferral, metering, monitoring, dropout reporting, stream
restarts, quantised live triggering, velocity), the non-destructive edits
(including an octave shift proved against an FFT), undo/redo, off-grid detection
and repair, settings precedence and persistence, command-line resolution, offline
bouncing and stems, the display's frame format byte for byte, the hardware probe
driven by a script instead of a person, project save/load, and the full
pad-by-pad workflow through the simulated surface, the block-arranging gestures
(paint, phrase fill, block and slot duplication), tempo tapping, the mixer
(gain, mute, solo, master gain, meter decay), overdub layers (summing, removal,
persistence), post-take processing, latency calibration against a synthetic
delayed loopback, surviving a surface that stops answering, and the scripted
simulator driving a whole record-arrange-play flow non-interactively, and this
release's widening: bank and page windowing, loop ranges, the song heat map and
its zoom, scenes, click routing and pre-roll, the project browser's metadata-only
scan, and every older project format still loading. No hardware, PortAudio or MIDI stack is needed — only `numpy`.

## Roadmap

`plans.md` is the product plan: 58 items across foundations, new features,
nice-to-haves, innovative bets and creature comforts, with the conventions
(button allocation registry, file-contention map, definition of done) that let
several people work on it at once. **42 are shipped, completing the v1.1, v1.2
and v1.3 trains**; each carries a status note saying what was built and where it
deviated from the plan. [`CHANGELOG.md`](CHANGELOG.md) is the release record.

`v1.4 — Plays with others` is next: MIDI clock and Link, importing audio from
disk, per-sample playback behaviour, swing, and the hardware pass.
