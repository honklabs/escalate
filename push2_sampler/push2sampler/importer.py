"""NF-08: bring audio you already own into a slot.

Everything else in this program makes its own audio, which means a drum hit or
a stem you already have is unreachable. This reads a file, resamples it to the
session rate, and works out how many bars it fills at the session tempo.

What it deliberately does **not** do is stretch. A 3.5-bar file stays 3.5 bars
long and is flagged off-grid by the same machinery that flags a take recorded at
a different tempo (`F-09`) -- the repair is one button away on the sample page
and it is the player's decision, not ours. Silently time-stretching someone's
audio to fit a grid it was never on is the kind of helpfulness nobody asks for.

Format support is honest about what is installed: ``.wav`` always, through the
standard library, and the rest only when ``soundfile`` is present. A missing
codec produces a sentence naming the file and the fix.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import wavio

#: Read with the standard library, so always available.
NATIVE_SUFFIXES: tuple[str, ...] = (".wav",)

#: Read only when ``soundfile`` (libsndfile) is installed.
SOUNDFILE_SUFFIXES: tuple[str, ...] = (
    ".flac", ".aiff", ".aif", ".ogg", ".oga", ".opus", ".mp3", ".w64", ".caf",
)

ALL_SUFFIXES: tuple[str, ...] = NATIVE_SUFFIXES + SOUNDFILE_SUFFIXES


@dataclass(frozen=True)
class AudioInfo:
    """What can be learned about a file without loading all of it."""

    path: Path
    frames: int = 0
    samplerate: int = 0
    channels: int = 0
    #: Empty when the file can be read; otherwise why it cannot.
    problem: str = ""

    @property
    def readable(self) -> bool:
        return not self.problem

    @property
    def seconds(self) -> float:
        if self.samplerate <= 0:
            return 0.0
        return self.frames / self.samplerate

    @property
    def label(self) -> str:
        """One line for the display."""
        if self.problem:
            return f"{self.path.name}  --  {self.problem}"
        channels = "mono" if self.channels == 1 else f"{self.channels}ch"
        return (
            f"{self.path.name}  {self.seconds:.2f}s  "
            f"{self.samplerate} Hz  {channels}"
        )


def looks_like_audio(path: Path) -> bool:
    """True for a suffix this program would ever try to read."""
    return path.suffix.lower() in ALL_SUFFIXES


def probe(path: str | Path) -> AudioInfo:
    """Read a file's header only.

    The browser draws a directory at a time, so opening every file in full to
    show a length would mean loading gigabytes to paint a grid -- the same
    reason ``Project.scan`` reads ``project.json`` rather than the takes.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in ALL_SUFFIXES:
        return AudioInfo(path, problem=f"not an audio file ({suffix or 'no suffix'})")
    if not path.is_file():
        return AudioInfo(path, problem="no such file")

    sf = wavio._soundfile()
    if sf is not None:
        try:
            info = sf.info(str(path))
        except Exception as exc:
            return AudioInfo(path, problem=_short(exc))
        return AudioInfo(
            path, frames=int(info.frames), samplerate=int(info.samplerate),
            channels=int(info.channels),
        )

    if suffix not in NATIVE_SUFFIXES:
        return AudioInfo(
            path,
            problem=f"needs soundfile for {suffix} files -- pip install soundfile",
        )
    try:
        with wave.open(str(path), "rb") as fh:
            return AudioInfo(
                path, frames=fh.getnframes(), samplerate=fh.getframerate(),
                channels=fh.getnchannels(),
            )
    except Exception as exc:
        return AudioInfo(path, problem=_short(exc))


def _short(exc: Exception) -> str:
    """One line, because this goes on a 960x160 display."""
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:72]


def listing(directory: str | Path) -> tuple[list[Path], list[Path]]:
    """``(directories, audio files)`` in ``directory``, each sorted by name.

    Hidden entries are skipped: a samples folder full of ``.DS_Store`` and
    ``__MACOSX`` is not a folder anyone wants to look at on 64 pads.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return [], []
    dirs: list[Path] = []
    files: list[Path] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return [], []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                dirs.append(entry)
            elif looks_like_audio(entry):
                files.append(entry)
        except OSError:  # pragma: no cover - a broken symlink
            continue
    return dirs, files


def bars_for(frames: int, bpm: float, samplerate: int, beats_per_bar: int = 4):
    """``(whole bars to claim, exact bars the audio fills)``.

    The claim is the nearest whole bar and at least one, so a half-bar hit is a
    one-bar slot rather than a zero-bar one; the exact figure is what decides
    whether it is flagged off-grid.
    """
    frames_per_bar = 60.0 / bpm * samplerate * beats_per_bar if bpm > 0 else 0.0
    if frames_per_bar <= 0:
        return 1, 1.0
    exact = frames / frames_per_bar
    return max(1, int(round(exact))) or 1, exact


def load(path: str | Path, samplerate: int) -> tuple[np.ndarray, AudioInfo]:
    """Read a file and resample it to ``samplerate``.

    Raises :class:`ImportError` with a readable message when it cannot -- the
    callers are a mode and a command line, and both want a sentence rather than
    a traceback.
    """
    info = probe(path)
    if not info.readable:
        raise ImportError(info.problem)
    try:
        audio, rate = wavio.read(path)
    except Exception as exc:
        raise ImportError(_short(exc)) from exc
    if audio.shape[0] == 0:
        raise ImportError("that file has no audio in it")
    if rate != samplerate:
        audio = wavio.resample(audio, rate, samplerate)
    return np.ascontiguousarray(audio, dtype=np.float32), info


def make_sample(project, path: str | Path, slot: int):
    """Build the :class:`~push2sampler.project.Sample` an import would install.

    Separate from installing it so the undo command can hold the result and put
    back exactly the same object on redo.
    """
    from .project import Sample

    audio, info = load(path, project.samplerate)
    bars, _exact = bars_for(
        audio.shape[0], project.bpm, project.samplerate, project.beats_per_bar
    )
    return Sample(
        slot=slot,
        bars=bars,
        audio=audio,
        name=Path(path).stem[:16],
        # The tempo it is *claimed* at, so the off-grid check compares the audio
        # against this session rather than against a tempo it never had.
        source_bpm=project.bpm,
        source_samplerate=project.samplerate,
    )
