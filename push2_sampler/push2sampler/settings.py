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
    # NH-03 lists 0/1/2/4/8 as the count-in lengths, but this stays a *range*.
    # A closed choices list is what silently swallowed `--samplerate 8000`
    # earlier in this project, and 3 is a real count-in in 3/4 time.
    "count_in_beats": Spec(4, int, 0, 16, label="count-in", unit=" beats"),
    "pre_roll_bars": Spec(0, int, 0, 8, label="pre-roll", unit=" bars"),
    "click_sound": Spec(
        "sine", str, choices=("sine", "tick", "cowbell"), label="click",
    ),
    "click_gain": Spec(1.0, float, 0.0, 2.0, step=0.05, label="click vol"),
    "click_when_recording": Spec(False, bool, label="click on rec only"),
    "click_channel": Spec(None, int, 0, 14, label="click out"),
    #: Blank library pads at full white is glare on 64 pads at once (CC-13).
    "dim_library": Spec(True, bool, label="dim library"),
    "monitor": Spec("off", str, choices=("off", "auto", "on"), label="monitor"),
    "monitor_gain": Spec(1.0, float, 0.0, 2.0, step=0.05, label="mon gain"),
    "rec_latency_ms": Spec(0.0, float, 0.0, 250.0, step=1.0, label="rec lat", unit="ms"),
    "play_while_recording": Spec(True, bool, label="play while rec"),
    "autosave_delay_s": Spec(2.0, float, 0.5, 30.0, step=0.5, label="autosave", unit="s"),
    # Post-take processing.  Off by default: a take should be what you played
    # until you ask for something else.
    "auto_trim": Spec(False, bool, label="auto trim"),
    "auto_normalize": Spec(False, bool, label="auto norm"),
    "auto_fade": Spec(False, bool, label="auto fade"),
    "input_device": Spec(None, int, label="in dev", restarts_audio=True),
    "output_device": Spec(None, int, label="out dev", restarts_audio=True),
    "blocksize": Spec(
        256, int, choices=(64, 128, 256, 512, 1024, 2048), label="block",
        restarts_audio=True,
    ),
    # Changing these needs every loaded take resampled, so they stay on the
    # command line and take effect when the program next starts.  Sample rate is
    # a range, not a list: 8000 and 22050 are as valid as 48000, and a closed
    # list silently turned anything unlisted into the default.
    "samplerate": Spec(48_000, int, 8_000, 192_000, label="rate"),
    "in_channels": Spec(1, int, 1, 8, label="in ch"),
    "out_channels": Spec(2, int, 1, 8, label="out ch"),
}

#: Settings the audio engine consumes, in the order the app pushes them.
ENGINE_SETTINGS: tuple[str, ...] = (
    "click_sound",
    "click_gain",
    "click_when_recording",
    "click_channel",
    "monitor",
    "monitor_gain",
    "play_while_recording",
    "rec_latency_ms",
    "input_device",
    "output_device",
    "blocksize",
)

#: The settings the on-device page exposes, one per button under the display,
#: in pages of eight.  There are more settings than buttons now, so the page
#: scrolls with the up/down arrows rather than leaving any of them unreachable.
EDITABLE_PAGES: tuple[tuple[str, ...], ...] = (
    (
        "count_in_beats",
        "monitor",
        "monitor_gain",
        "rec_latency_ms",
        "play_while_recording",
        "autosave_delay_s",
        "input_device",
        "blocksize",
    ),
    (
        "auto_trim",
        "auto_normalize",
        "auto_fade",
        "dim_library",
    ),
    (
        "pre_roll_bars",
        "click_sound",
        "click_gain",
        "click_when_recording",
        "click_channel",
    ),
)

#: Everything the device can edit, flattened.
EDITABLE: tuple[str, ...] = tuple(n for page in EDITABLE_PAGES for n in page)


#: Remembered session state, so powering on resumes where you left off.  Kept
#: out of :data:`SPECS` on purpose: these are not settings anyone edits, they
#: are a bookmark, and the settings page is built from SPECS.
UI_DEFAULTS: dict = {
    "project": None,
    "mode": "library",
    "slot": None,
    "loop": True,
    "metronome": False,
}
#: What each bookmark field must be.  Stated rather than inferred from the
#: default, because two of the defaults are ``None`` and inferring from that
#: accepts anything -- which is how a string ends up where a slot number goes.
UI_TYPES: dict = {
    "project": str,
    "mode": str,
    "slot": int,
    "loop": bool,
    "metronome": bool,
}
UI_KEY = "ui"


def _ui_ok(value, wanted: type, default) -> bool:
    """Whether ``value`` is an acceptable bookmark for a field of ``wanted``.

    ``bool`` is a subclass of ``int`` in Python, so a plain isinstance check
    would let ``True`` through as a slot number; both directions are excluded.
    """
    if value is None:
        return default is None
    if wanted is bool:
        return isinstance(value, bool)
    if wanted is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, wanted)


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / CONFIG_DIR / CONFIG_FILE


class Settings:
    """A validated settings dictionary that knows how to persist itself."""

    def __init__(self, values: dict | None = None, path: Path | None = None) -> None:
        self.path = path
        self.warning: str | None = None
        self._values = {name: spec.default for name, spec in SPECS.items()}
        #: Where you were last time; see :data:`UI_DEFAULTS`.
        self.ui: dict = dict(UI_DEFAULTS)
        if values:
            self.apply(values)
            self.apply_ui(values.get(UI_KEY))
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

    def apply_ui(self, values) -> None:
        """Merge remembered session state, ignoring anything unrecognisable.

        A bookmark is never worth a crash, so a malformed or foreign value is
        dropped rather than validated loudly.
        """
        if not isinstance(values, dict):
            return
        for name, wanted in UI_TYPES.items():
            if name in values and _ui_ok(values[name], wanted, UI_DEFAULTS[name]):
                self.ui[name] = values[name]

    def remember(self, **values) -> None:
        """Record session state, marking the file as needing a write."""
        for name, value in values.items():
            if name in UI_DEFAULTS and self.ui.get(name) != value:
                self.ui[name] = value
                self.dirty = True

    def as_dict(self) -> dict:
        return {**self._values, UI_KEY: dict(self.ui)}

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
        settings.apply_ui(payload.get(UI_KEY))
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
