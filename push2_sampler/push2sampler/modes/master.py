"""NF-12: master playback mode — the song, watched from the samples' side.

Every other page is for editing. The library shows what exists, a sample page
shows where one take plays, the song page shows the arrangement as a heat map.
None of them is the view you want while the whole thing runs and you are
listening: for that you had to pick one sample's page and watch a single row of
the truth.

This is the library grid, all 64 slots where they always are, and **each pad
flashes as its sample fires**. One glance says what is sounding, what is idle
through this section, and how busy the bar you are in actually is.

Two things decide whether it works, and both are about the flash.

**It marks the attack, not the duration.** ``Engine.sounding`` is true for as
long as a voice lives, so a four-bar pad would hold its pad lit for four bars
and tell you nothing. The engine publishes a separate ``fired`` set — slots
that *started* a voice in the last block — and that is what this reads.

**It decays over about a fifth of a second.** Long enough to catch out of the
corner of an eye, short enough that eighth notes stay separate. The plan wanted
this driven off ``App.blink`` so the whole surface runs on one heartbeat, but
blink is a 2 Hz square wave and cannot express three steps inside 180 ms, so
the timing is kept here instead. It is still no new machinery: a dict of
timestamps read on the render pass, no timer and no thread.

Nothing destructive is reachable from here. Delete, Mute and Duplicate are
deliberately not armed: this is the one page where you are listening rather
than deciding, and a stray press should cost nothing.
"""

from __future__ import annotations

import time

from .. import colors
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    PAD_COUNT,
    Btn,
)
from .base import Mode

#: How long a pad stays lit after its sample fires, in seconds.
#:
#: Three steps across this: white, then mid white, then back to the slot's own
#: colour.  At 120 BPM an eighth note is 250 ms, so a flash this long reads as
#: one hit per note rather than smearing into the next.  Whether it reads as a
#: flash or a flicker is a thing to judge with eyes on a real device -- expect
#: to change this number once, which is why it is a constant.
FLASH_S = 0.18

#: Fraction of the flash spent at full brightness before stepping down.
FLASH_PEAK = 0.45


class MasterMode(Mode):
    name = "master"

    def __init__(self, app) -> None:
        super().__init__(app)
        #: slot -> when it last fired.  Bounded by the slot count, not by time.
        self._hits: dict[int, float] = {}
        #: Slots that have fired in the bar being played, and which bar that is.
        self._bar_slots: set[int] = set()
        self._bar = -1

    @property
    def title(self) -> str:
        return "MASTER PLAY"

    def on_enter(self) -> None:
        self.app.notify("master playback - the grid flashes as samples fire")

    # -- state -------------------------------------------------------------
    def on_tick(self) -> None:
        now = time.monotonic()
        fired = self.engine.fired
        if fired:
            for slot in fired:
                self._hits[slot] = now
        bar = self.engine.current_bar
        if bar != self._bar:
            self._bar = bar
            self._bar_slots = set()
        if fired:
            self._bar_slots.update(fired)
        # Drop stale entries so the dict cannot grow past what is flashing.
        if self._hits:
            self._hits = {s: at for s, at in self._hits.items() if now - at < FLASH_S}

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        slot = self.app.slot_at(index)
        sample = self.project[slot]
        if sample is None:
            return True
        # Audition, the library's own gesture -- not "open this slot's page",
        # because leaving this view is what Session is for.
        self.engine.preview(sample.audio, sample.gain, slot=slot)
        self.app.notify(f"auditioning slot {slot + 1} {sample.name}")
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.goto_library()
            return True
        # Delete, Mute and Duplicate are left unhandled on purpose, so the app
        # cannot arm anything destructive while this page is open.
        if cc in (Btn.DELETE, Btn.MUTE, Btn.DUPLICATE):
            self.app.notify("not from master playback - Session to go back")
            return True
        return False

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        now = time.monotonic()
        for index in range(PAD_COUNT):
            slot = self.app.slot_at(index)
            sample = self.project[slot]
            if sample is None:
                pads[index] = colors.OFF.index
                continue
            resting = (
                colors.slot_color(sample.color) if sample.enabled
                else colors.GREEN_DIM.index
            )
            hit = self._hits.get(slot)
            if hit is None or not sample.enabled:
                pads[index] = resting
                continue
            age = now - hit
            if age < FLASH_S * FLASH_PEAK:
                # White rather than a brighter version of the slot's colour:
                # the palette has brightness steps for white and green only,
                # and eight user colours with no dim variants, so white is the
                # one flash that reads the same against every resting colour.
                pads[index] = colors.WHITE.index
            elif age < FLASH_S:
                pads[index] = colors.WHITE_MID.index
            else:
                pads[index] = resting

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.PLAY] = BTN_BRIGHT if self.engine.is_playing else BTN_DIM
        buttons[Btn.STOP] = BTN_DIM

    def status_lines(self) -> list[str]:
        bar = self.engine.current_bar
        where = f"bar {bar + 1}" if bar >= 0 else "stopped"
        filled = len(self.project.filled())
        lines = [
            f"MASTER PLAYBACK   bank {self.app.bank_letter}   {where}",
            f"{filled} sample(s) loaded   loop {self.app.loop_label}",
        ]
        if self.engine.is_playing:
            # How many slots fired this bar: a number that says whether a
            # section is as busy as it feels.
            lines.append(
                f"{len(self._bar_slots)} fired this bar   "
                f"{len(self.engine.sounding)} sounding now"
            )
        else:
            lines.append("Play to watch it   pad: audition   Session: back")
        return lines
