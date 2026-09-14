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
* `Shift`+`Session` opens **master playback**: the same grid with nothing to
  edit, each pad flashing as its sample fires. The flash marks the *attack*
  rather than the duration -- the engine publishes a "fired this block" set for
  it, because `sounding` cannot tell starting from sounding -- so a 4-bar pad
  blinks once instead of holding its pad lit for four bars.
* `Shift`+`Duplicate` **swaps** two slots: press one pad, then the pad it should
  change places with. Audio, bars, name, colour, gain, play mode and choke group
  all move; the slot *numbers* stay put, because a slot number is identity
  everywhere else in this program. One undo step.

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
* The first track encoder sets this sample's gain; the **second lays the sample
  back behind the beat**, 0-120 ms in 5 ms steps. That is what groove means when
  your grid is bars: a clap a hair behind the kick stops sounding like a
  machine. Late only -- a bar line is the earliest moment the engine knows
  about, so to push one sample *ahead* you lay everything else back, and the
  feel is relative anyway. The nudge defers the whole decision rather than just
  the audio: whether a `loop` renews, whether a `retrig` cuts, whether a choke
  fires are questions about the moment a sample *sounds*, and deciding at the
  bar line would cut a retriggered voice up to 120 ms before its replacement
  began. Saved with the project (format 9), one undo step, and applied on the
  way to the speakers so a take is never re-cut.
* **Chance** makes a bar a *maybe* instead of a certainty, so a song moves
  without you drawing every variation by hand. Hold `Shift`: encoder 2 sets the
  selected bar's chance (5-100 % in 5 % steps), encoder 3 makes the whole sample
  play only on **every Nth pass** of the loop (2-8), and encoder 4 rerolls the
  project's **dice** (0-63). An uncertain bar *flashes* rather than dimming,
  because brightness on a sample page already means recorded velocity. The roll
  is a **pure function** of `(seed, pass, bar, slot)` with no state to diverge,
  which is the whole of the reproducibility claim: bar 40 of pass 3 sounds the
  same whether you played from the top, dropped in at bar 17, or rendered the
  file offline. A stateful generator could not promise that. The dice are per
  project, not per sample, so the arrangement varies *together*. Saved with the
  project (format 10), one undo step each.

  A test found the half of that claim that was not obvious: a bounce renders
  **linearly** and therefore never wraps, so with passes counted only on a wrap
  a bounce sat on pass 1 for ever and a sample set to *every 2nd pass* was
  absent from the output file **entirely**. The render now covers a full cycle —
  the lowest common multiple of every audible sample's `every_n`, capped at 8
  passes — and the schedule is tiled across it.
* **Alternate takes** put several recordings of one part on one pad, up to
  eight. `Shift` + **Record** keeps the new take *beside* the old one instead of
  replacing it; encoder 3 picks which you are listening to, and encoder 4 (or
  button 7) decides how a trigger chooses: `fixed` always plays the one you
  picked, `cycle` advances one take per **pass** of the loop, and `random` picks
  per **trigger** from the project's dice — which is the difference between a
  loop that breathes across repeats and a part that never quite repeats. Three
  real performances of one snare on `random` is the difference between a sampler
  and a drummer.

  `random` needed its own dice stream, and the reason is not tidiness. "Did this
  bar play?" is `roll(...) < chance`, so on a 60 % bar every trigger you hear has
  a roll below 0.6 — reusing that number to index three takes puts all of them in
  the first two thirds and the third take **never sounds at all**. Measured
  55.8 / 44.2 / 0.0 on the shared stream, 33.2 / 33.3 / 33.5 once the seed is
  salted.

  Alternates are not layers: overdubs **sum**, alternates **replace**, so the two
  never coexist and adding a take flattens the layer breakdown. The edits and a
  length repair apply to *every* take, because they describe the part rather than
  one recording of it. And a `cycle` slot is a pass divisor exactly like
  `every_n` — three takes mean the song does not repeat until pass three, so a
  one-pass bounce would write take 1 and silently discard the other two. Project
  format 11; one WAV per take, and a slot whose take files have gone opens as a
  plain single-take slot rather than losing the take.
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

`Shift` + a strip button sends that slot to **its own output pair** -- `main`
(channels 1/2) through `3/4`, `5/6`, `7/8` -- cycling only through the pairs the
open stream actually has, so it never offers you a choice that would do nothing.
A routed slot leaves the main mix entirely, which is the point: a kick on 3/4 is
a kick on its own in a pair of headphones while 1/2 carries the rest. It is
therefore **not in a bounce** (a bounce is the main outputs) but **is in its own
stem** (a stem is what the slot played). A pair the device turns out not to have
falls back to the main mix rather than into silence, marked `!` on the display.
Needs `--out-channels 4` or more for there to be anywhere to go.

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
cycles the quantize amount, as fractions of a bar: off, 1/16, 1/8, 1/4, 1/2, and
1 bar, which is where a fresh page starts so your first press lands on a
downbeat.

The **swing encoder** pushes every odd grid line late, by 0-66 % of the
division: at a 1/8 quantize the downbeats stay put and the eighths between them
move, which is what swing is. It needs a quantize **finer than a beat** to do
anything, because sub-beat time exists nowhere else in this program -- every
arrangement trigger is on a bar line, and swinging bar lines is not swing. So
both the encoder and the page say which of those you are in rather than leaving
you turning a knob with no effect. For the arrangement, the bar-grid equivalent
is the per-sample nudge above.

Press `Record` and what you play is also **written into the arrangement**, at
the bar it sounded in -- so you can build the song by playing it, pass after
pass, instead of toggling bars. `Delete` does the opposite: while it is armed,
bars are wiped as the playhead crosses them, starting from the next bar line.
Everything you play in or erase is one undo step.

`Session` goes back to the library.

### 4b. Slicing: one take becomes a kit

`Convert` on a sample page opens the slice page. The pads are the take with
every cut marked, **pressing a pad plays the slice it falls in**, and the three
buttons below the display cut by **bars**, by **beats**, or at **transients**
with a sensitivity encoder. `Convert` again writes the slices into the free
slots after the source, as **one undo step** -- "slice this into a kit" is one
decision, and taking it back a pad at a time would be sixteen presses to undo
one. The original is kept unless you hold `Shift`.

Each slice carries the source's gain, colour, play mode, choke group, output and
nudge and **none of its bars**: those first things describe how the sound
behaves and every slice is the same sound, while where the whole loop played is
not where its pieces should. A slice is always 1 bar whatever its real length --
it is a hit, not a bar of music, and its true length would have the off-grid
check flag every one of them.

Transients come from a spectral-flux novelty curve in `analysis.py`, numpy only.
**Five rounds of prototyping against signals with chosen onset frames** found
four things first, each of which would have been a bad day inside a UI: onsets
landing 10-15 ms early (the analysis window's start, not the hit in it);
refinement on energy *level* finding the previous hit's tail rather than the
new attack; a held 440 Hz tone producing 59 onsets, because leakage wobble
divided by its own maximum looks like signal; and a global prominence floor
that changed nothing on any of eleven signals and was deleted rather than kept
as a knob that does not turn. Measured at the default: a 16th-note drum pattern
is 31 of 31 within 0.7 ms, a ghost note at a tenth the level survives, and
silence, noise and a held tone all yield nothing. Overlapping sustained notes
are approximate, which is why bars and beats exist.

### 4c. About: what the instrument thinks it heard

`Layout` on a sample page. The pads become a **spectrogram** -- time across,
frequency up with the lowest at the bottom, brightness is energy, rows spaced
by octaves so a drum does not occupy one row and hiss five. A kick is a blob
along the bottom, a hat a stripe across the top, a held note a line.

The display reads back what `analysis.describe` measured: a role, a pitch with
its note name, a tempo, how many hits and how dense, brightness as a centroid,
and the energy split across three bands. **Every reading carries a confidence,
and a weak one says so** rather than being rounded into a fact -- the page's
last line is "every reading is a measurement, not a fact", and that is the
design rather than a disclaimer. Button 1 accepts a suggested name, and is the
only thing on the page that can change the project.

**The plan asked for six roles and the features support five.** Six rounds of
prototyping established that `kick / snare / hat / bass / pad / vocal` is not
separable by band energy and envelope: a synthesised snare classified as a hat
at 0.85 confidence, and `pad` versus `vocal` is the same problem. The
vocabulary is therefore what the measurements can defend -- `low drum`,
`bright drum`, `drum`, `bass`, `tone`, `noise` -- and the honest cost is that a
snare reads as a bright drum.

The prototype found five more things, each measured rather than guessed:
autocorrelation on a chord finds the GCD period (220+277+330 came back as
55 Hz, making every pad a bass); white noise classified as a hat at 0.92
confidence until an envelope gate went in, because a struck sound decays and
noise does not; periodicity is not pitch confidence (a kick every half second
is 0.95 periodic *at the hit rate* and duly reported a 1200 Hz "pitch");
scoring harmonicity as the mean harmonic strength inverted the measure, so a
pure sine scored 0.13 and white noise 0.54; and note names were a semitone or
two out until the peak was interpolated, because one FFT bin at 110 Hz is 10%
and a semitone is 5.95%. The note-naming helper itself was an octave low --
440 Hz came back "A3" -- caught only because the test named the notes it
expected.

Tempo gets the same treatment: exact to a fraction of a BPM on crisp attacks,
useless on smeared ones, so below a confidence threshold it is **not reported
at all**. Its octave ambiguity (90 BPM in eighths is 180 in quarters, and
nothing in the timing distinguishes them) is resolved with the one thing a
sampler knows and a general analyser does not: the session's own tempo.

### 4d. Generated patterns

`Automate` on a sample page. Instead of tapping sixteen bars in, turn an
encoder until the rhythm is right: density, rotation, algorithm (`euclid` /
`every n` / `random` / `mirror`), a seed, and a **length**. The grid previews it
flashing -- so it never looks like bars that are stored -- with anything it
would replace in dim red. `Automate` again keeps it as one undo step;
`Session` discards.

`patterns.py` is pure functions from those five numbers to a `set[int]`, which
is what lets the preview and the commit call the *same* function: there is no
second code path to disagree with the first, and a pattern is reproducible from
five numbers rather than from luck.

**The length control is not in the plan, and building the page without it
showed why it has to be there.** Spread three bars evenly over a whole 64-bar
page and you get one hit every twenty-one bars, which is not a rhythm -- it is
a rounding error with a downbeat. A pattern is short and repeats: three over
eight, eight times, is the tresillo, and that is what turning a density encoder
is supposed to give you.

`euclid` is Bjorklund's algorithm, checked against Toussaint's published table
of traditional rhythms. Eighteen of its twenty-one entries matched immediately;
the three that did not are all the single-rest case, where the grouping loop
ends before it can interleave and the rest lands last rather than second.
Fixing that then contradicted a twenty-first entry which had been written down
from memory -- the memory was wrong, and two independent derivations agree
against it. Beyond the published examples the tests assert the property those
examples are *of*, exhaustively to length 64: the gaps between consecutive hits
never differ by more than one step.

### 4e. The timing coach

Button 2 on the About page switches the grid to a **timing scatter**: each hit
as a dot, time across, distance from the beat up and down -- early above the
centre line, late below, green within 10 ms and red past 25. The `coach`
setting (or `--coach`) prints the same summary after every take.

It reports **two separate facts**, and keeping them apart is the whole value:

```
very even (±3ms)   20ms behind the beat
```

*Evenness* is consistency; *placement* is where you sit. The first version
conflated them into one verdict and produced "very tight: 20ms late", which is
two statements wearing one label -- and the more interesting one is that
playing consistently 20 ms behind the beat is a groove, while being 5 ms out at
random is the thing to work on.

**The grid is inferred, not assumed.** Measuring a sixteenth pattern against
quarter notes would call every other hit 125 ms late at 120 BPM, which is the
wrong question rather than a timing error -- so beats, eighths and sixteenths
are all tried and the one your playing fits is used, and named. A finer grid
has to earn it twice: reduce the spread appreciably **and** have a quarter of
the hits land on lines the coarser grid lacks. That second rule came from a
test: seven hits on the beat and one 90 ms late chose a sixteenth grid and
reported the 90 ms error as 35, and a coach understating your error is the one
direction it must not fail in.

It never quantizes. `Shift`+`Device` -- which the plan suggested for recalling
this -- is already "apply the edits permanently", and putting an informational
readout on the same chord as a destructive action would be a poor trade, so it
lives on the page that already answers "tell me about this take".

### 4f. Harmony: which of these loops fit together

`Scale` on a sample page brings the library grid back, coloured by how each slot
sits against **that** one: green fits, amber is a note or two apart, red clashes,
dim white has no harmony to compare. The reference flashes. `Shift` + a pad
re-references without leaving, which is the second question anybody asks.

Press a red pad and the page offers a transpose; **button 1** applies it. That is
the editor's own `pitch_semitones` (`NF-03`), not a new field: "move this up two
semitones" is a thing the editor already does, so this is non-destructive,
visible there, and one undo step. Accepting twice does nothing the second time,
because the suggestion comes from rotating the pitch-class content until it
clashes least -- after the shift the best rotation *is* the one you are on. Ties
go to the smaller move: a C# triad against C major was first told to go up four
semitones, which does land on F and does fit, when down one is as good and is
what a hand expects.

**The plan asked for "key detection via chroma", and the key turned out to be
the unreliable half.** Naming a *tonic* from pitch-class weights is a guess
about emphasis: a held Cmaj7 comes back `E minor`, correctly observing that
those four notes also sit in E minor, and a C triad with twelve harmonics does
the same. The chroma underneath was right on all ten signals tested. So the
colours are computed from **pitch-class content** -- the fraction of one take's
energy landing on notes the other does not use -- and the key is shown labelled
as a guess, because it is still the thing a musician wants to read. Measured
against material built in known keys: itself 0.028, A minor 0.026, a Cmaj7 0.009,
G major 0.041, D major 0.135, E flat major 0.505, F sharp major 0.524. The two
thresholds sit in the gaps in that list rather than having been chosen.

The measure is **asymmetric on purpose**: a three-note pad inside a seven-note
progression fits, while the progression laid over the pad introduces four notes
the pad never plays, and "does adding this to what I have selected work" is a
directed question.

Drums are not coloured, and deciding that needs **two** gates because each
catches a case the other misses: the role gate (`IN-02`) rejects a kick, whose
pitch-class content is peaked enough to look tonal (0.077), and a flatness gate
rejects a chromatic run (0.001) and white noise that happened to read as a tone
(0.008). A kick under a chord progression is the most ordinary thing in music,
so "no harmony here" is the answer rather than a warning.

One limitation, stated because it moved a constant: the analysis band starts at
**90 Hz, not 60**. At 60 a C-G-C bass figure in octave 1 read as *clashing with
its own key* -- the one mistake this page must not make -- because the window is
more than a semitone wide down there and the note smears into classes it never
played. At 90 nothing in-key reads red; the residue is that the bottom octave
hedges towards "close", which is a hedge and not a warning.

### 4g. Living song: a variation across passes

`Shift`+`Clip` on a sample page adds a **variation** -- extra bars this sample
plays on only every Nth pass. "Every fourth pass, double the hats" is what it is
for: encoder 1 sets how often, encoder 2 how much, a pad adds one by hand, and
`Shift`+`Record` freezes however many passes you ask for as a single file.

**It needed no engine change at all,** which is the interesting part. An extra
trigger that fires only on every 4th pass *is* a trigger with `NH-10`'s
`every_n` of 4, so a variation is a second set of bars scheduled with that
divisor -- and it inherited reproducibility, correct bouncing and a readable grid
from work already done. `passes_needed` grew one clause and that was all of
`render.py`.

It is **bars, not a rule**: stored concretely so you can look at what pass 4 will
do, edit one by hand, and see it on a grid, rather than trusting something
evaluated at playback. And it is **arithmetic, not chance** -- "every 4th pass"
is a divisor, so the project's dice deliberately cannot move it. The two compose:
a chance on a variation bar is something that sometimes happens, on some passes.

The grid flashes a variation bar on the pass *immediately before* it plays, not
whenever it merely is not due -- otherwise "about to change" and "eventually"
are the same pixel, and the display of what is about to change is the one thing
the plan explicitly asked for. Project format 13.

### 4h. Fitting a take to another tempo

A take remembers the tempo it was cut at, so button 6 on a sample page decides
what happens when the song's is different: `off` (the take keeps its length and
goes yellow, as before), `resample` (faster or slower, **pitch moves with it**),
or `stretch` (WSOLA: pitch held, length changed). The first press offers whatever
the material wants, because `IN-02` already listened -- percussion gets
`resample`, because a break played faster *is* pitched up and that is a sound
records have been made of, and because measurement says percussion is precisely
what WSOLA is worst at (0.78-0.83 spectral similarity against 0.96-1.00 for a
chord).

A stretching slot is **no longer flagged off-grid**: the length is being handled,
so the yellow pad would be telling you to fix something already fixed. A change
too large to absorb still is flagged, because then it genuinely is not.

Five things the prototype found, each now a test. **Every stretch ended in a
click** -- running out of input left the tail silent, so a 2-second tone at 1.5x
finished with 615 frames of nothing and a 0.488 step into them against a source
whose worst step is 0.063; the read position is clamped so running out reuses the
final frames. **Normalised cross-correlation, the textbook similarity measure,
was measured and rejected**: 4x slower and worse on a chord. **The search had to
be vectorised**, not merely tidied -- as a Python loop a 30-second take took
2.2 s, as one `np.correlate` call it takes 0.33 s, bit-for-bit identical. **The
search runs on the channel sum** and the result is applied to both, because
searching per channel picks different offsets left and right and smears the
stereo image. And **the plan's own test assertion is only valid for one note**:
"the dominant frequency is unchanged" says nothing about a chord, whose three
near-equal partials make `argmax` pick whichever is momentarily loudest, so each
partial is checked separately.

There is **no worker thread**, which is how the plan's warning ("must not be
started from the audio callback") is met: `StretchJob` is stepped from the frame
loop exactly as `BounceJob` already was. Project format 12.

### 4i. The strip, the ring and the pulse

Three uses for hardware nothing else touches.

The **count-in fills a ring round the border of the grid**, one pad per sixteenth,
arriving at the top-left corner on the downbeat -- a shape you feel rather than a
number you read. The next pad shows dim before it lands, and a pre-roll flashes
the ring instead of filling it, because nothing is being counted during the
run-up and a ring that started then would arrive a bar early.

The **rightmost column pulses on the beat in every mode**, brighter on the
downbeat, lit for about a third of a beat. It only ever paints pads the current
page left dark, checked by looking for `OFF` rather than by tracking claims --
which means every mode, including ones not yet written, wins the collision
without knowing the overlay exists.

The **touch strip scrubs while stopped** (bottom is bar 1, top is the last bar,
and the grid follows to the page you land on) and picks a **loop range** with
`Shift`, from your finger to the end of that page. It is refused while playing or
recording and says so: a finger brushing the strip mid-phrase must not move the
playhead.

That needed a new engine verb, which a test found: scrubbing was written as
`play(bar)` then `stop()` and every scrub landed on bar 1, because `stop` rewinds
to the top *by design*. `Engine.seek` is a position change on a transport that
stays stopped, refused while running or recording.

**The strip has never been touched.** That it speaks pitch bend at all is
Ableton's document's claim, not a measurement -- `--selftest` has a step for it
and has never been completed here. Everything above is built so a strip that
sends something else is simply inert; nothing else depends on it.

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
| `Shift` + a button below the display | Mixer: send that slot to the next output pair |
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

## The monitor page

`--monitor-port` serves a small read-only web page that mirrors the surface:
the 64 pads in their real colours, the mode banner, the transport line, the
display's text and every lit button, updated ten times a second over
server-sent events. Off unless you ask for it.

```
python -m push2sampler --monitor-port my-song        # http://localhost:8765/
python -m push2sampler --sim --monitor-port my-song  # the LEDs, with no Push
```

For teaching (a room watching one Push), for streaming (an overlay without a
camera pointed at your hands), and for watching the LED state with no hardware
at all -- the simulator publishes the same snapshot.

Three refusals hold it up. **It never accepts a command**: every verb but `GET`
and `HEAD` is 405, and no path reads a query string, because a page that could
press a pad would be a hole in the surface reachable by anything that can open
a socket. **It never touches the app**: the render thread publishes a finished
snapshot and the request threads only read it, so there is no lock anywhere in
a program built on not having any. **It binds to loopback** unless
`--monitor-host` says otherwise, and says so loudly when you ask -- read-only
is not private, and the page carries your slot names and the shape of your song.

`/snapshot.json` is the same frame as JSON for a script, and fetching it counts
as watching. Nobody watching costs nothing: the snapshot is not built at all
unless a stream is open or the JSON was fetched in the last five seconds.

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
  everything else works unchanged. It has now been seen rendering on a real
  Push 2. Every line it draws is measured and shortened with an ellipsis rather
  than clipped at the 960th pixel, which is what it used to do.

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
| display frame header and 16-byte framing | spec, unit-tested byte for byte | **yes** -- the display renders; text lands where we put it |
| display XOR shaping mask | spec (`0xFFE7F3E7`) | **yes, after a correction** -- our low word was byte-transposed (`0xE7F3`), which showed as a gold striped background with blue text |
| display BGR565 channel order | spec, unit-tested byte for byte | not yet -- with the mask corrected the background is black, and black cannot reveal a channel-order mistake. The text hue will |
| User/Live port naming | spec | **yes** -- `Ableton Push 2 Live Port` and `Ableton Push 2 User Port`, both directions |
| Which port carries the surface | assumed User | **no** -- on a device in Live mode, input arrives only on the *Live* port |

`--selftest` fills this in. Until then, treat every row as a guess that the
program is built to be corrected on.

## The feature page

```
python tools/feature_page.py feature-grid.html
```

Builds the public feature page -- all 61 items on a 64-pad grid, coloured with
the program's own pad meanings -- from `plans.md`. Every item's code, title,
size, release and shipped state is read from the plan; the test count is read by
collecting the suite; the item the page opens on is read from `CHANGELOG.md`,
which unlike the roadmap table is in the order things happened.

It exists because the page already claimed to be generated from the plan and was
not: the numbers had been transcribed by hand, and two releases later the page
said 45 items shipped when the number was 47, with six shipped items still
coloured as unbuilt. The only thing the plan does not supply is the one-line
description of each feature -- a plan item is a spec, and a spec is not a
description -- so those live in the script, and rendering refuses if any item
lacks one.

## Tests

```
python -m pytest tests -q
```

1644 tests cover the grid/MIDI mapping, the transport and mixer (bar-accurate
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
scan, the MIDI clock PLL against a synthetic sender, importing from disk, play
modes and choke groups, master playback, swapping two slots, per-slot output
routing, swing and per-sample nudges measured in frames, onset detection against
signals with chosen onset frames, pitch to within a semitone and tempo to
within 2 BPM on material built at a known one, every Euclidean rhythm in
Toussaint's table plus maximal evenness for every length up to 64, the slice page's refusals, the monitor page's
refusals, the chance dice (uniformity, purity, and that what you hear is
bar-for-bar what gets bounced), alternate takes (cycling in order across passes,
a reproducible random, the starved-third-take correlation the salt exists for,
and every take of a cycling slot reaching the bounced file), harmonic
compatibility against material built in known keys (including the seventh chord
whose key name is measurably wrong, pinned rather than hidden, and the bass
figure that a 60 Hz analysis floor called clashing with its own key), the feature
page generator against the plan it reads, WSOLA against tones and chords built at
known frequencies (including the tail click, the vectorised search matching the
looped one bit for bit, and the stereo image surviving), the touch strip's
decoding against the document's claim, the count-in ring, the beat pulse losing
every collision, and a variation arriving on the pass it says and reaching the
bounced file, every internal doc link, and every older project format still
loading.
No hardware, PortAudio or MIDI stack is needed — only `numpy`.

## Roadmap

`plans.md` is the product plan: 61 items across foundations, new features,
nice-to-haves, innovative bets and creature comforts, with the conventions
(button allocation registry, file-contention map, definition of done) that let
several people work on it at once. **55 are shipped: every train up to v1.5,
and four of the v2.0 ideas**; each carries a status note saying what was built and
where it deviated from the plan. [`CHANGELOG.md`](CHANGELOG.md) is the release
record.

`v2.0 — Instrument` is under way: slicing, the listening assistant, generated
patterns and the timing coach have shipped; the other ideas in `plans.md` §8
and the two remaining nice-to-haves have not. The one thing this
project cannot do for itself is the human hardware pass — the display protocol
and most of the button map are still taken from Ableton's document rather than
from a device.
