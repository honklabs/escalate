"""Persistent settings, and the table that describes them.

A standalone instrument should not need a terminal to change its headphone
output, so everything here is editable on the device (see
:mod:`push2sampler.modes.settings`) and remembered in
``~/.config/push2sampler/settings.json``.

:data:`SPECS` is the single source of truth: it supplies the defaults, the
validation, and the labels and step sizes the settings page renders with, so a
new setting is one entry here rather than edits in four files.

Precedence is defaults -> file -> command line, and the command line wins for
one run only: it is not written back.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR = "push2sampler"
CONFIG_FILE = "settings.json"


@dataclass(frozen=True)
class Spec:
    """Everything known about one setting."""

    default: object
    kind: type
    lo: float | None = None
    hi: float | None = None
    choices: tuple = ()
    label: str = ""
    unit: str = ""
    #: How much one encoder click moves a numeric setting.
    step: float = 1.0
    #: True when changing it has to reopen the audio stream.
    restarts_audio: bool = False

    def coerce(self, value):
        """Bring ``value`` into range, or return the default if it is nonsense."""
        if self.kind is bool:
            return bool(value)
        if value is None and self.kind is int and self.lo is None:
            return None  # "default device"
        try:
            value = self.kind(value)
        except (TypeError, ValueError):
            return self.default
        if self.choices and value not in self.choices:
            return self.default
        if self.lo is not None:
            value = max(self.lo, value)
        if self.hi is not None:
            value = min(self.hi, value)
        return self.kind(value)

    def format(self, value) -> str:
        if self.kind is bool:
            return "on" if value else "off"
        if value is None:
            return "default"
        if self.kind is float:
            text = f"{value:.2f}".rstrip("0").rstrip(".")
        else:
            text = str(value)
        return f"{text}{self.unit}"

    def nudge(self, value, delta: int):
        """Move ``value`` by ``delta`` encoder clicks."""
        if self.kind is bool:
            return not value if delta else value
        if self.choices:
            order = list(self.choices)
            index = order.index(value) if value in order else 0
            return order[max(0, min(len(order) - 1, index + delta))]
        if value is None:  # a device index stepping up from "default"
            return self.coerce(max(0, delta - 1))
        return self.coerce(value + delta * self.step)

    def cycle(self, value):
        """Next value, wrapping; what pressing the button does."""
        if self.kind is bool:
            return not value
        if self.choices:
            order = list(self.choices)
            index = order.index(value) if value in order else -1
            return order[(index + 1) % len(order)]
        return self.nudge(value, 1)


SPECS: dict[str, Spec] = {
    "count_in_beats": Spec(4, int, 0, 16, label="count-in", unit=" beats"),
    "monitor": Spec("off", str, choices=("off", "auto", "on"), label="monitor"),
    "monitor_gain": Spec(1.0, float, 0.0, 2.0, step=0.05, label="mon gain"),
    "rec_latency_ms": Spec(0.0, float, 0.0, 250.0, step=1.0, label="rec lat", unit="ms"),
    "play_while_recording": Spec(True, bool, label="play while rec"),
    "autosave_delay_s": Spec(2.0, float, 0.5, 30.0, step=0.5, label="autosave", unit="s"),
    "input_device": Spec(None, int, label="in dev", restarts_audio=True),
    "output_device": Spec(None, int, label="out dev", restarts_audio=True),
    "blocksize": Spec(
        256, int, choices=(64, 128, 256, 512, 1024), label="block", restarts_audio=True
    ),
    # Changing these needs every loaded take resampled, so they stay on the
    # command line and take effect when the program next starts.
    "samplerate": Spec(48_000, int, choices=(44_100, 48_000, 88_200, 96_000), label="rate"),
    "in_channels": Spec(1, int, 1, 8, label="in ch"),
    "out_channels": Spec(2, int, 1, 8, label="out ch"),
}

#: Settings the audio engine consumes, in the order the app pushes them.
ENGINE_SETTINGS: tuple[str, ...] = (
    "monitor",
    "monitor_gain",
    "play_while_recording",
    "rec_latency_ms",
    "input_device",
    "output_device",
    "blocksize",
)

#: The settings the on-device page exposes, one per button under the display.
EDITABLE: tuple[str, ...] = (
    "count_in_beats",
    "monitor",
    "monitor_gain",
    "rec_latency_ms",
    "play_while_recording",
    "autosave_delay_s",
    "input_device",
    "blocksize",
)


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / CONFIG_DIR / CONFIG_FILE


class Settings:
    """A validated settings dictionary that knows how to persist itself."""

    def __init__(self, values: dict | None = None, path: Path | None = None) -> None:
        self.path = path
        self.warning: str | None = None
        self._values = {name: spec.default for name, spec in SPECS.items()}
        if values:
            self.apply(values)
        self.dirty = False

    # ------------------------------------------------------------------
    def __getitem__(self, name: str):
        return self._values[name]

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def get(self, name: str, fallback=None):
        return self._values.get(name, fallback)

    def set(self, name: str, value) -> object:
        """Validate and store one setting; returns the value actually stored."""
        spec = SPECS[name]
        coerced = spec.coerce(value)
        if self._values[name] != coerced:
            self._values[name] = coerced
            self.dirty = True
        return coerced

    def apply(self, values: dict) -> None:
        """Set many settings at once, ignoring names we do not know."""
        for name, value in values.items():
            if name in SPECS:
                self.set(name, value)

    def apply_overrides(self, values: dict) -> None:
        """Like :meth:`apply` but does not mark the file as needing a write."""
        was_dirty = self.dirty
        self.apply(values)
        self.dirty = was_dirty

    def as_dict(self) -> dict:
        return dict(self._values)

    def spec(self, name: str) -> Spec:
        return SPECS[name]

    def label(self, name: str) -> str:
        spec = SPECS[name]
        return f"{spec.label or name} {spec.format(self._values[name])}"

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Read settings from ``path``; fall back to defaults, never raise."""
        resolved = Path(path) if path is not None else default_path()
        settings = cls(path=resolved)
        if not resolved.exists():
            return settings
        try:
            payload = json.loads(resolved.read_text())
            if not isinstance(payload, dict):
                raise ValueError("not a JSON object")
        except Exception as exc:
            settings.warning = f"ignoring {resolved}: {exc}"
            return settings
        settings.apply(payload)
        settings.dirty = False
        return settings

    def save(self) -> Path | None:
        if self.path is None:
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n")
        tmp.replace(self.path)
        self.dirty = False
        return self.path
