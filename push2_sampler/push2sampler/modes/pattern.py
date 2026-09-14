"""Generating a pattern instead of tapping one in (IN-03).

`Automate` on a sample page opens this. Five encoders, a live preview on the
grid, and `Automate` again to keep it.

| Encoder | |
| --- | --- |
| 1 | **density** -- how many bars of the pattern play |
| 2 | **rotation** -- the same shape, starting somewhere else |
| 3 | **algorithm** -- euclid / every n / random / mirror |
| 4 | **seed** for `random`, or the **slot** to copy for `mirror` |
| 5 | **length** -- how long the pattern is before it repeats |

The preview writes nothing. The pattern is a pure function of those five
numbers (see :mod:`push2sampler.patterns`), so the preview and the commit call
the *same* function and what you see is exactly what gets stored -- there is no
second code path to disagree with the first.

The fifth encoder is not in the plan, and building the page without it showed
why it has to be there: spread three bars evenly over a whole 64-bar page and
you get a hit every twenty-one bars, which is not a rhythm. A pattern is short
and **repeats** -- three over eight, eight times, is the tresillo, and that is
what turning a density encoder is supposed to give you.

`Session` leaves without keeping it. `Automate` keeps it as **one** undo step,
replacing this sample's bars on the page you are on.

Why it replaces rather than adds
--------------------------------
A generated pattern is a *statement* about this sample's rhythm, and adding to
what is already there would make the preview a lie: you would see eight bars
and get eleven. Replacing is also what makes the encoders explorable -- you can
turn density back down and arrive where you started, which you cannot do if
every turn accumulates.

It replaces only **this page's 64 bars**, because that is what the grid shows
and what the preview covers. Patterning page A must not silently rewrite page D.
"""

from __future__ import annotations

from .. import colors
from ..constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_ON,
    DISPLAY_ROW_BOTTOM,
    ENCODER_TRACK,
    PAD_COUNT,
    Btn,
)
from ..history import SetBars
from ..patterns import (
    ALGORITHM_LABELS,
    ALGORITHMS,
    EUCLIDEAN,
    MIRROR,
    RANDOM,
    SEEDS,
    generate,
    tile,
)
from ..project import FULL_VELOCITY, PAGE_BARS, SLOT_COUNT
from .base import Mode

#: Length of the repeating pattern, in bars, and where the span encoder starts.
#: A 16-bar section is the commonest unit of song structure, and 4 hits in it is
#: a bar every four -- so the page opens on something ordinary and useful
#: rather than empty or arithmetic.
MIN_SPAN = 1
DEFAULT_SPAN = 16
DEFAULT_DENSITY = 4


class PatternMode(Mode):
    """Turn encoders until the bars are right, then keep them."""

    name = "pattern"
    transient = True

    @property
    def title(self) -> str:
        return f"PATTERN {self.slot + 1}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        self.density = DEFAULT_DENSITY
        #: Bars in the repeating pattern.  The page is 64 bars; a *rhythm* is
        #: much shorter than that and repeats -- see `patterns.tile`.
        self.span = DEFAULT_SPAN
        self.rotation = 0
        self.algorithm = EUCLIDEAN
        self.seed = 0
        #: Slot whose bars `mirror` copies.  Starts on the previous filled slot
        #: rather than slot 1, because "answer the thing I just made" is the
        #: reason to mirror at all.
        self.mirror_slot = self._nearest_filled()

    def _nearest_filled(self) -> int:
        """The closest other filled slot, searching backwards then forwards."""
        for offset in range(1, SLOT_COUNT):
            for candidate in ((self.slot - offset) % SLOT_COUNT,
                              (self.slot + offset) % SLOT_COUNT):
                if self.project[candidate] is not None and candidate != self.slot:
                    return candidate
        return self.slot

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        self.app.notify(
            "pattern: 1 density  2 rotate  3 algorithm  4 seed  5 length   "
            "Automate keeps it"
        )

    # -- the pattern -------------------------------------------------------
    @property
    def page_start(self) -> int:
        """First bar of the page being patterned."""
        return self.app.page * PAGE_BARS

    @property
    def bars(self) -> set[int]:
        """The previewed bars, as **song** bar numbers.

        Generated fresh on every read rather than cached: these are pure
        functions over at most 64 steps, and a cache is a way for the preview
        and the commit to disagree.

        `mirror` deliberately ignores the span and copies the other slot's bars
        across the whole page: tiling someone else's rhythm would be inventing
        a pattern rather than answering one.
        """
        if self.algorithm == MIRROR:
            mirrored = self.project[self.mirror_slot]
            source = set()
            if mirrored is not None and self.mirror_slot != self.slot:
                source = {bar - self.page_start for bar in mirrored.triggers
                          if self.page_start <= bar < self.page_start + PAGE_BARS}
            local = generate(MIRROR, 0, PAGE_BARS, rotation=self.rotation,
                             source=source)
        else:
            pattern = generate(self.algorithm, self.density, self.span,
                               rotation=self.rotation, seed=self.seed)
            local = tile(pattern, self.span, PAGE_BARS)
        return {self.page_start + bar for bar in local}

    # -- input -------------------------------------------------------------
    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """Pads are the preview.  Pressing one says so rather than editing it.

        Letting a pad toggle a bar here would put a hand-made edit inside a
        generated pattern, which the next encoder click would then wipe -- so
        the page says what the pads are for instead of silently losing work.
        """
        if pressed:
            self.app.notify(
                "the grid is a preview - turn the encoders, or Automate to keep it"
            )
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        if cc == Btn.AUTOMATE:
            self._commit()
            return True
        if cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            self.app.notify("pattern discarded")
            self.app.pop_mode()
            return True
        if cc == DISPLAY_ROW_BOTTOM[0]:
            self._cycle_algorithm(1)
            return True
        return False

    def on_encoder(self, cc: int, delta: int) -> bool:
        if cc == ENCODER_TRACK[0]:
            self.density = max(0, min(self.span, self.density + delta))
            self.app.notify(
                f"{self.density} of every {self.span} bars "
                f"({len(self.bars)} on the page)"
            )
            return True
        if cc == ENCODER_TRACK[1]:
            self.rotation = (self.rotation + delta) % max(1, self.span)
            self.app.notify(f"rotate {self.rotation}")
            return True
        if cc == ENCODER_TRACK[4]:
            self._change_span(delta)
            return True
        if cc == ENCODER_TRACK[2]:
            self._cycle_algorithm(delta)
            return True
        if cc == ENCODER_TRACK[3]:
            self._fourth_encoder(delta)
            return True
        return False

    def _change_span(self, delta: int) -> None:
        """How long the repeating pattern is, in bars.

        Density and rotation are both expressed *within* the span, so both are
        clamped when it shrinks -- leaving a density of 12 inside a span of 4
        would silently mean "every bar" and make the encoder look broken.
        """
        wanted = max(MIN_SPAN, min(PAGE_BARS, self.span + delta))
        if wanted == self.span:
            return
        self.span = wanted
        self.density = min(self.density, wanted)
        self.rotation %= wanted
        self.app.notify(
            f"pattern is {wanted} bar(s) long, repeating "
            f"({self.density} hit(s) each, {len(self.bars)} on the page)"
        )

    def _cycle_algorithm(self, delta: int) -> None:
        index = (ALGORITHMS.index(self.algorithm) + delta) % len(ALGORITHMS)
        self.algorithm = ALGORITHMS[index]
        label = ALGORITHM_LABELS[self.algorithm]
        if self.algorithm == MIRROR and self.mirror_slot == self.slot:
            # Mirroring yourself is an empty pattern, which looks like a bug.
            self.app.notify(f"{label}: no other filled slot to copy")
            return
        self.app.notify(f"{label}: {len(self.bars)} bar(s)")

    def _fourth_encoder(self, delta: int) -> None:
        """Seed for `random`, mirrored slot for `mirror`, nothing otherwise.

        One encoder doing two jobs is only acceptable because the two never
        apply at once, and because it says which job it is doing.
        """
        if self.algorithm == RANDOM:
            self.seed = (self.seed + delta) % SEEDS
            self.app.notify(f"seed {self.seed}: {len(self.bars)} bar(s)")
            return
        if self.algorithm == MIRROR:
            self._step_mirror(delta)
            return
        self.app.notify(
            f"{ALGORITHM_LABELS[self.algorithm]} has no seed - "
            "encoder 3 for random or mirror"
        )

    def _step_mirror(self, delta: int) -> None:
        """Walk to the next filled slot, skipping the empties and ourselves."""
        step = 1 if delta >= 0 else -1
        candidate = self.mirror_slot
        for _ in range(SLOT_COUNT):
            candidate = (candidate + step) % SLOT_COUNT
            if candidate != self.slot and self.project[candidate] is not None:
                self.mirror_slot = candidate
                name = self.project[candidate].name
                self.app.notify(
                    f"mirror slot {candidate + 1} {name}: {len(self.bars)} bar(s)"
                )
                return
        self.app.notify("no other filled slot to mirror")

    # -- committing --------------------------------------------------------
    def _commit(self) -> None:
        """Keep the previewed bars, as one undo step."""
        sample = self.sample
        if sample is None:
            self.app.notify("that slot is empty")
            return
        wanted = self.bars
        page_bars = range(self.page_start, self.page_start + PAGE_BARS)
        existing = {bar for bar in sample.triggers if bar in page_bars}
        if wanted == existing:
            self.app.notify("that is already the pattern")
            self.app.pop_mode()
            return
        # Every bar on this page, on or off: SetBars snapshots what it replaces,
        # so undo restores the hand-made arrangement this wiped -- including
        # the velocities, which a generated pattern has no opinion about.
        changes = {bar: (FULL_VELOCITY if bar in wanted else None)
                   for bar in page_bars}
        label = (f"{ALGORITHM_LABELS[self.algorithm]} {len(wanted)} bar(s)"
                 f" on page {self.app.page_letter}")
        self.app.do(SetBars(self.slot, changes, label))
        self.app.pop_mode()
        self.app.notify(f"kept: {label}")

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        """The preview flashes, so it never looks like the arrangement.

        A generated pattern shown in steady green would be indistinguishable
        from bars that are actually stored, and the whole point of this page is
        that nothing is stored yet.
        """
        bars = self.bars
        existing = self.sample.triggers if self.sample is not None else set()
        blink = self.app.blink
        for pad in range(PAD_COUNT):
            bar = self.app.bar_at(pad)
            if bar in bars:
                pads[pad] = colors.GREEN.index if blink else colors.GREEN_DIM.index
            elif bar in existing:
                # About to be cleared: shown so you can see what you are
                # replacing rather than discovering it afterwards.
                pads[pad] = colors.RED_DIM.index
            else:
                pads[pad] = colors.OFF.index

    def render_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.AUTOMATE] = BTN_BRIGHT
        buttons[Btn.SESSION] = BTN_ON
        buttons[DISPLAY_ROW_BOTTOM[0]] = BTN_ON
        for cc in DISPLAY_ROW_BOTTOM[1:]:
            buttons[cc] = 0

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["PATTERN", "that slot is empty"]
        bars = self.bars
        page_bars = range(self.page_start, self.page_start + PAGE_BARS)
        replacing = len([b for b in sample.triggers if b in page_bars])
        fourth = self._fourth_label()
        lines = [
            f"PATTERN slot {self.slot + 1} {sample.name}   "
            f"page {self.app.page_letter}   {len(bars)} bar(s)",
            f"{ALGORITHM_LABELS[self.algorithm]}   {self.density} of every "
            f"{self.span}   rotate {self.rotation}   {fourth}",
            self._shape_line(bars),
        ]
        if replacing:
            lines.append(
                f"replaces {replacing} bar(s) already on this page "
                f"(dim red) - one Undo puts them back"
            )
        lines.append(
            "1 density  2 rotate  3 algorithm  4 "
            + fourth.split()[0] + "  5 length"
        )
        lines.append("Automate: keep it   Session: discard")
        return lines

    def _fourth_label(self) -> str:
        if self.algorithm == RANDOM:
            return f"seed {self.seed}"
        if self.algorithm == MIRROR:
            mirrored = self.project[self.mirror_slot]
            if mirrored is None or self.mirror_slot == self.slot:
                return "mirror --"
            return f"mirror {self.mirror_slot + 1} {mirrored.name}"
        return "seed n/a"

    def _shape_line(self, bars: set[int]) -> str:
        """The first sixteen bars as characters, so the shape reads as text.

        The grid says this too, but on a display you can read at a glance the
        shape is what you are actually judging -- and it is the one thing that
        survives into a bug report pasted from the simulator.
        """
        width = 16
        body = "".join(
            "x" if (self.page_start + i) in bars else "."
            for i in range(min(width, PAGE_BARS))
        )
        return f"[{body}] first {width} of {PAGE_BARS} bars"
