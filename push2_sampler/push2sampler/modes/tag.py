"""Naming and colouring a slot, with no keyboard involved.

`Select` on a sample page opens this. The top seven rows are words to pick from
and the bottom row is the eight colours, so a slot gets both its identity and
its place in the library's colour scheme from one page.

Sixty-four slots of `S01`, `S02`, `S03` are unreadable; `kick`, `snare` and a
colour are how you find a take a week later.
"""

from __future__ import annotations

from .. import colors, names
from ..constants import BTN_BRIGHT, BTN_DIM, BTN_ON, DISPLAY_ROW_BOTTOM, GRID_W, Btn
from ..history import SetColor, SetName
from .base import Mode

#: The bottom row of pads is the colour picker; the rest are words.
COLOR_ROW = names.ROWS


class TagMode(Mode):
    name = "tag"

    @property
    def title(self) -> str:
        return f"NAME SLOT {self.slot + 1}"
    transient = True

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        #: Which category the word rows start from.
        self.category = 0

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        sample = self.sample
        if sample is None:
            self.app.pop_mode()
            return
        self.app.notify(f"naming slot {self.slot + 1}: {sample.name}")

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed or self.sample is None:
            return True
        row, column = index // GRID_W, index % GRID_W
        if row == COLOR_ROW:
            self._pick_color(column)
            return True
        word = names.word_at(self.category, index)
        if word is not None:
            self._pick_name(word)
        return True

    def _pick_name(self, word: str) -> None:
        taken = {s.name for s in self.project.filled() if s.slot != self.slot}
        self.app.do(SetName(self.slot, names.suffixed(word, taken), self.sample.name))

    def _pick_color(self, tag: int) -> None:
        sample = self.sample
        # Pressing the colour a slot already has clears it back to the default,
        # so the picker is a toggle rather than a one-way door.
        wanted = None if sample.color == tag else tag
        self.app.do(SetColor(self.slot, wanted, sample.color))

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc in (Btn.SELECT, Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        if cc in DISPLAY_ROW_BOTTOM:
            self.category = DISPLAY_ROW_BOTTOM.index(cc) % len(names.CATEGORIES)
            self.app.notify(f"{names.category_names()[self.category]}...")
            return True
        if cc in (Btn.UP, Btn.DOWN):
            step = -1 if cc == Btn.UP else 1
            self.category = (self.category + step) % len(names.CATEGORIES)
            return True
        return False

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        grid = names.grid_words(self.category)
        for index, word in enumerate(grid):
            pads[index] = colors.WHITE_DIM.index if word else colors.OFF.index
        sample = self.sample
        for column in range(GRID_W):
            pad = COLOR_ROW * GRID_W + column
            chosen = sample is not None and sample.color == column
            if column == 0:
                # The first swatch is "no colour", which is the default green.
                chosen = sample is not None and sample.color is None
            pads[pad] = colors.USER_COLORS[column].index
            if not chosen:
                continue
            # Mark the current choice by flashing it, since the swatch itself
            # already uses its own colour to say what it is.
            pads[pad] = (
                colors.USER_COLORS[column].index if self.app.blink
                else colors.WHITE.index
            )

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.SELECT] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.UP] = buttons[Btn.DOWN] = BTN_DIM
        for index, cc in enumerate(DISPLAY_ROW_BOTTOM):
            if index >= len(names.CATEGORIES):
                buttons[cc] = 0
            else:
                buttons[cc] = BTN_BRIGHT if index == self.category else BTN_DIM

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["TAG"]
        shown = [
            names.category_names()[(self.category + row) % len(names.CATEGORIES)]
            for row in range(names.ROWS)
        ]
        return [
            f"NAME slot {self.slot + 1}: {sample.name}",
            "rows: " + " ".join(shown[:4]),
            "      " + " ".join(shown[4:]),
            "bottom row of pads: colour   buttons below: jump to a category",
        ]
