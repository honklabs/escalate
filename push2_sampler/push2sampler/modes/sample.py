"""One sample's page: the 64 pads are the 64 bars of the song."""

from __future__ import annotations

from .. import colors
from ..constants import BTN_BRIGHT, BTN_DIM, BTN_ON, ENCODER_TRACK, PAD_COUNT, Btn
from ..history import ClearTriggers, DeleteSample, SetEnabled, SetGain, ToggleTrigger
from .base import Mode

#: Bars every this many get a faint tint when empty, so phrases are countable.
PHRASE_BARS = 4
#: Bars every this many get a brighter tint: the song's sections.
SECTION_BARS = 16


class SampleMode(Mode):
    name = "sample"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        sample = self.sample
        if sample is None:
            self.app.goto_library()
            return
        self.app.notify(f"slot {self.slot + 1}: {sample.bars} bar(s)")

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        sample = self.sample
        if sample is None:
            return True
        if self.app.delete_armed:
            self.app.delete_armed = False
            self.app.do(ClearTriggers(self.slot))
            return True
        self.app.do(ToggleTrigger(self.slot, index, index not in sample.triggers))
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        sample = self.sample
        if cc == Btn.RECORD:
            bars = sample.bars if sample else 1
            self.app.goto_record(self.slot, bars)
            return True
        if cc == Btn.MUTE and sample is not None:
            self.app.do(SetEnabled(self.slot, not sample.enabled))
            return True
        if cc == Btn.DELETE:
            if self.app.shift:
                self.app.do(DeleteSample(self.slot))
                self.app.goto_library()
            else:
                self.app.delete_armed = True
                self.app.notify("press any pad to clear all bars")
            return True
        if cc in (Btn.SESSION, Btn.LEFT, Btn.NOTE):
            self.app.goto_library()
            return True
        if cc in (Btn.UP, Btn.DOWN):
            nxt = self.app.next_filled_slot(self.slot, -1 if cc == Btn.UP else 1)
            if nxt is not None and nxt != self.slot:
                self.app.goto_sample(nxt)
            return True
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        sample = self.sample
        if sample is not None and cc == ENCODER_TRACK[0]:
            gain = max(0.0, min(2.0, sample.gain + delta * 0.02))
            if gain != sample.gain:
                self.app.do(SetGain(self.slot, gain, sample.gain))
            return True
        return False

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        sample = self.sample
        if sample is None:
            for i in range(PAD_COUNT):
                pads[i] = colors.OFF.index
            return
        others = self._other_trigger_bars()
        mine = sample.triggers
        on_color = colors.GREEN.index if sample.enabled else colors.GREEN_DIM.index
        for bar in range(PAD_COUNT):
            if bar in mine:
                pads[bar] = on_color
            elif bar in others:
                pads[bar] = colors.BLUE_DIM.index
            else:
                pads[bar] = _grid_tint(bar)
        if self.engine.is_playing:
            bar = self.engine.current_bar
            if 0 <= bar < PAD_COUNT:
                pads[bar] = colors.AMBER.index if bar in mine else colors.WHITE.index

    def _other_trigger_bars(self) -> set[int]:
        bars: set[int] = set()
        for other in self.project.filled():
            if other.slot != self.slot and other.enabled:
                bars |= other.triggers
        return bars

    def render_buttons(self, buttons: dict[int, int]) -> None:
        sample = self.sample
        buttons[Btn.RECORD] = colors.RED_DIM.index
        buttons[Btn.MUTE] = BTN_BRIGHT if (sample and not sample.enabled) else BTN_DIM
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.DELETE] = BTN_BRIGHT if self.app.delete_armed else BTN_DIM

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["SAMPLE"]
        state = "MUTED" if not sample.enabled else "audible"
        return [
            f"SLOT {self.slot + 1}  {sample.bars} bar(s)  {state}",
            f"plays on {len(sample.triggers)} bar(s)  gain {sample.gain:.2f}",
            "pad: toggle bar   Record: re-record   Mute: hear",
        ]


def _grid_tint(bar: int) -> int:
    """Faint marks on phrase and section boundaries so bars are countable."""
    if bar % SECTION_BARS == 0:
        return colors.WHITE_MID.index
    if bar % PHRASE_BARS == 0:
        return colors.WHITE_DIM.index
    return colors.OFF.index
