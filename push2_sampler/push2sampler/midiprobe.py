"""``--midi-probe``: facts about the MIDI link, not opinions about it.

``--led-test`` narrows a dark grid down to a layer by asking you what you see.
When its answer is "nothing, in either direction", there is nothing left to see
and the next questions have to be answered by the machine instead.

So this asks nobody anything it can find out itself, and it deliberately
distrusts *our own* code as much as the device:

* which ``mido`` backend is actually loaded -- everything below is that
  library's behaviour, not ours, and a surprising backend explains a lot;
* whether the Push is on the USB bus at all, via ``pyusb``, independently of
  MIDI -- this separates "not plugged in or not powered" from "MIDI layer";
* input read two ways, by **callback** and by **polling**.  ``Push2`` uses a
  callback, so a callback that never fires while polling works would be a bug
  in us, not in the device;
* **both** Push ports, in both directions.  We prefer the one named "User", and
  if the "Live" port answers when the User port does not, that is a finding
  about the device that no amount of staring at our own code would produce;
* every exception, printed rather than swallowed.

It writes ``midi-report.json``.  Nothing here changes a project or a setting.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .constants import PAD_COUNT, USB_PRODUCT_ID, USB_VENDOR_ID, Btn, index_to_note

#: Seconds spent listening on each input port.
LISTEN_S = 8.0

#: Velocities tried on every pad, in one blast per port.  1 is "some colour" on
#: any palette; 127 is the brightest thing the device can be asked for.
BLAST_VELOCITIES: tuple[int, ...] = (127, 122, 45, 1)

#: Pause between velocity passes, so a device that only latches on a change has
#: time to show one.  A constant so the tests can set it to zero.
BLAST_PAUSE_S = 0.15

#: The mido backends this program is written against, matched exactly.
#:
#: Not a substring test: "rtmidi" is a substring of "portmidi" ("po*rtmidi*"),
#: so the obvious ``"rtmidi" in name`` check waves through the one backend it is
#: meant to catch.  Its own test caught that.
RTMIDI_BACKENDS: tuple[str, ...] = (
    "mido.backends.rtmidi",
    "mido.backends.rtmidi_python",
)


@dataclass
class MidiReport:
    environment: dict = field(default_factory=dict)
    usb: dict = field(default_factory=dict)
    ports: dict = field(default_factory=dict)
    output_attempts: list = field(default_factory=list)
    input_attempts: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    lit: str = "unasked"
    verdict: str = ""

    def as_dict(self) -> dict:
        return {
            "kind": "midi-probe",
            "environment": self.environment,
            "usb": self.usb,
            "ports": self.ports,
            "output_attempts": self.output_attempts,
            "input_attempts": self.input_attempts,
            "notes": self.notes,
            "anything_lit": self.lit,
            "verdict": self.verdict,
        }


def _environment() -> dict:
    """What we are running on, and what MIDI library we actually got."""
    info = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "mido": None,
        "mido_backend": None,
        "rtmidi": None,
        "rtmidi_apis": None,
    }
    try:
        import mido

        info["mido"] = getattr(mido, "__version__", "unknown")
        backend = getattr(mido, "backend", None)
        info["mido_backend"] = getattr(backend, "name", str(backend))
    except Exception as exc:
        info["mido"] = f"import failed: {exc}"
        return info
    try:
        import rtmidi

        info["rtmidi"] = getattr(rtmidi, "__version__", "unknown")
        # Which MIDI APIs this build can use.  On macOS there should be
        # CoreMIDI; on Linux, ALSA and/or JACK.  An empty list is the answer.
        try:
            info["rtmidi_apis"] = [
                rtmidi.get_api_display_name(api) for api in rtmidi.get_compiled_api()
            ]
        except Exception as exc:  # pragma: no cover - depends on the build
            info["rtmidi_apis"] = f"unavailable: {exc}"
    except Exception as exc:
        info["rtmidi"] = f"import failed: {exc}"
    return info


def _usb() -> dict:
    """Is the Push on the bus?  Answered without MIDI, so it isolates it."""
    out: dict = {"checked": False}
    try:
        import usb.core
    except Exception as exc:
        out["note"] = f"pyusb not installed ({exc}); cannot check the bus directly"
        return out
    out["checked"] = True
    try:
        device = usb.core.find(idVendor=USB_VENDOR_ID, idProduct=USB_PRODUCT_ID)
    except Exception as exc:
        out["error"] = str(exc)
        if "backend" in str(exc).lower():
            # pyusb is a wrapper; without libusb underneath it can see nothing.
            out["note"] = (
                "pyusb is installed but has no libusb underneath, so it cannot "
                "see the bus -- this says nothing about the Push.  It is also "
                "why the colour display cannot work: install libusb "
                "(macOS: brew install libusb; Debian/Ubuntu: apt install libusb-1.0-0)"
            )
        return out
    if device is None:
        out["found"] = False
        out["note"] = (
            f"no USB device {USB_VENDOR_ID:#06x}:{USB_PRODUCT_ID:#06x} -- if MIDI "
            "ports for it exist anyway, they are stale"
        )
        return out
    out["found"] = True
    for attr in ("bus", "address", "bcdDevice"):
        try:
            out[attr] = getattr(device, attr, None)
        except Exception:  # pragma: no cover
            pass
    for attr, label in (("manufacturer", "manufacturer"), ("product", "product"),
                        ("serial_number", "serial")):
        try:
            out[label] = getattr(device, attr, None)
        except Exception as exc:
            # Reading strings needs permission to talk to the device, which is
            # itself worth knowing: it is the usual Linux udev problem.
            out[label] = f"unreadable: {exc}"
    return out


def _push_ports(names: list[str]) -> list[str]:
    """Push ports, User first -- the order we want to try them in."""
    push = [n for n in names if "push" in n.lower()]
    return sorted(push, key=lambda n: (0 if "user" in n.lower() else 1, n))


def _blast(port, say) -> dict:
    """Light everything, every way, on one output port."""
    import mido

    sent = 0
    for velocity in BLAST_VELOCITIES:
        for index in range(PAD_COUNT):
            port.send(
                mido.Message("note_on", channel=0, note=index_to_note(index),
                             velocity=velocity)
            )
            sent += 1
        time.sleep(BLAST_PAUSE_S)
    for cc in (Btn.PLAY, Btn.RECORD, Btn.SESSION):
        port.send(mido.Message("control_change", channel=0, control=cc, value=127))
        sent += 1
    return {"messages_sent": sent, "velocities": list(BLAST_VELOCITIES)}


def _try_outputs(report: MidiReport, names: list[str], ask, say) -> None:
    import mido

    say("\n[3/5] Sending to every Push output port")
    for name in _push_ports(names):
        attempt: dict = {"port": name}
        say(f"  {name}")
        try:
            port = mido.open_output(name)
        except Exception as exc:
            attempt["opened"] = False
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            say(f"    could not open: {exc}")
            report.output_attempts.append(attempt)
            continue
        attempt["opened"] = True
        try:
            attempt.update(_blast(port, say))
            say(f"    sent {attempt['messages_sent']} messages, no error")
        except Exception as exc:
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            say(f"    send failed: {exc}")
        finally:
            try:
                port.close()
            except Exception as exc:  # pragma: no cover
                attempt["close_error"] = str(exc)
        # Asked per port, not once at the end: a single question after blasting
        # every port cannot say WHICH port lit anything, and that is the whole
        # thing we are trying to find out.  The first version of this tool got
        # that wrong.
        answer = ask(f"    Did anything light from {name}? [y/n] ").strip().lower()
        attempt["lit"] = {"y": "yes", "yes": "yes", "s": "some"}.get(answer, "no")
        if attempt["lit"] != "no":
            report.lit = attempt["lit"]
        report.output_attempts.append(attempt)


def _try_inputs(report: MidiReport, names: list[str], say) -> None:
    """Read each port by callback *and* by polling, and say which worked."""
    import mido

    say("\n[4/5] Listening on every Push input port")
    say("  Press pads and buttons while each one listens.")
    for name in _push_ports(names):
        attempt: dict = {"port": name, "callback": [], "polled": []}
        say(f"  {name} -- {int(LISTEN_S)}s, press things now")
        received: list = []
        try:
            callback_port = mido.open_input(name, callback=received.append)
        except Exception as exc:
            attempt["callback_error"] = f"{type(exc).__name__}: {exc}"
            callback_port = None
            say(f"    callback open failed: {exc}")
        deadline = time.monotonic() + LISTEN_S
        while time.monotonic() < deadline:
            time.sleep(0.1)
        if callback_port is not None:
            try:
                callback_port.close()
            except Exception:  # pragma: no cover
                pass
        attempt["callback"] = [str(m) for m in received[:20]]
        attempt["callback_count"] = len(received)
        say(f"    callback: {len(received)} message(s)")

        # Now the same port, polled.  Push2 uses a callback, so a difference
        # here is our bug rather than the device's.
        polled: list = []
        try:
            with mido.open_input(name) as poll_port:
                say(f"    polling the same port for {int(LISTEN_S)}s, press again")
                deadline = time.monotonic() + LISTEN_S
                while time.monotonic() < deadline:
                    for msg in poll_port.iter_pending():
                        polled.append(msg)
                    time.sleep(0.02)
        except Exception as exc:
            attempt["polled_error"] = f"{type(exc).__name__}: {exc}"
            say(f"    polled open failed: {exc}")
        attempt["polled"] = [str(m) for m in polled[:20]]
        attempt["polled_count"] = len(polled)
        say(f"    polled:   {len(polled)} message(s)")
        for msg in (received[:5] or polled[:5]):
            say(f"      {msg}")
        report.input_attempts.append(attempt)


def _sending_ports(report: MidiReport) -> tuple[list[str], list[str]]:
    """Input ports that carried messages, and those that stayed silent."""
    sending, silent = [], []
    for attempt in report.input_attempts:
        if attempt.get("callback_count") or attempt.get("polled_count"):
            sending.append(attempt["port"])
        else:
            silent.append(attempt["port"])
    return sending, silent


def _verdict(report: MidiReport) -> str:
    usb_found = report.usb.get("found")
    sending, silent = _sending_ports(report)
    lit_ports = [
        a["port"] for a in report.output_attempts if a.get("lit") not in (None, "no")
    ]
    got_input = any(
        a.get("callback_count") or a.get("polled_count") for a in report.input_attempts
    )
    callback_only_broken = any(
        not a.get("callback_count") and a.get("polled_count")
        for a in report.input_attempts
    )
    opened = [a for a in report.output_attempts if a.get("opened")]
    send_errors = [a for a in report.output_attempts if a.get("error")]
    lit = report.lit

    backend = str(report.environment.get("mido_backend") or "")
    # "None" means mido has not resolved a backend yet, which is normal and not
    # a finding; a *named* backend that is not one of ours is.
    if backend and backend != "None" and backend not in RTMIDI_BACKENDS:
        return (
            "VERDICT: mido is not using the python-rtmidi backend "
            f"({backend}).  That backend is what the program is written "
            "against; set MIDO_BACKEND=mido.backends.rtmidi and run this again "
            "before believing anything else here."
        )
    if callback_only_broken:
        return (
            "VERDICT: polling receives and the callback does not.  That is OUR "
            "bug, not the device's -- Push2.open passes a callback to "
            "mido.open_input, and it is not firing on your platform.  The fix "
            "is in push2.py, and the device is fine."
        )
    if sending and silent:
        port = sending[0]
        hint = next((w for w in ("live", "user") if w in port.lower()), None)
        flag = f"--midi-port {hint}" if hint else f'--midi-port "{port}"'
        lit = (", ".join(lit_ports) if lit_ports else "no port lit anything")
        return (
            f"VERDICT: the surface is on ONE port and not the other.  Input "
            f"arrives on {sending} and nothing at all on {silent}.  A Push 2 "
            f"routes its controls to whichever port matches the mode it is in, "
            f"so this is the device telling us which one it is using -- not a "
            f"fault.  Run the program with `{flag}` to use it.  "
            f"(Output: {lit}.)  Since the program now listens to every Push "
            f"port for input, a plain run should also work; the flag pins the "
            f"OUTPUT port, which is the half a listener cannot infer."
        )
    if report.usb.get("checked") and usb_found is False:
        return (
            "VERDICT: the Push is not on the USB bus, even though MIDI ports "
            "with its name exist.  Those ports are stale -- the OS is still "
            "advertising a device that is gone.  Unplug and replug the cable, "
            "then run this again; the ports should disappear and come back."
        )
    if not got_input and lit == "no" and not send_errors and opened:
        extra = ""
        if usb_found:
            extra = (
                "  pyusb DOES see it on the bus, so this is not the cable and "
                "not power: the device is present but its MIDI endpoints are "
                "inert.  That is what a Push 2 does while another process owns "
                "it, and on macOS a second process can open the same port "
                "without error and simply receive nothing."
            )
        return (
            "VERDICT: the ports open and accept messages, and nothing comes "
            "back." + extra + "  Check for anything else holding the Push: "
            "Ableton Live (including a background process after quitting), "
            "Push 2's own firmware updater, a DAW with a control-surface "
            "script, or another copy of this program.  On macOS, look for Live "
            "in Activity Monitor by name."
        )
    if got_input and lit == "no":
        return (
            "VERDICT: input works, output does not.  The device is connected and "
            "talking to us, so this is the colour or note we send -- and since "
            "raw velocities on every pad did nothing, suspect the note numbers "
            "in index_to_note or the channel rather than the palette."
        )
    if got_input and lit in ("yes", "some"):
        return (
            "VERDICT: both directions work now.  Whatever was wrong was not in "
            "this layer -- run --led-test again, then --selftest."
        )
    return (
        "VERDICT: not conclusive.  Send midi-report.json; the useful fields are "
        "environment.mido_backend, usb.found, and the callback vs polled counts "
        "per port."
    )


def run_midi_probe(report_path: Path | str = "midi-report.json",
                   ask=input, say=print) -> int:
    """Gather the facts, print them, write them down.  0 if input arrived."""
    report = MidiReport()

    say("MIDI probe -- nothing lit and nothing received, so: what is true?")
    say("  Reads and reports only.  No project or setting is touched.\n")

    say("[1/5] Environment")
    report.environment = _environment()
    for key, value in report.environment.items():
        say(f"  {key}: {value}")

    say("\n[2/5] Is the Push on the USB bus?  (pyusb, independent of MIDI)")
    report.usb = _usb()
    for key, value in report.usb.items():
        say(f"  {key}: {value}")

    try:
        import mido

        inputs = list(mido.get_input_names())
        outputs = list(mido.get_output_names())
    except Exception as exc:
        say(f"\ncould not enumerate MIDI ports: {exc}")
        report.verdict = f"VERDICT: mido is unusable here: {exc}"
        _write(report, report_path, say)
        return 2
    report.ports = {"inputs": inputs, "outputs": outputs,
                    "push_inputs": _push_ports(inputs),
                    "push_outputs": _push_ports(outputs)}

    try:
        report.lit = "no"
        _try_outputs(report, outputs, ask, say)
        _try_inputs(report, inputs, say)
    except KeyboardInterrupt:
        say("\n  stopped early")

    say("\n[5/5] What that means")
    if report.usb.get("note"):
        report.notes.append(report.usb["note"])
    report.verdict = _verdict(report)
    say("\n" + report.verdict)
    for note in report.notes:
        say("\nALSO: " + note)
    _write(report, report_path, say)
    got_input = any(
        a.get("callback_count") or a.get("polled_count") for a in report.input_attempts
    )
    return 0 if got_input else 1


def _write(report: MidiReport, report_path: Path | str, say) -> None:
    path = Path(report_path)
    path.write_text(json.dumps(report.as_dict(), indent=2) + "\n")
    say(f"\nwritten to {path} -- paste it back, it is all facts and no opinions.")
