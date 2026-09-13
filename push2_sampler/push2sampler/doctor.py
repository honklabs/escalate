"""``python -m push2sampler doctor`` -- what is installed, and what to do about it.

The program degrades rather than refusing to start: no ``soundfile`` means
16-bit WAVs, no ``pyusb`` means no colour display, no ``mido`` means the
simulator only.  That is friendly right up to the moment something does not work
and you cannot tell which of those is why.

So this prints one row per thing that matters, each with its own fix, and
**always exits 0**: "everything is missing" is a diagnosis, not a crash.
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
from pathlib import Path

from . import __version__

OK = "ok"
WARN = "--"
BAD = "!!"

#: Importable name -> (what it gives you, how to get it, fatal without it).
PACKAGES: tuple[tuple[str, str, str, bool], ...] = (
    ("numpy", "all audio maths", "pip install numpy", True),
    ("mido", "MIDI to the Push", "pip install mido python-rtmidi", False),
    ("rtmidi", "the MIDI backend mido uses", "pip install python-rtmidi", False),
    ("sounddevice", "the audio stream", "pip install sounddevice", False),
    ("soundfile", "float32 WAVs (else 16-bit)", "pip install soundfile", False),
    ("usb", "the colour display", "pip install pyusb", False),
    ("PIL", "drawing on that display", "pip install Pillow", False),
)


class Row:
    """One line of the report: a state, a subject, a detail, and a fix."""

    def __init__(self, state: str, what: str, detail: str = "", fix: str = "") -> None:
        self.state, self.what, self.detail, self.fix = state, what, detail, fix

    def __str__(self) -> str:
        line = f"  [{self.state}] {self.what:<18} {self.detail}".rstrip()
        if self.fix and self.state != OK:
            line += f"\n{' ' * 26}-> {self.fix}"
        return line


def _import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _version_of(module) -> str:
    for attribute in ("__version__", "version", "VERSION"):
        value = getattr(module, attribute, None)
        if isinstance(value, str):
            return value
    return "installed"


def packages() -> list[Row]:
    rows = []
    for name, purpose, fix, fatal in PACKAGES:
        module = _import(name)
        if module is not None:
            rows.append(Row(OK, name, f"{_version_of(module)} - {purpose}"))
        else:
            rows.append(Row(BAD if fatal else WARN, name, f"missing - {purpose}", fix))
    return rows


def midi_ports() -> list[Row]:
    mido = _import("mido")
    if mido is None:
        return [Row(WARN, "MIDI ports", "cannot look: mido is missing",
                    "pip install mido python-rtmidi")]
    try:
        names = list(mido.get_input_names())
    except Exception as exc:
        return [Row(BAD, "MIDI ports", f"could not enumerate: {exc}",
                    "check the MIDI backend install")]
    push = [n for n in names if "push" in n.lower()]
    if push:
        return [Row(OK, "Push 2 port", ", ".join(push))]
    if names:
        return [Row(WARN, "Push 2 port", f"not among {len(names)} port(s): "
                    + ", ".join(names[:4]),
                    "plug the Push in with its own power supply, straight into "
                    "the computer, and quit Ableton Live")]
    return [Row(WARN, "Push 2 port", "no MIDI ports at all",
                "plug the Push in; --sim works without it")]


def audio_devices() -> list[Row]:
    sd = _import("sounddevice")
    if sd is None:
        return [Row(WARN, "audio devices", "cannot look: sounddevice is missing",
                    "pip install sounddevice")]
    try:
        devices = list(sd.query_devices())
    except Exception as exc:
        return [Row(BAD, "audio devices", f"could not enumerate: {exc}",
                    "check PortAudio is installed")]
    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    outputs = [d for d in devices if d.get("max_output_channels", 0) > 0]
    rows = [Row(
        OK if inputs and outputs else WARN,
        "audio devices",
        f"{len(inputs)} in, {len(outputs)} out",
        "without an input you cannot record; without an output you hear nothing",
    )]
    try:
        default_in, default_out = sd.default.device
        rate = sd.query_devices(default_out)["default_samplerate"]
        rows.append(Row(OK, "default output",
                        f"device {default_out} at {rate:.0f} Hz"))
        if default_in is not None and default_in >= 0:
            rows.append(Row(OK, "default input", f"device {default_in}"))
    except Exception as exc:
        rows.append(Row(WARN, "default device", f"unknown: {exc}",
                        "pass --input-device / --output-device"))
    return rows


def writable(project: str | Path = "song") -> list[Row]:
    """Can we actually write a project here, and the settings file?"""
    from .settings import default_path

    rows = []
    target = Path(project)
    probe = target if target.exists() else target.parent
    if os.access(probe, os.W_OK):
        rows.append(Row(OK, "project root", f"{probe.resolve()} is writable"))
    else:
        rows.append(Row(BAD, "project root", f"{probe.resolve()} is not writable",
                        "cd somewhere you own, or pass a different project path"))
    config = default_path()
    parent = config.parent if config.parent.exists() else config.parent.parent
    if os.access(parent, os.W_OK):
        rows.append(Row(OK, "settings file", str(config)))
    else:
        rows.append(Row(WARN, "settings file", f"{config} is not writable",
                        "settings will not persist; set XDG_CONFIG_HOME"))
    return rows


def report(project: str | Path = "song") -> list[str]:
    """The whole report as lines, so tests can read it without a terminal."""
    lines = [
        f"push2sampler {__version__}",
        f"  Python {platform.python_version()} on {platform.system()} "
        f"({platform.machine()})",
        f"  {sys.executable}",
        "",
        "Packages",
    ]
    lines += [str(row) for row in packages()]
    lines += ["", "Hardware"]
    lines += [str(row) for row in midi_ports()]
    lines += [str(row) for row in audio_devices()]
    lines += ["", "Writing"]
    lines += [str(row) for row in writable(project)]
    lines += [
        "",
        "Nothing here has been verified against a real Push 2. When you have one:",
        "  python -m push2sampler --selftest",
    ]
    return lines


def run(project: str | Path = "song") -> int:
    """Print the report.  Always 0: a diagnosis is not a failure."""
    for line in report(project):
        print(line)
    return 0
