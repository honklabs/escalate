"""Looking at a take: where it really starts, and how loud it is.

Used by the optional post-take processing (see ``auto_trim`` / ``auto_normalize``
/ ``auto_fade`` in :mod:`push2sampler.settings`).  Kept apart from the recorder
so the arithmetic can be tested on buffers rather than through a transport.
"""

from __future__ import annotations

import numpy as np

#: Window used to measure the noise floor at the very start of a take.
FLOOR_WINDOW_MS = 10.0
#: A transient must exceed the floor by this much to count as the start.
FLOOR_RATIO = 4.0
#: ...and must reach at least this absolute level, so that a take of pure
#: silence is not "detected" as starting wherever the dither happened to peak.
MIN_ONSET = 0.01
#: How far into a take auto-trim will look.  Beyond this it is not late timing,
#: it is a rest, and shifting it would move the music rather than fix it.
MAX_SHIFT_MS = 100.0
#: Normalise to this peak: -1 dBFS, leaving room for summing.
TARGET_PEAK = 0.891


def peak(buf) -> float:
    """Largest absolute sample, or 0.0 for an empty buffer."""
    array = np.asarray(buf)
    return float(np.max(np.abs(array))) if array.size else 0.0


def first_transient(buf, samplerate: int, max_shift_ms: float = MAX_SHIFT_MS) -> int:
    """Frame where the take audibly begins, or 0 if it already does.

    The threshold is relative to the take's own first few milliseconds, because
    "silence" means something different on a condenser mic in a live room than
    on a direct input.  Returns 0 rather than guessing when nothing in range
    stands out -- doing nothing is always the safe answer here.
    """
    array = np.asarray(buf, dtype=np.float32)
    if array.size == 0:
        return 0
    mono = array.mean(axis=1) if array.ndim > 1 else array
    limit = min(mono.shape[0], int(samplerate * max_shift_ms / 1000.0))
    if limit <= 1:
        return 0
    floor_frames = max(1, min(limit, int(samplerate * FLOOR_WINDOW_MS / 1000.0)))
    floor = float(np.max(np.abs(mono[:floor_frames])))
    threshold = max(MIN_ONSET, floor * FLOOR_RATIO)
    above = np.flatnonzero(np.abs(mono[:limit]) >= threshold)
    return int(above[0]) if above.size else 0


def shift_left(buf, frames: int) -> np.ndarray:
    """Drop ``frames`` from the front, padding the end to keep the length.

    Length is preserved deliberately: a take is an exact number of bars at the
    tempo it was recorded at (see ``F-09``), and returning something shorter
    would immediately flag the slot as off the grid.
    """
    array = np.asarray(buf, dtype=np.float32)
    if frames <= 0 or array.size == 0:
        return array
    frames = min(frames, array.shape[0])
    shifted = np.zeros_like(array)
    keep = array.shape[0] - frames
    if keep > 0:
        shifted[:keep] = array[frames:]
    return shifted


def normalize(buf, target: float = TARGET_PEAK) -> np.ndarray:
    """Scale so the loudest sample sits at ``target``.  Silence is untouched."""
    array = np.asarray(buf, dtype=np.float32)
    current = peak(array)
    if current <= 0.0:
        return array
    return np.asarray(array * (target / current), dtype=np.float32)


def fade_edges(buf, samplerate: int, ms: float = 2.0) -> np.ndarray:
    """Raised-cosine fade at both ends, so a looped take does not click."""
    array = np.array(buf, dtype=np.float32, copy=True)
    frames = int(samplerate * ms / 1000.0)
    if frames <= 0 or array.shape[0] < frames * 2:
        return array
    phase = np.pi * np.arange(frames, dtype=np.float32) / frames
    rise = (0.5 - 0.5 * np.cos(phase)).astype(np.float32)
    shape = (frames, 1) if array.ndim > 1 else (frames,)
    array[:frames] *= rise.reshape(shape)
    array[-frames:] *= rise[::-1].reshape(shape)
    return array


def process_take(buf, samplerate: int, trim: bool = False, normalise: bool = False,
                 fade: bool = False) -> tuple[np.ndarray, list[str]]:
    """Apply whichever post-take options are on.  Returns the audio and notes.

    The notes are what the display says afterwards: processing a take silently
    would leave you wondering why it does not sound like what you played.
    """
    audio = np.asarray(buf, dtype=np.float32)
    notes: list[str] = []
    if trim:
        offset = first_transient(audio, samplerate)
        if offset > 0:
            audio = shift_left(audio, offset)
            notes.append(f"trimmed {offset / samplerate * 1000:.0f}ms")
    if normalise:
        before = peak(audio)
        audio = normalize(audio)
        if before > 0:
            notes.append(f"normalised x{TARGET_PEAK / before:.2f}")
    if fade:
        audio = fade_edges(audio, samplerate)
        notes.append("faded")
    return audio, notes
