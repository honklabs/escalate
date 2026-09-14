"""NH-09: making a take fit a tempo it was not recorded at.

A take remembers the tempo it was cut at (`F-09`), so changing the song's tempo
leaves it the wrong length: a two-bar loop recorded at 240 BPM is 1.83 bars at
220. Until now the only answers were to live with it or to
[repair](project.Project.repair) it destructively -- pad or trim. This adds the
two non-destructive ones, per sample:

``resample``
    Play it faster or slower. Instant, and it **changes the pitch** -- which for
    a drum break is often the musical answer rather than a compromise.

``wsola``
    Waveform-similarity overlap-add: keep the pitch and change the length.
    Costs a pass over the audio, so it runs as a stepped job (`StretchJob`) and
    never in the callback.

Nothing here runs on the audio thread. `stretch` allocates, searches and
divides; it is called when a tempo changes, and what the callback sees is a
finished array, rebound in one assignment.

Measured, on material built at known frequencies (`tests/test_stretch.py`):

* a 440 Hz tone stretched by 0.5x, 0.75x, 1.25x, 1.5x and 2.0x comes back at
  439 Hz every time, and exactly the requested length;
* `resample` at the same rates comes back at 880, 586, 352, 293 and 220 Hz --
  the pitch scaling that makes it the wrong tool for a melody and the right one
  for a break;
* a C major chord keeps all three of its partials at 0.92-1.00 of full strength
  at every rate.
"""

from __future__ import annotations

import numpy as np

#: Per-sample stretch behaviour.  ``off`` is the default and what every project
#: before format 12 has: the take plays at its own length and the library flags
#: it yellow when that no longer fits.
STRETCH_OFF = "off"
STRETCH_RESAMPLE = "resample"
STRETCH_WSOLA = "wsola"
STRETCH_MODES = (STRETCH_OFF, STRETCH_RESAMPLE, STRETCH_WSOLA)

STRETCH_LABELS = {
    STRETCH_OFF: "off",
    STRETCH_RESAMPLE: "resample (pitch moves)",
    STRETCH_WSOLA: "stretch (pitch held)",
}

#: WSOLA analysis window.
#:
#: 1024 frames, chosen by measurement rather than by convention.  Frame sizes of
#: 256, 512, 1024 and 2048 were each tried at two rates against a drum loop, a
#: chord, a tone and noise; 1024 was best or within noise of best at both rates,
#: and every size held a 440 Hz tone's pitch exactly.
WSOLA_FRAME = 1024

#: A rate this close to 1 is not worth a pass over the audio.
RATE_EPSILON = 1e-4
#: Rates outside this are refused: past them the output is not the take any
#: more, and a tempo change that large means the take belongs to another song.
RATE_MIN, RATE_MAX = 0.25, 4.0


def _mono(buf: np.ndarray) -> np.ndarray:
    return buf if buf.ndim == 1 else buf.mean(axis=1)


def resample(buf: np.ndarray, frames: int) -> np.ndarray:
    """``buf`` linearly resampled to exactly ``frames``.  Pitch moves with it.

    Per channel, which is correct here: resampling is a single monotone map of
    time, so every channel gets the same one and the stereo image is untouched.
    """
    buf = np.asarray(buf, dtype=np.float32)
    frames = max(0, int(frames))
    if buf.ndim == 1:
        buf = buf[:, None]
    if frames == 0 or buf.shape[0] == 0:
        return np.zeros((frames, buf.shape[1]), dtype=np.float32)
    if frames == buf.shape[0]:
        return buf
    source = np.arange(buf.shape[0], dtype=np.float64)
    target = np.linspace(0.0, buf.shape[0] - 1, frames)
    out = np.empty((frames, buf.shape[1]), dtype=np.float32)
    for channel in range(buf.shape[1]):
        out[:, channel] = np.interp(target, source, buf[:, channel])
    return out


def wsola(buf: np.ndarray, rate: float, frame: int = WSOLA_FRAME) -> np.ndarray:
    """``buf`` stretched to ``rate`` times its length, keeping its pitch.

    Overlap-add of windowed frames taken from wherever the waveform best
    continues what was already written, rather than from a fixed grid -- which
    is what stops the copies fighting each other and turning a tone into a
    warble.

    **The search runs on the channel sum and the result is applied to every
    channel.** Searching per channel would choose different offsets left and
    right and smear the stereo image, which is a worse artefact than the one it
    would be fixing.
    """
    buf = np.asarray(buf, dtype=np.float32)
    if buf.ndim == 1:
        buf = buf[:, None]
    rate = float(rate)
    frames_in, channels = buf.shape
    keep = int(round(frames_in * rate))
    if rate <= 0 or keep <= 0:
        return np.zeros((0, channels), dtype=np.float32)
    if frames_in < frame * 2:
        # Too short to overlap-add meaningfully; resampling at least gets the
        # length right, and at this size nobody can hear the pitch move.
        return resample(buf, keep)

    hop_out = frame // 2
    hop_in = max(1, int(round(hop_out / rate)))
    #: Half a hop either side was measured against a full hop; the full hop was
    #: better or equal at both rates tested, and costs nothing once the search
    #: is a correlation rather than a loop.
    tolerance = hop_in
    window = np.hanning(frame).astype(np.float64)
    mono = _mono(buf).astype(np.float64)

    out = np.zeros((keep + frame, channels), dtype=np.float64)
    weight = np.zeros(keep + frame, dtype=np.float64)
    last_start = frames_in - frame

    read = 0
    written = 0
    index = 0
    while written < keep:
        # Clamped to the last whole frame: running out of input reuses the
        # final frames rather than leaving the tail silent.  Without this a
        # 2-second tone stretched to 1.5x ended in 615 frames of silence and a
        # 0.488 step into it -- an audible click, measured.
        ideal = min(int(round(index * hop_in)), last_start)
        if index == 0:
            start = ideal
        else:
            # Where the previous frame would carry on to if nothing moved.
            wanted = min(read + hop_out, last_start)
            target = mono[wanted:wanted + frame]
            low = max(0, ideal - tolerance)
            high = min(last_start, ideal + tolerance)
            if high <= low:
                start = low
            else:
                # Every candidate's similarity in one call.  As a Python loop
                # this was 7-13x slower and bit-for-bit identical: a 30-second
                # take went from 2.2 s to 0.33 s.
                scores = np.correlate(mono[low:high + frame], target, mode="valid")
                start = low + int(np.argmax(scores))
        piece = buf[start:start + frame].astype(np.float64) * window[:, None]
        out[written:written + frame] += piece
        weight[written:written + frame] += window
        read = start
        written += hop_out
        index += 1

    # Dividing by the summed window rather than assuming it sums to one is what
    # makes the first and last frames come out at the right level.
    weight[weight < 1e-6] = 1.0
    return (out[:keep] / weight[:keep, None]).astype(np.float32)


def stretch(buf: np.ndarray, rate: float, mode: str) -> np.ndarray:
    """``buf`` made ``rate`` times as long, however ``mode`` says.

    Returns the input unchanged for ``off``, for a rate of 1, and for a rate so
    far from 1 that the result would not be the take any more -- in which case
    the library's off-grid warning is the better answer and is still there.
    """
    buf = np.asarray(buf, dtype=np.float32)
    if buf.ndim == 1:
        buf = buf[:, None]
    if mode not in (STRETCH_RESAMPLE, STRETCH_WSOLA):
        return buf
    if not np.isfinite(rate) or abs(rate - 1.0) < RATE_EPSILON:
        return buf
    if not RATE_MIN <= rate <= RATE_MAX:
        return buf
    if mode == STRETCH_RESAMPLE:
        return resample(buf, int(round(buf.shape[0] * rate)))
    return wsola(buf, rate)


def stretch_rate(source_bpm: float, target_bpm: float) -> float:
    """How much longer a take cut at ``source_bpm`` must be to fit ``target_bpm``.

    Slower song, longer bars, longer take: the rate is ``source / target``.  0
    when either tempo is missing, which callers read as "nothing to do".
    """
    try:
        source, target = float(source_bpm), float(target_bpm)
    except (TypeError, ValueError):
        return 0.0
    if source <= 0 or target <= 0:
        return 0.0
    return source / target


def suggested_mode(role: str | None) -> str:
    """Which stretch a take of this `IN-02` role probably wants.

    Percussion gets ``resample``: a break played faster *is* pitched up, and
    that is a sound records have been made of, where WSOLA on a transient is
    just smeared.  Measured, a drum loop's spectrum survives a WSOLA stretch at
    only 0.78-0.83 similarity against 0.96-1.00 for a chord, so this is not a
    preference -- percussion is the case the method is worst at.

    Pitched material gets ``wsola``, because a bass line that changes key when
    you change tempo is not usable.
    """
    if not role:
        return STRETCH_OFF
    if role in ("bass", "tone"):
        return STRETCH_WSOLA
    return STRETCH_RESAMPLE


class StretchJob:
    """Stretch every slot that needs it, one slot per :meth:`step` (NH-09).

    A stepped job rather than the thread the plan asked for, and for a reason
    the plan could not have known: this program already renders bounces this
    way (`render.BounceJob`), driven from the frame loop.  The worry the plan
    was answering -- "the worker must not be started from the audio callback"
    -- is met more simply by there being no worker at all.  Nothing here runs on
    the audio thread, and the callback never sees a partial buffer because a
    slot's cache is rebound to a *finished* array in one assignment.

    One slot per step keeps a frame's worth of work bounded at roughly the cost
    of the longest single take, which measured about 400 ms for 30 seconds --
    long for a frame, so the surface pauses, which is why the job says what it
    is doing.
    """

    def __init__(self, project) -> None:
        self.project = project
        self.pending = list(project.pending_stretches())
        self.total = len(self.pending)
        self.done = not self.pending
        #: Slots finished, for a progress readout.
        self.finished = 0

    @property
    def progress(self) -> float:
        return 1.0 if not self.total else self.finished / self.total

    def step(self) -> bool:
        """Stretch one slot.  True while there is more to do."""
        if self.done:
            return False
        sample = self.pending.pop(0)
        # The set may have moved under us -- a tempo change, an edit, a delete
        # -- so re-ask rather than trusting the list we built.
        if self.project[sample.slot] is sample:
            rate = self.project.stretch_rate_for(sample)
            if RATE_MIN <= rate <= RATE_MAX and abs(rate - 1.0) >= RATE_EPSILON:
                sample.compute_stretch(self.project.samplerate, rate)
        self.finished += 1
        if not self.pending:
            self.done = True
            return False
        return True
