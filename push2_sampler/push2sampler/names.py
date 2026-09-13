"""A curated word list, so a sample can be named without a keyboard.

There is no text entry on a Push 2 and there should not be: picking "kick" from
a list is two presses, where spelling it on a grid is six and feels like using a
games console to enter a high score.

Eight categories of eight words each, which is exactly one row of buttons and
seven rows of pads.
"""

from __future__ import annotations

#: Category name -> its words.  Ordered; the display-row buttons follow it.
CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("drums", ("kick", "snare", "hat", "clap", "rim", "tom", "ride", "crash")),
    ("perc", ("shaker", "conga", "bongo", "cowbell", "tamb", "click", "block", "bell")),
    ("bass", ("bass", "sub", "808", "upright", "growl", "pluck", "reese", "thump")),
    ("keys", ("chord", "pad", "organ", "piano", "rhodes", "bell", "stab", "arp")),
    ("lead", ("lead", "riff", "melody", "hook", "line", "solo", "horn", "string")),
    ("voice", ("vox", "verse", "chorus", "adlib", "chant", "breath", "shout", "harmony")),
    ("fx", ("fx", "riser", "fall", "impact", "sweep", "reverse", "glitch", "noise")),
    ("field", ("room", "rain", "street", "crowd", "tape", "vinyl", "radio", "amb")),
)

#: Words laid out for the pads: seven rows of eight, one category per press.
ROWS = 7
COLUMNS = 8


def category_names() -> tuple[str, ...]:
    return tuple(name for name, _ in CATEGORIES)


def words(category: int) -> tuple[str, ...]:
    """The words in one category, or an empty tuple for a bad index."""
    if not 0 <= category < len(CATEGORIES):
        return ()
    return CATEGORIES[category][1]


def grid_words(category: int) -> list[str | None]:
    """``ROWS x COLUMNS`` words to show at once, starting at ``category``.

    The pads show several categories together rather than one at a time: with
    eight words per category and seven rows available, showing one category
    would waste six rows and hide the obvious neighbours.
    """
    out: list[str | None] = []
    for row in range(ROWS):
        index = (category + row) % len(CATEGORIES)
        row_words = list(words(index))
        row_words += [None] * (COLUMNS - len(row_words))
        out.extend(row_words[:COLUMNS])
    return out


def word_at(category: int, pad: int) -> str | None:
    """The word a pad means, or None where there is no word."""
    grid = grid_words(category)
    return grid[pad] if 0 <= pad < len(grid) else None


def suffixed(name: str, taken) -> str:
    """``name``, or ``name 2``/``name 3`` when the plain one is already used.

    Two kicks in a library are normal, and two slots called "kick" are not
    useful, so the second one names itself.
    """
    if name not in taken:
        return name
    for n in range(2, 100):
        candidate = f"{name} {n}"
        if candidate not in taken:
            return candidate
    return name
