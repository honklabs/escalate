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

import math
import time
from pathlib import Path

import numpy as np

from . import wavio
from .audio import Engine
from .project import TAKE_CYCLE

#: Audio rendered per step, in seconds of song.
CHUNK_SECONDS = 2.0
#: How long to keep rendering past the last bar for tails to finish.
MAX_TAIL_SECONDS = 20.0
#: Most passes a bounce will cover for `every_n` (NH-10).  Eight passes of a
#: 64-bar song is over half an hour; past that the render is the surprise.
MAX_PASSES = 8


def passes_needed(project) -> int:
    """How many passes a bounce must cover for `every_n` to be heard (NH-10).

    A linear render never loops, so without this a bounce is pass 1 for ever
    and a sample set to "every 2nd pass" is **absent from the file** -- which
    is what happened before this existed, and is the worst kind of bug: you
    hear the arrangement, you bounce it, and part of it is gone.

    The answer is the least common multiple of the pass divisors in use, so a
    song that genuinely varies over four passes bounces as four passes.  One
    when nothing uses the feature, which is every project that has not asked
    for it.

    A slot **cycling** its alternates (IN-06), and a slot with a **variation
    rule** (IN-05), are pass divisors too: three takes
    on `cycle` mean the song does not repeat until pass three, and bouncing one
    pass would put take 1 in the file and silently discard the other two.  Same
    bug as `every_n`'s, arriving by a different door.  `random` is not a
    divisor: it never repeats, so there is no cycle to cover, and one pass of it
    is as representative as any other.
    """
    divisors = {
        max(1, int(sample.every_n or 1))
        for sample in project.filled()
        if project.audible(sample) and sample.triggers
    }
    divisors |= {
        sample.take_count
        for sample in project.filled()
        if project.audible(sample) and sample.triggers
        and sample.take_mode == TAKE_CYCLE
    }
    # And so is a variation rule (IN-05): "every 4th pass, double the hats"
    # means the song does not repeat until pass four, so a shorter bounce would
    # not contain the fill at all.  Third door onto the same bug.
    divisors |= {
        max(1, int(sample.variation_every or 1))
        for sample in project.filled()
        if project.audible(sample) and sample.variation_bars
        and (sample.variation_every or 1) > 1
    }
    total = 1
    for divisor in sorted(divisors):
        total = total * divisor // math.gcd(total, divisor)
        if total >= MAX_PASSES:
            return MAX_PASSES
    return max(1, total)


def _engine_for(project, song_bars: int | None = None) -> Engine:
    return Engine(
        samplerate=project.samplerate,
        blocksize=1024,
        in_channels=1,
        out_channels=2,
        backend="offline",
        bpm=project.bpm,
        beats_per_bar=project.beats_per_bar,
        song_bars=song_bars or project.song_bars,
        monitor="off",
    )


class BounceJob:
    """One render, advanced by :meth:`step` until :attr:`done`."""

    def __init__(self, project, bars: int | None = None, tail: bool = True,
                 only_slot: int | None = None, passes: int | None = None) -> None:
        self.project = project
        # Render to the last bar in use, not to the nominal song length: four
        # pages are available and most songs use one.
        self.pass_bars = max(1, project.used_bars) if bars is None else max(1, bars)
        #: Passes covered.  Derived so `every_n` is actually heard (see
        #: `passes_needed`), or asked for outright by `IN-05`'s freeze -- which
        #: is a different question: `passes_needed` answers "how long before the
        #: song repeats", and a freeze answers "give me four times round".
        self.passes = passes_needed(project) if passes is None else max(1, int(passes))
        self.bars = self.pass_bars * self.passes
        self.tail = tail
        self.only_slot = only_slot
        self.done = False

        self._engine = _engine_for(project, song_bars=self.bars)
        self._engine.loop = False
        # The pass a bar belongs to is worked out from this, since a linear
        # render never wraps for a counter to notice.
        self._engine.pass_bars = self.pass_bars
        self._engine.chance_seed = project.chance_seed
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
        """The project's schedule, or just one slot's when exporting a stem.

        A full bounce drops anything **routed to a cue pair** (NH-11): a bounce
        is what comes out of the main outputs, and a cue pair is by definition
        not that -- it is the click, or the part you are auditioning to
        yourself.  Letting the engine's fallback carry it into the mix instead
        would put it in the file with no way to tell.

        A *stem* keeps it: a stem is one slot's own audio rather than a mix
        bus, so where that slot is routed is beside the point.
        """
        schedule = self.project.build_schedule()
        if self.only_slot is not None:
            return self._repeat([
                tuple(entry for entry in bar if entry.slot == self.only_slot)
                for bar in schedule
            ])
        filtered = [
            tuple(entry for entry in bar if entry.channel is None)
            for bar in schedule
        ]
        return self._repeat(filtered)

    def _repeat(self, schedule):
        """Lay the pass out `self.passes` times, to the engine's full length.

        The project's schedule is one song long; a multi-pass render needs a
        bar for every bar it will play, or the later passes would be silent for
        want of entries rather than for want of dice.
        """
        out = []
        for index in range(self.bars):
            source = index % self.pass_bars
            out.append(schedule[source] if source < len(schedule) else ())
        return out

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
        name = f"slot_{slot:03d}_{sample.name}.wav".replace(" ", "_")
        path = directory / name
        wavio.write(path, audio, project.samplerate)
        written.append(path)
    return written


def default_bounce_path(project_dir: str | Path) -> Path:
    """``<project>/bounces/<timestamp>.wav``, which is what the device uses."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(project_dir) / "bounces" / f"{stamp}.wav"
