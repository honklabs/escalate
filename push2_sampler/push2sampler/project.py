"""The song: 64 sample slots, each with its own trigger map over 64 bars.

A project is a directory::

    my-song/
      project.json
      samples/slot_00.wav
      samples/slot_07.wav

``project.json`` holds the tempo and, per filled slot, the take length in bars,
the bars it is triggered on, whether it is audible, and its gain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import wavio
from .constants import PAD_COUNT

SONG_BARS = 64
#: A take may be this far from its declared length before it is flagged.
LENGTH_TOLERANCE = 0.01
PROJECT_FILE = "project.json"
SAMPLES_DIR = "samples"
FORMAT_VERSION = 2


@dataclass
class Sample:
    """One recorded take, assigned to one of the 64 library slots."""

    slot: int
    bars: int
    audio: np.ndarray
    triggers: set[int] = field(default_factory=set)
    enabled: bool = True
    gain: float = 1.0
    name: str = ""
    #: Tempo and rate this take was captured at; 0 means "unknown" (v1 projects).
    source_bpm: float = 0.0
    source_samplerate: int = 0
    #: True once this take's audio is on disk, so autosave can skip rewriting it.
    audio_saved: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"S{self.slot + 1:02d}"

    @property
    def frames(self) -> int:
        return int(self.audio.shape[0])

    def set_trigger(self, bar: int, on: bool) -> None:
        """Enable or disable playback on ``bar``."""
        if not 0 <= bar < SONG_BARS:
            raise ValueError(f"bar out of range: {bar}")
        if on:
            self.triggers.add(bar)
        else:
            self.triggers.discard(bar)

    def toggle(self, bar: int) -> bool:
        """Toggle playback on ``bar``; returns the new state."""
        on = bar not in self.triggers
        self.set_trigger(bar, on)
        return on

    def bars_at(self, bpm: float, samplerate: int, beats_per_bar: int = 4) -> float:
        """How many bars this take's audio fills at the given tempo.

        Fractional by design: 2.0 means it fits exactly, 2.3 means it does not.
        """
        frames_per_bar = 60.0 / bpm * samplerate * beats_per_bar
        if frames_per_bar <= 0:
            return float(self.bars)
        return self.frames / frames_per_bar

    def to_json(self, audio_path: str) -> dict:
        return {
            "slot": self.slot,
            "name": self.name,
            "bars": self.bars,
            "triggers": sorted(self.triggers),
            "enabled": self.enabled,
            "gain": round(float(self.gain), 4),
            "source_bpm": round(float(self.source_bpm), 3),
            "source_samplerate": int(self.source_samplerate),
            "audio": audio_path,
        }


class Project:
    """Tempo plus the 64-slot sample library."""

    def __init__(self, samplerate: int = 48_000, bpm: float = 120.0,
                 beats_per_bar: int = 4) -> None:
        self.samplerate = samplerate
        self.bpm = float(bpm)
        self.beats_per_bar = beats_per_bar
        self.song_bars = SONG_BARS
        self.slots: list[Sample | None] = [None] * PAD_COUNT
        self.dirty = False

    # ------------------------------------------------------------------
    @property
    def frames_per_bar(self) -> float:
        return 60.0 / self.bpm * self.samplerate * self.beats_per_bar

    def expected_frames(self, bars: int) -> int:
        """How long a take of ``bars`` bars must be at the project's tempo."""
        return int(round(bars * self.frames_per_bar))

    def length_error(self, sample: Sample) -> float:
        """Relative length error of a take: +0.1 means 10% too long."""
        expected = self.expected_frames(sample.bars)
        if expected <= 0:
            return 0.0
        return (sample.frames - expected) / expected

    def mismatched(self, sample: Sample, tolerance: float = LENGTH_TOLERANCE) -> bool:
        """True when this take no longer fills its bars at the current tempo.

        It happens when a project recorded at one tempo is opened at another, or
        when audio that was never bar-aligned is imported.  The take is kept as
        it is -- playback would drift, so the UI flags it and offers a repair.
        """
        return abs(self.length_error(sample)) > tolerance

    def mismatched_slots(self) -> list[int]:
        return [s.slot for s in self.filled() if self.mismatched(s)]

    def fitted_audio(self, sample: Sample) -> np.ndarray:
        """``sample``'s audio padded with silence or trimmed to exactly its bars."""
        target = self.expected_frames(sample.bars)
        audio = sample.audio
        if audio.shape[0] == target:
            return audio
        fitted = np.zeros((target, audio.shape[1]), dtype=np.float32)
        keep = min(target, audio.shape[0])
        fitted[:keep] = audio[:keep]
        return fitted

    def repair(self, slot: int) -> bool:
        """Make one take exactly its declared length.  True if it changed."""
        sample = self.slots[slot]
        if sample is None or not self.mismatched(sample):
            return False
        sample.audio = self.fitted_audio(sample)
        sample.source_bpm = self.bpm
        sample.source_samplerate = self.samplerate
        sample.audio_saved = False
        self.dirty = True
        return True

    def __getitem__(self, slot: int) -> Sample | None:
        return self.slots[slot]

    def filled(self) -> list[Sample]:
        return [s for s in self.slots if s is not None]

    def first_empty(self) -> int | None:
        for i, s in enumerate(self.slots):
            if s is None:
                return i
        return None

    def put(self, slot: int, audio: np.ndarray, bars: int,
            triggers: set[int] | None = None) -> Sample:
        """Install a take in ``slot``, keeping trigger/mute state on re-record."""
        existing = self.slots[slot]
        sample = Sample(
            slot=slot,
            bars=bars,
            audio=np.ascontiguousarray(audio, dtype=np.float32),
            triggers=set(triggers) if triggers is not None
            else (set(existing.triggers) if existing else set()),
            enabled=existing.enabled if existing else True,
            gain=existing.gain if existing else 1.0,
            name=existing.name if existing else "",
            source_bpm=self.bpm,
            source_samplerate=self.samplerate,
        )
        self.slots[slot] = sample
        self.dirty = True
        return sample

    def install(self, slot: int, sample: Sample | None) -> None:
        """Put a sample (or ``None``) straight into a slot.

        Used by undo, which has to restore exactly the take it removed rather
        than build a new one.
        """
        self.slots[slot] = sample
        self.dirty = True

    def delete(self, slot: int) -> None:
        if self.slots[slot] is not None:
            self.slots[slot] = None
            self.dirty = True

    def bars_in_use(self) -> set[int]:
        """Every bar on which some audible sample is triggered."""
        used: set[int] = set()
        for sample in self.filled():
            if sample.enabled:
                used |= sample.triggers
        return used

    def build_schedule(self):
        """bar -> tuple of :class:`~push2sampler.audio.ScheduledSample`."""
        from .audio import ScheduledSample

        schedule: list[list[ScheduledSample]] = [[] for _ in range(self.song_bars)]
        for sample in self.filled():
            if not sample.enabled or sample.frames == 0:
                continue
            for bar in sorted(sample.triggers):
                if 0 <= bar < self.song_bars:
                    schedule[bar].append(
                        ScheduledSample(sample.slot, sample.audio, sample.gain)
                    )
        return [tuple(entries) for entries in schedule]

    # ------------------------------------------------------------------
    def save(self, directory: str | Path) -> Path:
        directory = Path(directory)
        (directory / SAMPLES_DIR).mkdir(parents=True, exist_ok=True)
        slots = []
        for sample in self.filled():
            rel = f"{SAMPLES_DIR}/slot_{sample.slot:02d}.wav"
            # Audio never changes in place, so only write takes we haven't yet.
            if not sample.audio_saved or not (directory / rel).exists():
                wavio.write(directory / rel, sample.audio, self.samplerate)
                sample.audio_saved = True
            slots.append(sample.to_json(rel))
        payload = {
            "version": FORMAT_VERSION,
            "samplerate": self.samplerate,
            "bpm": round(self.bpm, 3),
            "beats_per_bar": self.beats_per_bar,
            "song_bars": self.song_bars,
            "slots": slots,
        }
        path = directory / PROJECT_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(path)
        self.dirty = False
        return path

    @classmethod
    def load(cls, directory: str | Path, samplerate: int | None = None) -> "Project":
        directory = Path(directory)
        path = directory / PROJECT_FILE
        if not path.exists():
            return cls(samplerate=samplerate or 48_000)
        payload = json.loads(path.read_text())
        project = cls(
            samplerate=samplerate or int(payload.get("samplerate", 48_000)),
            bpm=float(payload.get("bpm", 120.0)),
            beats_per_bar=int(payload.get("beats_per_bar", 4)),
        )
        project.song_bars = int(payload.get("song_bars", SONG_BARS))
        for entry in payload.get("slots", []):
            audio_rel = entry.get("audio")
            if not audio_rel or not (directory / audio_rel).exists():
                continue
            audio, rate = wavio.read(directory / audio_rel)
            if rate != project.samplerate:
                audio = wavio.resample(audio, rate, project.samplerate)
            slot = int(entry["slot"])
            # Format 1 stored no provenance.  Assume such a take was recorded at
            # this project's own tempo -- the best guess available, and the one
            # that does not flag every existing project as mismatched.
            source_bpm = float(entry.get("source_bpm") or project.bpm)
            source_rate = int(entry.get("source_samplerate") or project.samplerate)
            project.slots[slot] = Sample(
                slot=slot,
                bars=int(entry.get("bars", 1)),
                audio=audio,
                triggers={int(b) for b in entry.get("triggers", [])},
                enabled=bool(entry.get("enabled", True)),
                gain=float(entry.get("gain", 1.0)),
                name=str(entry.get("name", "")),
                source_bpm=source_bpm,
                source_samplerate=source_rate,
                audio_saved=True,
            )
        project.dirty = False
        return project
