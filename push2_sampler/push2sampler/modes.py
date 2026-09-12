"""The three modes of the sampler.

Sample Library
    All 64 pads are sample slots.  White = blank, green = filled.  Press a
    blank pad to record into it; press a filled pad to open its page.

Record
    The pads show the take length in bars: white = included, off = not, and the
    selection always starts at the top-left pad.  Press Record for a four-beat
    count-in followed by exactly that many bars of recording, then the take
    lands in its slot and its own page opens.

Sample
    The 64 pads are now the 64 bars of the song.  Lit pads are the bars where
    this sample plays; they may overlap freely with other samples.  Record
    re-records the take, Mute decides whether you hear this sample while
    designing the song.
"""

from __future__ import annotations

from . import colors
from .constants import PAD_COUNT, BTN_BRIGHT, BTN_DIM, BTN_OFF, BTN_ON, Btn
from .project import SONG_BARS

COUNT_IN_BEATS = 4


class Mode:
    """Base class: handles nothing, lights nothing."""

    name = "mode"

    def __init__(self, app) -> None:
        self.app = app

    @property
    def project(self):
        return self.app.project

    @property
    def engine(self):
        return self.app.engine

    # -- lifecycle ---------------------------------------------------------
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    # -- input; return True when the event has been consumed ---------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        return False

    def on_button(self, cc: int, pressed: bool) -> bool:
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        return False

    def on_engine_event(self, event: tuple) -> None:
        pass

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        pass

    def render_buttons(self, buttons: dict[int, int]) -> None:
        pass

    def status_lines(self) -> list[str]:
        return [self.name]


class LibraryMode(Mode):
    """The sample library: 64 slots, white when blank, green when filled."""

    name = "library"

    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        sample = self.project[index]
        if self.app.delete_armed:
            self.app.delete_armed = False
            if sample is not None:
                self.project.delete(index)
                self.app.rebuild_schedule()
                self.app.save_soon()
                self.app.notify(f"deleted slot {index + 1}")
            return True
        if self.app.mute_armed:
            if sample is not None:
                sample.enabled = not sample.enabled
                self.project.dirty = True
                self.app.rebuild_schedule()
                self.app.save_soon()
                self.app.notify(
                    f"slot {index + 1}: {'on' if sample.enabled else 'muted'}"
                )
            return True
        if sample is None:
            self.app.goto_record(index)
            return True
        if self.app.shift:  # audition without leaving the library
            self.engine.preview(sample.audio, sample.gain)
            return True
        self.app.goto_sample(index)
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.RECORD:
            slot = self.project.first_empty()
            if slot is None:
                self.app.notify("library full")
            else:
                self.app.goto_record(slot)
            return True
        if cc == Btn.MUTE:
            # Shortcut for shaping the mix without opening each sample page.
            self.app.mute_armed = not self.app.mute_armed
            self.app.notify(
                "mute armed: press a pad" if self.app.mute_armed else "mute off"
            )
            return True
        return False

    def render_pads(self, pads: list[int]) -> None:
        sounding = set(self.engine.sounding)
        blink = self.app.blink
        for i in range(PAD_COUNT):
            sample = self.project[i]
            if sample is None:
                pads[i] = colors.WHITE.index
            elif self.app.delete_armed:
                pads[i] = colors.RED.index if blink else colors.RED_DIM.index
            elif self.app.mute_armed:
                pads[i] = colors.YELLOW.index if sample.enabled else colors.GREEN_DIM.index
            elif i in sounding:
                pads[i] = colors.AMBER.index
            elif sample.enabled:
                pads[i] = colors.GREEN.index
            else:
                pads[i] = colors.GREEN_DIM.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.MUTE] = BTN_BRIGHT if self.app.mute_armed else BTN_DIM

    def status_lines(self) -> list[str]:
        filled = len(self.project.filled())
        muted = sum(1 for s in self.project.filled() if not s.enabled)
        return [
            "SAMPLE LIBRARY",
            f"{filled}/64 slots filled, {muted} muted",
            "blank pad: record    filled pad: open page",
        ]


class RecordMode(Mode):
    """Choose a length in bars, then record it after a four-beat count-in."""

    name = "record"

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
                self.engine.arm_record(self.bars, self.app.count_in_beats)
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
        from .constants import ENCODER_TRACK

        if cc == ENCODER_TRACK[0] and self.engine.rec_state == "idle":
            self.bars = max(1, min(SONG_BARS, self.bars + delta))
            return True
        return False

    def on_engine_event(self, event: tuple) -> None:
        if event[0] == "record_done":
            bars, audio = event[1], event[2]
            self.project.put(self.slot, audio, bars)
            self.app.rebuild_schedule()
            self.app.save_soon()
            self.app.notify(f"recorded {bars} bar(s) into slot {self.slot + 1}")
            self.app.goto_sample(self.slot)

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
            return [head, f"count-in: {self.engine.count_in_beats_left}", "playing in..."]
        if state == "recording":
            return [head, f"recording bar {self.engine.current_bar + 1}/{self.bars}", ""]
        return [
            head,
            f"length: {self.bars} bar{'s' if self.bars != 1 else ''}",
            "pad: set length    Record: go",
        ]


class SampleMode(Mode):
    """One sample's page: the 64 pads are the 64 bars of the song."""

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
            sample.triggers.clear()
            self.project.dirty = True
            self.app.rebuild_schedule()
            self.app.notify("cleared all bars")
            return True
        on = sample.toggle(index)
        self.project.dirty = True
        self.app.rebuild_schedule()
        self.app.save_soon()
        self.app.notify(f"bar {index + 1}: {'on' if on else 'off'}")
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
            sample.enabled = not sample.enabled
            self.project.dirty = True
            self.app.rebuild_schedule()
            self.app.save_soon()
            self.app.notify(f"slot {self.slot + 1}: {'on' if sample.enabled else 'muted'}")
            return True
        if cc == Btn.DELETE:
            if self.app.shift:
                self.project.delete(self.slot)
                self.app.rebuild_schedule()
                self.app.save_soon()
                self.app.notify(f"deleted slot {self.slot + 1}")
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
        from .constants import ENCODER_TRACK

        sample = self.sample
        if sample is not None and cc == ENCODER_TRACK[0]:
            sample.gain = max(0.0, min(2.0, sample.gain + delta * 0.02))
            self.project.dirty = True
            self.app.rebuild_schedule()
            self.app.notify(f"gain {sample.gain:.2f}")
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
                pads[bar] = colors.OFF.index
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
