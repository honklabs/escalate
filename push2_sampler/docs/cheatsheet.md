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
| **Scale** | harmony: which loops fit together |
| **Setup** | settings page (open / close) |
| **Shift**+**Setup** | save the project right now |
| **Delete** | arm delete, then press a pad |
| **Tap Tempo** ×4 | set the tempo by tapping it |
| **Shift**+**Tap Tempo** | throw the taps away |
| **Tempo encoder** | BPM ±1 per click |
| **Shift**+**Tempo encoder** | BPM ±10 per click |
| hold **Tap Tempo** + **Tempo encoder** | BPM ±0.1 per click (beat-matching) |
| **Touch strip** | scrub the song (when stopped) |
| **Shift**+**Touch strip** | loop from there to the end of that page |
| **Rightmost column** | pulses on the beat while playing, in every mode |
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
| **Device** | open the editor (then **Select** trims it by ear) |
| **Convert** | slice this take across the pads |
| **Layout** | what this take sounds like, and a name for it |
| **Scale** | which other loops fit with this one |
| **Shift**+**Clip** | vary it across passes (living song) |
| **Automate** | generate this sample's bars instead of tapping them |
| **Select** | name and colour this slot |
| **Record** | re-record this slot |
| **Shift**+**Record** | record another take *beside* this one (up to 8) |
| **Delete** then a pad | clear every bar of this sample |
| **Shift**+**Delete** | delete the sample itself |
| **Up** / **Down** | previous / next filled slot |
| **encoder 1** | this sample's gain (0 – 2.0) |
| **encoder 2** | lay it back behind the beat, 0 – 120 ms |
| **encoder 3** | which alternate take plays |
| **encoder 4** | take mode: fixed / cycle / random |
| **Shift**+**encoder 2** | chance for the selected bar, 5 – 100% |
| **Shift**+**encoder 3** | play only on every Nth pass, 2 – 8 |
| **Shift**+**encoder 4** | reroll the project's dice, 0 – 63 |
| **button 1 below the display** | fit an off-grid take to its bars (when yellow) |
| **buttons 2-5 below** | play mode: one shot / loop / gate / retrig |
| **button 6 below** | at another tempo: off / resample / stretch |
| **button 7 below** | take mode; **Shift** removes the selected take |
| **button 8 below** | choke group: off → 1…8 → off |

| Pad colour | Means |
| --- | --- |
| green | plays here (hit hard, if this sample is velocity-sensitive) |
| mid green | plays here, hit at medium velocity |
| dim green | plays here, hit softly — or this sample is muted |
| dim blue | another sample plays here |
| amber | the playhead, on a bar where this sample plays |
| white | the playhead, anywhere else |
| flashing green | plays here *sometimes* — a [chance](#chance--bars-that-only-sometimes-play) bar |
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

## Alternate takes — several recordings on one pad

**Shift**+**Record** keeps the new take beside the old one instead of replacing
it, up to eight. Then a trigger picks one:

| Control | Does |
| --- | --- |
| **encoder 3** | which take you are listening to |
| **encoder 4** | `fixed` / `cycle` / `random` (**button 7** cycles the same) |
| **Shift**+**button 7** | remove the selected take |

| Mode | Chooses |
| --- | --- |
| `fixed` | always the one you picked |
| `cycle` | the next take each **pass** — pass 1 plays take 1 |
| `random` | a take per **trigger**, from the project's dice, reproducibly |

`cycle` is per pass, `random` is per trigger. A slot on eight bars plays one
take for the whole pass under `cycle`, and eight possibly-different ones under
`random`.

**Alternates are not layers**: overdubs sum, alternates replace, and the two
never coexist — adding an alternate flattens the layer breakdown. The edits and
a length repair apply to *every* take, because they describe the part.

A bounce covers a cycling slot's whole cycle, so all its takes reach the file.

---

## Living song — vary it across passes (**Shift**+**Clip**)

Extra bars a sample plays on **only every Nth pass**. "Every fourth pass, double
the hats."

| Control | Does |
| --- | --- |
| **encoder 1** | how often — every 2 to 8 passes |
| **encoder 2** | how much — extra bars, spread through the gaps |
| **encoder 3** | how many passes **Shift**+**Record** freezes |
| any pad | add or remove one bar by hand |
| **button 8 below** | clear it |
| **Shift**+**Record** | freeze that many passes as audio |

| Pad | Means |
| --- | --- |
| green | plays every pass |
| amber | varies, and this is the pass |
| flashing amber | varies, and it plays **next** pass |
| dim blue | varies, waiting its turn |

It is stored as **bars you can look at**, not a rule you have to trust — and it
is arithmetic, so the dice cannot move it. A bounce covers the whole cycle.

---

## At another tempo (**button 6** on a sample page)

| Mode | Does |
| --- | --- |
| `off` | nothing; the take keeps its length and goes yellow |
| `resample` | faster or slower, **pitch moves** — usually right for a break |
| `stretch` | pitch held, length changed — right for a bass line |

The first press offers whatever the material wants; the button then walks all
three. A stretching slot is no longer flagged off-grid, because the length is
handled. Computed between frames, so the take plays at its old length until it
is ready.

---

## The strip and the ring

- **Count-in** fills a ring round the edge of the grid, one pad per 16th.
- **The rightmost column** pulses on the beat in every mode, and never
  overwrites a pad the page is using.
- **The touch strip** scrubs while stopped; **Shift** + it picks a loop range.
  *The strip has never been verified on real hardware — if it does nothing, that
  is why.*

---

## Harmony — which loops fit together (**Scale**)

The library grid, coloured against **one reference slot**: the sample whose page
you came from, or the first filled slot from the library.

| Pad | Means |
| --- | --- |
| flashing | the reference — everything is compared to this |
| green | fits |
| amber | close, a note or two apart |
| red | clashes |
| dim white | a drum, or nothing with a key in it — nothing to compare |

| Control | Does |
| --- | --- |
| any filled pad | hear it, and read how it sits |
| **Shift** + a pad | compare against *that* slot instead |
| **button 1 below** | transpose the picked slot into line (one **Undo**) |
| **Scale** / **Session** | leave |

The transpose is the editor's own **pitch** edit, so it is non-destructive and
visible there. Accepting twice does nothing the second time, and ties go to the
smaller move.

The colours come from **pitch-class content**, not from a key. A key name is
shown and labelled a guess, because naming a tonic is the measurably weak part:
a held Cmaj7 reads "E minor". A bass part below about C2 is judged on its
harmonics and can read `close` where it should read `fits`.

---

## Chance — bars that only sometimes play

Press a bar on a sample page, then hold **Shift**:

| Control | Does |
| --- | --- |
| **encoder 2** | how likely *that bar* is — 5 – 100% in 5% steps |
| **encoder 3** | play only on every Nth pass of the loop — 2 to 8 |
| **encoder 4** | the project's dice, 0 – 63: a different variation, same every time |

An uncertain bar **flashes** green; a certain one is steady. (It cannot be a
dimmer green — brightness on a sample page already means recorded velocity.)

The status line reads `2 maybe-bar(s)   every 2 passes   dice 7`, and shows
nothing at all when nothing is uncertain. The transport grows `· pass 3` only
once something uses passes.

**Same dice, same song.** The roll is a pure function of `(seed, pass, bar,
slot)` with no state, so bar 40 of pass 3 sounds the same whether you played
from the top, dropped in halfway, or bounced the file. A bounce covers a whole
pass cycle — the lowest common multiple of every audible `every_n`, up to 8
passes — so what you hear is what lands in the file.

---

## Pattern — generate the bars (**Automate** on a sample page)

The grid is a **flashing** preview; bars it would replace show dim red. Nothing
is stored until you press **Automate** again.

| Control | Does |
| --- | --- |
| **encoder 1** | density — how many bars of the pattern play |
| **encoder 2** | rotation — same shape, different starting bar |
| **encoder 3** | algorithm: `euclid` / `every n` / `random` / `mirror` |
| **encoder 4** | seed (for `random`) or which slot to copy (for `mirror`) |
| **encoder 5** | **length** — how long the pattern is before it repeats |
| **button 1 below** | also cycles the algorithm |
| **Automate** | keep it — one Undo |
| **Session** | discard |

**Length is the one that matters.** Three bars over 64 is one hit every 21
bars; three over 8, repeating, is the tresillo:

```
density 3, length 64   x....................x..........
density 3, length 8    x..x..x.x..x..x.x..x..x.x..x..x.
```

Committing **replaces** this page's 64 bars and leaves the other pages alone.
Undo restores what was there, velocities included. Density 0 clears the page.
Pads do not edit here — the next encoder click would wipe the edit.

---

## About — what a take sounds like (**Layout** on a sample page)

The pads are a **spectrogram**: time across, frequency up (lowest at the
bottom), brightness is energy. A kick sits along the bottom, a hat across the
top, a held note is one horizontal line.

| Control | Does |
| --- | --- |
| any pad | hear the take |
| **button 1 below** | accept the suggested name — the only thing this page changes |
| **button 2 below** | switch between the spectrogram and the **timing scatter** |
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

### Timing view (button 2)

Each hit as a dot: time across, **early above** the line and **late below**.
Green within 10 ms, amber within 25 ms, red beyond.

```
very even (±3ms)   20ms behind the beat
8 hit(s) against beats   worst 24ms
```

Two separate facts: **evenness** is how consistent you are, **placement** is
where you sit. Consistently 20 ms behind is a groove; 5 ms out at random is
not. The grid (beats / 8ths / 16ths) is **inferred** from your playing and
named. **It never quantizes.** Turn on `coach` (or `--coach`) to get this after
every take.

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
| **Select** | trim it by ear instead (below) |
| **Device** | close the editor |
| **Shift**+**Device** | apply the edits to the recording for good (undoable) |

Nothing here touches the recording until you ask it to. Every turn is one undo
step, and turns within 1½ seconds of each other merge into one.

---

## Trim by ear (**Select** in the editor)

It never stops playing. **Select** does everything, and always means the same
thing: **that's it.**

```
Select      the take starts looping
tap a pad   "the start is here"
turn        until the short loop sounds right
Select      that's it -- it plays on
tap a pad   "the end is here"
turn        until it sounds right
Select      done
```

| Stage | You hear | A pad | The knobs |
| --- | --- | --- | --- |
| 1 find the start | the whole take, looping | marks it **here** | — |
| 2 tune the start | a short loop **from** the start | — | move it |
| 3 find the end | from the start on, looping | marks it **here** | — |
| 4 tune the end | a short loop **up to** the end | — | move it |

| Control | Does |
| --- | --- |
| **Select** | mark the point, or accept it |
| any pad | mark the point (hunting stages) |
| encoder 1 / 2 | coarse 20 ms / fine 1 ms |
| encoder 3 | how much you hear, 40–1000 ms |
| **button 1** | snap to the nearest attack |
| **button 8** | back to the take's edge |
| **Delete** | give up; the take is untouched |

Any pad, not the one under the playhead: you are tapping in time, not aiming.

The start loop runs **forward** from the point and the end loop runs **back** to
it, so the edge you are judging is the one at the loop seam. The anti-click fade
goes on the *other* edge — so **a click at the seam means your start has landed
mid-note**, which is worth hearing rather than smoothing away.

Writes the editor's own `trim in`/`trim out`, as **one** undo step.

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
| `--coach` | report how tight each take was, after every take |
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
