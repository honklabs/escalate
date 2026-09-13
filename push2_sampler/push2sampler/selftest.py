"""Guided hardware probe: find out what the Push 2 actually does.

Every hardware fact in this program -- which MIDI port to use, which control
change each button sends, what a palette index looks like, how the display is
fed -- came from Ableton's *Push 2 MIDI and Display Interface* document rather
than from a device.  This walks through those guesses with a real Push 2 and
writes down what really happened, so the maps in :mod:`push2sampler.constants`
can be corrected from evidence.

Run it with the Push plugged in::

    python -m push2sampler --selftest

It asks for one thing at a time.  Where a step needs a control pressed, press
it on the device; where it needs a judgement ("is that green?"), type an answer.
Enter skips a step, ``q`` quits and still writes the report.

The report lands in ``hardware-report.json`` (plus a readable ``.md``
alongside).  Commit it, or paste the markdown -- it is all that is needed to fix
whatever turns out to be wrong.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import colors
from .constants import (
    BTN_BRIGHT,
    DISPLAY_ROW_BOTTOM,
    DISPLAY_ROW_TOP,
    ENCODER_MASTER,
    ENCODER_SWING,
    ENCODER_TEMPO,
    ENCODER_TRACK,
    PAD_COUNT,
    Btn,
    index_to_note,
)

#: How long a step waits for a control to be touched before giving up on it.
LISTEN_TIMEOUT_S = 20.0

INTRO = """push2sampler hardware probe
===========================
This finds out what your Push 2 actually does, so the program can be corrected
where it guessed.  Nothing on the device is changed permanently.

Where a step names a control, press or turn it on the Push.  Where it asks a
question, type an answer.  Enter on its own skips a step; q quits and still
writes the report.
"""

#: Buttons worth confirming, in the order the probe asks for them.  The CC is
#: what this program currently believes; the probe records what arrives.
BUTTONS: tuple[tuple[str, int], ...] = (
    ("Play", Btn.PLAY),
    ("Record", Btn.RECORD),
    ("Stop (Stop Clip)", Btn.STOP),
    ("Session", Btn.SESSION),
    ("Note", Btn.NOTE),
    ("Shift", Btn.SHIFT),
    ("Mute", Btn.MUTE),
    ("Solo", Btn.SOLO),
    ("Delete", Btn.DELETE),
    ("Undo", Btn.UNDO),
    ("Metronome", Btn.METRONOME),
    ("Tap Tempo", Btn.TAP_TEMPO),
    ("Repeat", Btn.REPEAT),
    ("Accent", Btn.ACCENT),
    ("Setup", Btn.SETUP),
    ("User (top-left corner, by Setup -- may not exist on your unit)", Btn.USER),
    ("Up arrow", Btn.UP),
    ("Down arrow", Btn.DOWN),
    ("Left arrow", Btn.LEFT),
    ("Right arrow", Btn.RIGHT),
    ("Page left (the < above the display)", Btn.PAGE_LEFT),
    ("Page right", Btn.PAGE_RIGHT),
    ("New", Btn.NEW),
    ("Duplicate", Btn.DUPLICATE),
    ("Fixed Length", Btn.FIXED_LENGTH),
    ("Automate", Btn.AUTOMATE),
    ("Convert", Btn.CONVERT),
    ("Scale", Btn.SCALE),
    ("Device", Btn.DEVICE),
    ("Browse", Btn.BROWSE),
    ("Mix", Btn.MIX),
    ("Clip", Btn.CLIP),
    ("Master", Btn.MASTER),
    ("leftmost button ABOVE the display", DISPLAY_ROW_TOP[0]),
    ("leftmost button BELOW the display", DISPLAY_ROW_BOTTOM[0]),
)

ENCODERS: tuple[tuple[str, int], ...] = (
    ("Tempo (top left, above Swing)", ENCODER_TEMPO),
    ("Swing", ENCODER_SWING),
    ("first encoder above the display", ENCODER_TRACK[0]),
    ("Master volume (top right)", ENCODER_MASTER),
)


@dataclass
class Step:
    """One question and what came back."""

    name: str
    status: str = "unknown"  # ok | mismatch | missing | skipped | unavailable
    expected: object = None
    observed: object = None
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "expected": self.expected,
            "observed": self.observed,
            "detail": self.detail,
        }


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)
    ports: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add(self, step: Step) -> Step:
        self.steps.append(step)
        return step

    @property
    def mismatches(self) -> list[Step]:
        return [s for s in self.steps if s.status == "mismatch"]

    def as_dict(self) -> dict:
        counted = [s for s in self.steps if s.status in ("ok", "mismatch", "missing")]
        return {
            "tool": "push2sampler --selftest",
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "ports": self.ports,
            "summary": {
                "checked": len(counted),
                "ok": sum(1 for s in counted if s.status == "ok"),
                "mismatch": len(self.mismatches),
                "missing": sum(1 for s in counted if s.status == "missing"),
                "skipped": sum(1 for s in self.steps if s.status == "skipped"),
            },
            "corrections": [
                {"what": s.name, "believed": s.expected, "actual": s.observed}
                for s in self.mismatches
            ],
            "steps": [s.as_dict() for s in self.steps],
            "notes": self.notes,
        }

    def as_markdown(self) -> str:
        data = self.as_dict()
        out = [
            "# Push 2 hardware report",
            "",
            f"- recorded: {data['recorded_at']}",
            f"- platform: {data['platform']} (python {data['python']})",
            f"- MIDI in: `{self.ports.get('chosen_input', '?')}`",
            f"- MIDI out: `{self.ports.get('chosen_output', '?')}`",
            "",
            "## Summary",
            "",
            f"{data['summary']['ok']} ok, {data['summary']['mismatch']} wrong, "
            f"{data['summary']['missing']} not seen, {data['summary']['skipped']} skipped.",
            "",
        ]
        if data["corrections"]:
            out += ["## Needs correcting", "", "| what | believed | actual |", "| --- | --- | --- |"]
            out += [
                f"| {c['what']} | {c['believed']} | {c['actual']} |" for c in data["corrections"]
            ]
            out.append("")
        out += ["## Every step", "", "| step | result | believed | observed | note |",
                "| --- | --- | --- | --- | --- |"]
        for step in self.steps:
            out.append(
                f"| {step.name} | {step.status} | {step.expected if step.expected is not None else ''} "
                f"| {step.observed if step.observed is not None else ''} | {step.detail} |"
            )
        if self.notes:
            out += ["", "## Notes", ""] + [f"- {note}" for note in self.notes]
        return "\n".join(out) + "\n"


class Quit(Exception):
    """Raised when the operator asks to stop early."""


class Probe:
    """Walks the checks.  ``ask`` and ``listen`` are injected so this is testable."""

    def __init__(self, push, ask, listen, say, display=None) -> None:
        self.push = push
        self.ask = ask
        self.listen = listen
        self.say = say
        self.display = display
        self.report = Report()

    # ------------------------------------------------------------------
    def run(self) -> Report:
        self.push.capture_raw = True
        steps = (
            self.check_ports,
            self.check_grid_orientation,
            self.check_pad_notes,
            self.check_pad_pressure,
            self.check_colours,
            self.check_buttons,
            self.check_encoders,
            self.check_touch_strip,
            self.check_display,
        )
        try:
            for index, step in enumerate(steps, start=1):
                self.say(f"\n[{index}/{len(steps)}] {step.__doc__.splitlines()[0]}")
                step()
        except Quit:
            self.say("\nstopping early; the report still has everything so far.")
        finally:
            self.push.capture_raw = False
            try:
                self.push.clear()
            except Exception:  # pragma: no cover - best effort
                pass
        return self.report

    # -- helpers -------------------------------------------------------
    def _confirm(self, question: str) -> str:
        """Ask a yes/no/skip question.  Returns 'yes', 'no' or 'skipped'."""
        answer = self.ask(f"{question} [Enter=yes, n=no, s=skip, q=quit] ").strip().lower()
        if answer in ("q", "quit"):
            raise Quit
        if answer in ("s", "skip"):
            return "skipped"
        if answer in ("n", "no"):
            return "no"
        return "yes"

    def _await_message(self, prompt: str, kinds: tuple[str, ...]):
        """Wait for a message of one of ``kinds``; None if skipped or silent."""
        self.push.drain_raw()
        self.say(f"  {prompt}")
        self.say(f"    (or press Enter here to skip; waits {int(LISTEN_TIMEOUT_S)}s)")
        deadline = time.monotonic() + LISTEN_TIMEOUT_S
        while time.monotonic() < deadline:
            msg = self.listen(0.2)
            if msg is None:
                continue
            if msg == "__stdin__":  # the operator typed instead of pressing
                return None
            if getattr(msg, "type", None) in kinds:
                if msg.type == "control_change" and getattr(msg, "value", 0) == 0:
                    continue  # that is the release; wait for a press
                if msg.type == "note_on" and getattr(msg, "velocity", 0) == 0:
                    continue
                return msg
        return None

    def _light_only(self, indices) -> None:
        for i in range(PAD_COUNT):
            self.push.set_pad(i, colors.OFF)
        for i in indices:
            self.push.set_pad(i, colors.WHITE)

    # -- the checks ----------------------------------------------------
    def check_ports(self) -> None:
        """MIDI ports"""
        try:
            import mido

            inputs, outputs = mido.get_input_names(), mido.get_output_names()
        except Exception as exc:
            self.report.add(Step("midi ports", "unavailable", detail=str(exc)))
            return
        self.report.ports = {
            "inputs": inputs,
            "outputs": outputs,
            "chosen_input": getattr(self.push, "chosen_input", None),
            "chosen_output": getattr(self.push, "chosen_output", None),
        }
        for name in inputs:
            self.say(f"    in:  {name}")
        for name in outputs:
            self.say(f"    out: {name}")
        user_ports = [n for n in inputs if "user" in n.lower()]
        self.report.add(
            Step(
                "a User port exists",
                "ok" if user_ports else "mismatch",
                expected="a port with 'User' in the name",
                observed=user_ports or inputs,
            )
        )

    def check_grid_orientation(self) -> None:
        """Grid orientation -- is pad index 0 the top-left pad?"""
        self._light_only([0])
        answer = self.ask(
            "  One pad should be lit. Which corner is it?\n"
            "    [Enter=top-left, tr=top-right, bl=bottom-left, br=bottom-right, "
            "none, s=skip, q=quit] "
        ).strip().lower()
        if answer in ("q", "quit"):
            raise Quit
        if answer in ("s", "skip"):
            self.report.add(Step("pad 0 is top-left", "skipped"))
            return
        seen = {"": "top-left", "tl": "top-left", "tr": "top-right",
                "bl": "bottom-left", "br": "bottom-right"}.get(answer, answer or "none")
        if seen == "none":
            # Nothing lit is not an orientation finding, and every check after
            # this one is about to ask the same unanswerable question.  Say so
            # here rather than letting the operator answer "none" eight times.
            self.say("  Nothing lit means this is not the grid map -- it is the")
            self.say("  LEDs themselves.  Stop here and run:")
            self.say("      python -m push2sampler --led-test")
            self.say("  which finds out which layer is at fault.")
        self.report.add(
            Step(
                "pad 0 is top-left",
                "ok" if seen == "top-left" else "mismatch",
                expected="top-left",
                observed=seen,
                detail=(
                    "" if seen == "top-left"
                    else "no LED output at all -- run --led-test" if seen == "none"
                    else "index_to_note needs flipping"
                ),
            )
        )
        self._light_only(range(8))
        result = self._confirm("  Is the whole TOP row lit now?")
        self.report.add(
            Step("indices 0-7 are the top row", "ok" if result == "yes" else
                 "skipped" if result == "skipped" else "mismatch",
                 expected="top row", observed=result)
        )

    def check_pad_notes(self) -> None:
        """Pad notes -- which MIDI note each corner pad sends"""
        for label, index in (("TOP-LEFT", 0), ("BOTTOM-RIGHT", 63)):
            expected = index_to_note(index)
            self._light_only([index])
            msg = self._await_message(f"Press the {label} pad (it is lit).", ("note_on",))
            if msg is None:
                self.report.add(Step(f"{label.lower()} pad note", "missing", expected=expected))
                continue
            note = getattr(msg, "note", None)
            self.report.add(
                Step(
                    f"{label.lower()} pad note",
                    "ok" if note == expected else "mismatch",
                    expected=expected,
                    observed=note,
                )
            )

    def check_pad_pressure(self) -> None:
        """Pad velocity and aftertouch"""
        self._light_only([27, 28, 35, 36])
        msg = self._await_message("Hit one of the four lit middle pads HARD.", ("note_on",))
        if msg is None:
            self.report.add(Step("pad velocity", "missing"))
            return
        velocity = getattr(msg, "velocity", 0)
        self.report.add(
            Step("pad velocity", "ok" if velocity > 0 else "mismatch",
                 expected="1-127", observed=velocity,
                 detail="hard hit should be high" if velocity else "")
        )
        msg = self._await_message("Now press and hold a pad, leaning into it.", ("polytouch",))
        self.report.add(
            Step("pad aftertouch (polytouch)", "ok" if msg is not None else "missing",
                 expected="polytouch",
                 observed=getattr(msg, "type", None) if msg else None)
        )

    def check_colours(self) -> None:
        """Palette -- does each colour we upload look like its name?"""
        result = self._confirm("  Ready to check colours? The grid will change colour.")
        if result == "skipped":
            self.report.add(Step("palette", "skipped"))
            return
        for color in colors.PALETTE:
            for i in range(PAD_COUNT):
                self.push.set_pad(i, color)
            answer = self._confirm(f"  Does the grid look {color.name.replace('_', ' ')}?")
            self.report.add(
                Step(
                    f"colour {color.name} (palette {color.index})",
                    "ok" if answer == "yes" else "skipped" if answer == "skipped" else "mismatch",
                    expected=color.rgb,
                    observed=answer,
                )
            )
        self._light_only([])

    def check_buttons(self) -> None:
        """Buttons -- which control change each one sends"""
        self.say("  Press each button as it is named. Enter skips one.")
        self.say("  A name that is not on your panel at all is a finding too:")
        self.say("  press Enter and it is recorded as missing.")
        for label, expected in BUTTONS:
            self.push.set_button(expected, BTN_BRIGHT)
            msg = self._await_message(f"Press {label}.", ("control_change",))
            self.push.set_button(expected, 0)
            if msg is None:
                self.report.add(Step(f"button {label}", "missing", expected=expected))
                continue
            observed = getattr(msg, "control", None)
            self.report.add(
                Step(
                    f"button {label}",
                    "ok" if observed == expected else "mismatch",
                    expected=expected,
                    observed=observed,
                    detail="" if observed == expected
                    else "update constants.Btn / the display rows",
                )
            )

    def check_encoders(self) -> None:
        """Encoders -- control change and which way is clockwise"""
        for label, expected in ENCODERS:
            msg = self._await_message(f"Turn the {label} encoder CLOCKWISE.", ("control_change",))
            if msg is None:
                self.report.add(Step(f"encoder {label}", "missing", expected=expected))
                continue
            observed = getattr(msg, "control", None)
            value = getattr(msg, "value", 0)
            clockwise_positive = 0 < value < 64
            status = "ok" if observed == expected and clockwise_positive else "mismatch"
            self.report.add(
                Step(
                    f"encoder {label}",
                    status,
                    expected=expected,
                    observed=f"cc {observed}, value {value}",
                    detail="" if clockwise_positive
                    else "clockwise sends >=64, so encoder_delta is inverted",
                )
            )

    def check_touch_strip(self) -> None:
        """Touch strip -- what it sends when you slide it"""
        msg = self._await_message(
            "Slide a finger up the touch strip (left of the pads).",
            ("pitchwheel", "control_change", "note_on"),
        )
        if msg is None:
            self.report.add(Step("touch strip", "missing", expected="pitchwheel"))
            return
        kind = getattr(msg, "type", None)
        detail = ""
        if kind == "pitchwheel":
            detail = f"pitch={getattr(msg, 'pitch', None)}"
        elif kind == "control_change":
            detail = f"cc={getattr(msg, 'control', None)} value={getattr(msg, 'value', None)}"
        self.report.add(
            Step("touch strip", "ok" if kind == "pitchwheel" else "mismatch",
                 expected="pitchwheel", observed=kind, detail=detail)
        )

    def check_display(self) -> None:
        """Display -- can we draw on the colour screen?"""
        if self.display is None:
            self.report.add(
                Step("display", "unavailable",
                     detail="pyusb/Pillow missing, or the screen is claimed by Live")
            )
            return
        try:
            self.display.draw([
                "PUSH2SAMPLER SELFTEST",
                "If you can read this, the display works.",
                "white text, grey text below",
                "0123456789  ABCDEFGHIJ",
            ])
        except Exception as exc:
            self.report.add(Step("display", "mismatch", detail=f"draw failed: {exc}"))
            return
        answer = self._confirm("  Is that text on the Push display, readable and not garbled?")
        self.report.add(
            Step("display", "ok" if answer == "yes" else
                 "skipped" if answer == "skipped" else "mismatch",
                 expected="four readable lines", observed=answer,
                 detail="" if answer == "yes" else "check the frame header / BGR565 packing")
        )


# ----------------------------------------------------------------------
def terminal_io(push):
    """Real ``ask`` / ``listen`` / ``say`` for a person at a terminal."""
    import sys

    def say(text: str) -> None:
        print(text, flush=True)

    def ask(prompt: str) -> str:
        try:
            return input(prompt)
        except EOFError:
            return "q"

    def listen(timeout: float):
        """Next MIDI message, or the sentinel '__stdin__' if a line is typed."""
        msg = push.next_raw(timeout=timeout)
        if msg is not None:
            return msg
        try:
            import select

            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                return "__stdin__"
        except Exception:  # pragma: no cover - not a tty, or no select
            pass
        return None

    return ask, listen, say


def run_selftest(report_path: Path, push=None, display=None) -> int:
    """Open the hardware, walk the checks, write the report.  Returns an exit code."""
    from .display import open_display
    from .push2 import Push2

    print(INTRO)
    owns_push = push is None
    if push is None:
        push = Push2()
        try:
            push.open()
        except Exception as exc:
            print(f"could not open the Push 2: {exc}")
            if "mido" in str(exc) or "rtmidi" in str(exc):
                print("Install the MIDI stack first: pip install -r requirements.txt")
            else:
                print("Plug it in, quit Ableton Live if it is running, and try again.")
            return 2
    if display is None:
        display = open_display()

    ask, listen, say = terminal_io(push)
    probe = Probe(push, ask, listen, say, display=display)
    try:
        report = probe.run()
    finally:
        if owns_push:
            push.close()

    report_path = Path(report_path)
    report_path.write_text(json.dumps(report.as_dict(), indent=2) + "\n")
    markdown = report_path.with_suffix(".md")
    markdown.write_text(report.as_markdown())

    data = report.as_dict()
    print("\n" + "-" * 60)
    print(f"ok {data['summary']['ok']}   wrong {data['summary']['mismatch']}   "
          f"not seen {data['summary']['missing']}   skipped {data['summary']['skipped']}")
    for correction in data["corrections"]:
        print(f"  WRONG: {correction['what']}: "
              f"believed {correction['believed']}, actually {correction['actual']}")
    print(f"\nwritten to {report_path} and {markdown}")
    print("Commit those, or paste the markdown, and the maps can be corrected.")
    return 0
