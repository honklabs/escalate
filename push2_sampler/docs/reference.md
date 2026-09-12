# Reference

Every mode, control, colour, setting and file. For a guided path through the
same material, read [Getting started](getting-started.md) instead.

- [Concepts](#concepts)
- [Controls that work everywhere](#controls-that-work-everywhere)
- [Modes](#modes) — [Library](#sample-library) · [Record](#record-mode) ·
  [Sample page](#sample-page) · [Editor](#sample-editor) ·
  [Perform](#perform-mode) · [Settings](#settings-page)
- [Colours](#colours)
- [Settings](#settings)
- [Undo](#undo)
- [Timing and recording](#timing-and-recording)
- [Files](#files)
- [Command line](#command-line)
- [Not built yet](#not-built-yet)

---

## Concepts

**Slot.** One of 64 sample slots, one per pad. A slot holds one recorded take.

**Take.** The audio in a slot. Recorded as an exact number of bars at the tempo
of the moment, and it remembers that tempo.

**Song.** 64 bars. Every sample has its own set of bars it plays on; they
overlap freely, including with themselves.

**Trigger.** One sample playing on one bar. Optionally carries a velocity.

**Edits.** Trim, fades, pitch, reverse and normalise, stored beside a take and
applied on the way to the speakers. The recording is never changed until you
explicitly apply them.

**Mode.** What the 64 pads currently mean. The Library is home; the Sample page
replaces it; the Editor, Perform and Settings open *over* whatever you were
doing and close back to it.

---

## Controls that work everywhere

These work in every mode unless that mode says otherwise.

| Control | Action |
| --- | --- |
| **Play** | Start the song from bar 1, or stop it |
| **Shift**+**Play** | Open or close [Perform mode](#perform-mode), starting the loop |
| **Stop** | Stop now |
| **Shift**+**Stop** | [Stop at the end of the bar](#stopping) |
| **Stop** twice quickly | Stop, and disarm everything that was armed |
| **Session**, **Note**, **◀** | Close an overlay, or go home to the Library |
| **Setup** | Open or close the [Settings page](#settings-page) |
| **Shift**+**Setup** | Save the project now |
| **Metronome** | Click on/off |
| **Shift**+**Metronome** | Cycle monitoring: off → auto → on |
| **Repeat** | Loop the 64-bar song on/off |
| **Undo** | Take back the last edit (64 deep) |
| **Shift**+**Undo** | Redo |
| **Delete** | Arm deleting; the next pad press acts (mode-dependent) |
| **Tap Tempo** | [Tap a tempo](#tapping-a-tempo): four taps set it |
| **Shift**+**Tap Tempo** | Throw away the taps so far |
| Tempo encoder | BPM ±1 per click, ±10 with **Shift**, ±0.1 holding **Tap Tempo** |
| The 8 buttons **above** the display | Input level meter (not pressable controls) |

The **Record** and **Duplicate** buttons mean different things in different
modes, and are listed with each.

---

## Modes

### Sample Library

Home. All 64 pads are sample slots.

**Pads**

| Press | Result |
| --- | --- |
| A blank pad | Opens [Record mode](#record-mode) for that slot |
| Tap a filled pad | Opens that sample's [page](#sample-page) |
| Hold a filled pad (~0.4 s) | Auditions it, and stays in the library |
| **Shift** + a filled pad | Auditions it immediately |
| **Delete** armed, then a pad | Deletes that slot |
| **Mute** armed, then a pad | Mutes/unmutes that slot |
| **Duplicate** armed, then a pad | Copies that slot to the next empty one |
| **Duplicate** armed, then **Shift** + a pad | Moves it instead of copying |

**Buttons**

| Control | Action |
| --- | --- |
| **Record** | Record into the first free slot |
| **Shift**+**Record** | [Bounce](#bouncing) the song to a file |
| **Mute** | Arm mute; the next pad press toggles that slot's audibility |
| **Duplicate** | Arm duplicate; press again to cancel |

The display lists how many slots are filled and how many are muted, and names
any slots that have fallen [off the grid](#off-grid-takes).

A duplicated slot carries the original's arrangement, velocities, mute state,
gain and edits. It **shares the original's audio** rather than copying it, so
duplicating a long take costs nothing; the two become independent the moment
either one's edits are applied, because an edit builds a new array rather than
writing into the old one. "Next empty slot" means the next one in reading order,
wrapping round the grid.

### Record mode

Reached from a blank pad in the library, or **Record** on a sample page to
re-record it.

The pads show the **length of the take in bars**: white = included, off = not.
The selection always begins at the top-left pad and runs in reading order, so the
pad you press is the last bar included — top-left is 1 bar, the end of the first
row is 8, the bottom-right pad is 64.

| Control | Action |
| --- | --- |
| Any pad | Set the length (locked once recording starts) |
| Track encoder 1 | Adjust the length by one bar per click |
| **Record** | Start: count-in, then record. Again during a take: cancel |
| **Stop** | Cancel a running take; pressed when idle, back out to the library |
| **Session**, **Note**, **◀** | Back out (cancelling any running take) |
| **Play** | Starts the song when idle; ignored during a take |

**What happens when you press Record.** Four clicks of count-in (configurable),
then recording begins exactly on the downbeat and runs for precisely the number
of bars selected. The rest of the song plays along throughout, so you can record
in time with it. When the last bar ends it stops by itself, stores the take, and
opens that sample's page.

While it runs, the pads show progress: bars already captured in dim red, the bar
being captured in bright red, the rest still white. During the count-in the
selection flashes red on each beat.

### Sample page

One sample, and where it plays. **The 64 pads are the 64 bars of the song** — pad
1 is bar 1, the pad below it is bar 9, the bottom-right pad is bar 64.

| Control | Action |
| --- | --- |
| Any pad | Toggle whether this sample plays on that bar |
| Hold a pad, press another | [Paint](#painting-a-range) every bar between them |
| Double-tap a pad | [Fill or clear the 4-bar phrase](#filling-a-phrase) from there |
| **Delete** armed, then any pad | Clear every bar for this sample |
| **Duplicate**, then two pads | [Duplicate a block of bars](#duplicating-a-block) |
| **Record** | Re-record this slot, keeping its arrangement, mute and gain |
| **Mute** | Whether you hear this sample at all |
| **Accent** | Velocity response on/off for this sample |
| **Device** | Open the [editor](#sample-editor) |
| **Shift**+**Delete** | Delete this sample and return to the library |
| **▲** / **▼** | Jump to the previous / next filled slot |
| Track encoder 1 | This sample's gain (0–2) |
| First button **below** the display | [Fit an off-grid take](#off-grid-takes) to its bars |

#### Painting a range

Hold one pad and press another: every bar between them, inclusive, is set to
whatever state the **held** pad's own press produced. So holding an empty bar
paints the range on, and holding a bar that was playing paints it off. Direction
does not matter.

The paint is one undo step. The held pad's own toggle is a separate step before
it, so taking a painted range back is two presses of **Undo**: one for the range,
one for the bar you started from.

#### Filling a phrase

Double-tap a pad (two presses within 0.35 s) to deal with four bars at once —
"just play it for the next four bars" as one gesture.

- Double-tap an **empty** bar: the sample is laid out across the next four bars,
  spaced by its own length. A 1-bar take fills bars N, N+1, N+2, N+3; a 2-bar
  take fills N and N+2; a 4-bar take already covers the phrase, so nothing is
  added and the display says so.
- Double-tap a bar that **was playing**: the sample is cleared from all four.

Clipped at bar 64, never wrapped. Like painting, the fill is its own undo step
on top of the first tap's toggle.

#### Duplicating a block

Press **Duplicate**, then the **first bar of the block**, then **where it should
go**. The distance between the two presses is the block's length, which is why no
separate length control is needed: bar 1 then bar 5 duplicates bars 1–4 onto
5–8.

Velocities come with it. Destination bars the source does not play on are
**cleared**, so the copy is what lands there rather than a merge. The block is
clipped at bar 64, not wrapped. **Shift** on the second press moves the block
instead of copying it. The whole thing is one undo step.

Pressing an earlier bar second is refused with a reason rather than guessed at,
and pressing **Duplicate** again cancels.

### Sample editor

**Device** from a sample page. Non-destructive: the recording is untouched until
you apply.

**Pads** are the take — 64 slices, each lit by how loud that slice is, with the
parts being trimmed away in dim red. **Pressing a pad auditions from that point.**

Each of the eight encoders above the display owns one parameter. The button
*below* each one resets that parameter to its default, or toggles it where it is
a switch.

| Encoder | Parameter | Range | Step |
| --- | --- | --- | --- |
| 1 | trim in | 0–10000 ms | 5 ms |
| 2 | trim out | 0–10000 ms | 5 ms |
| 3 | fade in | 0–2000 ms | 2 ms |
| 4 | fade out | 0–2000 ms | 2 ms |
| 5 | pitch | −12 to +12 semitones | 1 |
| 6 | gain | 0–2 | 0.05 |
| 7 | reverse | on/off | — |
| 8 | normalise | on/off | — |

| Control | Action |
| --- | --- |
| **Device** | Close the editor |
| **Shift**+**Device** | Apply the edits to the recording for good (undoable) |
| **Session**, **Note**, **◀** | Close |

Edits are applied in a fixed order: **trim → reverse → pitch → fades →
normalise**. Fades come after pitch so their length is what you asked for in the
result; normalise comes last so it sees the finished audio. Normalise targets
−1 dBFS. Pitch is resampling, so it changes the length: +12 semitones plays
twice as fast and is half as long.

Trimming makes a take shorter than its bars, so it will show as
[off grid](#off-grid-takes). That is correct, not a fault.

### Perform mode

**Shift**+**Play**. The loop starts and the pads fire samples instead of
navigating.

| Control | Action |
| --- | --- |
| A filled pad | Fire that sample, quantised to the next grid line |
| **Record** | Toggle *writing*: fired pads are also written into the arrangement |
| **Fixed Length** | Cycle quantize: 1 bar → off → 1/4 bar → 1/2 bar → 1 bar |
| **Delete** | Arm erasing: bars are wiped as the playhead crosses them |
| **Session**, **Note**, **◀** | Leave |
| **Shift**+**Play** | Also leaves |

Quantize defaults to **1 bar**. With quantize off, a pad sounds immediately. A
pad pressed while the transport is stopped always sounds immediately.

With **Record** on, a fired pad is written at the bar where it *sounded*, not
where you pressed — so a late hit still lands on the bar. Firing a pad on a bar
that already plays that sample changes nothing and says so.

Erasing starts at the **next** bar line rather than the bar already playing: the
current bar is mostly behind you, and wiping it would feel like erasing the past.
Erasing removes that bar for **every** sample, as one undo step.

If the sample has velocity response on ([Accent](#sample-page)), how hard you hit
the pad sets the level, and a written trigger keeps that velocity.

### Settings page

**Setup**. The pads stay dark on purpose — nothing on this page edits your song.

Each of the eight buttons *below* the display owns one setting. The encoder above
it adjusts the value; pressing the button cycles it. Changes take effect at once
and are written to the settings file when the page closes.

| | | |
| --- | --- | --- |
| count-in beats | monitoring | monitor gain |
| record latency | play while recording | autosave delay |
| input device | audio block size | |

**Setup**, **Session**, **Note**, **◀** or **Stop** closes it.

Choosing a device that will not open is not fatal: the previous device is kept
and the display says what went wrong.

---

## Colours

### In the library

| Colour | Meaning |
| --- | --- |
| White | Empty slot |
| Green | Filled |
| Dim green | Filled but muted |
| Amber | Sounding right now |
| Dim amber | Comes in on the **next** bar |
| Yellow | Filled, but [off grid](#off-grid-takes) |
| Flashing red | **Delete** is armed |
| Yellow (all filled slots) | **Mute** is armed |
| Flashing blue (all filled slots) | **Duplicate** is armed |
| Amber bar filling the grid | A [bounce](#bouncing) is rendering |

The dim amber is a one-bar look-ahead, so you can see what is about to enter
while the song plays. It only appears while the transport is running, never for a
muted sample, and not on the last bar unless the loop is on.

### On a sample page

| Colour | Meaning |
| --- | --- |
| Green | This sample plays on this bar |
| Green, in three brightnesses | …and velocity response is on, showing how hard it was played |
| Dim green | Plays here, but the sample is muted |
| Dim blue | Some *other* sample plays here |
| Faint white | Empty bar that starts a 4-bar phrase |
| Brighter white | Empty bar that starts a 16-bar section |
| White | The playhead |
| Amber | The playhead, on a bar where this sample plays |
| Flashing blue | The first bar of a block being [duplicated](#duplicating-a-block) |

### In Record mode

White = bar included in the take. Dim red = already captured. Bright red = being
captured now, or flashing during the count-in.

### In the editor

Green in three brightnesses = how loud that slice of the take is. Dim red = being
trimmed away. Off = silence.

### In perform mode

Green = a sample you can fire. Dim green = muted. Amber = sounding. Dim white =
an empty slot, nothing to fire.

---

## Settings

Three sources, each overriding the last: built-in defaults, then
`~/.config/push2sampler/settings.json`, then the command line. **Command-line
values steer one run and are not written back.** `--settings PATH` uses a
different file; `--no-settings` ignores the file entirely.

A malformed settings file is ignored with a warning rather than crashing, and a
value out of range is quietly repaired. A command-line value that cannot be used
is reported, so a flag can never silently do nothing.

| Setting | Default | Range | On the device? |
| --- | --- | --- | --- |
| `count_in_beats` | 4 | 0–16 | yes |
| `monitor` | `off` | off / auto / on | yes |
| `monitor_gain` | 1.0 | 0–2 | yes |
| `rec_latency_ms` | 0 | 0–250 | yes |
| `play_while_recording` | on | on/off | yes |
| `autosave_delay_s` | 2.0 | 0.5–30 | yes |
| `input_device` | system default | device index | yes |
| `blocksize` | 256 | 64–2048, powers of two | yes |
| `output_device` | system default | device index | command line only |
| `samplerate` | 48000 | 8000–192000 | command line only |
| `in_channels` | 1 | 1–8 | command line only |
| `out_channels` | 2 | 1–8 | command line only |

Sample rate and channel counts are command-line only because changing them means
resampling every take already loaded. Device and block size changes reopen the
audio stream in place.

---

## Undo

64 edits deep, in memory only — a safety net for your hands, not project history,
and not written to disk.

Everything destructive is covered: bar toggles, painted ranges, filled phrases,
duplicated blocks and slots, clearing an arrangement, erasing bars while looping,
mute, gain, tempo (tapped, nudged or turned), velocity response, each editor
parameter, applying edits, fitting an off-grid take, recording a take, and
deleting one. An undone delete restores the take itself — audio, arrangement,
mute state and gain. An undone slot move puts the sample back where it was.

A gesture that writes many bars is **one** step, however many bars it touched.

Edits that arrive in a stream coalesce: one sweep of an encoder is **one** undo
step, not forty. A new edit clears the redo stack.

---

## Timing and recording

The engine runs one duplex audio stream and keeps the transport position in
frames. Each audio block is split at every beat, bar, loop point, end-of-take and
pending trigger, so a sample starts on the **exact frame** of its bar rather than
on an audio block boundary.

Takes are exactly `bars × 4 beats` long at the current tempo, which is why the
tempo is locked while a take runs.

Every voice gets a 3 ms fade at each end, and anything cut short — Stop, a new
take, the 97th simultaneous voice — fades over 10 ms instead of stopping dead, so
boundaries and stops do not click. 96 voices sound at once; beyond that the
oldest is faded out rather than truncated.

Only the audio callback writes transport state. The UI thread allocates up front,
publishes what it is asking for, and posts a command the callback applies at the
top of the next block — it never takes a lock, so a slow UI pass cannot become a
dropout. When the audio system does report a dropout, the display says so.

### Stopping

**Stop** stops immediately and rewinds to bar 1. Voices that were sounding fade
over 10 ms rather than being cut, so a stop never clicks.

**Shift**+**Stop** stops at the **next bar line** instead, so a loop finishes its
bar rather than ending mid-phrase. While it waits, the transport keeps running,
the display reads `ENDING`, and the **Stop** button is lit bright. The bar the
stop lands on never starts: nothing new is scheduled onto it. Pressing **Play**
cancels a pending stop, and a take is never deferred — **Stop** during a recording
cancels it at once, Shift or no Shift.

A **second Stop within half a second** is the panic gesture: it stops and
disarms whatever was armed (delete, mute, duplicate), so there is always a way
back to a surface that will not surprise you. The display says `all clear` when
it actually disarmed something.

### Tapping a tempo

**Tap Tempo** four times sets the tempo from how far apart the taps were. Three
intervals means one tap can be wrong: the median interval decides what "about
right" is, and any interval more than 35% away from it is thrown away before the
rest are averaged.

- Fewer than four taps so far: the display counts them (`tap 2/4`).
- A gap of more than 2.5 seconds starts a new series.
- **Shift**+**Tap Tempo** throws the series away.
- Tapping during a take is refused with a reason — the tempo is locked while
  recording, and collecting taps that will be discarded would be worse.
- The result is clamped to 40–240 BPM like any other tempo change, and it is one
  undo step.

**Holding Tap Tempo** turns the tempo encoder into a **±0.1 BPM** nudge for
beat-matching against something else. Doing that also discards the tap series, so
the press that is holding the button is not mistaken for a tap. The transport
readout grows a decimal when the tempo is not a whole number, so a nudge is
visible: `121.3 BPM`.

### Input latency

If takes land consistently late, set `record latency` to roughly your interface's
input latency in milliseconds. The program records a little extra and slides the
window, so the audio lines up with the grid. There is no automatic measurement
yet.

### Off-grid takes

A take records the tempo and sample rate it was captured at. If its audio no
longer fills its declared bars at the current tempo — because the tempo changed,
or because it was trimmed — the slot turns **yellow** and its page explains:

```
OFF GRID: 1.83 bars at 220 BPM (recorded at 240) - button 1 below to fit
```

The audio is left alone. The first button below the display pads or trims it to
fit exactly, which is undoable. Pitch-preserving stretching is not built.

The tolerance is 1%, so rounding does not trip it.

---

## Files

### A project

```
my-song/
  project.json          tempo, and per slot: length in bars, the bars it plays
                        on, how hard each was played, mute, gain, the edits,
                        and the tempo/rate the take was recorded at
  samples/slot_00.wav   one file per filled slot, named by slot number
  bounces/*.wav         whatever you have bounced
```

Saved a couple of seconds after any change (see `autosave_delay_s`) and on exit.
`project.json` is written atomically — a crash mid-save cannot corrupt it. Audio
files are only rewritten when the audio itself changed.

The format version is 4, and older versions load: a version-1 take assumes it was
recorded at the project's tempo, and versions 2 and 3 simply lack velocities and
edits respectively.

WAVs are float32 when `soundfile` is installed, 16-bit PCM otherwise. A project
whose files are at a different sample rate than the session is resampled on load.

### Bouncing

**Shift**+**Record** in the library renders the song to
`<project>/bounces/<timestamp>.wav`. The render happens a chunk at a time inside
the event loop, so the surface stays responsive and you can keep playing; the grid
shows progress as one amber bar.

Both the on-device bounce and `--bounce` keep the tails of samples that overrun
the last bar (up to 20 seconds). Muted samples are left out of the mix but are
still exported as stems. Stems sum back to the mix exactly.

### Settings

`~/.config/push2sampler/settings.json`, honouring `XDG_CONFIG_HOME`.

---

## Command line

```
python -m push2sampler [project] [options]
```

`project` is a directory, created if missing; the default is `./song`.

| Flag | Effect |
| --- | --- |
| `--bpm N` | Tempo for this run |
| `--settings PATH` | Use a different settings file |
| `--no-settings` | Ignore the settings file |
| `--samplerate N` | 8000–192000, default 48000 |
| `--blocksize N` | 64–2048 |
| `--in-channels N`, `--out-channels N` | Channel counts |
| `--input-device N`, `--output-device N` | Audio device indices (see `--list-devices`) |
| `--rec-latency-ms N` | Trim this much from the front of each take |
| `--monitor off\|auto\|on` | Hear the input. Default off: on speakers it feeds back |
| `--monitor-gain N` | Level the monitored input is mixed at |
| `--count-in N` | Count-in beats, default 4 |
| `--no-play-while-recording` | Do not play the song during a take |
| `--no-display` | Skip the Push's colour screen |
| `--no-save` | Never write to the project directory |
| `--sim` | Run the [simulator](simulator.md) instead of hardware |
| `--bounce OUT.WAV` | Render the song and exit; needs no hardware |
| `--stems DIR` | Render one WAV per slot and exit |
| `--selftest` | Walk the hardware and write a report |
| `--report PATH` | Where `--selftest` writes (default `./hardware-report.json`) |
| `--list-ports` | List MIDI ports and exit |
| `--list-devices` | List audio devices and exit |

---

## Not built yet

So you do not go looking:

- **No time-stretch.** A take from another tempo is detected and can be padded or
  trimmed, not stretched with its pitch preserved.
- **No sync.** No MIDI clock in or out, no Ableton Link. The program is an island.
  Tempo tapping and the fine nudge are the manual substitutes.
- **No importing** audio from disk; you can only record into it.
- **64 slots and 64 bars**, one bank, one page.
- **No mixer page**; gain is per sample, on its own page.
- **No swing**, no per-trigger probability, no choke groups or loop/gate modes —
  every sample is a one-shot that plays to its end.
- **No scenes or snapshots** of an arrangement; duplicating a block of bars is as
  close as it gets.
- **Aftertouch** is received and ignored; velocity is used.
- **The colour display** shows text only: mode, transport, levels and messages.
  No waveform drawing, no graphics.

`plans.md` in the project root tracks all of it, with 37 of 58 planned items
still open.
