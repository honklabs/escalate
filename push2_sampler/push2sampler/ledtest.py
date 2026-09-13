"""``--led-test``: find out *why* the pads are dark.

``--selftest`` assumes the LEDs work and asks what you see.  When nothing lights
at all that question has no useful answer, and every later check inherits the
same silence.  This asks the more basic questions first, one layer at a time, so
a dark grid becomes a specific finding instead of a mystery:

  0. Does the Push answer us at all?  (press a pad; we print what arrives)
  1. Do the pads light from a **factory** palette index?  No SysEx involved.
  2. Do they light from **our** private palette block?  SysEx involved.
  3. Do the **button** LEDs light?
  4. Does a colour need a channel other than the static one?

The interesting outcome is stage 1 lighting and stage 2 staying dark: that means
:meth:`push2sampler.push2.Push2.program_palette` is wrong, and since every
colour in ``colors.py`` is addressed at an index 64 or above, the whole program
would be painting in entries the device has left black.  No error, no traceback,
just a surface that looks dead.

Stage 0 is the one that decides whether anything after it is worth reading.  If
pressing a pad produces messages, the port is right and the cable is fine, and
the fault is in what we *send*.  If it produces nothing either, the problem is
upstream of this program.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import colors
from .constants import BTN_BRIGHT, GRID_W, PAD_COUNT, Btn, index_to_note

#: How long stage 0 waits for you to press a pad.
LISTEN_S = 20.0

#: Eight factory palette indices, one per row, spread across the range.  These
#: are *not* from the spec -- the factory palette is undocumented, which is why
#: we reprogram it.  They are here only to answer "does any velocity light this
#: pad", so their actual colours do not matter.
FACTORY_ROW_VELOCITIES: tuple[int, ...] = (1, 3, 5, 25, 45, 87, 122, 127)

#: One of our own palette entries per row, in the same shape as stage 1 so the
#: two stages are directly comparable.
OURS_ROWS: tuple[tuple[str, int], ...] = (
    ("white", colors.WHITE.index),
    ("white dim", colors.WHITE_DIM.index),
    ("green", colors.GREEN.index),
    ("green dim", colors.GREEN_DIM.index),
    ("amber", colors.AMBER.index),
    ("red", colors.RED.index),
    ("blue", colors.BLUE.index),
    ("yellow", colors.YELLOW.index),
)

#: Buttons for stage 3.  Play and Record are the two nobody can mistake.
TEST_BUTTONS: tuple[tuple[str, int], ...] = (
    ("Play", Btn.PLAY),
    ("Record", Btn.RECORD),
)

#: Channels to try in stage 4.  Channel 0 (MIDI 1) should be the static one;
#: the others are animation channels in the spec, and if one of *those* is what
#: lights a pad then our understanding is off by one somewhere.
TEST_CHANNELS: tuple[int, ...] = (0, 1, 2, 3)


@dataclass
class LedFinding:
    stage: str
    result: str
    detail: str = ""

    def as_dict(self) -> dict:
        return {"stage": self.stage, "result": self.result, "detail": self.detail}


@dataclass
class LedReport:
    findings: list[LedFinding] = field(default_factory=list)
    ports: dict = field(default_factory=dict)
    verdict: str = ""

    def add(self, stage: str, result: str, detail: str = "") -> None:
        self.findings.append(LedFinding(stage, result, detail))

    def result(self, stage: str) -> str | None:
        for finding in self.findings:
            if finding.stage == stage:
                return finding.result
        return None

    def as_dict(self) -> dict:
        return {
            "kind": "led-test",
            "ports": self.ports,
            "believed_corner_notes": dict(
                zip(("top-left", "top-right", "bottom-left", "bottom-right"),
                    (note for _, note in note_map_sample()))
            ),
            "findings": [f.as_dict() for f in self.findings],
            "verdict": self.verdict,
        }


def _yesno(ask, prompt: str) -> str:
    """Ask a yes/no/some question.  Returns 'yes', 'no', 'some' or 'skip'."""
    answer = ask(f"  {prompt}\n    [y=yes, n=nothing, s=some of it, Enter=skip] ")
    answer = (answer or "").strip().lower()
    return {
        "y": "yes", "yes": "yes",
        "n": "no", "no": "no", "none": "no",
        "s": "some", "some": "some",
    }.get(answer, "skip")


def _all_off(push) -> None:
    for i in range(PAD_COUNT):
        push.send_pad_raw(i, 0)


def _light_rows(push, values, channel: int = 0) -> None:
    """One value per row of eight, top row first."""
    for row, value in enumerate(values):
        for column in range(GRID_W):
            push.send_pad_raw(row * GRID_W + column, value, channel)


def run_led_test(report_path: Path | str = "led-report.json", push=None,
                 ask=input, say=print) -> int:
    """Walk the stages.  Returns 0 if the pads lit, 1 if they never did."""
    from .push2 import Push2

    report = LedReport()
    owns_push = push is None
    if push is None:
        push = Push2()
        try:
            # No palette upload: stage 1 has to happen before we touch it.
            push.open(program_palette=False)
        except Exception as exc:
            say(f"could not open the Push 2: {exc}")
            return 2
    report.ports = {
        "chosen_input": getattr(push, "chosen_input", None),
        "chosen_output": getattr(push, "chosen_output", None),
    }
    say("LED test -- why are the pads dark?")
    say(f"  MIDI in:  {report.ports['chosen_input']}")
    say(f"  MIDI out: {report.ports['chosen_output']}")
    say("  Nothing here changes a project.  Ctrl-C is safe.\n")

    try:
        _stage0_input(push, report, ask, say)
        _stage1_factory(push, report, ask, say)
        _stage2_ours(push, report, ask, say)
        _stage3_buttons(push, report, ask, say)
        _stage4_channels(push, report, ask, say)
    except KeyboardInterrupt:
        say("\n  stopped early")
    finally:
        try:
            _all_off(push)
        except Exception:  # pragma: no cover - best effort
            pass
        if owns_push:
            push.close()

    report.verdict = _verdict(report)
    say("\n" + "-" * 60)
    for finding in report.findings:
        say(f"  {finding.stage}: {finding.result}"
            + (f"  ({finding.detail})" if finding.detail else ""))
    say("\n" + report.verdict)

    path = Path(report_path)
    path.write_text(json.dumps(report.as_dict(), indent=2) + "\n")
    say(f"\nwritten to {path} -- paste it back and the maps can be corrected.")
    return 0 if report.result("pads light at all") == "yes" else 1


# -- the stages ------------------------------------------------------------
def _stage0_input(push, report: LedReport, ask, say) -> None:
    say("[1/5] Does the Push answer us?")
    push.capture_raw = True
    push.drain_raw()
    say(f"  Press and release any pad.  (listening for {int(LISTEN_S)}s)")
    seen = []
    deadline = time.monotonic() + LISTEN_S
    while time.monotonic() < deadline and len(seen) < 4:
        msg = push.next_raw(0.2)
        if msg is not None:
            seen.append(msg)
    if not seen:
        report.add("push sends to us", "no",
                   "no MIDI arrived -- the input port is wrong, or the Push is "
                   "not powered, or another program has it")
        say("  nothing arrived.")
        return
    for msg in seen:
        say(f"    got: {msg}")
    report.add("push sends to us", "yes", "; ".join(str(m) for m in seen))


def _stage1_factory(push, report: LedReport, ask, say) -> None:
    say("\n[2/5] Do the pads light from a FACTORY palette index?")
    say("  No SysEx has been sent yet -- this is the plainest thing we can do:")
    say(f"  a note-on per pad, one velocity per row {FACTORY_ROW_VELOCITIES}.")
    _all_off(push)
    _light_rows(push, FACTORY_ROW_VELOCITIES)
    answer = _yesno(ask, "Did any pads light?")
    report.add("pads light at all", answer,
               f"velocities by row: {FACTORY_ROW_VELOCITIES}")
    if answer == "some":
        which = ask("    Which rows lit (e.g. '1,2,5', top row is 1)? ").strip()
        report.add("factory rows lit", which or "unstated")
    _all_off(push)


def _stage2_ours(push, report: LedReport, ask, say) -> None:
    say("\n[3/5] Do they light from OUR palette block?")
    say("  Uploading palette entries 64-83 over SysEx, then using them.")
    try:
        push.program_palette()
    except Exception as exc:
        report.add("our palette", "error", str(exc))
        say(f"  the upload itself failed: {exc}")
        return
    time.sleep(0.3)  # give the device a moment to apply the palette
    _all_off(push)
    _light_rows(push, [index for _, index in OURS_ROWS])
    say("  Rows, top to bottom: " + ", ".join(name for name, _ in OURS_ROWS))
    answer = _yesno(ask, "Did any pads light, and are those the colours?")
    report.add("our palette", answer,
               "rows: " + ", ".join(f"{n}={i}" for n, i in OURS_ROWS))
    if answer in ("some", "yes"):
        wrong = ask("    Any row the wrong colour?  Which, and what colour? ").strip()
        if wrong:
            report.add("our palette colours", "mismatch", wrong)
    _all_off(push)


def _stage3_buttons(push, report: LedReport, ask, say) -> None:
    say("\n[4/5] Do the button LEDs light?")
    for name, cc in TEST_BUTTONS:
        push.button_leds.pop(cc, None)
        push.set_button(cc, BTN_BRIGHT)
    say("  " + " and ".join(name for name, _ in TEST_BUTTONS) + " should be lit.")
    answer = _yesno(ask, "Are they?")
    report.add("button LEDs", answer,
               ", ".join(f"{n}=cc{c}" for n, c in TEST_BUTTONS))
    for _, cc in TEST_BUTTONS:
        push.set_button(cc, 0)


def _stage4_channels(push, report: LedReport, ask, say) -> None:
    # "some" counts as working: if any pad lit, channel 1 is not the problem.
    if report.result("pads light at all") in ("yes", "some"):
        report.add("channel", "not needed", "channel 1 already lit something")
        return
    say("\n[5/5] Is it the channel?")
    say("  We send static colours on MIDI channel 1.  Trying others.")
    lit = []
    for channel in TEST_CHANNELS:
        _all_off(push)
        _light_rows(push, [127] * 8, channel)
        answer = _yesno(ask, f"MIDI channel {channel + 1}: anything?")
        if answer in ("yes", "some"):
            lit.append(channel + 1)
    _all_off(push)
    report.add("channel", ", ".join(str(c) for c in lit) if lit else "none lit")


def _verdict(report: LedReport) -> str:
    """Say what the answers mean, in the order that matters."""
    answers = report.result("push sends to us")
    pads = report.result("pads light at all")
    ours = report.result("our palette")
    buttons = report.result("button LEDs")

    if answers == "no" and pads != "yes" and buttons != "yes":
        return (
            "VERDICT: nothing in either direction.  This is not the palette and\n"
            "not the button map -- the Push is not really connected to us.  Check\n"
            "its own power supply, a direct USB port rather than a hub, and that\n"
            "Ableton Live is not running.  --list-ports shows what we opened."
        )
    if pads == "some":
        # Checked before the "buttons light, pads do not" case below, which
        # would otherwise claim the pads are dead when most of them lit.
        return (
            "VERDICT: partial.  Some pads light and some do not, which points at\n"
            "the note range rather than the colours -- note the rows above and\n"
            "compare against index_to_note in constants.py."
        )
    if pads == "yes" and ours in ("no", "error"):
        return (
            "VERDICT: program_palette is wrong.  The pads light from factory\n"
            "indices but not from ours, and every colour in colors.py is an index\n"
            "of 64 or above -- so the whole program paints into entries the device\n"
            "left black.  This is the fix: correct the SysEx in\n"
            "Push2.program_palette, or address factory indices instead of\n"
            "uploading a private block at all."
        )
    if pads != "yes" and buttons == "yes":
        return (
            "VERDICT: buttons light, pads do not.  Output works, so this is the\n"
            "pad addressing: index_to_note, the note range, or the channel.\n"
            "Check the channel line above."
        )
    if pads == "yes" and ours == "yes":
        return (
            "VERDICT: the LEDs are fine.  Both palettes work and the buttons\n"
            "light, so run --selftest now; whatever was dark before was not this."
        )
    return (
        "VERDICT: not conclusive.  Paste the findings above; the useful pairs are\n"
        "stage 1 against stage 2 (palette) and stage 2 against stage 4 (channel)."
    )


def note_map_sample() -> list[tuple[int, int]]:
    """``(pad index, note)`` for the four corners -- printed by ``--led-test``.

    Included in the report so a wrong grid orientation is visible even when the
    operator only pasted the JSON.
    """
    return [(i, index_to_note(i)) for i in (0, GRID_W - 1, PAD_COUNT - GRID_W, PAD_COUNT - 1)]
