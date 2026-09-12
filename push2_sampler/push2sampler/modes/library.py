"""The sample library: 64 slots, white when blank, green when filled."""

from __future__ import annotations

import time

from .. import colors
from ..constants import BTN_BRIGHT, BTN_DIM, BTN_ON, PAD_COUNT, Btn
from ..history import CopySlot, DeleteSample, SetEnabled
from .base import Mode

#: Hold a filled pad for this long to audition it instead of opening its page.
HOLD_PREVIEW_S = 0.4


class LibraryMode(Mode):
    name = "library"

    def __init__(self, app) -> None:
        super().__init__(app)
        self._held_slot: int | None = None
        self._held_since = 0.0
        self._auditioned = False

    def on_exit(self) -> None:
        self._clear_hold()

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        sample = self.project[index]
        if not pressed:
            return self._on_release(index, sample)

        if self.app.delete_armed:
            self.app.delete_armed = False
            if sample is not None:
                self.app.do(DeleteSample(index))
            return True
        if self.app.mute_armed:
            if sample is not None:
                self.app.do(SetEnabled(index, not sample.enabled))
            return True
        if self.app.duplicate_armed:
            self.app.duplicate_armed = False
            self._duplicate(index, sample)
            return True
        if sample is None:
            self.app.goto_record(index)
            return True
        if self.app.shift:  # audition without leaving the library
            self._audition(index, sample)
            return True
        # A filled pad commits on release: a short press opens its page, a long
        # press auditions it instead (see on_tick).
        self._held_slot = index
        self._held_since = time.monotonic()
        self._auditioned = False
        return True

    def _on_release(self, index: int, sample) -> bool:
        if self._held_slot != index:
            return True
        auditioned = self._auditioned
        self._clear_hold()
        if not auditioned and sample is not None:
            self.app.goto_sample(index)
        return True

    def on_tick(self) -> None:
        if self._held_slot is None or self._auditioned:
            return
        if time.monotonic() - self._held_since < HOLD_PREVIEW_S:
            return
        sample = self.project[self._held_slot]
        if sample is None:  # deleted from under us
            self._clear_hold()
            return
        self._auditioned = True
        self._audition(self._held_slot, sample)

    def _audition(self, index: int, sample) -> None:
        self.engine.preview(sample.audio, sample.gain, slot=index)
        self.app.notify(f"auditioning slot {index + 1}")

    def _clear_hold(self) -> None:
        self._held_slot = None
        self._auditioned = False

    def _duplicate(self, index: int, sample) -> None:
        """Copy (or with Shift, move) a slot to the next empty one."""
        if sample is None:
            self.app.notify("nothing in that slot to duplicate")
            return
        destination = self.project.next_empty(index)
        if destination is None:
            self.app.notify("no empty slot to duplicate into")
            return
        self.app.do(CopySlot(index, destination, move=self.app.shift))

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.RECORD and self.app.shift:
            self.app.start_bounce()
            return True
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
        if cc == Btn.DUPLICATE:
            self.app.duplicate_armed = not self.app.duplicate_armed
            self.app.delete_armed = self.app.mute_armed = False
            self.app.notify(
                "duplicate armed: press a slot (Shift to move)"
                if self.app.duplicate_armed else "duplicate off"
            )
            return True
        return False

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        if self.app.bounce is not None:
            self._render_progress(pads, self.app.bounce.progress)
            return
        sounding = set(self.engine.sounding)
        upcoming = self._next_bar_slots()
        blink = self.app.blink
        for i in range(PAD_COUNT):
            sample = self.project[i]
            if sample is None:
                pads[i] = colors.WHITE.index
            elif self.app.delete_armed:
                pads[i] = colors.RED.index if blink else colors.RED_DIM.index
            elif self.app.mute_armed:
                pads[i] = colors.YELLOW.index if sample.enabled else colors.GREEN_DIM.index
            elif self.app.duplicate_armed:
                pads[i] = colors.BLUE.index if blink else colors.BLUE_DIM.index
            elif i in sounding:
                pads[i] = colors.AMBER.index
            elif i in upcoming:
                pads[i] = colors.AMBER_DIM.index  # comes in on the next bar
            elif self.project.mismatched(sample):
                pads[i] = colors.YELLOW.index  # does not fill its bars any more
            elif sample.enabled:
                pads[i] = colors.GREEN.index
            else:
                pads[i] = colors.GREEN_DIM.index

    def _next_bar_slots(self) -> set[int]:
        """Slots that will come in on the next bar, so you can see what is next."""
        if not self.engine.is_playing:
            return set()
        bar = self.engine.current_bar
        if bar < 0:
            return set()
        nxt = bar + 1
        if nxt >= self.project.song_bars:
            if not self.engine.loop:
                return set()  # there is no next bar; the song ends here
            nxt = 0
        return self.project.slots_at_bar(nxt)

    @staticmethod
    def _render_progress(pads: list[int], progress: float) -> None:
        """The whole grid becomes one bar filling up while a bounce renders."""
        filled = int(progress * PAD_COUNT + 0.5)
        for i in range(PAD_COUNT):
            pads[i] = colors.AMBER.index if i < filled else colors.AMBER_DIM.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.MUTE] = BTN_BRIGHT if self.app.mute_armed else BTN_DIM
        buttons[Btn.DUPLICATE] = BTN_BRIGHT if self.app.duplicate_armed else BTN_DIM

    def status_lines(self) -> list[str]:
        filled = len(self.project.filled())
        muted = sum(1 for s in self.project.filled() if not s.enabled)
        if self.app.duplicate_armed:
            return [
                "DUPLICATE",
                "press a filled slot: it is copied to the next empty one",
                "Shift + a slot moves it instead of copying",
                "Duplicate again to cancel",
            ]
        lines = [
            "SAMPLE LIBRARY",
            f"{filled}/64 slots filled, {muted} muted",
            "blank pad: record   tap: open page   hold: audition",
            "Shift+Record: bounce   Duplicate: copy a slot",
        ]
        if self.app.bounce is not None:
            return ["BOUNCING", f"{self.app.bounce.progress * 100:.0f}%",
                    "rendering the song to a file"]
        off_grid = self.project.mismatched_slots()
        if off_grid:
            slots = ", ".join(str(slot + 1) for slot in off_grid[:6])
            lines.append(f"yellow: off the grid (slot {slots}) - open to fix")
        return lines
