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
    CHOKE_GROUPS,
    DISPLAY_ROW_BOTTOM,
    ENCODER_TRACK,
    NUDGE_MAX_MS,
    PAD_COUNT,
    PLAY_MODE_LABELS,
    PLAY_MODES,
    Btn,
)
from ..history import (
    AddLayer,
    ClearTriggers,
    DeleteSample,
    RemoveLayer,
    RemoveTake,
    RepairLength,
    SetActiveTake,
    SetBars,
    SetChokeGroup,
    SetTakeMode,
    SetPlayMode,
    SetEnabled,
    SetChanceSeed,
    SetEveryN,
    SetGain,
    SetNudge,
    SetProbability,
    SetVelocitySensitivity,
    ToggleTrigger,
)
from ..project import (
    CERTAIN,
    FULL_VELOCITY,
    MAX_EVERY_N,
    PAGE_BARS,
    TAKE_FIXED,
    TAKE_MODES,
)

#: Milliseconds per click of the nudge encoder (NH-02).
NUDGE_STEP_MS = 5.0
#: Percentage points per click of the probability encoder (NH-10).
PROBABILITY_STEP = 5
#: How many project dice there are.  Small enough to walk through and come
#: back to the one you liked, which is the whole reason it is a seed.
CHANCE_SEEDS = 64
#: What each take mode does, in the words the display has room for (IN-06).
TAKE_MODE_HELP = {
    "fixed": "fixed: always the take you picked",
    "cycle": "cycle: the next take each pass",
    "random": "random: a take per hit, same every time",
}
from .base import Mode
from .harmony import HarmonyMode
from .info import InfoMode
from .pattern import PatternMode
from .sample_edit import SampleEditMode
from .slice import SliceMode
from .tag import TagMode

#: Bottom display-row button that fits an off-grid take to its bars.
REPAIR_BUTTON = DISPLAY_ROW_BOTTOM[0]

#: Buttons 2-5 below the display pick the play mode, one each (NF-02).
#:
#: The plan wanted 1-4 for the modes and 5-8 for the choke group, but button 1
#: is already the off-grid repair, and eight choke groups plus "off" do not fit
#: in four buttons.  So the modes shift one right and the group cycles on the
#: last button, where the display names the value.
PLAY_MODE_BUTTONS: dict[int, str] = dict(zip(DISPLAY_ROW_BOTTOM[1:5], PLAY_MODES))
#: Button 8 cycles the choke group: off, 1..8, off.
CHOKE_BUTTON = DISPLAY_ROW_BOTTOM[7]
#: Button 7 cycles the take mode; `Shift` + it removes the selected take
#: (IN-06).  Both on one button because `Delete` is already "clear all bars"
#: and `Shift`+`Delete` is already "delete the sample", so removing one
#: alternate had nowhere else to go -- and `Shift` reading as "the destructive
#: one" is the pattern this surface already uses.
TAKE_BUTTON = DISPLAY_ROW_BOTTOM[6]

#: Bars every this many get a faint tint when empty, so phrases are countable.
PHRASE_BARS = 4
#: Bars every this many get a brighter tint: the song's sections.
SECTION_BARS = 16
#: Two presses of the same pad within this are a double tap, not two toggles.
DOUBLE_TAP_S = 0.35


class SampleMode(Mode):
    name = "sample"

    @property
    def title(self) -> str:
        sample = self.sample
        named = f' "{sample.name}"' if sample else ""
        return f"SLOT {self.slot + 1}{named}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        #: The bar being held down, and the state its press painted it to, so
        #: holding one bar and pressing another paints everything between.
        self._held_bar: int | None = None
        self._paint_on = False
        #: Last single tap, for spotting a double tap on the same bar.
        self._tapped_bar: int | None = None
        #: Bar that Shift + encoder 2 adjusts, or None.
        self._selected_bar: int | None = None
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
        # The bar Shift + encoder 2 adjusts (NH-10).  "The selected bar" in the
        # plan had no referent on this page, and the last one you touched is
        # the only candidate a hand would agree with.
        self._selected_bar = bar if bar in sample.triggers else None
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
            if self.app.shift and sample is not None:
                # An alternate, not a replacement (IN-06).  The plan put this
                # behind a setting, but a setting that silently changes what
                # `Record` does is worse than two gestures you can see: you
                # would press Record expecting a fresh take and quietly collect
                # eight.  The length is fixed to the existing take's, because an
                # alternate of a different length is not an alternate.
                self.app.goto_record(self.slot, bars, alternate=True)
            else:
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
        if cc == Btn.CONVERT and sample is not None:
            self.app.push_mode(SliceMode(self.app, self.slot))
            return True
        if cc == Btn.SCALE and sample is not None:
            self.app.push_mode(HarmonyMode(self.app, self.slot))
            return True
        if cc == Btn.LAYOUT and sample is not None:
            self.app.push_mode(InfoMode(self.app, self.slot))
            return True
        if cc == Btn.AUTOMATE and sample is not None:
            self.app.push_mode(PatternMode(self.app, self.slot))
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
        if cc in PLAY_MODE_BUTTONS and sample is not None:
            wanted = PLAY_MODE_BUTTONS[cc]
            if wanted == sample.play_mode:
                self.app.notify(f"already {PLAY_MODE_LABELS[wanted]}")
            else:
                self.app.do(SetPlayMode(self.slot, wanted, sample.play_mode))
            return True
        if cc == TAKE_BUTTON and sample is not None:
            self._take_button(sample)
            return True
        if cc == CHOKE_BUTTON and sample is not None:
            # off -> 1 -> ... -> 8 -> off
            current = sample.choke_group or 0
            group = None if current >= CHOKE_GROUPS else current + 1
            self.app.do(SetChokeGroup(self.slot, group, sample.choke_group))
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
            if sample.takes:
                # Layers and alternates never coexist: adding an alternate
                # flattens the breakdown, so there is genuinely nothing to peel
                # and saying which take to remove instead is more use than
                # "nothing to remove".
                self.app.notify(
                    "no layers on a slot with takes - Shift+button 7 removes a take"
                )
            elif sample.layer_count <= 1:
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
        if sample is None:
            return False
        if cc == ENCODER_TRACK[0]:
            gain = max(0.0, min(2.0, sample.gain + delta * 0.02))
            if gain != sample.gain:
                self.app.do(SetGain(self.slot, gain, sample.gain))
            return True
        if cc == ENCODER_TRACK[1]:
            if self.app.shift:
                self._set_probability(sample, delta)
            else:
                self._nudge(sample, delta)
            return True
        if cc == ENCODER_TRACK[2]:
            if self.app.shift:
                self._set_every_n(sample, delta)
            else:
                self._select_take(sample, delta)
            return True
        if cc == ENCODER_TRACK[3]:
            if self.app.shift:
                self._reroll(delta)
            else:
                self._set_take_mode(sample, delta)
            return True
        return False

    def _select_take(self, sample, delta: int) -> None:
        """Encoder 3: which alternate this slot plays (IN-06).

        Auditionable by ear as you turn: selecting a take installs it as the
        slot's audio, so `Play` and a pad press both give you the one you are
        looking at.
        """
        if not sample.takes:
            self.app.notify("only one take - Shift+Record adds another")
            return
        wanted = max(0, min(sample.take_count - 1, sample.active_take + delta))
        if wanted == sample.active_take:
            return
        self.app.do(SetActiveTake(self.slot, wanted, sample.active_take))
        self.app.notify(f"take {wanted + 1} of {sample.take_count}")

    def _take_help(self, sample) -> str:
        """The alternates line, or how to make some (IN-06)."""
        if not sample.takes:
            return "Shift+Record: another take of this part, beside this one"
        return (f"take {sample.active_take + 1} of {sample.take_count}   "
                f"{TAKE_MODE_HELP[sample.take_mode]}   "
                "enc 3: pick   4: mode")

    def _take_button(self, sample) -> None:
        """Button 7: cycle the take mode, or `Shift` to remove a take (IN-06)."""
        if self.app.shift:
            if not sample.takes:
                self.app.notify("only one take - Shift+Record adds another")
                return
            self.app.do(RemoveTake(self.slot))
            left = sample.take_count
            self.app.notify(
                f"take removed - {left} take(s) left" if sample.takes
                else "take removed - one take left"
            )
            return
        if not sample.takes:
            self.app.notify("only one take - Shift+Record adds another")
            return
        self._set_take_mode(sample, 1 if sample.take_mode != TAKE_MODES[-1]
                            else -(len(TAKE_MODES) - 1))

    def _set_take_mode(self, sample, delta: int) -> None:
        """Encoder 4: fixed / cycle / random (IN-06)."""
        if not sample.takes:
            self.app.notify("only one take - Shift+Record adds another")
            return
        current = TAKE_MODES.index(
            sample.take_mode if sample.take_mode in TAKE_MODES else TAKE_FIXED
        )
        wanted = max(0, min(len(TAKE_MODES) - 1, current + delta))
        if wanted == current:
            return
        mode = TAKE_MODES[wanted]
        self.app.do(SetTakeMode(self.slot, mode, sample.take_mode))
        self.app.notify(TAKE_MODE_HELP[mode])

    def _set_probability(self, sample, delta: int) -> None:
        """Shift + encoder 2: how likely the selected bar is to play (NH-10).

        Needs a bar chosen, and says so rather than picking one: silently
        editing whichever bar happened to be first would be worse than asking.
        """
        bar = self._selected_bar
        if bar is None or bar not in sample.triggers:
            self.app.notify("press a bar first, then Shift + encoder 2")
            return
        current = sample.probabilities.get(bar, CERTAIN)
        wanted = max(PROBABILITY_STEP,
                     min(CERTAIN, current + delta * PROBABILITY_STEP))
        if wanted == current:
            return
        self.app.do(SetProbability(self.slot, bar, wanted, current))
        self.app.notify(
            f"bar {bar + 1}: {'always plays' if wanted >= CERTAIN else f'{wanted}% chance'}"
        )

    def _set_every_n(self, sample, delta: int) -> None:
        """Shift + encoder 3: play only on every Nth pass of the loop."""
        current = sample.every_n or 1
        wanted = max(1, min(MAX_EVERY_N, current + delta))
        if wanted == current:
            return
        self.app.do(SetEveryN(self.slot, 0 if wanted == 1 else wanted,
                              sample.every_n))
        self.app.notify(
            "every pass" if wanted == 1 else f"only every {wanted} passes"
        )

    def _chance_summary(self, sample) -> str:
        """What is uncertain about this sample, or nothing at all (NH-10).

        Only shown when something is set: "100% chance" on every bar of every
        ordinary sample would be four lines of noise on a four-line display.
        """
        parts = []
        maybe = len(sample.probabilities)
        if maybe:
            parts.append(f"{maybe} maybe-bar(s)")
        if (sample.every_n or 1) > 1:
            parts.append(f"every {sample.every_n} passes")
        if parts:
            parts.append(f"dice {self.project.chance_seed}")
        return ("   " + "   ".join(parts)) if parts else ""

    def _chance_help(self, sample) -> str:
        bar = self._selected_bar
        if bar is not None and bar in sample.triggers:
            chance = sample.probabilities.get(bar, CERTAIN)
            state = "always" if chance >= CERTAIN else f"{chance}%"
            return (f"bar {bar + 1} selected ({state})   "
                    "Shift+enc 2: chance   3: passes   4: dice")
        return ("press a bar, then Shift+enc 2: chance   "
                "3: every Nth pass   4: reroll the dice")

    def _reroll(self, delta: int) -> None:
        """Shift + encoder 4: the project's dice (NH-10).

        Per project rather than per sample, because the point of a seed is that
        the *whole* arrangement varies together and reproducibly -- and it is
        editable at all because otherwise the seed is 0 for ever and a
        probabilistic song has exactly one variation.
        """
        if not self._uses_chance():
            self.app.notify("nothing has a chance set yet - Shift+enc 2 first")
            return
        previous = self.project.chance_seed
        wanted = (previous + delta) % CHANCE_SEEDS
        if wanted == previous:
            return
        self.app.do(SetChanceSeed(wanted, previous))
        self.engine.chance_seed = wanted
        self.app.notify(f"dice {wanted}: a different variation, same every time")

    def _uses_chance(self) -> bool:
        return any(
            other.probabilities or (other.every_n or 1) > 1
            for other in self.project.filled()
        )

    def _nudge(self, sample, delta: int) -> None:
        """Lay this sample back behind the beat, in milliseconds (NH-02).

        Late only.  Pushing one sample *ahead* of the beat would need the
        engine to know about a bar line before it arrives, and the feel is
        relative anyway: laying everything else back is how you push one thing
        forward.
        """
        wanted = max(0.0, min(NUDGE_MAX_MS, sample.nudge_ms + delta * NUDGE_STEP_MS))
        if wanted == sample.nudge_ms:
            return
        self.app.do(SetNudge(self.slot, wanted, sample.nudge_ms))
        self.app.notify(
            "on the beat" if not wanted else f"{wanted:.0f}ms behind the beat"
        )

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

    def _trigger_color(self, sample, bar: int) -> int:
        """Green, in three steps, so you can see how hard a bar was played.

        A bar with a **probability** below 100 flashes between its colour and
        dark instead (NH-10).  Brightness is already spoken for by velocity --
        the plan wanted probability there too, and the two would have been
        indistinguishable -- and a pad that blinks is a much better way to say
        "this might not play" than a shade nobody can calibrate by eye.
        """
        base = self._velocity_color(sample, bar)
        if sample.probabilities.get(bar, CERTAIN) < CERTAIN and not self.app.blink:
            return colors.OFF.index
        return base

    @staticmethod
    def _velocity_color(sample, bar: int) -> int:
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
        buttons[Btn.CONVERT] = BTN_ON if sample is not None else 0
        buttons[Btn.LAYOUT] = BTN_ON if sample is not None else 0
        buttons[Btn.SCALE] = BTN_ON if sample is not None else 0
        buttons[Btn.AUTOMATE] = BTN_ON if sample is not None else 0
        buttons[Btn.NEW] = (
            colors.RED.index if self._layering and self.app.blink else BTN_DIM
        )
        if sample is not None:
            for cc, mode in PLAY_MODE_BUTTONS.items():
                buttons[cc] = BTN_BRIGHT if sample.play_mode == mode else BTN_DIM
            buttons[CHOKE_BUTTON] = BTN_ON if sample.choke_group else BTN_DIM
            # Lit only when there is a choice to make: a single-take slot's
            # button would be a light with nothing behind it.
            buttons[TAKE_BUTTON] = BTN_ON if sample.takes else 0
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
        elif sample.takes:
            # Never both: adding an alternate flattens the layers.
            layers = f"  take {sample.active_take + 1}/{sample.take_count}"
        lines = [
            f"SLOT {self.slot + 1} {sample.name}  {sample.bars} bar(s)  "
            f"{state}{layers}   page {self.app.page_letter}",
            f"plays on {len(sample.triggers)} bar(s)  gain {sample.gain:.2f}  {velocity}"
            + (f"  +{sample.nudge_ms:.0f}ms" if sample.nudge_ms else "")
            + self._chance_summary(sample),
            f"{PLAY_MODE_LABELS[sample.play_mode]}"
            + (f"  choke {sample.choke_group}" if sample.choke_group else "")
            + (f"  takes {sample.take_mode}" if sample.takes else "")
            + "   buttons 2-5: mode   7: takes   8: choke group",
            "pad: toggle   hold+pad: paint   double tap: fill 4 bars",
            "encoder 1: gain   encoder 2: lay it back behind the beat",
            self._chance_help(sample),
            self._take_help(sample),
            "Record: re-record   New: layer   Mute: hear   Device: edit"
            "   Convert: slice   Layout: about   Automate: pattern"
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
