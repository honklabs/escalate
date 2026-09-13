"""Perform mode: play the song in with your hands instead of toggling bars.

The pads are the sample library again, but now they *fire*: a press plays that
sample, quantised to the next grid line so it lands in time even when your hand
does not.  With `Record` armed, each pad you play is also written into the
arrangement at the bar it sounded in -- overdubbing the 64-bar grid live, pass
after pass, which is how people actually write.

`Delete` armed does the opposite: bars the playhead crosses are wiped as it goes,
the classic erase-while-looping gesture.
"""

from __future__ import annotations

from .. import colors
from ..audio import QUANTIZE_BEATS
from ..constants import BTN_BRIGHT, BTN_DIM, BTN_ON, PAD_COUNT, Btn
from ..history import ClearBar, ToggleTrigger
from ..project import FULL_VELOCITY
from .base import Mode

#: Labels for the quantize amounts, matching audio.QUANTIZE_BEATS.
QUANTIZE_LABELS = ("off", "1/4 bar", "1/2 bar", "1 bar")


def _velocity_scale(sensitivity: float, velocity: int) -> float:
    """How loud a hit of ``velocity`` is, at this sample's sensitivity."""
    sensitivity = max(0.0, min(1.0, sensitivity))
    if sensitivity <= 0.0:
        return 1.0
    return (1.0 - sensitivity) + sensitivity * (max(1, velocity) / FULL_VELOCITY)


class PerformMode(Mode):
    name = "perform"
    transient = True

    def __init__(self, app, quantize_index: int = 3) -> None:
        super().__init__(app)
        self.quantize_index = quantize_index % len(QUANTIZE_BEATS)
        self.writing = False
        self._erasing = False
        self._last_erased: int | None = None

    @property
    def quantize_beats(self) -> float:
        return QUANTIZE_BEATS[self.quantize_index]

    def on_enter(self) -> None:
        self.app.notify("perform: pads fire, Record writes, Session exits")

    def on_exit(self) -> None:
        self.writing = False

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        sample = self.project[index]
        if sample is None:
            return True
        scale = _velocity_scale(sample.velocity_sensitivity, velocity)
        self.engine.trigger(
            sample.audio,
            sample.gain * scale,
            slot=index,
            quantize_beats=self.quantize_beats,
        )
        if self.writing:
            bar = self.engine.next_grid_bar(self.quantize_beats)
            if bar not in sample.triggers:
                # Keep the dynamics of the performance, not just its notes.
                self.app.do(ToggleTrigger(index, bar, True, velocity=velocity))
            else:
                self.app.notify(f"slot {index + 1} already plays on bar {bar + 1}")
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.RECORD:
            self.writing = not self.writing
            self.app.notify(
                "writing what you play into the song" if self.writing else "playing only"
            )
            return True
        if cc == Btn.FIXED_LENGTH:
            self.quantize_index = (self.quantize_index + 1) % len(QUANTIZE_BEATS)
            self.app.notify(f"quantize {QUANTIZE_LABELS[self.quantize_index]}")
            return True
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        return False

    def on_tick(self) -> None:
        """Erase as the playhead goes, while Delete is armed."""
        if not (self.app.delete_armed and self.engine.is_playing):
            self._erasing = False
            return
        bar = self.engine.current_bar
        if not self._erasing:
            # Start at the next bar line: the bar already playing is mostly
            # behind you, and wiping it would feel like erasing the past.
            self._erasing = True
            self._last_erased = bar
            return
        if bar < 0 or bar == self._last_erased:
            return
        self._last_erased = bar
        if any(bar in sample.triggers for sample in self.project.filled()):
            self.app.do(ClearBar(bar))

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        sounding = set(self.engine.sounding)
        for i in range(PAD_COUNT):
            sample = self.project[i]
            if sample is None:
                pads[i] = colors.WHITE_DIM.index  # nothing to fire here
            elif i in sounding:
                pads[i] = colors.AMBER.index
            elif not sample.enabled:
                pads[i] = colors.GREEN_DIM.index
            else:
                pads[i] = colors.GREEN.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        if self.writing:
            buttons[Btn.RECORD] = (
                colors.RED.index if self.app.blink else colors.RED_DIM.index
            )
        else:
            buttons[Btn.RECORD] = colors.RED_DIM.index
        buttons[Btn.FIXED_LENGTH] = BTN_ON
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.DELETE] = BTN_BRIGHT if self.app.delete_armed else BTN_DIM

    def status_lines(self) -> list[str]:
        mode = "WRITING" if self.writing else "playing"
        erase = "   ERASING" if self.app.delete_armed else ""
        return [
            f"PERFORM  {mode}  quantize {QUANTIZE_LABELS[self.quantize_index]}{erase}",
            "pads fire samples   Record: write them in   Fixed Length: quantize",
            "Delete: erase bars as they pass   Session: back",
        ]
