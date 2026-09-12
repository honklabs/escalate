"""Non-destructive edits to a take.

A recorded take is never altered in place.  Instead each sample carries an
:class:`Edits` -- trim, fades, pitch, reverse, normalise -- and
:func:`render_edits` applies them on the way to the mixer.  That means an edit can be
taken back, or changed a dozen times while you listen, without ever losing the
original recording; committing the edits destructively is a separate, deliberate
act.

The order is fixed and matters: trim, then reverse, then pitch, then the fades,
then normalise.  Fades come after pitch so their length is what you asked for in
the *result*, and normalise comes last so it sees the finished audio.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .audio import make_fade
from .wavio import resample

#: Normalise to just under full scale, so a bounce has somewhere to go.
NORMALIZE_PEAK = 0.891  # -1 dBFS
#: Keep at least this much audio however hard the trims are pushed.
MIN_FRAMES = 16


@dataclass(frozen=True)
class Edits:
    """What to do to a take before it plays.  Frozen, so it is a cache key."""

    trim_start_ms: float = 0.0
    trim_end_ms: float = 0.0
    fade_in_ms: float = 0.0
    fade_out_ms: float = 0.0
    pitch_semitones: float = 0.0
    reverse: bool = False
    normalize: bool = False

    @property
    def is_default(self) -> bool:
        return self == DEFAULT_EDITS

    def with_value(self, field: str, value) -> "Edits":
        return replace(self, **{field: value})

    def as_dict(self) -> dict:
        return {
            "trim_start_ms": round(float(self.trim_start_ms), 3),
            "trim_end_ms": round(float(self.trim_end_ms), 3),
            "fade_in_ms": round(float(self.fade_in_ms), 3),
            "fade_out_ms": round(float(self.fade_out_ms), 3),
            "pitch_semitones": round(float(self.pitch_semitones), 3),
            "reverse": bool(self.reverse),
            "normalize": bool(self.normalize),
        }

    @classmethod
    def from_dict(cls, payload: dict | None) -> "Edits":
        """Read edits from a project file, coercing each field on its own.

        A hand-edited file with one nonsense value loses that value and keeps
        the rest -- and never stores a string where a number has to be, which
        would fail much later, in the middle of rendering audio.
        """
        if not payload:
            return DEFAULT_EDITS
        values = {}
        for name in cls.__dataclass_fields__:
            if name not in payload:
                continue
            default = getattr(DEFAULT_EDITS, name)
            try:
                values[name] = bool(payload[name]) if isinstance(default, bool) \
                    else float(payload[name])
            except (TypeError, ValueError):
                continue  # keep the default for this one field
        return cls(**values)


#: An Edits that does nothing.
DEFAULT_EDITS = Edits()


def pitch_ratio(semitones: float) -> float:
    """Playback speed for a pitch shift: +12 semitones plays twice as fast."""
    return float(2.0 ** (semitones / 12.0))


def render_edits(audio: np.ndarray, samplerate: int, edits: Edits) -> np.ndarray:
    """Apply ``edits`` to ``audio``.  Returns ``audio`` itself when there is
    nothing to do, so the common case costs nothing."""
    if edits.is_default or audio.shape[0] == 0:
        return audio

    out = _trim(audio, samplerate, edits)
    if edits.reverse:
        out = out[::-1]
    if edits.pitch_semitones:
        ratio = pitch_ratio(edits.pitch_semitones)
        out = resample(out, samplerate, max(1, int(round(samplerate / ratio))))
    out = _faded(out, samplerate, edits)
    if edits.normalize:
        peak = float(np.abs(out).max())
        if peak > 0:
            out = out * (NORMALIZE_PEAK / peak)
    return np.ascontiguousarray(out, dtype=np.float32)


def _trim(audio: np.ndarray, samplerate: int, edits: Edits) -> np.ndarray:
    total = audio.shape[0]
    start = min(_frames(edits.trim_start_ms, samplerate), max(0, total - MIN_FRAMES))
    end = total - _frames(edits.trim_end_ms, samplerate)
    end = max(end, start + MIN_FRAMES)
    return audio[start : min(end, total)]


def _faded(audio: np.ndarray, samplerate: int, edits: Edits) -> np.ndarray:
    fade_in = min(_frames(edits.fade_in_ms, samplerate), audio.shape[0])
    fade_out = min(_frames(edits.fade_out_ms, samplerate), audio.shape[0])
    if not fade_in and not fade_out:
        return audio
    out = np.array(audio, dtype=np.float32, copy=True)
    if fade_in:
        rise, _ = make_fade(fade_in)
        out[:fade_in] *= rise[:, None]
    if fade_out:
        _, fall = make_fade(fade_out)
        out[-fade_out:] *= fall[:, None]
    return out


def _frames(milliseconds: float, samplerate: int) -> int:
    return max(0, int(round(max(0.0, milliseconds) * samplerate / 1000.0)))
