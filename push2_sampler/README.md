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

## The workflow

### 1. Sample Library

All 64 pads are sample slots.

| Pad | Meaning |
| --- | --- |
| **white** | blank slot |
| **green** | filled slot |
| dim green | filled, but muted (you won't hear it) |
| amber | that sample is sounding right now |

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

Then **Session** (or the left arrow) takes you back to the library, where you
repeat the whole process with the next sample.

### Undo

`Undo` takes back the last 64 edits and `Shift`+`Undo` puts them back: a
deleted take returns with its audio and its arrangement, a cleared arrangement
returns with its bars, a tempo nudge returns to the old tempo. A sweep of an
encoder is one undo step, not forty. The journal is in memory only — it is a
safety net for your hands, not project history.

## Key map

| Control | Action |
| --- | --- |
| 8x8 pads | slot / take length / song bar, depending on the mode |
| hold a pad | Library: audition the sample instead of opening its page |
| `Play` | start or stop the song from bar 1 |
| `Stop` | stop; in Record mode cancel the take, then back out to the library |
| `Record` | Library: record into the first free slot · Record mode: go · Sample page: re-record |
| `Session`, `Note`, `◀` | back to the Sample Library |
| `Mute` | Sample page: hear / don't hear this sample |
| `Delete` | arm delete (then press a pad) · `Shift`+`Delete` on a sample page deletes it |
| `Undo` | take back the last edit · `Shift`+`Undo` redoes it |
| `Metronome` | click on/off |
| `Repeat` | loop the 64-bar song on/off |
| `▲` / `▼` | Sample page: jump to the previous / next filled slot |
| Tempo encoder | BPM (hold `Shift` for ±10) |
| Track encoder 1 | Record mode: take length · Sample page: gain |
| `Shift`+`Setup` | save the project now (it also autosaves) |

## Timing and recording

The engine runs one duplex audio stream and keeps the transport position in
frames. A block is split at every beat, bar, loop point and end-of-take, so a
sample always starts on the exact frame of its bar rather than on an audio
block boundary. Takes are exactly `bars x 4 beats` long at the current tempo,
which is why the tempo is locked while a take runs.

Every voice gets a 3 ms fade at each end, and anything cut short — `Stop`, a
new take, or the 97th simultaneous voice — fades out over 10 ms instead of
stopping dead, so loop boundaries and stops do not click.

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
  project.json        tempo, and per slot: length in bars, trigger bars, mute, gain
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

`p N` presses a pad (or `p col,row`), `b NAME` presses a button, `shift on/off`,
`t ±N` turns the tempo encoder, `k ±N` the first track encoder, `wait S` lets
the transport run, `q` quits.

## Hardware notes

* The program uses the **Push 2 User port**, so it coexists with anything on
  the Live port. Press the Push's `User` button if the pads don't respond.
* Pad colours are addressed by palette index, and the factory palette is not
  stable across firmware, so the program uploads its own palette entries (64+)
  over SysEx at startup.
* The colour display is optional: with `pyusb` and `Pillow` installed it shows
  the current mode, tempo and bar; without them (or with `--no-display`)
  everything else works unchanged.

## Tests

```
python -m pytest tests -q
```

118 tests cover the grid/MIDI mapping, the transport and mixer (bar-accurate
triggering, overlap, looping, declicking envelopes, latency compensation, exact
take lengths, command deferral, dropout reporting), undo/redo, project
save/load, and the full pad-by-pad workflow through the simulated surface. No hardware, PortAudio or MIDI stack is needed — only `numpy`.

## Roadmap

`plans.md` is the product plan: 58 items across foundations, new features,
nice-to-haves, innovative bets and creature comforts, with the conventions
(button allocation registry, file-contention map, definition of done) that let
several people work on it at once.
