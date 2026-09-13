"""The song at a glance: all 64 bars against all 64 slots, on 64 pads.

Every other page shows one sample's arrangement. This one shows the whole
thing, which is how you notice that bar 33 is bare or that the second half is
just the first half again.

It cannot be one pad per bar per slot -- that is 4096 cells on 64 pads -- so the
overview is a **heat map**: each pad is an 8-bar by 8-slot cell, coloured by how
many triggers are inside it. Pressing a cell zooms in, and then each pad really
is one bar of one slot.

    overview            zoom (one cell)
    columns = bars      columns = bars   (8 of them)
    rows    = slots     rows    = slots  (8 of them)
"""

from __future__ import annotations

from .. import colors
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    GRID_H,
    GRID_W,
    PAD_COUNT,
    Btn,
)
from ..history import SetBars, ToggleTrigger
from ..project import BANK_SLOTS, PAGE_BARS
from .base import Mode

#: Bars and slots per overview cell.
CELL_BARS = PAGE_BARS // GRID_W
CELL_SLOTS = BANK_SLOTS // GRID_H

#: Density ramp, sparse to dense.  Reuses the existing palette rather than
#: adding four colours that would mean nothing anywhere else.
DENSITY: tuple[int, ...] = (
    colors.OFF.index,
    colors.BLUE_DIM.index,
    colors.BLUE.index,
    colors.AMBER.index,
    colors.WHITE.index,
)


def density_step(count: int) -> int:
    """Which rung of the ramp a cell with ``count`` triggers sits on."""
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count <= 3:
        return 2
    if count <= 7:
        return 3
    return 4


class SongMode(Mode):
    name = "song"
    transient = True

    def __init__(self, app) -> None:
        super().__init__(app)
        #: The cell being examined, as (column, row), or None in the overview.
        self.cell: tuple[int, int] | None = None

    @property
    def zoomed(self) -> bool:
        return self.cell is not None

    # -- geometry ----------------------------------------------------------
    def cell_origin(self, column: int, row: int) -> tuple[int, int]:
        """The first bar and first slot of an overview cell."""
        bar = self.app.page * PAGE_BARS + column * CELL_BARS
        slot = self.app.bank * BANK_SLOTS + row * CELL_SLOTS
        return bar, slot

    def zoom_target(self, pad: int) -> tuple[int, int]:
        """The (bar, slot) one pad means while zoomed in."""
        column, row = pad % GRID_W, pad // GRID_W
        bar, slot = self.cell_origin(*self.cell)
        return bar + column, slot + row

    def cell_of_bar(self, bar: int) -> int | None:
        """Which overview column a bar falls in, or None if off this page."""
        pad = self.app.pad_of_bar(bar)
        return None if pad is None else pad % PAGE_BARS // CELL_BARS

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        if not self.zoomed:
            self.cell = (index % GRID_W, index // GRID_W)
            bar, slot = self.cell_origin(*self.cell)
            self.app.notify(
                f"bars {bar + 1}-{bar + CELL_BARS}, slots {slot + 1}-{slot + CELL_SLOTS}"
            )
            return True
        bar, slot = self.zoom_target(index)
        sample = self.project[slot]
        if sample is None:
            self.app.notify(f"slot {slot + 1} is empty")
            return True
        if bar >= self.project.song_bars:
            return True
        self.app.do(ToggleTrigger(slot, bar, bar not in sample.triggers))
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.CLIP:
            # One button in and back out, so the zoom is never a trap.
            if self.zoomed:
                self.cell = None
                self.app.notify("song overview")
            else:
                self.app.pop_mode()
            return True
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        if cc == Btn.DELETE and self.zoomed:
            self._clear_cell()
            return True
        if cc in (Btn.PAGE_LEFT, Btn.PAGE_RIGHT) and self.zoomed and not self.app.shift:
            # Page moves the zoom here rather than the bank: while you are
            # inside a cell, the next cell is what "next" means.
            self._step_cell(-1 if cc == Btn.PAGE_LEFT else 1)
            return True
        return False

    def _step_cell(self, step: int) -> None:
        column, row = self.cell
        flat = (row * GRID_W + column + step) % PAD_COUNT
        self.cell = (flat % GRID_W, flat // GRID_W)
        bar, slot = self.cell_origin(*self.cell)
        self.app.notify(f"bars {bar + 1}-{bar + CELL_BARS}, slots {slot + 1}-{slot + CELL_SLOTS}")

    def _clear_cell(self) -> None:
        """Wipe one cell: eight bars of eight slots, as one undo step each."""
        self.app.delete_armed = False
        bar0, slot0 = self.cell_origin(*self.cell)
        cleared = 0
        for slot in range(slot0, slot0 + CELL_SLOTS):
            sample = self.project[slot]
            if sample is None:
                continue
            changes = {
                bar: None
                for bar in range(bar0, min(bar0 + CELL_BARS, self.project.song_bars))
                if bar in sample.triggers
            }
            if changes:
                cleared += len(changes)
                self.app.do(SetBars(slot, changes, f"cleared slot {slot + 1} here"))
        self.app.notify(
            f"cleared {cleared} trigger(s)" if cleared else "nothing here to clear"
        )

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        if self.zoomed:
            self._render_zoom(pads)
        else:
            self._render_overview(pads)

    def _render_overview(self, pads: list[int]) -> None:
        counts = self._cell_counts()
        playing = self.cell_of_bar(self.engine.current_bar) if self.engine.is_playing else None
        for row in range(GRID_H):
            for column in range(GRID_W):
                step = density_step(counts[row][column])
                if column == playing:
                    # Brighten the whole column rather than drawing a separate
                    # playhead, so the density stays readable underneath it.
                    step = min(len(DENSITY) - 1, step + 1)
                pads[row * GRID_W + column] = DENSITY[step]

    def _cell_counts(self) -> list[list[int]]:
        counts = [[0] * GRID_W for _ in range(GRID_H)]
        bank_start = self.app.bank * BANK_SLOTS
        page_start = self.app.page * PAGE_BARS
        for sample in self.project.filled():
            row = (sample.slot - bank_start) // CELL_SLOTS
            if not 0 <= row < GRID_H or sample.slot < bank_start:
                continue
            for bar in sample.triggers:
                column = (bar - page_start) // CELL_BARS
                if 0 <= column < GRID_W and bar >= page_start:
                    counts[row][column] += 1
        return counts

    def _render_zoom(self, pads: list[int]) -> None:
        bar0, slot0 = self.cell_origin(*self.cell)
        playhead = self.engine.current_bar if self.engine.is_playing else -1
        for row in range(GRID_H):
            slot = slot0 + row
            sample = self.project[slot] if slot < len(self.project.slots) else None
            for column in range(GRID_W):
                bar = bar0 + column
                pad = row * GRID_W + column
                if sample is None:
                    pads[pad] = colors.OFF.index
                elif bar in sample.triggers:
                    pads[pad] = (
                        colors.WHITE.index if bar == playhead
                        else colors.slot_color(sample.color)
                    )
                elif bar == playhead:
                    pads[pad] = colors.WHITE_DIM.index
                else:
                    pads[pad] = colors.AMBER_DIM.index if row % 2 else colors.OFF.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.CLIP] = BTN_BRIGHT if self.zoomed else BTN_ON
        buttons[Btn.SESSION] = BTN_ON
        if self.zoomed:
            buttons[Btn.PAGE_LEFT] = buttons[Btn.PAGE_RIGHT] = BTN_DIM
            buttons[Btn.DELETE] = BTN_DIM

    def status_lines(self) -> list[str]:
        page, bank = self.app.page_letter, self.app.bank_letter
        if not self.zoomed:
            counts = self._cell_counts()
            total = sum(sum(row) for row in counts)
            busiest = max((max(row) for row in counts), default=0)
            return [
                f"SONG  page {page}  bank {bank}  {total} trigger(s)",
                f"each pad = {CELL_BARS} bars x {CELL_SLOTS} slots, "
                f"busiest {busiest}",
                "press a pad to zoom in   Clip: back to the library",
                "columns are bars, rows are slots",
            ]
        bar, slot = self.cell_origin(*self.cell)
        return [
            f"SONG ZOOM  bars {bar + 1}-{bar + CELL_BARS}  "
            f"slots {slot + 1}-{slot + CELL_SLOTS}",
            "each pad toggles one slot on one bar",
            "Page left/right: next cell   Delete: clear this cell",
            "Clip: back to the overview   Session: leave",
        ]
