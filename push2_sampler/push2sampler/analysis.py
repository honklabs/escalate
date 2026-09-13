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


# ==========================================================================
# What a take sounds like (IN-02)
# ==========================================================================
# `describe` answers the questions a player would ask about a slot -- what kind
# of sound is this, what note, how fast, how bright, how loud -- entirely from
# DSP.  No network, no model weights, nothing to install.
#
# THE SPEC ASKED FOR SIX ROLES AND THE FEATURES SUPPORT FIVE.  Six rounds of
# prototyping against synthesised material with known answers, and the first
# finding was a product one rather than a bug:
#
#   1. `kick / snare / hat / bass / pad / vocal` IS NOT SEPARABLE by band
#      energy and envelope.  A synthesised snare classified as a hat, 0.85
#      confident, because nothing here tells a noise burst with a 200 Hz body
#      from one without; `pad` and `vocal` are the same problem.  So the
#      vocabulary is what the measurements can stand behind -- `low drum`,
#      `bright drum`, `drum`, `bass`, `tone`, `noise` -- and the honest cost is
#      that a snare comes back as "bright drum".  A label the instrument cannot
#      defend is worse than a coarser one it can.
#   2. AUTOCORRELATION ON A CHORD FINDS THE GCD PERIOD, not the root: a
#      220/277/330 chord came back as 55 Hz, which made every pad look like a
#      bass.  Replaced by matching against a harmonic series.
#   3. WHITE NOISE CLASSIFIED AS A HAT, 0.92 confident.  The feature that fixes
#      it was already being computed: a struck sound decays and noise does not,
#      so envelope sustain gates it.
#   4. PERIODICITY IS NOT PITCH CONFIDENCE.  A kick every half second is 0.95
#      periodic -- at the HIT RATE -- and duly reported a 1200 Hz "pitch",
#      which was the top of the search range.
#   5. SCORING HARMONICITY AS THE MEAN HARMONIC STRENGTH INVERTED IT.  A pure
#      sine has energy in harmonic 1 only, so its mean is max/8: it scored
#      0.13 while white noise, with all eight bands equally full, scored 0.54.
#      Tones became noise and noise became a tone.  Fraction of total energy on
#      the series was right all along; its sub-octave bias needed the separate
#      "the fundamental must be present" guard, not a different measure.
#   6. PITCH WAS BIASED LOW BY THE BAND WIDTH.  A candidate whose +/-4% band
#      merely contains the true peak scores like the true f0, and argmax takes
#      the lowest: 110 Hz read 97, 440 read 409.  Fixed by refining onto the
#      actual peak.
#   7. 55 Hz WAS NOT RESOLVABLE AT ALL in the onset detector's 1024-point
#      window -- 47 Hz bins.  Pitch gets its own 4096-point window (11.7 Hz),
#      which is also why `PITCH_FLOOR_HZ` exists rather than pretending.
#   8. EVEN THEN, NOTE NAMES WERE WRONG.  Pitch landed within one bin, but one
#      bin at 110 Hz is 10% and a semitone is 5.95%, so the name was a
#      semitone or two out.  Parabolic interpolation across the peak brings the
#      worst error to 1.1%, which names every test note correctly.
#   9. And the note-naming helper itself was an octave low -- 440 Hz came back
#      as "A3" -- caught only because the test named the notes it expected.
#
# Measured after all that, on synthesised signals: a kick pattern is `low
# drum`, hats are `bright drum`, a snare is `bright drum` (see finding 1), a
# 55-880 Hz sine is `bass`/`tone` with its note named correctly, a chord is
# `tone` at low confidence (correctly: a chord is not one note), white noise is
# `noise`, and silence is nothing at all.

#: Window for pitch work.  Longer than the onset detector's, because a bass
#: note needs the resolution and 1024 points cannot give it.
PITCH_FFT = 4096
#: Harmonics matched, and each band's half-width as a fraction of its centre.
HARMONICS = 8
HARMONIC_BAND = 0.04
#: Below this fundamental there is nothing a short take can resolve.
PITCH_FLOOR_HZ = 60.0
PITCH_CEILING_HZ = 1200.0
#: Harmonicity above this is a note; below it, unpitched.
TONAL_MIN = 0.18
#: An f0 below this is called `bass` rather than `tone`.
BASS_MAX_HZ = 160.0
#: Fraction of a take within 20% of its peak, above which it is "sustained".
PERCUSSIVE_MAX = 0.35
#: Band edges for the bright/dark split, in Hz.
LOW_HZ, HIGH_HZ = 200.0, 2000.0
#: A peak below this is silence as far as any of this is concerned.
SILENT_PEAK = 0.001
#: Tempo is only claimed from at least this many onsets.
TEMPO_MIN_ONSETS = 4
#: Inter-onset gaps outside this range are not a beat.
TEMPO_MIN_GAP_S, TEMPO_MAX_GAP_S = 0.05, 2.0
#: Tempo is folded by octaves into this range, the way a person would read it.
TEMPO_LOW, TEMPO_HIGH = 60.0, 190.0
#: Below this confidence no tempo is reported at all.
#:
#: Measured: material with crisp attacks (a click or sampled-drum loop) reads
#: its true tempo to within 0.2 BPM at confidence 0.98-1.00, while material
#: whose attacks are smeared -- a synthesised kick whose body sweeps downward
#: for 150 ms -- reads 20-80 BPM out at confidence 0.00-0.24.  A coarser
#: minimum onset gap did not help: measured at 30, 60 and 100 ms the smeared
#: case was wrong at all three.  The confidence was honest throughout, so the
#: fix is to act on it: "no clear tempo" beats "about 98 BPM (loose)" when the
#: real answer is 120.
TEMPO_MIN_CONFIDENCE = 0.25

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

#: Role names.  Five plus `noise`; see finding 1 for why not the spec's six.
ROLE_LOW_DRUM = "low drum"
ROLE_BRIGHT_DRUM = "bright drum"
ROLE_DRUM = "drum"
ROLE_BASS = "bass"
ROLE_TONE = "tone"
ROLE_NOISE = "noise"
ROLES = (ROLE_LOW_DRUM, ROLE_BRIGHT_DRUM, ROLE_DRUM, ROLE_BASS, ROLE_TONE,
         ROLE_NOISE)

#: A short name suggestion per role, for the naming page.  Deliberately generic:
#: the instrument knows the sound is a low struck thing, not that it is your
#: 808.
ROLE_NAMES = {
    ROLE_LOW_DRUM: "kick",
    ROLE_BRIGHT_DRUM: "hat",
    ROLE_DRUM: "drum",
    ROLE_BASS: "bass",
    ROLE_TONE: "tone",
    ROLE_NOISE: "noise",
}


def note_name(hz: float) -> str:
    """A pitch as a note name, or "" for no pitch.

    A4 = 440.  The first version of this returned "A3" for 440 Hz and the only
    reason it was caught is that the test named the notes it expected -- which
    is the argument for writing the expectation down rather than eyeballing
    frequencies.
    """
    if hz <= 0:
        return ""
    semitones = int(round(12.0 * np.log2(hz / 440.0))) + 57
    if semitones < 0:
        return ""
    return f"{NOTE_NAMES[semitones % 12]}{semitones // 12}"


def loudness(buf) -> tuple[float, float]:
    """``(rms, peak)`` of a buffer, both 0.0 when it is empty."""
    mono = _mono(np.asarray(buf)) if buf is not None else np.zeros(0)
    if mono.size == 0:
        return 0.0, 0.0
    return float(np.sqrt(np.mean(mono ** 2))), float(np.abs(mono).max())


def sustain(buf) -> float:
    """Fraction of the take within 20% of its peak: 0 struck, 1 held.

    The feature that separates "a hat" from "two seconds of white noise",
    which band energy could not (finding 3).
    """
    mono = np.abs(_mono(np.asarray(buf))) if buf is not None else np.zeros(0)
    if mono.size == 0:
        return 0.0
    top = float(mono.max())
    return float((mono > top * 0.2).mean()) if top > 0 else 0.0


def bands(buf, samplerate: int) -> tuple[float, float, float]:
    """Fraction of energy below 200 Hz, 200-2000, and above, over loud frames.

    Quiet frames are dropped: the silence between hits would otherwise drag a
    drum loop's spectrum towards whatever the noise floor looks like.
    """
    magnitudes = _magnitudes(_mono(np.asarray(buf)))
    if magnitudes.size == 0:
        return (0.0, 0.0, 0.0)
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / samplerate)
    energy = magnitudes.sum(axis=1)
    if energy.max() <= 0:
        return (0.0, 0.0, 0.0)
    loud = magnitudes[energy >= energy.max() * 0.1]
    low = float(loud[:, freqs < LOW_HZ].sum())
    mid = float(loud[:, (freqs >= LOW_HZ) & (freqs < HIGH_HZ)].sum())
    high = float(loud[:, freqs >= HIGH_HZ].sum())
    total = low + mid + high
    if total <= 0:
        return (0.0, 0.0, 0.0)
    return (low / total, mid / total, high / total)


def centroid(buf, samplerate: int) -> float:
    """Spectral centroid in Hz over the loud frames: how bright it is."""
    magnitudes = _magnitudes(_mono(np.asarray(buf)))
    if magnitudes.size == 0:
        return 0.0
    freqs = np.fft.rfftfreq(N_FFT, 1.0 / samplerate)
    energy = magnitudes.sum(axis=1)
    if energy.max() <= 0:
        return 0.0
    loud = magnitudes[energy >= energy.max() * 0.1]
    total = float(loud.sum())
    if total <= 0:
        return 0.0
    return float((loud * freqs).sum() / total)


def _loudest_spectrum(buf, samplerate: int):
    """Magnitudes and bin frequencies of the loudest `PITCH_FFT` window."""
    mono = _mono(np.asarray(buf, dtype=np.float32))
    if mono.size == 0:
        return None, None
    if mono.size < PITCH_FFT:
        mono = np.pad(mono, (0, PITCH_FFT - mono.size))
    stride = max(1, PITCH_FFT // 4)
    starts = range(0, max(1, len(mono) - PITCH_FFT + 1), stride)
    best = max(starts, key=lambda s: float(np.abs(mono[s:s + PITCH_FFT]).sum()))
    window = np.hanning(PITCH_FFT).astype(np.float32)
    segment = mono[best:best + PITCH_FFT] * window
    return np.abs(np.fft.rfft(segment)), np.fft.rfftfreq(PITCH_FFT, 1.0 / samplerate)


def harmonicity(buf, samplerate: int) -> tuple[float, float]:
    """``(f0_hz, 0..1)``: the best fundamental, and how much sits on its series.

    The confidence is the fraction of the loudest window's energy lying within
    4% of harmonics 1-8 of `f0`.  A sine is near 1, a chord about a third
    (correctly: a chord is not one note), white noise near 0.
    """
    frame, freqs = _loudest_spectrum(buf, samplerate)
    if frame is None:
        return 0.0, 0.0
    total = float(frame.sum())
    if total <= 0:
        return 0.0, 0.0
    nyquist = float(freqs[-1])
    peak_bin = float(frame.max())
    best_score, best_f0 = 0.0, 0.0
    for f0 in np.geomspace(PITCH_FLOOR_HZ, min(PITCH_CEILING_HZ, nyquist / 2), 300):
        harmonics = f0 * np.arange(1, HARMONICS + 1)
        harmonics = harmonics[harmonics < nyquist]
        if harmonics.size < 2:
            continue
        first = (freqs > f0 * (1 - HARMONIC_BAND)) & (freqs < f0 * (1 + HARMONIC_BAND))
        if not first.any() or float(frame[first].max()) < peak_bin * 0.25:
            # Finding 5: without this, a low f0 scores on its upper harmonics
            # alone and everything tonal comes back a bass.
            continue
        energy = 0.0
        for harmonic in harmonics:
            band = ((freqs > harmonic * (1 - HARMONIC_BAND))
                    & (freqs < harmonic * (1 + HARMONIC_BAND)))
            if band.any():
                energy += float(frame[band].sum())
        score = energy / total
        if score > best_score:
            best_score, best_f0 = score, f0
    if best_f0 <= 0:
        return 0.0, 0.0
    return _refine_pitch(frame, freqs, best_f0), min(1.0, best_score)


def _refine_pitch(frame, freqs, f0: float) -> float:
    """The real peak in `f0`'s band, interpolated across its neighbours.

    Two findings in one function.  Taking the band's own centre left the
    estimate biased low by up to the band width (6); taking the nearest bin
    left it up to one bin out, which at 110 Hz is 10% -- wider than the 5.95%
    of a semitone, so note names came out wrong (8).
    """
    band = np.flatnonzero((freqs > f0 * (1 - HARMONIC_BAND))
                          & (freqs < f0 * (1 + HARMONIC_BAND)))
    if band.size == 0:
        return float(f0)
    k = int(band[int(np.argmax(frame[band]))])
    if 0 < k < len(frame) - 1:
        left, here, right = float(frame[k - 1]), float(frame[k]), float(frame[k + 1])
        denominator = left - 2.0 * here + right
        if denominator != 0.0:
            shift = float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))
            return float(freqs[k] + shift * (freqs[1] - freqs[0]))
    return float(freqs[k])


def tempo(onset_frames, samplerate: int,
          reference_bpm: float = 0.0) -> tuple[float, float]:
    """``(bpm, 0..1)`` from the gaps between onsets, or ``(0, 0)``.

    The most common gap between hits *is* the beat, or a division of it, in
    almost any rhythmic material -- and the onsets have already been found, so
    this costs nothing on top. The confidence is how tightly the gaps cluster:
    a machine-exact loop is near 1, a rubato performance near 0.

    **Tempo has an unresolvable octave ambiguity from onsets alone.** "90 BPM
    with a hit on every eighth" and "180 BPM with a hit on every beat" are the
    same recording, and nothing in the timing distinguishes them -- only a
    model of where the strong beats fall would, which is a great deal of
    machinery for a reading on an info page.  Measured, a 90 BPM loop played in
    eighths reads 180 at full confidence, and that answer is not wrong so much
    as the other half of a pair.

    So `reference_bpm` is the way out that a *sampler* has and a general
    analyser does not: the session already has a tempo, and of the octaves of
    the detected figure the one nearest the session's is almost always the one
    meant.  Without a reference the figure is folded into a range a person
    would read and left there.
    """
    frames = np.asarray(list(onset_frames or []), dtype=np.float64)
    if frames.size < TEMPO_MIN_ONSETS:
        return 0.0, 0.0
    gaps = np.diff(frames) / max(1, samplerate)
    gaps = gaps[(gaps > TEMPO_MIN_GAP_S) & (gaps < TEMPO_MAX_GAP_S)]
    if gaps.size < 3:
        return 0.0, 0.0
    median = float(np.median(gaps))
    if median <= 0:
        return 0.0, 0.0
    spread = float(np.median(np.abs(gaps - median))) / median
    bpm = 60.0 / median
    if reference_bpm and reference_bpm > 0:
        # Pick the octave nearest the session, comparing in log space so that
        # "half" and "double" are equally far away.
        candidates = [bpm * 2.0 ** n for n in range(-3, 4)]
        candidates = [c for c in candidates if TEMPO_LOW / 2 <= c <= TEMPO_HIGH * 2]
        if candidates:
            bpm = min(candidates,
                      key=lambda c: abs(np.log2(c / reference_bpm)))
    else:
        for _ in range(8):
            if bpm < TEMPO_LOW:
                bpm *= 2.0
            elif bpm > TEMPO_HIGH:
                bpm /= 2.0
            else:
                break
    confidence = max(0.0, min(1.0, 1.0 - spread * 4.0))
    if confidence < TEMPO_MIN_CONFIDENCE:
        # Saying nothing is the honest answer: see TEMPO_MIN_CONFIDENCE.
        return 0.0, confidence
    return bpm, confidence


class Description:
    """What listening to one take established.  Plain attributes, no behaviour.

    `role` is None when nothing could be said -- silence, or an empty slot.
    Every confidence is 0..1 and every one of them is allowed to be low: this
    page's job is to say what it thinks *and* how sure it is, because a guess
    stated confidently is worse than no guess.
    """

    __slots__ = ("role", "confidence", "detail", "f0", "note", "pitch_confidence",
                 "centroid", "rms", "peak", "sustain", "bands", "onsets",
                 "density", "bpm", "bpm_confidence", "seconds")

    def __init__(self, **fields) -> None:
        for name in self.__slots__:
            setattr(self, name, fields.get(name))

    @property
    def suggested_name(self) -> str:
        """A short name for this take, or "" when there is nothing to say.

        Generic on purpose: the measurements know the sound is a low struck
        thing, not that it is your 808.  A pitched take gets its note, because
        that is the one specific thing actually measured.
        """
        if not self.role:
            return ""
        base = ROLE_NAMES.get(self.role, self.role)
        if self.role in (ROLE_BASS, ROLE_TONE) and self.note:
            return f"{base} {self.note}"
        return base

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"<Description {self.role!r} {self.confidence:.2f} {self.detail!r}>"


def describe(buf, samplerate: int, onset_frames=None,
             reference_bpm: float = 0.0) -> Description:
    """Everything `analysis` can say about one take.

    `onset_frames` is passed in when the caller already has them (the slice
    page does), because finding them is the expensive part.  Never raises: an
    empty or silent buffer comes back with `role` None, which is the honest
    answer and what the info page renders.
    """
    audio = np.asarray(buf, dtype=np.float32) if buf is not None else np.zeros((0, 1))
    seconds = audio.shape[0] / max(1, samplerate)
    rms, peak = loudness(audio)
    if audio.size == 0 or peak <= SILENT_PEAK:
        return Description(role=None, confidence=0.0, detail="silent", f0=0.0,
                           note="", pitch_confidence=0.0, centroid=0.0, rms=rms,
                           peak=peak, sustain=0.0, bands=(0.0, 0.0, 0.0),
                           onsets=[], density=0.0, bpm=0.0, bpm_confidence=0.0,
                           seconds=seconds)

    found = list(onset_frames) if onset_frames is not None else onsets(audio, samplerate)
    low, mid, high = bands(audio, samplerate)
    held = sustain(audio)
    f0, harmonic = harmonicity(audio, samplerate)
    bpm, bpm_confidence = tempo(found, samplerate, reference_bpm)

    if held < PERCUSSIVE_MAX:
        if low > 0.45:
            role, confidence, detail = ROLE_LOW_DRUM, low, "low, struck"
        elif high > 0.5:
            role, confidence, detail = ROLE_BRIGHT_DRUM, high, "bright, struck"
        else:
            role, confidence, detail = ROLE_DRUM, max(mid, 0.4), "struck"
    elif harmonic > TONAL_MIN:
        role = ROLE_BASS if f0 < BASS_MAX_HZ else ROLE_TONE
        confidence, detail = harmonic, f"{f0:.0f} Hz"
    else:
        role, confidence, detail = ROLE_NOISE, 1.0 - harmonic, "sustained, unpitched"

    pitched = role in (ROLE_BASS, ROLE_TONE)
    return Description(
        role=role, confidence=float(min(1.0, confidence)), detail=detail,
        f0=f0 if pitched else 0.0,
        note=note_name(f0) if pitched else "",
        pitch_confidence=harmonic,
        centroid=centroid(audio, samplerate), rms=rms, peak=peak, sustain=held,
        bands=(low, mid, high), onsets=found,
        density=len(found) / seconds if seconds > 0 else 0.0,
        bpm=bpm, bpm_confidence=bpm_confidence, seconds=seconds,
    )
