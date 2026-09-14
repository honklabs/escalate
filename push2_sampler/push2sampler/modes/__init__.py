"""The modes of the sampler.

Sample Library
    All 64 pads are sample slots.  White = blank, green = filled.  Press a
    blank pad to record into it; press a filled pad to open its page.

Record
    The pads show the take length in bars: white = included, off = not, and the
    selection always starts at the top-left pad.  Press Record for a four-beat
    count-in followed by exactly that many bars of recording, then the take
    lands in its slot and its own page opens.

Perform
    The pads fire samples, quantised to the grid, and can write what you play
    into the arrangement as the loop goes round.

Edit
    One take's shape: trim, fades, pitch, reverse, normalise, all undoable and
    none of it touching the recording until you say so.

Mixer
    Eight slots at a time as vertical level meters, with an encoder of gain and
    a mute button per strip, plus solo and a master gain.

Browser
    The projects on disk, as pads: open, create, duplicate or delete a song
    without going back to a terminal.

Harmony
    The library grid coloured by how each slot's notes sit against one
    reference slot: green fits, amber is a neighbour, red clashes, white has no
    harmony to compare.  One button transposes a clashing loop into line.

Living
    One sample's bars plus a *variation*: extra bars it plays on only every Nth
    pass, so a short arrangement stops repeating itself.  `Shift`+`Record`
    freezes a chosen number of passes as audio.

Song
    The whole arrangement as a heat map: every bar against every slot, with a
    zoom into any eight-by-eight cell where each pad is one bar of one slot.

Sample
    The 64 pads are now the 64 bars of the song.  Lit pads are the bars where
    this sample plays; they may overlap freely with other samples.  Record
    re-records the take, Mute decides whether you hear this sample while
    designing the song.

One module per mode; :mod:`push2sampler.modes.base` holds the contract they
share.
"""

from __future__ import annotations

from .base import COUNT_IN_BEATS, Mode
from .browser import BrowserMode
from .harmony import HarmonyMode
from .library import LibraryMode
from .living import LivingMode
from .mixer import MixerMode
from .perform import PerformMode
from .record import RecordMode
from .sample import SampleMode
from .info import InfoMode
from .pattern import PatternMode
from .sample_edit import SampleEditMode
from .slice import SliceMode
from .song import SongMode
from .tag import TagMode
from .settings import SettingsMode

__all__ = [
    "COUNT_IN_BEATS",
    "BrowserMode",
    "HarmonyMode",
    "LibraryMode",
    "LivingMode",
    "MixerMode",
    "Mode",
    "PerformMode",
    "RecordMode",
    "InfoMode",
    "PatternMode",
    "SampleEditMode",
    "SliceMode",
    "SampleMode",
    "SettingsMode",
    "SongMode",
    "TagMode",
]
