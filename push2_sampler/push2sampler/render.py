"""Bounce the song to audio, offline and faster than real time.

Nothing else in the program leaves the box: this is how a finished song becomes
a file you can listen to elsewhere, and how stems get exported.

A bounce runs on a throwaway :class:`~push2sampler.audio.Engine` in ``offline``
mode, so it never touches the live one -- you can keep working while it renders.
:class:`BounceJob` renders a chunk at a time and is stepped by the UI loop, which
keeps the surface responsive without threads or locks: rendering is numpy, so a
two-minute song takes a second or two spread over a handful of frames.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from . import wavio
from .audio import Engine

#: Audio rendered per step, in seconds of song.
CHUNK_SECONDS = 2.0
#: How long to keep rendering past the last bar for tails to finish.
MAX_TAIL_SECONDS = 20.0


def _engine_for(project) -> Engine:
    return Engine(
        samplerate=project.samplerate,
        blocksize=1024,
        in_channels=1,
        out_channels=2,
        backend="offline",
        bpm=project.bpm,
        beats_per_bar=project.beats_per_bar,
        song_bars=project.song_bars,
        monitor="off",
    )


class BounceJob:
    """One render, advanced by :meth:`step` until :attr:`done`."""

    def __init__(self, project, bars: int | None = None, tail: bool = True,
                 only_slot: int | None = None) -> None:
        self.project = project
        self.bars = project.song_bars if bars is None else max(1, bars)
        self.tail = tail
        self.only_slot = only_slot
        self.done = False

        self._engine = _engine_for(project)
        self._engine.loop = False
        self._engine.set_schedule(self._schedule())
        self._engine.play(0)
        self._chunk = max(1, int(CHUNK_SECONDS * project.samplerate))
        self._body_frames = int(round(self.bars * project.frames_per_bar))
        self._max_frames = self._body_frames + (
            int(MAX_TAIL_SECONDS * project.samplerate) if tail else 0
        )
        self._parts: list[np.ndarray] = []
        self._rendered = 0

    def _schedule(self):
        """The project's schedule, or just one slot's when exporting a stem."""
        if self.only_slot is None:
            return self.project.build_schedule()
        return [
            tuple(entry for entry in bar if entry.slot == self.only_slot)
            for bar in self.project.build_schedule()
        ]

    @property
    def progress(self) -> float:
        if self.done:
            return 1.0
        return min(1.0, self._rendered / max(1, self._body_frames))

    def step(self) -> bool:
        """Render one chunk.  Returns True while there is more to do."""
        if self.done:
            return False
        frames = min(self._chunk, self._max_frames - self._rendered)
        if frames <= 0:
            self.done = True
            return False
        self._parts.append(self._engine.process_offline(frames))
        self._rendered += frames
        if self._rendered >= self._body_frames:
            # Past the last bar: stop as soon as nothing is still sounding.
            if not self.tail or not self._engine._voices:
                self.done = True
                return False
        return True

    def run(self) -> np.ndarray:
        """Render the whole thing in one go, for the command line."""
        while self.step():
            pass
        return self.result()

    def result(self) -> np.ndarray:
        if not self._parts:
            return np.zeros((0, 2), dtype=np.float32)
        return np.concatenate(self._parts, axis=0)


def render_song(project, bars: int | None = None, tail: bool = True) -> np.ndarray:
    return BounceJob(project, bars=bars, tail=tail).run()


def render_stems(project, bars: int | None = None) -> dict[int, np.ndarray]:
    """One render per filled slot, mixed at that slot's own triggers."""
    return {
        sample.slot: BounceJob(project, bars=bars, only_slot=sample.slot).run()
        for sample in project.filled()
    }


def bounce_to(project, path: str | Path, bars: int | None = None) -> Path:
    path = Path(path)
    wavio.write(path, render_song(project, bars=bars), project.samplerate)
    return path


def stems_to(project, directory: str | Path, bars: int | None = None) -> list[Path]:
    directory = Path(directory)
    written = []
    for slot, audio in render_stems(project, bars=bars).items():
        sample = project[slot]
        name = f"slot_{slot:02d}_{sample.name}.wav".replace(" ", "_")
        path = directory / name
        wavio.write(path, audio, project.samplerate)
        written.append(path)
    return written


def default_bounce_path(project_dir: str | Path) -> Path:
    """``<project>/bounces/<timestamp>.wav``, which is what the device uses."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(project_dir) / "bounces" / f"{stamp}.wav"
