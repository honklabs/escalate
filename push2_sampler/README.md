# push2sampler

A Python program that turns an **Ableton Push 2** into a standalone sample
library and 64-bar looper. No Ableton Live involved: the program talks to the
Push 2 directly over its User MIDI port, and does its own recording, mixing and
bar-accurate playback.

```
pip install -r requirements.txt
python -m push2sampler my-song           # with a Push 2 plugged in
python -m push2sampler --sim my-song     # no hardware: terminal simulator
```

## When you first plug the Push 2 in

Run the hardware probe before anything else:

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

All 64 pads are sample slots.

| Pad | Meaning |
| --- | --- |
| **white** | blank slot |
| **green** | filled slot |
| dim green | filled, but muted (you won't hear it) |
| amber | that sample is sounding right now |
| yellow | filled, but the take no longer fits its bars — see below |

* Press a **blank** pad → **Record mode** for that slot.
* **Tap** a **filled** pad → that sample's own **Sample page**.
* **Hold** a filled pad (about half a second) → audition it instead, without
  leaving the library. The pad turns amber while it plays. `Shift` + a filled
  pad does the same thing immediately.

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

The 64 pads are now the **64 bars of the song**. Press a pad to enable or
disable this sample on that bar:

| Pad | Meaning |
| --- | --- |
| green | this sample plays here |
| two dimmer greens | plays here, but softer -- see velocity below |
| dim blue | some *other* sample plays here |
| faint white | an empty bar that starts a 4-bar phrase |
| brighter white | an empty bar that starts a 16-bar section |
| white | the playhead, while the song is playing |
| amber | the playhead, on a bar where this sample plays |

The two faint tints are a ruler: they fall on columns 1 and 5 of every row, with
the brighter mark every other row, so you can count phrases without counting
pads.

Samples may overlap freely — a 4-bar sample triggered on bars 0 and 2 will
simply play over itself, and other samples layer on top.

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

### 5. Bouncing

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
| `Shift`+`Play` | open/close perform mode and start the loop |
| `Shift`+`Record` | Library: bounce the song to a file |
| `Accent` | Sample page: velocity response on/off |
| `Fixed Length` | Perform: quantize amount |
| `Play` | start or stop the song from bar 1 |
| `Stop` | stop; in Record mode cancel the take, then back out to the library |
| `Record` | Library: record into the first free slot · Record mode: go · Sample page: re-record |
| `Session`, `Note`, `◀` | back to the Sample Library |
| `Mute` | Sample page: hear / don't hear this sample |
| `Delete` | arm delete (then press a pad) · `Shift`+`Delete` on a sample page deletes it |
| `Undo` | take back the last edit · `Shift`+`Undo` redoes it |
| `Metronome` | click on/off · `Shift`+`Metronome` cycles input monitoring |
| button 1 below the display | Sample page: fit an off-grid take to its bars |
| the 8 buttons above the display | input level meter |
| `Repeat` | loop the 64-bar song on/off |
| `▲` / `▼` | Sample page: jump to the previous / next filled slot |
| Tempo encoder | BPM (hold `Shift` for ±10) |
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
                      hard each was played, mute, gain, and the tempo/rate the
                      take was recorded at
  bounces/*.wav       whatever you have bounced
  samples/slot_00.wav one file per filled slot
```

WAVs are float32 when `soundfile` is installed, otherwise 16-bit PCM via the
standard library. Projects are reloaded at startup, resampling if the file rate
differs from the session rate.

## Terminal simulator

`--sim` runs the complete program — modes, transport, recorder — against a fake
control surface, printing the pad grid as letters after every command. Useful
for trying the workflow, and for demos without hardware:

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

* The program uses the **Push 2 User port**, so it coexists with anything on
  the Live port. Press the Push's `User` button if the pads don't respond.
* Pad colours are addressed by palette index, and the factory palette is not
  stable across firmware, so the program uploads its own palette entries (64+)
  over SysEx at startup.
* The colour display is optional: with `pyusb` and `Pillow` installed it shows
  the current mode, tempo and bar; without them (or with `--no-display`)
  everything else works unchanged.

### Confirmed against real hardware

| what | source | confirmed on a device |
| --- | --- | --- |
| pad notes 36-99, bottom-left first | spec | not yet |
| button control changes | spec | not yet |
| palette SysEx (set entry + reapply) | spec | not yet |
| encoder relative values | spec | not yet |
| touch strip as pitchwheel | spec | not yet |
| display frame header and BGR565 packing | spec, unit-tested byte for byte | not yet |
| User/Live port naming | spec | not yet |

`--selftest` fills this in. Until then, treat every row as a guess that the
program is built to be corrected on.

## Tests

```
python -m pytest tests -q
```

257 tests cover the grid/MIDI mapping, the transport and mixer (bar-accurate
triggering, overlap, looping, declicking envelopes, latency compensation, exact
take lengths, command deferral, metering, monitoring, dropout reporting, stream
restarts, quantised live triggering, velocity), undo/redo, off-grid detection and
repair, settings precedence and persistence, command-line resolution, offline
bouncing and stems, the display's frame format byte for byte, the hardware probe
driven by a script instead of a person, project save/load, and the full
pad-by-pad workflow through the simulated surface. No hardware, PortAudio or MIDI stack is needed — only `numpy`.

## Roadmap

`plans.md` is the product plan: 58 items across foundations, new features,
nice-to-haves, innovative bets and creature comforts, with the conventions
(button allocation registry, file-contention map, definition of done) that let
several people work on it at once.
