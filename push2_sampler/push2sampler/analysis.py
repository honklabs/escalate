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


# ==========================================================================
# Where the hits are (IN-01)
# ==========================================================================
# `onsets` is used by the slice page to cut a take at its transients.  Numpy
# only -- no scipy, no librosa -- because everything else here runs on numpy
# and an instrument that needs a scientific stack to slice a drum loop is not
# an instrument.
#
# How it works:
#   1. Spectral flux: a short-time magnitude spectrum, and per frame the sum of
#      the energy that *appeared* since the last one.  A struck note adds energy
#      across many bins at once, which is what makes this cheap and reliable on
#      percussive material.
#   2. An adaptive threshold: a peak must clear its own neighbourhood's median
#      plus a multiple of that neighbourhood's spread, because a mix gets louder
#      and quieter and a fixed threshold would follow it around.
#   3. A structure gate, a sharpness test and a minimum gap -- each of which
#      exists because of a specific way the first version was wrong.
#   4. Refinement: the frame index becomes a sample position by finding the
#      actual energy *rise* near it.
#
# What five rounds of prototyping bought, per the plan's advice for the IN-*
# items.  Each of these was measured against synthetic signals with chosen
# onset frames, and four would have been a bad day inside a UI:
#
#   1. ONSETS LANDED 10-15 ms EARLY.  The reported position was the analysis
#      window's *start*, and a 1024-sample window can begin long before the hit
#      inside it.  The target was +/-5 ms, so the first version could not have
#      met it at any setting.  Hence step 4.
#   2. REFINING ON ENERGY *LEVEL* FOUND THE PREVIOUS HIT'S TAIL.  "Where does
#      this neighbourhood first reach a quarter of its peak" is right for a hit
#      in silence and wrong the moment hits overlap: 1 of 8 matched on sustained
#      material.  An onset is where energy goes *up* and a decaying tail is
#      going down, so refinement follows the rise.
#   3. A CONSTANT 440 Hz TONE PRODUCED 59 ONSETS.  A sine that is not
#      bin-centred leaks, the leakage wobbles frame to frame, rectified flux of
#      that wobble is non-zero everywhere -- and dividing by the maximum then
#      turns the wobble into full-scale "signal".  STRUCTURE_MIN is the fix: a
#      curve whose peak is not clear of its own median holds no transients.
#      Measured, a steady tone is about 3.6 and a drum take over 30.
#   4. A GLOBAL PROMINENCE FLOOR CHANGED NOTHING on any of eleven signals and
#      was deleted rather than kept as a knob that does not turn.  The tail
#      bumps it was meant to catch are not small against the global maximum;
#      they are small against nothing, because the threshold is local and their
#      neighbourhood is quiet.
#   5. THE SHARPNESS TEST IS WHAT MAKES `sensitivity` MEAN ANYTHING on
#      sustained material.  Without it the count was identical at every
#      setting; with it, turning sensitivity down stops the detector slicing a
#      decay tail.
#
# Where it is good, and where it is not.  Measured at the default sensitivity:
#
#   a 16th-note drum pattern ......... 31 of 31, worst error 0.7 ms
#   the same at a fifth the level .... 31 of 31, worst error 0.7 ms
#   two hits 50 ms apart ............. both, separately
#   a ghost note at a tenth the level  found, at every sensitivity
#   silence / white noise / a tone ... nothing, which is the right answer
#   overlapping sustained notes ...... approximate: extra cuts in the decay
#
# That last row is the honest limit and no amount of threshold work moved it:
# the tail of a sustained note genuinely looks like a small attack.  Turning
# sensitivity down helps, and the slice page offers **bars** and **beats** for
# material that transients suit badly -- a choice of three is the answer to
# this, not a better curve.

#: Analysis window and hop.  1024 at 48 kHz is 21 ms: long enough to resolve
#: the low end of a kick, short enough that the hop is 5 ms.
N_FFT = 1024
HOP = 256
#: Peak-to-median ratio a novelty curve needs before it is considered to hold
#: any onsets at all.  See finding 3 above.
STRUCTURE_MIN = 8.0
#: Frames either side that a peak must stand above to count as an attack
#: rather than a hump.  See finding 5.
SHOULDER = 4
#: How much higher than its shoulders, at the strictest sensitivity.
SHARPNESS = 2.0
#: Resolution of the refinement pass, in milliseconds.  Fine enough for the
#: 5 ms target; coarse enough that one cycle of a low note is not a "rise".
REFINE_MS = 1.0
#: Two onsets closer than this are one onset.  30 ms is about the fastest a
#: hand plays two separate hits, and below it a flam becomes two slices.
MIN_GAP_MS = 30.0
#: Local window for the adaptive threshold, in frames (~112 ms at 48 kHz).
THRESHOLD_WINDOW = 21
#: Most slices the slice page will make, so a take of a thousand transients
#: cannot fill the library.
MAX_SLICES = 64


def _mono(buf: np.ndarray) -> np.ndarray:
    if buf.ndim == 1:
        return buf.astype(np.float32, copy=False)
    return buf.mean(axis=1).astype(np.float32, copy=False)


def _magnitudes(mono: np.ndarray) -> np.ndarray:
    """Short-time magnitude spectrum, as ``(frames, bins)``."""
    if len(mono) < N_FFT:
        mono = np.pad(mono, (0, N_FFT - len(mono)))
    window = np.hanning(N_FFT).astype(np.float32)
    frames = 1 + (len(mono) - N_FFT) // HOP
    # One strided gather rather than a Python loop: a four-minute take is a
    # few thousand frames and this runs while the UI is waiting.
    index = np.arange(N_FFT)[None, :] + HOP * np.arange(frames)[:, None]
    return np.abs(np.fft.rfft(mono[index] * window, axis=1))


def novelty(buf: np.ndarray) -> np.ndarray:
    """Half-wave-rectified spectral flux: energy that *appeared* per frame."""
    magnitudes = _magnitudes(_mono(buf))
    rising = np.diff(magnitudes, axis=0, prepend=magnitudes[:1])
    return np.maximum(rising, 0.0).sum(axis=1)


def _peak_frames(curve: np.ndarray, sensitivity: float) -> list[int]:
    """Frames of `curve` that are attacks, at this sensitivity."""
    if curve.size < 3:
        return []
    peak = float(curve.max())
    median = float(np.median(curve))
    if peak <= 0.0 or peak / max(median, 1e-9) < STRUCTURE_MIN:
        # No transient structure: silence, noise, or a held tone.  Returning
        # nothing is the right answer and the alternative is 59 wrong ones.
        return []
    normalised = curve / peak

    half = THRESHOLD_WINDOW // 2
    padded = np.pad(normalised, half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, THRESHOLD_WINDOW)
    local_median = np.median(windows, axis=1)
    # Mean absolute deviation rather than standard deviation: a single loud
    # hit in a quiet bar should not raise the bar for its neighbours.
    spread = np.mean(np.abs(windows - local_median[:, None]), axis=1)
    threshold = local_median + (3.0 - 2.7 * sensitivity) * spread + 0.02
    sharpness = SHARPNESS * (1.0 - 0.8 * sensitivity)

    found: list[int] = []
    for i in range(1, len(normalised) - 1):
        here = normalised[i]
        if here < threshold[i] or here < normalised[i - 1] or here < normalised[i + 1]:
            continue
        lo, hi = max(0, i - SHOULDER), min(len(normalised), i + SHOULDER + 1)
        shoulder = max(
            float(np.mean(normalised[lo:i])) if i > lo else 0.0,
            float(np.mean(normalised[i + 1:hi])) if hi > i + 1 else 0.0,
        )
        if here < shoulder * (1.0 + sharpness):
            continue
        found.append(i)
    return found


def _refine(mono: np.ndarray, frame_start: int, samplerate: int) -> int:
    """Turn a frame index into the sample the attack really begins on.

    The largest positive jump in short-time energy inside the window, because
    that is what an attack is -- and, unlike the energy level, it is not fooled
    by a hit landing on the loud tail of the one before it.
    """
    lo = max(0, frame_start)
    hi = min(len(mono), frame_start + N_FFT + HOP)
    step = max(1, int(samplerate * REFINE_MS / 1000.0))
    segment = np.abs(mono[lo:hi])
    usable = len(segment) // step * step
    if usable < step * 3:
        return frame_start
    blocks = segment[:usable].reshape(-1, step).max(axis=1)
    rise = np.diff(blocks)
    if rise.size == 0 or rise.max() <= 0.0:
        return frame_start
    # +1 because rise[i] is the jump *into* block i+1.
    return lo + (int(np.argmax(rise)) + 1) * step


def onsets(buf: np.ndarray, samplerate: int, sensitivity: float = 0.5,
           limit: int = MAX_SLICES) -> list[int]:
    """Sample positions of the attacks in `buf`, earliest first.

    `sensitivity` runs 0 (only unmistakable hits) to 1 (everything that might
    be one).  `limit` keeps the loudest that many, so a take full of transients
    cannot produce more slices than there are pads.

    Never raises: an empty buffer, one sample, silence and a held tone all
    return an empty list, because this is called from a UI and "I found
    nothing" is a usable answer where an exception is not.
    """
    if buf is None or len(buf) == 0:
        return []
    sensitivity = max(0.0, min(1.0, float(sensitivity)))
    mono = _mono(buf)
    curve = novelty(buf)
    frames = _peak_frames(curve, sensitivity)
    if not frames:
        return []

    if len(frames) > limit > 0:
        # Keep the strongest, then put them back in time order: a kit built
        # from the *first* 64 of 200 transients would stop halfway through the
        # take, which is never what was wanted.
        frames = sorted(sorted(frames, key=lambda f: -curve[f])[:limit])

    gap = max(1, int(samplerate * MIN_GAP_MS / 1000.0))
    out: list[int] = []
    for frame in frames:
        position = _refine(mono, frame * HOP, samplerate)
        if out and position - out[-1] < gap:
            # Refinement can collapse two coarse frames onto one attack.
            continue
        out.append(min(position, len(mono) - 1))
    return out


def even_slices(total_frames: int, count: int) -> list[int]:
    """`count` equal slice points across `total_frames`, starting at 0.

    Used for the bars and beats modes.  Rounding is done once from the exact
    division rather than by accumulating a step, so the last slice cannot drift
    off the end of a long take.
    """
    count = max(1, int(count))
    if total_frames <= 0:
        return [0]
    return [int(round(i * total_frames / count)) for i in range(count)]


def slice_buffers(buf: np.ndarray, points: list[int]) -> list[np.ndarray]:
    """Cut `buf` at `points`, each slice running to the next point.

    Views, not copies, so slicing an eight-bar take costs nothing until
    something writes to one.
    """
    if buf is None or len(buf) == 0 or not points:
        return []
    edges = sorted({max(0, min(int(p), len(buf))) for p in points})
    out = []
    for i, start in enumerate(edges):
        end = edges[i + 1] if i + 1 < len(edges) else len(buf)
        if end > start:
            out.append(buf[start:end])
    return out
