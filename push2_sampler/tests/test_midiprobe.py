"""The MIDI probe.

This one reports facts rather than asking questions, so the tests fake the
facts: a stand-in ``mido`` module whose ports behave the way a particular
hypothesis would, and then an assertion that the probe names that hypothesis.

The verdict is the whole product -- a JSON dump nobody can read is not a
diagnosis -- so every branch of it is pinned here.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

from push2sampler import midiprobe
from push2sampler.constants import PAD_COUNT


class FakeMessage:
    def __init__(self, type, **fields) -> None:
        self.type = type
        self.__dict__.update(fields)

    def __str__(self) -> str:
        bits = " ".join(f"{k}={v}" for k, v in self.__dict__.items() if k != "type")
        return f"{self.type} {bits}"


class FakeOutput:
    def __init__(self, name, fail_send=False) -> None:
        self.name = name
        self.sent: list = []
        self.fail_send = fail_send
        self.closed = False

    def send(self, msg) -> None:
        if self.fail_send:
            raise OSError("write failed")
        self.sent.append(msg)

    def close(self) -> None:
        self.closed = True


class FakeInput:
    """An input port that can answer by callback, by polling, or not at all."""

    def __init__(self, name, callback=None, via="none", messages=()) -> None:
        self.name = name
        self.via = via
        self.messages = list(messages)
        self.closed = False
        if callback is not None and via == "callback":
            for msg in self.messages:
                callback(msg)

    def iter_pending(self):
        if self.via == "polled":
            out, self.messages = self.messages, []
            return iter(out)
        return iter(())

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True


def install_mido(monkeypatch, *, names, backend="mido.backends.rtmidi",
                 via="none", messages=(), fail_output_open=False,
                 fail_send=False):
    outputs: list[FakeOutput] = []

    def open_output(name):
        if fail_output_open:
            raise OSError("port busy")
        port = FakeOutput(name, fail_send=fail_send)
        outputs.append(port)
        return port

    def open_input(name, callback=None):
        return FakeInput(name, callback=callback, via=via, messages=messages)

    fake = types.ModuleType("mido")
    fake.__version__ = "1.3.0"
    fake.backend = types.SimpleNamespace(name=backend)
    fake.Message = FakeMessage
    fake.get_input_names = lambda: list(names)
    fake.get_output_names = lambda: list(names)
    fake.open_output = open_output
    fake.open_input = open_input
    monkeypatch.setitem(sys.modules, "mido", fake)
    return outputs


def install_usb(monkeypatch, found=True, **attrs):
    device = types.SimpleNamespace(bus=1, address=5, bcdDevice=256,
                                  manufacturer="Ableton AG", product="Ableton Push 2",
                                  serial_number="0123", **attrs)
    core = types.SimpleNamespace(find=lambda **_kw: device if found else None)
    usb = types.ModuleType("usb")
    usb.core = core
    monkeypatch.setitem(sys.modules, "usb", usb)
    monkeypatch.setitem(sys.modules, "usb.core", core)


PORTS = ["Midi Through", "Ableton Push 2 Live Port", "Ableton Push 2 User Port"]


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """Two listen windows per port at 8 s each is not a unit test."""
    monkeypatch.setattr(midiprobe, "LISTEN_S", 0.01)
    monkeypatch.setattr(midiprobe, "BLAST_VELOCITIES", (127,))
    monkeypatch.setattr(midiprobe, "BLAST_PAUSE_S", 0.0)


def run(tmp_path, answers=("n",), **kwargs):
    queue = list(answers)
    said: list[str] = []
    path = tmp_path / "midi-report.json"
    code = midiprobe.run_midi_probe(
        path,
        ask=lambda _p: queue.pop(0) if queue else "n",
        say=said.append,
    )
    return code, json.loads(path.read_text()), "\n".join(said)


# -- port ordering ---------------------------------------------------------
def test_user_port_is_tried_before_the_live_port():
    assert midiprobe._push_ports(PORTS) == [
        "Ableton Push 2 User Port",
        "Ableton Push 2 Live Port",
    ]


def test_non_push_ports_are_left_alone():
    assert "Midi Through" not in midiprobe._push_ports(PORTS)


# -- the verdicts ----------------------------------------------------------
def test_a_wrong_backend_is_reported_before_anything_else(monkeypatch, tmp_path):
    """Everything below the backend is that library's behaviour, not ours."""
    install_mido(monkeypatch, names=PORTS, backend="mido.backends.portmidi")
    install_usb(monkeypatch)
    code, report, said = run(tmp_path)
    assert "not using the python-rtmidi backend" in report["verdict"]
    assert "MIDO_BACKEND" in report["verdict"]
    assert report["environment"]["mido_backend"] == "mido.backends.portmidi"


def test_callback_silent_but_polling_works_blames_us(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS, via="polled",
                 messages=[FakeMessage("note_on", note=92, velocity=120)])
    install_usb(monkeypatch)
    code, report, said = run(tmp_path)
    assert "OUR bug" in report["verdict"]
    assert "push2.py" in report["verdict"]
    assert "the device is fine" in report["verdict"]
    assert code == 0  # input did arrive, by one route


def test_stale_ports_when_usb_cannot_see_the_device(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch, found=False)
    code, report, said = run(tmp_path)
    assert "not on the USB bus" in report["verdict"]
    assert "stale" in report["verdict"]
    assert report["usb"]["found"] is False


def test_silent_both_ways_with_usb_present_blames_another_process(monkeypatch, tmp_path):
    """The case the user actually hit."""
    install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch)
    code, report, said = run(tmp_path)
    assert code == 1
    assert "ports open and accept messages" in report["verdict"]
    assert "not the cable" in report["verdict"]
    assert "Ableton Live" in report["verdict"]
    # It must not blame the palette or the note map, which it cannot know about
    assert "palette" not in report["verdict"]


def test_input_works_output_does_not_blames_what_we_send(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS, via="callback",
                 messages=[FakeMessage("note_on", note=92, velocity=120)])
    install_usb(monkeypatch)
    code, report, said = run(tmp_path, answers=("n",))
    assert "input works, output does not" in report["verdict"]
    assert "index_to_note" in report["verdict"]


def test_both_directions_working_sends_you_back_to_the_led_test(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS, via="callback",
                 messages=[FakeMessage("note_on", note=92, velocity=120)])
    install_usb(monkeypatch)
    code, report, said = run(tmp_path, answers=("y",))
    assert "both directions work" in report["verdict"]
    assert "--led-test" in report["verdict"]
    assert code == 0


# -- what it records -------------------------------------------------------
def test_every_push_port_is_tried_in_both_directions(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch)
    _, report, _ = run(tmp_path)
    tried_out = [a["port"] for a in report["output_attempts"]]
    tried_in = [a["port"] for a in report["input_attempts"]]
    assert tried_out == ["Ableton Push 2 User Port", "Ableton Push 2 Live Port"]
    assert tried_in == tried_out


def test_the_blast_covers_every_pad_and_some_buttons(monkeypatch, tmp_path):
    outputs = install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch)
    _, report, _ = run(tmp_path)
    # one velocity (patched) across 64 pads, plus three buttons
    assert report["output_attempts"][0]["messages_sent"] == PAD_COUNT + 3
    notes = [m for m in outputs[0].sent if m.type == "note_on"]
    assert len({m.note for m in notes}) == PAD_COUNT


def test_a_port_that_will_not_open_is_recorded_not_raised(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS, fail_output_open=True)
    install_usb(monkeypatch)
    code, report, said = run(tmp_path)
    assert all(a["opened"] is False for a in report["output_attempts"])
    assert "port busy" in report["output_attempts"][0]["error"]
    assert "OSError" in report["output_attempts"][0]["error"]


def test_a_failing_send_is_recorded_not_raised(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS, fail_send=True)
    install_usb(monkeypatch)
    _, report, _ = run(tmp_path)
    assert "write failed" in report["output_attempts"][0]["error"]


def test_usb_details_are_captured_when_available(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch)
    _, report, _ = run(tmp_path)
    assert report["usb"]["found"] is True
    assert report["usb"]["product"] == "Ableton Push 2"
    assert report["usb"]["manufacturer"] == "Ableton AG"


def test_unreadable_usb_strings_are_a_finding(monkeypatch, tmp_path):
    """On Linux this is the udev permission problem, and worth naming."""
    class Boom:
        bus = 1
        address = 2
        bcdDevice = 3

        @property
        def manufacturer(self):
            raise ValueError("Operation not permitted")

        product = "Ableton Push 2"
        serial_number = "x"

    core = types.SimpleNamespace(find=lambda **_kw: Boom())
    usb = types.ModuleType("usb")
    usb.core = core
    monkeypatch.setitem(sys.modules, "usb", usb)
    monkeypatch.setitem(sys.modules, "usb.core", core)
    install_mido(monkeypatch, names=PORTS)
    _, report, _ = run(tmp_path)
    assert "unreadable" in report["usb"]["manufacturer"]
    assert "not permitted" in report["usb"]["manufacturer"]


def test_ports_are_listed_in_the_report(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch)
    _, report, _ = run(tmp_path)
    assert report["ports"]["inputs"] == PORTS
    assert report["ports"]["push_outputs"][0] == "Ableton Push 2 User Port"


def test_unusable_mido_is_a_verdict_not_a_traceback(monkeypatch, tmp_path):
    fake = types.ModuleType("mido")
    fake.backend = types.SimpleNamespace(name="mido.backends.rtmidi")

    def boom():
        raise OSError("no MIDI subsystem")

    fake.get_input_names = boom
    fake.get_output_names = boom
    monkeypatch.setitem(sys.modules, "mido", fake)
    install_usb(monkeypatch)
    code, report, said = run(tmp_path)
    assert code == 2
    assert "mido is unusable" in report["verdict"]
    assert "no MIDI subsystem" in report["verdict"]


def test_report_is_written_even_when_nothing_worked(monkeypatch, tmp_path):
    install_mido(monkeypatch, names=PORTS)
    install_usb(monkeypatch, found=False)
    _, report, said = run(tmp_path)
    assert report["kind"] == "midi-probe"
    assert (tmp_path / "midi-report.json").exists()
    assert "written to" in said


def test_the_backend_check_is_not_a_substring_match(monkeypatch, tmp_path):
    """"rtmidi" is a substring of "portmidi" -- po*rtmidi*.

    The obvious `"rtmidi" in name` test waves through the one backend it exists
    to catch, so this pins the exact-match behaviour in both directions.
    """
    assert "rtmidi" in "mido.backends.portmidi"          # the trap
    assert "mido.backends.portmidi" not in midiprobe.RTMIDI_BACKENDS

    install_usb(monkeypatch)
    for backend, caught in (
        ("mido.backends.portmidi", True),
        ("mido.backends.pygame", True),
        ("mido.backends.rtmidi", False),
        ("mido.backends.rtmidi_python", False),
    ):
        install_mido(monkeypatch, names=PORTS, backend=backend)
        _, report, _ = run(tmp_path)
        named = "not using the python-rtmidi backend" in report["verdict"]
        assert named is caught, f"{backend}: expected caught={caught}"


def test_an_unresolved_backend_is_not_reported_as_wrong(monkeypatch, tmp_path):
    """mido leaves .backend unset until first use; that is normal."""
    install_mido(monkeypatch, names=PORTS, backend=None)
    install_usb(monkeypatch)
    _, report, _ = run(tmp_path)
    assert "not using the python-rtmidi backend" not in report["verdict"]


def test_pyusb_missing_is_reported_and_not_fatal(monkeypatch, tmp_path):
    """pyusb is optional, so the bus check has to be allowed to be unavailable."""
    monkeypatch.setitem(sys.modules, "usb", None)
    monkeypatch.setitem(sys.modules, "usb.core", None)
    install_mido(monkeypatch, names=PORTS)
    code, report, said = run(tmp_path)
    assert report["usb"]["checked"] is False
    assert "pyusb not installed" in report["usb"]["note"]
    # and the verdict must not claim the device is off the bus, which it cannot know
    assert "not on the USB bus" not in report["verdict"]
