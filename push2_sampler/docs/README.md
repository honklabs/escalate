# push2sampler documentation

Five documents, depending on what you need:

| | |
| --- | --- |
| **[Getting started](getting-started.md)** | A tutorial. Start here. Takes you from an unplugged Push 2 to a finished, bounced song, using every feature the program has. About an hour. |
| **[Reference](reference.md)** | Every mode, every control, every colour, every setting, both file formats, and the full command line. Look things up here. |
| **[Cheat sheet](cheatsheet.md)** | One page. Print it and put it next to the Push. |
| **[Troubleshooting](troubleshooting.md)** | Symptom → cause → fix. Read this before concluding something is broken. |
| **[The simulator](simulator.md)** | Running the whole program with no hardware at all, which is also how to report a bug you cannot reproduce. |

## What this program is

A Push 2 and a microphone, and nothing else, as a complete instrument. You
record short loops, say where each one plays across a 64-bar song, and build the
arrangement with your hands on the 8×8 grid. There is no DAW, no mouse, and
nothing to look at on a computer screen — the laptop is a power supply and a
disk.

## One thing to know before you trust it

Every hardware fact in this program — which MIDI port to use, what control
change each button sends, what a palette colour looks like, how the display is
fed — was taken from Ableton's *Push 2 MIDI and Display Interface* document
rather than measured on a device. **Nobody has run it on real hardware yet.**

So the first thing to do with a Push 2 in front of you is not to make music, it
is to run the probe:

```
python -m push2sampler --selftest
```

It takes a few minutes, asks you to press things, and writes down what your Push
*actually* does. See [Getting started](getting-started.md#step-2-run-the-probe).
