"""The hardware probe, driven by a script instead of a person."""

from dataclasses import dataclass


from push2sampler import selftest
from push2sampler.constants import Btn, index_to_note
from push2sampler.push2 import SimPush
from push2sampler.selftest import BUTTONS, ENCODERS, Probe, run_selftest


@dataclass
class Msg:
    """Stands in for a mido message."""

    type: str
    note: int = 0
    velocity: int = 0
    control: int = 0
    value: int = 0
    pitch: int = 0


SKIP = "__stdin__"


class Script:
    """Scripted answers and device messages for one probe run."""

    def __init__(self, answers=(), messages=()):
        self.answers = list(answers)
        self.messages = list(messages)
        self.asked: list[str] = []
        self.said: list[str] = []

    def ask(self, prompt):
        self.asked.append(prompt)
        return self.answers.pop(0) if self.answers else ""

    def listen(self, _timeout):
        # Running out of messages stands for the operator pressing Enter, which
        # keeps a scripted run from waiting out the real timeout.
        return self.messages.pop(0) if self.messages else SKIP

    def say(self, text):
        self.said.append(text)


def perfect_messages():
    """What a Push 2 that matches our maps exactly would send."""
    messages = [
        Msg("note_on", note=index_to_note(0), velocity=100),  # top-left pad
        Msg("note_on", note=index_to_note(63), velocity=100),  # bottom-right
        Msg("note_on", note=index_to_note(27), velocity=120),  # a hard hit
        Msg("polytouch", note=index_to_note(27), velocity=40),
    ]
    messages += [Msg("control_change", control=cc, value=127) for _, cc in BUTTONS]
    messages += [Msg("control_change", control=cc, value=1) for _, cc in ENCODERS]
    messages.append(Msg("pitchwheel", pitch=4096))
    return messages


def run(monkeypatch, answers, messages, display=None):
    monkeypatch.setattr(selftest, "LISTEN_TIMEOUT_S", 0.2)
    push = SimPush()
    push.open()
    script = Script(answers, messages)
    probe = Probe(push, script.ask, script.listen, script.say, display=display)
    return probe.run(), script, push


def statuses(report):
    return {step.name: step.status for step in report.steps}


# ----------------------------------------------------------------------
def test_a_device_that_matches_our_maps_reports_no_mismatches(monkeypatch):
    answers = ["", ""]  # corner is top-left, top row lit
    answers += [""] * (1 + len(__import__("push2sampler").colors.PALETTE))  # colours
    report, _, _ = run(monkeypatch, answers, perfect_messages())
    assert report.mismatches == []
    data = report.as_dict()
    assert data["corrections"] == []
    assert data["summary"]["ok"] > 30
    assert data["summary"]["mismatch"] == 0


def test_a_flipped_grid_is_caught_and_named(monkeypatch):
    messages = perfect_messages()
    messages[0] = Msg("note_on", note=36, velocity=100)  # bottom-left note instead
    report, _, _ = run(monkeypatch, ["bl", "n"], messages)
    result = statuses(report)
    assert result["pad 0 is top-left"] == "mismatch"
    assert result["indices 0-7 are the top row"] == "mismatch"
    assert result["top-left pad note"] == "mismatch"
    correction = [c for c in report.as_dict()["corrections"] if "top-left pad note" in c["what"]]
    assert correction[0] == {"what": "top-left pad note", "believed": 92, "actual": 36}


def test_a_button_on_a_different_cc_is_recorded(monkeypatch):
    messages = perfect_messages()
    # The first button asked about is Play; pretend it sends something else.
    play_index = 4
    messages[play_index] = Msg("control_change", control=99, value=127)
    report, _, _ = run(monkeypatch, ["", "n"], messages)
    step = next(s for s in report.steps if s.name == "button Play")
    assert step.status == "mismatch"
    assert step.expected == Btn.PLAY
    assert step.observed == 99
    assert "constants" in step.detail


def test_an_inverted_encoder_is_diagnosed(monkeypatch):
    messages = perfect_messages()
    encoder_index = 4 + len(BUTTONS)
    messages[encoder_index] = Msg("control_change", control=ENCODERS[0][1], value=127)
    report, _, _ = run(monkeypatch, ["", "n"], messages)
    step = next(s for s in report.steps if s.name.startswith("encoder Tempo"))
    assert step.status == "mismatch"
    assert "inverted" in step.detail


def test_controls_that_never_arrive_are_marked_missing(monkeypatch):
    report, _, _ = run(monkeypatch, ["", "n"], [])  # nothing is ever pressed
    result = statuses(report)
    assert result["top-left pad note"] == "missing"
    assert result["button Play"] == "missing"
    assert result["touch strip"] == "missing"
    assert report.as_dict()["summary"]["missing"] > 30


def test_colours_that_look_wrong_are_recorded(monkeypatch):
    from push2sampler import colors

    answers = ["", "n", ""] + ["n"] * len(colors.PALETTE)
    report, _, _ = run(monkeypatch, answers, perfect_messages())
    wrong = [s for s in report.steps if s.name.startswith("colour ")]
    assert len(wrong) == len(colors.PALETTE)
    assert all(s.status == "mismatch" for s in wrong)
    assert wrong[0].expected == colors.WHITE.rgb


def test_quitting_early_keeps_what_was_learned(monkeypatch):
    report, script, push = run(monkeypatch, ["q"], perfect_messages())
    assert any("stopping early" in line for line in script.said)
    assert [s.name for s in report.steps]  # the port check already ran
    assert all(s.name != "button Play" for s in report.steps)
    assert push.capture_raw is False  # and the tap is turned back off


def test_the_pads_are_left_dark_afterwards(monkeypatch):
    _, _, push = run(monkeypatch, ["", ""], perfect_messages())
    assert set(push.pad_leds) == {0}


def test_a_missing_display_is_reported_as_unavailable(monkeypatch):
    report, _, _ = run(monkeypatch, ["", ""], perfect_messages(), display=None)
    step = next(s for s in report.steps if s.name == "display")
    assert step.status == "unavailable"
    assert "pyusb" in step.detail


def test_a_working_display_is_confirmed(monkeypatch):
    class FakeDisplay:
        def __init__(self):
            self.lines = None

        def draw(self, lines):
            self.lines = lines

    display = FakeDisplay()
    answers = ["", ""] + ["s"] + [""]  # skip colours, confirm the display
    report, _, _ = run(monkeypatch, answers, perfect_messages(), display=display)
    step = next(s for s in report.steps if s.name == "display")
    assert step.status == "ok"
    assert display.lines and "SELFTEST" in display.lines[0]


def test_a_display_that_raises_is_a_mismatch_not_a_crash(monkeypatch):
    class Broken:
        def draw(self, lines):
            raise RuntimeError("usb pipe error")

    report, _, _ = run(monkeypatch, ["", "", "s"], perfect_messages(), display=Broken())
    step = next(s for s in report.steps if s.name == "display")
    assert step.status == "mismatch"
    assert "usb pipe error" in step.detail


# ----------------------------------------------------------------- report
def test_the_markdown_report_leads_with_the_corrections(monkeypatch):
    messages = perfect_messages()
    messages[4] = Msg("control_change", control=99, value=127)
    report, _, _ = run(monkeypatch, ["", "n"], messages)
    markdown = report.as_markdown()
    assert "# Push 2 hardware report" in markdown
    assert "## Needs correcting" in markdown
    assert "| button Play | 85 | 99 |" in markdown
    assert "## Every step" in markdown


def test_run_selftest_writes_both_files(tmp_path, monkeypatch):
    monkeypatch.setattr(selftest, "LISTEN_TIMEOUT_S", 0.2)
    push = SimPush()
    push.open()
    script = Script(["", ""], perfect_messages())
    monkeypatch.setattr(selftest, "terminal_io", lambda _p: (script.ask, script.listen, script.say))
    report_path = tmp_path / "hardware-report.json"
    assert run_selftest(report_path, push=push) == 0
    assert report_path.exists()
    assert report_path.with_suffix(".md").exists()
    assert "Push 2 hardware report" in report_path.with_suffix(".md").read_text()


def test_run_selftest_without_hardware_explains_itself(tmp_path, capsys):
    # No push passed and no mido installed in this environment.
    assert run_selftest(tmp_path / "r.json") == 2
    out = capsys.readouterr().out
    assert "could not open the Push 2" in out
