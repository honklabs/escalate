"""IN-04: which of your loops fit together, and what would fix one that does not.

The library grid, coloured by how each slot sits against **one reference
slot** -- the sample whose page you came from. Green fits, amber is a
neighbour, red clashes, white has no harmony to compare. Pick a red pad and
the page offers a transpose that would bring it in, on one button.

Two things this page deliberately does not do.

It does not colour drums. A kick under a chord progression is the most
ordinary thing in music, so "no harmony here" is the honest answer rather than
a warning -- and `analysis.harmony` needs two independent gates to say it,
because a kick's chroma is peaked enough to look tonal and white noise
sometimes reads as a tone.

And it does not compute a colour from a **key name**. A prototype measured key
naming wrong on two of ten signals (a held Cmaj7 comes back "E minor",
correctly noting those four notes also sit in E minor), while the chroma
underneath was right every time. So the key is shown, labelled as a guess, and
the colours come from the pitch classes.
"""

from __future__ import annotations

from .. import colors
from ..analysis import (
    FIT_CLASH,
    FIT_NEAR,
    FIT_SAME,
    FIT_UNPITCHED,
    fit,
    harmony,
    suggest_transpose,
)
from ..constants import BTN_BRIGHT, BTN_DIM, BTN_ON, DISPLAY_ROW_BOTTOM, PAD_COUNT, Btn
from ..history import SetEdit
from .base import Mode

#: Button that applies the suggested transpose to the picked slot.
ACCEPT_BUTTON = DISPLAY_ROW_BOTTOM[0]

#: Pad colour per verdict.  The program's own meanings: green is "this is
#: fine", amber is "look at this", red is "this is wrong", white is "nothing to
#: say".  Deliberately the same four the library already uses.
FIT_COLORS = {
    FIT_SAME: colors.GREEN,
    FIT_NEAR: colors.AMBER,
    FIT_CLASH: colors.RED,
    FIT_UNPITCHED: colors.WHITE_DIM,
}

FIT_WORDS = {
    FIT_SAME: "fits",
    FIT_NEAR: "close - a note or two apart",
    FIT_CLASH: "clashes",
    FIT_UNPITCHED: "no harmony to compare",
}


class HarmonyMode(Mode):
    name = "harmony"

    @property
    def title(self) -> str:
        return f"HARMONY vs {self.slot + 1}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        #: The reference: every other slot is described relative to this one.
        self.slot = slot
        #: The slot being asked about, or None.
        self.picked: int | None = None
        self._harmonies: dict[int, object] = {}

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        reference = self.reading(self.slot)
        if reference is None:
            self.app.notify("nothing in that slot to compare against")
            return
        if not reference.tonal:
            # Not an error: it is the answer.  Saying which gate refused is
            # more use than "unpitched" -- one means "this is a drum", the
            # other means "there is no key in this".
            why = ("no notes in it" if reference.role in ("bass", "tone")
                   else f"a {reference.role}, not a pitched part")
            self.app.notify(f"slot {self.slot + 1} is {why} - nothing to compare to")
            return
        self.app.notify(
            f"slot {self.slot + 1}: {reference.note_names}"
            f"  (about {reference.key})"
        )

    # -- the readings ------------------------------------------------------
    def reading(self, slot: int):
        """One slot's harmony, measured once per version of its audio.

        An FFT over every filled slot is not a per-frame cost, and this page is
        opened by a button press.  Cached lazily, so opening the page costs
        only the reference plus whatever you look at -- 256 filled slots would
        otherwise mean 256 FFT passes before the first pad lit.

        **Keyed on the audio, not on the slot.**  Caching per slot alone was
        wrong and a test caught it: accepting a transpose and then pressing
        Undo left the page still holding the *transposed* reading, so it went
        on saying "fits" about audio that had been put back to clashing.  The
        page cannot see an undo -- it does not go through a mode -- so the
        answer is to notice the audio changed rather than to be told.  The same
        staleness would have arrived from a re-record, an overdub, or an edit
        applied on the editor page.
        """
        sample = self.project[slot]
        if sample is None:
            return None
        audio = sample.effective_audio(self.project.samplerate)
        key = (id(audio), audio.shape)
        cached = self._harmonies.get(slot)
        if cached is not None and cached[0] == key:
            return cached[1]
        reading = harmony(audio, self.project.samplerate)
        self._harmonies[slot] = (key, reading)
        return reading

    def verdict(self, slot: int) -> str:
        if slot == self.slot:
            return FIT_SAME
        return fit(self.reading(slot), self.reading(self.slot))

    def shift_for(self, slot: int) -> int:
        if slot == self.slot:
            return 0
        return suggest_transpose(self.reading(slot), self.reading(self.slot))

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        if not pressed:
            return True
        slot = self.app.slot_at(index)
        sample = self.project[slot]
        if sample is None:
            self.app.notify("empty slot")
            return True
        if self.app.shift:
            # Re-reference without leaving: "and against *that* one?" is the
            # second question anybody asks, and going back to a sample page to
            # ask it would lose the readings already measured.
            self.slot = slot
            self.picked = None
            self.on_enter()
            return True
        if slot == self.slot:
            self.picked = None
            self.app.notify(f"slot {slot + 1} is the one everything is compared to")
            return True
        self.picked = slot
        # Hearing it is half the answer: the colour says the notes disagree,
        # your ears say whether you mind.
        self.engine.preview(
            sample.effective_audio(self.project.samplerate), sample.gain, slot=slot
        )
        reading = self.reading(slot)
        verdict = self.verdict(slot)
        parts = [f"slot {slot + 1}: {FIT_WORDS[verdict]}"]
        if reading is not None and reading.tonal:
            parts.append(reading.note_names)
        shift = self.shift_for(slot)
        if shift:
            parts.append(f"button 1: move it {shift:+d}")
        self.app.notify("   ".join(parts))
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == ACCEPT_BUTTON:
            self._accept()
            return True
        if cc in (Btn.SCALE, Btn.SESSION, Btn.LEFT, Btn.NOTE):
            self.app.pop_mode()
            return True
        if cc in (Btn.PAGE_LEFT, Btn.PAGE_RIGHT):
            return False  # the app's own bank paging still works
        return False

    def _accept(self) -> None:
        """Apply the suggested transpose to the picked slot.

        It is the editor's own pitch edit (`NF-03`), not a new field: "move
        this loop up two semitones" is the thing the editor already does, and a
        second way to say it would be a second thing to keep in step.  So it is
        non-destructive, visible on the editor page, and one Undo.
        """
        if self.picked is None:
            self.app.notify("pick a pad first, then button 1")
            return
        sample = self.project[self.picked]
        if sample is None:
            self.picked = None
            return
        shift = self.shift_for(self.picked)
        if not shift:
            self.app.notify(f"slot {self.picked + 1} already fits - nothing to move")
            return
        wanted = sample.edits.pitch_semitones + shift
        self.app.do(SetEdit(self.picked, "pitch_semitones", wanted,
                            sample.edits.pitch_semitones))
        # No cache to clear: `reading` keys on the audio, so the next call
        # measures the transposed take by itself.  Asking again then suggests
        # 0, which is what makes accepting twice a no-op rather than a drift.
        self.app.notify(
            f"slot {self.picked + 1} moved {shift:+d} semitones - "
            f"{FIT_WORDS[self.verdict(self.picked)]}"
        )

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        for index in range(PAD_COUNT):
            slot = self.app.slot_at(index)
            if self.project[slot] is None:
                pads[index] = colors.OFF.index
                continue
            if slot == self.slot:
                # The reference flashes, so "compared to what" is never a
                # question you have to read the display to answer.
                pads[index] = (colors.WHITE.index if self.app.blink
                               else colors.GREEN.index)
                continue
            color = FIT_COLORS[self.verdict(slot)]
            if slot == self.picked and not self.app.blink:
                pads[index] = colors.WHITE.index
            else:
                pads[index] = color.index

    def render_buttons(self, buttons: dict) -> None:
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.SCALE] = BTN_BRIGHT
        offered = self.picked is not None and self.shift_for(self.picked)
        buttons[ACCEPT_BUTTON] = (
            BTN_BRIGHT if offered and self.app.blink else BTN_DIM if offered else 0
        )

    def status_lines(self) -> list[str]:
        reference = self.reading(self.slot)
        if reference is None:
            return ["HARMONY", "nothing in that slot"]
        if not reference.tonal:
            return [
                f"HARMONY vs slot {self.slot + 1}",
                f"that slot is a {reference.role or 'silence'} - it has no key,",
                "so there is nothing for the others to agree or disagree with",
                "Scale or Session: leave",
            ]
        counts = {FIT_SAME: 0, FIT_NEAR: 0, FIT_CLASH: 0, FIT_UNPITCHED: 0}
        for sample in self.project.filled():
            if sample.slot != self.slot:
                counts[self.verdict(sample.slot)] += 1
        lines = [
            f"HARMONY vs slot {self.slot + 1} {self.sample.name}"
            f"   {reference.note_names}",
            f"about {reference.key} (a guess, {reference.key_confidence:.2f})"
            f"   {counts[FIT_SAME]} fit   {counts[FIT_NEAR]} close   "
            f"{counts[FIT_CLASH]} clash   {counts[FIT_UNPITCHED]} unpitched",
            "green fits   amber is close   red clashes   white has no harmony",
        ]
        if self.picked is None:
            lines.append("press a pad to hear it and read how it sits"
                         "   Shift+pad: compare against that one instead")
        else:
            picked = self.reading(self.picked)
            shift = self.shift_for(self.picked)
            detail = FIT_WORDS[self.verdict(self.picked)]
            notes = picked.note_names if picked and picked.tonal else ""
            lines.append(f"slot {self.picked + 1}: {detail}   {notes}")
            lines.append(
                f"button 1 moves it {shift:+d} semitones (the editor's pitch, one Undo)"
                if shift else "nothing to move: it already fits"
            )
        return lines
