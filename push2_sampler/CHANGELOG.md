# Changelog

Releases of `push2sampler`, the Push 2 sampler in this directory. Tags are
scoped (`push2sampler-v1.0`) because the repository belongs to another project
and its version namespace is left alone.

Item codes (`CC-03`, `NH-01`, …) are the work items in [`plans.md`](plans.md),
where each one carries a note on what was built and where it departed from the
plan.

---

## Unreleased

### Bars that only sometimes play (`NH-10`)

Hold **Shift** on a sample page. **Encoder 2** sets the selected bar's chance
(5–100 % in 5 % steps), **encoder 3** makes the whole sample play only on
**every Nth pass** of the loop (2–8), and **encoder 4** rerolls the project's
**dice** (0–63). A 64-bar arrangement of certainties has shown you everything it
will ever do after one pass; this is how it keeps moving without you drawing
every variation by hand.

An uncertain bar **flashes** green. The plan said pad brightness would show
probability, but brightness on a sample page already means *recorded velocity* —
a quiet hit at 100 % and a loud hit at 40 % would be the same pixel.

#### The spec's own RNG could not keep the spec's promise

The plan asked for "a per-pass seeded RNG so a pass is reproducible for bounce".
A generator advanced once per trigger is reproducible **only if you always start
from the same place**: drop in at bar 17 instead of playing from the top and
every roll after it differs, so what you bounce is not what you heard. The
dice are a pure function of position instead —

```
roll(seed, pass, bar, slot) -> a number in [0, 1)
```

— with no state to diverge. Bar 40 of pass 3 rolls the same number whether you
arrived from the top, dropped in halfway, or rendered the file offline.
Measured uniform at 24.3 % / 49.2 % / 74.7 % for p=25/50/75 over 8192 rolls.

The dice are per **project**, not per sample: a kick that drops out and a snare
that answers it have to agree about which pass this is.

#### A test found the feature missing from its own bounce

A bounce renders **linearly** — start to end, once — so it never loops, so a
pass counter incremented on the loop wrap sat at **1 for ever**. A sample set to
*every 2nd pass* was in the arrangement you heard and **absent from the output
file entirely**. You would build it, listen to it, bounce it, and part of it
would simply be gone.

Two fixes. The pass is now derived from the *position* when there is no loop to
wrap, and the render asks how long a full cycle is before it starts:
`passes_needed` is the lowest common multiple of every audible triggered
sample's `every_n`, capped at 8 passes, with the schedule tiled across it. An
8-bar song with one *every 2nd pass* sample now bounces 16 bars and the two
halves differ. Muted samples are excluded from that LCM — a muted *every 5th
pass* sample must not quintuple your file length.

There is now a test that plays the song, bounces it, and asserts the bars you
heard are bar-for-bar the bars in the file.

#### Smaller decisions

- **`Shift`+encoder 2 asks for a bar rather than picking one.** "The selected
  bar" had no referent on a page of 64 pads, so it means the bar you last
  pressed — and with none pressed the page says so rather than silently editing
  whichever bar happened to be first.
- **The floor is 5 %, not 0 %.** A 0 % bar is a bar that does not play, which
  the pad already says by being off; two different-looking ways to express one
  state is worse than a floor.
- **The status line shows nothing when nothing is uncertain.** `100% chance` on
  every bar of every ordinary sample would be four lines of noise on a
  four-line display. Likewise `· pass N` joins the transport readout only once
  a sample actually cares which pass it is.

Project format **10**; every older format still loads. 45 new tests
(`tests/test_chance.py`), 1332 in total.

### How tight you played it (`IN-08`)

Button 2 on the About page switches the grid to a **timing scatter**: each hit
as a dot, time across, distance from the beat up and down — early above the
centre line, late below, green within 10 ms, amber within 25, red beyond. The
new `coach` setting (or `--coach`) prints the same summary after every take.

**It never quantizes.** A coach that silently corrected you would be teaching
you nothing and taking your playing away at the same time.

#### Two facts, not one verdict

The first version conflated consistency and placement into `very tight: 20ms
late` — two statements wearing one label. Playing *consistently* 20 ms behind
the beat is a **groove**; being 5 ms out at random is the thing to practise. So
the report says both, separately:

```
very even (±3ms)   20ms behind the beat
8 hit(s) against beats   worst 24ms
```

#### The grid is inferred, not assumed

Measuring a sixteenth-note pattern against quarter notes reports every other
hit as 125 ms late at 120 BPM, which is not a timing error but the wrong
question. So beats, eighths and sixteenths are all tried, the one the playing
fits is kept, and it is **named** — "you played sixteenths" is itself worth
knowing. Nothing finer is offered: below a sixteenth the lines sit closer
together than human timing error and every take would fit.

**A finer grid has to earn it twice, and the second rule came from a test.**
A better spread alone was not enough: seven hits on the beat and one 90 ms late
chose a sixteenth grid — 90 ms is near a sixteenth at 120 BPM — and the report
described that 90 ms error as 35. **A coach understating your error is the one
direction it must not fail in.** So a quarter of the hits must also land on
lines the coarser grid does not have. Genuine syncopation still reads as
eighths, and there is a test for each direction.

#### And the chord the plan asked for was taken

`Shift`+`Device` is already "apply the edits to the recording for good" — a
destructive action — so an informational readout does not go there even though
the plan suggested it. The timing view lives on the page that already answers
"tell me about this take", as a second view rather than a second page.

`coach` is off by default, like the other post-take options: being told how
tight you are is useful when you asked and discouraging when you did not.

### Generate the bars instead of tapping them (`IN-03`)

`Automate` on a sample page. Five encoders — density, rotation, algorithm, a
seed, and a **length** — with the grid previewing the result **flashing green**,
so it never looks like bars that are stored, and anything it would replace in
dim red so you can see what you are about to lose. `Automate` again keeps it as
one undo step; `Session` discards.

Four algorithms: `euclid` spreads the hits as evenly as the arithmetic allows,
`every n` uses a fixed interval, `random` uses a **seed** so a pattern you
liked is findable again, and `mirror` copies another slot's bars so a snare can
answer a kick.

A pattern is a deterministic function of those five numbers, which is what lets
the preview and the commit call the *same* function — there is no second code
path to disagree with the first.

#### The fifth encoder is not in the plan, and the page is useless without it

Built exactly to spec, the density encoder spreads its hits over the whole
64-bar page. Three bars over 64 is **one hit every twenty-one bars**, which is
not a rhythm — it is a rounding error with a downbeat. A pattern is short and
repeats, so encoder 5 sets its length and it tiles across the page:

```
density 3, length 64   x....................x..........
density 3, length 8    x..x..x.x..x..x.x..x..x.x..x..x.
```

The second one is the Cuban tresillo, eight times, which is what turning a
density encoder is supposed to give you. Density and rotation are counted
*within* the length and clamp when it shrinks; `mirror` ignores it, because
tiling someone else's rhythm would be inventing a pattern rather than answering
one.

#### Getting the reference table right, and what it taught

"Matches the canonical Bjorklund output" is only a test if the canonical output
is written down, so twenty-one rhythms from Toussaint's *The Euclidean Algorithm
Generates Traditional Musical Rhythms* went into the test file — the ones that
name E(3,8) as the tresillo and E(5,8) as the cinquillo.

Eighteen matched immediately. The three that did not — E(3,4), E(5,6), E(7,8) —
are all the case of exactly one rest, where the grouping loop ends before it can
interleave and the rest lands last rather than second.

Fixing that then contradicted a twenty-first entry: E(2,3), written down from
memory as `xx.`. **The memory was wrong, not the code.** The single-rest family
puts its rest second throughout, and an independent derivation agrees on `x.x`.
Two derivations against one recollection is the right way round — and the lesson
went into the tests as *properties* rather than more examples: for every length
up to 64, the gaps between consecutive hits never differ by more than one step,
the hit count is exact, and a pattern with hits starts on one. A published
example is a spot check.

#### Four decisions the spec left open

- **Committing replaces rather than adds.** Adding would make the preview a lie
  — you would see sixteen bars and get eighteen — and replacing is what makes
  the encoders explorable, because you can turn density down and arrive back
  where you started.
- **It touches only the page you are looking at.** Patterning page A must not
  rewrite page D.
- **The pads do not edit.** A hand-made toggle would be wiped by the next
  encoder click, so a press says what the grid is for rather than losing the
  work quietly.
- **Undo restores the velocities**, which a generated pattern has no opinion
  about. Density zero is a legitimate pattern: it clears the page, undoably.

`IN-02`'s arrangement hint is now unblocked and this is the page it feeds — a
hint becomes a fifth algorithm rather than a second mechanic.

### The instrument tells you what it heard (`IN-02`)

`Layout` on a sample page opens an **About** page. The pads become a
spectrogram — time across, frequency up with the lowest at the bottom,
brightness is energy, rows spaced by octaves so a drum does not take one row
and hiss five — and the display reads back what was measured: a role, a pitch
with its note name, a tempo, how many hits and how dense, brightness, and the
energy split across three bands. All DSP: no network, no model weights, nothing
to install.

**Every reading carries a confidence, and a weak one says so.** `tone A4
(0.89)` and `tone A4 (0.21)  not sure` are different statements, and the page
prints `no tempo to read` in preference to a figure it does not believe. Its
last line — "every reading is a measurement, not a fact" — is the design, not a
disclaimer.

Button 1 accepts a suggested name (`kick`, `hat`, `bass A2`, `tone A4`) as one
undo step, and is the only thing on the page that can change the project: a
page whose job is to tell you what it thinks should not quietly act on it.

#### Five roles, not the six the plan asked for

`kick / snare / hat / bass / pad / vocal` **is not separable by band energy and
envelope**, and establishing that was the first result of prototyping: a
synthesised snare classified as a hat at 0.85 confidence, because nothing in
those features tells a noise burst with a 200 Hz body from one without — and
`pad` versus `vocal` is the same problem from the other end.

So the vocabulary is what the measurements can defend — `low drum`, `bright
drum`, `drum`, `bass`, `tone`, `noise` — and the honest cost, written into a
test as *expected* behaviour, is that a snare reads as a bright drum. A label
the instrument cannot stand behind is worse than a coarser one it can.

#### What the other five rounds found

- **Autocorrelation on a chord finds the GCD period.** A 220/277/330 chord came
  back as 55 Hz, which made every pad look like a bass.
- **White noise classified as a hat, 0.92 confident.** Band energy cannot
  separate them — both are mostly high. What does is that a struck sound decays
  and noise does not, and that feature was already being computed.
- **Periodicity is not pitch confidence.** A kick every half second is 0.95
  periodic *at the hit rate*, and duly reported a 1200 Hz "pitch" — which was
  the top of the search range.
- **Scoring harmonicity as the mean harmonic strength inverted it.** A pure
  sine has energy in harmonic 1 only, so its mean was max/8: it scored 0.13
  while white noise, all eight bands equally full, scored 0.54. Tones became
  noise and noise became tones.
- **Note names were wrong until the peak was interpolated.** Pitch landed
  within one FFT bin, but one bin at 110 Hz is 10% and a semitone is 5.95%.
  And the note-naming helper was itself an octave low — 440 Hz returned "A3" —
  caught only because the test named the notes it expected instead of checking
  that a string came back.

#### Tempo: exact, useless, or silent

Measured across 90/120/140/170 BPM at one, two and four hits per beat, material
with **crisp attacks** reads its true tempo to within 0.4 BPM. Material whose
attacks are **smeared** — a synthesised kick whose body sweeps for 150 ms —
reads 20 to 80 BPM out, and a coarser minimum onset gap does not help: measured
at 30, 60 and 100 ms it was wrong at all three. The confidence was honest
throughout, so below a threshold **no tempo is reported at all**.

Tempo also has an **unresolvable octave ambiguity** from onsets alone: 90 BPM
in eighths and 180 in quarters are the same recording, and measured, the
eighths read 180 at full confidence. Resolving it properly needs a model of
where the strong beats fall. Instead the page passes the **session's own
tempo** as a reference — the one piece of context a sampler has and a general
analyser does not.

#### The arrangement hint waits for generative patterns

The plan also asked for a hint proposing *bars* for a new sample. It is not
here on purpose: a proposal that lights a pattern and waits for a press is
exactly the mechanic `IN-03` needs, and building it twice would be the wrong
order. The propose-then-accept shape is already set by this page's name button.

#### And it corrected a doc claim

`docs/simulator.md` said "recording captures silence", twice. It does not: with
no audio device the engine feeds itself a 220 Hz stand-in tone, deliberately,
so a simulated take is not silent and every downstream page does not look
broken. The About page is what exposed it — it reported a clean A3 from a
simulated recording.

### Slice a take across the pads (`IN-01`)

The first of the `v2.0` ideas. `Convert` on a sample page turns one take into a
kit: eight bars of drumming into eight one-bar samples, or one pad per hit.

The pads are the take with every cut marked in white, the cut you last
auditioned flashing amber, and **pressing a pad plays the slice it falls in** —
you check the cuts before committing to them. Three buttons cut by **bars**, by
**beats**, or at **transients** with a sensitivity encoder; `Convert` again
writes the slices into the free slots after the source, as **one undo step**,
because "slice this into a kit" is one decision. `Shift`+`Convert` removes the
original, and that is undoable too.

A slice carries the source's gain, colour, play mode, choke group, output pair
and nudge — every slice is the same sound — and **none of its bars**, because
where the whole loop played is not where its pieces should. Each is 1 bar
whatever its real length: a slice is a hit, not a bar of music, and its true
length would have the off-grid check flag every one of them yellow.

#### Prototyping first paid for itself again

The plan's advice for the `IN-*` items was to budget a day of prototyping
inside each one, and, as with the clock's PLL, the throwaway found four things
before any of this existed — each a measurement against synthetic signals with
*chosen* onset frames, and each a bad day inside a UI:

- **Onsets landed 10–15 ms early.** The reported position was the analysis
  window's *start*, and a 1024-sample window can begin long before the hit
  inside it. The target was ±5 ms, so the first version could not have met it
  at any setting.
- **Refining on energy *level* found the previous hit's tail.** Right for a hit
  in silence, wrong the moment hits overlap: 1 of 8 matched on sustained
  material. An onset is where energy goes *up*, and a decaying tail is going
  down.
- **A held 440 Hz tone produced 59 onsets.** A sine that is not bin-centred
  leaks, the leakage wobbles frame to frame, and dividing the flux curve by its
  own maximum turns that wobble into full-scale signal. A peak-to-median
  structure gate fixes it: measured, a held tone is about 3.6 and a drum take
  over 30.
- **A global prominence floor changed nothing** on any of eleven signals, and
  was deleted rather than kept as a knob that does not turn.

A fifth thing the prototype nearly hid: at the strictest sensitivity the
sustained-material slice *count* came out exactly right, which looked like
success until the positions were checked — it was two misses cancelling two
extras. Counting is not matching.

#### What it does well, and what it does not

Measured at the default sensitivity: a 16th-note drum pattern is **31 of 31
within 0.7 ms**; the same at a fifth the level is identical; a ghost note at a
tenth the level survives at every sensitivity; two hits 50 ms apart are two
hits; and silence, white noise and a held tone all yield nothing.

**Overlapping sustained notes are approximate** — extra cuts in the decay — and
no amount of threshold work moved that, because the tail of a sustained note
genuinely looks like a small attack. **bars** and **beats** are the answer to
it: a choice of three, not a better curve. The sensitivity encoder says when it
cannot do anything, because a knob that turns silently in two of three modes
looks broken.

#### One mistake worth recording

`analysis.py` already existed — NH-08's post-take trim, normalise and fade —
and the first version of this work **overwrote it** instead of adding to it.
Thirteen tests caught it immediately, and it was recovered from git and merged
rather than rewritten. The lesson is the one the file itself is about: look at
what is there before writing over it.

---

## v1.5.0

Two release trains, finished together: **`v1.4` Plays with others** (sync,
importing, per-sample playback, output routing, the monitor page, groove, and
the hardware pass) and **`v1.5` Watch it play**. Newest first. With `v1.4`
complete, 51 of the 61 items in [`plans.md`](plans.md) are shipped and only the
`v2.0` ideas remain.

Tags for this directory are scoped (`push2sampler-v1.5`) because the repository
belongs to another project. **No tag has actually been pushed** — including
`push2sampler-v1.0`: the credentials these releases were built with can push
branches but not tag refs, so the version in `push2sampler/__init__.py` and this
file are the record.


### Swing, and laying a sample behind the beat (`NH-02`)

The last item in `v1.4`, and the one place in this project where the plan was
judged **wrong** rather than incomplete.

The spec was "the swing encoder delays every second 8th note", with a test
reading "swing does not shift bar-aligned triggers". Every trigger in this
program is bar-aligned. In a bar-addressed sequencer that second line does not
describe an edge case — it describes the feature doing nothing at all. There
are no 8th notes in the arrangement to swing.

So it shipped as the two things it was reaching for.

#### Swing, where sub-beat time actually exists

Perform mode's quantize gained `1/16 bar` and `1/8 bar`, and the **swing
encoder** (previously unbound) pushes every **odd** grid line late by 0–66 % of
the division. At an eighth-note grid the downbeats stay put and the eighths
between them move, which is what swing is. Per song, saved, one undo step.

It is a no-op at a whole beat or coarser — pushing every other beat back is not
a groove, it is a wrong tempo — and a no-op on a hit that is already late,
because making a late hit later is the opposite of quantizing. Grid lines are
counted from the start of the song, so "odd" means the same thing in bar 200 as
in bar 1.

**Both places say whether swing is reaching them**, because this knob does
nothing in most of its positions: the encoder's message names perform mode, and
the perform page reads either `swing 30%` or `(swing needs a sub-beat
quantize)`. A knob that appears to do nothing is worse than no knob.

#### Groove: a per-sample nudge

What groove means when your grid is bars. **Encoder 2** on a sample page moves
that sample 0–120 ms later than the bar line it fires on, in 5 ms steps, shown
as `+20ms`. A clap laid 20 ms behind the kick stops sounding like a machine, and
every layer can have its own amount. Format 9, one undo step, and it affects
playback and bounces because it is a property of the song rather than a
listening choice.

**Late only.** Starting *before* a bar line needs the engine to know about that
line before it arrives — lookahead across loop wraps, page boundaries and tempo
changes — for a control that is relative anyway: laying everything else back is
how you push one thing forward. At the 240 BPM clamp a bar is still a full
second, so 120 ms can never spill past its own bar line, which is what makes
the deferred start safe with no wrap handling at all. There is a test asserting
exactly that, so the day someone raises the tempo clamp it fails loudly.

**A nudge defers the whole decision, not just the audio.** The engine's pending
list now holds either a voice or a scheduled entry, and a nudged entry resolves
its play mode and choke group at the moment it *sounds*. Deciding at the bar
line would cut a retriggered voice up to 120 ms before its replacement began —
an audible hole where a retrigger should be seamless.

Recording is untouched by both halves. Swing offsets a live trigger's start, and
a nudge is applied on the way to the speakers like the edits are, so neither can
change where a take was captured.

**Per-sample `groove_enabled` was not built.** With swing confined to live
triggering, "which samples swing" is answered by which pad you are hitting, and
a flag for a feature that only applies while your finger is on the pad would be
a setting with nowhere to matter. The per-sample control that does matter is the
nudge, and it is per sample by construction.

### The surface, in a browser (`NH-12`)

`--monitor-port` serves a small read-only page mirroring the whole surface: the
64 pads in their real colours, the mode banner, the transport line, the
display's text and every lit button, ten times a second over server-sent
events. Off unless you ask for it, and `--monitor-port` on its own means 8765.

For a room watching one Push, for a stream that wants the grid without a camera
pointed at your hands, and for seeing what the LEDs would be doing with no
hardware at all — `--sim --monitor-port` publishes the same snapshot.

Three refusals hold it up:

- **It never accepts a command.** Every verb but `GET` and `HEAD` is 405, and no
  path reads a query string. A page that could press a pad would be a hole in
  the surface reachable by anything that can open a socket.
- **It never touches the app.** The render thread stores a finished snapshot
  into one attribute; the request threads only read it. No lock anywhere, in a
  program whose audio design is built on not having any — and the snapshot
  mirrors the frame `render()` actually drew rather than asking the modes to
  render again, because two renders could disagree.
- **It binds to loopback**, and `--monitor-host` warns when you ask for
  anything else. Read-only is not private: the page carries your slot names and
  the shape of your song.

Nobody watching costs nothing — with no stream open and no recent
`/snapshot.json`, the snapshot is not built at all. Failing to bind is a message
rather than a crash, and if building a snapshot ever raises, the page closes and
the instrument carries on.

Two things the first run found. **`/snapshot.json` was permanently empty**: a
script polling it never opens a stream, so nothing was ever published for it to
return; fetching it now counts as watching. And **dim pads were invisible** —
the page carries the palette's own RGB, and `#242424` on a lit screen is nothing
like a white LED at 14 % in a dark room. Rather than falsify the colour there is
a *brighten dim pads* box, off by default.

#### The docs now have a test

Writing this up meant renumbering the tutorial, which had accumulated two `Step
11b`s and two `Step 11c`s across four rounds of insertion — and renumbering
broke an in-page link that nobody would have clicked for months.

`tests/test_docs.py` now walks every markdown file in the project: every
in-page anchor resolves, every relative link resolves including its anchor, no
two headings share a slug, and the tutorial's steps are `1..n` exactly once
each. It found three more dead or ambiguous anchors on its first run, all
pre-existing, and the reference's "Not built yet" list turned out to still be
promising that there was no sync, no importing and no choke groups.

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

### Master playback mode (`NF-12`)

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

### Swap two samples (`CC-19`)

`Shift`+`Duplicate` arms a swap. The filled pads flash cyan, the pad you pick
holds white, the second press exchanges them — audio, bars, velocities, name,
colour, gain, play mode, choke group and edits. The slot *numbers* stay put,
because a slot number is identity everywhere else in this program. Picking an
empty slot second is a move, and is allowed. One undo step, and the rare command
whose undo is itself applied again.

`Duplicate` alone is unchanged. Swap is a separate chord rather than a third
state of the button: cycling copy → move → swap would turn "move" into a mode
and change a gesture that already works.

### Duplicate was silently losing four fields

Found while building the swap. `copy_slot` never carried a slot's **colour tag**,
its **overdub layers**, its **play mode** or its **choke group** — three
features, each added in a different release, and none of them updated the
copier. So `Duplicate` quietly dropped all four.

Fixed, and guarded against the next one: `Project.NOT_COPIED` names the fields a
copy deliberately skips, and a test walks every field of `Sample` asserting it is
in one list or the other.

### The mode you are in, on the big display (`CC-20`)

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

### Also in v1.3

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

### Bugs found by using it in v1.3

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

### Also in v1.2

- The settings page **scrolls** with up/down, now that there are more settings
  than there are buttons under the display.
- The project format is **version 5**, adding overdub layers and the master
  gain. Versions 1–4 load unchanged.
- `--script`, `--until-idle`, `--quiet`, `--doctor`, `--calibrate` and
  `--version` are new on the command line; the project argument now defaults to
  the last project you had open.

### Bugs found by using it in v1.2

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

### Bugs found by using it in v1.0

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
