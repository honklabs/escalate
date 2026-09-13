# Cheat sheet

One page. Everything the program responds to. Print it, put it next to the Push.

New here? [Getting started](getting-started.md) explains *why* in the order you
need it. This is the *what*, for when you have already done that once.

---

## Everywhere, in every mode

| Control | Does |
| --- | --- |
| **Play** | start the song from bar 1 |
| **Stop** | stop everything now |
| **Shift**+**Stop** | stop at the end of the bar (display reads `ENDING`) |
| **Stop**, **Stop** | panic: stop and disarm whatever was armed |
| **Shift**+**Play** | perform mode (play the arrangement in by hand) |
| **Metronome** | click on / off |
| **Shift**+**Metronome** | monitoring: `off` → `auto` → `on` |
| **Repeat** | loop scope: `page` → `song` → `off` |
| **Page ◀** / **Page ▶** | bank A–D (which 64 slots the grid shows) |
| **Shift**+**Page ◀/▶** | song page A–D (which 64 bars a sample page shows) |
| **Undo** | take back the last edit (64 deep) |
| **Shift**+**Undo** | redo |
| **Session** / **Note** / **Left arrow** | back — leave this page |
| **Shift**+**Session** | master playback: watch the song from the samples grid |
| **Clip** | song overview (open / close) |
| **Mix** | mixer page (open / close) |
| **Browse** | project browser (open / close) |
| **Shift**+**Browse** | import audio from disk (open / close) |
| **Setup** | settings page (open / close) |
| **Shift**+**Setup** | save the project right now |
| **Delete** | arm delete, then press a pad |
| **Tap Tempo** ×4 | set the tempo by tapping it |
| **Shift**+**Tap Tempo** | throw the taps away |
| **Tempo encoder** | BPM ±1 per click |
| **Shift**+**Tempo encoder** | BPM ±10 per click |
| hold **Tap Tempo** + **Tempo encoder** | BPM ±0.1 per click (beat-matching) |
| **Row above the display** | input level meter (not buttons) |
| any button | briefly lights its own LED, so a dead button is obvious |

A lit **Undo** means there is something to take back. A dark one means there
isn't.

---

## Library — 64 of 256 samples (one bank)

The page you start on, and the one **Session** always returns you to.

| Control | Does |
| --- | --- |
| tap a **white** pad | record into that slot → Record mode |
| tap a **filled** pad | open that sample's page |
| **hold** a filled pad (½ s) | audition it, stay in the library |
| **Shift** + a filled pad | audition it immediately |
| **Record** | record into the first empty slot |
| **Shift**+**Record** | bounce the song to `bounces/<timestamp>.wav` |
| **Mute** then a pad | mute / unmute that slot |
| **Duplicate** then a pad | copy that slot to the next empty one |
| **Shift**+**Duplicate** | arm swap: the next two pads trade places |
| **Duplicate** then **Shift** + a pad | move it instead of copying |
| **buttons below the display** | recall one of 8 scenes |
| **Shift** + a button below | store the arrangement in that scene |

**Delete** disarms itself after 3 seconds. Deleting a slot that *plays* somewhere
takes two presses — the first says `slot 7 plays on 12 bars - press again`.

| Pad colour | Means |
| --- | --- |
| white | empty |
| green | filled |
| dim green | filled, muted |
| amber | sounding right now — auditioned, or playing in the song |
| dim amber | comes in on the next bar |
| yellow | filled, but the wrong length for this tempo |
| flashing red | **Delete** is armed; the next pad you press is deleted |
| every filled pad yellow | **Mute** is armed; the next pad you press is muted |
| every filled pad flashing blue | **Duplicate** is armed |
| amber bar filling the grid | a bounce is rendering |

---

## Record mode — choose a length, play it

| Control | Does |
| --- | --- |
| any pad | set the length: top-left through that pad, in reading order |
| **encoder 1** | same thing, ±1 bar |
| **Record** | count in, then record |
| **Record** (while recording) | start the take over |
| **Stop** | end the take early, or cancel before it starts |
| **Session** | give up, back to the library |

White pads are the bars that will be recorded; the first white pad is always the
top-left one. Recording stops by itself and drops you on the new sample's page.

| Pad colour | Means |
| --- | --- |
| white | this bar will be recorded |
| off | not included |
| red, flashing on each beat | counting in |
| bright red | being recorded right now |
| dim red | already recorded |

---

## Sample page — where this sample plays

Each pad is **one bar of the current song page**: on page A, top-left is bar 1,
the pad below it is bar 9, bottom-right is bar 64. **Shift**+**Page ◀/▶** moves
to another page of 64.

| Control | Does |
| --- | --- |
| any pad | this sample plays on that bar / stops playing there |
| hold a pad, press another | paint every bar between them |
| double-tap an empty pad | lay the take across the next 4 bars |
| double-tap a playing pad | clear it from those 4 bars |
| **Duplicate**, bar A, bar B | copy the block A…B-1 onto B (the gap is its length) |
| **Duplicate**, bar A, **Shift**+bar B | move it instead of copying |
| **New** | overdub another pass on top (sound-on-sound) |
| **Shift**+**New** | remove the last overdubbed layer |
| **Mute** | mute this sample (`MUTED` on the display) |
| **Accent** | velocity sensitivity: `flat` ⇄ `velocity` |
| **Device** | open the editor |
| **Convert** | slice this take across the pads |
| **Layout** | what this take sounds like, and a name for it |
| **Select** | name and colour this slot |
| **Record** | re-record this slot |
| **Delete** then a pad | clear every bar of this sample |
| **Shift**+**Delete** | delete the sample itself |
| **Up** / **Down** | previous / next filled slot |
| **encoder 1** | this sample's gain (0 – 2.0) |
| **encoder 2** | lay it back behind the beat, 0 – 120 ms |
| **button 1 below the display** | fit an off-grid take to its bars (when yellow) |
| **buttons 2-5 below** | play mode: one shot / loop / gate / retrig |
| **button 8 below** | choke group: off → 1…8 → off |

| Pad colour | Means |
| --- | --- |
| green | plays here (hit hard, if this sample is velocity-sensitive) |
| mid green | plays here, hit at medium velocity |
| dim green | plays here, hit softly — or this sample is muted |
| dim blue | another sample plays here |
| amber | the playhead, on a bar where this sample plays |
| white | the playhead, anywhere else |
| flashing blue | the first bar of a block you are duplicating |
| faint white | 4-bar phrase mark; brighter every 16 bars |

---

## Master playback (**Shift**+**Session**)

The library grid, and nothing to edit. Each pad **flashes white as its sample
fires**, then falls back to the slot's own colour.

| Control | Does |
| --- | --- |
| any filled pad | audition it |
| **Play** / **Stop** | as everywhere |
| **Page ◀/▶** | another bank |
| **Session** | leave |

**Delete**, **Mute** and **Duplicate** do nothing here on purpose — this is the
page where you are listening, not deciding. The display counts how many slots
fired in the bar you are in.

The flash marks the **attack**, not how long the sample lasts: a 4-bar pad
flashes once rather than holding its pad lit for four bars.

---

## Swap two samples (**Shift**+**Duplicate**)

| Step | |
| --- | --- |
| **Shift**+**Duplicate** | arms it; filled pads flash cyan |
| first pad | holds white — "this one" |
| second pad | they trade places |
| the same pad twice | cancels |

Everything moves: audio, the bars it plays on, name, colour, gain, play mode,
choke group. The slot *numbers* stay put. Picking an empty second slot is a
**move**, and is allowed. One **Undo**.

---

## Play modes and chokes — how a sample ends

| Play mode | What it does |
| --- | --- |
| **one shot** | plays to the end of the recording, whatever else happens |
| **loop** | repeats until a bar where it is *not* triggered, then releases |
| **gate** | stops at the end of the bar it started in, however long the audio |
| **retrig** | a new trigger cuts the previous voice instead of layering it |

A **choke group** (1–8) makes samples cut each other — a closed hat silencing an
open one. A sample never chokes itself; that is what **retrig** is for.

---

## Groove — laying a take behind the beat

**Encoder 2** on a sample page, 0–120 ms in 5 ms steps, shown as `+20ms` on the
display. Per sample, saved with the song, one undo step. This is what groove
means when your grid is bars: a clap a hair behind the kick.

**Late only.** To push one sample *ahead*, lay everything else back — a bar line
is the earliest moment the engine knows about.

Recording is untouched: the nudge is applied on the way to the speakers, so it
affects playback and bounces but never where a take was captured.

---

## About — what a take sounds like (**Layout** on a sample page)

The pads are a **spectrogram**: time across, frequency up (lowest at the
bottom), brightness is energy. A kick sits along the bottom, a hat across the
top, a held note is one horizontal line.

| Control | Does |
| --- | --- |
| any pad | hear the take |
| **button 1 below** | accept the suggested name — the only thing this page changes |
| **Layout** / **Session** | close |

| Reading | |
| --- | --- |
| sounds like | `low drum` `bright drum` `drum` `bass` `tone` `noise` |
| pitch | the note, for pitched takes only |
| tempo | from the gaps between hits — absent when it cannot be trusted |
| hits | how many, and per second |
| brightness | `dark` `warm` `bright` `very bright`, plus the centroid |

**Every reading shows its confidence**, and a weak one says `not sure` rather
than being rounded into a fact. Five roles, not six: nothing here can tell a
snare from a hat, so a snare reads as `bright drum`.

---

## Slice — one take becomes a kit (**Convert** on a sample page)

The pads are the take; every cut is marked white. **Press a pad to hear that
slice.**

| Control | Does |
| --- | --- |
| **button 1 below** | cut by **bars** — one slice per bar |
| **button 2** | cut by **beats** |
| **button 3** | cut at **transients** (where the hits are) |
| **encoder 1** | transient sensitivity, 0.00–1.00 |
| **Convert** | write the slices, keep the original |
| **Shift**+**Convert** | write them and remove the original |
| **Session** | leave, changing nothing |

Slices land in the free slots **after** the source. Each is **1 bar** whatever
its length, named `take/1`, `take/2`…, and carries the source's gain, colour,
play mode, choke group, output and nudge but **none of its bars**. The whole
conversion is **one Undo**.

A one-bar take opens on **beats**. Not enough free slots refuses and says how
many there are. At most 64 slices; two hits closer than 30 ms are one hit.

Transients are excellent on percussive material (measured: 31 of 31 within
0.7 ms) and approximate on overlapping sustained notes — turn sensitivity down,
or use bars/beats.

---

## Editor — shape a take (**Device** on a sample page)

The grid becomes the audio: 64 slices, bright where it is loud. **Press a pad to
play the take from there.** Dim red is what you are trimming away.

Encoders above the display, left to right; the button underneath resets or
toggles:

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| trim in | trim out | fade in | fade out | pitch | gain | reverse | normalise |
| 5 ms | 5 ms | 2 ms | 2 ms | ±12 st | 0.05 | on/off | on/off |

| Control | Does |
| --- | --- |
| **Device** | close the editor |
| **Shift**+**Device** | apply the edits to the recording for good (undoable) |

Nothing here touches the recording until you ask it to. Every turn is one undo
step, and turns within 1½ seconds of each other merge into one.

---

## Perform mode — play it in (**Shift**+**Play**)

The library grid again, but the pads *fire*.

| Control | Does |
| --- | --- |
| any filled pad | fire that sample at the next quantize point |
| **Record** | also write what you play into the arrangement (`WRITING`) |
| **Fixed Length** | quantize: `1 bar` → `off` → `1/16` → `1/8` → `1/4` → `1/2` → `1 bar` (bar fractions) |
| **swing encoder** | swing 0–66 %: pushes the odd grid lines late |
| **Delete** | erase bars as the playhead crosses them; press again to stop |
| **Session** | leave |

**Swing needs a sub-beat quantize** (`1/16 bar` or `1/8 bar`). Everything in the
arrangement is on a bar line, and bar lines never swing — so the display says
`(swing needs a sub-beat quantize)` rather than leaving you turning a knob with
no effect. For the arrangement, use **groove** on a sample's own page.

Hit harder for more level on any sample set to `velocity` (**Accent** on its
page).

---

## Mixer (**Mix**)

Eight strips at a time: the current row of the library, as vertical level meters.

| Control | Does |
| --- | --- |
| **encoders 1–8** | gain of each strip |
| **buttons below the display** | mute each strip |
| **Solo**, then a button below | solo that strip |
| **Solo** again | clear the solo |
| **Master encoder** | gain on the whole mix |
| **Shift** + a button below | send that slot to the next output pair |
| **Up** / **Down**, or any pad | another row of eight |
| **Mix** | close |

Meters fill upwards: green, amber in the top quarter, red at the very top. Solo
overrides mute without destroying it — un-solo and your mix is exactly as it was.

### Output pairs

**Shift** + a strip button cycles `main` → `3/4` → `5/6` → `7/8` → `main`,
stopping at the pairs your device really has. A routed slot leaves the main mix,
so headphones on that pair hear it alone.

| | |
| --- | --- |
| A routed slot in a bounce | no — a bounce is the main outputs |
| A routed slot in its stem | yes — full audio |
| A pair the device hasn't got | falls back to `main`, flagged with `!` |

Needs `--out-channels 4` (or more) for there to be anywhere to route to.

---

## Song overview (**Clip**)

The whole arrangement as a heat map. Each pad is **8 bars × 8 slots** — columns
are bars, rows are slots.

| Pad colour | Triggers in that cell |
| --- | --- |
| off | none |
| dim blue | 1 |
| blue | 2–3 |
| amber | 4–7 |
| white | 8+ |

The playing column is one rung brighter. **Press a pad to zoom in**; each pad is
then one bar of one slot. **Page ◀/▶** moves to the next cell, **Delete** clears
the cell, **Clip** zooms back out then leaves.

---

## Import (**Shift**+**Browse**)

A file browser on the pads, starting at the samples root.

| Control | Does |
| --- | --- |
| a pad | highlight it; the display says what it is |
| the same pad again | open the folder, or import the file |
| **Up** / **Down** | previous / next |
| **button 1** | import / open the highlighted one |
| **button 2** | up one folder |
| **button 3** | back to the samples root |
| **button 5** | your home folder |
| **Browse** or **Session** | leave |

White = folder, blue = audio file, bright = highlighted. Nothing is highlighted
until you press something, so a first press never imports.

The file is resampled to the session rate and claims the nearest whole number of
bars. It is **never stretched**: a 3.5-bar file stays 3.5 bars and is flagged
off-grid, and **button 1** on its sample page fits it if you want that. Imports
land in the first empty slot, never over a take, and are one **Undo**.

`.wav` always works. `.flac`, `.aiff`, `.mp3` and friends need `soundfile`
installed — without it those pads say so rather than failing when pressed.

---

## Browser (**Browse**)

| Control | Does |
| --- | --- |
| a pad | highlight that project |
| the same pad again | open it |
| **Up** / **Down** | previous / next |
| **button 1** | open the highlighted one |
| **button 2** | new project |
| **button 3** | duplicate it |
| **button 5** | **hold** to delete it |

Green = has samples, dim white = empty, dim amber = the one you have open.
Opening saves your current song first and does not restart the audio.

---

## Naming (**Select** on a sample page)

Top 7 rows of pads = words (8 categories × 8). Bottom row = 8 colours; press the
same one again to clear it. Buttons below = jump to a category.

---

## Settings (**Setup**)

The pads go dark on purpose. Each button *below* the display owns one setting;
the encoder above it changes the value, pressing the button resets or cycles it.

| 1 | 2 | 3 | 4 |
| --- | --- | --- | --- |
| count-in beats | monitoring | monitor gain | record latency |

| 5 | 6 | 7 | 8 |
| --- | --- | --- | --- |
| play while recording | autosave delay | input device | audio block size |

**Up** / **Down** reaches two more pages:

- page 2 — **auto trim**, **auto normalise**, **auto fade** (post-take
  processing, all off by default), and **dim library**.
- page 3 — **pre-roll**, **click sound**, **click volume**, **click on rec
  only**, **click output**.

**Setup** again closes the page and writes
`~/.config/push2sampler/settings.json`. Changing the input device or block size
restarts the audio stream; if the new one will not open, the old one is kept and
the display says why.

---

## Command line

| | |
| --- | --- |
| `python -m push2sampler SONG` | run it |
| `--sim` | no hardware: terminal simulator ([docs](simulator.md)) |
| `--script F` | run a simulator command file and exit (add `--quiet`, `--until-idle`) |
| `doctor` | what is installed, what is missing, and how to fix it |
| `--version` | print the version |
| `--selftest` | guided hardware probe, writes `hardware-report.json` |
| `--led-test` | the pads are dark: which layer is at fault, writes `led-report.json` |
| `--midi-probe` | nothing in either direction: facts about the MIDI link, writes `midi-report.json` |
| `--calibrate` | measure input latency and store it |
| `--lights-off` | blank every pad and button LED and exit |
| `--import FILE` | import an audio file into the project and exit |
| `--slot N` | with `--import`, which slot (1-256); default the first empty |
| `--samples-root DIR` | where **Shift**+**Browse** starts looking |
| `--clock ROLE` | `internal`, `midi_slave`, `midi_master`, `link` |
| `--clock-port NAME` | which MIDI port carries clock (not the Push's) |
| `--midi-port NAME` | force the Push port (`live`, `user`, any substring) |
| `--list-ports` / `--list-devices` | what Python can see |
| `--bounce OUT.wav SONG` | render the mix, no hardware needed |
| `--stems DIR SONG` | one WAV per filled slot |
| `--bpm N` | tempo for this run |
| `--monitor-port [N]` | serve the read-only monitor page (default 8765, `0` off) |
| `--monitor-host HOST` | what it binds to; loopback by default |
| `--monitor off\|auto\|on` | hear the input — *audio* monitoring, nothing to do with the page |
| `--rec-latency-ms N` | trim N ms off the front of each take |
| `--count-in N` | count-in beats (default 4) |
| `--no-play-while-recording` | silence the song during a take |
| `--input-device N` / `--output-device N` | pick audio devices |
| `--samplerate N` / `--blocksize N` | stream format |
| `--no-settings` | ignore the settings file |
| `--no-save` | never write to the project directory |
| `--no-display` | skip the Push screen |

Command-line values win for that run and are **not** written back to the
settings file.

---

## Monitor page

`--monitor-port` mirrors the surface in a browser: the pads in their colours,
the banner, the transport, the display text and every lit button.

| | |
| --- | --- |
| `/` | the page (`http://localhost:8765/`) |
| `/events` | one message per frame, server-sent |
| `/snapshot.json` | the latest frame, for a script |

**Read-only**: every verb but `GET` and `HEAD` is refused. **Loopback only**
unless `--monitor-host` says otherwise — read-only is not private, and the page
carries your slot names and your song's shape. Works with `--sim`, which is how
you watch the LEDs with no hardware at all.

---

## Files

```
SONG/project.json            tempo, pages, master gain, 8 scenes; per slot:
                             bars, trigger bars, velocities, mute, gain,
                             colour, edits
SONG/samples/slot_NNN.wav    one per filled slot (0-255)
SONG/bounces/*.wav           what you have bounced
~/.config/push2sampler/settings.json
```

**256 slots** in 4 banks, **256 bars** in 4 pages. The grid always shows 64 of
each; the display names which.

Saves itself a couple of seconds after any change, and on exit. A `*` on the
transport line means there is something unsaved; `saved` appears when it writes.

Start with no project name and you get the project, page and slot you were last
in. `SURFACE OFFLINE` on the display means the Push stopped answering — the audio
carries on, and it reconnects by itself.
