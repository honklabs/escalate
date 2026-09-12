# Troubleshooting

Symptom → cause → fix. Read the relevant row before concluding something is
broken; most of these are configuration, not faults.

Two things first:

1. **Run the probe.** `python -m push2sampler --selftest` tests the MIDI ports,
   the pads, the buttons, the encoders and the display one at a time and writes
   down what it found. If a control does nothing, the probe will tell you whether
   the program is looking at the wrong control change number — which is likely,
   because [nobody has run this on real hardware yet](README.md#one-thing-to-know-before-you-trust-it).
2. **Read the display.** Nearly every failure in this program announces itself
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

Press the Push's **User** button. This program speaks to the *User* port, which
only carries traffic when the Push is in user mode — in Live mode the Push
answers Live, not us.

If they are still dark, the program may have picked the wrong one of several
matching ports. Check what it chose:

```
python -m push2sampler --list-ports
```

It prefers a port with "User" in the name and avoids one with "Live". If your
port names are unusual, the probe's report will say so.

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

Record latency is set too high. Lower it.

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

### Undo will not go back far enough

The journal is 64 edits deep. Also, runs of similar edits made within about a
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

It saves itself a couple of seconds after the last change and again on exit.
**Shift**+**Setup** saves immediately and says `project saved`. If you started
with `--no-save`, nothing is ever written.

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
