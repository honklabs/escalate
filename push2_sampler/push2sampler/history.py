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

from .constants import PLAY_MODE_LABELS, pair_label
from .project import format_bpm

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
    """Turn one bar of one sample on or off, optionally with a velocity."""

    slot: int
    bar: int
    on: bool
    velocity: int | None = None
    _previous_velocity: int | None = None
    _was_on: bool = False

    @property
    def label(self) -> str:
        return f"bar {self.bar + 1} {'on' if self.on else 'off'}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._was_on = self.bar in sample.triggers
        self._previous_velocity = sample.velocities.get(self.bar)
        sample.set_trigger(self.bar, self.on, self.velocity)

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        sample.set_trigger(self.bar, self._was_on, self._previous_velocity)


@dataclass
class SetBars(Command):
    """Set many bars of one sample at once, as one undo step.

    Every gesture that writes a block of bars -- painting a range, filling a
    phrase, duplicating a block -- is this command with a different set of
    changes and its own wording, so the restore path is written once.

    ``changes`` maps a bar to the velocity it should play at, or to ``None`` to
    turn that bar off.
    """

    slot: int
    changes: dict
    display: str = "bars changed"
    _previous: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.display

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        # Snapshot before touching anything: (was it on, at what velocity).
        self._previous = {
            bar: (bar in sample.triggers, sample.velocities.get(bar))
            for bar in self.changes
        }
        for bar, velocity in self.changes.items():
            sample.set_trigger(bar, velocity is not None, velocity)

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        for bar, (was_on, velocity) in self._previous.items():
            sample.set_trigger(bar, was_on, velocity)


@dataclass
class RecallScene(Command):
    """Swap the whole arrangement for a stored snapshot.

    The snapshot covers what is audible and where each take plays -- not the
    audio, gain, edits or layers, which belong to the *take* rather than to the
    arrangement.  Undo puts back a snapshot of the state it replaced, so an A/B
    comparison can always be walked back.
    """

    index: int
    _previous: object = None

    @property
    def label(self) -> str:
        return f"scene {self.index + 1}"

    def apply(self, project) -> None:
        if self._previous is None:
            self._previous = project.snapshot()
        project.recall_scene(self.index)

    def revert(self, project) -> None:
        if self._previous is not None:
            project.restore(self._previous)


@dataclass
class StoreScene(Command):
    """Keep the arrangement as it stands in one of the eight scene slots."""

    index: int
    _previous: object = None

    @property
    def label(self) -> str:
        return f"stored scene {self.index + 1}"

    def apply(self, project) -> None:
        self._previous = project.scenes[self.index]
        project.store_scene(self.index)

    def revert(self, project) -> None:
        project.scenes[self.index] = self._previous
        project.dirty = True


@dataclass
class CopySlot(Command):
    """Copy (or move) a whole sample into another slot.

    The copy shares the original's audio array rather than duplicating it:
    nothing in this program mutates a take's samples in place -- an edit builds a
    new array -- so the two slots are independent the moment either is edited.
    """

    src: int
    dst: int
    move: bool = False
    _previous_dst: object = None
    _previous_src: object = None
    _installed: object = None

    @property
    def label(self) -> str:
        verb = "moved" if self.move else "copied"
        return f"{verb} slot {self.src + 1} to {self.dst + 1}"

    def apply(self, project) -> None:
        self._previous_dst = project[self.dst]
        self._previous_src = project[self.src]
        if self._previous_src is None:
            return
        if self._installed is None:
            self._installed = project.copy_slot(self.src, self.dst)
        else:  # redo: put back the very sample we made the first time
            project.install(self.dst, self._installed)
        if self.move:
            project.install(self.src, None)

    def revert(self, project) -> None:
        project.install(self.dst, self._previous_dst)
        if self.move:
            project.install(self.src, self._previous_src)


@dataclass
class SwapSlots(Command):
    """Exchange two slots' contents (CC-19).

    The rare command whose ``revert`` is its own ``apply``: swapping the same
    pair again puts everything back.  Spelled out rather than left to look like
    a copy-paste slip.
    """

    a: int
    b: int

    @property
    def label(self) -> str:
        return f"swapped slots {self.a + 1} and {self.b + 1}"

    def apply(self, project) -> None:
        project.swap_slots(self.a, self.b)

    def revert(self, project) -> None:
        project.swap_slots(self.a, self.b)


@dataclass
class ClearTriggers(Command):
    """Clear every bar of one sample, remembering them all."""

    slot: int
    _previous: set[int] = field(default_factory=set)
    _previous_velocities: dict = field(default_factory=dict)

    label = "cleared all bars"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous = set(sample.triggers)
        self._previous_velocities = dict(sample.velocities)
        sample.triggers.clear()
        sample.velocities.clear()

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.triggers = set(self._previous)
            sample.velocities = dict(self._previous_velocities)


@dataclass
class ClearBar(Command):
    """Remove one bar from every sample, for erase-while-looping."""

    bar: int
    #: (slot, velocity) for every sample that played on this bar.
    _removed: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"erased bar {self.bar + 1}"

    def apply(self, project) -> None:
        self._removed = [
            (sample.slot, sample.velocities.get(self.bar))
            for sample in project.filled()
            if self.bar in sample.triggers
        ]
        for slot, _ in self._removed:
            project[slot].set_trigger(self.bar, False)

    def revert(self, project) -> None:
        for slot, velocity in self._removed:
            sample = project[slot]
            if sample is not None:
                sample.set_trigger(self.bar, True, velocity)


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
class ImportSample(Command):
    """Put a file from disk into a slot (NF-08).

    The built sample is held rather than rebuilt, so redo installs the very
    object the first import made -- re-reading the file would be slower and,
    if it had been moved meanwhile, would fail in the middle of a redo.
    """

    slot: int
    sample: object
    source: str = ""
    _previous: object = None

    @property
    def label(self) -> str:
        name = getattr(self.sample, "name", "") or "file"
        return f"imported {name} to slot {self.slot + 1}"

    def apply(self, project) -> None:
        self._previous = project[self.slot]
        project.install(self.slot, self.sample)

    def revert(self, project) -> None:
        project.install(self.slot, self._previous)


@dataclass
class SetProbability(Command):
    """How likely one bar of one sample is to play (NH-10).

    Encoder steps coalesce, like gain and the nudge.  100 is stored as *absent*
    so an ordinary project carries no probability data at all -- which is why
    the revert writes through `set_trigger` rather than the dict.
    """

    slot: int
    bar: int
    chance: int
    previous: int
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        if self.chance >= 100:
            return f"bar {self.bar + 1} always plays"
        return f"bar {self.bar + 1} {self.chance}% chance"

    def _write(self, project, chance: int) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        if chance >= 100:
            sample.probabilities.pop(self.bar, None)
        else:
            sample.probabilities[self.bar] = max(1, min(99, int(chance)))
        project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.chance)

    def revert(self, project) -> None:
        self._write(project, self.previous)

    def merge(self, newer: Command) -> bool:
        if (not isinstance(newer, SetProbability) or newer.slot != self.slot
                or newer.bar != self.bar
                or newer.at - self.at > MERGE_WINDOW_S):
            return False
        self.chance = newer.chance
        self.at = newer.at
        return True


@dataclass
class SetEveryN(Command):
    """Play a sample only on every Nth pass of the loop (NH-10)."""

    slot: int
    every_n: int
    previous: int

    @property
    def label(self) -> str:
        if self.every_n <= 1:
            return f"slot {self.slot + 1} every pass"
        return f"slot {self.slot + 1} every {self.every_n} passes"

    def _write(self, project, value: int) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.every_n = int(value)
            project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.every_n)

    def revert(self, project) -> None:
        self._write(project, self.previous)


@dataclass
class SetChanceSeed(Command):
    """Reroll the project's dice (NH-10).

    Without this the seed is 0 for ever and a probabilistic arrangement has
    exactly one variation -- which is half a feature: "makes a short
    arrangement feel long" needs "not that one, another one" as well.
    """

    seed: int
    previous: int

    @property
    def label(self) -> str:
        return f"dice {self.seed}"

    def apply(self, project) -> None:
        project.chance_seed = int(self.seed)
        project.dirty = True

    def revert(self, project) -> None:
        project.chance_seed = int(self.previous)
        project.dirty = True


@dataclass
class AddTake(Command):
    """Keep a new recording beside the slot's existing one (IN-06).

    Stores the alternates as they were rather than "the last one added", so
    undo is exact even after the slot has been re-selected or overdubbed.
    """

    slot: int
    audio: np.ndarray
    _previous: object = None
    _previous_active: int = 0
    _previous_layers: object = None
    _previous_audio: object = None
    _added: bool = False

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1}: take added"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous = list(sample.takes)
        self._previous_active = sample.active_take
        self._previous_layers = list(sample.layers)
        self._previous_audio = sample.audio
        self._added = sample.add_take(self.audio)

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None or not self._added:
            return
        sample.set_takes(list(self._previous or []), self._previous_active)
        if not self._previous:
            # The slot had no alternates at all, so put back the audio and the
            # layer breakdown `add_take` flattened.
            sample.audio = self._previous_audio
            sample.layers = list(self._previous_layers or [])
            sample.audio_saved = False
            sample.set_edits(sample.edits)  # drops the render cache


@dataclass
class RemoveTake(Command):
    """Drop the selected alternate, keeping it for undo (IN-06)."""

    slot: int
    _previous: object = None
    _previous_active: int = 0
    _removed: bool = False

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1}: take removed"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous = list(sample.takes)
        self._previous_active = sample.active_take
        self._removed = sample.remove_take()

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None or not self._removed:
            return
        sample.set_takes(list(self._previous or []), self._previous_active)


@dataclass
class SetActiveTake(Command):
    """Select which alternate a `fixed` slot plays (IN-06)."""

    slot: int
    index: int
    previous: int
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1}: take {self.index + 1}"

    def merge(self, other: "Command") -> bool:
        # An encoder sweep through the alternates is one decision, like gain.
        if not isinstance(other, SetActiveTake) or other.slot != self.slot:
            return False
        if other.at - self.at > MERGE_WINDOW_S:
            return False
        self.index, self.at = other.index, other.at
        return True

    def _write(self, project, value: int) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.set_active_take(value)
            project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.index)

    def revert(self, project) -> None:
        self._write(project, self.previous)


@dataclass
class SetTakeMode(Command):
    """How a trigger chooses among the alternates (IN-06)."""

    slot: int
    mode: str
    previous: str

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1}: takes {self.mode}"

    def _write(self, project, value: str) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.take_mode = value
            project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.mode)

    def revert(self, project) -> None:
        self._write(project, self.previous)


@dataclass
class SetVariation(Command):
    """The bars a sample plays only on some passes, and how often (IN-05)."""

    slot: int
    bars: set
    every: int
    previous_bars: set
    previous_every: int

    @property
    def label(self) -> str:
        if not self.bars or (self.every or 1) <= 1:
            return f"slot {self.slot + 1}: no variation"
        return (f"slot {self.slot + 1}: {len(self.bars)} extra bar(s) "
                f"every {self.every} passes")

    def _write(self, project, bars, every) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.variation_bars = set(bars)
            sample.variation_every = int(every)
            project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.bars, self.every)

    def revert(self, project) -> None:
        self._write(project, self.previous_bars, self.previous_every)


@dataclass
class SetStretchMode(Command):
    """How a take answers a tempo it was not recorded at (NH-09)."""

    slot: int
    mode: str
    previous: str

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1}: tempo {self.mode}"

    def _write(self, project, value: str) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.stretch_mode = value
            project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.mode)

    def revert(self, project) -> None:
        self._write(project, self.previous)


@dataclass
class SliceTake(Command):
    """Write several slices into several slots at once (IN-01).

    One command for the whole conversion, because "slice this take into a kit"
    is one decision: undoing it a pad at a time would be sixteen presses to
    take back one.  It holds the built samples rather than re-slicing, for the
    reason ``ImportSample`` does -- redo must install the very objects the
    first commit made, not recompute them from a take that may since have been
    edited.

    ``replaced`` is the source slot when the original was consumed, and None
    when it was kept.  Reverting restores whatever each destination held,
    including the source, so a slice that overwrote something is fully
    reversible.
    """

    samples: list           # the Sample objects, in destination order
    slots: list             # the destination slot numbers, same order
    source: int = -1
    replaced: bool = False
    _previous: list = field(default_factory=list)
    _source_before: object = None

    @property
    def label(self) -> str:
        count = len(self.slots)
        where = f"slot{'s' if count != 1 else ''} "
        where += ", ".join(str(s + 1) for s in self.slots[:3])
        if count > 3:
            where += f" +{count - 3}"
        return f"sliced into {where}"

    def apply(self, project) -> None:
        self._previous = [project[slot] for slot in self.slots]
        self._source_before = project[self.source] if self.source >= 0 else None
        for slot, sample in zip(self.slots, self.samples):
            project.install(slot, sample)
        if self.replaced and self.source >= 0 and self.source not in self.slots:
            project.install(self.source, None)

    def revert(self, project) -> None:
        for slot, before in zip(self.slots, self._previous):
            project.install(slot, before)
        if self.replaced and self.source >= 0 and self.source not in self.slots:
            project.install(self.source, self._source_before)


@dataclass
class SetOutput(Command):
    """Send a slot to a different output pair (NH-11)."""

    slot: int
    output: int
    previous: int

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1} out {pair_label(self.output)}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.output = self.output

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.output = self.previous


@dataclass
class SetNudge(Command):
    """Lay a sample back behind the beat, or straighten it up (NH-02).

    Encoder steps coalesce the way gain and tempo do: turning a knob is one
    decision, not thirty.
    """

    slot: int
    nudge_ms: float
    previous: float
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        if not self.nudge_ms:
            return f"slot {self.slot + 1} on the beat"
        return f"slot {self.slot + 1} +{self.nudge_ms:.0f}ms"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.nudge_ms = self.nudge_ms

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.nudge_ms = self.previous

    def merge(self, newer: Command) -> bool:
        if (not isinstance(newer, SetNudge) or newer.slot != self.slot
                or newer.at - self.at > MERGE_WINDOW_S):
            return False
        self.nudge_ms = newer.nudge_ms
        self.at = newer.at
        return True


@dataclass
class SetSwing(Command):
    """Change the song's swing; consecutive encoder steps coalesce (NH-02)."""

    swing: float
    previous: float
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        return "straight" if not self.swing else f"swing {self.swing * 100:.0f}%"

    def apply(self, project) -> None:
        project.swing = self.swing

    def revert(self, project) -> None:
        project.swing = self.previous

    def merge(self, newer: Command) -> bool:
        if not isinstance(newer, SetSwing) or newer.at - self.at > MERGE_WINDOW_S:
            return False
        self.swing = newer.swing
        self.at = newer.at
        return True


@dataclass
class SetPlayMode(Command):
    """Change how a sample ends when it is triggered (NF-02)."""

    slot: int
    mode: str
    previous: str

    @property
    def label(self) -> str:
        return f"play mode {PLAY_MODE_LABELS.get(self.mode, self.mode)}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.play_mode = self.mode

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.play_mode = self.previous


@dataclass
class SetChokeGroup(Command):
    """Put a sample in a choke group, or take it out of one."""

    slot: int
    group: int | None
    previous: int | None

    @property
    def label(self) -> str:
        return f"choke {self.group}" if self.group else "choke off"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.choke_group = self.group

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.choke_group = self.previous


@dataclass
class SetVelocitySensitivity(Command):
    """Turn velocity response on or off for one sample."""

    slot: int
    sensitivity: float
    previous: float

    @property
    def label(self) -> str:
        return f"velocity {'on' if self.sensitivity > 0 else 'off'}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.velocity_sensitivity = self.sensitivity

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.velocity_sensitivity = self.previous


@dataclass
class SetName(Command):
    """Rename a slot, from the curated word list."""

    slot: int
    name: str
    previous: str

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1}: {self.name}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.name = self.name

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.name = self.previous


@dataclass
class SetColor(Command):
    """Tag a slot with one of the eight user colours, or clear the tag."""

    slot: int
    color: int | None
    previous: int | None

    @property
    def label(self) -> str:
        return f"slot {self.slot + 1} colour {'cleared' if self.color is None else self.color + 1}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.color = self.color

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.color = self.previous


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
class SetMasterGain(Command):
    """Change the gain on the whole mix; encoder steps coalesce."""

    gain: float
    previous: float
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        return f"master {self.gain:.2f}"

    def apply(self, project) -> None:
        project.master_gain = self.gain

    def revert(self, project) -> None:
        project.master_gain = self.previous

    def merge(self, newer: Command) -> bool:
        if not isinstance(newer, SetMasterGain) or newer.at - self.at > MERGE_WINDOW_S:
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
        return f"{format_bpm(self.bpm)} BPM"

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
class AddLayer(Command):
    """Sum another pass into an existing take, keeping the old sum for undo."""

    slot: int
    audio: np.ndarray
    _previous_layers: object = None
    _previous_audio: object = None

    @property
    def label(self) -> str:
        return f"layered slot {self.slot + 1}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous_layers = list(sample.layers)
        self._previous_audio = sample.audio
        sample.add_layer(self.audio)

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None or self._previous_audio is None:
            return
        sample.layers = list(self._previous_layers or [])
        sample.audio = self._previous_audio
        sample.audio_saved = False
        sample.set_edits(sample.edits)  # drops the render cache


@dataclass
class RemoveLayer(Command):
    """Peel the most recent layer off a take."""

    slot: int
    _previous_layers: object = None
    _previous_audio: object = None

    @property
    def label(self) -> str:
        return f"removed a layer from slot {self.slot + 1}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous_layers = list(sample.layers)
        self._previous_audio = sample.audio
        sample.remove_layer()

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None or self._previous_audio is None:
            return
        sample.layers = list(self._previous_layers or [])
        sample.audio = self._previous_audio
        sample.audio_saved = False
        sample.set_edits(sample.edits)


@dataclass
class SetEdit(Command):
    """Change one non-destructive edit; encoder sweeps coalesce."""

    slot: int
    field: str
    value: object
    previous: object
    #: How to say it on screen.  The page owns its own wording and units, so
    #: there is only ever one formatter for a value.
    display: str = ""
    at: float = field(default_factory=time.monotonic)

    @property
    def label(self) -> str:
        if self.display:
            return self.display
        return f"{self.field.replace('_', ' ')} {_format_edit(self.value)}"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.set_edits(sample.edits.with_value(self.field, self.value))

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is not None:
            sample.set_edits(sample.edits.with_value(self.field, self.previous))

    def merge(self, newer: Command) -> bool:
        if not isinstance(newer, SetEdit):
            return False
        if (newer.slot, newer.field) != (self.slot, self.field):
            return False
        if newer.at - self.at > MERGE_WINDOW_S:
            return False
        self.value = newer.value
        self.display = newer.display
        self.at = newer.at
        return True


@dataclass
class SetTrim(Command):
    """Both trims at once, as one step (IN-09).

    Trim-by-ear settles the start and the end in one sitting, and taking that
    back should be one press of `Undo` rather than two -- a person who abandons
    the result wants the take they had before they started, not the half-trimmed
    thing they had in the middle.  `SetEdit` cannot express that: it is one
    field, and two of them are two steps however close together they land.
    """

    slot: int
    start_ms: float
    end_ms: float
    previous_start_ms: float
    previous_end_ms: float

    @property
    def label(self) -> str:
        if not self.start_ms and not self.end_ms:
            return f"slot {self.slot + 1}: trim cleared"
        return (f"slot {self.slot + 1}: trim {self.start_ms:.0f}ms in, "
                f"{self.end_ms:.0f}ms off the end")

    def _write(self, project, start, end) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        sample.set_edits(sample.edits
                         .with_value("trim_start_ms", float(start))
                         .with_value("trim_end_ms", float(end)))
        project.dirty = True

    def apply(self, project) -> None:
        self._write(project, self.start_ms, self.end_ms)

    def revert(self, project) -> None:
        self._write(project, self.previous_start_ms, self.previous_end_ms)


@dataclass
class ApplyEdits(Command):
    """Fold a sample's edits into its recording, keeping the original for undo."""

    slot: int
    _previous_audio: object = None
    _previous_edits: object = None

    label = "edits applied"

    def apply(self, project) -> None:
        sample = project[self.slot]
        if sample is None:
            return
        self._previous_audio = sample.audio
        self._previous_edits = sample.edits
        sample.apply_edits()

    def revert(self, project) -> None:
        sample = project[self.slot]
        if sample is None or self._previous_audio is None:
            return
        sample.audio = self._previous_audio
        sample.set_edits(self._previous_edits)
        sample.audio_saved = False


def _format_edit(value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:.0f}" if abs(value) >= 10 else f"{value:.1f}"
    return str(value)


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
