# Troubleshooting

Symptom → cause → fix. Read the relevant row before concluding something is
broken; most of these are configuration, not faults.

Three things first:

1. **Ask the program.** `python -m push2sampler doctor` prints one row per thing
   that matters — Python, each optional package, the MIDI ports and audio devices
   it can see, whether it can write where you are — with a one-line fix beside
   anything missing. It always exits 0, so it is safe to run before you know
   what is wrong. Most of the rows below are things it will tell you in a
   second.
2. **Run the probe.** `python -m push2sampler --selftest` tests the MIDI ports,
   the pads, the buttons, the encoders and the display one at a time and writes
   down what it found. If a control does nothing, the probe will tell you whether
   the program is looking at the wrong control change number — which is likely,
   because [nobody has run this on real hardware yet](README.md#one-thing-to-know-before-you-trust-it).
3. **Read the display.** Nearly every failure in this program announces itself
   there: a device that would not open, a bounce that failed, a take that does
   not fit its bars, a clipping input. The program does not fail silently on
   purpose.

---

## Starting up

### The Push 2 will not open

```
RuntimeError: no Push 2 MIDI input port found (looked for 'Push 2' in [...])
```

The list in the message is every MIDI port Python can see. If the Push is not in
it, the program never had a chance.

| Cause | Fix |
| --- | --- |
| Not plugged in, or plugged into a hub that does not power it | Straight into the computer, with the Push's own power supply |
| `python-rtmidi` missing | `pip install -r requirements.txt`; confirm with `python -m push2sampler --list-ports` |
| Linux, no permission on the USB device | Add your user to the group owning the device, or install Ableton's udev rule |
| Ableton Live is running | Quit it. It takes the Push's ports and display |

### The ports are there but the pads stay dark

Run this first — it answers the question in about a minute:

```
python -m push2sampler --led-test
```

It works through the layers in order and tells you which one is at fault,
because "dark" has several causes that look identical:

| Stage | Question |
| --- | --- |
| 1 | Does the Push send *us* anything? Press a pad; it prints what arrives |
| 2 | Do the pads light from a **factory** palette index? No SysEx involved |
| 3 | Do they light from **our** uploaded palette block? SysEx involved |
| 4 | Do the **button** LEDs light? |
| 5 | Does a colour need a MIDI channel other than channel 1? |

The outcome worth knowing about is **stage 2 lighting and stage 3 dark**. Every
colour this program uses is a *private palette index* of 64 or above, uploaded
at startup over SysEx that has never been confirmed on a device. If that upload
does not take, the program spends its life painting in palette entries the Push
has left black — no error, no traceback, a grid that looks dead. `--led-test`
says so in one line, and writes `led-report.json`.

It prints a verdict at the end. Paste that back, or the JSON.

### `--led-test` said nothing happened in either direction

Then there is nothing left to *look* at, and the next questions have to be
answered by the machine:

```
python -m push2sampler --midi-probe
```

This one asks you almost nothing. It reports:

- which **mido backend** is actually loaded — the program is written against
  `python-rtmidi`, and anything else invalidates every other reading;
- whether the Push is **on the USB bus at all**, via `pyusb`, independently of
  MIDI. This is what separates "not plugged in, not powered, or stale ports"
  from "the MIDI layer";
- input read **two ways**, by callback and by polling. `Push2` uses a callback,
  so a callback that stays silent while polling works is *our* bug, not the
  device's, and the probe says so in those words;
- **both** Push ports, in both directions. If the Live port answers when the
  User port does not, that is a real finding about the device;
- every exception, printed rather than swallowed.

It writes `midi-report.json`, which is all facts and no opinions — the useful
fields are `environment.mido_backend`, `usb.found`, and the callback-versus-
polled counts per port.

The most common cause of silence in both directions, once the ports open
without error, is **something else holding the Push**: Ableton Live (including
a background process that outlives quitting it), Push's firmware updater, or
another DAW with a control-surface script. On macOS a second process can open
the same port, get no error, and receive nothing at all.

### Pads and buttons do nothing, but the lights work (or vice versa)

The Push 2 routes its surface to **one of its two MIDI ports** depending on the
mode it is in, and on a device in Live mode the User port carries **no input at
all** — the pads and buttons report on the Live port instead. This is the
device telling you which port it is using; it is not a fault, and there is
nothing to press to change it.

The program handles this by itself: it **listens to every Push port** for
input, so it does not need to know which mode the device is in. If input still
does not arrive, or if the *lights* are going to the wrong port, pin it:

```
python -m push2sampler --midi-port live my-song
python -m push2sampler --midi-port user my-song
```

`--midi-port` matches any part of a port name and forces both directions.
`--midi-probe` tells you which port carries what, and prints the exact flag to
use.

### If the grid is dark and you have not run the LED test

**The program does not need any button pressed on the Push.** It opens
the User port and sends colours; it never sends a mode change, and there is
nothing to press to let it in. If a walkthrough ever told you to press a `User`
button before starting, that was wrong — and depending on your unit there may
not be such a button to press. So look at the port choice instead.

The program may have picked the wrong one of several matching ports. Check what
it chose:

```
python -m push2sampler --list-ports
```

It prefers a port with "User" in the name and avoids one with "Live". If your
port names are unusual — on Linux/ALSA they are often `Ableton Push 2 MIDI 1`
and `MIDI 2`, with no "User" anywhere — then it took the first match, which may
be the Live port. There is no flag for this yet; say which names you have and
it becomes one.

Two things do genuinely take the surface away from us:

| Cause | Fix |
| --- | --- |
| Ableton Live is running | Quit it. While it is driving the Push it owns the surface and the display, and it repaints over anything we send |
| Bus power only | Plug in the Push's own power supply. On USB power alone it runs dim and the display may not come up |

If Live is running and you would rather not quit it, that is what the Push's
user mode is for — but it is a Live-side arrangement, not something this program
takes part in. Quitting Live is the supported answer.

### "ignoring …/settings.json: …" on startup

Your settings file is unreadable or malformed. The program carried on with
defaults rather than refusing to start. Delete
`~/.config/push2sampler/settings.json` (the settings page will write a fresh
one) or run with `--no-settings` to confirm that is all it was.

### A command-line option appears to do nothing

The program now tells you when it refuses one:

```
refusing --samplerate 5000: out of range 8000-192000
```

If you see that, the value was rejected and the previous one kept. Otherwise,
note that command-line values apply to **that run only** and are never written
to the settings file — if you expected a setting to stick, set it on the
**Setup** page instead.

---

## The surface

### The grid went dark and nothing responds

Look at the display. If it says

```
SURFACE OFFLINE - check the cable; the audio is still running
```

then the Push stopped accepting writes — almost always the USB cable. **The
audio is genuinely still running**: the song keeps playing, a take in progress
keeps recording, and nothing is lost. Reseat the cable and it reconnects by
itself within a couple of seconds, relights the whole grid, and says
`surface back`.

If the display is dark too, you have no display (see below), so run with
`--no-display` or watch the terminal.

---

## Sound

### No sound at all

In order of likelihood:

1. **Nothing is arranged.** A recorded sample does not play until you press the
   bars it should play on, on its own page. A filled slot with no bars set makes
   no sound. Open the sample's page; if every pad is dark, that is the problem.
2. **The transport is stopped.** Press **Play**.
3. **The sample is muted.** Its pad is dim green in the library. Press **Mute**
   on its page.
4. **The wrong output device.** `python -m push2sampler --list-devices`, then
   `--output-device N`.
5. **Gain at zero.** Encoder 1 on the sample page; the page shows the value.

### I cannot hear myself while recording

Monitoring is **off** by default and that is deliberate: routing an input to an
output in the same room as a speaker howls.

**Shift**+**Metronome** cycles `off` → `auto` → `on`. Use `auto` — it passes the
input through only while a take is actually running.

If it is on and you still hear nothing, the input device is wrong: the eight
buttons *above* the display are an input meter, and they should move when you
make a noise. If they do not, set **input device** on the **Setup** page until
they do.

### Feedback — a rising howl

Monitoring is on with speakers, not headphones. **Shift**+**Metronome** back to
`off`, or put headphones on.

### "input clipping" on the display

Your input level is too hot and the recording is being squared off. Turn it down
at the source (the interface's own gain), not in this program — once a take is
clipped, no amount of gain here recovers it.

### "audio dropout (...)"

The audio callback missed its deadline. The audio is fine; this is a warning.

| Cause | Fix |
| --- | --- |
| Block size too small for this machine | Raise **audio block size** on the **Setup** page (256 → 512 → 1024) |
| Something else is loading the CPU | Close it; this is a real-time program |
| Very many voices at once | Samples overlap freely, but 96 simultaneous voices is the ceiling |

### "audio: ..." on the display

The audio device reported an error and the stream stopped. The message is the
device's own. Usually it means the device was unplugged or taken by another
program; pick a different one on the **Setup** page, which restarts the stream.

### A device I chose on the Setup page was not used

Choosing a device that will not open is not fatal. The program keeps the one that
was working and puts the reason on the display. Read it — it is the device
driver's explanation, not ours.

---

## Recording

### Takes land late — everything is slightly behind the beat

Your interface has input latency: the sound reaches the program some
milliseconds after it happened, so the recording starts late relative to the
grid.

Set **record latency** on the **Setup** page to roughly that many milliseconds
and the program trims it off the front of every take. Start at 10 and work up or
down until a loop sits in time against the click. Typical values are 5–20 ms;
if you need far more than that, suspect the buffer size instead.

This only affects takes recorded *after* you change it. Earlier takes keep the
timing they were recorded with.

### Takes land early

Record latency is set too high. Lower it — or measure it:

```
python -m push2sampler --calibrate
```

### Calibration says it heard nothing

The output is not reaching the input. Connect a cable from out to in, or point a
microphone at the speaker, and raise both a little. It needs to actually hear the
click.

### Calibration refuses its own measurement

`too much to be latency` means it found something more than 250 ms out, which is
a room reflection rather than the click itself. Move the microphone closer to the
speaker, or use a cable.

`varying by N ms` means the rounds disagreed. Somewhere quieter, or a cable.

### The count-in is too long, or I want none

**count-in beats** on the **Setup** page, or `--count-in N`. Zero works: recording
starts at the next downbeat with no clicks.

### I cannot hear the click during the count-in

**Metronome**, and check monitoring is not masking it.

### Recording did not stop where I expected

It stops after exactly the number of bars you lit in Record mode, counted from
the downbeat after the count-in. If it stopped sooner than you played, you
selected fewer bars than you thought — the selection always starts at the
top-left pad and runs in reading order, so the pad you press is the *last* bar
included, not the only one.

### I want the song silent while I record

**play while recording** on the **Setup** page, or
`--no-play-while-recording`. It is on by default because recording a second part
against the first is the usual case.

### "library full"

All 64 slots are filled. Delete one (**Delete**, then its pad — undoable) or
start another project.

---

## Timing and length

### A slot went yellow

The take is the wrong *length* for the current tempo — almost always because you
recorded it at one tempo and then changed the tempo. Its page says so:

```
OFF GRID: 1.83 bars at 220 BPM (recorded at 240) - button 1 below to fit
```

Nothing was changed behind your back; the audio is exactly as recorded. Two
honest options:

- **Press button 1 below the display** to pad or trim it to fit its bars. This is
  undoable, and it is the right answer when the mismatch is small.
- **Put the tempo back** to what it says it was recorded at, and the yellow goes
  away.

There is no pitch-preserving time stretch yet, so a take recorded at 90 cannot be
made to *sound* right at 140. Re-record it.

### A slot went yellow after I edited it

Correct, and expected. Trimming makes the take shorter than the bars it claims,
so it no longer fits. Either fit it (button 1) or reduce what you trimmed.

### Samples drift apart over a long loop

Everything in this program is scheduled in samples from a single clock, so true
drift is not possible. What you are hearing is more likely one take being
slightly the wrong length — check for yellow slots.

---

## Editing and arranging

### The editor will not open

**Device** only opens the editor on a sample page with a sample in it. From the
library, tap the slot first.

### My edits do not seem to apply

They do, on the way to the speakers — the file on disk is untouched on purpose.
If you hear no difference: check the value actually moved (the display shows it),
and remember that **trim in** of 5 ms is inaudible. Turn it up until the dim red
region on the grid is obvious, then listen.

### I applied edits and now want the original back

**Undo.** Applying edits to the recording is a single undo step like any other.
Once you have done 64 further edits it is gone, so if a take matters, bounce it
first.

### A pad I press in perform mode does not fire immediately

By design: it waits for the next quantize point so it lands in time. **Fixed
Length** cycles `1 bar` → `1/2 bar` → `1/4 bar` → `off`. `off` fires instantly.

### Perform mode is not writing what I play

Press **Record** inside perform mode; the display must say `WRITING`. Firing
pads without it is rehearsal — audible, but nothing is recorded into the
arrangement.

### "slot N already plays on bar M"

You fired a pad that was already written at that bar. Nothing was changed. Not an
error.

### Erasing in perform mode wiped less than I expected

Erasing starts at the **next** bar line, not the bar currently playing — so the
bar you are hearing when you press **Delete** survives. That is deliberate: it
means arming erase never damages the bar you were listening to. Hold it through a
pass of the loop to clear more.

### Holding a pad and pressing another did not paint the range

Check which pad you held. The **held** pad's own press decides the direction: hold
an empty bar and the range paints on, hold one that was already playing and it
paints off. If nothing happened at all, the whole range was already in that state.

### A double-tap toggled the bar twice instead of filling the phrase

The two presses have to be within about a third of a second. A slower pair is two
ordinary toggles, which is deliberate — a fill should not happen by accident.

If the fill did nothing and the display said `nothing to fill`, the take is four
bars or longer, so it already covers the phrase; there is nothing to add.

### Duplicate did not copy what I expected

On a **sample page**, the two presses are *the start of the block* and *where it
goes*, and the **gap between them is the block's length** — bar 1 then bar 5
copies bars 1–4 onto 5–8, not bar 1 alone onto bar 5. Pressing an earlier bar
second is refused (`press a later bar`) rather than guessed at.

Destination bars that the source does not play on are **cleared**: the copy
replaces what was there rather than merging into it. That is one undo step if it
was not what you wanted.

In the **library**, Duplicate copies to the *next empty slot*, wrapping round the
grid — not to a slot you choose. If every slot is full it says so.

### Shift+Stop did not stop

It is waiting for the bar line; the display reads `ENDING` and the **Stop** button
is lit bright. At 120 BPM that is up to two seconds. Press **Stop** on its own to
stop immediately, or **Play** to cancel the pending stop.

During a take, **Stop** always cancels at once — a recording is never deferred.

### Tap Tempo did nothing

- Fewer than four taps so far: the display is counting them (`tap 2/4`).
- More than 2.5 seconds between taps starts a new series, so slow tapping never
  accumulates.
- `taps too uneven` means no three intervals agreed closely enough to trust.
- `cannot change tempo during a take` is exactly that: the tempo is locked while
  recording, because it decides how long the take must be.
- The result is clamped to 40–240 BPM.

### The tempo will not move in small steps

Hold **Tap Tempo** while turning the tempo encoder: that is the ±0.1 nudge.
Without it the encoder moves in whole BPM, or tens with **Shift**. When the tempo
is not a whole number the readout shows a decimal, so you can tell which you got.

### Delete did nothing

Two deliberate gates:

- **The arm lapses after three seconds.** If you armed **Delete**, got
  distracted, and then pressed a pad, nothing happens — which is the point. Arm
  it again.
- **A slot that plays somewhere takes two presses.** The first says
  `slot 7 plays on 12 bars - press again`. Press the *same* pad again to go
  ahead; press a different one and it warns about that one instead. A slot that
  plays nowhere deletes on the first press, because there is nothing to regret.

### A take came out quieter or shorter than I played

Check page 2 of the **Setup** page: **auto trim**, **auto normalise** and **auto
fade** are off by default, but if one is on it processes every take as it lands.
The display says what it did (`trimmed 30ms, normalised x1.4`) — if you missed
that message, this is where it came from.

Auto-trim never changes a take's *length* (it pads the end by as much as it took
off the front), so it cannot put a slot off the grid.

### Overdubbing recorded silence

**New** plays the take along while you record, so it needs the take to be
arranged somewhere to hear it — but that only affects what you *hear*, not what
is captured. If the layer itself is silent, your input is the problem, not the
overdub: see [I cannot hear myself while recording](#i-cannot-hear-myself-while-recording).

If you meant to *replace* the take rather than add to it, that is **Record**,
not **New**.

### Shift+New will not remove a layer

The original recording is not removable — only overdubs are, and the display
says `only one layer; nothing to remove`.

Note that **applying edits** (Shift+Device) or **fitting an off-grid take**
collapses the layers into one, because both replace the audio with something
that is no longer their sum. The sound does not change, but the passes can no
longer be separated.

### Soloing wiped my mutes

It did not. Solo is stored separately from each sample's own mute state
precisely so that this cannot happen: press **Solo** again and the mix comes
back exactly as it was. While a solo is on, it overrides mute — that is standard
and intended.

### The mixer only shows eight slots

By design: there are eight encoders. **Up**/**Down**, or pressing any pad, moves
to another row of eight. The display names which slots you are looking at.

### A pad I pressed opened a different slot than I expected

You are in another **bank**. There are 256 slots and 64 pads, so the grid shows
one bank of 64 at a time — the display names it (A–D) and **Page ◀/▶** moves it.
The grid flashes when you switch, which is the cue you missed.

### A sample I recorded has vanished from the library

Almost certainly the same thing: it is in a bank you are not looking at. The
library's display line names how many slots are filled **in this bank** and how
many in all four, so if the second number is bigger than the first, go looking
with **Page ◀/▶**.

### Bars I arranged are not on the grid any more

You are on another **song page**. Four pages of 64 bars each, and a sample page
shows one; **Shift**+**Page ◀/▶** moves it. The sample page's display line ends
with the page letter.

### The song stops at bar 64 instead of playing on

**Repeat** cycles what the loop covers, and it starts on `page` — which loops the
page you are working on and leaves the rest of the song waiting. Press **Repeat**
until the transport line says `loop song`.

### Playback starts somewhere I did not expect

**Play** starts at the loop's start, not always at bar 1. With a page loop, that
is the page you are on — which is usually what you wanted, but it means moving to
page C and pressing **Play** starts at bar 129.

### A project opened with triggers missing

The display says so on the way in: `dropped N trigger(s) past bar …`. A trigger
beyond the last page can never play, so it is dropped rather than kept as a
silent surprise. That happens with a file edited by hand, or one written by a
newer version with more pages.

### The song overview is all one colour

It is a density map, so a uniform colour means uniform density. If everything is
white, every 8×8 block has eight or more triggers in it — zoom in with a press to
see the detail. If everything is off, nothing is arranged **on this page and in
this bank**; the overview only counts what the window is showing.

### A scene did not restore what I expected

A scene holds **what is audible and where it plays** — mute state and trigger
sets. It deliberately does not touch the audio, the gain, your edits or your
layers, because those belong to the take rather than the arrangement.

A slot you recorded *after* storing the scene is left alone rather than emptied:
a scene is a variation, not a rollback of the whole library.

### The click is in my bounce

It is not — the click is never bounced. If you are hearing a tick in an export,
it came from the input while monitoring was on, not from the metronome.

If you want the click out of your *headphones* while keeping it for a player, set
**click output** on page 3 of **Setup** to a channel pair your interface actually
has. A channel it does not have quietly falls back to the main mix rather than
routing the click into silence.

### The browser will not delete a project

Two guards, both deliberate:

- **The button must be held** for about a second. Deleting a project is the one
  action in this program that **Undo** cannot reach.
- **You cannot delete the project you have open.** Open another one first.

### Undo will not go back far enough

The journal is 64 edits deep, and **opening another project clears it** — it
described the other song. Also, runs of similar edits made within about a
second and a half of each other merge into one step — so a sweep of the tempo
encoder is one undo, not forty. That is a feature, but it means the number of
presses needed is not the number of changes you made.

---

## Saving and bouncing

### "nothing to bounce yet"

No sample has any bars set, so the song is silent. Arrange something first.

### "no project directory to bounce into"

You started with `--no-save`. Use `--bounce OUT.wav SONG` from a terminal
instead, which writes where you tell it.

### "bounce failed: ..."

The message is the filesystem's. Usually a full or read-only disk, or a path
that does not exist.

### The bounce does not sound like what I heard

Expected differences, all of them intentional:

- **Muted samples are not in the bounce.** Muting is a mix decision, not a
  monitoring one.
- **The click is never in the bounce.**
- **Monitored input is never in the bounce.** It is not part of the song.

If something else differs, that is a bug worth reporting — see below.

### Did it save?

Look at the end of the transport line: a `*` means something is unwritten. It
saves itself a couple of seconds after the last change and again on exit, and
says `saved` when it does. **Shift**+**Setup** saves immediately.

If a save *fails*, the reason is on the display (`could not save: ...`) and the
pending write is dropped rather than retried every frame. Fix the cause — a full
disk, a read-only directory — and press **Shift**+**Setup**.

If you started with `--no-save`, nothing is ever written and there is never a
`*`.

### It opened the wrong project

With no project named, it reopens the one you had last. Name one explicitly to
override that. A remembered directory that no longer exists falls back to
`./song` rather than recreating it.

### It came back on the wrong page

It restores the library or a sample page, and nothing else — a record arm or a
bounce is never resumed. If the slot you were on has been deleted since, you get
the library.

### Bounced WAVs are 16-bit, not float

`soundfile` is not installed. The program falls back to its own 16-bit writer
rather than refusing. `pip install soundfile` for float files.

---

## The display

### The display stays dark

The display needs `pyusb` and `Pillow`, and a USB connection to the device
itself, separate from MIDI. Without them the program runs perfectly well — it
just has nowhere to put its messages, so you lose the status line.

```
pip install pyusb Pillow
```

On Linux you also need permission on the USB device. Quit Ableton Live, which
claims it.

Run with `--no-display` to stop it trying.

### "display error: ..."

The USB write failed, usually because the device went away. The rest of the
program is unaffected. Reconnect and restart.

---

## When it really is a bug

Reproduce it in the simulator and you have a bug report anyone can run, with no
hardware involved:

```
python -m push2sampler --sim my-song
```

See [the simulator](simulator.md) for the commands. A short list of simulator
commands that shows the wrong grid or the wrong status line is the most useful
thing you can send.

And if you have hardware, `hardware-report.json` from `--selftest` is the other
half: it is the only record of what a real Push 2 actually does with this
program.
