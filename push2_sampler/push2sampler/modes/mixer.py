"""The mixer: eight slots at a time, with meters on the pads.

`Mix` opens it. The grid stops being a library or an arrangement and becomes
eight vertical level meters, one per slot in the current row, so you can see
which take is too loud rather than guessing from the mix.

Row by row rather than all 64 at once, because there are only eight encoders and
a fader you cannot see the value of is worse than no fader.
"""

from __future__ import annotations

from .. import colors
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    ENCODER_MASTER,
    ENCODER_TRACK,
    GRID_H,
    GRID_W,
    PAD_COUNT,
    Btn,
)
from ..history import SetEnabled, SetGain, SetMasterGain
from .base import Mode

#: Gain change per encoder click.
GAIN_STEP = 0.02
#: Master gain change per click of the master encoder.
MASTER_STEP = 0.02
#: Meter segments at or above these fractions go amber, then red.
METER_HOT = 0.75
METER_PEAK = 0.95


class MixerMode(Mode):
    name = "mixer"
    transient = True

    def __init__(self, app, row: int = 0) -> None:
        super().__init__(app)
        self.row = row
        #: While armed, the buttons under the display solo rather than mute.
        self.solo_armed = False

    @property
    def slots(self) -> range:
        """The eight slots this page is showing."""
        start = self.row * GRID_W
        return range(start, start + GRID_W)

    def on_enter(self) -> None:
        self.app.notify("mixer: encoders set gain, buttons below mute")

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """Pads are meters here, not controls -- but a press picks the row.

        Pressing anywhere in a column selects that column's row of slots, which
        makes the grid navigable without hunting for the arrows.
        """
        if pressed:
            self.row = index // GRID_W
            self.app.notify(f"slots {self.row * GRID_W + 1}-{self.row * GRID_W + GRID_W}")
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc in (Btn.MIX, Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        if cc == Btn.SOLO:
            self._toggle_solo_arm()
            return True
        if cc in DISPLAY_ROW_BOTTOM:
            self._strip_button(DISPLAY_ROW_BOTTOM.index(cc))
            return True
        if cc in (Btn.UP, Btn.DOWN):
            self.row = (self.row + (-1 if cc == Btn.UP else 1)) % GRID_H
            return True
        return False

    def _toggle_solo_arm(self) -> None:
        """Arm soloing, or -- if something is soloed -- clear it."""
        if self.project.soloed is not None:
            self.project.solo(None)
            self.solo_armed = False
            self.app.rebuild_schedule()
            self.app.notify("solo off")
            return
        self.solo_armed = not self.solo_armed
        self.app.notify(
            "solo: press a button below" if self.solo_armed else "solo off"
        )

    def _strip_button(self, column: int) -> None:
        """One of the eight strips: mute it, or solo it while Solo is armed."""
        slot = self.row * GRID_W + column
        sample = self.project[slot]
        if sample is None:
            self.app.notify(f"slot {slot + 1} is empty")
            return
        if self.solo_armed:
            # Solo is a listening decision, not an edit to the song, so it is
            # not on the undo stack -- there is nothing to restore.
            self.project.solo(slot)
            self.solo_armed = False
            self.app.rebuild_schedule()
            soloed = self.project.soloed
            self.app.notify(f"solo slot {soloed + 1}" if soloed is not None else "solo off")
            return
        self.app.do(SetEnabled(slot, not sample.enabled))

    def on_encoder(self, cc: int, delta: int) -> bool:
        if cc == ENCODER_MASTER:
            previous = self.project.master_gain
            gain = max(0.0, min(2.0, previous + delta * MASTER_STEP))
            if gain != previous:
                self.app.do(SetMasterGain(gain, previous))
                self.engine.master_gain = gain
            return True
        if cc in ENCODER_TRACK:
            slot = self.row * GRID_W + ENCODER_TRACK.index(cc)
            sample = self.project[slot]
            if sample is not None:
                gain = max(0.0, min(2.0, sample.gain + delta * GAIN_STEP))
                if gain != sample.gain:
                    self.app.do(SetGain(slot, gain, sample.gain))
            return True
        return False

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        """Eight vertical meters: bottom row is quiet, top row is clipping."""
        for i in range(PAD_COUNT):
            pads[i] = colors.OFF.index
        peaks = self.engine.slot_peaks
        for column, slot in enumerate(self.slots):
            sample = self.project[slot]
            if sample is None:
                continue
            audible = self.project.audible(sample)
            level = peaks[slot] if slot < len(peaks) else 0.0
            lit = min(GRID_H, int(level * GRID_H + 0.5))
            for step in range(GRID_H):
                # Row 0 is the top of the grid, so a meter fills upwards.
                pads[(GRID_H - 1 - step) * GRID_W + column] = self._segment(
                    step, lit, audible
                )

    @staticmethod
    def _segment(step: int, lit: int, audible: bool) -> int:
        fraction = (step + 1) / GRID_H
        if step >= lit:
            # Unlit segments still show the strip exists, and whether it is muted.
            return colors.WHITE_DIM.index if audible else colors.OFF.index
        if not audible:
            return colors.GREEN_DIM.index
        if fraction >= METER_PEAK:
            return colors.RED.index
        if fraction >= METER_HOT:
            return colors.AMBER.index
        return colors.GREEN.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.MIX] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.UP] = buttons[Btn.DOWN] = BTN_DIM
        buttons[Btn.SOLO] = (
            BTN_BRIGHT if (self.solo_armed or self.project.soloed is not None)
            else BTN_DIM
        )
        for column, cc in enumerate(DISPLAY_ROW_BOTTOM):
            slot = self.row * GRID_W + column
            sample = self.project[slot]
            if sample is None:
                buttons[cc] = 0
            elif self.project.soloed == slot:
                buttons[cc] = BTN_BRIGHT
            else:
                buttons[cc] = BTN_DIM if sample.enabled else BTN_ON

    def status_lines(self) -> list[str]:
        first = self.row * GRID_W
        head = f"MIXER  slots {first + 1}-{first + GRID_W}  master {self.project.master_gain:.2f}"
        if self.project.soloed is not None:
            head += f"  SOLO {self.project.soloed + 1}"
        gains = []
        for slot in self.slots:
            sample = self.project[slot]
            if sample is None:
                gains.append("--")
            elif not sample.enabled:
                gains.append("mute")
            else:
                gains.append(f"{sample.gain:.2f}")
        return [
            head,
            " ".join(f"{g:>5}" for g in gains),
            "encoder above each strip: gain   button below: mute",
            "Solo then a button: solo it   up/down: another row   Mix: close",
        ]
