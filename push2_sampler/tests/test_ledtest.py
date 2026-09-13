"""The LED diagnostic, driven by scripted answers.

The point of these is the *verdict*: the tool exists to turn a dark grid into
one sentence saying which layer is at fault, so each test pins one of those
sentences against the answers that should produce it.
"""

from __future__ import annotations

import json

import pytest

from push2sampler import colors, ledtest
from push2sampler.constants import GRID_W, PAD_COUNT, Btn, index_to_note
from push2sampler.push2 import SimPush


class FakeMsg:
    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:  # what the report shows
        return self.text


class FeedPush(SimPush):
    """A SimPush that keeps its seeded messages.

    ``run_led_test`` drains stale input before it listens, which is right on
    hardware and would throw away anything a test pre-loaded.
    """

    def drain_raw(self) -> None:
        pass


def run(answers, raw=(), push=None):
    """Drive run_led_test with scripted answers; returns (code, report, said)."""
    push = push or (FeedPush() if raw else SimPush())
    push.open()
    for msg in raw:
        push.raw.put(msg)
    queue = list(answers)
    said: list[str] = []

    def ask(_prompt):
        return queue.pop(0) if queue else ""

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "led-report.json"
        code = ledtest.run_led_test(path, push=push, ask=ask, say=said.append)
        report = json.loads(path.read_text())
    return code, report, "\n".join(said)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    """Stage 0 listens for 20 s; tests must not."""
    monkeypatch.setattr(ledtest, "LISTEN_S", 0.01)


def test_everything_works_says_run_the_selftest():
    # pads light, our palette works, buttons light
    code, report, said = run(["y", "y", "", "y"], raw=[FakeMsg("note_on 92")])
    assert code == 0
    assert "the LEDs are fine" in report["verdict"]
    assert "--selftest" in report["verdict"]


def test_factory_lights_but_ours_does_not_blames_program_palette():
    """The case this tool was written for."""
    code, report, said = run(["y", "n", "n"], raw=[FakeMsg("note_on 92")])
    assert code == 0  # the pads *can* light, so this is not a dead surface
    assert "program_palette is wrong" in report["verdict"]
    assert "64 or above" in report["verdict"]


def test_nothing_in_either_direction_blames_the_connection():
    code, report, said = run(["n", "n", "n", "n", "n", "n", "n"])
    assert code == 1
    assert "not really connected" in report["verdict"]
    assert "power supply" in report["verdict"]
    # and it must not blame the palette, which it cannot know anything about
    assert "program_palette" not in report["verdict"]


def test_buttons_light_but_pads_do_not_blames_pad_addressing():
    code, report, said = run(["n", "n", "y", "n", "n", "n", "n"], raw=[FakeMsg("cc 85")])
    assert code == 1
    assert "buttons light, pads do not" in report["verdict"]
    assert "index_to_note" in report["verdict"]


def test_partial_grid_points_at_the_note_range():
    code, report, said = run(["s", "1,2,3", "y", "", "y"], raw=[FakeMsg("x")])
    assert "Some pads light and some do not" in report["verdict"]
    assert report["findings"][2]["result"] == "1,2,3"


def test_stage_0_records_what_arrived():
    _, report, _ = run(["y", "y", "", "y"],
                       raw=[FakeMsg("note_on note=92 velocity=120")])
    stage0 = report["findings"][0]
    assert stage0["stage"] == "push sends to us"
    assert stage0["result"] == "yes"
    assert "velocity=120" in stage0["detail"]


def test_stage_0_silence_is_recorded_as_a_cause():
    _, report, _ = run(["n", "n", "n", "n", "n", "n", "n"])
    assert report["findings"][0]["result"] == "no"
    assert "not powered" in report["findings"][0]["detail"]


def test_stage_1_is_answered_before_the_palette_is_uploaded():
    """The whole diagnostic rests on this ordering.

    If the palette were uploaded first, stage 1 and stage 2 would be the same
    question and a broken upload would be invisible again.
    """
    order = []

    class OrderPush(SimPush):
        def program_palette(self):
            order.append("palette")

    push = OrderPush()
    push.open()

    def ask(_prompt):
        order.append("asked")
        return "n"

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        ledtest.run_led_test(Path(tmp) / "r.json", push=push, ask=ask, say=lambda *_: None)

    assert order[0] == "asked", "stage 1 must be asked before anything is uploaded"
    assert "palette" in order
    assert order.index("palette") == 1


def test_stage_1_lights_one_velocity_per_row():
    push = SimPush()
    push.open()
    push.sent.clear()
    ledtest._light_rows(push, ledtest.FACTORY_ROW_VELOCITIES)
    sent = [(i, v) for kind, i, v in push.sent if kind == "pad"]
    assert len(sent) == PAD_COUNT
    for row, velocity in enumerate(ledtest.FACTORY_ROW_VELOCITIES):
        row_values = {v for i, v in sent if row * GRID_W <= i < (row + 1) * GRID_W}
        assert row_values == {velocity}


def test_our_rows_are_all_private_palette_indices():
    """If one of these were a factory index the two stages would not compare."""
    for _, index in ledtest.OURS_ROWS:
        assert index >= 64
    assert {index for _, index in ledtest.OURS_ROWS} <= {c.index for c in colors.PALETTE}


def test_send_pad_raw_bypasses_the_dedupe_cache():
    push = SimPush()
    push.open()
    push.set_pad(0, colors.WHITE)
    push.sent.clear()
    push.set_pad(0, colors.WHITE)      # deduped away
    assert push.sent == []
    push.send_pad_raw(0, colors.WHITE.index)
    assert push.sent == [("pad", 0, colors.WHITE.index)]


def test_send_pad_raw_carries_the_channel_to_the_wire():
    """SimPush ignores the channel; the real one must not (see test_push2)."""
    seen = []

    class ChannelPush(SimPush):
        def _send_pad_on(self, index, value, channel):
            seen.append((index, value, channel))

    push = ChannelPush()
    push.open()
    ledtest._light_rows(push, [127] * 8, channel=2)
    assert len(seen) == PAD_COUNT
    assert {channel for _, _, channel in seen} == {2}


def test_channel_stage_is_skipped_when_channel_one_worked():
    _, report, _ = run(["y", "y", "", "y"], raw=[FakeMsg("x")])
    channel = [f for f in report["findings"] if f["stage"] == "channel"]
    assert channel and channel[0]["result"] == "not needed"


def test_channel_stage_reports_which_channel_lit():
    # nothing on channel 1, something on channel 3
    answers = ["n", "n", "n", "n", "n", "y", "n"]
    _, report, _ = run(answers)
    channel = [f for f in report["findings"] if f["stage"] == "channel"][0]
    assert channel["result"] == "3"


def test_buttons_are_resent_even_if_already_lit():
    """The cache would otherwise swallow the one message this stage sends."""
    push = SimPush()
    push.open()
    push.set_button(Btn.PLAY, 127)
    push.sent.clear()
    report = ledtest.LedReport()
    ledtest._stage3_buttons(push, report, lambda _p: "y", lambda *_: None)
    assert ("button", Btn.PLAY, 127) in push.sent


def test_report_carries_the_corner_notes_we_believe():
    _, report, _ = run(["y", "y", "", "y"], raw=[FakeMsg("x")])
    corners = report["believed_corner_notes"]
    assert corners["top-left"] == index_to_note(0)
    assert corners["bottom-right"] == index_to_note(PAD_COUNT - 1)


def test_palette_upload_failure_is_a_finding_not_a_crash():
    class BrokenPush(SimPush):
        def program_palette(self):
            raise RuntimeError("sysex refused")

    push = BrokenPush()
    push.open()
    _, report, said = run(["y", "n", "n"], push=push)
    ours = [f for f in report["findings"] if f["stage"] == "our palette"][0]
    assert ours["result"] == "error"
    assert "sysex refused" in ours["detail"]


def test_grid_is_left_dark_afterwards():
    push = SimPush()
    push.open()
    run(["y", "y", "", "y"], push=push)
    assert push.pad_leds == [-1] * PAD_COUNT  # raw sends invalidate the cache
    assert [v for kind, _, v in push.sent if kind == "pad"][-PAD_COUNT:] == [0] * PAD_COUNT
