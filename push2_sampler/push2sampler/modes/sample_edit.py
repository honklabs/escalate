"""The sample editor: shape a take without losing the recording.

Opened with `Device` from a sample's page.  Each of the eight encoders above the
display owns one parameter -- trim in, trim out, fade in, fade out, pitch, gain,
reverse, normalise -- and the button under each one puts that parameter back to
its default, or toggles it where it is a switch.

The grid is the take: 64 pads, one per slice of the audio, lit by how loud that
slice is.  Trimmed-away slices go dim red, so you can see what you are cutting.
Press a pad to hear the take from that point.

Nothing here touches the recording.  `Shift`+`Device` commits the edits for
good, and even that is one undo step.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import colors
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    ENCODER_TRACK,
    PAD_COUNT,
    Btn,
)
from ..history import ApplyEdits, SetEdit, SetGain
from .base import Mode


@dataclass(frozen=True)
class Param:
    """One editable parameter, and how an encoder moves it."""

    field: str
    label: str
    step: float = 1.0
    lo: float = 0.0
    hi: float = 0.0
    unit: str = ""
    toggle: bool = False

    def nudge(self, value, delta: int):
        if self.toggle:
            return not value if delta else value
        return max(self.lo, min(self.hi, float(value) + delta * self.step))

    def format(self, value) -> str:
        if self.toggle:
            return "on" if value else "off"
        if self.unit == "st":  # semitones read better signed
            return f"{value:+.0f}st" if value else "0"
        return f"{value:.0f}{self.unit}" if value else f"0{self.unit}"


#: One per encoder above the display, in order.  ``gain`` is the sample's own
#: gain rather than an edit, so it is handled separately below.
PARAMS: tuple[Param, ...] = (
    Param("trim_start_ms", "trim in", step=5.0, hi=10_000.0, unit="ms"),
    Param("trim_end_ms", "trim out", step=5.0, hi=10_000.0, unit="ms"),
    Param("fade_in_ms", "fade in", step=2.0, hi=2_000.0, unit="ms"),
    Param("fade_out_ms", "fade out", step=2.0, hi=2_000.0, unit="ms"),
    Param("pitch_semitones", "pitch", step=1.0, lo=-12.0, hi=12.0, unit="st"),
    Param("gain", "gain", step=0.05, lo=0.0, hi=2.0),
    Param("reverse", "reverse", toggle=True),
    Param("normalize", "normalise", toggle=True),
)

#: Amplitude thresholds for the three brightnesses of the waveform.
LOUD = 0.5
MID = 0.12


class SampleEditMode(Mode):
    name = "edit"

    @property
    def title(self) -> str:
        return f"EDIT SLOT {self.slot + 1}"
    transient = True

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        if self.sample is None:
            self.app.pop_mode()
            return
        self.app.notify("edit: encoders shape the take, Device closes")

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """Audition from the pressed slice, so you can hear what you are cutting."""
        if not pressed:
            return True
        sample = self.sample
        if sample is None:
            return True
        audio = sample.effective_audio(self.project.samplerate)
        start = int(index / PAD_COUNT * audio.shape[0])
        if start < audio.shape[0]:
            self.engine.preview(audio[start:], sample.gain, slot=self.slot)
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        sample = self.sample
        if cc == Btn.DEVICE:
            if self.app.shift and sample is not None:
                if sample.edits.is_default:
                    self.app.notify("nothing to apply")
                else:
                    self.app.do(ApplyEdits(self.slot))
            else:
                self.app.pop_mode()
            return True
        if cc in DISPLAY_ROW_BOTTOM and sample is not None:
            index = DISPLAY_ROW_BOTTOM.index(cc)
            if index < len(PARAMS):
                self._reset_or_toggle(PARAMS[index])
            return True
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        if cc not in ENCODER_TRACK or self.sample is None:
            return False
        index = ENCODER_TRACK.index(cc)
        if index < len(PARAMS):
            param = PARAMS[index]
            self._change(param, param.nudge(self._value(param), delta))
        return True

    # -- editing -----------------------------------------------------------
    def _value(self, param: Param):
        sample = self.sample
        if param.field == "gain":
            return sample.gain
        return getattr(sample.edits, param.field)

    def _change(self, param: Param, value) -> None:
        current = self._value(param)
        if value == current:
            return
        if param.field == "gain":
            self.app.do(SetGain(self.slot, value, current))
        else:
            self.app.do(
                SetEdit(
                    self.slot,
                    param.field,
                    value,
                    current,
                    display=f"{param.label} {param.format(value)}",
                )
            )

    def _reset_or_toggle(self, param: Param) -> None:
        """Pressing a button toggles a switch, or puts a number back to zero."""
        if param.toggle:
            self._change(param, not self._value(param))
            return
        default = 1.0 if param.field == "gain" else 0.0
        if self._value(param) == default:
            self.app.notify(f"{param.label} already {param.format(default)}")
            return
        self._change(param, default)

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        sample = self.sample
        if sample is None:
            for i in range(PAD_COUNT):
                pads[i] = colors.OFF.index
            return
        envelope = _envelope(sample.audio, PAD_COUNT)
        kept = _kept_range(sample, self.project.samplerate)
        for i, level in enumerate(envelope):
            if not kept[0] <= i < kept[1]:
                pads[i] = colors.RED_DIM.index  # about to be trimmed away
            elif level >= LOUD:
                pads[i] = colors.GREEN.index
            elif level >= MID:
                pads[i] = colors.GREEN_MID.index
            elif level > 0.0:
                pads[i] = colors.GREEN_DIM.index
            else:
                pads[i] = colors.OFF.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        sample = self.sample
        buttons[Btn.DEVICE] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        for index, cc in enumerate(DISPLAY_ROW_BOTTOM):
            if index >= len(PARAMS):
                buttons[cc] = BTN_DIM
                continue
            param = PARAMS[index]
            changed = sample is not None and self._value(param) != (
                1.0 if param.field == "gain" else (False if param.toggle else 0.0)
            )
            buttons[cc] = BTN_BRIGHT if changed else BTN_ON

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["EDIT"]
        pending = "" if sample.edits.is_default else "   Shift+Device applies"
        lines = [f"EDIT slot {self.slot + 1}{pending}", _wave_line(sample, self.project)]
        row: list[str] = []
        for param in PARAMS:
            row.append(f"{param.label} {param.format(self._value(param))}")
            if len(row) == 4:
                lines.append("   ".join(row))
                row = []
        if row:
            lines.append("   ".join(row))
        return lines


def _envelope(audio: np.ndarray, buckets: int) -> list[float]:
    """Peak amplitude per slice of the take, for drawing it."""
    if audio.shape[0] == 0:
        return [0.0] * buckets
    mono = np.abs(audio).max(axis=1)
    edges = np.linspace(0, mono.shape[0], buckets + 1).astype(int)
    return [
        float(mono[a:b].max()) if b > a else 0.0
        for a, b in zip(edges[:-1], edges[1:])
    ]


def _kept_range(sample, samplerate: int) -> tuple[float, float]:
    """Which slices of the grid survive the trims, as fractional pad indices."""
    total = sample.raw_frames
    if total <= 0:
        return (0.0, float(PAD_COUNT))
    start = sample.edits.trim_start_ms * samplerate / 1000.0
    end = total - sample.edits.trim_end_ms * samplerate / 1000.0
    return (start / total * PAD_COUNT, max(0.0, end) / total * PAD_COUNT)


def _wave_line(sample, project, width: int = 44) -> str:
    """The take as one line of text, so it reads with or without the screen."""
    ramp = " .:-=+*#"
    envelope = _envelope(sample.effective_audio(project.samplerate), width)
    body = "".join(ramp[min(len(ramp) - 1, int(level * len(ramp)))] for level in envelope)
    seconds = sample.frames / max(1, project.samplerate)
    return f"[{body}] {seconds:.2f}s"
