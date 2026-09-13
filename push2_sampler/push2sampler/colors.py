"""Pad colours.

Push 2 pads are addressed by *palette index*, not by RGB value: a note-on
whose velocity is ``n`` lights the pad in palette entry ``n``.  The factory
palette is undocumented and has shifted between firmware versions, so rather
than guessing indices we reprogram a private block of the palette (entries 64
and up) with exactly the colours this program needs -- see
:meth:`push2sampler.push2.Push2.program_palette`.

Index 0 is left alone: on every Push 2 firmware it means "off".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Color:
    name: str
    index: int
    rgb: tuple[int, int, int]

    def __int__(self) -> int:  # lets colours be passed straight to set_pad()
        return self.index


OFF = Color("off", 0, (0, 0, 0))

# Private palette block.  Keep these indices stable: they are uploaded to the
# device at startup and also used by the simulator to draw its text grid.
WHITE = Color("white", 64, (255, 255, 255))
WHITE_DIM = Color("white_dim", 65, (36, 36, 36))
WHITE_MID = Color("white_mid", 75, (96, 96, 96))
GREEN = Color("green", 66, (0, 255, 60))
GREEN_MID = Color("green_mid", 76, (0, 120, 30))
GREEN_DIM = Color("green_dim", 67, (0, 48, 14))
AMBER = Color("amber", 68, (255, 130, 0))
AMBER_DIM = Color("amber_dim", 69, (48, 24, 0))
RED = Color("red", 70, (255, 0, 0))
RED_DIM = Color("red_dim", 71, (56, 0, 0))
BLUE = Color("blue", 72, (0, 90, 255))
BLUE_DIM = Color("blue_dim", 73, (0, 16, 56))
YELLOW = Color("yellow", 74, (255, 214, 0))

#: Eight colours a slot can be tagged with, so a full library is readable at a
#: glance (CC-18).  Index 0 is the default green every untagged slot already
#: used, so tagging is additive: nothing changes appearance until you ask.
USER_COLORS: tuple[Color, ...] = (
    GREEN,
    Color("user_cyan", 77, (0, 210, 200)),
    Color("user_blue", 78, (40, 90, 255)),
    Color("user_violet", 79, (150, 60, 255)),
    Color("user_magenta", 80, (255, 40, 160)),
    Color("user_red", 81, (255, 40, 40)),
    Color("user_orange", 82, (255, 120, 0)),
    Color("user_lime", 83, (170, 255, 0)),
)


def slot_color(tag: int | None) -> int:
    """Palette index for a slot's user colour tag, defaulting to green."""
    if tag is None or not 0 <= tag < len(USER_COLORS):
        return GREEN.index
    return USER_COLORS[tag].index

#: Every colour that must be uploaded to the device.
PALETTE: tuple[Color, ...] = (
    WHITE,
    WHITE_DIM,
    WHITE_MID,
    GREEN,
    GREEN_MID,
    GREEN_DIM,
    AMBER,
    AMBER_DIM,
    RED,
    RED_DIM,
    BLUE,
    BLUE_DIM,
    YELLOW,
    *USER_COLORS[1:],  # USER_COLORS[0] is GREEN, already above
)

BY_INDEX = {c.index: c for c in (OFF,) + PALETTE}

#: Single letters used by the terminal simulator to draw the pad grid.
SIM_GLYPHS = {
    OFF.index: ".",
    WHITE.index: "W",
    WHITE_MID.index: "m",
    WHITE_DIM.index: "w",
    GREEN.index: "G",
    GREEN_MID.index: "h",
    GREEN_DIM.index: "g",
    AMBER.index: "A",
    AMBER_DIM.index: "a",
    RED.index: "R",
    RED_DIM.index: "r",
    BLUE.index: "B",
    BLUE_DIM.index: "b",
    YELLOW.index: "Y",
    # The user colours share one glyph: the simulator's grid is about state, and
    # eight more letters would make it less readable rather than more.
    **{c.index: "C" for c in USER_COLORS[1:]},
}
