"""One sample's page: the 64 pads are the 64 bars of one page of the song.

A song is up to four pages of 64 bars, so the pads are a window onto it.
``app.bar_at`` and ``app.pad_of_bar`` are the only places that know which
window, and every gesture below works in absolute bar numbers -- which is why
adding pages barely touched this file.
"""

from __future__ import annotations

import time

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
from ..history import (
    AddLayer,
    ClearTriggers,
    DeleteSample,
    RemoveLayer,
    RepairLength,
    SetBars,
    SetEnabled,
    SetGain,
    SetVelocitySensitivity,
    ToggleTrigger,
)
from ..project import FULL_VELOCITY, PAGE_BARS
from .base import Mode
from .sample_edit import SampleEditMode
from .tag import TagMode

#: Bottom display-row button that fits an off-grid take to its bars.
REPAIR_BUTTON = DISPLAY_ROW_BOTTOM[0]

#: Bars every this many get a faint tint when empty, so phrases are countable.
PHRASE_BARS = 4
#: Bars every this many get a brighter tint: the song's sections.
SECTION_BARS = 16
#: Two presses of the same pad within this are a double tap, not two toggles.
DOUBLE_TAP_S = 0.35


class SampleMode(Mode):
    name = "sample"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        #: The bar being held down, and the state its press painted it to, so
        #: holding one bar and pressing another paints everything between.
        self._held_bar: int | None = None
        self._paint_on = False
        #: Last single tap, for spotting a double tap on the same bar.
        self._tapped_bar: int | None = None
        self._tapped_at = 0.0
        #: First bar of a block being duplicated, once it has been picked.
        self._copy_from: int | None = None
        #: True while a sound-on-sound take is running for this slot.
        self._layering = False

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
            if self._held_bar == self.app.bar_at(index):
                self._held_bar = None
            return True
        sample = self.sample
        if sample is None:
            return True
        if self.app.delete_armed:
            self.app.delete_armed = False
            self.app.do(ClearTriggers(self.slot))
            return True
        bar = self.app.bar_at(index)
        if self.app.duplicate_armed:
            self._duplicate(sample, bar)
            return True
        if self._held_bar is not None and self._held_bar != bar:
            # Hold one bar, press another: paint everything between them to
            # whatever the held bar's own press made it.
            self._paint(sample, self._held_bar, bar)
            return True
        now = time.monotonic()
        if bar == self._tapped_bar and now - self._tapped_at <= DOUBLE_TAP_S:
            self._tapped_bar = None
            self._phrase(sample, bar)
            return True
        self.app.do(ToggleTrigger(self.slot, bar, bar not in sample.triggers))
        self._held_bar = bar
        self._paint_on = bar in sample.triggers
        self._tapped_bar, self._tapped_at = bar, now
        return True

    def _paint(self, sample, anchor: int, other: int) -> None:
        """Set every bar between two pads to the state the first press made."""
        lo, hi = (anchor, other) if anchor <= other else (other, anchor)
        target = FULL_VELOCITY if self._paint_on else None
        changes = {
            bar: target
            for bar in range(lo, hi + 1)
            if (bar in sample.triggers) != self._paint_on
        }
        if not changes:
            return  # the whole range is already painted; say nothing
        verb = "on" if self._paint_on else "off"
        self.app.do(SetBars(self.slot, changes, f"bars {lo + 1}-{hi + 1} {verb}"))

    def _phrase(self, sample, bar: int) -> None:
        """Double tap: fill the next phrase with this take, or clear it.

        The first tap of the double tap has already toggled the bar, so which way
        this goes is simply whether that left the bar playing.
        """
        page_end = (bar // PAGE_BARS + 1) * PAGE_BARS
        end = min(bar + PHRASE_BARS, page_end, self.project.song_bars)
        filling = bar in sample.triggers
        if filling:
            stride = max(1, sample.bars)
            wanted = {b: FULL_VELOCITY for b in range(bar, end, stride)}
        else:
            wanted = {b: None for b in range(bar, end)}
        changes = {
            b: v for b, v in wanted.items() if (b in sample.triggers) != (v is not None)
        }
        span = f"bars {bar + 1}-{end}"
        if not changes:
            self.app.notify(f"nothing to {'fill' if filling else 'clear'} in {span}")
            return
        self.app.do(SetBars(self.slot, changes, f"{'filled' if filling else 'cleared'} {span}"))

    def _duplicate(self, sample, index: int) -> None:
        """Pick the start of a block, then where it goes; the gap is its length."""
        if self._copy_from is None:
            self._copy_from = index
            self.app.notify(f"from bar {index + 1}: now press where it goes")
            return
        source, self._copy_from = self._copy_from, None
        self.app.duplicate_armed = False
        length = index - source
        if length <= 0:
            self.app.notify("press a later bar: the gap is the block length")
            return
        move = self.app.shift
        changes = self.project.copy_bar_range(self.slot, source, index, length, move=move)
        changes = {
            b: v for b, v in changes.items() if (b in sample.triggers) != (v is not None)
            or (v is not None and sample.velocity_at(b) != v)
        }
        if not changes:
            self.app.notify("that block is already there")
            return
        verb = "moved" if move else "copied"
        self.app.do(SetBars(
            self.slot, changes,
            f"{verb} bars {source + 1}-{source + length} to {index + 1}",
        ))

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
        if cc == Btn.DEVICE and sample is not None:
            self.app.push_mode(SampleEditMode(self.app, self.slot))
            return True
        if cc == Btn.ACCENT and sample is not None:
            wanted = 0.0 if sample.velocity_sensitivity > 0 else 1.0
            self.app.do(
                SetVelocitySensitivity(self.slot, wanted, sample.velocity_sensitivity)
            )
            return True
        if cc == Btn.DELETE:
            if self.app.shift:
                if self.app.confirm_delete(self.slot, "slot"):
                    self.app.do(DeleteSample(self.slot))
                    self.app.goto_library()
            else:
                self.app.delete_armed = True
                self.app.notify("press any pad to clear all bars")
            return True
        if cc == Btn.SELECT and sample is not None:
            self.app.push_mode(TagMode(self.app, self.slot))
            return True
        if cc == Btn.NEW and sample is not None:
            self._overdub(sample)
            return True
        if cc == Btn.DUPLICATE and sample is not None:
            self.app.duplicate_armed = not self.app.duplicate_armed
            self._copy_from = None
            self.app.delete_armed = False
            self.app.notify(
                "duplicate: press the first bar of the block"
                if self.app.duplicate_armed else "duplicate off"
            )
            return True
        if cc == REPAIR_BUTTON and sample is not None:
            if self.project.mismatched(sample):
                self.app.do(RepairLength(self.slot))
            else:
                self.app.notify("this take already fits its bars")
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

    def _overdub(self, sample) -> None:
        """`New`: record another pass on top.  `Shift`+`New` peels one off.

        The take plays along wherever it is arranged, which is what makes this
        sound-on-sound rather than just a second recording -- so overdubbing a
        sample that plays nowhere yet is silent, and says so.
        """
        if self.app.shift:
            if sample.layer_count <= 1:
                self.app.notify("only one layer; nothing to remove")
            else:
                self.app.do(RemoveLayer(self.slot))
            return
        if self.engine.rec_state != "idle":
            self.engine.cancel_record()
            self._layering = False
            self.app.notify("layer cancelled")
            return
        self._layering = True
        self.engine.arm_record(
            sample.bars, self.app.count_in_beats,
            pre_roll_bars=self.app.pre_roll_bars,
        )
        extra = "" if sample.triggers else " (not arranged, so you will hear nothing)"
        self.app.notify(f"layering {sample.bars} bar(s) onto slot {self.slot + 1}{extra}")

    def on_engine_event(self, event: tuple) -> None:
        if not self._layering:
            return
        if event[0] == "record_done":
            self._layering = False
            if self.sample is not None:
                self.app.do(AddLayer(self.slot, event[2]))
        elif event[0] == "record_cancelled":
            self._layering = False

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
        for pad in range(PAD_COUNT):
            bar = self.app.bar_at(pad)
            if bar in mine:
                pads[pad] = self._trigger_color(sample, bar)
            elif bar in others:
                pads[pad] = colors.BLUE_DIM.index
            else:
                pads[pad] = _grid_tint(bar)
        if self._copy_from is not None:
            pad = self.app.pad_of_bar(self._copy_from)
            if pad is not None:
                pads[pad] = (
                    colors.BLUE.index if self.app.blink else colors.WHITE.index
                )
        if self.engine.is_playing:
            pad = self.app.pad_of_bar(self.engine.current_bar)
            if pad is not None:
                bar = self.app.bar_at(pad)
                pads[pad] = colors.AMBER.index if bar in mine else colors.WHITE.index

    @staticmethod
    def _trigger_color(sample, bar: int) -> int:
        """Green, in three steps, so you can see how hard a bar was played."""
        if not sample.enabled:
            return colors.GREEN_DIM.index
        if sample.velocity_sensitivity <= 0:
            return colors.GREEN.index
        velocity = sample.velocity_at(bar)
        if velocity >= 100:
            return colors.GREEN.index
        if velocity >= 55:
            return colors.GREEN_MID.index
        return colors.GREEN_DIM.index

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
        buttons[Btn.ACCENT] = (
            BTN_BRIGHT if sample and sample.velocity_sensitivity > 0 else BTN_DIM
        )
        buttons[Btn.DEVICE] = (
            BTN_BRIGHT if sample and not sample.edits.is_default else BTN_ON
        )
        buttons[Btn.DUPLICATE] = BTN_BRIGHT if self.app.duplicate_armed else BTN_DIM
        buttons[Btn.SELECT] = BTN_DIM
        buttons[Btn.NEW] = (
            colors.RED.index if self._layering and self.app.blink else BTN_DIM
        )
        if sample is not None and self.project.mismatched(sample):
            buttons[REPAIR_BUTTON] = BTN_BRIGHT if self.app.blink else BTN_DIM

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["SAMPLE"]
        state = "MUTED" if not sample.enabled else "audible"
        velocity = "velocity" if sample.velocity_sensitivity > 0 else "flat"
        if self.app.duplicate_armed:
            if self._copy_from is None:
                return [
                    "DUPLICATE",
                    "press the first bar of the block you want to repeat",
                    "then press where it should go; the gap is its length",
                    "Shift on the second press moves the block instead",
                ]
            return [
                f"DUPLICATE from bar {self._copy_from + 1}",
                "now press where it goes -- the gap sets how many bars copy",
                f"bar {self._copy_from + 5} would copy a 4-bar block",
                "Shift moves instead of copying   Duplicate cancels",
            ]
        if self._layering:
            return [
                f"LAYERING slot {self.slot + 1}  layer {sample.layer_count + 1}",
                f"{self.engine.rec_state.replace('_', ' ')}, {sample.bars} bar(s)",
                "play along with what is already there",
                "New or Stop cancels",
            ]
        layers = ""
        if sample.layer_count > 1:
            layers = f"  {sample.layer_count} layers"
        lines = [
            f"SLOT {self.slot + 1} {sample.name}  {sample.bars} bar(s)  "
            f"{state}{layers}   page {self.app.page_letter}",
            f"plays on {len(sample.triggers)} bar(s)  gain {sample.gain:.2f}  {velocity}",
            "pad: toggle   hold+pad: paint   double tap: fill 4 bars",
            "Record: re-record   New: layer   Mute: hear   Device: edit"
            + ("   (edited)" if not sample.edits.is_default else ""),
        ]
        if self.project.mismatched(sample):
            measured = sample.bars_at(self.project.bpm, self.project.samplerate,
                                      self.project.beats_per_bar)
            recorded_at = sample.source_bpm or self.project.bpm
            lines.append(
                f"OFF GRID: {measured:.2f} bars at {self.project.bpm:.0f} BPM "
                f"(recorded at {recorded_at:.0f}) - button 1 below to fit"
            )
        return lines


def _grid_tint(bar: int) -> int:
    """Faint marks on phrase and section boundaries so bars are countable."""
    if bar % SECTION_BARS == 0:
        return colors.WHITE_MID.index
    if bar % PHRASE_BARS == 0:
        return colors.WHITE_DIM.index
    return colors.OFF.index
