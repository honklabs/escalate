"""Slicing a take across the pads: one take becomes a kit (IN-01).

`Convert` on a sample page opens this. The grid is the take -- the same
envelope the [editor](sample_edit.py) draws -- with the slice points marked, and
pressing a pad plays the slice you are pointing at so you can hear the cut
before committing to it.

Three ways to cut, on the buttons below the display:

**bars** and **beats** divide the take evenly, which is the right answer for
anything played to the grid: eight bars of drumming into eight one-bar slices is
one press. **transients** asks :mod:`push2sampler.analysis` where the hits are,
with a sensitivity encoder, and is the right answer for a take whose rhythm is
not the grid's.

`Convert` again commits, writing the slices into the free slots after the
source. The whole conversion is **one undo step**, because "slice this into a
kit" is one decision -- taking it back a pad at a time would be sixteen presses
to undo one.

Why the original is kept by default
-----------------------------------
Slicing is the one gesture here that turns one take into many, and the
instinct to tidy up after it is wrong: the slices are views into the source's
audio, the source is what you would re-slice from at a different sensitivity,
and the pad you pressed `Convert` on is where your hands expect it to still be.
`Shift`+`Convert` consumes it when you really are done, and that is undoable
like everything else.
"""

from __future__ import annotations

import numpy as np

from .. import colors
from ..analysis import MAX_SLICES, even_slices, onsets, slice_buffers
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    ENCODER_TRACK,
    PAD_COUNT,
    Btn,
)
from ..history import SliceTake
from ..project import Sample
from .base import Mode

#: How to cut, in the order of the buttons below the display.
BY_BARS, BY_BEATS, BY_TRANSIENTS = "bars", "beats", "transients"
MODES = (BY_BARS, BY_BEATS, BY_TRANSIENTS)
MODE_LABELS = {
    BY_BARS: "bars",
    BY_BEATS: "beats",
    BY_TRANSIENTS: "transients",
}
#: Sensitivity change per encoder click.
SENSITIVITY_STEP = 0.05
#: Envelope levels the pads use, matching the editor's so the take looks the
#: same on both pages.
LOUD, MID = 0.5, 0.15


class SliceMode(Mode):
    """Choose the cuts, hear them, then commit."""

    name = "slice"
    transient = True

    @property
    def title(self) -> str:
        return f"SLICE {self.slot + 1}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        # A one-bar take has nothing to cut by bars, so opening on `bars`
        # would land you on a page that refuses to do anything.
        sample = app.project[slot]
        self.how = BY_BEATS if sample is not None and sample.bars < 2 else BY_BARS
        self.sensitivity = 0.5
        #: Which slice the last pad press auditioned, for the display.
        self.previewing: int | None = None
        self._points: list[int] | None = None

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        self.app.notify(
            f"slice slot {self.slot + 1}: buttons 1-3 choose how, "
            "Convert commits"
        )

    # -- the cuts ----------------------------------------------------------
    def invalidate(self) -> None:
        """Forget the computed points, so the next read recomputes them."""
        self._points = None

    @property
    def points(self) -> list[int]:
        """Frame positions the take is cut at, first always 0.

        Cached because the transient mode runs an FFT over the whole take and
        this is read by every render pass -- thirty times a second is not the
        place to re-analyse a four-minute recording.
        """
        if self._points is None:
            self._points = self._compute()
        return self._points

    def _compute(self) -> list[int]:
        sample = self.sample
        if sample is None:
            return []
        audio = sample.effective_audio(self.project.samplerate)
        total = audio.shape[0]
        if total <= 0:
            return []
        if self.how == BY_TRANSIENTS:
            found = onsets(audio, self.project.samplerate, self.sensitivity)
            # A slice always starts at 0: the head of the take is a slice even
            # when the first detected attack is 30 ms in, or that audio would
            # be silently dropped.
            if not found or found[0] > 0:
                found = [0] + found
            return found[:MAX_SLICES]
        count = sample.bars if self.how == BY_BARS else (
            sample.bars * self.project.beats_per_bar
        )
        return even_slices(total, min(max(1, count), MAX_SLICES))

    @property
    def slices(self) -> list[np.ndarray]:
        sample = self.sample
        if sample is None:
            return []
        return slice_buffers(
            sample.effective_audio(self.project.samplerate), self.points
        )

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """A pad plays the slice it falls in.  Nothing here edits the song."""
        if not pressed:
            return True
        which = self._slice_at(index)
        if which is None:
            self.app.notify("nothing to slice")
            return True
        pieces = self.slices
        if which >= len(pieces):
            return True
        self.previewing = which
        self.engine.preview(np.ascontiguousarray(pieces[which]), slot=-1)
        start = self.points[which] / max(1, self.project.samplerate)
        length = len(pieces[which]) / max(1, self.project.samplerate)
        self.app.notify(
            f"slice {which + 1}/{len(pieces)}  at {start:.2f}s  {length:.2f}s long"
        )
        return True

    def _slice_at(self, pad: int) -> int | None:
        """Which slice the audio under `pad` belongs to."""
        sample = self.sample
        points = self.points
        if sample is None or not points:
            return None
        total = sample.effective_audio(self.project.samplerate).shape[0]
        if total <= 0:
            return None
        frame = int(pad / PAD_COUNT * total)
        # The last point at or before this pad's frame.
        which = 0
        for i, point in enumerate(points):
            if point <= frame:
                which = i
            else:
                break
        return which

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.CONVERT:
            self._commit(consume=self.app.shift)
            return True
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.pop_mode()
            return True
        if cc in DISPLAY_ROW_BOTTOM:
            index = DISPLAY_ROW_BOTTOM.index(cc)
            if index < len(MODES):
                self._set_how(MODES[index])
            return True
        return False

    def _set_how(self, how: str) -> None:
        if how == self.how:
            self.app.notify(f"already slicing by {MODE_LABELS[how]}")
            return
        self.how = how
        self.invalidate()
        count = len(self.slices)
        extra = ""
        if how == BY_TRANSIENTS and count <= 1:
            # Saying "1 slice" and stopping would look like a bug rather than
            # a detector that found nothing it was sure about.
            extra = " - no clear hits; try turning sensitivity up"
        self.app.notify(
            f"by {MODE_LABELS[how]}: {count} slice{'s' if count != 1 else ''}{extra}"
        )

    def on_encoder(self, cc: int, delta: int) -> bool:
        if cc != ENCODER_TRACK[0]:
            return False
        if self.how != BY_TRANSIENTS:
            # The bars and beats counts come from the take's own length, so
            # there is nothing for this encoder to do -- say so rather than
            # letting it turn silently.
            self.app.notify("sensitivity applies to transient slicing")
            return True
        wanted = max(0.0, min(1.0, self.sensitivity + delta * SENSITIVITY_STEP))
        if wanted == self.sensitivity:
            return True
        self.sensitivity = wanted
        self.invalidate()
        count = len(self.slices)
        self.app.notify(
            f"sensitivity {wanted:.2f}: {count} slice{'s' if count != 1 else ''}"
        )
        return True

    # -- committing --------------------------------------------------------
    def _commit(self, consume: bool = False) -> None:
        """Write the slices into free slots, as one undo step."""
        sample = self.sample
        pieces = self.slices
        if sample is None or len(pieces) < 2:
            self.app.notify("nothing to slice: one slice is the take you have")
            return
        destinations = self._destinations(len(pieces), consume)
        if destinations is None:
            return

        built = [
            self._slice_sample(sample, slot, piece, index)
            for index, (slot, piece) in enumerate(zip(destinations, pieces))
        ]
        self.app.do(SliceTake(built, destinations, source=self.slot,
                              replaced=consume))
        self.app.pop_mode()
        first, last = destinations[0] + 1, destinations[-1] + 1
        kept = "" if consume else f", slot {self.slot + 1} kept"
        self.app.notify(
            f"{len(built)} slices into slots {first}-{last}{kept}"
        )

    def _destinations(self, count: int, consume: bool) -> list[int] | None:
        """`count` empty slots, or None after saying why there are not enough.

        Searched from the slot after the source and wrapping, so a kit lands
        next to the take it came from rather than at slot 1.  The source itself
        counts as free when it is being consumed: slicing an 8-bar take into 8
        when 8 slots remain must not fail on an off-by-one.
        """
        free: list[int] = []
        total = len(self.project.slots)
        for offset in range(total):
            slot = (self.slot + 1 + offset) % total
            if self.project[slot] is None or (consume and slot == self.slot):
                free.append(slot)
            if len(free) == count:
                return sorted(free)
        self.app.notify(
            f"{count} slices need {count} empty slots and there are "
            f"{len(free)} - delete something, or slice into fewer"
        )
        return None

    def _slice_sample(self, source, slot: int, piece: np.ndarray,
                      index: int) -> Sample:
        """One slice as a Sample: the source's character, none of its bars.

        It carries gain, colour, play mode, choke group and output, because
        those describe how the *sound* should behave and every slice is the
        same sound.  It carries **no triggers**: where the source played is not
        where its pieces play, and a kit that arrived already arranged would be
        a mess to undo by hand.

        ``bars`` is 1 whatever the slice's real length.  A slice is a hit, not
        a bar of music, and the off-grid machinery would otherwise flag all
        sixteen of them yellow for being the wrong length -- see the reference.
        """
        name = source.name or f"S{self.slot + 1:02d}"
        return Sample(
            slot=slot,
            bars=1,
            audio=np.ascontiguousarray(piece, dtype=np.float32),
            name=f"{name}/{index + 1}",
            gain=source.gain,
            color=source.color,
            play_mode=source.play_mode,
            choke_group=source.choke_group,
            output=source.output,
            nudge_ms=source.nudge_ms,
            source_bpm=source.source_bpm,
            source_samplerate=self.project.samplerate,
        )

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        sample = self.sample
        if sample is None:
            for i in range(PAD_COUNT):
                pads[i] = colors.OFF.index
            return
        audio = sample.effective_audio(self.project.samplerate)
        envelope = _envelope(audio, PAD_COUNT)
        total = max(1, audio.shape[0])
        # The pad each slice point falls on, so a cut is visible as a mark
        # rather than having to be counted.
        marks = {int(point / total * PAD_COUNT) for point in self.points}
        for pad in range(PAD_COUNT):
            level = envelope[pad]
            if pad in marks:
                # A cut is white against the take's green, and flashes on the
                # slice you last auditioned so "which one did I just hear" has
                # an answer.
                here = self._slice_at(pad)
                if here is not None and here == self.previewing and self.app.blink:
                    pads[pad] = colors.AMBER.index
                else:
                    pads[pad] = colors.WHITE.index
            elif level >= LOUD:
                pads[pad] = colors.GREEN.index
            elif level >= MID:
                pads[pad] = colors.GREEN_MID.index
            elif level > 0.0:
                pads[pad] = colors.GREEN_DIM.index
            else:
                pads[pad] = colors.WHITE_DIM.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.CONVERT] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        for index, cc in enumerate(DISPLAY_ROW_BOTTOM):
            if index >= len(MODES):
                buttons[cc] = 0
            else:
                buttons[cc] = BTN_BRIGHT if MODES[index] == self.how else BTN_ON

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["SLICE", "that slot is empty"]
        count = len(self.slices)
        head = (f"SLICE slot {self.slot + 1} {sample.name}  "
                f"by {MODE_LABELS[self.how]}  {count} slice"
                f"{'s' if count != 1 else ''}")
        lines = [head, _wave_line(sample, self.project)]
        if self.how == BY_TRANSIENTS:
            lines.append(
                f"sensitivity {self.sensitivity:.2f} (encoder 1)"
                + ("  no clear hits yet" if count <= 1 else "")
            )
        else:
            lines.append(
                f"{sample.bars} bar(s) at {self.project.beats_per_bar} beats"
                "   encoder 1: sensitivity, for transients"
            )
        lines.append(
            "pad: hear that slice   buttons 1-3: bars / beats / transients"
        )
        lines.append(
            "Convert: write the slices   Shift+Convert: and remove the original"
        )
        return lines


def _envelope(audio: np.ndarray, buckets: int) -> list[float]:
    """Peak amplitude per bucket, the same shape the editor draws."""
    if audio.shape[0] == 0:
        return [0.0] * buckets
    mono = np.abs(audio).max(axis=1)
    edges = np.linspace(0, mono.shape[0], buckets + 1).astype(int)
    return [
        float(mono[a:b].max()) if b > a else 0.0
        for a, b in zip(edges[:-1], edges[1:])
    ]


def _wave_line(sample, project, width: int = 44) -> str:
    ramp = " .:-=+*#"
    envelope = _envelope(sample.effective_audio(project.samplerate), width)
    body = "".join(
        ramp[min(len(ramp) - 1, int(level * len(ramp)))] for level in envelope
    )
    seconds = sample.frames / max(1, project.samplerate)
    return f"[{body}] {seconds:.2f}s"
