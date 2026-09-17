# Reference

Every mode, control, colour, setting and file. For a guided path through the
same material, read [Getting started](getting-started.md) instead.

- [Concepts](#concepts)
- [Controls that work everywhere](#controls-that-work-everywhere)
- [Banks and pages](#banks-and-pages)
- [Modes](#modes) — [Library](#sample-library) · [Record](#record-mode) ·
  [Sample page](#sample-page) · [Master playback](#master-playback-mode) ·
  [Swap](#swapping-two-samples) · [Harmony](#harmony-page) ·
  [Living song](#living-song-page) ·
  [Slice](#slice-page) ·
  [About](#about-page) · [Pattern](#pattern-page) ·
  [Editor](#sample-editor) · [Trim by ear](#trim-by-ear) ·
  [Perform](#perform-mode) · [Song](#song-page) · [Mixer](#mixer-page) ·
  [Output routing](#output-routing) · [Browser](#project-browser) ·
  [Import](#import-browser) · [Naming](#naming-and-colouring-a-slot) ·
  [Settings](#settings-page)
- [The touch strip and the count-in ring](#the-touch-strip-and-the-count-in-ring)
- [Clock](#clock--playing-with-other-gear)
- [The display](#the-display) · [The monitor page](#the-monitor-page)
- [Scenes](#scenes)
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

**Slot.** One of **256** sample slots. A slot holds one recorded take. The grid
shows 64 at a time — one **bank**.

**Take.** The audio in a slot. Recorded as an exact number of bars at the tempo
of the moment, and it remembers that tempo.

**Song.** Up to **256 bars**, as four **pages** of 64 played one after another —
about eight minutes. Every sample has its own set of bars it plays on; they
overlap freely, including with themselves.

**Trigger.** One sample playing on one bar. Optionally carries a velocity.

**Edits.** Trim, fades, pitch, reverse and normalise, stored beside a take and
applied on the way to the speakers. The recording is never changed until you
explicitly apply them.

**Scene.** One of eight stored snapshots of the arrangement — what is audible
and where it plays — for comparing two versions or switching live.

**Mode.** What the 64 pads currently mean. The Library is home; the Sample page
replaces it; the Editor, Perform, Song, Mixer, Browser, Naming and Settings pages
open *over* whatever you were doing and close back to it.

---

## Banks and pages

There are 256 slots and 256 bars, and 64 pads. So the grid is a **window**, and
two controls move it:

| Control | Moves |
| --- | --- |
| **Page ◀** / **Page ▶** | The **bank**: which 64 slots the library, perform and mixer pages show |
| **Shift**+**Page ◀/▶** | The **song page**: which 64 bars a sample page shows |

Banks are labelled A–D and so are pages. The display always names both.

**A bank is a view, not a song section.** Everything in every bank plays,
always — switching bank changes what you can *reach*, never what you hear. The
grid flashes for a moment when you switch, so you always know you moved.

**Pages are consecutive.** Page A is bars 1–64, page B is 65–128, and the song
runs through them in order. What the loop covers is separate, and **Repeat**
cycles it:

| Loop scope | What happens |
| --- | --- |
| `page` (default) | Loops the page you are working on — the rest of the song waits |
| `song` | Loops all four pages |
| `off` | Plays to the end of the song and stops |

**Play** starts at the loop's start, so with a page loop it starts on the page
you are on. The transport line names the scope, and the big readout puts the
page letter next to the bar: `BAR 129C`.

An older project, from before pages existed, opens as **one** page.

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
| **Clip** | Open or close the [Song page](#song-page) |
| **Mix** | Open or close the [Mixer page](#mixer-page) |
| **Browse** | Open or close the [Project browser](#project-browser) |
| **Page ◀/▶** | Change [bank](#banks-and-pages) |
| **Shift**+**Page ◀/▶** | Change [song page](#banks-and-pages) |
| **Setup** | Open or close the [Settings page](#settings-page) |
| **Shift**+**Setup** | Save the project now |
| **Metronome** | Click on/off |
| **Shift**+**Metronome** | Cycle monitoring: off → auto → on |
| **Repeat** | Cycle the [loop scope](#banks-and-pages): page → song → off |
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
| Buttons **below** the display | The eight [scenes](#scenes) |
| **Shift** + a button below | Store the arrangement in that scene |

The display names the bank, how many slots are filled in it and in all four, how
many are muted, and names
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
| **Scale** | [Which other loops fit with this one](#harmony-page) |
| **Shift**+**Clip** | [Vary it across passes](#living-song-page) |
| **Shift**+**Delete** | Delete this sample and return to the library |
| **▲** / **▼** | Jump to the previous / next filled slot |
| Track encoder 1 | This sample's gain (0–2) |
| Track encoder 2 | [Nudge](#groove--laying-a-sample-back-behind-the-beat) this sample behind the beat |
| Track encoder 3 | Which [alternate take](#alternate-takes) plays |
| Track encoder 4 | How a trigger [chooses a take](#alternate-takes): fixed / cycle / random |
| **Shift**+encoder 2 | [Chance](#chance--bars-that-only-sometimes-play) for the selected bar |
| **Shift**+encoder 3 | Play only on [every Nth pass](#chance--bars-that-only-sometimes-play) |
| **Shift**+encoder 4 | [Reroll the dice](#chance--bars-that-only-sometimes-play) for the whole project |
| **Shift**+**Record** | Record [another take](#alternate-takes) beside this one |
| First button **below** the display | [Fit an off-grid take](#off-grid-takes) to its bars |
| Button **6** below the display | [What happens at another tempo](#fitting-another-tempo): off / resample / stretch |
| Button **7** below the display | Cycle the take mode; **Shift** removes the selected take |

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

#### Play modes — how a sample ends

A sample used to play to the end of its recording no matter what else happened,
which is right for a drum hit and wrong for almost everything sustained: a
4-bar pad bled straight over the chord that replaced it. The **play mode** is
one of four, on buttons **2–5** below the display, lit to show which is set:

| Mode | Ends when |
| --- | --- |
| `one shot` | the recording runs out. The original behaviour, and still right for a hit or a loop that exactly fills its bars |
| `loop` | a bar arrives that this sample is *not* triggered on. One take can then hold a whole section from a single trigger |
| `gate` | the bar it started in ends, however long the audio is |
| `retrig` | a new trigger on this slot arrives — it cuts the previous voice instead of layering on top of it |

Three details that follow from where the decision is made:

- **Ends happen at bar lines, never by polling.** The engine already splits
  every block at each bar line, so a gate's release starts on the exact frame
  of the line whatever the audio block size is. Nothing drifts with the buffer.
- **Ends run before starts.** At a bar line, voices that finish there are
  released *before* anything new is scheduled onto it — otherwise a retrigger
  or a choke would cut the voice it had just started.
- **A renewed loop is one voice, not two.** Triggering a looping sample on
  consecutive bars does not stack a second copy; the existing voice keeps
  running and the new trigger simply renews it.

A loop's seam keeps the 3 ms head and tail fades every take has, so looping
gives a hair of a dip at the loop point rather than the click a hard splice
would give. Same trade as everywhere else the program declicks.

#### Choke groups

Button **8** below the display cycles this sample's **choke group**: off, then
1 through 8, then off again. Samples in the same group cut each other — the way
a closed hat silences an open one.

A sample never chokes **itself**. A sample's relationship with its own voices is
what the play mode is for, and conflating the two would make `one shot` inside a
group behave like `retrig` with no way to say otherwise.

Both settings are per sample, saved with the project (format 7), and each change
is one undo step. Pressing the mode that is already set says so and does not
consume an undo step.

#### Groove — laying a sample back behind the beat

**Encoder 2** on a sample page moves that sample **0–120 ms later** than the bar
line it is triggered on, in 5 ms steps, and the second status line says
`+20ms` when it is not zero. This is what groove means when your grid is bars:
a clap that lands a hair behind the kick stops sounding like a machine.

| | |
| --- | --- |
| Per sample | so one layer can lay back while the rest stay square |
| Late only | 0 to +120 ms, never negative |
| Frame-accurate | the engine splits the block at the nudged start, so it does not drift with the buffer size |
| Saved with the project | format 9, and every older format loads straight |
| One undo step | consecutive encoder clicks coalesce, like gain and tempo |

**Why late only.** A bar line is the earliest moment the engine knows about, so
starting *before* one would mean looking a bar ahead — across loop wraps, page
boundaries and tempo changes — for a control that is relative anyway. Laying
everything **else** back is how you push one thing forward, and it needs no
lookahead at all. At the fastest tempo the program allows (240 BPM) a bar is
still a full second, so 120 ms can never spill past the bar line it belongs to.

**The nudge defers the whole decision, not just the audio.** Whether a `loop`
renews, whether a `retrig` cuts, whether a choke group fires are questions about
the moment a sample *sounds*, so they are answered then — deciding at the bar
line would cut a retriggered voice up to 120 ms before its replacement began,
which is an audible hole where a retrigger should be seamless.

Recording is untouched: a nudge is applied on the way to the speakers, like
[the edits](#sample-editor), so it never changes where a take was captured.

#### Chance — bars that only sometimes play

A 64-bar arrangement built from bars that either play or do not is exact, and
after four passes you have heard everything it will ever do. Chance makes a bar
*likely* instead of certain, so the song moves without you drawing every
variation by hand.

Three controls, all on a sample page, all needing **Shift** so the unshifted
encoders keep doing what they did:

| Control | Sets | Range |
| --- | --- | --- |
| **Shift**+encoder 2 | how likely the **selected bar** is to play | 5–100% in 5% steps |
| **Shift**+encoder 3 | play only on **every Nth pass** of the loop | every pass, or every 2–8 |
| **Shift**+encoder 4 | the project's **dice** — which variation you get | 0–63 |

**Chance is per bar; passes are per sample.** "This clap lands 70% of the time"
is a question about one bar. "This whole fill arrives every other time round" is
a question about the take. Putting each on the control that matches its scope
means neither needs a second control to undo it.

**Press a bar first.** Shift+encoder 2 edits the bar you last pressed and says
`press a bar first, then Shift + encoder 2` if you have not pressed one. It
does not pick a bar for you: silently editing whichever bar happened to be
first is worse than asking.

**A maybe-bar flashes.** On the grid a certain bar is a steady green and an
uncertain one **blinks**. It cannot be a dimmer green instead, because
brightness on a sample page already means recorded velocity — a quiet hit at
100% and a loud hit at 40% would look identical.

##### Same dice, same song

The dice are a **pure function of where you are**, not a running generator:

```
roll(seed, pass, bar, slot) -> a number in [0, 1)
```

Nothing is remembered between rolls. That is the whole of the reproducibility
claim, and a stateful generator could not make it. A generator advanced once
per trigger gives bar 40 a different answer depending on how many triggers came
before it, so starting playback at bar 17 instead of bar 1 would change
everything after — and **what you bounced would not be what you heard**. With a
pure function, bar 40 of pass 3 rolls the same number whether you arrived there
from the top, dropped in halfway, or rendered the file offline.

So the dice are per **project**, not per sample: the point of a seed is that the
whole arrangement varies *together* and repeatably. It is editable at all
because otherwise the seed would be 0 for ever and a probabilistic song would
have exactly one variation in it.

| | |
| --- | --- |
| The pass counter | starts at 1 on **Play**, advances on each loop wrap, and is derived from the position when there is no loop to wrap |
| The status line | shows `2 maybe-bar(s)   every 2 passes   dice 7`, and nothing at all when nothing is uncertain |
| The transport readout | grows `· pass 3` only once something actually uses passes |
| Saved with the project | format 10, and every older format loads straight |
| One undo step each | chance, passes and the dice are all undoable |

##### What a bounce had to learn

A [bounce](#bouncing) renders the song **linearly** — start to end, once. It
therefore never wraps, so when passes were counted only on a wrap, a bounce sat
on pass 1 for ever and a sample set to *every 2nd pass* was **absent from the
output file entirely**. You would build an arrangement, listen to it, bounce
it, and part of it would be gone.

The render now asks how long a full cycle is before it starts:
`passes_needed` is the **lowest common multiple** of every audible triggered
sample's `every_n`, capped at 8 passes, and the schedule is tiled across them.
An 8-bar song with one *every 2nd pass* sample bounces 16 bars, and both halves
differ. Nothing set to a pass cycle means one pass and the file is the length it
always was.

Muted samples are excluded from the calculation, the same way they are excluded
from the mix — a muted *every 5th pass* sample cannot stretch your file to five
times its length.

#### Alternate takes

One pad can hold several recordings of the same part. **Shift**+**Record** on a
sample page keeps the new take *beside* the old one instead of replacing it, up
to eight. Then a trigger picks one.

| Control | Does |
| --- | --- |
| **Shift**+**Record** | Record another take of this part, beside the existing ones |
| Encoder 3 | Which take you are listening to — selecting it installs it, so pads and **Play** both give you the one you see |
| Encoder 4 | How a trigger chooses: `fixed` / `cycle` / `random` |
| Button **7** below the display | Cycles the same three modes |
| **Shift**+button **7** | Remove the selected take |

| Mode | Chooses |
| --- | --- |
| `fixed` | always the take you selected |
| `cycle` | the next take on each **pass** of the loop — pass 1 plays take 1 |
| `random` | a take per **trigger**, from the project's [dice](#chance--bars-that-only-sometimes-play) |

**`cycle` is per pass and `random` is per trigger**, and that is the difference
worth knowing. A slot triggered on eight bars plays *one* take for the whole
pass under `cycle` — which is what "this loop breathes across repeats" means —
and eight possibly-different takes under `random`, which is what stops a
repeated hit sounding machine-stamped.

`random` uses the same dice as chance, and so is just as reproducible: the same
seed gives the same takes in the same places, every time and in a bounce.

##### Two takes are not two layers

[Overdubbing](#overdubbing) **sums**; alternates **replace**. So the two never
coexist: adding an alternate flattens the layer breakdown, and **Shift**+**New**
on a slot with alternates says so rather than peeling the wrong one. The audio
is the layers' sum either way, so nothing you can hear is lost — only the
ability to undo an overdub you made before you went looking for alternates.

Overdubbing a slot that *has* alternates overdubs the **selected** one, which is
the take you are listening to.

Three things that follow from alternates being alternates *of one part*:

- **The edits apply to all of them.** A trim that is right for take 1 is right
  for take 2, and folding the edits into one take only would make switching
  takes change the trim.
- **So does a [repair](#off-grid-takes).** A part that is two bars long is two
  bars long in all of its takes; leaving the others the wrong length would make
  switching takes re-break the song.
- **An alternate keeps the original's length.** The record page will not let you
  change it, because a take of a different length is not an alternate — it would
  change the arrangement.

**Record** still replaces, and only **Shift**+**Record** adds. The plan put this
behind a setting; a setting that silently changes what **Record** does is worse
than two gestures you can see, because you would press **Record** expecting a
fresh take and quietly collect eight.

##### A cycling slot lengthens a bounce

For the same reason [`every Nth pass`](#what-a-bounce-had-to-learn) does: three
takes on `cycle` mean the song does not repeat until pass three, so a one-pass
bounce would write take 1 and silently discard the other two. `passes_needed`
counts cycling take counts alongside the `every_n` divisors, so an 8-bar song
with a three-take cycling slot bounces 24 bars.

`random` is **not** a divisor — it never repeats, so there is no cycle to cover,
and one pass of it is as representative as any other.

Saved with the project (format 10 → **11**), one WAV per take, and every older
format still loads as a plain single-take slot. If a slot's take files have gone
missing it opens as a single-take slot playing the audio it always had: losing
the breakdown must not lose the take.

#### Fitting another tempo

A take remembers the tempo it was cut at, so changing the song's tempo leaves it
the wrong length — a two-bar loop cut at 240 BPM is 1.83 bars at 220. Button
**6** below the display decides what to do about it, per sample:

| Mode | Does |
| --- | --- |
| `off` | nothing. The take keeps its own length and the library flags it yellow |
| `resample` | plays it faster or slower. Instant, and **the pitch moves with it** |
| `stretch` | keeps the pitch and changes the length. Costs a pass over the audio |

**For a drum break, `resample` is usually the right answer.** A break played
faster *is* pitched up, and that is a sound records have been made of — while
stretching a transient only smears it. The first press offers whichever mode the
material wants, because the program already knows
[what it heard](#about-page): percussion gets `resample`, a bass line or a
pitched part gets `stretch`. The button then walks all three.

Measured: a chord's spectrum survives a stretch at 0.96–1.00 similarity, a drum
loop's at 0.78–0.83. That is not a preference, it is what the method is worst at.

**A stretching slot is no longer flagged off-grid**, because the length is being
handled — the yellow pad and the repair offer would be telling you to fix
something already fixed. A tempo change too large to absorb (past 4× either way)
*is* still flagged, because then it genuinely is not handled.

Nothing here runs while audio is playing back. A stretch is computed a slot at a
time between frames, the button flashes while that happens, and the take plays
at its old length until the new one is finished — playing something beats playing
nothing. A 30-second take takes about a third of a second.

Saved with the project (format 10 → **12**); every older format opens with
stretching off, which is what it always did.

### Living song page

**Shift**+**Clip** on a sample page opens the one thing this program has that a
grid of certainties cannot do: a **variation**. Extra bars this sample plays on
only every Nth pass.

"Every fourth pass, double the hats" is what it is for.

| Control | Does |
| --- | --- |
| Encoder 1 | how often the variation plays — every 2 to 8 passes |
| Encoder 2 | how much it adds — extra bars, spread through the gaps |
| Encoder 3 | how many passes **Shift**+**Record** freezes |
| any pad | add or remove one bar by hand |
| Button **8** below the display | clear the variation |
| **Shift**+**Record** | freeze that many passes as audio |
| **Clip** / **Session** | leave |

| Pad | Means |
| --- | --- |
| green | plays every pass — the arrangement |
| amber | part of the variation, and **this** is the pass it plays on |
| flashing amber | it plays on the **next** pass |
| dim blue | part of the variation, waiting its turn |
| white | the playhead |

**It is bars, not a rule.** A rule evaluated at playback would be a thing you
have to trust; a set of bars is a thing you can look at, edit one of by hand, and
see on a grid. The status line says which pass is next and how far off the
change is: `pass 2   the extra bars play in 2 passes`.

**And it is arithmetic, not chance.** "Every 4th pass" is a divisor, so the
project's [dice](#chance--bars-that-only-sometimes-play) deliberately cannot move
it — rolling for it would make the fill arrive at unpredictable times, which is
not what the words say. Chance and a variation compose freely: a maybe-bar
inside a variation is a bar that sometimes plays, on some passes.

A variation lengthens a bounce the same way `every Nth pass` does, so the fill
is always in the file. **Shift**+**Record** here is the exception: it renders the
number of passes *you* asked for, because "how long before the song repeats" and
"give me four times round" are different questions.

Saved with the project (format **13**); every older format opens without one.

### Master playback mode

**Shift**+**Session** opens the page whose only job is playback. It is the
library grid — all 64 slots exactly where they always are, honouring the
current bank — and **each pad flashes as its sample fires**.

Every other page is for editing. The library shows what *exists*, a sample page
shows where *one take* plays, the song page shows the arrangement as a heat map.
None of them is the view you want while the whole thing runs and you are
listening; for that you had to pick one sample's page and watch a single row of
the truth.

| Control | Does |
| --- | --- |
| any filled pad | audition it |
| **Play** / **Stop** | as everywhere else |
| **Page ◀** / **Page ▶** | another bank of 64 |
| **Session**, **Note**, **Left** | leave, back to the library |

| Pad | Means |
| --- | --- |
| the slot's own colour | filled and resting |
| dim green | filled but muted — it never flashes |
| white, then mid white | it just fired |
| off | empty slot |

**Delete**, **Mute** and **Duplicate** are deliberately inert here. This is the
one page where you are listening rather than deciding, so a stray press should
cost nothing; pressing one says so rather than arming anything.

The display counts **how many slots fired in the bar you are in** — a number
that tells you whether a section is as busy as it feels — and how many are
sounding right now.

#### Why the flash marks the attack

`Engine.sounding` is true for as long as a voice is alive, so a four-bar pad is
sounding for four bars. A view that lit its pad for all of them would say
nothing about the music. The engine therefore publishes a second set — the
slots that *started* a voice in the last block — and that is what this page
reads. A four-bar pad flashes once.

Every attack goes through one place in the engine, so a sample fired **by hand**
in perform mode, or auditioned from the library, flashes too.

The flash lasts about a fifth of a second, in two steps. At 120 BPM an eighth
note is 250 ms, so it reads as one hit per note rather than smearing into the
next. It is white rather than a brighter version of the slot's own colour
because the palette has brightness steps for white and green only — the eight
user colours have no dim variants — so white is the one flash that reads the
same against every resting colour.

### Swapping two samples

**Shift**+**Duplicate** arms a swap; the filled pads flash cyan. Press one pad
and it holds white — "this one" — then press the pad it should change places
with. Pressing the same pad twice cancels, as does **Shift**+**Duplicate**
again.

`Duplicate` on its own is unchanged: it still copies a slot to the next empty
one, with **Shift** on the *pad* press moving it instead. Swap is a separate
chord rather than a third state of the button, because cycling
copy → move → swap would turn "move" into a mode and change a gesture that
already works.

Everything moves: the audio, the bars it plays on, its velocities, name,
colour, gain, play mode, choke group and edits. The slot **numbers** stay put —
a slot number is identity everywhere else in this program, from the schedule to
the WAV filename to every undo entry, so the *contents* move and each sample's
own record of which slot it is in is rewritten to match.

Picking an empty slot second is allowed, and is a move: the gesture is the same
to the hands, so refusing it would only be surprising. The whole thing is one
**Undo** — and it is the rare command whose undo is simply itself applied again.

A sounding voice keeps its own buffer, so swapping while the song plays cuts
nothing; the next bar line picks up the new arrangement.

### Harmony page

**Scale** opens the library grid coloured by how each slot's notes sit against
**one reference slot** — the sample whose page you pressed it from. From the
library it opens against the first filled slot.

| Pad | Means |
| --- | --- |
| flashing white/green | the reference: everything is compared to this |
| green | fits — its notes sit inside the reference's |
| amber | close — a note or two apart |
| red | clashes |
| dim white | no harmony to compare (a drum, or nothing with a key in it) |
| off | empty slot |

| Control | Does |
| --- | --- |
| any filled pad | audition it, and read how it sits |
| **Shift** + a pad | compare everything against *that* slot instead |
| Button **1** below the display | apply the suggested transpose to the picked slot |
| **Scale** / **Session** | leave |

**The transpose is the editor's own pitch edit.** "Move this loop up two
semitones" is a thing [the editor](#sample-editor) already does, so accepting a
suggestion sets `pitch_semitones` rather than inventing a second way to say the
same thing. It is non-destructive, visible on the editor page, and one **Undo**.

Accepting twice does nothing the second time. The suggestion is found by
rotating the pitch-class content until it clashes least, so after the shift the
best rotation *is* the one you are on — the page says `already fits - nothing to
move` rather than drifting another semitone.

Ties go to the **smaller** move. A C# triad against C major was first told to go
up four semitones, which does land it on F and does fit; down one is just as
good and is what a hand expects.

#### What it measures, and what it does not

The page answers "do these two clash", and that lives in **pitch-class
content** — not in a key. Measured against material built in known keys:

| Against a C major progression | Clash | Verdict |
| --- | --- | --- |
| itself | 0.028 | fits |
| A minor | 0.026 | fits |
| a C triad | 0.010 | fits |
| a Cmaj7 | 0.009 | fits |
| G major (the dominant) | 0.041 | fits |
| D major | 0.135 | close |
| E♭ major | 0.505 | clashes |
| F♯ major (the tritone) | 0.524 | clashes |

The number is the fraction of one take's energy landing on notes the other one
does not use. The two thresholds sit in the gaps in that table rather than
having been chosen.

**It is asymmetric, on purpose.** "Does adding this to what I have selected
work" is a directed question: a three-note pad inside a seven-note progression
fits, while the progression laid over the pad introduces four notes the pad
never plays.

**A key name is shown, and labelled a guess.** Naming a *tonic* from pitch-class
weights is a guess about emphasis, and it is measurably the weak part: a held
Cmaj7 comes back `E minor` — correctly noting those four notes also sit in E
minor — and a C triad with twelve harmonics does the same. The chroma
underneath was right on all ten signals tested, so the colours never come from
the name. The display says `about C major (a guess, 0.90)`.

**Drums are not coloured.** A kick under a chord progression is the most
ordinary thing in music, so `no harmony to compare` is the answer rather than a
warning. Deciding that needs **two** independent gates, and each catches a case
the other misses: the role gate rejects a kick, whose pitch-class content is
peaked enough to look tonal (0.077); the flatness gate rejects a chromatic run
(0.001) and white noise that happened to read as a tone (0.008).

#### The bottom octave

A bass part below about C2 is judged on its **harmonics**, and can read `close`
where it should read `fits`. At the session rates this program uses, the
analysis window is more than a semitone wide down at 60 Hz, so a very low note
smears into pitch classes it never played.

That is not a detail: with the analysis band starting at 60 Hz, a C–G–C bass
figure in octave 1 read as **clashing with its own key**, which is the one
mistake this page must not make. The band starts at 90 Hz instead, and no
in-key material tested reads red. The residue is that the lowest octave hedges
towards `close`, which is a hedge and not a warning.

### Slice page

**Convert** from a sample page. One take becomes a kit: eight bars of drumming
into eight one-bar samples, or one pad per hit.

The pads are the take, drawn the way [the editor](#sample-editor) draws it, with
every cut marked in **white** — and the cut you last auditioned flashing amber,
so "which one did I just hear" has an answer. **Pressing a pad plays the slice
it falls in**, which is how you check a cut before committing to it.

| Control | Action |
| --- | --- |
| Any pad | Hear the slice under it |
| Button 1 below the display | Cut by **bars** — one slice per bar of the take |
| Button 2 | Cut by **beats** |
| Button 3 | Cut at **transients** — where the hits actually are |
| Track encoder 1 | Transient sensitivity, 0.00–1.00 |
| **Convert** | Write the slices, and go back |
| **Shift**+**Convert** | Write them **and** remove the original |
| **Session**, **Note**, **◀** | Leave, having changed nothing |

**bars** and **beats** divide evenly, which is the right answer for anything
played to the grid. **transients** is the right answer for a take whose rhythm
is not the grid's. A one-bar take opens on **beats**, because there is nothing
to cut a single bar into by bars.

Slices go to the free slots **after** the source and wrap round, so a kit lands
next to the take it came from rather than at slot 1. Not enough free slots is a
refusal with the numbers in it:

```
8 slices need 8 empty slots and there are 3 - delete something, or slice into fewer
```

**The whole conversion is one undo step.** "Slice this into a kit" is one
decision, and taking it back a pad at a time would be sixteen presses to undo
one.

#### What a slice carries

| Carried from the source | Not carried |
| --- | --- |
| Gain, colour, play mode, choke group, output pair, [nudge](#groove--laying-a-sample-back-behind-the-beat) | The bars it played on |

Those first things describe how the *sound* behaves and every slice is the same
sound. The arrangement is not: where the source played is not where its pieces
play, and a kit that arrived already arranged would be a mess to undo by hand.
Slices are named after the source — `kit/1`, `kit/2` — and each is **1 bar**
whatever its real length, because a slice is a hit rather than a bar of music;
giving each its true length would have the [off-grid](#off-grid-takes) check
flag all sixteen of them yellow.

**The original is kept** unless you hold **Shift**. Slicing is the one gesture
here that turns one take into many, and the instinct to tidy up after it is
wrong: the slices share the source's audio, the source is what you would
re-slice from at another sensitivity, and the pad you pressed **Convert** on is
where your hands expect it to still be.

#### How transient detection works, and where it does not

A spectral-flux novelty curve with an adaptive threshold, in numpy only — no
scientific stack to install. Measured against signals whose onsets were chosen
rather than guessed:

| Material | Result |
| --- | --- |
| A 16th-note drum pattern | 31 of 31, worst error **0.7 ms** |
| The same at a fifth the level | 31 of 31, worst error 0.7 ms |
| Two hits 50 ms apart | Both, separately |
| A ghost note at a tenth the level | Found, at every sensitivity |
| Silence, white noise, a held tone | **Nothing**, which is the right answer |
| Overlapping sustained notes | Approximate: a few extra cuts in the decay |

That last row is the honest limit, and no amount of threshold work moved it:
the tail of a sustained note genuinely looks like a small attack. Turning
sensitivity down helps — and **bars** and **beats** exist for material that
transients suit badly. A choice of three is the answer to this, not a better
curve.

Two hits closer than **30 ms** are treated as one: below that a flam is one
attack, and two slices would be wrong. At most **64** slices are made, so a
take full of transients cannot outrun the grid; when there are more, the
loudest are kept **in time order**, because a kit built from the first 64 of
200 hits would stop halfway through the take.

The sensitivity encoder says so when it cannot do anything — it applies to
transient slicing only, and a knob that turns silently in two of three modes
would look broken.

### Pattern page

**Automate** from a sample page. Instead of tapping sixteen bars in, turn an
encoder until the rhythm is right.

The grid is a **live preview, flashing green**, so it never looks like bars
that are actually stored — and bars this would *replace* show in dim red, so
you can see what you are about to lose rather than discovering it afterwards.

| Control | Action |
| --- | --- |
| Track encoder 1 | **Density** — how many bars of the pattern play |
| Track encoder 2 | **Rotation** — the same shape, starting somewhere else |
| Track encoder 3 | **Algorithm** — euclid / every n / random / mirror |
| Track encoder 4 | **Seed** for `random`, or the **slot** to copy for `mirror` |
| Track encoder 5 | **Length** — how long the pattern is before it repeats |
| Button 1 below the display | Also cycles the algorithm |
| **Automate** | Keep it, as one undo step |
| **Session**, **Note**, **◀** | Discard it |

| Algorithm | What it does |
| --- | --- |
| `euclid` | Spreads the hits as evenly as the arithmetic allows — [Bjorklund's algorithm](#euclidean-rhythms), which is where most traditional rhythms come from |
| `every n` | A fixed interval. The plain answer, and often the right one |
| `random` | A **seeded** choice, so a pattern you liked is findable again |
| `mirror` | Copies another slot's bars, so a snare can answer a kick |

A pattern is a **deterministic function of those five numbers.** The preview
and the commit call the same function, so what you see is exactly what gets
stored — there is no second code path to disagree with the first — and a
pattern you liked is reproducible from five numbers rather than from luck.

#### Length is the control that makes it musical

Spread three bars evenly over a whole 64-bar page and you get one hit every
twenty-one bars, which is not a rhythm. **A pattern is short and repeats**:
three over eight, eight times, is the tresillo. So encoder 5 sets the pattern's
length and it tiles across the page.

```
density 3, length 64   x....................x..........
density 3, length 8    x..x..x.x..x..x.x..x..x.x..x..x.
```

Density and rotation are both counted *within* the length, so shortening it
clamps them — a density of 12 inside a length of 4 would silently mean "every
bar" and make the encoder look broken. `mirror` ignores the length entirely:
tiling someone else's rhythm would be inventing a pattern rather than
answering one.

#### What committing does

It **replaces** this sample's bars on the page you are looking at. Adding to
them would make the preview a lie — you would see sixteen bars and get
eighteen — and replacing is what makes the encoders explorable, because you
can turn density back down and arrive where you started.

It touches only **this page's 64 bars**: patterning page A must not rewrite
page D. One **Undo** puts back everything it replaced, **including the
velocities**, which a generated pattern has no opinion about. Density zero is
a legitimate pattern: it clears the page, undoably.

The pads do not edit here. A hand-made toggle inside a generated pattern would
be wiped by the next encoder click, so pressing a pad says what the grid is
for instead of silently losing the work.

#### Euclidean rhythms

`euclid` is Bjorklund's algorithm, and its outputs are checked against the
table in Toussaint's *The Euclidean Algorithm Generates Traditional Musical
Rhythms* — E(3,8) is the Cuban **tresillo**, E(5,8) the **cinquillo**, E(2,5) a
Persian *khafif-e-ramal*. Beyond those twenty-one examples the tests assert the
property they are examples *of*, for every length up to 64: the gaps between
consecutive hits never differ by more than one step, there are exactly as many
hits as asked for, and a pattern with any hits starts on one.

### About page

**Layout** from a sample page. The instrument has heard everything you played,
so it can tell you something about it — entirely from DSP, with no network, no
model weights and nothing to install.

The pads are a **spectrogram**: columns are time, rows are frequency with the
lowest at the bottom, brightness is energy. It is the one view of a take no
other page gives — [the editor](#sample-editor) shows the envelope and this
shows what is inside it. A kick is a bright blob along the bottom, a hat a
stripe across the top, a held note a horizontal line. Rows are spaced by
**octaves**, not linearly: a linear split would put every drum in the bottom
row and give five rows to hiss nobody can hear.

| Control | Action |
| --- | --- |
| Any pad | Hear the take |
| Button 1 below the display | **Accept the suggested name** |
| **Layout**, **Session**, **Note**, **◀** | Close |

Accepting the name is the **only** thing this page can change. A page whose job
is to tell you what it thinks should not quietly act on it.

#### What it reads, and how sure it is

```
ABOUT slot 1 kick   4.00s  2 bar(s)
sounds like: low drum (0.97)
about 120 BPM (0.98)   8 hit(s)   2.0/s
dark (123 Hz)   low 97% mid 3% high 1%   peak 0.97
button 1: name it 'kick'   pad: hear it
every reading is a measurement, not a fact - Layout: close
```

**Every reading carries a confidence, and low confidence is shown rather than
rounded away.** `tone A4 (0.89)` and `tone A4 (0.21)  not sure` are different
statements, and the page prefers saying `no tempo to read` to printing a figure
it does not believe. That last line is not decoration: a guess stated
confidently is worse than no guess.

| Reading | What it is |
| --- | --- |
| **sounds like** | One of `low drum`, `bright drum`, `drum`, `bass`, `tone`, `noise` |
| **pitch** | The fundamental and its note name, for pitched takes only |
| **tempo** | Read from the gaps between hits; absent when it cannot be trusted |
| **hits** | How many attacks, and how many per second |
| **brightness** | `dark` / `warm` / `bright` / `very bright`, and the spectral centroid |
| **bands** | How the energy splits below 200 Hz, 200–2000, and above |

#### Five roles, not six

The plan asked for `kick / snare / hat / bass / pad / vocal`. **Those six are
not separable by these measurements**, and finding that out was the first
result of prototyping: a synthesised snare classified as a hat at 0.85
confidence, because nothing in band energy or envelope tells a noise burst with
a 200 Hz body from one without — and `pad` versus `vocal` is the same problem.

So the vocabulary is what the measurements can stand behind, and the honest
cost is that **a snare comes back as `bright drum`.** A label the instrument
cannot defend would be worse than a coarser one it can.

| Told apart by | Which roles |
| --- | --- |
| Envelope — does it decay? | drums vs. everything sustained |
| Band energy | `low drum` vs. `bright drum` |
| Harmonic structure | `bass` / `tone` vs. `noise` |
| Pitch | `bass` (below 160 Hz) vs. `tone` |

#### Where the numbers stop

- **Pitch** is good to within 2% on a clear note — inside a semitone (5.95%),
  which is what naming one requires. Below about **60 Hz** there is nothing a
  short take can resolve, and the page says no pitch rather than guessing. A
  **chord** reads as a `tone` at low confidence, correctly: a chord is not one
  note, so only a third of its energy lies on any one harmonic series.
- **Tempo** is exact to a fraction of a BPM on material with crisp attacks and
  useless on material whose attacks are smeared, so below a confidence
  threshold it is not reported at all. It also has an **unresolvable octave
  ambiguity** — 90 BPM in eighths and 180 BPM in quarters are the same
  recording — which the page resolves using the one thing a sampler knows and
  a general analyser does not: [the session's own tempo](#tapping-a-tempo).
- **Names** are generic on purpose. The measurements know the sound is a low
  struck thing, not that it is your 808. A pitched take gets its note, because
  the note is the one specific thing actually measured.

#### Timing — how tight you played it

**Button 2** switches the grid between the spectrogram and the **timing
scatter**: each hit as a dot, time across, distance from the beat up and down.
Above the centre line is **early**, below is **late**, and the centre line is
always drawn, because a scatter with no axis cannot be read.

| Dot | How far off |
| --- | --- |
| Green | Within 10 ms |
| Amber | Within 25 ms |
| Red | Further |

The display reports **two separate facts**, and keeping them apart is the
point:

```
very even (±3ms)   20ms behind the beat
8 hit(s) against beats   worst 24ms   green within 10ms, amber 25ms
```

**Evenness** is how consistent you are. **Placement** is where you sit relative
to the beat. An earlier version conflated them into one verdict and produced
"very tight: 20ms late", which is two statements wearing one label — and the
more interesting one is that playing *consistently* 20 ms behind the beat is a
groove, not a mistake, while being 5 ms out at random is the thing to work on.

**The grid is inferred, not assumed.** Measuring a sixteenth-note pattern
against quarter notes would report every other hit as 125 ms late at 120 BPM,
which is not a timing error but the wrong question — so the report tries beats,
eighths and sixteenths and keeps the one your playing actually fits, and says
which. A finer grid has to earn it twice: it must reduce the spread
appreciably **and** a quarter of the hits must land on lines the coarser grid
does not have. Without that second rule, seven hits on the beat and one 90 ms
late chose a sixteenth grid and reported the 90 ms error as 35 — and a coach
understating your error is the one direction it must not fail in.

Nothing finer than a sixteenth is offered: below that the lines sit closer
together than human timing error and every take would "fit".

**It never quantizes.** A coach that silently corrected you would be teaching
you nothing and taking your playing away at the same time. To actually move a
take, use [auto-trim](#post-take-processing) or the
[editor](#sample-editor).

Turn the **`coach`** setting on (the settings page, or `--coach`) and this
summary appears after every take. Off by default: being told how tight you are
is useful when you asked and discouraging when you did not.

#### Not built: arrangement hints

The plan also asked for a hint proposing *bars* for a new sample from what
already occupies them. It is not here, deliberately: a proposal that lights a
pattern and waits for a press is the same mechanic
[generative patterns](#not-built-yet) will need, and building it twice — once
for hints and once for patterns — would be the wrong order. It waits for that
item, and the propose-then-accept shape is already set by this page's name
button.

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
| **Select** | Open [trim by ear](#trim-by-ear) — find the trim by listening instead |
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

### Trim by ear

**Select** from the editor. The encoders above are a good way to *adjust* a
trim and a poor way to *find* one, because between two listens the sound is
gone and you end up comparing what you hear against a memory of what you heard.
This page never stops the sound.

**Select** drives the whole thing, and it always means the same thing: **that's
it.** While you are hunting, that means *here is the point*; while you are
tuning, it means *the point is right, move on*.

| Stage | What you hear | **Select** does | A pad does | The knobs do |
| --- | --- | --- | --- | --- |
| 1 · find the start | the whole take, looping | marks the start **here** | marks the start **here** | nothing |
| 2 · tune the start | a short loop **from** the start | accepts it → 3 | nothing | move the point |
| 3 · find the end | from the start onward, looping | marks the end **here** | marks the end **here** | nothing |
| 4 · tune the end | a short loop **up to** the end | accepts it, and you are done | nothing | move the point |

So the whole gesture is: listen, tap when you hear the start, turn the knob
until it is right, **Select**, listen on, tap when you hear the end, turn,
**Select**.

**Any pad means "now".** Not the pad under the playhead — you are tapping in
time with what you hear, not aiming — so any of the 64 will do. Use the pads
rather than **Select** for the marking if you can: your hand is already over
the grid and a pad is a percussion surface, so it is more accurate. **Select**
does the same job for anyone who would rather drive it from one key.

| Control | Action |
| --- | --- |
| **Select** | That's it — mark the point, or accept it |
| Any pad | Mark the point (hunting stages only) |
| Encoder 1 | Coarse, 20 ms a click (tuning stages) |
| Encoder 2 | Fine, 1 ms a click (tuning stages) |
| Encoder 3 | How much you hear: 40–1000 ms, 200 ms to start with |
| Button 1 | Snap the point to the nearest attack |
| Button 8 | Put the point back to the take's own edge |
| **Delete** | Give up; the take is exactly as it was |
| **Device**, **Session**, **Note**, **◀** | Also give up |

The two short loops are deliberately **not** the same shape. A start loop runs
*forward* from the point, so the sound at the loop seam is the **attack**; an
end loop runs *back* to the point, so the sound at the seam is the **cut**.
Whichever edge you are judging is the one put under your ear.

The fade that stops the seam clicking goes on the **other** edge — the one you
are not judging. That matters: a start faded in sounds clean whether or not it
clips the attack, which is the one thing this page must never do. So if a start
lands in the middle of a sustained note you will hear a click at the seam. That
is the truth, and it is telling you where you are.

While you are tuning, **the grid magnifies**: instead of the whole take it
shows about four loop-lengths either side of the point, so the picture is at the
resolution the knobs are working at.

It writes the same `trim in` and `trim out` the editor's own encoders write, so
nothing here is a separate kind of trim — the editor's picture, **Shift**+**Device**
and everything downstream carry on unchanged. The result is **one** undo step
covering both ends. Opening the page a second time picks up the trim already
there rather than starting over.

### Perform mode

**Shift**+**Play**. The loop starts and the pads fire samples instead of
navigating.

| Control | Action |
| --- | --- |
| A filled pad | Fire that sample, quantised to the next grid line |
| **Record** | Toggle *writing*: fired pads are also written into the arrangement |
| **Fixed Length** | Cycle quantize: 1 bar → off → 1/16 → 1/8 → 1/4 → 1/2 → 1 bar |
| **Delete** | Arm erasing: bars are wiped as the playhead crosses them |
| **Session**, **Note**, **◀** | Leave |
| **Shift**+**Play** | Also leaves |

Quantize defaults to **1 bar**, the coarsest, so your first press lands on a
downbeat rather than wherever your hand was. With quantize off, a pad sounds
immediately. A pad pressed while the transport is stopped always sounds
immediately.

The divisions are **fractions of a bar**, which read as note values in 4/4:
`1/16 bar` is a sixteenth, `1/8 bar` an eighth, `1/4 bar` a quarter note.

With **Record** on, a fired pad is written at the bar where it *sounded*, not
where you pressed — so a late hit still lands on the bar. Firing a pad on a bar
that already plays that sample changes nothing and says so.

Erasing starts at the **next** bar line rather than the bar already playing: the
current bar is mostly behind you, and wiping it would feel like erasing the past.
Erasing removes that bar for **every** sample, as one undo step.

If the sample has velocity response on ([Accent](#sample-page)), how hard you hit
the pad sets the level, and a written trigger keeps that velocity.

#### Swing

The **swing encoder** (second from the left, above the display) pushes every
**odd** grid line late, by 0–66 % of the division. At a `1/8 bar` quantize the
downbeats stay put and the eighths between them move, which is what swing is.

**Swing reaches only what you play by hand, here.** Every trigger in the
arrangement is on a bar line, and swinging bar lines is not swing — so swing
needs a quantize **finer than a beat** (`1/16 bar` or `1/8 bar`) to do anything
at all. Rather than leave you turning a knob with no effect, both the encoder
and this page's first line say so:

```
PERFORM A  playing  quantize 1 bar  (swing needs a sub-beat quantize)
PERFORM A  playing  quantize 1/8 bar  swing 30%
```

It is a no-op at a whole beat or coarser (pushing every other beat back is not
a groove, it is a wrong tempo) and a no-op on an already-late hit, because
making a late hit later is the opposite of quantizing. Grid lines are counted
from the start of the song, so "odd" means the same thing in bar 200 as in bar 1.

Swing is saved with the project and is one undo step. To move a sample in the
**arrangement**, use [groove](#groove--laying-a-sample-back-behind-the-beat) on
its own page instead — that is the bar-grid equivalent, and it is the one that
affects playback and bounces.

### Song page

**Clip**. The whole arrangement at once, which no other page shows: every other
page is one sample's bars or one bank's slots.

It cannot be one pad per bar per slot — that is 4096 cells on 64 pads — so the
overview is a **heat map**. Each pad is a cell of **8 bars by 8 slots**: columns
are bars left to right, rows are slots top to bottom, within the current page and
bank.

| Colour | Triggers in that cell |
| --- | --- |
| Off | none |
| Dim blue | 1 |
| Blue | 2–3 |
| Amber | 4–7 |
| White | 8 or more |

The column the playhead is in is brightened **one rung**, rather than drawn over,
so the density stays readable underneath it.

**Press a pad to zoom in.** The grid becomes that cell: each pad is now one bar
of one slot, and pressing it toggles exactly what the sample page would.

| Control | Action |
| --- | --- |
| A pad (overview) | Zoom into that cell |
| A pad (zoomed) | Toggle one slot on one bar |
| **Clip** | Zoomed: back to the overview. Overview: leave |
| **Page ◀/▶** (zoomed) | The next cell along |
| **Delete** (zoomed) | Clear the whole cell |
| **Session**, **Note**, **◀** | Leave |

In the zoom, a row with nothing in its slot is dark, alternate rows carry a faint
tint so you can count them, and triggers show in [the slot's own
colour](#naming-and-colouring-a-slot).

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
| **Shift** + a button below | Send that slot to the next [output pair](#output-routing) |
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

### Output routing

By default every slot goes to the **main mix**, which is output channels 1/2 —
the first pair, and only the first pair, however many channels the device has.

**Shift** + a button below the display walks that slot through the pairs your
interface actually has: `main` → `3/4` → `5/6` → `7/8` → back to `main`. It
stops at what is really open rather than offering pairs that would silently fall
back, so on a two-channel device the press says so instead:

```
only 2 output channels - nowhere to route slot 5 to
```

The mixer's third status line lists whatever is routed, and nothing when nothing
is — a row reading `main main main main` is noise on a four-line display.

```
out 3:3/4  7:5/6
```

A routed slot leaves the main mix entirely. That is the point: send a kick to
3/4 and a pair of headphones fed from those channels hears the kick alone, while
1/2 carries the rest. Three consequences follow, and all three are deliberate:

| | |
| --- | --- |
| It is **not** in a [bounce](#bouncing) | A bounce is what comes out of the main outputs, and a cue pair is by definition not that |
| It **is** in its own [stem](#bouncing) | A stem is one slot's audio; where it was listening does not change what it played |
| It is **not** in the main meters' sum | The per-slot meters still show it — it is playing, just not there |

A pair the device turns out not to have (a project made on an eight-output
interface, opened on a laptop) **falls back to the main mix** rather than into
silence, the same way [the click channel](#the-click) does. The mixer marks it
with a `!` and says plainly what happened:

```
out 3:5/6!
! this device has 2 channel(s), so those fall back to the main mix
```

Routing is per slot, saved with the project, and on the undo stack. It needs
`--out-channels` to be set high enough for the pairs to exist — that count is
[a command-line setting](#settings), because a stream's channel count is fixed
when the stream opens.

### Project browser

**Browse**. The songs on disk, as pads — so switching song does not mean quitting
to a terminal. The root is the folder the open project lives in.

| Colour | Meaning |
| --- | --- |
| Green | A project with samples in it |
| Dim white | A project directory with none |
| Flashing amber/white | The one highlighted |
| Dim amber | The project you have open |

| Control | Action |
| --- | --- |
| A pad | Highlight that project |
| The same pad again | Open it |
| **▲** / **▼** | Highlight the previous / next |
| Button 1 below the display | Open the highlighted project |
| Button 2 | Start a new project, named from the date and a word |
| Button 3 | Duplicate the highlighted project, audio and all |
| Button 5 | **Hold** to delete it |
| **Browse**, **Session**, **Note**, **◀** | Leave |

The display names the highlighted project, its tempo, how many samples it has,
how many pages, and when it last changed.

**Opening a project saves the one you were in first** — switching songs must
never be the thing that loses one — stops the transport, and swaps the project
with **the audio stream untouched**, so the change is silent rather than a gap.
The undo journal is cleared on the way, because it described the other song.

Deleting is the one action in this program that undo cannot reach, which is why
it needs the button held for a second rather than a press. You cannot delete the
project you have open.

Only each `project.json` is read, never the audio, so a directory of sixty-four
songs draws instantly. A project whose manifest will not parse is still listed,
honestly showing zero samples.

### Import browser

**Shift**+**Browse** opens a file browser over the **samples root**: the
`samples_root` setting when there is one, otherwise the folder your project
lives in — which is usually where the takes you want to reuse already are.
`--samples-root DIR` sets it for a run.

Folders are white, audio files blue, and the highlighted entry is bright. One
press highlights and describes; a second press opens the folder or imports the
file. Nothing is highlighted when you arrive, so the first press on any pad —
including the top-left one — can never import something by accident.

| Control | Does |
| --- | --- |
| a pad | highlight it |
| the same pad again | open the folder, or import the file |
| **Up** / **Down** | previous / next entry |
| **button 1** | import / open the highlighted entry |
| **button 2** | up one folder |
| **button 3** | back to the samples root |
| **button 5** | your home folder |
| **Browse**, **Session**, **Note**, **Left** | leave |

Hidden entries and non-audio files are not shown — a samples folder full of
`.DS_Store` is not something worth looking at on 64 pads. More than 64 entries
in one folder shows the first 64 and says how many it left out.

#### What an import does, and what it refuses to do

The file is read, **resampled** to the session rate if it differs, and given the
nearest whole number of bars at the session tempo — at least one, so a short hit
is a one-bar slot rather than a zero-bar one. It claims the session's tempo as
its own, so the off-grid check compares it against *this* session rather than a
tempo it never had.

It is **not stretched**. A 3.5-bar file stays 3.5 bars long and is flagged
off-grid by exactly the machinery that flags a take recorded at another tempo,
with the same repair on **button 1** of its sample page. Silently time-stretching
someone's audio to fit a grid it was never on is the kind of helpfulness nobody
asks for, and it would be unrecoverable.

It never lands **over** a take: the target is the first empty slot, and if every
slot is full it says so. `--import FILE --slot N` is how you choose a particular
one, and it refuses rather than overwriting.

The whole import is one **Undo** step, and redo puts back the very sample the
import built rather than re-reading the file — which would be slower and would
fail mid-redo if the file had moved.

#### Formats

`.wav` always, through the standard library. `.flac`, `.aiff`, `.aif`, `.ogg`,
`.oga`, `.opus`, `.mp3`, `.w64` and `.caf` only when `soundfile` is installed.
Without it, those pads are still listed but highlighting one says
`needs soundfile for .flac files -- pip install soundfile` instead of failing
when you press it. A corrupt file, or an empty one, gives a sentence too.

#### From the command line

```
python -m push2sampler --import kick.wav my-song
python -m push2sampler --import pad.wav --slot 12 my-song
```

Needs no hardware and no audio device. It prints the slot, the bar count and the
tempo, saves the project, and says so when the file lands off grid.

### Naming and colouring a slot

**Select** on a sample page. There is no text entry on a Push 2 and there should
not be: picking `kick` from a list is two presses where spelling it on a grid is
six.

- **The top seven rows of pads are words** — seven categories at once, eight
  words each. Press one to name the slot.
- **The bottom row is eight colours.** Press one to tag the slot; press the same
  one again to clear it.
- **The buttons below the display** jump to a category; **▲**/**▼** scroll them.

The categories are drums, perc, bass, keys, lead, voice, fx and field.

A second `kick` names itself `kick 2`, because two slots with the same name is
not a name. Both the name and the colour are one undo step each, and both are
saved with the project.

Colours are additive: an untagged slot is green, exactly as before. Muted, armed
and sounding states still win over a tag, because those are what you need to see
while playing.

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

Page 2 — [post-take processing](#post-take-processing), and the library dimmer:

| | | |
| --- | --- | --- |
| auto trim | auto normalise | auto fade |
| dim library | | |

Page 3 — [the click](#the-click):

| | | |
| --- | --- | --- |
| pre-roll | click sound | click volume |
| click on rec only | click output | |

**Setup**, **Session**, **Note**, **◀** or **Stop** closes it.

Choosing a device that will not open is not fatal: the previous device is kept
and the display says what went wrong.

---

## The touch strip and the count-in ring

Two pieces of the hardware nobody uses.

**The count-in fills a ring round the edge of the grid**, one pad per sixteenth,
so a four-beat count-in is sixteen pads arriving at the top-left corner on the
downbeat. You can feel it coming out of the corner of your eye; a number you
have to read. The next pad shows dim before it lands, and a **pre-roll** flashes
the whole ring instead of filling it — nothing is being counted yet, and a ring
that started during the run-up would arrive a bar early.

**The rightmost column pulses on the beat, in every mode**, as an ambient
metronome: the bottom pad on beat 1 (brighter, so the downbeat reads), then
upward. It is lit for about a third of a beat — a pulse, not a lamp — and it
**only ever paints pads the current page left dark**. A page that means something
by that column keeps it. A metronome you can see out of the corner of your eye is
worth having; one that lies about the arrangement is not.

**The touch strip scrubs the transport while stopped.** The bottom of the strip
is bar 1 and the top is the last bar; the grid follows to the page you land on.
It is refused while playing or recording and says so — a finger brushing the
strip mid-phrase must not move the playhead. **Shift** and the strip instead
picks a loop range: from where your finger is to the end of that page, in one
gesture.

<a id="the-strip-is-unverified"></a>

**One thing to know: the strip has never been touched.** That it speaks MIDI
pitch bend at all comes from Ableton's *Push 2 MIDI and Display Interface*
document, not from a device — `--selftest` has a step for it and has never been
completed here. Everything above is built so that a strip which turns out to
send something else is simply inert: nothing else in the program depends on it.
If the strip does nothing on your Push, that is the most likely reason, and
[the probe](#command-line) is how it gets fixed.

## Clock — playing with other gear

By default the sampler runs on its own tempo. `clock_role` in the settings, or
`--clock` for one run, changes who is in charge:

| Role | What it does |
| --- | --- |
| `internal` | our own tempo. The default, and everything before this existed |
| `midi_slave` | follow MIDI clock, start/stop/continue and song position from another device |
| `midi_master` | send 24 ppqn clock, start/stop, and a song position on each seek |
| `link` | Ableton Link — see the caveat below |

`--clock-port NAME` picks which MIDI port, by any part of its name. It is a
**separate port from the Push's own**: the surface and the clock have nothing to
do with each other, and a device sending clock is rarely the device you are
pressing.

```
python -m push2sampler --clock midi_slave --clock-port "Elektron" my-song
python -m push2sampler --clock midi_master --clock-port "IAC" my-song
```

The transport line gains `SYNC` when the loop is locked and `sync?` while it is
still chasing, and a line below says what the clock is doing —
`clock slave locked 120.4 BPM (+2 mbeat)`.

### How following works, and why it works that way

Two decisions matter more than the rest.

**The playhead is never moved to correct phase.** Jumping the transport to line
up with an incoming clock would stutter, and could move it *backwards* — which
cuts every sounding voice. Instead only the tempo is nudged, and the position
converges on its own. The engine needed no changes for this at all: the slave
only ever calls the same tempo setter a hand does.

**Phase is compared at tick arrival.** When clock tick *n* arrives, the sender
is at exactly `n / 24` beats. Comparing on our own 30 Hz refresh instead would
mean reading a position quantised to 1/24 beat — 21 ms at 120 BPM, and so
never better than that. The MIDI thread therefore timestamps the tick and
samples the transport right then, and the arithmetic happens afterwards.

Measured against a synthetic sender over 32 bars: **0.3 ms** at a steady 120
BPM, 0.3 ms after starting at the wrong tempo, 0.2 ms after a 2:1 cold start,
about 1.3 ms through a ±3 % tempo wobble, and under 6 ms with a millisecond of
arrival jitter. It never moves the music backwards in any of those.

Three refusals worth knowing:

- **A tick gap under 2 ms is not a tempo**, it is a broken sender, and it is
  refused rather than clamped — a clamped 1250 BPM would look like a
  deliberate 240 and claim a lock that is not real.
- **A silence longer than a second unlocks** rather than freewheeling on a
  stale estimate, and the next tick re-seeds the tempo outright instead of
  crawling toward it.
- **The tempo is still refused mid-take.** A take's length is frames measured
  at the tempo it was cut at, so an incoming tempo change during a recording
  is ignored, exactly as a hand-turned one is.

### Sending clock

`midi_master` emits from a thread that watches the **engine's own position**
rather than the wall clock, so what we send follows the audio device exactly
and cannot drift from what is being heard. A backwards jump — a loop wrap or a
seek — re-anchors rather than emitting a catch-up burst, because a burst
arrives at whatever is following as a tempo spike.

### What has not been verified

`midi_slave` and `midi_master` have been tested only against a **synthetic**
clock, in the same sense that the surface constants were once only from a
document: no real drum machine, modular or DAW has been on the other end of
them. The numbers above are real measurements of real code, but of code driven
by a simulation.

**Ableton Link is a seam, not a feature.** `LinkClock` has the lazy import and
the absent-safe fallback, and says `link unavailable` when the library is
missing — which it has been in every environment this program has ever run in.
Nothing behind that import has been exercised. Choosing `link` will tell you so
and leave you on the internal clock rather than pretending.

## The display

Three regions, each answering a different question.

| Where | What it says |
| --- | --- |
| **top, large** | the page you are on — `LIBRARY A`, `SLOT 7 "kick"`, `RECORD 4 BARS` |
| middle | what this page does, and its current state |
| **bottom, large** | where the music is: `BAR 17A · 3 · 124 BPM` |

The banner is the same words in the same place every time, which is what makes
it glanceable; it comes from the mode itself rather than from parsing its first
status line, because a status line is prose that changes with state.

A page layered **over** another says so: `SETUP  over SLOT 7`. Perform mode,
the settings page and the editor all open on top of whatever you were doing,
and forgetting that is the single most common confusion about this program —
leaving **Shift**+**Record** on a sample page re-records the take, while in the
library it bounces the song.

The banner turns **red** while a take is recording and **amber** while something
destructive is armed. Colour is emphasis only: the words already say the same
thing, because a display this program has never seen render on real hardware is
a bad place to put information that exists nowhere else.

Vertical space is the real constraint — 160 pixels — so the banner costs one of
the text lines. A machine with no scalable font gets the banner at body size
rather than not at all.

## The monitor page

`--monitor-port` serves a small web page that mirrors the surface: the 64 pads
in their real colours, the banner, the transport line, the display's text and
every lit button. Off unless you ask for it.

```
python -m push2sampler --monitor-port my-song      # http://localhost:8765/
python -m push2sampler --monitor-port 9000 my-song
```

It was built for three things the device cannot do: **teaching** (a room
watching one Push), **streaming** (an overlay without a camera pointed at your
hands), and **debugging the LEDs with no hardware at all** — the
[simulator](simulator.md) publishes the same snapshot, so `--sim
--monitor-port` gives you the grid in a browser while you type commands in a
terminal.

Three rules hold it up, and each is a refusal:

| Rule | How |
| --- | --- |
| **It never accepts a command** | Every verb but `GET` and `HEAD` is refused with 405, and no path reads a query string |
| **It never touches the instrument** | The render thread publishes a finished snapshot; the request threads only read it. No locks, in a program whose audio design is built on not having any |
| **It stays on this machine** | Bound to `127.0.0.1` unless `--monitor-host` says otherwise, and saying otherwise prints a warning |

A page that could press a pad would be a hole in the surface reachable by
anything that can open a socket. A page that can only watch is safe to leave
running — but **read-only is not private**: the page carries your slot names,
your tempo and the shape of your song, so `--monitor-host 0.0.0.0` puts all of
that on the network.

| Path | Serves |
| --- | --- |
| `/` | The page. One file, no build step, no CDN — it works with no network |
| `/events` | Server-sent events: one message per new frame |
| `/snapshot.json` | The latest frame, for a script. Fetching it counts as watching |

**Nobody watching costs nothing.** The app skips building a snapshot entirely
unless a stream is open or the JSON was fetched in the last five seconds, so a
monitor left enabled and unopened is one attribute read per frame. Published at
ten frames a second rather than the LEDs' thirty: the page is not a meter.

The pads carry the palette's own RGB, which means a dim state looks dim on a
lit screen in a way an LED does not in a dark room. Rather than falsify the
colour there is a **brighten dim pads** box on the page: off by default, so what
you see is what the Push is told.

Failing to bind is a message and nothing more — an instrument that would not
start because port 8765 was busy would be an absurd thing to have built. If
building a snapshot ever raises, the page is closed and the instrument carries
on.

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
| `pre_roll_bars` | 0 | 0–8 | yes |
| `click_sound` | `sine` | sine / tick / cowbell | yes |
| `click_gain` | 1.0 | 0–2 | yes |
| `click_when_recording` | off | on/off | yes |
| `click_channel` | none | 0–14, or none for the main mix | yes |
| `samples_root` | `""` | a folder path; empty means beside the project | no |
| `clock_role` | `internal` | internal / midi_slave / midi_master / link | no |
| `clock_port` | `""` | part of a MIDI port name | no |
| `dim_library` | on | on/off | yes |
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

## Scenes

Eight snapshots of the arrangement, on the row of buttons **below** the display
in the library. **Shift** + a button stores; a plain press recalls. A lit button
means that scene has something in it.

A scene holds **what is audible and where it plays** — the mute state and the
trigger set of every filled slot. It does **not** hold the audio, the gain, the
edits or the layers: those belong to the *take* rather than to the arrangement,
and a scene that silently re-pitched your samples would be a trap.

Use them to compare two versions of a chorus, or to switch between them while
playing. A recall is one undo step, so an A/B can always be walked back.

Two details that follow from how the engine works:

- **A recall never cuts a sounding voice.** Triggers are only read at bar lines
  and a voice already playing owns its buffer, so a recall mid-bar takes effect
  at the next bar and nothing is chopped.
- **A slot recorded since the snapshot is left alone**, not emptied. A scene is a
  variation, not a rollback of the whole library.

Scenes are saved with the project.

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

### The click

| Setting | What it does |
| --- | --- |
| `count_in_beats` | Beats of count-in before a take. 0 starts on the next downbeat |
| `pre_roll_bars` | Bars of the **song** played before the count-in, so you arrive in the groove rather than starting cold. Only the count-in beats click |
| `click_sound` | `sine` (soft), `tick` (a short burst that cuts through a mix), `cowbell` (audible against anything) |
| `click_gain` | How loud it is |
| `click_when_recording` | Click only during a take, silent while you play |
| `click_channel` | The first of a **separate output pair** for the click |

A separate click output is the one worth knowing about. Set it to a channel your
interface actually has — on a four-output box, channel 3 — and the main mix,
along with anything you bounce from it, is **click-free**, while a pair of
headphones fed from those channels still hears it. A channel the device does not
have falls back to the main mix rather than routing the click into silence.

### Post-take processing

Three settings, all **off** by default, applied to a take the moment it finishes.
A take should be what you played until you ask for something else.

| Setting | What it does |
| --- | --- |
| `auto_trim` | Finds where the take audibly begins and slides it onto the grid |
| `auto_normalize` | Scales the take so its loudest sample sits at −1 dBFS |
| `auto_fade` | 2 ms fade at both ends, so a looped take does not click |
| `coach` | After every take, say how tight it was — see [Timing](#timing--how-tight-you-played-it). Purely informational |

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
  project.json             tempo, page count, master gain, the eight scenes,
                           and per slot: length in bars, the bars it plays on,
                           how hard each was played, mute, gain, colour, the
                           edits, and the tempo/rate it was recorded at
  samples/slot_000.wav     one file per filled slot, named by slot number
  samples/slot_000_L1.wav  one per overdub layer, when a take has any
  bounces/*.wav            whatever you have bounced
```

Saved a couple of seconds after any change (see `autosave_delay_s`) and on exit.
`project.json` is written atomically — a crash mid-save cannot corrupt it. Audio
files are only rewritten when the audio itself changed.

The format version is **6**, and every older version loads: a version-1 take
assumes it was recorded at the project's tempo, and versions 2–5 simply lack
velocities, edits, overdub layers, and pages/scenes/colours respectively. A
project from before pages opens as **one** page.

A trigger past the last page, or a slot outside the 256, is **dropped on load
with a warning on the display** — it could never play, and keeping it would be a
silent surprise later.

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

A bounce renders **to the last bar anything plays on**, not to the nominal 256.
With four pages available and most songs using one, rendering the full length
would put minutes of silence on the end of every export.

Both the on-device bounce and `--bounce` keep the tails of samples that overrun
the last bar (up to 20 seconds).

**A bounce is what you are hearing out of the main outputs**, so two kinds of
slot are absent from it:

| | In the mix? | In its stem? |
| --- | --- | --- |
| A muted slot | No | No — the file is written, and it is silence |
| A slot on [another output pair](#output-routing) | No | **Yes** |
| Everything else | Yes | Yes |

Muting is a statement about whether a take belongs in the song at all, so it
silences the stem too — a stem of something you have muted is a stem of
nothing. Routing is a statement about *where you are listening*, which does not
change what the take played, so the stem is the full audio. Un-mute a slot, or
set it back to `main`, to hear it in the next bounce.

With nothing muted and nothing routed, the stems sum back to the mix exactly.

### The settings file

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
| `--coach` | Report how tight each take was — see [Timing](#timing--how-tight-you-played-it) |
| `--monitor-port [N]` | Serve [the monitor page](#the-monitor-page); default 8765, `0` off |
| `--monitor-host HOST` | What it binds to; loopback by default |
| `--list-ports` | List MIDI ports and exit |
| `--list-devices` | List audio devices and exit |

`--monitor` and `--monitor-port` are unrelated despite the names: the first is
*audio* monitoring (hearing your input), the second is the web page.

---

## Not built yet

So you do not go looking:

- **No global LED brightness.** Blank pads can be dimmed, but the Push's own
  brightness SysEx is not sent: its command byte is unverified, and a knob that
  might do something else is worse than no knob.
- **No renaming a project**; duplicate it and the copy is named for you.
- **No time-stretch.** A take from another tempo — recorded or
  [imported](#import-browser) — is detected and can be padded or trimmed, not
  stretched with its pitch preserved.
- **No Ableton Link.** [MIDI clock](#clock--playing-with-other-gear) works in
  both directions; Link is a seam with nothing behind it, because the native
  library has never been available here. `--clock link` says so rather than
  pretending.
- **No per-trigger probability**, and no randomisation of anything.
  [Swing](#swing) and [groove](#groove--laying-a-sample-back-behind-the-beat)
  did ship, in the two places a bar grid can carry them.
- **No per-layer editing** of an overdub: layers can be added and removed, not
  soloed or re-balanced against each other.
- **No key detection**, and nothing that proposes *bars* for you.
  [Slicing](#slice-page) and [the About page](#about-page) did ship — tempo,
  pitch, brightness and a name suggestion, each with a confidence — but a hint
  that proposes an arrangement waits for generative patterns, which needs the
  same propose-then-accept mechanic.
- **No probability per trigger** — a bar either plays or it does not.
  [Generated patterns](#pattern-page) did ship, and so did
  [swing](#swing) and [groove](#groove--laying-a-sample-back-behind-the-beat),
  but nothing here is stochastic at playback time.
- **Aftertouch** is received and ignored; velocity is used.
- **The colour display** shows text only: a mode banner, transport, levels and
  messages. No waveform drawing, no graphics. It does now render on real
  hardware — the first photograph of it found a transposed byte in the XOR mask
  (a gold striped background with blue text) and status lines running off the
  right-hand edge, both fixed. The one thing still unconfirmed is the BGR565
  channel order, which a black background cannot reveal.

`plans.md` in the project root tracks all of it: all 62 planned items are
shipped, every release train through `v2.1`.
[`CHANGELOG.md`](../CHANGELOG.md) is the release record.
