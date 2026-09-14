"""Record mode: choose a length in bars, then record it after a count-in."""

from __future__ import annotations

from .. import analysis, colors
from ..constants import (
    BTN_DIM,
    BTN_OFF,
    BTN_ON,
    ENCODER_TRACK,
    PAD_COUNT,
    RING,
    Btn,
)

#: Set form, for asking whether a pad is part of the ring.
RING_SET = frozenset(RING)
from ..history import AddTake, PutSample
from ..project import MAX_TAKES, SONG_BARS
from .base import Mode


class RecordMode(Mode):
    name = "record"

    @property
    def title(self) -> str:
        what = "TAKE" if self.alternate else "RECORD"
        return f"{what} {self.bars} BAR{'S' if self.bars != 1 else ''}"

    def __init__(self, app, slot: int, bars: int = 1,
                 alternate: bool = False) -> None:
        super().__init__(app)
        self.slot = slot
        self.bars = max(1, min(SONG_BARS, bars))
        #: Keep the take beside the slot's existing one instead of replacing it
        #: (IN-06).  Set by `Shift`+`Record` from a sample page.
        self.alternate = alternate

    @property
    def full(self) -> bool:
        """True when an alternate cannot be added because the slot is full."""
        sample = self.project[self.slot]
        return bool(self.alternate and sample is not None
                    and sample.take_count >= MAX_TAKES)

    def on_enter(self) -> None:
        if self.full:
            self.app.notify(f"slot {self.slot + 1}: {MAX_TAKES} takes already")
        elif self.alternate:
            self.app.notify(
                f"slot {self.slot + 1}: another take, {self.bars} bar(s) - press Record"
            )
        else:
            self.app.notify(f"slot {self.slot + 1}: pick length, then Record")

    def on_exit(self) -> None:
        if self.engine.rec_state != "idle":
            self.engine.cancel_record()

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        if self.engine.rec_state != "idle":
            return True  # length is locked once the count-in has started
        if self.alternate:
            # An alternate is the same length as what it replaces, or it is not
            # an alternate -- switching takes would change the arrangement.
            self.app.notify("an alternate take keeps the length of the original")
            return True
        # The selection always starts at the top-left pad, so the pad that was
        # pressed is simply the last included bar.
        self.bars = index + 1
        self.app.notify(f"length: {self.bars} bar{'s' if self.bars != 1 else ''}")
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.RECORD:
            if self.full:
                self.app.notify(f"slot {self.slot + 1} already holds {MAX_TAKES} takes")
            elif self.engine.rec_state == "idle":
                self.engine.arm_record(
                    self.bars, self.app.count_in_beats,
                    pre_roll_bars=self.app.pre_roll_bars,
                )
            else:
                self.engine.cancel_record()
                self.app.notify("take cancelled")
            return True
        if cc == Btn.STOP:
            if self.engine.rec_state != "idle":
                self.engine.cancel_record()
                self.app.notify("take cancelled")
            else:
                self.app.goto_library()
            return True
        if cc in (Btn.SESSION, Btn.LEFT, Btn.NOTE):
            self.app.goto_library()
            return True
        if cc == Btn.PLAY and self.engine.rec_state != "idle":
            return True  # don't let Play disturb a take in progress
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        if self.alternate:
            return True
        if cc == ENCODER_TRACK[0] and self.engine.rec_state == "idle":
            self.bars = max(1, min(SONG_BARS, self.bars + delta))
            return True
        return False

    def on_engine_event(self, event: tuple) -> None:
        if event[0] == "record_done":
            bars, audio = event[1], event[2]
            audio, notes = self._post_process(audio)
            coaching = self._coach(audio, bars)
            if self.alternate and self.project[self.slot] is not None:
                self.app.do(AddTake(self.slot, audio))
            else:
                self.app.do(PutSample(self.slot, audio, bars))
            self.app.goto_sample(self.slot)
            # After the page change, not before: goto_sample announces the slot,
            # which would otherwise bury the news that the take was processed.
            if coaching:
                # Last, so it is the line left on the display: how you played
                # is more interesting than what was normalised.
                notes = notes + [coaching]
            if notes:
                self.app.notify("   ".join(notes))

    def _coach(self, audio, bars: int) -> str:
        """How tight the take was, when the `coach` setting asks (IN-08).

        Measured on the audio as stored, so auto-trim's shift is included --
        a take that was slid onto the grid really is on the grid now, and
        reporting the pre-trim timing would be reporting something you no
        longer have.
        """
        if not self.app.settings.get("coach"):
            return ""
        samplerate = self.engine.transport.samplerate
        found = analysis.onsets(audio, samplerate)
        report = analysis.timing_report(
            found, samplerate, self.engine.bpm,
            self.engine.transport.beats_per_bar,
        )
        return report.summary()

    def _post_process(self, audio):
        """Apply the optional auto-trim / normalise / fade, all off by default.

        Undoing the take restores whatever the slot held before, so this needs
        no separate undo of its own -- but it does need to say what it did.
        """
        settings = self.app.settings
        if not any(settings.get(name) for name in ("auto_trim", "auto_normalize",
                                                   "auto_fade")):
            return audio, []
        return analysis.process_take(
            audio,
            self.engine.transport.samplerate,
            trim=bool(settings.get("auto_trim")),
            normalise=bool(settings.get("auto_normalize")),
            fade=bool(settings.get("auto_fade")),
        )

    # -- output ------------------------------------------------------------
    def _count_in_ring(self, pads: list[int]) -> None:
        """The count-in round the edge of the grid, one pad per 16th (IN-07).

        A shape filling clockwise is something you can feel arriving out of the
        corner of your eye; a number is something you have to read.  The take's
        own length still shows in the middle, so you have not lost sight of what
        you are about to record.

        The pre-roll flashes the whole ring instead of filling it: nothing is
        being counted yet, and a ring that started filling during the run-up
        would arrive at the top a bar early.
        """
        elapsed, total = self.engine.count_in_sixteenths
        if self.engine.in_pre_roll or total <= 0:
            lit = self.engine.beat_phase < 0.5
            for pad in RING:
                pads[pad] = colors.RED_DIM.index if lit else colors.OFF.index
        else:
            for step in range(min(elapsed, len(RING))):
                pads[RING[step]] = colors.RED.index
            # The one about to fill, so the next 16th is visible before it lands.
            if elapsed < len(RING):
                pads[RING[elapsed]] = colors.RED_DIM.index
        # The length, dim, inside the ring: still the thing being recorded.
        for i in range(self.bars):
            if i not in RING_SET:
                pads[i] = colors.WHITE_DIM.index

    def render_pads(self, pads: list[int]) -> None:
        state = self.engine.rec_state
        for i in range(PAD_COUNT):
            pads[i] = colors.OFF.index
        if state == "idle":
            for i in range(self.bars):
                pads[i] = colors.WHITE.index
            return
        if state == "count_in":
            self._count_in_ring(pads)
            return
        bar = self.engine.current_bar
        for i in range(self.bars):
            if i < bar:
                pads[i] = colors.RED_DIM.index
            elif i == bar:
                pads[i] = colors.RED.index
            else:
                pads[i] = colors.WHITE.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        state = self.engine.rec_state
        if state == "idle":
            buttons[Btn.RECORD] = colors.RED_DIM.index
        else:
            buttons[Btn.RECORD] = (
                colors.RED.index if self.app.blink else colors.RED_DIM.index
            )
        buttons[Btn.STOP] = BTN_ON
        buttons[Btn.SESSION] = BTN_DIM
        if state != "idle":
            buttons[Btn.PLAY] = BTN_OFF

    def status_lines(self) -> list[str]:
        state = self.engine.rec_state
        head = f"RECORD -> slot {self.slot + 1}"
        if state == "count_in":
            if self.engine.in_pre_roll:
                return [head, "pre-roll: the song is running", "get ready..."]
            return [head, f"count-in: {self.engine.count_in_beats_left}", "playing in..."]
        if state == "recording":
            return [head, f"recording bar {self.engine.current_bar + 1}/{self.bars}", ""]
        return [
            head,
            f"length: {self.bars} bar{'s' if self.bars != 1 else ''}",
            "pad: set length    Record: go",
        ]
