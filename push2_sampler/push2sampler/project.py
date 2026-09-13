"""The song: 256 sample slots, each with its own trigger map over 256 bars.

A project is a directory::

    my-song/
      project.json
      samples/slot_000.wav
      samples/slot_007.wav

``project.json`` holds the tempo and, per filled slot, the take length in bars,
the bars it is triggered on, whether it is audible, and its gain.

Slots and bars are addressed by one flat integer each, and the grid shows a
window of 64 at a time: slots in **banks** (a view of one library, so a bank is
not a song section) and bars in **pages** (consecutive stretches of one song).
Keeping identity a single integer is what lets every undo command, velocity map
and schedule entry stay keyed exactly as it was when there were only 64.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import wavio
from .constants import (
    CHOKE_GROUPS,
    ONE_SHOT,
    OUTPUT_PAIRS,
    PLAY_MODES,
    pair_first_channel,
)
from .edits import DEFAULT_EDITS, Edits, render_edits

#: Bars on one song page, and slots in one library bank: both are one gridful.
PAGE_BARS = 64
BANK_SLOTS = 64
#: How many of each.  Banks are a *view* of one library -- a bank is not a song
#: section -- while pages are consecutive stretches of one song.
BANKS = 4
SONG_PAGES = 4
#: Total addressable slots and bars.  Slot and bar identity stays a single
#: integer: ``bank = slot // BANK_SLOTS``, ``page = bar // PAGE_BARS``.  The
#: plan offered a list-of-lists or a ``(bank, slot)`` key; one flat index is a
#: third option that keeps every command, velocity map and schedule entry in
#: this program keyed the way it already was.
SLOT_COUNT = BANKS * BANK_SLOTS
SONG_BARS = SONG_PAGES * PAGE_BARS
#: A take may be this far from its declared length before it is flagged.
LENGTH_TOLERANCE = 0.01
#: Velocity of a bar that was not played in by hand: as hard as it goes.
FULL_VELOCITY = 127
PROJECT_FILE = "project.json"
SAMPLES_DIR = "samples"
FORMAT_VERSION = 8
#: How many scene snapshots a project keeps.
SCENE_COUNT = 8
#: User colours a slot can be tagged with, as palette indices; see colors.py.
SLOT_COLORS = 8


def _load_color(value) -> int | None:
    """A slot's user colour, or None for the default.  Never raises on junk."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value < SLOT_COLORS else None


def _load_play_mode(value) -> str:
    """A play mode from a project file, defaulting rather than raising.

    Per-field coercion, for the same reason ``Edits.from_dict`` does it: a
    hand-edited project file should not crash inside the audio callback.
    """
    return value if value in PLAY_MODES else ONE_SHOT


def _load_choke_group(value) -> int | None:
    try:
        group = int(value)
    except (TypeError, ValueError):
        return None
    return group if 1 <= group <= CHOKE_GROUPS else None


def _load_output(value) -> int:
    """An output pair from a project file, defaulting to the main mix."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if 0 <= value < OUTPUT_PAIRS else 0


def _load_scenes(value) -> list[dict | None]:
    """Scene snapshots from JSON, dropping anything malformed.

    A snapshot is a convenience for comparing arrangements; one that will not
    parse is worth losing silently rather than refusing to open the song.
    """
    scenes: list[dict | None] = [None] * SCENE_COUNT
    if not isinstance(value, list):
        return scenes
    for index, entry in enumerate(value[:SCENE_COUNT]):
        if not isinstance(entry, dict):
            continue
        slots = entry.get("slots")
        if not isinstance(slots, dict):
            continue
        restored: dict[int, dict] = {}
        for key, state in slots.items():
            try:
                slot = int(key)
            except (TypeError, ValueError):
                continue
            if not 0 <= slot < SLOT_COUNT or not isinstance(state, dict):
                continue
            bars = state.get("triggers")
            restored[slot] = {
                "enabled": bool(state.get("enabled", True)),
                "triggers": sorted(
                    int(b) for b in (bars or []) if 0 <= int(b) < SONG_BARS
                ),
                "velocities": {
                    str(bar): int(v)
                    for bar, v in (state.get("velocities") or {}).items()
                },
            }
        scenes[index] = {"name": str(entry.get("name", "")), "slots": restored}
    return scenes


def format_bpm(bpm: float) -> str:
    """A tempo as it should be read: "120", but "120.3" after a fine nudge.

    One formatter, so the transport readout and the undo label can never
    disagree about how much of the tempo you are being shown.
    """
    return f"{bpm:.1f}" if round(bpm, 3) % 1 else f"{bpm:.0f}"


@dataclass
class Sample:
    """One recorded take, assigned to one of the 64 library slots."""

    slot: int
    bars: int
    audio: np.ndarray
    triggers: set[int] = field(default_factory=set)
    #: How hard each bar was played, for the bars that were not played flat out.
    #: Keys are always a subset of ``triggers``; a missing one means full.
    velocities: dict[int, int] = field(default_factory=dict)
    #: 0 = ignore how hard the pad was hit, 1 = velocity controls the level.
    velocity_sensitivity: float = 0.0
    enabled: bool = True
    gain: float = 1.0
    name: str = ""
    #: Tempo and rate this take was captured at; 0 means "unknown" (v1 projects).
    source_bpm: float = 0.0
    source_samplerate: int = 0
    #: Non-destructive trim/fade/pitch/reverse/normalise.
    edits: Edits = DEFAULT_EDITS
    #: One of the eight user colours, or None for the default green (CC-18).
    color: int | None = None
    #: How this sample behaves when triggered: one of ``PLAY_MODES`` (NF-02).
    play_mode: str = ONE_SHOT
    #: 1-8, or None.  Samples sharing a group cut each other.
    choke_group: int | None = None
    #: Output pair: 0 is the main mix, 1 and up are cue pairs (NH-11).
    output: int = 0
    #: Sound-on-sound layers, kept individually so the last one can be removed.
    #: Empty means "the take is just ``audio``"; otherwise ``audio`` is their
    #: sum and that invariant is maintained by :meth:`set_layers`.
    layers: list = field(default_factory=list)
    #: True once this take's audio is on disk, so autosave can skip rewriting it.
    audio_saved: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"S{self.slot + 1:02d}"
        self._rendered: np.ndarray | None = None
        self._rendered_key: tuple | None = None

    @property
    def raw_frames(self) -> int:
        """Length of the recording itself, before any edits."""
        return int(self.audio.shape[0])

    @property
    def frames(self) -> int:
        """Length of what actually plays, edits included."""
        return int(self.effective_audio().shape[0])

    def effective_audio(self, samplerate: int | None = None) -> np.ndarray:
        """The audio as edited, cached until an edit or the recording changes.

        With no edits this is the recording itself, by identity -- the editor
        costs nothing until it is used.
        """
        rate = samplerate or self.source_samplerate or 48_000
        key = (self.edits, rate, id(self.audio), self.audio.shape)
        if self._rendered_key == key and self._rendered is not None:
            return self._rendered
        rendered = render_edits(self.audio, rate, self.edits)
        self._rendered_key = key
        # Holding the key's array alive keeps its id() from being reused.
        self._rendered = rendered
        return rendered

    @property
    def layer_count(self) -> int:
        """How many layers make up this take; 1 for an ordinary recording."""
        return len(self.layers) or 1

    def add_layer(self, audio: np.ndarray) -> None:
        """Sum another pass into this take, keeping it removable.

        The first overdub promotes the existing recording to layer 1, so a take
        never silently loses the ability to be peeled back.
        """
        layers = list(self.layers) or [self.audio]
        layers.append(np.ascontiguousarray(audio, dtype=np.float32))
        self.set_layers(layers)

    def remove_layer(self) -> bool:
        """Drop the most recent layer.  False when there is only one."""
        if len(self.layers) <= 1:
            return False
        self.set_layers(list(self.layers[:-1]))
        return True

    def set_layers(self, layers: list) -> None:
        """Install layers and re-sum them into ``audio``."""
        self.layers = layers
        frames = max((int(layer.shape[0]) for layer in layers), default=0)
        channels = max((int(layer.shape[1]) for layer in layers), default=1)
        summed = np.zeros((frames, channels), dtype=np.float32)
        for layer in layers:
            summed[: layer.shape[0], : layer.shape[1]] += layer
        self.audio = summed
        self.audio_saved = False
        self._rendered_key = None
        self._rendered = None

    def flatten(self) -> None:
        """Forget the layer breakdown, keeping the audio as it now sounds.

        Called wherever ``audio`` is replaced by something that is no longer the
        sum of the layers -- applying edits, or fitting an off-grid take -- so
        the invariant can never quietly go stale.
        """
        self.layers = []

    def set_edits(self, edits: Edits) -> None:
        self.edits = edits
        self._rendered_key = None
        self._rendered = None

    def apply_edits(self) -> bool:
        """Fold the edits into the recording for good.  True if anything changed."""
        if self.edits.is_default:
            return False
        self.audio = np.ascontiguousarray(self.effective_audio(), dtype=np.float32)
        self.set_edits(DEFAULT_EDITS)
        self.flatten()
        self.audio_saved = False
        return True

    def set_trigger(self, bar: int, on: bool, velocity: int | None = None) -> None:
        """Enable or disable playback on ``bar``, optionally with a velocity."""
        if not 0 <= bar < SONG_BARS:
            raise ValueError(f"bar out of range: {bar}")
        if not on:
            self.triggers.discard(bar)
            self.velocities.pop(bar, None)
            return
        self.triggers.add(bar)
        if velocity is None or velocity >= FULL_VELOCITY:
            self.velocities.pop(bar, None)
        else:
            self.velocities[bar] = max(1, int(velocity))

    def toggle(self, bar: int) -> bool:
        """Toggle playback on ``bar``; returns the new state."""
        on = bar not in self.triggers
        self.set_trigger(bar, on)
        return on

    def velocity_at(self, bar: int) -> int:
        return self.velocities.get(bar, FULL_VELOCITY)

    def velocity_scale(self, bar: int) -> float:
        """Level multiplier for ``bar``, given how hard it was played.

        At sensitivity 0 every bar plays at the sample's own gain, which is what
        a take toggled in by hand should do.
        """
        sensitivity = max(0.0, min(1.0, self.velocity_sensitivity))
        if sensitivity <= 0.0:
            return 1.0
        loudness = self.velocity_at(bar) / FULL_VELOCITY
        return (1.0 - sensitivity) + sensitivity * loudness

    def bars_at(self, bpm: float, samplerate: int, beats_per_bar: int = 4) -> float:
        """How many bars this take's audio fills at the given tempo.

        Fractional by design: 2.0 means it fits exactly, 2.3 means it does not.
        """
        frames_per_bar = 60.0 / bpm * samplerate * beats_per_bar
        if frames_per_bar <= 0:
            return float(self.bars)
        return self.frames / frames_per_bar

    def layer_paths(self) -> list[str]:
        """Relative WAV path per layer; empty for a take with no overdubs."""
        if not self.layers:
            return []
        return [
            f"{SAMPLES_DIR}/slot_{self.slot:03d}_L{i + 1}.wav"
            for i in range(len(self.layers))
        ]

    def to_json(self, audio_path: str) -> dict:
        return {
            "layers": self.layer_paths(),
            "slot": self.slot,
            "name": self.name,
            "bars": self.bars,
            "triggers": sorted(self.triggers),
            "enabled": self.enabled,
            "gain": round(float(self.gain), 4),
            "color": self.color,
            "play_mode": self.play_mode,
            "choke_group": self.choke_group,
            "output": self.output,
            "velocities": {str(bar): v for bar, v in sorted(self.velocities.items())},
            "edits": self.edits.as_dict(),
            "velocity_sensitivity": round(float(self.velocity_sensitivity), 3),
            "source_bpm": round(float(self.source_bpm), 3),
            "source_samplerate": int(self.source_samplerate),
            "audio": audio_path,
        }


@dataclass(frozen=True)
class ProjectSummary:
    """What the browser needs to know about a project it has not opened."""

    path: Path
    name: str
    bpm: float
    slots: int
    pages: int
    modified: float

    @property
    def has_audio(self) -> bool:
        return self.slots > 0

    @classmethod
    def read(cls, directory: Path) -> "ProjectSummary | None":
        """Read one project's metadata, or None if that is not a project."""
        path = Path(directory)
        manifest = path / PROJECT_FILE
        if not path.is_dir() or not manifest.exists():
            return None
        try:
            payload = json.loads(manifest.read_text())
            if not isinstance(payload, dict):
                raise ValueError("not a JSON object")
        except Exception:
            # A project whose manifest will not parse is still a directory
            # someone made, so it is listed -- as empty, which is what the
            # browser can honestly say about it.
            payload = {}
        slots = payload.get("slots")
        return cls(
            path=path,
            name=path.name,
            bpm=float(payload.get("bpm") or 120.0),
            slots=len(slots) if isinstance(slots, list) else 0,
            pages=int(payload.get("pages") or 1),
            modified=manifest.stat().st_mtime,
        )


class Project:
    """Tempo plus the 256-slot sample library."""

    def __init__(self, samplerate: int = 48_000, bpm: float = 120.0,
                 beats_per_bar: int = 4) -> None:
        self.samplerate = samplerate
        self.bpm = float(bpm)
        self.beats_per_bar = beats_per_bar
        #: Song pages of PAGE_BARS bars each, played consecutively.
        self.pages = SONG_PAGES
        self.slots: list[Sample | None] = [None] * SLOT_COUNT
        #: Eight snapshots of the arrangement; see :meth:`store_scene`.
        self.scenes: list[dict | None] = [None] * SCENE_COUNT
        #: Anything worth saying about how this project loaded; see load().
        self.warning: str | None = None
        #: Gain on the whole mix.
        self.master_gain = 1.0
        #: Slot being soloed, or None.  Kept separate from ``Sample.enabled`` so
        #: that soloing and un-soloing never destroys the mute state you set by
        #: hand -- that is the whole point of a solo button.
        self.soloed: int | None = None
        self.dirty = False

    # ------------------------------------------------------------------
    @property
    def song_bars(self) -> int:
        """Total bars: the pages, end to end."""
        return self.pages * PAGE_BARS

    @property
    def banks(self) -> int:
        return BANKS

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
        """``sample``'s audio padded with silence or trimmed to exactly its bars.

        Works on the edited audio: fitting is destructive anyway, so it folds in
        whatever the editor is doing rather than fighting it.
        """
        target = self.expected_frames(sample.bars)
        audio = sample.effective_audio(self.samplerate)
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
        sample.set_edits(DEFAULT_EDITS)
        sample.flatten()
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
            velocities=dict(existing.velocities) if existing else {},
            velocity_sensitivity=existing.velocity_sensitivity if existing else 0.0,
            enabled=existing.enabled if existing else True,
            gain=existing.gain if existing else 1.0,
            name=existing.name if existing else "",
            source_bpm=self.bpm,
            source_samplerate=self.samplerate,
        )
        self.slots[slot] = sample
        self.dirty = True
        return sample  # layers default to empty: this is a new recording

    def next_empty(self, after: int) -> int | None:
        """The first empty slot after ``after``, wrapping round every bank."""
        for offset in range(1, SLOT_COUNT + 1):
            candidate = (after + offset) % SLOT_COUNT
            if self.slots[candidate] is None:
                return candidate
        return None

    def copy_slot(self, src: int, dst: int) -> Sample | None:
        """Put a copy of ``src`` in ``dst``, arrangement and all.

        The audio array is shared, not duplicated.  Nothing here mutates a take's
        samples in place -- an edit or a repair builds a new array and rebinds
        ``sample.audio`` -- so the two slots behave independently from the start
        and a 30-second take does not cost 30 seconds of memory to duplicate.
        """
        source = self.slots[src]
        if source is None:
            return None
        copy = Sample(
            slot=dst,
            bars=source.bars,
            audio=source.audio,
            triggers=set(source.triggers),
            velocities=dict(source.velocities),
            velocity_sensitivity=source.velocity_sensitivity,
            enabled=source.enabled,
            gain=source.gain,
            name=f"{source.name}+",
            source_bpm=source.source_bpm,
            source_samplerate=source.source_samplerate,
            edits=source.edits,
            color=source.color,
            play_mode=source.play_mode,
            choke_group=source.choke_group,
            output=source.output,
            layers=list(source.layers),
        )
        self.slots[dst] = copy
        self.dirty = True
        return copy

    #: Fields a copy deliberately does *not* take from its source.
    #:
    #: Everything else must be carried, and ``test_project`` asserts that every
    #: field of ``Sample`` is in one list or the other.  Three features in a row
    #: -- colour tags, overdub layers, play modes -- each added a field and none
    #: updated ``copy_slot``, so duplicating a slot quietly lost them.
    NOT_COPIED: tuple[str, ...] = (
        "slot",          # the copy's own identity
        "name",          # gets a "+" so the two are tellable apart
        "audio_saved",   # the copy has never been written under its own name
    )

    def swap_slots(self, a: int, b: int) -> bool:
        """Exchange the contents of two slots.  True if anything moved.

        The *contents* move and the slot numbers stay put, because a slot
        number is identity everywhere else in this program -- the schedule, the
        velocity map, the WAV filename, every undo entry -- so each sample's
        ``slot`` is rewritten to match its new home rather than travelling with
        it.

        Swapping with an empty slot is a move, and is allowed: the gesture is
        the same to the hands, so refusing it would only be surprising.
        """
        if a == b or not (0 <= a < SLOT_COUNT and 0 <= b < SLOT_COUNT):
            return False
        first, second = self.slots[a], self.slots[b]
        if first is None and second is None:
            return False
        self.slots[a], self.slots[b] = second, first
        for slot in (a, b):
            sample = self.slots[slot]
            if sample is not None:
                sample.slot = slot
                # The WAV's filename comes from the slot number, so the audio
                # has to be written again under its new one.
                sample.audio_saved = False
        self.dirty = True
        return True

    def copy_bar_range(self, slot: int, src_start: int, dst_start: int,
                       length: int, move: bool = False) -> dict[int, int | None]:
        """The bar changes that duplicating a block of an arrangement would make.

        Computes rather than applies, so the caller can hand the result to one
        undoable :class:`~push2sampler.history.SetBars`.  A block that would run
        past the last bar is clipped, not wrapped: bar 64 is the end of the song,
        not a join.
        """
        sample = self.slots[slot]
        if sample is None or length <= 0:
            return {}
        changes: dict[int, int | None] = {}
        for offset in range(length):
            src, dst = src_start + offset, dst_start + offset
            if not 0 <= dst < self.song_bars:
                break  # clipped at the end of the song
            if 0 <= src < self.song_bars and src in sample.triggers:
                changes[dst] = sample.velocity_at(src)
            else:
                changes[dst] = None
        if move:
            for offset in range(length):
                src = src_start + offset
                # Only clear source bars the copy did not land on.
                if 0 <= src < self.song_bars and src not in changes:
                    changes[src] = None
        return changes

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

    def audible(self, sample: "Sample") -> bool:
        """Whether this sample is heard, taking mute *and* solo into account."""
        if self.soloed is not None:
            return sample.slot == self.soloed
        return sample.enabled

    def solo(self, slot: int | None) -> None:
        """Solo a slot, or clear it.  Soloing the soloed slot clears it."""
        self.soloed = None if slot is None or slot == self.soloed else slot
        self.dirty = True

    # ------------------------------------------------------------------
    # scenes: snapshots of the arrangement, for A/B and live variation
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """The whole arrangement -- what is audible, and where it plays."""
        return {
            "name": "",
            "slots": {
                sample.slot: {
                    "enabled": sample.enabled,
                    "triggers": sorted(sample.triggers),
                    "velocities": {str(b): v for b, v in sorted(sample.velocities.items())},
                }
                for sample in self.filled()
            },
        }

    def store_scene(self, index: int) -> None:
        self.scenes[index] = self.snapshot()
        self.dirty = True

    def restore(self, snapshot: dict) -> None:
        """Apply a snapshot taken by :meth:`snapshot`."""
        for slot, state in snapshot["slots"].items():
            sample = self.slots[slot]
            if sample is None:
                continue
            sample.enabled = bool(state.get("enabled", True))
            sample.triggers = {
                int(b) for b in state.get("triggers", ()) if 0 <= int(b) < self.song_bars
            }
            sample.velocities = {
                int(bar): int(v)
                for bar, v in (state.get("velocities") or {}).items()
                if int(bar) in sample.triggers
            }
        self.dirty = True

    def recall_scene(self, index: int) -> bool:
        """Put a stored arrangement back.  False if that scene is empty.

        Only the enable map and the trigger sets move: audio, gain, edits and
        layers are properties of the *take*, not of the arrangement, and a scene
        that silently re-pitched your samples would be a trap.

        Slots recorded since the snapshot are left alone rather than emptied --
        a scene is a variation, not a rollback of the whole library.
        """
        scene = self.scenes[index]
        if scene is None:
            return False
        self.restore(scene)
        return True

    def scene_filled(self, index: int) -> bool:
        return self.scenes[index] is not None

    def slots_at_bar(self, bar: int) -> set[int]:
        """Slots of the audible samples triggered on ``bar``."""
        if not 0 <= bar < self.song_bars:
            return set()
        return {s.slot for s in self.filled() if self.audible(s) and bar in s.triggers}

    @property
    def used_bars(self) -> int:
        """Bars up to and including the last one anything plays on.

        With four pages available most songs use one, so this is what a bounce
        renders rather than the nominal length -- otherwise a 16-bar song would
        come out with two minutes of silence stuck on the end.
        """
        used = self.bars_in_use()
        return max(used) + 1 if used else 0

    def bars_in_use(self) -> set[int]:
        """Every bar on which some audible sample is triggered."""
        used: set[int] = set()
        for sample in self.filled():
            if self.audible(sample):
                used |= sample.triggers
        return used

    def build_schedule(self):
        """bar -> tuple of :class:`~push2sampler.audio.ScheduledSample`."""
        from .audio import ScheduledSample

        schedule: list[list[ScheduledSample]] = [[] for _ in range(self.song_bars)]
        for sample in self.filled():
            if not self.audible(sample) or sample.frames == 0:
                continue
            audio = sample.effective_audio(self.samplerate)
            for bar in sorted(sample.triggers):
                if 0 <= bar < self.song_bars:
                    schedule[bar].append(
                        ScheduledSample(
                            sample.slot,
                            audio,
                            sample.gain * sample.velocity_scale(bar),
                            play_mode=sample.play_mode,
                            choke_group=sample.choke_group,
                            channel=pair_first_channel(sample.output),
                        )
                    )
        return [tuple(entries) for entries in schedule]

    # ------------------------------------------------------------------
    def save(self, directory: str | Path) -> Path:
        directory = Path(directory)
        (directory / SAMPLES_DIR).mkdir(parents=True, exist_ok=True)
        slots = []
        for sample in self.filled():
            rel = f"{SAMPLES_DIR}/slot_{sample.slot:03d}.wav"
            paths = sample.layer_paths()
            # Audio never changes in place, so only write takes we haven't yet.
            if not sample.audio_saved or not (directory / rel).exists():
                wavio.write(directory / rel, sample.audio, self.samplerate)
                for layer, path in zip(sample.layers, paths):
                    wavio.write(directory / path, layer, self.samplerate)
                sample.audio_saved = True
            slots.append(sample.to_json(rel))
        payload = {
            "version": FORMAT_VERSION,
            "samplerate": self.samplerate,
            "bpm": round(self.bpm, 3),
            "master_gain": round(float(self.master_gain), 4),
            "beats_per_bar": self.beats_per_bar,
            "pages": self.pages,
            # Kept for readers older than format 6, which derive the length from
            # it; format 6 and up use "pages".
            "song_bars": self.song_bars,
            "scenes": [scene for scene in self.scenes],
            "slots": slots,
        }
        path = directory / PROJECT_FILE
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n")
        tmp.replace(path)
        self.dirty = False
        return path

    @staticmethod
    def scan(root: str | Path) -> list["ProjectSummary"]:
        """Summarise every project under ``root``, without loading any audio.

        The browser shows sixty-four of these at once, so reading the WAVs would
        mean loading a gigabyte to draw a grid.  Everything shown comes out of
        ``project.json``.
        """
        root = Path(root)
        if not root.is_dir():
            return []
        found = []
        for entry in sorted(root.iterdir()):
            summary = ProjectSummary.read(entry)
            if summary is not None:
                found.append(summary)
        return found

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
        # Format 6 stores the page count; before that a project was one page of
        # 64 bars, whatever "song_bars" happened to say.
        if "pages" in payload:
            project.pages = max(1, min(SONG_PAGES, int(payload["pages"] or 1)))
        else:
            declared = int(payload.get("song_bars") or PAGE_BARS)
            project.pages = max(1, min(SONG_PAGES, -(-declared // PAGE_BARS)))
        project.master_gain = float(payload.get("master_gain", 1.0) or 1.0)
        project.scenes = _load_scenes(payload.get("scenes"))
        dropped_bars = 0
        dropped_slots: list[int] = []
        for entry in payload.get("slots", []):
            audio_rel = entry.get("audio")
            if not audio_rel or not (directory / audio_rel).exists():
                continue
            audio, rate = wavio.read(directory / audio_rel)
            if rate != project.samplerate:
                audio = wavio.resample(audio, rate, project.samplerate)
            slot = int(entry["slot"])
            # Layers are optional and best-effort: a take whose layer files have
            # gone keeps playing as the summed audio, it just cannot be peeled
            # back any more.  Losing the breakdown must not lose the take.
            layers = []
            for rel in entry.get("layers") or []:
                path = directory / rel
                if not path.exists():
                    layers = []
                    break
                layer, layer_rate = wavio.read(path)
                if layer_rate != project.samplerate:
                    layer = wavio.resample(layer, layer_rate, project.samplerate)
                layers.append(layer)
            # Format 1 stored no provenance.  Assume such a take was recorded at
            # this project's own tempo -- the best guess available, and the one
            # that does not flag every existing project as mismatched.
            source_bpm = float(entry.get("source_bpm") or project.bpm)
            source_rate = int(entry.get("source_samplerate") or project.samplerate)
            if not 0 <= slot < SLOT_COUNT:
                dropped_slots.append(slot)
                continue
            # A trigger beyond the last page cannot play, so it is dropped
            # rather than kept as a silent surprise -- but loudly, on the way in.
            limit = project.song_bars
            triggers = {int(b) for b in entry.get("triggers", [])}
            kept = {b for b in triggers if 0 <= b < limit}
            dropped_bars += len(triggers) - len(kept)
            project.slots[slot] = Sample(
                slot=slot,
                bars=int(entry.get("bars", 1)),
                audio=audio,
                triggers=kept,
                velocities={
                    int(bar): int(v)
                    for bar, v in (entry.get("velocities") or {}).items()
                    if int(bar) in kept
                },
                velocity_sensitivity=float(entry.get("velocity_sensitivity", 0.0) or 0.0),
                edits=Edits.from_dict(entry.get("edits")),
                enabled=bool(entry.get("enabled", True)),
                gain=float(entry.get("gain", 1.0)),
                name=str(entry.get("name", "")),
                color=_load_color(entry.get("color")),
                play_mode=_load_play_mode(entry.get("play_mode")),
                choke_group=_load_choke_group(entry.get("choke_group")),
                output=_load_output(entry.get("output")),
                source_bpm=source_bpm,
                source_samplerate=source_rate,
                layers=layers,
                audio_saved=True,
            )
        notes = []
        if dropped_bars:
            notes.append(f"dropped {dropped_bars} trigger(s) past bar {project.song_bars}")
        if dropped_slots:
            notes.append(f"dropped {len(dropped_slots)} slot(s) outside 1-{SLOT_COUNT}")
        project.warning = "; ".join(notes) or None
        project.dirty = False
        return project
