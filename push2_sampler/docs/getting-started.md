# Getting started

A tutorial. By the end you will have recorded several loops, arranged them across
a 64-bar song, played parts in by hand, shaped a take, fixed a mistake, and
bounced the result to a file you can play anywhere — using every feature the
program currently has.

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

### Step 3: start the program

```
python -m push2sampler my-first-song
```

`my-first-song` is a directory; it is created if it does not exist. The grid
should light up **all white**: 64 empty sample slots.

If the pads stay dark, press the Push's **User** button — the program talks to
the User port, so the Push has to be in user mode.

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
page. What you are looking at is **the 64 bars of your song**.

If it went wrong, press **Record** again to redo the take, or **Session** to go
back to the library and forget it.

### Step 6: put the loop in the song

On the sample page, every pad is one bar of the song: pad 1 is bar 1, the pad
below it is bar 9, the bottom-right pad is bar 64.

1. **Press the top-left pad.** It goes green: this sample now plays on bar 1.
2. **Press Play.** The song runs from bar 1, you hear your loop, and a white
   pad walks across the grid — that is the playhead. When it reaches bar 64 it
   loops back.
3. Press a few more pads while it plays. Each one adds another place the loop
   fires. You can do this while playing; nothing needs to stop.
4. **Press Stop.**

You may notice faint white pads you did not press. Those are a ruler: a dim mark
on every bar that starts a 4-bar phrase, a brighter one on every 16-bar section.
They make it possible to count bars without counting pads.

---

## Part 3 — Building up

### Step 7: a second layer

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
  until loops sit in time.
- **input device.** If the meter above the display never moves, step this until
  it does. Choosing a device that will not open is not fatal — the old one is
  kept and the display tells you why.

**Setup** again closes the page and writes the settings to
`~/.config/push2sampler/settings.json`.

### Step 13: tempo, click, loop

- **Tempo encoder** (top left) changes BPM by 1 per click, or 10 with **Shift**
  held. A sweep of the encoder is one undo step, not forty.
- **Metronome** turns the click on and off.
- **Repeat** turns the 64-bar loop on and off. With it off, the song plays once
  and stops.

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

### Step 15: undo

**Undo** takes back the last 64 edits. **Shift**+**Undo** puts them back.

It covers everything: a deleted take comes back with its audio *and* its
arrangement, a cleared arrangement comes back with its bars, a tempo nudge goes
back to the old tempo, applied edits come back as edits. The button is lit only
when there is something to take back.

Two destructive gestures worth knowing, both undoable:

- **Delete**, then any pad — in the library deletes that slot; on a sample page
  clears all its bars.
- **Shift**+**Delete** on a sample page deletes the sample outright.

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
- **[Reference](reference.md)** — the exact behaviour of each mode, every colour,
  every setting.
- **[Troubleshooting](troubleshooting.md)** — when something does not sound
  right.

And if you ran the probe in step 2, the report it wrote is the most useful thing
you can contribute: it turns this program's hardware guesses into facts.
