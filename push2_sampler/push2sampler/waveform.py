"""Drawing a take: as 64 pads, and as one line of text.

Both shapes answer "what does this audio look like" for a page that has no
picture to show -- the pad grid is the only graphic this instrument has, and the
text line is what the terminal simulator and the colour display get.

Extracted because `sample_edit` and `slice` had each grown their own identical
copy, and `trim` (`IN-09`) would have been the third.  Two copies of a function
are a coincidence; three are a bug waiting to be fixed in only two of them.
"""

from __future__ import annotations

import numpy as np

#: Characters for a text waveform, quietest first.
RAMP = " .:-=+*#"


def envelope(audio: np.ndarray, buckets: int) -> list[float]:
    """Peak amplitude per equal slice of ``audio``, as ``buckets`` values.

    Peak rather than RMS because this is drawn at eight brightnesses on a pad:
    RMS would make a sharp transient look like nothing, and a transient is the
    thing a person is usually looking for.
    """
    if buckets <= 0:
        return []
    if audio is None or audio.shape[0] == 0:
        return [0.0] * buckets
    mono = np.abs(audio).max(axis=1)
    edges = np.linspace(0, mono.shape[0], buckets + 1).astype(int)
    return [
        float(mono[a:b].max()) if b > a else 0.0
        for a, b in zip(edges[:-1], edges[1:])
    ]


def text_wave(audio: np.ndarray, seconds: float, width: int = 44) -> str:
    """``audio`` as one line, with its length on the end."""
    levels = envelope(audio, width)
    body = "".join(RAMP[min(len(RAMP) - 1, int(level * len(RAMP)))] for level in levels)
    return f"[{body}] {seconds:.2f}s"


def wave_line(sample, project, width: int = 44) -> str:
    """The take a sample will actually play, as one line of text."""
    audio = sample.effective_audio(project.samplerate)
    seconds = sample.frames / max(1, project.samplerate)
    return text_wave(audio, seconds, width)
