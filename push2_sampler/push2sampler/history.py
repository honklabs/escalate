"""Undo/redo.

Every edit to a project goes through :meth:`History.do` as a small reversible
command, so `Undo` can take it back: a deleted take keeps its audio, a cleared
arrangement keeps its bars, a tempo nudge keeps the old tempo.

Commands that arrive in a stream -- gain and tempo come from encoders, one step
per click -- coalesce into the entry already on top of the stack while it is
recent, so one sweep of an encoder is one undo step rather than forty.

The journal lives in memory only: it is a safety net for the hands, not project
history, and it is not written to disk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

#: How many edits can be taken back.
DEPTH = 64
#: Window in which a repeated encoder edit folds into the previous one.
MERGE_WINDOW_S = 1.5


class Command:
    """One reversible edit.  ``apply`` must be safe to call again for redo."""

    #: Shown by the UI when the command is done or undone.
    label = "edit"

    def apply(self, project) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def revert(self, project) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def merge(self, newer: "Command") -> bool:
        """Fold ``newer`` into this command; return False to keep them apart."""
        return False


@dataclass
class ToggleTrigger(Command):
    """Turn one bar of one sample on or off."""

    slot: int
    bar: int
    on: bool

    @property
    def label(self) -> str:
        return f"bar {self.bar + 1} {'on' if self.on else 'off'}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.set_trigger(self.bar, self.on)

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.set_trigger(self.bar, not self.on)


@dataclass
class ClearTriggers(Command):
    """Clear every bar of one sample, remembering them all."""

    slot: int
    _previous: set[int] = field(default_factory=set)

    label = "cleared all bars"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous = set(sample.triggers)
        sample.triggers.clear()

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.triggers = set(self._previous)


@dataclass
class ClearBar(Command):
    """Remove one bar from every sample, for erase-while-looping."""

    bar: int
    _removed: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"erased bar {self.bar + 1}"

    def apply(self, project) -> None:
        self._removed = [
            sample.slot for sample in project.filled() if self.bar in sample.triggers
        ]
        for slot in self._removed:
            project[slot].set_trigger(self.bar, False)

    def revert(self, project) -> None:
        for slot in self._removed:
            sample = project[slot]
            if sample is not None:
                sample.set_trigger(self.bar, True)


@dataclass
class SetEnabled(Command):
    """Mute or unmute one sample."""

    slot: int
    enabled: bool

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1} {'on' if self.enabled else 'muted'}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.enabled = self.enabled

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.enabled = not self.enabled


@dataclass
class SetGain(Command):
    """Change one sample's gain; consecutive encoder steps coalesce."""

    slot: int
    gain: float
    previous: float
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        return f"gain {self.gain:.2f}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.gain = self.gain

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.gain = self.previous

    def merge(self, newer: Command) -> bool:
        if not isinstance(newer, SetGain) or newer.slot != self.slot:
            return False
        if newer.at - self.at > MERGE_WINDOW_S:
            return False
        self.gain = newer.gain
        self.at = newer.at
        return True


@dataclass
class SetBpm(Command):
    """Change the tempo; consecutive encoder steps coalesce."""

    bpm: float
    previous: float
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        return f"{self.bpm:.0f} BPM"

    def apply(self, project) -> None:
        project.bpm = self.bpm

    def revert(self, project) -> None:
        project.bpm = self.previous

    def merge(self, newer: Command) -> bool:
        if not isinstance(newer, SetBpm) or newer.at - self.at > MERGE_WINDOW_S:
            return False
        self.bpm = newer.bpm
        self.at = newer.at
        return True


@dataclass
class PutSample(Command):
    """Install a take in a slot, keeping whatever it replaced for undo."""

    slot: int
    audio: np.ndarray
    bars: int
    _previous: object = None
    _installed: object = None

    @property
    def label(self) -> str:
        return f"recorded {self.bars} bar(s) into slot {self.slot + 1}"

    def apply(self, project) -> None:
        self._previous = project[self.slot]
        if self._installed is None:
            # put() carries the slot's arrangement, mute and gain across.
            self._installed = project.put(self.slot, self.audio, self.bars)
        else:
            project.install(self.slot, self._installed)

    def revert(self, project) -> None:
        project.install(self.slot, self._previous)


@dataclass
class RepairLength(Command):
    """Pad or trim a take so it exactly fills its bars at the current tempo."""

    slot: int
    _previous_audio: object = None
    _previous_source: tuple = ()

    label = "repaired length"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous_audio = sample.audio
        self._previous_source = (sample.source_bpm, sample.source_samplerate)
        project.repair(self.slot)

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None or self._previous_audio is None:
            return
        sample.audio = self._previous_audio
        sample.source_bpm, sample.source_samplerate = self._previous_source
        # The WAV on disk is the repaired one, so it has to be written again.
        sample.audio_saved = False


@dataclass
class DeleteSample(Command):
    """Empty a slot, keeping the take itself so undo can put it back."""

    slot: int
    _previous: object = None

    @property
    def label(self) -> str:
        return f"deleted slot {self.slot + 1}"

    def apply(self, project) -> None:
        self._previous = project[self.slot]
        project.install(self.slot, None)

    def revert(self, project) -> None:
        project.install(self.slot, self._previous)


class History:
    """A bounded undo/redo stack over one project."""

    def __init__(self, depth: int = DEPTH) -> None:
        self.depth = depth
        self._done: list[Command] = []
        self._undone: list[Command] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()

    def do(self, project, command: Command) -> str:
        """Apply ``command`` and record it.  Returns the label to show."""
        command.apply(project)
        project.dirty = True
        self._undone.clear()
        if self._done and self._done[-1].merge(command):
            return self._done[-1].label
        self._done.append(command)
        if len(self._done) > self.depth:
            del self._done[0]
        return command.label

    def undo(self, project) -> str | None:
        if not self._done:
            return None
        command = self._done.pop()
        command.revert(project)
        project.dirty = True
        self._undone.append(command)
        return command.label

    def redo(self, project) -> str | None:
        if not self._undone:
            return None
        command = self._undone.pop()
        command.apply(project)
        project.dirty = True
        self._done.append(command)
        return command.label
