"""Build the run sheet: every feature, and the buttons that show it working.

`feature_page.py` answers "what does this program do". This answers the
different question you have with the hardware actually in front of you: **what
do I press to see that.** So it is organised by *where you are on the
instrument* rather than by release -- eleven places, in the order you would
naturally reach them -- because a person holding a Push 2 navigates by page,
not by version number.

Like the feature page it reads the item list from `plans.md`, so a feature
cannot be left out by being forgotten: every code the plan carries needs a
recipe here or the build refuses. What the plan cannot supply is the recipe
itself, which is this file's content.

    python tools/demo_page.py out.html
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from feature_page import read_plan  # noqa: E402

#: Where you are when you do the thing.  Ordered the way you reach them.
#:
#: ``how`` is what gets you there from the library, which is where the program
#: opens and where `Session` always returns you -- so every recipe can assume
#: the library as its starting point and say only what is different.
GROUPS: tuple[tuple[str, str, str, str], ...] = (
    ("library", "The library", "where the program opens",
     "All 64 pads are sample slots. White is empty, green is filled. This is "
     "home: <b>Session</b> gets you back here from anywhere."),
    ("record", "Recording", "press a white pad in the library",
     "The pads become the length of the take, counted from the top-left."),
    ("sample", "A sample's own page", "tap a filled pad in the library",
     "The same 64 pads are now 64 bars of the song. This page has more on it "
     "than any other, because it is where a part is actually built."),
    ("editor", "The editor", "<b>Device</b> on a sample page",
     "The grid becomes the waveform. Nothing here touches the recording."),
    ("from_sample", "Pages you open from a sample", "one button each, from a sample page",
     "Each takes over the grid for one job and gives it back when you leave."),
    ("song", "Whole-song pages", "from anywhere",
     "The pages that are about the arrangement rather than one part."),
    ("perform", "Playing it in", "<b>Shift</b>+<b>Play</b>",
     "The pads stop navigating and start firing."),
    ("everywhere", "Everywhere, in every mode", "no navigation needed",
     "Transport, banks, pages and the things that are always true."),
    ("settings", "Settings", "<b>Setup</b>",
     "The pads go dark. Each button <i>below</i> the display owns one setting; "
     "the encoder above it changes the value. <b>Up</b>/<b>Down</b> reaches "
     "three pages."),
    ("terminal", "From a terminal", "no hardware needed for most of these",
     "The parts that are a command rather than a button."),
    ("underneath", "Underneath", "nothing to press",
     "Real features with no control of their own. Here is how you would "
     "satisfy yourself each one is doing its job."),
)

GROUP_KEYS = tuple(key for key, *_ in GROUPS)

#: code -> (group, steps, proof).  A step is ``(kind, what, why)``:
#:
#: * ``press`` -- a named button; ``+`` splits a chord into separate keycaps
#: * ``pad``   -- a gesture on the 8x8 grid
#: * ``turn``  -- an encoder (the row *above* the display)
#: * ``look``  -- nothing to do; the point is what is already on screen
#: * ``type``  -- a terminal command
#:
#: The kinds are not decoration: "press Shift+Clip" and "hold a pad for half a
#: second" are different physical acts, and a run sheet that rendered them the
#: same would be read wrong at speed.
RECIPES: dict[str, tuple[str, tuple, str]] = {

    # ---------------------------------------------------------- the library
    "CC-01": ("library", (
        ("pad", "hold a green pad for about half a second",
         "audition it without leaving the library"),
    ), "The pad turns amber while it plays, then back to green. You never left "
       "the library. <b>Shift</b> + a green pad does it instantly."),

    "NF-07": ("library", (
        ("press", "Page ▶", "bank B"),
        ("press", "Page ◀", "back to bank A"),
    ), "The whole grid flashes as it changes, and the display names the bank. "
       "256 slots in four banks — and a bank is only a <i>view</i>, so "
       "everything in every bank keeps playing whichever one you are looking at."),

    "NH-06": ("library", (
        ("press", "Shift+button 1 below the display", "store the whole arrangement in scene 1"),
        ("pad", "change some bars on a sample page, then come back", "make it different"),
        ("press", "button 1 below the display", "recall it"),
    ), "Your first arrangement is back. Eight scenes, for A/B-ing two versions "
       "of a chorus. One <b>Undo</b>."),

    "NH-05": ("library", (
        ("press", "Duplicate", "arms it; filled pads flash blue"),
        ("pad", "a green pad", "copies it to the next empty slot"),
    ), "Audio and arrangement both. The copy shares the original's audio until "
       "one of them is edited, so duplicating a long take costs nothing. "
       "<b>Shift</b> on the second press <i>moves</i> it instead."),

    "CC-19": ("library", (
        ("press", "Shift+Duplicate", "arms the swap; filled pads flash cyan"),
        ("pad", "the first pad", "holds white — “this one”"),
        ("pad", "the second pad", "they trade places"),
    ), "Everything moves: audio, bars, name, colour, gain, play mode, choke "
       "group. The slot <i>numbers</i> stay put, because a slot number is "
       "identity everywhere else. Pressing the same pad twice cancels."),

    "NF-05": ("library", (
        ("press", "Shift+Record", "bounce the whole song to a WAV"),
    ), "An amber bar fills the grid as it renders, then the display names the "
       "file in <code>bounces/</code>. It is computed between frames, so the "
       "surface stays live while it works."),

    "NF-12": ("library", (
        ("press", "Play", "start the song"),
        ("press", "Shift+Session", "master playback"),
    ), "The same grid with nothing to edit — each pad <b>flashes white as its "
       "sample fires</b>. The flash marks the <i>attack</i>, not the duration, "
       "so a four-bar pad blinks once instead of holding its pad lit for four "
       "bars. <b>Delete</b>, <b>Mute</b> and <b>Duplicate</b> do nothing here "
       "on purpose: this is the page where you listen."),

    "CC-13": ("library", (
        ("press", "Setup", "settings"),
        ("press", "Down", "settings page 2"),
        ("turn", "encoder 5", "dim library on / off"),
    ), "Every filled pad drops to a lower brightness. Sixty-four pads at full "
       "tilt is glare rather than information."),

    # ---------------------------------------------------------- recording
    "NH-03": ("record", (
        ("press", "Metronome", "click on/off — works anywhere"),
        ("press", "Setup", "then encoder 1: count-in beats"),
        ("press", "Down", "twice, for settings page 3"),
        ("turn", "encoders 1–5", "pre-roll, click sound, volume, rec-only, output"),
    ), "The count-in is four beats by default. Pre-roll runs the <i>song</i> "
       "for a bar or two first, so you arrive at a take already in the groove "
       "rather than starting cold on a downbeat."),

    "NH-08": ("record", (
        ("press", "Setup", "settings"),
        ("press", "Down", "page 2"),
        ("turn", "encoders 1–3", "auto trim, auto normalise, auto fade"),
    ), "All three are <b>off by default</b> — a program that silently edits "
       "your recording is one you cannot trust. With auto-trim on, the leading "
       "silence is gone the moment a take lands."),

    "F-09": ("record", (
        ("turn", "the tempo encoder", "change the BPM after recording something"),
        ("look", "the library", "the take's pad has gone yellow"),
    ), "Yellow means the recording is no longer the right length for its bars. "
       "It is not a fault — the loop really is the wrong length now. "
       "<b>Button 1</b> on its sample page fits it; <b>button 6</b> stretches "
       "it instead."),

    # ------------------------------------------------- a sample's own page
    "CC-06": ("sample", (
        ("look", "the empty pads", "a faint white ruler"),
    ), "Faint marks fall on bars 1 and 5 of every row, brighter every 16 bars. "
       "You can count phrases without counting pads."),

    "CC-11": ("sample", (
        ("pad", "hold one bar", "and keep holding"),
        ("pad", "press another bar", "fills everything between them"),
    ), "One undo step however many bars it wrote. Whether it fills or clears "
       "is whatever the <i>held</i> pad's own press produced."),

    "CC-12": ("sample", (
        ("pad", "double-tap an empty bar", "lays the take across the next four"),
    ), "Spaced by the take's own length, so a two-bar loop lands on bars 1, 3, "
       "5, 7. Double-tapping a playing bar clears those four instead."),

    "NH-04": ("sample", (
        ("press", "New", "overdub another pass on top"),
        ("press", "Shift+New", "peel the last layer back off"),
    ), "Sound on sound: the layers sum. The display counts them, and both "
       "directions are one undo step. Layers are kept in the project, so you "
       "can still remove one after a reload."),

    "IN-06": ("sample", (
        ("press", "Shift+Record", "record another take <i>beside</i> this one"),
        ("turn", "encoder 3", "which take you are hearing"),
        ("turn", "encoder 4", "fixed / cycle / random"),
    ), "Up to eight takes on one pad. <code>cycle</code> advances one take per "
       "pass; <code>random</code> picks per trigger, from the project's dice, "
       "so it is the same every time you play it. Three real performances of "
       "one snare on <code>random</code> is the difference between a sampler "
       "and a drummer."),

    "NF-10": ("sample", (
        ("press", "Accent", "velocity sensitivity on"),
        ("pad", "hit some bars hard and others softly", "the velocity is stored"),
    ), "Bars you hit softly are a dimmer green. The sample plays at that level "
       "on that bar. <b>Accent</b> again puts the part back to flat."),

    "NH-02": ("sample", (
        ("turn", "encoder 2", "lay this sample back behind the beat"),
    ), "0–120 ms in 5 ms steps, shown as <code>+20ms</code>. That is what "
       "groove means when your grid is bars: a clap a hair behind the kick. "
       "<b>Late only</b> — to push one sample ahead, lay everything else back, "
       "because a bar line is the earliest moment the engine knows about."),

    "NH-10": ("sample", (
        ("pad", "press a bar", "select it"),
        ("press", "hold Shift", "and keep holding"),
        ("turn", "encoder 2", "how likely that bar is: 5–100%"),
        ("turn", "encoder 3", "or: play only on every Nth pass"),
        ("turn", "encoder 4", "the project's dice, 0–63"),
    ), "An uncertain bar <b>flashes</b> green rather than dimming — brightness "
       "on this page already means recorded velocity. Same dice, same song: "
       "the roll is a pure function of position, so bar 40 of pass 3 sounds "
       "the same whether you played from the top, dropped in halfway, or "
       "bounced the file."),

    "NF-02": ("sample", (
        ("press", "buttons 2–5 below the display", "one shot / loop / gate / retrig"),
        ("press", "button 8 below the display", "choke group: off → 1…8 → off"),
    ), "How the sample <i>ends</i>. <code>gate</code> stops it at the end of "
       "its bar however long the audio is — what a four-bar pad needs when the "
       "next chord arrives. A choke group makes samples cut each other, the "
       "way a closed hat silences an open one; a sample never chokes itself, "
       "which is what <code>retrig</code> is for."),

    "NH-09": ("sample", (
        ("turn", "the tempo encoder", "move the BPM so the take no longer fits"),
        ("press", "button 6 below the display", "off → what it suggests → the other → off"),
    ), "<code>resample</code> moves the pitch (usually right for a drum "
       "break); <code>stretch</code> holds the pitch and changes the length "
       "(right for a bass line). It offers whichever the material wants first. "
       "Computed between frames, so the take keeps playing at its old length "
       "until the new one is ready."),

    "CC-03": ("sample", (
        ("press", "Shift+Delete", "delete this sample"),
    ), "If the sample plays anywhere, the display says <code>slot 7 plays on "
       "12 bars — press again</code> and nothing happens until you do. "
       "<b>Delete</b> disarms itself after three seconds."),

    # ---------------------------------------------------------- the editor
    "NF-03": ("editor", (
        ("press", "Device", "open the editor from a sample page"),
        ("pad", "press a pad", "hear the take from that point"),
        ("turn", "encoders 1–8", "trim in/out, fades, pitch, gain, reverse, normalise"),
        ("press", "Shift+Device", "fold the edits into the recording for good"),
    ), "The grid is the waveform, bright where it is loud, with the parts you "
       "are trimming away in <b>dim red</b>. Nothing touches the recording "
       "until that last press — and even that is one undo step. A turn and the "
       "next turn within a second and a half merge into one undo."),

    "IN-09": ("editor", (
        ("press", "Device", "the editor"),
        ("press", "Select", "trim by ear — it starts playing and does not stop"),
        ("pad", "tap any pad when you hear the start", "a short loop of that spot begins"),
        ("press", "button 1 below the display", "snap to the nearest attack"),
        ("turn", "encoder 1 / 2", "coarse 20 ms / fine 1 ms"),
        ("press", "Select", "that's it — it plays on"),
        ("pad", "tap any pad when you hear the end", ""),
        ("press", "Select", "done"),
    ), "<b>Select</b> always means the same thing: <i>that's it.</i> Hunting, "
       "that is <i>here is the point</i>; tuning, <i>the point is right, move "
       "on</i>. Any pad, not the one under the playhead — you are tapping in "
       "time, not aiming. <b>If you hear a click at the loop, your start has "
       "landed mid-note</b>: that is deliberate, and it is telling you to move "
       "it. <b>Delete</b> gives up and the take is untouched."),

    # ------------------------------------------- pages opened from a sample
    "IN-01": ("from_sample", (
        ("press", "Convert", "the slice page"),
        ("press", "button 3 below the display", "cut at transients"),
        ("turn", "encoder 1", "transient sensitivity"),
        ("pad", "press a pad", "hear that slice"),
        ("press", "Convert", "write them into the free slots"),
    ), "One recording becomes up to 64 playable pieces, laid across the pads "
       "at its own attacks. Buttons 1 and 2 cut by bars and beats instead. "
       "Each slice is one bar whatever its length, named <code>take/1</code>, "
       "<code>take/2</code>…, and the whole conversion is one <b>Undo</b>. "
       "<b>Shift</b>+<b>Convert</b> removes the original too."),

    "IN-02": ("from_sample", (
        ("press", "Layout", "the about page"),
        ("look", "the pads", "a spectrogram: time across, frequency up"),
        ("press", "button 1 below the display", "accept the name it suggests"),
    ), "A kick sits along the bottom, a hat across the top, a held note is one "
       "horizontal line. It reports what it heard — role, pitch, tempo, "
       "brightness — and <b>every reading carries its confidence</b>: a weak "
       "one says <code>not sure</code> rather than being rounded into a fact."),

    "IN-08": ("from_sample", (
        ("press", "Layout", "the about page"),
        ("press", "button 2 below the display", "switch to the timing scatter"),
    ), "Every hit as a dot: time across, <b>early above</b> the line and "
       "<b>late below</b>. Green within 10 ms, amber within 25, red beyond. "
       "Two separate facts — <i>evenness</i> is how consistent you are, "
       "<i>placement</i> is where you sit. Consistently 20 ms behind is a "
       "groove; 5 ms out at random is not. <b>It never quantizes.</b> "
       "<code>--coach</code> shows it after every take."),

    "IN-03": ("from_sample", (
        ("press", "Automate", "the pattern page"),
        ("turn", "encoder 1", "density — how many bars play"),
        ("turn", "encoder 3", "euclid / every n / random / mirror"),
        ("turn", "encoder 5", "length — how long before it repeats"),
        ("press", "Automate", "keep it"),
    ), "The grid <b>flashes</b> a preview and nothing is stored until that "
       "second press; <b>Session</b> discards it. <b>Length is the one that "
       "matters</b>: three bars over 64 is one hit every 21 bars, three over "
       "8 repeating is the tresillo. Pads do not edit here, because the next "
       "encoder click would wipe what you tapped."),

    "IN-04": ("from_sample", (
        ("press", "Scale", "the harmony page"),
        ("pad", "press any filled pad", "hear it, and read how it sits"),
        ("press", "button 1 below the display", "transpose it into line"),
    ), "The library, coloured against one reference slot (flashing). Green "
       "fits, amber is a note or two apart, red clashes, dim white is a drum "
       "— nothing with a key in it, so nothing to compare. The colours come "
       "from <b>pitch-class content, not from a key name</b>: naming a tonic "
       "is the measurably weak part, so the key is shown and labelled a guess. "
       "The transpose is the editor's own pitch edit, so it is undoable and "
       "visible there."),

    "IN-05": ("from_sample", (
        ("press", "Shift+Clip", "the living song page"),
        ("turn", "encoder 1", "how often — every 2 to 8 passes"),
        ("turn", "encoder 2", "how much — extra bars"),
        ("press", "Shift+Record", "freeze that many passes as one file"),
    ), "Extra bars a part plays on <b>only every Nth pass</b> — “every "
       "fourth pass, double the hats”. Amber is the pass it plays, "
       "<b>flashing amber is the pass before</b>, dim blue is waiting its "
       "turn. It is stored as bars you can look at, not a rule you have to "
       "trust."),

    "CC-17": ("from_sample", (
        ("press", "Select", "the naming page"),
        ("pad", "press a word", "the slot is named"),
    ), "The top seven rows are words — eight categories of eight, from "
       "<code>kick</code> and <code>snare</code> through <code>bass</code>, "
       "<code>chord</code>, <code>vox</code> and <code>riser</code>; the "
       "buttons below jump between categories. A second <code>kick</code> "
       "names itself <code>kick 2</code>. There is no keyboard on a Push, and "
       "twenty takes called <code>S01</code> to <code>S20</code> are "
       "unfindable."),

    "CC-18": ("from_sample", (
        ("press", "Select", "the naming page"),
        ("pad", "press one of the bottom row", "eight colours"),
    ), "The slot shows in that colour in the library, so a full bank becomes "
       "readable at a glance. The same colour again clears it. Muted and "
       "sounding still look the way they always did."),

    # ------------------------------------------------------ whole-song pages
    "NF-01": ("song", (
        ("press", "Clip", "the song overview"),
        ("pad", "press a pad", "zoom into that cell"),
        ("press", "Clip", "zoom out, then leave"),
    ), "The whole arrangement as a heat map — each pad is <b>8 bars × 8 "
       "slots</b>, columns bars and rows slots. Off is none, dim blue is one "
       "trigger, blue 2–3, amber 4–7, white 8 or more, and the playing column "
       "is one rung brighter. Zoomed in, each pad is one bar of one slot."),

    "NH-01": ("song", (
        ("press", "Mix", "the mixer"),
        ("turn", "encoders 1–8", "gain per strip"),
        ("press", "buttons below the display", "mute a strip"),
        ("press", "Solo", "then a button below — solo that strip"),
    ), "Eight strips at a time as vertical meters, filling upwards: green, "
       "amber in the top quarter, red at the very top. <b>Solo overrides mute "
       "without destroying it</b> — un-solo and your mix is exactly as it was. "
       "<b>Up</b>/<b>Down</b> reaches another row of eight."),

    "NH-11": ("song", (
        ("type", "python -m push2sampler --out-channels 4 my-song",
         "you need somewhere to route to"),
        ("press", "Mix", "the mixer"),
        ("press", "Shift+a strip button", "main → 3/4 → 5/6 → 7/8 → main"),
    ), "A routed slot <b>leaves the main mix</b>, so headphones on that pair "
       "hear it alone — that is a cue bus. It is therefore not in a bounce, "
       "which is the main outputs, but it is in full in its own stem. A pair "
       "your device has not got falls back to <code>main</code> and is flagged "
       "with <code>!</code>."),

    "NF-06": ("song", (
        ("press", "Browse", "the project browser"),
        ("pad", "press a pad", "highlight that project"),
        ("pad", "the same pad again", "open it"),
    ), "Switch songs from the pads, with no terminal and <b>without restarting "
       "the audio</b>. Green has samples, dim white is empty, dim amber is the "
       "one you have open. Opening saves your current song first. Button 2 "
       "makes a new one, button 3 duplicates, and button 5 held deletes."),

    "NF-08": ("song", (
        ("press", "Shift+Browse", "the import browser"),
        ("pad", "press a pad", "highlight it; the display says what it is"),
        ("pad", "the same pad again", "open the folder, or import the file"),
    ), "A file browser on the pads — white for folders, blue for audio. "
       "Nothing is highlighted until you press something, so a first press can "
       "never import by accident. The file is resampled to the session rate "
       "and <b>never stretched</b>: a 3.5-bar file stays 3.5 bars and is "
       "flagged off-grid. It lands in the first empty slot, never over a take, "
       "as one <b>Undo</b>."),

    "NF-11": ("song", (
        ("press", "Shift+Page ▶", "song page B"),
        ("press", "Shift+Page ◀", "back to A"),
    ), "Four pages of 64 bars — 256 bars, about eight minutes, playing "
       "consecutively. The display names which page you are on, and "
       "<b>Repeat</b> decides whether the loop is this page, the whole song, "
       "or off."),

    # ------------------------------------------------------------- perform
    "NF-04": ("perform", (
        ("press", "Shift+Play", "perform mode; the loop starts"),
        ("press", "Fixed Length", "quantize: 1 bar → off → 1/16 → 1/8 → 1/4 → 1/2"),
        ("pad", "hit filled pads in time", "they fire at the next grid line"),
        ("press", "Record", "now what you play is written in (<code>WRITING</code>)"),
    ), "Quantize defaults to <b>1 bar</b>, the coarsest, so your first press "
       "lands on a downbeat rather than wherever your hand was. With "
       "<b>Record</b> on, a fired pad is written at the bar where it "
       "<i>sounded</i>, not where you pressed — so a late hit still lands on "
       "the bar. <b>Delete</b> erases bars as the playhead crosses them."),

    # ---------------------------------------------------------- everywhere
    "CC-02": ("everywhere", (
        ("press", "Shift+Stop", "stop at the end of the current bar"),
        ("press", "Stop", "stop now"),
        ("press", "Stop", "again — disarm whatever was armed"),
    ), "The display reads <code>ENDING</code> while a bar-line stop is "
       "pending. Two Stops is the panic button: whatever you armed by accident "
       "is now disarmed."),

    "CC-07": ("everywhere", (
        ("press", "Play", "start the song"),
        ("look", "any page with bars on it", "the playhead is there too"),
    ), "White where the sample is silent, amber on a bar where it plays. On "
       "the song overview the playing column is one rung brighter; in the "
       "editor and the trim page it runs across the waveform."),

    "IN-07": ("everywhere", (
        ("press", "Record", "watch the count-in fill a ring round the grid"),
        ("look", "the rightmost column", "it pulses on the beat, in every mode"),
        ("pad", "touch the strip while stopped", "scrub the song"),
    ), "The ring is one pad per sixteenth — a shape you can feel filling "
       "rather than a number you have to read, and it leaves the middle of the "
       "grid alone. The beat pulse never overwrites a pad the page is using. "
       "<b>Shift</b> + the strip picks a loop range instead. "
       "<i>The touch strip has never been verified on real hardware — if it "
       "does nothing, that is why.</i>"),

    "F-04": ("everywhere", (
        ("press", "Undo", "take back the last edit"),
        ("press", "Shift+Undo", "redo it"),
    ), "Sixty-four deep. A lit <b>Undo</b> means there is something to take "
       "back and a dark one means there isn't. One sweep of an encoder is "
       "<i>one</i> step rather than forty, because turns within a second and a "
       "half merge."),

    "NH-07": ("everywhere", (
        ("press", "Tap Tempo", "four times, in time"),
        ("turn", "the tempo encoder", "±1 BPM"),
        ("turn", "Shift + the tempo encoder", "±10 BPM"),
        ("turn", "hold Tap Tempo + the tempo encoder", "±0.1 BPM, for beat-matching"),
    ), "<b>Shift</b>+<b>Tap Tempo</b> throws the taps away if you lose it "
       "halfway."),

    "CC-08": ("everywhere", (
        ("look", "the bottom of the display", "bar, beat and tempo, large"),
    ), "Readable from across a room, which is the point — you glance at it "
       "mid-take rather than reading it. It grows <code>· pass 3</code> only "
       "once something in the song actually uses passes."),

    "CC-20": ("everywhere", (
        ("look", "the top of the display", "the mode you are in"),
        ("press", "Device", "from a sample page — the banner now reads <code>EDIT over SAMPLE 7</code>"),
    ), "Large, always the same place, always the same words. The <code>over</code> "
       "form matters: knowing you will come back to the sample page is exactly "
       "what people get wrong about a page opened on top of another. Red while "
       "recording, amber while armed for something destructive, white "
       "otherwise — and only where the words already say the same thing."),

    "CC-05": ("everywhere", (
        ("press", "any button at all", "its own LED lights briefly"),
    ), "Whether or not the current page does anything with it. A button that "
       "does not light is a dead button, and you find that out in a second "
       "rather than wondering whether the feature is broken."),

    "CC-10": ("everywhere", (
        ("pad", "change anything", "a <code>*</code> appears on the transport line"),
        ("look", "a couple of seconds later", "<code>saved</code>"),
    ), "It saves itself after any change and on exit. <b>Shift</b>+<b>Setup</b> "
       "writes immediately if you would rather not wait."),

    "F-03": ("everywhere", (
        ("pad", "tap a filled pad", "a sample page"),
        ("press", "Device", "the editor, opened over it"),
        ("press", "Session", "back to the sample page — not to the library"),
    ), "Pages layer instead of replacing each other, so leaving one puts you "
       "back where you were. The display's banner says so while you are there."),

    "CC-14": ("everywhere", (
        ("press", "Play", "start the song"),
        ("look", "now unplug the Push's USB", "the music keeps playing"),
        ("look", "plug it back in", "the grid relights itself"),
    ), "The display reads <code>SURFACE OFFLINE</code> while it is gone. The "
       "audio never depended on the surface, and it reconnects by itself."),

    # ----------------------------------------------------------- settings
    "F-06": ("settings", (
        ("press", "Setup", "the settings page"),
        ("press", "button 1–8 below the display", "reset or cycle that setting"),
        ("turn", "the encoder above it", "change its value"),
        ("press", "Up / Down", "three pages of settings"),
    ), "The pads go dark on purpose — nothing here is a pad. <b>Setup</b> "
       "again closes it and writes "
       "<code>~/.config/push2sampler/settings.json</code>. Changing the input "
       "device or block size restarts the audio stream; if the new one will "
       "not open, <b>the old one is kept</b> and the display says why."),

    "F-07": ("settings", (
        ("look", "the row of buttons above the display", "an input level meter"),
        ("press", "Shift+Metronome", "monitoring: off → auto → on"),
    ), "The eight buttons above the display are a meter, not controls. "
       "<code>auto</code> is the useful one: you hear the input only while a "
       "take is running, which is when a player needs it and the only time it "
       "will not feed back."),

    # ----------------------------------------------------------- terminal
    "CC-16": ("terminal", (
        ("type", "python -m push2sampler doctor", "what it can and cannot see"),
        ("type", "python -m push2sampler --version", ""),
    ), "One row per thing that matters — Python, each optional package, the "
       "MIDI ports and audio devices it can find, whether it can write where "
       "you are — each with a one-line fix beside anything missing. It always "
       "exits 0, because “everything is missing” is a diagnosis, not "
       "a crash."),

    "CC-15": ("terminal", (
        ("type", "python -m push2sampler --sim my-song", "the whole program, in a terminal"),
        ("type", "p 0", "press pad 0"),
        ("type", "record", "press the Record button"),
        ("type", "wait 7", "let the transport run"),
    ), "Every mode, the transport, the recorder, undo, bouncing and the "
       "project file are real; only the surface and the clock are faked. The "
       "modes do not know. Add <code>--monitor-port</code> and you get the "
       "grid in a browser in real colours as you type."),

    "NF-05.stems": ("terminal", (), ""),  # placeholder removed below

    "CC-09": ("terminal", (
        ("type", "python -m push2sampler --calibrate", "measure your input latency"),
    ), "It plays a click, listens for it coming back, and stores the number. "
       "Everything you record afterwards is aligned by it. You can also set it "
       "by hand on settings page 1, encoder 4."),

    "NF-09": ("terminal", (
        ("type", "python -m push2sampler --clock midi_slave --clock-port \"my drum machine\"", ""),
        ("type", "python -m push2sampler --clock midi_master", "or send it instead"),
    ), "Tracks to 0.3 ms over 32 bars — <i>measured against a synthetic "
       "sender, never yet against real gear.</i> Ableton Link is a seam with "
       "nothing behind it and says so rather than pretending; MIDI clock is "
       "the sync that works."),

    "NH-12": ("terminal", (
        ("type", "python -m push2sampler --monitor-port my-song", ""),
        ("look", "http://localhost:8765/", "the surface in a browser"),
    ), "The pads in their real colours, the banner, the transport, the display "
       "text and every lit button, updated as it happens. <b>Read-only</b> — "
       "every verb but GET is refused — and <b>loopback only</b> unless you "
       "say otherwise, because read-only is not private and the page carries "
       "your slot names. Works with <code>--sim</code>, which is how you watch "
       "the LEDs with no hardware at all."),

    "F-08": ("terminal", (
        ("type", "python -m push2sampler --selftest", "the guided hardware probe"),
        ("type", "python -m push2sampler --led-test", "if the pads stay dark"),
        ("type", "python -m push2sampler --midi-probe", "if that finds nothing either"),
    ), "Nine checks — ports, grid orientation, the notes the corner pads send, "
       "velocity, every palette colour, 35 buttons, the encoders, the strip, "
       "the display — writing <code>hardware-report.json</code> and a markdown "
       "version whose first table is exactly the list of corrections to make. "
       "<b>It has still never been completed on a device</b>, and it is the "
       "one thing this project cannot do for itself."),

    # --------------------------------------------------------- underneath
    "F-01": ("underneath", (
        ("press", "Setup", "then encoder 8: drop the block size right down"),
        ("press", "Play", "and work the surface hard while it plays"),
    ), "The audio callback never waits on a lock, so a slow screen redraw "
       "cannot become an audible dropout. If one ever does happen the display "
       "says <code>audio dropout</code> with a count — it is reported rather "
       "than hidden, which is the actual feature."),

    "F-02": ("underneath", (),
     "Nothing to press: every mode lives in its own file behind one small "
     "interface, instead of one file that knew about all of them. You would "
     "only notice it by adding a page — which is why the program now has "
     "twenty of them."),

    "F-05": ("underneath", (
        ("press", "Shift+Play", "perform mode"),
        ("pad", "fire the same pad twice, fast", "no click where the first one is cut"),
    ), "Three-millisecond fades on every voice start, stop and steal. The "
       "thing to listen for is the <i>absence</i> of a click — which is also "
       "why the one place a click survives on purpose (a trim landing "
       "mid-note) carries information."),

    "CC-04": ("underneath", (
        ("type", "python -m push2sampler", "with no project name at all"),
    ), "You get back the project, bank, song page and slot you left. It is a "
       "bookmark rather than a setting, so it is kept out of the settings "
       "page."),
}

# The stems export shares NF-05's item; the placeholder above only existed to
# make that obvious while writing, and must not reach the page.
RECIPES.pop("NF-05.stems", None)


def check(items) -> list[str]:
    """Problems that should stop a build, as sentences."""
    problems = []
    codes = {item.code for item in items}
    missing = sorted(codes - set(RECIPES))
    if missing:
        problems.append(f"no recipe for: {', '.join(missing)} (add one in RECIPES)")
    orphan = sorted(set(RECIPES) - codes)
    if orphan:
        problems.append(f"recipe for an item the plan does not have: {', '.join(orphan)}")
    for code, (group, _steps, _proof) in sorted(RECIPES.items()):
        if group not in GROUP_KEYS:
            problems.append(f"{code} is in group {group!r}, which does not exist")
    return problems


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _cap(part: str) -> str:
    """One keycap, or prose.

    A button's engraved label starts with a capital; anything else is an
    instruction ("a strip button", "the tempo encoder") and stays prose,
    because there is nothing on the panel reading *the tempo encoder*.
    """
    if part[:1].isupper() or part.startswith("button"):
        return f'<kbd>{_esc(part)}</kbd>'
    return f'<span class="prose">{_esc(part)}</span>'


def _keys(text: str) -> str:
    """Render ``Shift+Page ▶`` as two keycaps, and ``Up / Down`` as a choice.

    The two separators mean opposite things -- ``+`` is *both at once* and
    ``/`` is *either one* -- so they cannot render the same. Writing
    ``Up / Down`` as one keycap was the first version, and it invents a button
    that does not exist.
    """
    chords = []
    for alternative in text.split("/"):
        parts = [part.strip() for part in alternative.split("+") if part.strip()]
        chords.append('<span class="plus">+</span>'.join(_cap(p) for p in parts))
    joined = '<span class="slash">or</span>'.join(chords)
    return f'<span class="chord">{joined}</span>'


KIND_LABEL = {
    "press": "press",
    "pad": "pad",
    "turn": "turn",
    "look": "look",
    "type": "type",
}


def _step(kind: str, what: str, why: str) -> str:
    if kind == "press":
        body = _keys(what)
    elif kind == "type":
        body = f'<code class="cmd">{_esc(what)}</code>'
    else:
        body = f'<span class="prose">{_esc(what)}</span>'
    gloss = f'<span class="why">{why}</span>' if why else ""
    return (f'      <li class="step step-{kind}">'
            f'<span class="kind">{KIND_LABEL[kind]}</span>'
            f'<span class="what">{body}</span>{gloss}</li>')


def _entry(item, recipe) -> str:
    _group, steps, proof = recipe
    if steps:
        body = ('    <ol class="steps">\n'
                + "\n".join(_step(*step) for step in steps)
                + "\n    </ol>")
    else:
        body = '    <p class="nothing">Nothing to press.</p>'
    return f"""  <article class="entry" data-find="{_esc((item.code + ' ' + item.title).lower())}">
    <header class="entry-head">
      <h3>{_esc(item.title)}</h3>
      <span class="code">{_esc(item.code)}</span>
    </header>
{body}
    <p class="proof">{proof}</p>
  </article>"""


def _section(key: str, title: str, how: str, blurb: str, items) -> str:
    entries = [item for item in items if RECIPES[item.code][0] == key]
    if not entries:
        return ""
    rows = "\n".join(_entry(item, RECIPES[item.code]) for item in entries)
    return f"""<section class="place" id="{key}">
  <header class="place-head">
    <div class="place-title">
      <h2>{_esc(title)}</h2>
      <p class="how">{how}</p>
    </div>
    <p class="count">{len(entries)} thing{'s' if len(entries) != 1 else ''} to try</p>
    <p class="place-blurb">{blurb}</p>
  </header>
{rows}
</section>"""


def build(version: str) -> str:
    _trains, items = read_plan()
    problems = check(items)
    if problems:
        raise SystemExit("; ".join(problems))
    sections = "\n\n".join(
        _section(key, title, how, blurb, items) for key, title, how, blurb in GROUPS
    )
    jumps = "\n".join(
        f'    <a href="#{key}">{_esc(title)}</a>'
        for key, title, _how, _blurb in GROUPS
        if any(RECIPES[i.code][0] == key for i in items)
    )
    return TEMPLATE.format(
        sections=sections, jumps=jumps, total=len(items), version=_esc(version),
    )


TEMPLATE = """<title>Push 2 Run Sheet</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* The instrument is a dark slab with engraved keycaps and coloured pads; this
   page is the sheet you prop against it, so the ground is paper-ish and the
   only things that look like hardware are the keycaps. */
:root {{
  --paper:    #f4f4f1;
  --card:     #ffffff;
  --sunk:     #ececeA;
  --rule:     #dcdcd6;
  --rule-soft:#e8e8e3;
  --ink:      #191a1d;
  --ink-2:    #4a4e58;
  --muted:    #71757f;
  --accent:   #b35600;
  --accent-soft: #f0e3d4;
  /* One hue per kind of action, so a run sheet can be read at speed. */
  --press:    #1f4fd6;
  --pad:      #0f8a3d;
  --turn:     #8a5a00;
  --look:     #6b6f7e;
  --type:     #7a3aa8;
  --cap-face: #2b2f36;
  --cap-edge: #14171b;
  --cap-ink:  #eceef2;
  --shadow:   0 1px 2px rgba(20,22,26,.06);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:    #131418;
    --card:     #1a1c21;
    --sunk:     #212429;
    --rule:     #2c3038;
    --rule-soft:#22252b;
    --ink:      #eceef2;
    --ink-2:    #b4b9c4;
    --muted:    #838896;
    --accent:   #ff8c1a;
    --accent-soft: #3a2a14;
    --press:    #6f97ff;
    --pad:      #35c96d;
    --turn:     #e0a63a;
    --look:     #8d92a0;
    --type:     #bb8ce6;
    --cap-face: #333841;
    --cap-edge: #0d0f12;
    --cap-ink:  #eceef2;
    --shadow:   0 1px 0 rgba(255,255,255,.04);
  }}
}}
:root[data-theme="dark"] {{
  --paper:    #131418;
  --card:     #1a1c21;
  --sunk:     #212429;
  --rule:     #2c3038;
  --rule-soft:#22252b;
  --ink:      #eceef2;
  --ink-2:    #b4b9c4;
  --muted:    #838896;
  --accent:   #ff8c1a;
  --accent-soft: #3a2a14;
  --press:    #6f97ff;
  --pad:      #35c96d;
  --turn:     #e0a63a;
  --look:     #8d92a0;
  --type:     #bb8ce6;
  --cap-face: #333841;
  --cap-edge: #0d0f12;
  --cap-ink:  #eceef2;
  --shadow:   0 1px 0 rgba(255,255,255,.04);
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding-block: 0 64px;
  padding-left: 20px;
  padding-right: 20px;
  background: var(--paper);
  color: var(--ink);
  font: 400 16px/1.55 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.page {{ max-width: 980px; margin: 0 auto; }}
h1, h2, h3 {{ margin: 0; font-family: Archivo, ui-sans-serif, system-ui, sans-serif; text-wrap: balance; }}
p {{ margin: 0; }}
a {{ color: inherit; }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }}
code, kbd, .mono {{ font-family: "IBM Plex Mono", ui-monospace, monospace; }}
.primer code, .proof code, .why code, footer code {{
  font-size: .86em; background: var(--sunk); border: 1px solid var(--rule-soft);
  border-radius: 3px; padding: 1px 5px; overflow-wrap: anywhere;
}}

/* ---------------------------------------------------------- masthead */
header.top {{ padding-block: 40px 26px; display: flex; flex-direction: column; gap: 14px; }}
.eyebrow {{
  font-family: "IBM Plex Mono", monospace; font-size: 11.5px; font-weight: 500;
  letter-spacing: .18em; text-transform: uppercase; color: var(--muted);
}}
h1 {{ font-size: clamp(30px, 5.6vw, 48px); font-weight: 700; letter-spacing: -.025em; line-height: 1.03; }}
.lede {{ color: var(--ink-2); max-width: 62ch; font-size: 17px; }}
.lede b {{ color: var(--ink); font-weight: 600; }}

/* ---------------------------------------------------------- the primer */
.primer {{
  background: var(--card); border: 1px solid var(--rule); border-radius: 6px;
  padding: 22px 24px; display: flex; flex-direction: column; gap: 12px;
  box-shadow: var(--shadow); margin-top: 8px;
}}
.primer h2 {{ font-size: 15px; font-weight: 600; letter-spacing: -.01em; }}
.primer p {{ color: var(--ink-2); font-size: 15px; max-width: 70ch; }}
.primer ol {{ margin: 0; padding-left: 20px; color: var(--ink-2); font-size: 15px; display: flex; flex-direction: column; gap: 5px; }}

/* ---------------------------------------------------------- jump bar */
.jumps {{
  position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5;
  display: flex; flex-wrap: wrap; gap: 4px 6px;
  padding-block: 10px; margin-block: 26px 4px;
  background: var(--paper); border-bottom: 1px solid var(--rule-soft);
}}
.jumps a {{
  font-family: "IBM Plex Mono", monospace; font-size: 12px; text-decoration: none;
  padding: 4px 9px; border-radius: 3px; color: var(--ink-2);
  border: 1px solid var(--rule);
}}
.jumps a:hover {{ background: var(--sunk); color: var(--ink); }}
.finder {{ display: flex; gap: 8px; align-items: center; margin-left: auto; }}
.finder input {{
  font: 400 13px/1.4 "IBM Plex Mono", monospace; color: var(--ink);
  background: var(--card); border: 1px solid var(--rule); border-radius: 3px;
  padding: 5px 9px; width: 150px; max-width: 42vw;
}}
.finder input::placeholder {{ color: var(--muted); }}

/* ---------------------------------------------------------- a place */
.place {{ padding-block: 40px 8px; scroll-margin-top: 108px; }}
.place-head {{
  display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 20px;
  align-items: baseline; padding-bottom: 14px; margin-bottom: 18px;
  border-bottom: 2px solid var(--ink);
}}
.place-title {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; }}
.place-head h2 {{ font-size: clamp(20px, 3.2vw, 26px); font-weight: 700; letter-spacing: -.02em; }}
.how {{
  font-family: "IBM Plex Mono", monospace; font-size: 12.5px; color: var(--accent);
}}
.place-blurb {{ grid-column: 1 / -1; color: var(--ink-2); font-size: 15px; max-width: 70ch; }}
.count {{
  font-family: "IBM Plex Mono", monospace; font-size: 12px; color: var(--muted);
  white-space: nowrap; font-variant-numeric: tabular-nums;
}}

/* ---------------------------------------------------------- an entry */
.entry {{
  padding-block: 18px; border-bottom: 1px solid var(--rule-soft);
  display: flex; flex-direction: column; gap: 11px;
}}
.entry:last-child {{ border-bottom: 0; }}
.entry-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; }}
.entry-head h3 {{ font-size: 18px; font-weight: 600; letter-spacing: -.012em; }}
.code {{
  font-family: "IBM Plex Mono", monospace; font-size: 11.5px; color: var(--muted);
  letter-spacing: .05em;
}}

/* The steps are the point of the page, so they get the structure. */
.steps {{
  list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; gap: 0;
  border-left: 2px solid var(--rule);
}}
.step {{
  display: grid; grid-template-columns: 52px minmax(0, auto) minmax(0, 1fr);
  gap: 4px 14px; align-items: baseline;
  padding: 7px 0 7px 14px;
}}
.step + .step {{ border-top: 1px solid var(--rule-soft); }}
.kind {{
  font-family: "IBM Plex Mono", monospace; font-size: 10.5px; font-weight: 600;
  letter-spacing: .1em; text-transform: uppercase; color: var(--look);
}}
.step-press .kind {{ color: var(--press); }}
.step-pad   .kind {{ color: var(--pad); }}
.step-turn  .kind {{ color: var(--turn); }}
.step-type  .kind {{ color: var(--type); }}
.what {{ min-width: 0; }}
.why {{ color: var(--muted); font-size: 14.5px; min-width: 0; }}

/* A keycap, because the buttons on a Push are engraved and physical. */
.chord {{ display: inline-flex; flex-wrap: wrap; align-items: center; gap: 3px; }}
kbd {{
  display: inline-block; font-size: 12.5px; font-weight: 500; line-height: 1.5;
  padding: 2px 8px; border-radius: 4px; white-space: nowrap;
  background: var(--cap-face); color: var(--cap-ink);
  border: 1px solid var(--cap-edge); box-shadow: inset 0 -1px 0 rgba(0,0,0,.35);
}}
.plus {{ color: var(--muted); font-size: 12px; }}
.slash {{ color: var(--muted); font-size: 11.5px; font-family: "IBM Plex Sans", sans-serif; padding: 0 2px; }}
.prose {{ font-size: 15px; color: var(--ink); }}
.cmd {{
  font-size: 12.5px; background: var(--sunk); border: 1px solid var(--rule);
  border-radius: 3px; padding: 2px 7px; display: inline-block;
  overflow-wrap: anywhere;
}}
.nothing {{ color: var(--muted); font-style: italic; font-size: 15px; }}

.proof {{
  color: var(--ink-2); font-size: 15px; max-width: 72ch;
  padding-left: 14px; border-left: 2px solid var(--accent);
}}
.proof b {{ color: var(--ink); font-weight: 600; }}
.proof code {{ font-size: 12.5px; background: var(--sunk); padding: 1px 5px; border-radius: 3px; }}

.nomatch {{ padding: 40px 0; color: var(--muted); font-size: 15px; }}

footer {{
  margin-top: 48px; padding-top: 22px; border-top: 1px solid var(--rule);
  color: var(--muted); font-size: 13.5px;
  display: flex; flex-direction: column; gap: 5px;
}}
footer code {{ font-size: 12px; }}

@media (max-width: 620px) {{
  /* Five rows of tabs stuck to the top is most of a phone screen, and it
     covered the heading you had just jumped to. */
  .jumps {{ position: static; }}
  .place {{ scroll-margin-top: 8px; }}
  .finder {{ margin-left: 0; width: 100%; }}
  .finder input {{ width: 100%; max-width: none; }}
  .step {{ grid-template-columns: 46px minmax(0, 1fr); }}
  .why {{ grid-column: 2; }}
  .place-head {{ grid-template-columns: minmax(0, 1fr); }}
  .count {{ grid-row: 1; justify-self: start; }}
}}
@media print {{
  .jumps {{ display: none; }}
  .entry {{ break-inside: avoid; }}
}}
</style>

<div class="page">

  <header class="top">
    <p class="eyebrow">push2sampler {version} &middot; {total} features</p>
    <h1>Every feature, and the buttons that show it working.</h1>
    <p class="lede">
      A run sheet for someone sitting in front of the hardware. Grouped by
      <b>where you are on the instrument</b> rather than by release, because
      that is how you actually get to things. Each entry is the presses in
      order, then what you should see or hear if it worked.
    </p>
  </header>

  <div class="primer">
    <h2>Before any of it works, you need one recorded sample</h2>
    <ol>
      <li>Press the <b>top-left pad</b>. It is white, meaning empty, so this
        opens Record mode.</li>
      <li>Press the <b>second pad</b> to record two bars, or just take the one.</li>
      <li>Press <b>Record</b>. You get four beats of count-in, then it records,
        then it stops by itself and drops you on the new sample's page.</li>
      <li>Press a few pads to put the sample on some bars, then <b>Play</b>.</li>
    </ol>
    <p>
      That is the whole workflow; everything below is something you can do to
      it. No hardware? <code>python -m push2sampler --sim my-song</code> is the
      same program in a terminal — type <code>p 0</code> for a pad and the
      button's own name for a button.
    </p>
  </div>

  <nav class="jumps">
{jumps}
    <span class="finder">
      <input id="find" type="search" placeholder="filter&hellip;"
             aria-label="Filter features by name or code" autocomplete="off">
    </span>
  </nav>

{sections}

  <p class="nomatch" id="nomatch" hidden>Nothing matches that.</p>

  <footer>
    <p>Generated by <code>tools/demo_page.py</code> from <code>plans.md</code>:
      the feature list and every title come from the plan, so a feature cannot
      be missed by being forgotten — the build refuses if any item has no
      recipe here.</p>
    <p>Button names are the labels engraved on the Push 2.
      <b>button 1</b>&hairsp;&ndash;&hairsp;<b>8</b> mean the row <i>below</i>
      the display; <b>encoder 1</b>&hairsp;&ndash;&hairsp;<b>8</b> mean the
      knobs <i>above</i> it.</p>
  </footer>
</div>

<script>
// A run sheet is long, so it gets a filter. Empty at rest: everything on the
// page is visible when it loads, which is what a filter must not change.
const find = document.getElementById("find");
const entries = Array.from(document.querySelectorAll(".entry"));
const places = Array.from(document.querySelectorAll(".place"));
const nomatch = document.getElementById("nomatch");

find.addEventListener("input", () => {{
  const needle = find.value.trim().toLowerCase();
  let shown = 0;
  for (const entry of entries) {{
    const hit = !needle || entry.dataset.find.includes(needle)
      || entry.textContent.toLowerCase().includes(needle);
    entry.hidden = !hit;
    if (hit) shown++;
  }}
  // A heading with nothing under it is worse than no heading.
  for (const place of places) {{
    place.hidden = !place.querySelector(".entry:not([hidden])");
  }}
  nomatch.hidden = shown > 0;
}});
</script>
"""


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "run-sheet.html"
    from push2sampler import __version__

    out.write_text(build(__version__))
    _trains, items = read_plan()
    print(f"{out}: {len(items)} features, {len(RECIPES)} recipes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
