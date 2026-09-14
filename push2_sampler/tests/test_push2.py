from dataclasses import dataclass

import pytest

from push2sampler import colors
from push2sampler.constants import PAD_COUNT, Btn, index_to_note
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
    #: The touch strip's 14-bit value, as mido reports it (IN-07).
    pitch: int = 0
    value: int = 0


def test_pad_notes_become_pad_events():
    assert translate_midi(Msg("note_on", note=92, velocity=110)) == PadEvent(0, True, 110)
    assert translate_midi(Msg("note_off", note=92)) == PadEvent(0, False, 0)
    # A note-on with velocity 0 is a release.
    assert translate_midi(Msg("note_on", note=36, velocity=0)) == PadEvent(56, False, 0)


def test_non_pad_notes_are_ignored():
    assert translate_midi(Msg("note_on", note=0, velocity=120)) is None  # encoder touch
    assert translate_midi(Msg("polytouch", note=92, velocity=40)) is None
    assert translate_midi(Msg("clock")) is None


def test_the_touch_strip_becomes_a_strip_event():
    """It used to be dropped; IN-07 gave it a job.

    Unverified against hardware -- that the strip speaks pitch bend at all comes
    from Ableton's document -- so everything downstream treats it as advisory.
    """
    from push2sampler.push2 import StripEvent

    assert translate_midi(Msg("pitchwheel", pitch=-8192)) == StripEvent(0.0, True)
    assert translate_midi(Msg("pitchwheel", pitch=8191)) == StripEvent(1.0, True)
    bottom = translate_midi(Msg("pitchwheel", pitch=-4096))
    assert bottom.position == pytest.approx(0.25, abs=0.001)
    # The spring-back-to-centre when a finger leaves must not read as "the
    # middle of the song".
    assert translate_midi(Msg("pitchwheel", pitch=0)).touched is False


def test_the_strip_is_monotonic_across_its_range():
    positions = [
        translate_midi(Msg("pitchwheel", pitch=raw)).position
        for raw in range(-8192, 8192, 97)
    ]
    assert positions == sorted(positions)
    assert positions[0] == 0.0 and positions[-1] < 1.0


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


class FakePort:
    """Records everything sent, so the wire format can be asserted."""

    def __init__(self) -> None:
        self.sent: list = []
        self.closed = False

    def send(self, msg) -> None:
        self.sent.append(msg)

    def close(self) -> None:
        self.closed = True


class FakeMessage:
    """Enough of mido.Message to assert what goes on the wire."""

    def __init__(self, type, **fields) -> None:
        self.type = type
        self.channel = fields.get("channel", 0)
        self.note = fields.get("note", 0)
        self.velocity = fields.get("velocity", 0)
        self.control = fields.get("control", 0)
        self.value = fields.get("value", 0)
        self.data = tuple(fields.get("data", ()))


def _opened_push(monkeypatch, **kwargs):
    """A Push2 with a fake mido underneath, opened with the given keywords.

    mido is an optional dependency and is not installed in CI, and these tests
    are about *our* byte layout rather than mido's, so the module is supplied
    here instead of being required.
    """
    import sys
    import types

    port = FakePort()
    names = ["Ableton Push 2 Live Port", "Ableton Push 2 User Port"]
    fake = types.ModuleType("mido")
    fake.Message = FakeMessage
    fake.get_input_names = lambda: names
    fake.get_output_names = lambda: names
    fake.open_output = lambda name: port
    fake.open_input = lambda name, callback=None: FakePort()
    monkeypatch.setitem(sys.modules, "mido", fake)
    push = Push2()
    push.open(**kwargs)
    return push, port


def test_open_uploads_the_palette_and_says_so(monkeypatch):
    push, port = _opened_push(monkeypatch)
    assert push.palette_programmed
    sysex = [m for m in port.sent if m.type == "sysex"]
    # one per colour, plus the reapply
    assert len(sysex) == len(colors.PALETTE) + 1
    assert push.chosen_output == "Ableton Push 2 User Port"


def test_open_can_skip_the_palette_for_the_led_test(monkeypatch):
    """--led-test has to see the pads before the palette is touched."""
    push, port = _opened_push(monkeypatch, program_palette=False)
    assert not push.palette_programmed
    assert [m for m in port.sent if m.type == "sysex"] == []


def test_set_palette_entry_sysex_is_seven_bit_split(monkeypatch):
    """Each colour component goes out as a low 7 bits plus one high bit."""
    _, port = _opened_push(monkeypatch)
    white = [m for m in port.sent
             if m.type == "sysex" and len(m.data) > 6 and m.data[6] == colors.WHITE.index]
    assert white, "no palette entry for white was sent"
    data = list(white[0].data)
    assert data[5] == 0x03                      # set palette entry
    assert data[6] == colors.WHITE.index
    # 255 -> 0x7F low, 1 high; four components (r, g, b, unused white LED)
    assert data[7:15] == [0x7F, 1, 0x7F, 1, 0x7F, 1, 0, 0]


def test_pads_go_out_on_the_static_channel(monkeypatch):
    push, port = _opened_push(monkeypatch)
    port.sent.clear()
    push.set_pad(0, colors.GREEN)
    (msg,) = [m for m in port.sent if m.type == "note_on"]
    assert msg.channel == 0                     # MIDI channel 1: static, no animation
    assert msg.note == index_to_note(0)
    assert msg.velocity == colors.GREEN.index


def test_send_pad_raw_carries_an_explicit_channel_to_the_wire(monkeypatch):
    push, port = _opened_push(monkeypatch)
    port.sent.clear()
    push.send_pad_raw(0, 127, channel=2)
    (msg,) = [m for m in port.sent if m.type == "note_on"]
    assert (msg.channel, msg.velocity) == (2, 127)


def test_send_pad_raw_resends_the_same_value(monkeypatch):
    push, port = _opened_push(monkeypatch)
    push.set_pad(3, colors.RED)
    port.sent.clear()
    push.set_pad(3, colors.RED)                 # deduped
    assert port.sent == []
    push.send_pad_raw(3, colors.RED.index)
    push.send_pad_raw(3, colors.RED.index)      # and again
    assert len([m for m in port.sent if m.type == "note_on"]) == 2


def _mido_with_ports(monkeypatch, names, fail_open=()):
    """A fake mido whose input ports can be opened and fed individually."""
    import sys
    import types

    opened: dict = {}
    out = FakePort()

    class In(FakePort):
        def __init__(self, name, callback) -> None:
            super().__init__()
            self.name = name
            self.callback = callback

    def open_input(name, callback=None):
        if name in fail_open:
            raise OSError(f"{name} busy")
        port = In(name, callback)
        opened[name] = port
        return port

    fake = types.ModuleType("mido")
    fake.Message = FakeMessage
    fake.get_input_names = lambda: list(names)
    fake.get_output_names = lambda: list(names)
    fake.open_output = lambda name: out
    fake.open_input = open_input
    monkeypatch.setitem(sys.modules, "mido", fake)
    return opened, out


BOTH_PORTS = ["Ableton Push 2 Live Port", "Ableton Push 2 User Port"]


def test_every_push_input_port_is_opened_preferred_one_first(monkeypatch):
    """A Push 2 routes its surface to one port or the other by mode.

    Listening to both costs nothing -- only one of them sends -- and means the
    program works without being told which mode the device is in (F-08/5).
    """
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    assert push.chosen_inputs == ["Ableton Push 2 User Port",
                                  "Ableton Push 2 Live Port"]
    assert set(opened) == set(BOTH_PORTS)
    assert push.chosen_input == "Ableton Push 2 User Port"


def test_input_from_the_non_preferred_port_still_reaches_the_app(monkeypatch):
    """The actual bug: the surface was on the Live port and we only read User."""
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    live = opened["Ableton Push 2 Live Port"]
    live.callback(FakeMessage("note_on", note=index_to_note(0), velocity=120))
    assert push.poll_events() == [PadEvent(0, True, 120)]


def test_listen_all_can_be_turned_off(monkeypatch):
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2(listen_all=False)
    push.open()
    assert push.chosen_inputs == ["Ableton Push 2 User Port"]
    assert list(opened) == ["Ableton Push 2 User Port"]


def test_one_unopenable_input_port_does_not_stop_the_other(monkeypatch):
    opened, _ = _mido_with_ports(
        monkeypatch, BOTH_PORTS, fail_open=("Ableton Push 2 User Port",)
    )
    push = Push2()
    push.open()
    assert push.chosen_inputs == ["Ableton Push 2 Live Port"]
    live = opened["Ableton Push 2 Live Port"]
    live.callback(FakeMessage("control_change", control=Btn.PLAY, value=127))
    assert push.poll_events() == [ButtonEvent(Btn.PLAY, True)]


def test_no_openable_input_port_is_an_error(monkeypatch):
    _mido_with_ports(monkeypatch, BOTH_PORTS, fail_open=tuple(BOTH_PORTS))
    push = Push2()
    try:
        push.open()
    except RuntimeError as exc:
        assert "could not open any" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a RuntimeError")


def test_midi_port_forces_one_port_in_both_directions(monkeypatch):
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2(port_name="live")
    push.open()
    assert push.chosen_output == "Ableton Push 2 Live Port"
    assert push.chosen_input == "Ableton Push 2 Live Port"
    # still listens to the other one as well
    assert set(push.chosen_inputs) == set(BOTH_PORTS)


def test_midi_port_overrides_the_user_port_preference():
    push = Push2(port_name="live")
    assert push._pick(BOTH_PORTS, "output") == "Ableton Push 2 Live Port"


def test_an_unmatched_midi_port_says_what_it_had():
    push = Push2(port_name="nonesuch")
    try:
        push._pick(BOTH_PORTS, "input")
    except RuntimeError as exc:
        assert "nonesuch" in str(exc)
        assert "Ableton Push 2 User Port" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a RuntimeError")


def test_close_closes_every_input_port(monkeypatch):
    opened, out = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    push.close()
    assert all(port.closed for port in opened.values())
    assert out.closed
    assert push.chosen_inputs == list(push.chosen_inputs)  # untouched by close


def test_all_off_reaches_buttons_this_process_never_lit(monkeypatch):
    """clear() only knows what it lit, which in a fresh process is nothing.

    A previous run that crashed, or a diagnostic that exited, leaves LEDs on
    that nothing else can reach -- so starting up has to send an explicit off.
    """
    from push2sampler.constants import ALL_BUTTON_CCS

    push = SimPush()
    push.sent.clear()
    push.clear()
    assert [s for s in push.sent if s[0] == "button"] == []   # knows of none

    push.sent.clear()
    push.all_off()
    buttons = {cc: v for kind, cc, v in push.sent if kind == "button"}
    assert set(buttons) == set(ALL_BUTTON_CCS)
    assert set(buttons.values()) == {0}
    pads = {i: v for kind, i, v in push.sent if kind == "pad"}
    assert len(pads) == PAD_COUNT and set(pads.values()) == {0}


def test_open_blanks_the_whole_surface(monkeypatch):
    from push2sampler.constants import ALL_BUTTON_CCS

    _, out = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    zeroed = {m.control for m in out.sent
              if m.type == "control_change" and m.value == 0}
    assert zeroed == set(ALL_BUTTON_CCS)
    notes = {m.note: m.velocity for m in out.sent if m.type == "note_on"}
    assert len(notes) == PAD_COUNT and set(notes.values()) == {0}


def test_every_button_in_the_map_is_in_all_button_ccs():
    """So a control added to Btn cannot be left un-blankable."""
    from push2sampler.constants import (
        ALL_BUTTON_CCS,
        DISPLAY_ROW_BOTTOM,
        DISPLAY_ROW_TOP,
        Btn,
    )

    named = {v for k, v in vars(Btn).items()
             if not k.startswith("_") and isinstance(v, int)}
    assert named <= set(ALL_BUTTON_CCS)
    assert set(DISPLAY_ROW_TOP) <= set(ALL_BUTTON_CCS)
    assert set(DISPLAY_ROW_BOTTOM) <= set(ALL_BUTTON_CCS)


# -- following the surface to whichever port it is on ----------------------
def test_output_follows_the_port_the_input_arrived_on(monkeypatch):
    """Input says which port the device uses; output has no such signal.

    Guessing wrong means a surface that receives fine and stays dark, which is
    exactly what happened on the first real device (F-08 finding 8).
    """
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    assert push.chosen_output == "Ableton Push 2 User Port"

    live = opened["Ableton Push 2 Live Port"]
    live.callback(FakeMessage("note_on", note=index_to_note(0), velocity=100))
    # Applied on the polling thread, not the callback thread.
    assert push.chosen_output == "Ableton Push 2 User Port"
    push.poll_events()
    assert push.chosen_output == "Ableton Push 2 Live Port"
    assert push.followed_output == "Ableton Push 2 Live Port"


def test_following_repaints_everything(monkeypatch):
    """The new port has never had our palette and knows nothing of our state."""
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    push.set_pad(0, colors.GREEN)
    assert push.pad_leds[0] == colors.GREEN.index

    opened["Ableton Push 2 Live Port"].callback(
        FakeMessage("control_change", control=Btn.PLAY, value=127)
    )
    push.poll_events()
    assert push.pad_leds == [-1] * PAD_COUNT       # cache dropped: resend all
    assert push.palette_programmed


def test_input_on_the_port_we_already_send_to_changes_nothing(monkeypatch):
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    user = opened["Ableton Push 2 User Port"]
    user.callback(FakeMessage("note_on", note=index_to_note(0), velocity=100))
    push.poll_events()
    assert push.chosen_output == "Ableton Push 2 User Port"
    assert push.followed_output is None


def test_an_explicit_midi_port_is_never_second_guessed(monkeypatch):
    """--midi-port is a decision, not a hint."""
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2(port_name="user")
    push.open()
    assert push.follow_input is False
    opened["Ableton Push 2 Live Port"].callback(
        FakeMessage("note_on", note=index_to_note(0), velocity=100)
    )
    push.poll_events()
    assert push.chosen_output == "Ableton Push 2 User Port"


def test_events_still_arrive_on_the_switch(monkeypatch):
    """Following a port must not eat the message that triggered it."""
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    opened["Ableton Push 2 Live Port"].callback(
        FakeMessage("note_on", note=index_to_note(5), velocity=100)
    )
    assert push.poll_events() == [PadEvent(5, True, 100)]


def test_input_is_counted_per_port(monkeypatch):
    opened, _ = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    for _ in range(3):
        opened["Ableton Push 2 Live Port"].callback(
            FakeMessage("note_on", note=index_to_note(0), velocity=1)
        )
    assert push.input_seen == {"Ableton Push 2 Live Port": 3}


def test_a_failed_switch_keeps_the_working_port(monkeypatch):
    import sys
    import types

    opened, out = _mido_with_ports(monkeypatch, BOTH_PORTS)
    push = Push2()
    push.open()
    mido = sys.modules["mido"]
    monkeypatch.setattr(
        mido, "open_output",
        lambda name: (_ for _ in ()).throw(OSError("busy")),
    )
    opened["Ableton Push 2 Live Port"].callback(
        FakeMessage("note_on", note=index_to_note(0), velocity=100)
    )
    push.poll_events()
    assert push.chosen_output == "Ableton Push 2 User Port"
    assert push._outport is out          # still usable
