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
from .library import LibraryMode
from .mixer import MixerMode
from .perform import PerformMode
from .record import RecordMode
from .sample import SampleMode
from .sample_edit import SampleEditMode
from .settings import SettingsMode

__all__ = [
    "COUNT_IN_BEATS",
    "LibraryMode",
    "MixerMode",
    "Mode",
    "PerformMode",
    "RecordMode",
    "SampleEditMode",
    "SampleMode",
    "SettingsMode",
]
