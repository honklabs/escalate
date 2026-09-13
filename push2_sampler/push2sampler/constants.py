"""Ableton Push 2 hardware constants and grid geometry.

The Push 2 exposes two MIDI ports over USB: the *Live port* (used by Ableton
Live) and the *User port*, which is the one third-party applications should
talk to.  Everything in this module describes the User-port protocol.

Grid geometry
-------------
The 8x8 pad grid sends notes 36..99.  Note 36 is the **bottom-left** pad and
notes increase left-to-right, then upwards.  Throughout this program we prefer
a "reading order" *pad index*: index 0 is the **top-left** pad, index 7 the
top-right, index 63 the bottom-right.  That matches how the layout was
described ("must start at top left pad"), and makes a pad index map directly
onto a bar number or a sample slot number.
"""

from __future__ import annotations

GRID_W = 8
GRID_H = 8
PAD_COUNT = GRID_W * GRID_H

#: MIDI note of the bottom-left pad.
PAD_NOTE_LOW = 36
#: MIDI note of the top-right pad.
PAD_NOTE_HIGH = PAD_NOTE_LOW + PAD_COUNT - 1

USB_VENDOR_ID = 0x2982
USB_PRODUCT_ID = 0x1967

#: Manufacturer/device prefix for every Push 2 SysEx message (after F0).
SYSEX_PREFIX = (0x00, 0x21, 0x1D, 0x01, 0x01)
SYSEX_SET_PALETTE_ENTRY = 0x03
SYSEX_REAPPLY_PALETTE = 0x05


# --------------------------------------------------------------------------
# Buttons (control change numbers)
# --------------------------------------------------------------------------
class Btn:
    """Control-change numbers of the Push 2 buttons we use."""

    TAP_TEMPO = 3
    METRONOME = 9
    MASTER = 28
    STOP = 29
    SETUP = 30
    LAYOUT = 31
    CONVERT = 35
    SELECT = 48
    SHIFT = 49
    NOTE = 50
    SESSION = 51
    ADD_TRACK = 53
    OCTAVE_DOWN = 54
    OCTAVE_UP = 55
    REPEAT = 56
    ACCENT = 57
    SCALE = 58
    USER = 59
    MUTE = 60
    SOLO = 61
    PAGE_LEFT = 62
    PAGE_RIGHT = 63
    LEFT = 44
    RIGHT = 45
    UP = 46
    DOWN = 47
    PLAY = 85
    RECORD = 86
    NEW = 87
    DUPLICATE = 88
    AUTOMATE = 89
    FIXED_LENGTH = 90
    DEVICE = 110
    BROWSE = 111
    MIX = 112
    CLIP = 113
    DELETE = 118
    UNDO = 119


#: The eight buttons above the display, left to right.
DISPLAY_ROW_TOP = tuple(range(102, 110))
#: The eight buttons below the display, left to right.
DISPLAY_ROW_BOTTOM = tuple(range(20, 28))

# --------------------------------------------------------------------------
# How a sample behaves when it is triggered (NF-02)
# --------------------------------------------------------------------------
#: Play to the end of the recording, whatever else happens.  The original
#: behaviour, and still the right one for a drum hit or a full-bar loop.
ONE_SHOT = "one_shot"
#: Repeat until a bar where this sample is *not* triggered, then release.
#: Lets one take hold a section without a trigger on every bar.
LOOP = "loop"
#: Stop at the end of the bar it started in, however long the audio is.
#: What a 4-bar pad needs when the next chord arrives.
GATE = "gate"
#: A new trigger cuts the previous voice of the same slot instead of layering.
RETRIGGER = "retrigger"

PLAY_MODES: tuple[str, ...] = (ONE_SHOT, LOOP, GATE, RETRIGGER)

#: Short labels for the display, in ``PLAY_MODES`` order.
PLAY_MODE_LABELS: dict[str, str] = {
    ONE_SHOT: "one shot",
    LOOP: "loop",
    GATE: "gate",
    RETRIGGER: "retrig",
}

#: Choke groups a sample can belong to: 1-8, or None for "chokes nothing".
#: Samples sharing a group cut each other, the way a closed hat cuts an open one.
CHOKE_GROUPS = 8

#: Every button LED this program can light.
#:
#: Used to blank the surface on startup and after a diagnostic.  ``clear()``
#: only knows about buttons it has lit itself, which is nothing at all in a
#: fresh process -- so a run that crashed, or a probe that lit things and
#: exited, would leave LEDs on with no way to reach them.
ALL_BUTTON_CCS: tuple[int, ...] = tuple(sorted(
    {value for name, value in vars(Btn).items()
     if not name.startswith("_") and isinstance(value, int)}
    | set(DISPLAY_ROW_TOP) | set(DISPLAY_ROW_BOTTOM)
))

#: Relative encoders.  Value 1..63 is clockwise, 127..65 counter-clockwise.
ENCODER_TEMPO = 14
ENCODER_SWING = 15
ENCODER_TRACK = tuple(range(71, 79))
ENCODER_MASTER = 79
ENCODER_CCS = frozenset((ENCODER_TEMPO, ENCODER_SWING, ENCODER_MASTER)) | frozenset(ENCODER_TRACK)

#: Touching (not turning) an encoder sends note on/off in this range; ignored.
ENCODER_TOUCH_NOTES = frozenset(range(0, 12))

#: Brightness values for the monochrome (white) buttons.
BTN_OFF = 0
BTN_DIM = 12
BTN_ON = 60
BTN_BRIGHT = 127


# --------------------------------------------------------------------------
# Grid helpers
# --------------------------------------------------------------------------
def index_to_xy(index: int) -> tuple[int, int]:
    """Return ``(col, row)`` for a pad index, row 0 being the **top** row."""
    _check_index(index)
    return index % GRID_W, index // GRID_W


def xy_to_index(col: int, row: int) -> int:
    """Inverse of :func:`index_to_xy` (row 0 is the top row)."""
    if not 0 <= col < GRID_W or not 0 <= row < GRID_H:
        raise ValueError(f"pad coordinates out of range: {(col, row)}")
    return row * GRID_W + col


def index_to_note(index: int) -> int:
    """Map a reading-order pad index to its Push 2 MIDI note."""
    col, row = index_to_xy(index)
    return PAD_NOTE_LOW + (GRID_H - 1 - row) * GRID_W + col


def note_to_index(note: int) -> int:
    """Map a Push 2 pad note to its reading-order pad index.

    Raises :class:`ValueError` for notes outside the pad grid.
    """
    if not PAD_NOTE_LOW <= note <= PAD_NOTE_HIGH:
        raise ValueError(f"note {note} is not a grid pad")
    row_from_bottom, col = divmod(note - PAD_NOTE_LOW, GRID_W)
    return xy_to_index(col, GRID_H - 1 - row_from_bottom)


def is_pad_note(note: int) -> bool:
    return PAD_NOTE_LOW <= note <= PAD_NOTE_HIGH


def encoder_delta(value: int) -> int:
    """Decode a relative-encoder CC value into a signed step count."""
    return value if value < 64 else value - 128


def _check_index(index: int) -> None:
    if not 0 <= index < PAD_COUNT:
        raise ValueError(f"pad index out of range: {index}")
