from dataclasses import dataclass

from push2sampler import colors
from push2sampler.constants import Btn, index_to_note
from push2sampler.push2 import (
    ButtonEvent,
    EncoderEvent,
    PadEvent,
    Push2,
    SimPush,
    translate_midi,
)


@dataclass
class Msg:
    """A stand-in for a mido message."""

    type: str
    note: int = 0
    velocity: int = 0
    control: int = 0
    value: int = 0


def test_pad_notes_become_pad_events():
    assert translate_midi(Msg("note_on", note=92, velocity=110)) == PadEvent(0, True, 110)
    assert translate_midi(Msg("note_off", note=92)) == PadEvent(0, False, 0)
    # A note-on with velocity 0 is a release.
    assert translate_midi(Msg("note_on", note=36, velocity=0)) == PadEvent(56, False, 0)


def test_non_pad_notes_are_ignored():
    assert translate_midi(Msg("note_on", note=0, velocity=120)) is None  # encoder touch
    assert translate_midi(Msg("polytouch", note=92, velocity=40)) is None
    assert translate_midi(Msg("pitchwheel")) is None


def test_buttons_and_encoders():
    assert translate_midi(Msg("control_change", control=Btn.PLAY, value=127)) == ButtonEvent(
        Btn.PLAY, True
    )
    assert translate_midi(Msg("control_change", control=Btn.PLAY, value=0)) == ButtonEvent(
        Btn.PLAY, False
    )
    assert translate_midi(Msg("control_change", control=14, value=2)) == EncoderEvent(14, 2)
    assert translate_midi(Msg("control_change", control=14, value=126)) == EncoderEvent(14, -2)
    assert translate_midi(Msg("control_change", control=14, value=0)) is None


def test_led_writes_are_deduplicated():
    push = SimPush()
    push.set_pad(0, colors.GREEN)
    push.set_pad(0, colors.GREEN)
    push.set_pad(0, colors.WHITE)
    push.set_button(Btn.PLAY, 127)
    push.set_button(Btn.PLAY, 127)
    assert push.sent == [
        ("pad", 0, colors.GREEN.index),
        ("pad", 0, colors.WHITE.index),
        ("button", Btn.PLAY, 127),
    ]


def test_clear_turns_everything_off():
    push = SimPush()
    push.set_pad(3, colors.GREEN)
    push.set_button(Btn.PLAY, 127)
    push.clear()
    assert push.pad_leds == [0] * 64
    assert push.button_leds[Btn.PLAY] == 0


def test_grid_rendering_is_top_row_first():
    push = SimPush()
    push.set_pad(0, colors.GREEN)
    push.set_pad(63, colors.RED)
    rows = push.grid().splitlines()
    assert rows[0].startswith("G")
    assert rows[7].endswith("R")


def test_events_round_trip_through_the_queue():
    push = SimPush()
    push.press_pad(5)
    push.press_button(Btn.RECORD)
    push.turn(14, -3)
    assert push.poll_events() == [
        PadEvent(5, True, 100),
        PadEvent(5, False, 0),
        ButtonEvent(Btn.RECORD, True),
        ButtonEvent(Btn.RECORD, False),
        EncoderEvent(14, -3),
    ]
    assert push.poll_events() == []


def test_port_selection_prefers_the_user_port():
    push = Push2()
    names = ["Midi Through", "Ableton Push 2 Live Port", "Ableton Push 2 User Port"]
    assert push._pick(names, "input") == "Ableton Push 2 User Port"


def test_port_selection_falls_back_to_the_only_match():
    push = Push2()
    assert push._pick(["Ableton Push 2"], "output") == "Ableton Push 2"


def test_port_selection_reports_a_missing_device():
    push = Push2()
    try:
        push._pick(["Midi Through"], "input")
    except RuntimeError as exc:
        assert "Push 2" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a RuntimeError")


def test_palette_indices_are_unique_and_in_range():
    indices = [c.index for c in colors.PALETTE]
    assert len(set(indices)) == len(indices)
    assert all(1 <= i <= 127 for i in indices)
    assert all(index_to_note(i) in range(36, 100) for i in range(64))
