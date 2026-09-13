# Getting started

A tutorial. By the end you will have recorded several loops, arranged them across
a song, played parts in by hand, shaped a take, named and coloured your samples,
kept two versions of the arrangement, fixed a mistake, and bounced the result to
a file you can play anywhere — using every feature the program currently has.

You need: a Push 2, a USB cable, **headphones** (see
[step 4](#step-4-decide-how-you-will-hear-yourself)), and something to record —
a microphone, a guitar through an interface, or your own voice.

No prior knowledge of the program is assumed. Where a step says *press* something
it means on the Push, not on the computer.

---

## Part 1 — Setting up

### Step 1: install

```
cd push2_sampler
pip install -r requirements.txt
```

The first four packages are required. `soundfile`, `pyusb` and `Pillow` are
optional: without them you get 16-bit WAV files instead of float, and no colour
display, and everything else works identically.

Check what Python can see:

```
python -m push2sampler --list-ports     # should list "Ableton Push 2 User Port"
python -m push2sampler --list-devices   # your audio interfaces
```

Or ask the program itself what it can and cannot see:

```
python -m push2sampler doctor
```

That prints one row per thing that matters — Python, each optional package, the
MIDI ports, the audio devices, whether it can write where you are — with a
one-line fix beside anything missing. It is the fastest way to find out that the
reason nothing works is a package you never installed.

If the Push ports are missing, the cable or the MIDI stack is the problem, not
the program — see [Troubleshooting](troubleshooting.md#the-push-2-will-not-open).

### Step 2: run the probe

**Do this before making music.** Quit Ableton Live first if it is running; it
claims the Push's display.

```
python -m push2sampler --selftest
```

It walks nine checks: MIDI ports, which corner pad lights first, what notes the
corner pads send, velocity and aftertouch, every palette colour, 35 buttons one
at a time, four encoders including which way is clockwise, the touch strip, and
the display.

- Where it names a control, **press or turn that control on the Push**.
- Where it asks a question ("does the grid look green?"), type an answer.
- **Enter** on its own skips a step. **q** quits and still saves what it learned.

It writes `hardware-report.json` and `hardware-report.md`. The first table in the
markdown is headed *Needs correcting* — if it is empty, every guess in the
program was right. If it is not, that table is exactly what needs fixing, and
worth sending back.

Either way, continue; the probe changes nothing.

**If the very first check shows nothing lit at all**, stop and run the LED test
instead — the probe's remaining questions all assume the pads work, so answering
"none" eight times teaches nobody anything:

```
python -m push2sampler --led-test
```

It works through the layers one at a time (does the Push answer us, do the pads
light from a factory colour, do they light from *our* uploaded palette, do the
buttons light, is it the MIDI channel) and prints which one is at fault. See
[Troubleshooting](troubleshooting.md#the-ports-are-there-but-the-pads-stay-dark).

### Step 3: start the program

```
python -m push2sampler my-first-song
```

`my-first-song` is a directory; it is created if it does not exist. The grid
should light up **dim white**: 64 empty sample slots. (Dim on purpose — 64 pads
at full brightness is glare, and the brightest white is saved for the playhead.)

If the pads stay dark, see
[Troubleshooting](troubleshooting.md#the-ports-are-there-but-the-pads-stay-dark).
Nothing here needs a button pressed on the Push first: the program opens the
User port and starts sending, and it never asks the Push to change mode.

### Step 4: decide how you will hear yourself

Monitoring is **off** by default, deliberately: on speakers it feeds back and
howls. On headphones you want it on.

Hold **Shift** and press **Metronome** to cycle: `off` → `auto` → `on`. The
display says which. **`auto`** is the one you want — it passes the input through
only while a take is actually recording, which is when you need to hear yourself
and cannot get feedback from a loop that is not playing.

The eight buttons **above** the display are an input level meter. Make a noise;
they should light. If they do not, your input device is wrong — see
[step 12](#step-12-the-settings-worth-knowing).

---

## Part 2 — Your first loop

### Step 5: record two bars

1. **Press any blank (white) pad.** The grid goes dark except the top-left pad,
   which is white. You are in Record mode, and that pad means "one bar".
2. **Press the second pad in the top row.** Now two pads are white: a two-bar
   take. The selection always starts at the top-left and runs in reading order,
   so the pad you press is simply the last bar included. Try pressing the pad at
   the end of the first row — eight bars — then come back to two.
3. **Press Record.** You get four clicks — one bar of count-in — and then
   recording starts *exactly* on the downbeat. Play or sing for two bars.
4. It stops on its own. You did not have to press anything.

The take is now in the slot you chose, and the grid has become that sample's own
page. What you are looking at is **64 bars of your song** — the first page of
four, which is plenty for now.

If it went wrong, press **Record** again to redo the take, or **Session** to go
back to the library and forget it.

### Step 6: put the loop in the song

On the sample page, every pad is one bar of the song: pad 1 is bar 1, the pad
below it is bar 9, the bottom-right pad is bar 64.

1. **Press the top-left pad.** It goes green: this sample now plays on bar 1.
2. **Press Play.** The song runs from bar 1, you hear your loop, and a white
   pad walks across the grid — that is the playhead. When it reaches bar 64 it
   loops back, because the loop starts out covering just this page.
3. Press a few more pads while it plays. Each one adds another place the loop
   fires. You can do this while playing; nothing needs to stop.
4. **Press Stop.**

You may notice faint white pads you did not press. Those are a ruler: a dim mark
on every bar that starts a 4-bar phrase, a brighter one on every 16-bar section.
They make it possible to count bars without counting pads.

### Step 6b: three faster ways to fill bars

Pressing one bar at a time is exact, but most arranging is blocks. Three gestures
cover nearly all of it — try each on your loop:

1. **Hold one pad and press another.** Every bar between them, inclusive, is set
   at once. Whether it paints *on* or *off* is decided by the pad you are holding:
   hold an empty bar and the range fills, hold one that was playing and the range
   empties. Useful for "this runs from bar 9 to bar 24".
2. **Double-tap an empty pad.** The take is laid across the next four bars, spaced
   by its own length — a 1-bar loop fills four bars, a 2-bar loop fills two of
   them. This is "just play it for a phrase" in one gesture. Double-tap a bar that
   *was* playing and it clears those four instead.
3. **Press Duplicate, then the start of a block, then where it goes.** The gap
   between your two presses is how long the block is: press bar 1 then bar 5 and
   bars 1–4 are copied onto 5–8. Hold **Shift** for the second press to *move* the
   block rather than copy it.

All three are a single **Undo** each, however many bars they touched — so the
fast way is not the risky way. (After a paint or a fill you will need a second
**Undo** for the first press that started it.)

### Step 6c: play it twice, on top of itself

A second pass on the *same* slot, rather than a second slot:

1. On the sample's page, **press New**. You get a count-in, the song plays, your
   loop plays where you arranged it, and whatever you play now is **added to the
   take** rather than replacing it.
2. When it lands, the display says `2 layers`.
3. Don't like the second pass? **Shift**+**New** peels it off. Repeatedly, back
   to the original recording, which can never be removed.

This is sound-on-sound: a hi-hat over a kick, a harmony over a vocal, all in one
slot. The layers survive saving, so you can take a pass off tomorrow.

Because the take plays along while you overdub, a sample you have not arranged
anywhere is silent during the overdub — the program says so if you try.

---

## Part 3 — Building up

### Step 7: a second part

1. **Press Session** to go back to the library. Your first slot is green; the
   rest are white.
2. **Press a blank pad**, choose a length, **Record**. While the count-in runs
   and while you record, *the song plays along* — so you can record the second
   part in time with the first. That is the whole point.
3. When it lands, arrange it: press the bars where it should play. Notice that
   the bars where your *other* sample plays are shown in **dim blue**, so you can
   place the new part in relation to what is already there.

Samples overlap freely. A 4-bar loop triggered on bars 1 and 3 will play over
itself; two different samples on the same bar simply both play.

Two other things to notice while the song runs. Back in the library, a slot that
is **sounding** is amber and one that comes in on the **next** bar is dim amber —
so you can see what is about to enter without reading a screen. And if you want a
variation of a take rather than a new one, press **Duplicate** then its pad in the
library: you get a copy in the next empty slot, with the same arrangement, which
you can then re-record, retune or trim independently.

### Step 7b: more than 64 of anything

You have four banks of 64 slots — 256 samples — and four song pages of 64 bars,
which is about eight minutes. The grid always shows 64 of each, so two controls
move the window:

- **Page ◀** and **Page ▶** change the **bank**: which 64 slots the library
  shows. The grid flashes for a moment so you know you moved, and the display
  names the bank (A–D). Everything in every bank still plays — a bank is a view,
  not a song section.
- **Shift**+**Page ◀/▶** changes the **song page**: which 64 bars a sample page
  shows. Page A is bars 1–64, page B is 65–128, and the song runs through them
  in order.

There is a third thing **Repeat** now does: it cycles what the loop covers.
`page` (the default) loops just the page you are working on, `song` loops all
four, `off` plays to the end and stops. Working on the chorus while the verse
waits is the point.

### Step 8: decide what you hear while you work

Two ways to silence a sample without losing it:

- On its **sample page**, press **Mute**. The page says `MUTED`, and in the
  library its pad goes dim green.
- In the **library**, press **Mute** (nothing selected), then press any filled
  pad. Faster when you want to solo by ear across several slots.

Muting changes what plays and what gets bounced. It does not change the
arrangement, and it is undoable.

### Step 9: audition without leaving the library

In the library, **hold** a filled pad for about half a second. It plays, and the
pad turns amber, but you stay in the library — useful when you are hunting for a
particular take among twenty. A short **tap** opens the sample's page instead.
**Shift** + a pad auditions immediately, no waiting.

---

## Part 4 — Playing, not programming

### Step 10: play the arrangement in

Toggling bars is precise but slow. Perform mode lets you play the song in.

1. **Hold Shift and press Play.** The loop starts and the grid becomes the
   library again — but now the pads **fire** their samples.
2. Hit a pad. It does not play instantly: it waits for the next bar line, so it
   lands in time even if your timing does not. **Fixed Length** cycles how much
   it waits: `1 bar` (the default), `1/2 bar`, `1/4 bar`, or `off` for
   immediately.
3. **Press Record.** The display says `WRITING`. Now every pad you play is also
   *written into the arrangement*, at the bar where it sounded. Play a part in
   over a couple of passes of the loop.
4. Too much? **Press Delete** to arm erasing. Bars are wiped as the playhead
   crosses them, starting from the next bar line — hold it for a pass and the
   song empties out behind the playhead. Press **Delete** again to stop.
5. **Session** leaves perform mode.

Everything you played in, and everything you erased, is on the undo stack.

### Step 11: make the pads velocity-sensitive

By default a sample plays at one level however hard you hit the pad, which is
right for a loop toggled in by hand. For something you are playing live, you
want dynamics.

1. Go to a sample's page (tap its pad in the library).
2. **Press Accent.** The page changes from `flat` to `velocity`.
3. Go back to perform mode (**Shift**+**Play**) and hit that pad softly, then
   hard. The level follows.
4. Play a part in with **Record** on, then look at the sample page: the bars are
   now green in **three brightnesses**, showing how hard each one was played.

---

## Part 5 — Fixing and finishing

### Step 11b: see the whole song

Every page so far shows one sample's bars, or one bank's slots. **Press Clip**
and you get the whole arrangement at once.

Each pad is a block of **8 bars by 8 slots** — columns are bars, rows are slots —
coloured by how much happens inside it: dim blue for one trigger, blue for a
couple, amber for a handful, white for a lot. The column the playhead is in
brightens. That is how you see at a glance that bar 33 is bare, or that your
second half is just your first half again.

**Press any pad to zoom in.** Now each pad really is one bar of one slot, and
pressing it toggles exactly what the sample page would. **Page ◀/▶** steps to the
next block, **Delete** clears the block you are in, and **Clip** zooms back out
then leaves.

### Step 11c: balance it

Toggling bars tells you *what* plays. The mixer tells you how loudly.

**Press Mix.** The grid becomes eight vertical level meters — one per slot in the
top row of your library — filling upwards in green, amber near the top, red when
a slot is about to clip. That is the fastest way to find the take that is too
loud.

- **The eight encoders** set the gain of the eight strips.
- **The eight buttons below the display** mute them.
- **Solo**, then one of those buttons, hears one strip alone. Press **Solo**
  again to come back. This never disturbs the mutes you set by hand: un-soloing
  gives you exactly the mix you had.
- **The master encoder** (top right) sets the level of the whole mix.
- **Up**/**Down**, or pressing any pad, moves to another row of eight.
- **Mix** closes it.

Muting here changes the bounce too. The master gain is saved with the project.

### Step 11b: decide how each sample ends

Everything so far has played to the end of its recording. That is right for a
drum hit and wrong for a pad: trigger a 4-bar chord on bar 1 and again on bar 3,
and the first one plays straight over the second.

On a sample page, the four buttons **2–5** below the display set that:

1. Open a sample page for a take of a bar or more.
2. Press **button 4** — `gate`. The display names it.
3. Put the sample on bars 1 and 2, and press **Play**.

Now it re-strikes cleanly on each bar instead of overlapping itself, because a
gate stops at the end of the bar it started in however long the audio is.

The other two are worth knowing by ear:

- **`loop`** (button 3) repeats until a bar it is *not* triggered on. Put a
  1-bar take on bar 1 only, set it to `loop`, and then turn on bars 2–8: it
  plays continuously and lets go at bar 9. One trigger holds a section.
- **`retrig`** (button 5) cuts the previous voice of that slot instead of
  layering. For a bass or a lead, where two notes at once is a mistake.

**Button 8** cycles a **choke group**, 1 to 8. Put two samples in the same group
and they cut each other — an open hat and a closed one, or two vocal takes that
should never overlap. A sample never chokes itself; that is what `retrig` is
for.

All of it is per sample, saved with the song, and one **Undo** each.

### Step 11c: bring in a sample you already have

Not everything has to be recorded. **Shift**+**Browse** opens a file browser on
the pads.

1. **Shift**+**Browse**. White pads are folders, blue pads are audio files.
2. **Press a blue pad.** The display names it, with its length, rate and
   channels. Nothing has happened yet — the first press only highlights.
3. **Press the same pad again.** It is imported into the first empty slot,
   resampled to your session rate if it needs it, and its sample page opens.

Buttons below the display move around: **2** goes up a folder, **3** back to
the start, **5** to your home folder. **Browse** again leaves.

Two things it will not do. It will not put a sample over one of your takes —
imports always land in an empty slot. And it will not **stretch** audio: if the
file is not a whole number of bars at your tempo, the display says `OFF GRID`
and the take goes in at its real length. **Button 1** on its sample page fits it
to its bars if that is what you want; leaving it is fine too, and is the right
answer for a one-shot hit that was never meant to fill a bar.

`.wav` always works. Other formats need `soundfile` (`pip install soundfile`);
without it those files are still listed but say so when you highlight them.

By default the browser starts in the folder your song lives in. Point it
somewhere better once and forget about it:

```
python -m push2sampler --samples-root ~/Music/samples my-first-song
```

And from the terminal, when a browser is more trouble than it is worth:

```
python -m push2sampler --import ~/Music/samples/kick.wav my-first-song
```

### Step 11d: watch it play

Everything so far has been editing. Now just listen.

Press **Shift**+**Session**. The grid is your library again, but nothing here
edits anything: **each pad flashes white as its sample fires.** Press **Play**
and watch. One glance tells you what is carrying a section and what is sitting
out, which is hard to see from any of the editing pages.

Press a pad to hear that sample on its own. **Delete**, **Mute** and
**Duplicate** do nothing here on purpose — this is the page for listening, so a
stray press costs nothing. **Session** goes back.

The flash marks the moment a sample *starts*, not how long it lasts: a 4-bar pad
blinks once rather than staying lit for four bars. The display counts how many
slots fired in the bar you are in.

### Step 11e: put two samples in the wrong order, then fix it

Say your kick is on pad 1 and your snare on pad 2, and you would rather it was
the other way round.

1. **Shift**+**Duplicate.** The filled pads flash cyan.
2. **Press the kick's pad.** It holds white — "this one".
3. **Press the snare's pad.** They trade places.

Everything goes with them: the audio, the bars each plays on, names, colours,
gains, play modes. One **Undo** puts it back.

Picking an *empty* pad second moves the sample there instead, which is the same
gesture and does what you would expect.

### Step 12: the settings worth knowing

**Press Setup.** The pads go dark — deliberately, so there is no chance of
thinking this page edits your song. Each of the eight buttons *below* the display
owns one setting; the encoder above it changes the value, and pressing the button
resets it or toggles it.

| | | |
| --- | --- | --- |
| count-in beats | monitoring | monitor gain |
| record latency | play while recording | autosave delay |
| input device | audio block size | |

The two that matter most early on:

- **record latency.** If your takes land consistently *late* against the grid,
  your interface has input latency. Set this to roughly that many milliseconds
  and the program trims it off the front of each take. Start at 10 and adjust
  until loops sit in time — or measure it properly, once, and never think about
  it again:

  ```
  python -m push2sampler --calibrate
  ```

  Connect the output back to the input, or point a microphone at the speaker. It
  plays five clicks, times their return, and writes the median. One cough cannot
  set your timing, and it refuses an absurd figure rather than storing it.
- **input device.** If the meter above the display never moves, step this until
  it does. Choosing a device that will not open is not fatal — the old one is
  kept and the display tells you why.

**Setup** again closes the page and writes the settings to
`~/.config/push2sampler/settings.json`.

### Step 13: tempo, click, loop

- **Tempo encoder** (top left) changes BPM by 1 per click, or 10 with **Shift**
  held. A sweep of the encoder is one undo step, not forty.
- **Tap Tempo**, four times, sets the tempo by feel instead. The display counts
  your taps (`tap 2/4`); one badly-placed tap out of four is thrown away rather
  than believed. **Shift**+**Tap** starts over.
- **Hold Tap Tempo and turn the tempo encoder** for ±0.1 BPM, which is what you
  want when matching something playing in the room. The readout grows a decimal
  so you can see it: `121.3 BPM`.
- **Metronome** turns the click on and off. Page 3 of the **Setup** page has the
  rest of it: the click's **sound** (a soft sine, a sharp tick, or a cowbell that
  cuts through anything), its **volume**, **click on rec only** so it is silent
  while you play, a **pre-roll** that runs the song for a few bars before the
  count-in so you arrive already in the groove, and a **click output** — set that
  to a channel your interface has and the click goes only there, keeping it out
  of the main mix and out of everything you bounce.
- **Repeat** turns the 64-bar loop on and off. With it off, the song plays once
  and stops.
- **Shift**+**Stop** stops at the end of the current bar rather than instantly, so
  a loop finishes its bar. The display reads `ENDING` until it does. Plain **Stop**
  stops immediately; pressing **Stop** twice quickly also disarms anything you
  left armed, which is the fastest way out of a state you did not mean to be in.

One catch worth understanding: a take recorded at 120 BPM is the wrong *length*
for a song at 140. When that happens the slot turns **yellow** in the library,
and its page says so:

```
OFF GRID: 1.83 bars at 220 BPM (recorded at 240) - button 1 below to fit
```

Nothing was done behind your back — the audio is untouched. Press the first
button below the display to pad or trim it to fit, which is undoable. (Stretching
it in pitch-preserving fashion is not built yet.)

### Step 14: shape a take

**Press Device** on a sample page to open the editor.

The grid becomes the take itself: 64 pads, one per slice of the audio, lit by how
loud that slice is. **Press a pad to hear the take from that point.**

Each encoder owns one parameter; the button under it resets or toggles it:

| | | | |
| --- | --- | --- | --- |
| trim in | trim out | fade in | fade out |
| pitch (±12 semitones) | gain | reverse | normalise |

The parts you are trimming away go **dim red** on the grid, so you can see the
cut. The display carries a one-line picture of the waveform and the resulting
length.

Try this: turn up **trim in** until the dead air at the start of your take is
red, add a short **fade out** so the loop does not click, and turn on
**normalise** to bring a quiet take up.

**None of this touches the recording.** Edits are stored alongside the audio and
applied on the way to the speakers, so you can change them as often as you like
and undo any of them. When you are sure, **Shift**+**Device** folds them into the
recording for good — and even that is one undo step.

Note that trimming makes the take shorter than its bars, so it may go yellow per
step 13. That is correct: the loop really is shorter now.

### Step 14b: name it, colour it

Twenty takes called `S01` to `S20` are unfindable. There is no keyboard, and you
do not need one.

**Press Select** on a sample page. The top seven rows of pads are words — eight
categories of eight, from `kick` and `snare` through `bass`, `chord`, `vox` and
`riser` — and the buttons below the display jump between categories. Press a
word and the slot is named. A second `kick` names itself `kick 2`.

**The bottom row of pads is eight colours.** Press one and the slot shows in that
colour in the library, so a full bank becomes readable at a glance. Press the same
one again to clear it. Muted and sounding still look the way they always did.

Both are one **Undo** each, and both are saved with the song.

### Step 14c: keep two versions of the arrangement

The eight buttons **below the display** in the library are scenes.

1. Arrange something you like. **Hold Shift and press the first button.** That
   button lights: the arrangement is stored.
2. Now change things — mute a sample, move some bars, add a part.
3. **Press that first button** (no Shift). You are back to the stored version.

A scene remembers what is audible and where it plays. It does *not* touch the
audio, the gain or your edits — those belong to the take, not the arrangement.
Recalling is one **Undo** step, so an A/B never costs you anything, and a recall
while the song is playing lands on the next bar rather than chopping a note.

### Step 14d: start another song, without a terminal

**Press Browse.** The pads are the songs on disk: green has samples in it, dim
white is empty, and dim amber is the one you have open.

- Press a pad to highlight it; **press the same pad again to open it**.
- **Button 2** below the display starts a new song, named from today's date and a
  word.
- **Button 3** duplicates the highlighted one, audio and all — the safe way to
  try a different arrangement.
- **Button 5**, *held* for a second, deletes it. Held, because this is the one
  action **Undo** cannot reach.

Opening a song saves the one you were in first, and swaps it in without
restarting the audio, so there is no gap or click.

### Step 15: undo

**Undo** takes back the last 64 edits. **Shift**+**Undo** puts them back.

It covers everything: a deleted take comes back with its audio *and* its
arrangement, a cleared arrangement comes back with its bars, a tempo nudge goes
back to the old tempo, applied edits come back as edits. The button is lit only
when there is something to take back.

It also covers the block gestures from [step 6b](#step-6b-three-faster-ways-to-fill-bars):
a painted range, a filled phrase, a duplicated block or a duplicated slot is one
step each, and an undone *move* puts the sample back where it was.

Two destructive gestures worth knowing, both undoable:

- **Delete**, then any pad — in the library deletes that slot; on a sample page
  clears all its bars.
- **Shift**+**Delete** on a sample page deletes the sample outright.

If you ever lose track of what is armed, press **Stop** twice: it stops and
disarms everything.

### Step 16: bounce it

**Hold Shift and press Record** in the library. The whole grid becomes one
progress bar filling up in amber, and the display counts the percentage. It
renders far faster than real time, and you can keep playing while it works.

The file lands in `my-first-song/bounces/<timestamp>.wav`.

From a terminal — no Push, no audio device needed:

```
python -m push2sampler --bounce song.wav my-first-song    # the mix
python -m push2sampler --stems stems/ my-first-song       # one file per slot
```

Stems sum back to the mix exactly, and both keep the tails of samples that
overrun the last bar.

---

## You now know the whole program

Your project directory holds everything:

```
my-first-song/
  project.json          tempo, and for each slot: length, which bars it plays
                        on, how hard each was played, mute, gain, its edits
  samples/slot_00.wav   one file per filled slot
  bounces/*.wav         whatever you have bounced
```

It saves itself a couple of seconds after any change, and on exit.
**Shift**+**Setup** saves immediately if you want to be sure.

## Where to go next

- **[Cheat sheet](cheatsheet.md)** — every control on one page.
- **[The changelog](../CHANGELOG.md)** — what each release added, and the bugs
  each one turned up.
- **[Reference](reference.md)** — the exact behaviour of each mode, every colour,
  every setting.
- **[Troubleshooting](troubleshooting.md)** — when something does not sound
  right.

And if you ran the probe in step 2, the report it wrote is the most useful thing
you can contribute: it turns this program's hardware guesses into facts.
