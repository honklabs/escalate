"""Record mode: choose a length in bars, then record it after a count-in."""

from __future__ import annotations

from .. import analysis, colors
from ..constants import BTN_DIM, BTN_OFF, BTN_ON, ENCODER_TRACK, PAD_COUNT, Btn
from ..history import PutSample
from ..project import SONG_BARS
from .base import Mode


class RecordMode(Mode):
    name = "record"

    @property
    def title(self) -> str:
        return f"RECORD {self.bars} BAR{'S' if self.bars != 1 else ''}"

    def __init__(self, app, slot: int, bars: int = 1) -> None:
        super().__init__(app)
        self.slot = slot
        self.bars = max(1, min(SONG_BARS, bars))

    def on_enter(self) -> None:
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
        # The selection always starts at the top-left pad, so the pad that was
        # pressed is simply the last included bar.
        self.bars = index + 1
        self.app.notify(f"length: {self.bars} bar{'s' if self.bars != 1 else ''}")
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.RECORD:
            if self.engine.rec_state == "idle":
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
        if cc == ENCODER_TRACK[0] and self.engine.rec_state == "idle":
            self.bars = max(1, min(SONG_BARS, self.bars + delta))
            return True
        return False

    def on_engine_event(self, event: tuple) -> None:
        if event[0] == "record_done":
            bars, audio = event[1], event[2]
            audio, notes = self._post_process(audio)
            self.app.do(PutSample(self.slot, audio, bars))
            self.app.goto_sample(self.slot)
            # After the page change, not before: goto_sample announces the slot,
            # which would otherwise bury the news that the take was processed.
            if notes:
                self.app.notify(", ".join(notes))

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
    def render_pads(self, pads: list[int]) -> None:
        state = self.engine.rec_state
        for i in range(PAD_COUNT):
            pads[i] = colors.OFF.index
        if state == "idle":
            for i in range(self.bars):
                pads[i] = colors.WHITE.index
            return
        if state == "count_in":
            lit = self.engine.beat_phase < 0.5
            for i in range(self.bars):
                pads[i] = colors.RED.index if lit else colors.OFF.index
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
