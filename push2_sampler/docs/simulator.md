# The simulator

The whole program, with no Push 2 and no audio device, driven from a terminal.

```
python -m push2sampler --sim my-song
```

What is real: every mode, the transport, the recorder, the arranger, the
arrangement, undo, the settings page, the editor, bouncing, and the project file.
The modes do not know they are being simulated.

What is fake: the control surface (you type instead of pressing) and the clock
(a plain thread runs the transport in wall-clock time instead of an audio
callback). There is no sound, and recording captures silence.

Which makes it good for three things:

- **Learning the program** without touching hardware, or while the Push is
  somewhere else.
- **Reporting a bug** that anyone can reproduce by pasting your lines back in.
- **Trying a gesture** you are not sure about before you do it to a real song.

---

## What you see

After every command it prints the 8×8 grid, the glyph legend, and the status
lines — which are exactly what the Push's display would be showing.

```
A . . . w . . .
G . . . w . . .
m . . . w . . .
w . . . w . . .
m . . . w . . .
w . . . w . . .
m . . . w . . .
w . . . w . . .
W m w white  G h g green  A a amber  R r red  B b blue  Y yellow  . off
  SLOT 1  2 bar(s)  audible
  plays on 2 bar(s)  gain 1.00  flat
  pad: toggle   hold+pad: paint   double tap: fill 4 bars
  Record: re-record   New: layer   Mute: hear   Device: edit
  PLAY  120 BPM  bar 1/64  loop  *
  in [###.........] mon off
```

The `*` at the end of the transport line means there are changes not yet written
to disk; it goes away a couple of seconds later when the autosave fires.

Upper case is bright, lower case is dim. That grid is a sample page: amber is the
playhead, green is a bar this sample plays on, and the dim white marks are the
4-bar and 16-bar ruler.

When a terminal is watching, the glyphs come out in the colour they name. Piped
to a file, or with `NO_COLOR` set, they stay plain — so the grids in a bug report
paste cleanly.

The `in [###...]` bar is the input meter. In the simulator it does not move,
because there is no input.

---

## Commands

### Pads

| | |
| --- | --- |
| `p 12` | press and release pad 12 (0–63, reading order: 0 is top-left) |
| `p 3,4` | the same pad by column,row |
| `hold 12` | press pad 12 and keep holding it |
| `rel 12` | release it |

`hold` / `rel` is how you reach anything that cares how long a pad is held — the
library's hold-to-audition, and painting a range of bars (`hold 3`, `p 11`,
`rel 3`).

`hold` and `rel` also take a **button** name, for the gestures that need one held
down: `hold tap` then `t +3` is the ±0.1 BPM nudge.

### Buttons

| | |
| --- | --- |
| `b play` | press a button by name |
| `play` | the same thing; the `b` is optional |
| `b1` … `b8` | the eight buttons *below* the display, whatever the current mode has put there |

Names: `play` `stop` `record`/`rec` `metronome`/`click` `repeat`/`loop` `mute`
`delete` `duplicate`/`dup` `tap` `new`/`layer` `mix`/`mixer` `solo`
`clip`/`song` `browse` `select`/`tag` `pageleft`/`pl` `pageright`/`pr`
`session`/`library`/`back` `left` `up` `down` `setup` `undo` `quantize`/`fixed`
`accent`/`velocity` `device`/`edit` `repair`/`fit`.

### Shift

Shift is a held modifier, so it is a state, not a press:

```
shift on
play          # Shift+Play -> perform mode
shift off
```

`shift on` / `shift off` (`1`/`0`, `true`/`false`, `down` also work).

### Encoders

| | |
| --- | --- |
| `t +4` | turn the tempo encoder 4 clicks up |
| `t -2` | and down |
| `k +1` | turn track encoder 1 |
| `k 3 +2` | turn track encoder 3 two clicks up |

Encoders 1–8 are the ones above the display. Which parameter each one owns
depends on the mode — on the settings and editor pages, one per column.

### Time and housekeeping

| | |
| --- | --- |
| `wait 2.5` | let the transport run 2.5 seconds |
| `g` / `s` | print the grid and status again |
| `?` | print the command list |
| `macro NAME cmd; cmd` | name a sequence, then run it by typing `NAME` |
| `q` | quit (and save) |
| `# anything` | a comment; ignored |

A macro may not shadow a real command or button name — it refuses rather than
quietly taking over `play`.

`wait` is the one to understand. Nothing advances while the REPL is waiting for
you to type, so to hear a count-in finish, or a take complete, or a playhead
move, you have to give it the time. A 2-bar take at 120 BPM with a 4-beat
count-in takes 6 seconds: `wait 7`.

---

## A scripted session

Commands can come from a file, which makes a reproducible demo — and, because it
exits with a status, something CI can run:

```
python -m push2sampler --script demo.sim --quiet --until-idle my-song
```

| Flag | Effect |
| --- | --- |
| `--script FILE` | Run FILE and exit. Implies `--sim`; `-` reads stdin |
| `--quiet` | Do not print the grid after every command |
| `--until-idle` | Once the script runs out, wait for the transport to stop |

The exit status is **0** unless a command failed, so a typo in a script is a
test failure rather than a silent no-op.

`--until-idle` applies *after* the script is exhausted, not between its lines —
a take finishing mid-script is not the end of the script. It is bounded at a
minute, because a looping transport never goes idle on its own.

Or pipe it, which works just as well for a one-liner:

```
printf 'p 0\np 1\nrecord\nwait 7\np 0\np 8\nplay\nwait 4\nq\n' \
  | python -m push2sampler --sim my-song
```

Line by line, that is the whole workflow:

| Line | What it is |
| --- | --- |
| `p 0` | press the empty top-left slot → Record mode |
| `p 1` | second pad: a 2-bar take |
| `record` | count in 4 beats, record 2 bars |
| `wait 7` | give it the 6 seconds that takes, and land on the sample page |
| `p 0` | this sample plays on bar 1 |
| `p 8` | and on bar 9 |
| `play` | run the song |
| `wait 4` | watch the playhead cross the first two bars |
| `q` | quit; the project is saved |

Check the result without the simulator at all:

```
python -m push2sampler --bounce /tmp/out.wav my-song
```

(Silence, in this case — the simulator recorded nothing. The *structure* is
real: 2 bars of sample on bars 1 and 9, in a 64-bar song.)

---

### One thing a script can surprise you with

The settings page is not simulated — it writes
`~/.config/push2sampler/settings.json` for real, the same file your hardware runs
use. A script that visits **Setup** and turns an encoder changes your actual
count-in, and the next script that relies on a 4-beat count-in will then be
waiting the wrong number of seconds.

So for anything you intend to run more than once, keep it out of the way:

```
python -m push2sampler --sim --no-settings my-song          # defaults, writes nothing
python -m push2sampler --sim --settings /tmp/demo.json my-song   # its own file
```

`--no-save` does the same for the project directory.

---

## A longer tour

Every mode, in one script. Run it with `--no-settings` (see above) and read the
grid after each step:

```
# record a 2-bar take into slot 1
p 0
p 1
record
wait 7

# arrange it on bars 1, 5, 9
p 0
p 4
p 8

# paint bars 17-24 on in one gesture
hold 16
p 23
rel 16

# double-tap bar 33: a 2-bar take fills the phrase as bars 33 and 35
p 32
p 32

# duplicate bars 1-8 onto bar 9: the gap between the presses is the length
dup
p 0
p 8

# name and colour the slot
select
p 0              # "kick"
p 59             # bottom row: a colour swatch
select

# the song overview, and a zoom into its first cell
clip
p 0
clip
clip

# bank B, and song page B
pr
s
pl
shift on
pr
shift off
s

# overdub a second pass onto the same take
new
wait 3
s                # the display now says "2 layers"
shift on
new              # ...and this peels it back off
shift off

# the mixer: gain, mute, solo, master
mix
k 1 -5           # turn slot 1 down
b1               # mute it
b1               # and back
solo
b1               # hear slot 1 alone
solo             # clear the solo
mix              # close

# shape it in the editor
device
k 1 +10          # trim 50ms off the front
k 4 +25          # 50ms fade out
k 8 +1           # normalise on
device           # close the editor

# velocity-sensitive, then perform it
accent
shift on
play
shift off
record           # WRITING
p 0
wait 2
p 0
delete           # erase as the playhead passes
wait 3
delete
session

# import a file from disk, if there is one to import
shift on
browse           # the import browser; --samples-root says where it starts
shift off
p 0              # highlight the first entry
p 0              # and open it, or import it
session

# settings
setup
k 1 +2           # count-in beats
b2               # cycle monitoring
setup

# undo the erase, then get back to the library and bounce
undo
undo
session
shift on
record
shift off
wait 2

# tempo: tap it, then nudge it finely
tap
tap
tap
tap
hold tap
t +3
rel tap
q
```

Leave the tempo block until last, as it is here. The REPL waits only 0.12 s
between lines, so four scripted taps read as a tempo far above the range and land
clamped at 240 BPM — which would then make your 4-bar take the wrong length for
the song and turn it yellow. Tapping is a gesture for hands, not for a script;
what a script can usefully show is that the taps are counted (`tap 2/4`), that the
fourth sets a tempo, and that `hold tap` + `t +3` moves it by 0.3.

Two things that script teaches better than prose:

That import block does nothing when the folder is empty, which is the point: it
says `nothing to import` rather than failing, so the tour runs anywhere.

- **Perform mode and the settings page are layers.** You entered them from the
  sample page, so leaving them puts you back on the sample page — not in the
  library. Hence the extra `session` before the bounce: **Shift**+**Record**
  bounces in the library, but re-records the take on a sample page. The status
  line always names the page you are on; read it before pressing something
  destructive.
- **Undo reports what it undid**, by name — `undo: bar 3 on`, `undo: velocity
  on`. Which two things the tour's pair of `undo`s takes back depends on
  everything above them, so read the messages rather than counting presses. If
  it says `nothing to undo`, the history is empty, not stuck.

---

## Using it as a bug report

The ideal report is a paste of the lines that produce the wrong thing, plus the
grid or status line you got and the one you expected. That is enough for anyone
to reproduce it on any machine, with no Push and no interface — and the grid is
unambiguous about what the program thought it was showing.

Hardware faults are the other half, and the simulator cannot see those. For
anything that looks like a control sending the wrong thing, or a colour coming
out wrong on the device, run the probe instead:

```
python -m push2sampler --selftest
```

See [Getting started, step 2](getting-started.md#step-2-run-the-probe).

---

## What the simulator will not tell you

- **Timing against a real clock.** The null backend advances the transport on a
  thread; it is close enough to watch a playhead, but not a measurement.
- **Anything about latency.** There is no input, so record-latency compensation
  cannot be judged here.
- **Whether audio actually works.** Device selection, dropouts, clipping and
  feedback are all real-device problems.
- **Whether the hardware matches.** Every control change number, palette colour
  and display byte in this program came from Ableton's documentation and is still
  unverified. The simulator faithfully reproduces our *assumptions*.
- **Whether a cable is plugged in.** `SimPush` never goes offline, so the
  reconnect handling is exercised by the tests rather than here.

What it *does* now reach is every control — but only because that keeps getting
caught rather than designed in. The mixer and overdub shipped with three buttons
that had no simulator name, making two whole features undriveable without
hardware; banks, the song page, the browser and the namer nearly did the same a
release later. **If you add a control, add its name to `BUTTONS` in `sim.py` in
the same change.**
