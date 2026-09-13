# Reference

Every mode, control, colour, setting and file. For a guided path through the
same material, read [Getting started](getting-started.md) instead.

- [Concepts](#concepts)
- [Controls that work everywhere](#controls-that-work-everywhere)
- [Modes](#modes) — [Library](#sample-library) · [Record](#record-mode) ·
  [Sample page](#sample-page) · [Editor](#sample-editor) ·
  [Perform](#perform-mode) · [Mixer](#mixer-page) · [Settings](#settings-page)
- [Colours](#colours)
- [Settings](#settings)
- [Undo](#undo)
- [Resuming](#resuming)
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
| **Mix** | Open or close the [Mixer page](#mixer-page) |
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

The **Record**, **Duplicate** and **New** buttons mean different things in
different modes, and are listed with each.

Every button press briefly lights its own LED, for about 80 ms, whether or not
the mode you are in does anything with it. That is deliberate: it means a button
that appears dead really is unbound rather than broken.

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
| **New** | [Overdub](#overdubbing) another pass on top of this take |
| **Shift**+**New** | Remove the most recent overdubbed layer |
| **Mute** | Whether you hear this sample at all |
| **Accent** | Velocity response on/off for this sample |
| **Device** | Open the [editor](#sample-editor) |
| **Shift**+**Delete** | Delete this sample and return to the library |
| **▲** / **▼** | Jump to the previous / next filled slot |
| Track encoder 1 | This sample's gain (0–2) |
| First button **below** the display | [Fit an off-grid take](#off-grid-takes) to its bars |

#### Overdubbing

**New** records another pass *on top of* the take rather than replacing it. The
count-in runs, the song plays, the take itself plays wherever it is arranged, and
what you play is summed in. The page stays put throughout, so you watch the
arrangement rather than a recording screen.

The layer is exactly the take's own length in bars, so an overdub can never put a
slot off the grid.

Layers are kept **individually**, so **Shift**+**New** peels the last one off —
repeatedly, back to the original recording, which can never be removed. The
display counts them (`3 layers`). Both adding and removing are one undo step.

Two things follow from how this is stored:

- Layers survive saving and reloading (they are their own WAVs), so you can come
  back tomorrow and still take a pass off.
- **Applying edits, or fitting an off-grid take, forgets the breakdown.** Both
  replace the audio with something that is no longer the sum of the layers, so
  the take becomes a single layer again. The sound does not change.

An overdub on a take that plays nowhere yet is silent, and says so.

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

### Mixer page

**Mix**. Eight slots at a time — the current row of the library — as eight
vertical level meters. Row by row rather than all 64 at once, because there are
only eight encoders and a fader whose value you cannot see is worse than no
fader.

| Control | Action |
| --- | --- |
| Track encoders 1–8 | Gain of that strip's slot (0–2) |
| Buttons **below** the display | Mute/unmute that strip |
| **Solo** | Arm soloing; press it again to clear a solo |
| **Solo**, then a button below | Solo that strip |
| Master encoder | Gain on the whole mix (0–2) |
| **▲** / **▼** | Another row of eight |
| Any pad | Select that pad's row |
| **Mix**, **Session**, **Note**, **◀** | Close |

**Solo does not disturb your mutes.** It is stored separately from each sample's
own mute state, so soloing and then un-soloing gives you back exactly the mix you
had — which is the entire point of a solo button. Solo overrides mute while it is
on, and it is not on the undo stack because there is nothing to restore; master
gain is.

Muting and soloing both change what is heard **and what gets bounced**. The
master gain is applied last, after everything is summed, and is saved with the
project.

| Meter colour | Meaning |
| --- | --- |
| Green | Level, filling upwards from the bottom row |
| Amber | The top quarter |
| Red | The very top: about to clip |
| Faint white | An empty segment of a strip that exists |
| Dim green | A muted strip's level |
| Off | No sample in that slot |

### Settings page

**Setup**. The pads stay dark on purpose — nothing on this page edits your song.

Each of the eight buttons *below* the display owns one setting. The encoder above
it adjusts the value; pressing the button cycles it. Changes take effect at once
and are written to the settings file when the page closes.

There are more settings than there are buttons, so the page **scrolls** with
**▲** / **▼** rather than leaving any of them unreachable. The display says which
page you are on.

Page 1:

| | | |
| --- | --- | --- |
| count-in beats | monitoring | monitor gain |
| record latency | play while recording | autosave delay |
| input device | audio block size | |

Page 2 — [post-take processing](#post-take-processing):

| | | |
| --- | --- | --- |
| auto trim | auto normalise | auto fade |

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
| `auto_trim` | off | on/off | yes |
| `auto_normalize` | off | on/off | yes |
| `auto_fade` | off | on/off | yes |
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
So is adding or removing an overdub layer, and so is a master gain sweep.

Soloing is **not** undoable, deliberately: it is a decision about what you are
listening to rather than an edit to the song, so there is nothing to restore.

---

## Resuming

Start with no project argument and you get the session you were last in: the same
project directory, the same page, the same selected slot, and the loop and
metronome as you left them. It is stored in the `ui` section of the settings
file, separately from the settings themselves, because it is a bookmark rather
than something anyone edits.

Naming a project on the command line always wins. A remembered directory that is
no longer there falls back to `./song` rather than creating an empty tree
somewhere you have forgotten about.

Only the library and a sample page are restored. Coming back up inside a record
arm, a bounce or the settings page would be hostile, and a slot that has been
deleted since simply lands you in the library.

---

## Saving

The project is written a couple of seconds after the last change (see
`autosave_delay_s`) and again on exit. While anything is unwritten the transport
line ends in `*`; when the autosave fires the display says `saved`.

If a save **fails** — a full disk, a read-only directory — the reason goes on the
display and the pending save is dropped rather than retried every frame. A
read-only disk does not heal in 30 ms, and one message beats a hundred.

**Shift**+**Setup** saves immediately.

---

## When the Push disappears

Unplug the cable mid-session and the program does not stop. The first failed
write marks the surface offline; the display says

```
SURFACE OFFLINE - check the cable; the audio is still running
```

and that is literally true — the transport keeps running, a take in progress
keeps recording, and the project is untouched. Every two seconds it tries to
reopen the port; when the Push comes back it re-uploads the palette and relights
the whole grid, and the display says `surface back`.

A cable moving must never cost a take.

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
window, so the audio lines up with the grid.

To measure it rather than guess:

```
python -m push2sampler --calibrate
```

Connect the output to the input, or point a microphone at the speaker. It plays
five clicks, times each one's return, takes the median so that one cough cannot
set your timing, and writes the result to `rec_latency_ms`. It refuses anything
over 250 ms — past that it has found a room reflection, not latency — and says
so rather than writing a wrong number. If the rounds disagree by more than 10 ms
it tells you to try again somewhere quieter.

Detection is by cross-correlation rather than by watching for a level: a click
that has been through a speaker and a microphone is smeared and coloured, and its
shape survives that far better than its amplitude.

### Post-take processing

Three settings, all **off** by default, applied to a take the moment it finishes.
A take should be what you played until you ask for something else.

| Setting | What it does |
| --- | --- |
| `auto_trim` | Finds where the take audibly begins and slides it onto the grid |
| `auto_normalize` | Scales the take so its loudest sample sits at −1 dBFS |
| `auto_fade` | 2 ms fade at both ends, so a looped take does not click |

Whatever they do, the display says so afterwards (`trimmed 30ms, normalised
x1.4`) — silently processing a recording would leave you wondering why it does
not sound like what you played.

**Auto-trim keeps the length.** It drops frames from the front and pads the same
number onto the end, so the take stays exactly its number of bars and cannot be
put [off the grid](#off-grid-takes) by being tidied up. It looks no more than
100 ms in: beyond that you have recorded a rest, and moving it would move the
music. The threshold is measured against the take's own first 10 ms, because
"silence" means something different on a condenser mic in a live room than on a
direct input. If nothing stands out, it does nothing.

Undo restores whatever the slot held before the take, processing and all.

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
  project.json            tempo, master gain, and per slot: length in bars, the
                          bars it plays on, how hard each was played, mute,
                          gain, the edits, and the tempo/rate it was recorded at
  samples/slot_00.wav     one file per filled slot, named by slot number
  samples/slot_00_L1.wav  one per overdub layer, when a take has any
  bounces/*.wav           whatever you have bounced
```

Saved a couple of seconds after any change (see `autosave_delay_s`) and on exit.
`project.json` is written atomically — a crash mid-save cannot corrupt it. Audio
files are only rewritten when the audio itself changed.

The format version is **5**, and every older version loads: a version-1 take
assumes it was recorded at the project's tempo, and versions 2, 3 and 4 simply
lack velocities, edits, and overdub layers respectively.

A take whose layer files have gone missing still loads and still plays — as the
summed audio it already was. It just cannot be [peeled back](#overdubbing) any
more. Losing the breakdown must never mean losing the take.

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

`project` is a directory, created if missing. With no project named you get
[the one you had open last](#resuming), falling back to `./song`.

`--help` carries three worked examples. `doctor` is worth running first on a new
machine: it prints one row per thing that matters — Python, each optional
package, the MIDI ports and audio devices it can see, whether it can write where
you are — each with a one-line fix when it is missing. It **always exits 0**,
because "everything is missing" is a diagnosis rather than a crash.

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
| `--script FILE` | Feed FILE to the simulator and exit (implies `--sim`); `-` is stdin |
| `--until-idle` | With `--script`, wait for the transport to stop before quitting |
| `--quiet` | With `--script`, do not print the grid after every command |
| `--bounce OUT.WAV` | Render the song and exit; needs no hardware |
| `--stems DIR` | Render one WAV per slot and exit |
| `--selftest` | Walk the hardware and write a report |
| `--calibrate` | [Measure input latency](#input-latency) and store it |
| `doctor` / `--doctor` | Print what is installed and what is missing, then exit |
| `--version` | Print the version and exit |
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
- **No swing**, no per-trigger probability, no choke groups or loop/gate modes —
  every sample is a one-shot that plays to its end.
- **No scenes or snapshots** of an arrangement; duplicating a block of bars is as
  close as it gets.
- **No per-layer editing** of an overdub: layers can be added and removed, not
  soloed or re-balanced against each other.
- **No banks.** One page of 64 slots, one 64-bar song.
- **Aftertouch** is received and ignored; velocity is used.
- **The colour display** shows text only: mode, transport, levels and messages.
  No waveform drawing, no graphics.

`plans.md` in the project root tracks all of it: 32 of the 58 planned items are
shipped, which completes the `v1.1` and `v1.2` release trains, and 26 remain.
[`CHANGELOG.md`](../CHANGELOG.md) is the release record.
