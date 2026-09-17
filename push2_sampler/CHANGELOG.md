# Changelog

Releases of `push2sampler`, the Push 2 sampler in this directory. Tags are
scoped (`push2sampler-v1.0`) because the repository belongs to another project
and its version namespace is left alone.

Item codes (`CC-03`, `NH-01`, …) are the work items in [`plans.md`](plans.md),
where each one carries a note on what was built and where it departed from the
plan.

---

## v2.1.0 — Editing by ear

One item, `IN-09`: **trim a take without ever stopping the sound.**

### Trim by ear (`IN-09`)

`Select` in the editor. The take plays round and round; you **tap any pad** the
moment you hear where it should start; a very short loop of that spot then plays
over and over while the knobs move it. `Select` accepts it, the take plays on,
and you mark the end the same way.

One button drives all four stages, and it always means the same thing: **that's
it.** While you are hunting, that means *here is the point*; while you are
tuning, *the point is right, move on*. It is the button that opens the page as
well, so the whole gesture is one key.

**Why it exists.** `NF-03` already had trim on two encoders, in milliseconds,
next to a 64-pad picture of the take — a good way to *adjust* a trim and a poor
way to *find* one. Finding the start of a loop goes turn, listen, turn back,
listen, and between two listens the sound is gone, so you end up comparing what
you hear against a *memory* of what you heard. Looping a short window turns the
same decision into a comparison, which is a different and much easier task.

**The window is asymmetric, and that turned out to be the whole design.** A
start window runs *forward* from the point, so the sound at the loop seam is the
attack; an end window runs *back* to the point, so the sound at the seam is the
cut. Whichever edge you are judging is the one the loop puts under your ear.

**And the anti-click fade goes on the edge you are *not* judging.** This was the
build's one real finding. The first version faded both ends of the window,
which is the obvious thing to do — and it made every start sound clean whether
or not it clipped the attack, which is precisely the question the page exists to
answer. So a start window is faded at its tail and an end window at its head.
The consequence is that a start landing mid-sustain now clicks at the seam, and
that click is *information*: it is telling you where you are. There is a test
asserting the judged edge is untouched, because this is the kind of thing a
later tidy-up would "fix".

Also: encoder 1 coarse at 20 ms and encoder 2 fine at 1 ms, because one step
size cannot both cross a bar and settle the last millisecond; encoder 3 sets how
much you hear, 40 ms for a snare and 600 ms for a vocal entry; button 1 snaps to
the nearest attack, reusing the onset detection `IN-01` already had; the grid
magnifies to a few window-lengths either side of the point while tuning, because
a picture that cannot show what a knob does is a decoration. `Delete` abandons
everything.

It writes `trim_start_ms` and `trim_end_ms` — the editor's own fields — so
nothing downstream needed to learn anything, and the result is **one** undo step
covering both ends (`SetTrim`; two `SetEdit`s would have been two presses of
`Undo`).

### The audition voice

New in the engine: a **looping preview on a negative slot**, plus its playback
position published once a block.

The negative slot is the load-bearing part. `_end_voices` and
`_release_all(samples_only=True)` both skip a negative slot, so an audition is
not gated at a bar line, not renewed or released by the scheduler, and not cut
when the transport starts — it belongs to the page that asked for it and only
that page ends it. Without that, the first bar line would silence the page
mid-decision.

The published position is the other half. A page that timed the audition from a
wall clock would be wrong by however much the output stream is buffered, would
drift on every dropout, and would have no idea where a loop had wrapped — so
the frame a person tapping along is actually aiming at is the one the *callback*
last played. `Engine.audition_frame` is callback-written and UI-read, the same
single-writer arrangement `sounding` and `fired` already use.

### Four bugs a review found, all in one place

Every one was in the **audition voice's lifetime or its position**, and none
was visible to a test that drove the page on its own — they only show up when
something *else* touches the engine. That is the seam a new kind of voice
introduces, and it is where to look next time.

- **`Stop` silenced the page for good.** `_stop_now` releases every voice,
  negative slots included, and nothing put the audition back. The page went
  quiet mid-decision with its playhead frozen, so the *next tap marked frame 0*
  and wrote a wrong trim. Arming a take and voice stealing did the same. The
  negative slot was right for the scheduler and is not a general exemption;
  treating it as one was the mistake. The engine now publishes `auditioning`
  and the page heals from it.
- **Four buttons could bury the page while it was still sounding.** `Mix`,
  `Clip`, `Browse` and `Setup` open with `push_mode`, and **`push_mode` does
  not call `on_exit` on the mode it covers** — so the loop played on forever
  underneath a mixer, with no `on_tick` left to stop it. The page now claims
  every button it does not use: while it owns your ears it owns the surface.
- **Replacing an audition clicked** when the outgoing loop was within the 10 ms
  release of its buffer end: `_mix`'s looping branch required
  `releasing is None`, so a released loop took the linear path and was dropped
  at the buffer end mid-fade. A release now wraps like anything else. **This
  was not a new bug** — every looping sample released at a bar line has had
  that edge since `NF-02`.
- **The published playhead was a block ahead of the speaker**, because
  `voice.pos` was read *after* the block was mixed. So every tap landed late,
  in the same direction as reaction time, and two errors that should be
  independent added instead. It is the position at the *start* of the rendered
  block now. The device's own output buffer is still unaccounted for; that
  wants `CC-09`'s measured number and is worth doing if anyone reports tapping
  consistently late.

### Also

- `waveform.py`: `envelope` and `wave_line` had been copied into `sample_edit`
  and `slice` independently, and this would have been the third copy. Two
  copies of a function are a coincidence; three are a bug waiting to be fixed
  in only two of them.
- A bug the tests found: pressing straight through the stages with the
  transport idle marks every point at frame 0, so "the end is here, at the
  beginning" has to mean the shortest legal take rather than an empty one.
  Both points are now kept at least 10 ms apart, and there is a test for it —
  a sample of no length is something every later stage of the program would
  otherwise need an opinion about.
- Two tests written before the playhead fix had asserted the bug: they expected
  the frame published after a block to be the *end* of it. Worth noting because
  a test can pin a defect as firmly as it pins a feature.

54 new tests; 1710 in total.

---

## v2.0.1 — The display, seen

**The colour display rendered on real hardware for the first time.** A
photograph of it fixed two bugs and, between them, they are a better argument
for looking at the real thing than anything in this file.

### The XOR mask had two bytes the wrong way round (`F-08` finding 9)

The panel XORs every 32-bit word of an incoming frame with `0xFFE7F3E7`, so we
XOR with the same pattern and the two cancel. Ours was stored as two 16-bit
words, and the first was typed `0xE7F3` instead of `0xF3E7` — the low word's
bytes transposed. The result: alternate columns cancelled and the rest did not,
giving a **gold background with vertical striping and blue text**, which is
precisely what the photograph shows.

It is now derived rather than typed:

```python
XOR_MASK32 = 0xFFE7F3E7
XOR_PATTERN = np.array([XOR_MASK32 & 0xFFFF, XOR_MASK32 >> 16], dtype=np.uint16)
```

**The test that was supposed to catch this passed on any value at all.** It
asserted `words[0] == expected_pixel ^ XOR_PATTERN[0]` — the constant under test
on both sides of the equals sign, which says only that XOR is XOR. The
assertions are literal now (`^ 0xF3E7`), plus one pinning the mask against the
documented number *stated in bytes*, and one checking that a black frame shapes
back to black. Black is the useful case: `0x0000` is every channel zero, so a
channel-order mistake cannot show up there and only the mask can — which is also
how the diagnosis was made without a second photograph.

### Text ran off the right-hand edge (`F-08` finding 10)

`0 muted`, `song page  0` and `hold: audit` were all cut mid-word. Nothing
measured anything: `draw()` placed each string at x=12 and let PIL clip
whatever did not fit. Now `display.fit(text, measure, limit)` binary-searches
the longest prefix that fits with an ellipsis on it, and the banner, the text
lines and the big readout all pass through it.

`measure` is a callable rather than a font because **Pillow is optional**, and
that is the second lesson here: the whole of `draw()` sat below a
`from PIL import …`, so on a machine without Pillow — including this one — none
of it was reachable from the suite and its only test asserted that it raises
`ImportError`. Lifting the logic out into a pure function that takes its
measuring as an argument made it testable; eight new tests cover it.

### Still unconfirmed

With the mask right the background should be black, and because black cannot
reveal a channel-order mistake, **the text hue is the only remaining evidence
about whether the BGR565 packing is correct**. One more photograph settles it.

---

## v2.0.0 — Instrument

The last three items of the **`v2.0` Instrument** train, which finishes the
plan: **all 61 items in [`plans.md`](plans.md) are shipped.**

Tags for this directory are scoped (`push2sampler-v2.0`) and, as with every
release before it, **no tag has actually been pushed** — the credentials can
push branches but not tag refs, so the version in `push2sampler/__init__.py`
and this file are the record.

One thing has not changed and should be said in the release that claims to
finish the plan: **most hardware facts in this program are still Ableton's
document's claims rather than measurements.** `--selftest` has never been
completed on a device, the colour display has never been seen to render, and
the touch strip this release gives a job to has never been touched. Those are
the open items now, and no amount of software finishes them.

*(The display one is closed as of v2.0.1 — it renders, and looking at it cost
two bug fixes. The other two are still open.)*

### A variation across passes (`IN-05`)

**Shift**+**Clip** on a sample page adds extra bars a sample plays on **only
every Nth pass**. "Every fourth pass, double the hats." Encoder 1 sets how
often, encoder 2 how much, a pad adds one by hand, button 8 clears it, and
**Shift**+**Record** freezes however many passes you ask for as one file.

**It needed no engine change at all.** That is the finding. An extra trigger
that fires only on every 4th pass *is* a trigger with `NH-10`'s `every_n` of 4,
so a variation is a second set of bars scheduled with that divisor — and it
inherited reproducibility, correct bouncing and a readable grid from work
already done. `passes_needed` grew one clause; that was the whole of
`render.py`'s involvement, and `audio.py` was not touched.

**It is bars, not a rule.** The spec's "per-pass variation rules" implies
something evaluated at playback. Storing the bars instead means you can look at
what pass 4 will do, edit one by hand, and see it on a grid. A rule you have to
trust is a worse instrument than a pattern you can read.

**And it is arithmetic, not chance.** "Every 4th pass" is a divisor, so the
project's dice deliberately cannot move it — a fill arriving at unpredictable
times is not what those words say. There is a test asserting the seed changes
nothing, because given how much of this came from `NH-10` it is easy to expect
the opposite. The two still compose: a chance on a variation bar is something
that sometimes happens, on some passes.

Two smaller findings. **The fill goes in the gaps, not over the span** — the
first version spread `IN-03`'s euclidean pattern across the span the sample
occupies, which for hats on bars 1, 3, 5, 7 put the new bars on the old ones and
subtracted them away to nothing. And **the grid flashes only on the pass
immediately before**: flashing whenever the variation merely was not due made
"about to change" and "eventually" the same pixel, which is the one thing the
plan explicitly asked the display for.

Project format **13**. 44 new tests (`tests/test_living.py`).

### Fitting a take to another tempo (`NH-09`)

Button **6** on a sample page: `off`, `resample` (faster or slower, **pitch moves
with it**) or `stretch` (WSOLA — pitch held, length changed). The first press
offers whatever the material wants, because `IN-02` already listened; the button
then walks all three.

**For a drum break, `resample` is usually the right answer** — a break played
faster *is* pitched up, and that is a sound records have been made of. Measured,
a chord's spectrum survives a stretch at 0.96–1.00 similarity and a drum loop's
at 0.78–0.83, so percussion is precisely what the method is worst at.

A stretching slot is **no longer flagged off-grid**: the length is being handled,
so the yellow pad would be telling you to fix something already fixed. A change
too large to absorb still is.

#### Five things the prototype found

- **Every stretch ended in a click.** Running out of input left the tail silent:
  a 2-second tone at 1.5× finished with 615 frames of nothing and a 0.488 step
  into them, against a source whose worst sample-to-sample step is 0.063. The
  read position is clamped, so running out reuses the final frames.
- **Normalised cross-correlation was measured and rejected.** The textbook
  similarity measure ran 4× slower and scored *worse* on a chord (0.953 against
  0.957).
- **The search had to be vectorised, not tidied.** As a Python loop over
  candidates a 30-second take took 2.2 s; as one `np.correlate` call it takes
  0.33 s, bit-for-bit identical.
- **The search runs on the channel sum.** Per channel it picks different offsets
  left and right and smears the stereo image — a worse artefact than the one
  being fixed. A test asserts both channels come back identical.
- **The plan's own assertion is only valid for one note.** "The dominant
  frequency is unchanged" says nothing about a chord, whose three near-equal
  partials make `argmax` pick whichever is momentarily loudest, so each partial
  is checked separately.

And there is **no worker thread**, which is how the plan's warning is met: "the
stretching worker must not be started from the audio callback" is answered by
there being no worker. `StretchJob` is stepped from the frame loop exactly as
`BounceJob` already was, and a stretch is rebound in one assignment.

Project format **12**. 83 new tests (`tests/test_stretch.py`).

### The strip, the ring and the pulse (`IN-07`)

Three uses for hardware nothing else in this program touched.

The **count-in fills a ring round the border of the grid**, one pad per
sixteenth, arriving at the top-left corner on the downbeat — a shape you feel
rather than a number you read. The next pad shows dim before it lands. A
**pre-roll flashes the ring instead of filling it**, because nothing is being
counted during the run-up and a ring that started then would arrive a bar early.

The **rightmost column pulses on the beat in every mode**, brighter on the
downbeat, lit for about a third of a beat. It only paints pads the current page
left dark — checked by looking for `OFF` rather than by tracking claims, which
means every mode, including ones not yet written, wins the collision without
knowing the overlay exists.

The **touch strip scrubs while stopped** (bottom is bar 1, top is the last bar,
and the grid follows to the page you land on) and picks a **loop range** with
**Shift**, from your finger to the end of that page. It is refused while playing
or recording and says so.

**That needed a new engine verb, and a test found it.** Scrubbing was written as
`play(bar)` then `stop()`, and every scrub landed on bar 1 — because `stop`
rewinds to the top *by design*, being the "back to the start" gesture.
`Engine.seek` is the missing third thing: a position change on a transport that
stays stopped, refused while running or recording.

**The strip has never been touched.** That it speaks pitch bend at all is
Ableton's document's claim, not a measurement. Everything above is built so that
a strip which sends something else is simply inert; nothing else depends on it.
This item is done because the work is done, not because the hardware is
confirmed.

31 new tests (`tests/test_strip.py`).

### And the feature page caught two of its own

Marking the last release complete made the page say **"v2.0 complete, v2.0 in
progress"**, and left its headline promising "things it does, *or will*" with
nothing left to will. Both are now conditional, and both were caught by the
tests added with the generator rather than by reading the page — which is what
that generator was for.

Its spot-check on an unshipped item had to go too: it named a code and asserted
it was open, and the codes it named kept shipping. It now tests the *mechanism*
against a table written in the test, which is what has to hold whatever the plan
currently says.

---

## v1.7.0

One item, and the eight prototype rounds it took. **58 of the 61 items in
[`plans.md`](plans.md) are shipped**; `IN-05`, `IN-07` and `NH-09` remain, and
`IN-07` waits on hardware this project cannot verify for itself.

Tags for this directory are scoped (`push2sampler-v1.7`) and, as with every
release before it, **no tag has actually been pushed** — the credentials can
push branches but not tag refs, so the version in `push2sampler/__init__.py`
and this file are the record.

### Which of your loops fit together (`IN-04`)

**Scale** on a sample page brings the library grid back, coloured by how each
slot sits against *that* one: green fits, amber is a note or two apart, red
clashes, dim white has no harmony to compare. The reference flashes, and
**Shift** + a pad re-references without leaving.

Press a red pad and the page offers a transpose; **button 1** applies it. That
is the editor's own `pitch_semitones`, not a new field — "move this up two
semitones" is what the editor already does — so it is non-destructive, visible
there, and one **Undo**. Accepting twice does nothing the second time: the
suggestion comes from rotating the pitch-class content until it clashes least,
so after the shift the best rotation *is* the one you are on.

#### The plan asked for key detection, and the key is the unreliable half

Naming a *tonic* from pitch-class weights is a guess about emphasis. Measured, a
held Cmaj7 comes back **E minor** — correctly observing that those four notes
also sit in E minor — and a C triad with twelve harmonics does the same. The
chroma underneath was right on all ten signals tested.

So the colours are computed from pitch-class content directly: the fraction of
one take's energy landing on notes the other one does not use.

| Against a C major progression | Clash | Verdict |
| --- | --- | --- |
| itself | 0.028 | fits |
| A minor | 0.026 | fits |
| a Cmaj7 | 0.009 | fits |
| G major | 0.041 | fits |
| D major | 0.135 | close |
| E♭ major | 0.505 | clashes |
| F♯ major | 0.524 | clashes |

The two thresholds sit in the gaps in that table rather than having been
chosen, and a test asserts the table. A key name is still shown, because it is
what a musician wants to read — labelled `about C major (a guess, 0.90)`, and
never what a colour comes from. `test_the_key_name_is_wrong_on_a_seventh_chord`
pins the known failure instead of hiding it.

**Shared notes, not the circle of fifths.** C major and A minor are the same
seven notes yet sit three fifths apart, while C major and C minor sit zero apart
and share four. The measure had to be content overlap.

**And it is asymmetric.** A three-note pad inside a seven-note progression fits;
the progression laid over the pad introduces four notes the pad never plays.
"Does adding this to what I have selected work" is a directed question.

#### Two gates to say "that's a drum", because one was not enough

A kick reads `low drum` but its pitch-class content is peaked enough (0.077) to
pass a flatness test. White noise sometimes reads as `tone` but its content is
flat (0.008). Each gate catches a case the other misses, and a seven-note melody
at 0.106 sits close enough to the kick that separating them on flatness alone was
never going to hold.

A kick under a chord progression is the most ordinary thing in music, so drums
read `no harmony to compare` rather than a warning.

#### A 60 Hz analysis floor called a bass part wrong about its own key

At the rates this program uses, the window is more than a semitone wide down at
60 Hz, so a very low note smears into pitch classes it never played. A C–G–C
bass figure in octave 1 came back **clashing with C major** — an in-key part
called wrong, which is the one mistake this page must not make. The band starts
at **90 Hz** instead, where nothing in-key tested reads red. 130 Hz fixed
nothing further and cost an octave-3 bass its "fits", so 90 it is. The residue,
stated in the docs and held by a test: the bottom octave hedges towards `close`.

#### And a cache that lied after an undo

The first version measured each slot once and kept it. Accepting a transpose and
pressing **Undo** then left the page still holding the *transposed* reading, so
it went on saying "fits" about audio that had been put back to clashing. A page
cannot see an undo — it does not go through a mode — so the reading is keyed on
the audio rather than on the slot, which fixes the same staleness arriving from a
re-record, an overdub, or an edit applied on the editor page.

51 new tests (`tests/test_harmony.py`), 1484 in total.

---

## v1.6.0

Three items of the **`v2.0` Instrument** train, and a page that can no longer
lie about them. With `IN-06` and `NH-10` in, 57 of the 61 items in
[`plans.md`](plans.md) are shipped; `IN-04`, `IN-05`, `IN-07` and `NH-09`
remain.

Tags for this directory are scoped (`push2sampler-v1.6`) and, as with every
release before it, **no tag has actually been pushed** — the credentials can
push branches but not tag refs, so the version in `push2sampler/__init__.py`
and this file are the record.

### The feature page is generated now (`tools/feature_page.py`)

The public feature page's footer said its codes, titles, sizes and releases were
read from `plans.md`, "so this page cannot drift from it". That was not true:
they had been transcribed by hand, and two releases later the page said **45
items shipped when the number was 47**, with six shipped items still coloured as
unbuilt.

A claim a document makes about itself has to be enforced by something, so:

```
python tools/feature_page.py feature-grid.html
```

reads the roadmap table for each item's release and whether it is struck
through, reads each item's own heading for its title and size, counts the test
suite by collecting it, and takes "the most recently shipped item" from the
**changelog** rather than the roadmap table — the table groups by release and
says nothing about *when* within one, which is why the page had been opening on
the wrong item.

The one thing the plan does not supply is the one-line description of each
feature, because the plan's own prose is a specification and a specification is
not a description. Those live in the script, and `build()` refuses to render a
page if any plan item lacks one. 26 tests
(`tests/test_feature_page.py`) hold the rest, including that the template's
JavaScript braces survive `str.format`, that the only external resources are the
two allowed font hosts, and that a title containing `<` or `&` is escaped.

### Several recordings of one part, on one pad (`IN-06`)

**Shift**+**Record** on a sample page keeps the new take *beside* the existing
one instead of replacing it, up to eight. **Encoder 3** picks which you are
listening to; **encoder 4** (or **button 7**) decides how a trigger chooses:

| Mode | Chooses |
| --- | --- |
| `fixed` | always the take you selected |
| `cycle` | the next take on each **pass** of the loop — pass 1 plays take 1 |
| `random` | a take per **trigger**, from the project's dice |

`cycle` is per pass and `random` is per trigger, which is the difference between
a loop that breathes across repeats and a part that never quite repeats. Three
real performances of one snare on `random` is the difference between a sampler
and a drummer.

#### The alternates needed their own dice

Not for tidiness. "Did this bar play?" is `roll(...) < chance`, so on a 60 % bar
every trigger you hear has a roll below 0.6 — and reusing that number to index
three takes puts all of them in the first two thirds. The third take does not
sound *rarely*; it **never sounds at all**.

```
shared stream : 55.8 / 44.2 /  0.0
salted        : 33.2 / 33.3 / 33.5
```

`_TAKE_SALT` is the fix, and the measurement above is a test.

#### And a cycling slot lengthens a bounce

Exactly as `every Nth pass` does, and for the same reason: three takes on
`cycle` mean the song does not repeat until pass three, so a one-pass bounce
would write take 1 and silently discard the other two. `passes_needed` now
counts cycling take counts alongside the `every_n` divisors — an 8-bar song with
a three-take cycling slot bounces 24 bars, with a different take in each third.
`random` is deliberately **not** a divisor: it never repeats, so there is no
cycle to cover.

#### Alternates are not layers

Overdubs **sum**; alternates **replace**. Both cannot be true of one pad, so the
two never coexist: adding an alternate flattens the layer breakdown, and
**Shift**+**New** says so rather than peeling the wrong one. The audio is the
layers' sum either way, so nothing audible is lost — only the ability to undo an
overdub made before you went looking for alternates. Overdubbing a slot that has
alternates overdubs the **selected** one.

Three things follow from alternates being alternates *of one part*, each with a
test: the **edits** apply to every take, a length **repair** fits every take,
and an alternate **keeps the original's length** (the record page refuses to
change it — a take of a different length would change the arrangement).

#### Two places the plan had to give way

- **"`Sample.takes: list[Take]` instead of a single buffer"** would have
  invalidated every other field's relationship to `audio`. Shipped as the same
  shape `layers` already has: the list is empty for an ordinary slot, and when
  it is not, `audio is takes[active_take]` — one invariant, maintained in one
  method, and `set_takes` collapses a one-element list back to empty because
  "one alternate" and "no alternates" are the same state.
- **"Pads on the sample page's top row select the active take"** would have
  stolen bars 1–8 of the arrangement, which is what those pads *are*. The
  selection is encoder 3 instead. Likewise **"recording into a filled slot adds
  a take, per a setting"**: a setting that silently changes what **Record** does
  is worse than two gestures you can see — you would press **Record** expecting
  a fresh take and quietly collect eight.

Project format **11**, one WAV per take; every older format loads as a plain
single-take slot, and a slot whose take files have gone missing opens playing
the audio it always had. `AddTake`, `RemoveTake`, `SetActiveTake` and
`SetTakeMode` are each one undo step. 75 new tests
(`tests/test_takes.py`), 1407 in total.

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

*Written when it was true of everything. A Push 2 has since been attached —
see `F-08`'s findings in [`plans.md`](plans.md) for the ten corrections that
came out of it, and the v2.0.1 entry above for the two the display gave up.
Kept here because the general warning still applies to everything the findings
do not cover.*

Every hardware constant — MIDI port names, the control change behind each
button, the palette SysEx, the display protocol — comes from Ableton's *Push 2
MIDI and Display Interface* document rather than from observation, except where
a finding says otherwise.

```
python -m push2sampler --selftest
```

walks a real device and writes `hardware-report.json`. The "Needs correcting"
table at the top of the markdown it produces is the whole fix list, and it is
the one thing this project cannot produce for itself. **It has still never been
completed on a device.**
