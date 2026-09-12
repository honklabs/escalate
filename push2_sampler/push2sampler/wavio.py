"""Minimal WAV read/write for float32 numpy buffers shaped ``(frames, ch)``.

``soundfile`` is used when it is installed (it keeps full float precision);
otherwise we fall back to the standard library's :mod:`wave` module and 16-bit
PCM, so the program never hard-depends on libsndfile.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def _soundfile():
    try:
        import soundfile  # type: ignore
    except Exception:
        return None
    return soundfile


def write(path: str | Path, data: np.ndarray, samplerate: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2:
        raise ValueError(f"expected a (frames, channels) buffer, got shape {data.shape}")
    sf = _soundfile()
    if sf is not None:
        sf.write(str(path), data, samplerate, subtype="FLOAT")
        return
    clipped = np.clip(data, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(data.shape[1])
        fh.setsampwidth(2)
        fh.setframerate(samplerate)
        fh.writeframes(pcm.tobytes())


def read(path: str | Path) -> tuple[np.ndarray, int]:
    """Return ``(data, samplerate)`` with ``data`` float32 ``(frames, ch)``."""
    path = Path(path)
    sf = _soundfile()
    if sf is not None:
        data, samplerate = sf.read(str(path), dtype="float32", always_2d=True)
        return np.ascontiguousarray(data, dtype=np.float32), int(samplerate)
    with wave.open(str(path), "rb") as fh:
        channels = fh.getnchannels()
        width = fh.getsampwidth()
        samplerate = fh.getframerate()
        raw = fh.readframes(fh.getnframes())
    if width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:  # pragma: no cover - unusual widths
        raise ValueError(f"unsupported sample width: {width * 8} bit")
    return np.ascontiguousarray(samples.reshape(-1, channels)), int(samplerate)


def resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear-interpolation resample; good enough for loading foreign files."""
    if src_rate == dst_rate or data.shape[0] == 0:
        return data
    ratio = dst_rate / src_rate
    n_out = max(1, int(round(data.shape[0] * ratio)))
    src_idx = np.linspace(0.0, data.shape[0] - 1, n_out)
    out = np.empty((n_out, data.shape[1]), dtype=np.float32)
    grid = np.arange(data.shape[0])
    for ch in range(data.shape[1]):
        out[:, ch] = np.interp(src_idx, grid, data[:, ch])
    return out
