"""IN-05: the song as a score that never plays the same way twice.

One sample's bars, plus a **variation** -- extra bars it plays on only every Nth
pass. "Every fourth pass, double the hats" is the thing this is for, and the
page shows it as bars you can look at rather than as a rule you have to trust.

It needed far less new machinery than the plan expected, because three earlier
items had already built it:

* `NH-10` gave every trigger a pass divisor, so an extra bar that plays only on
  every 4th pass **is** a trigger with ``every_n`` of 4. The engine learned
  nothing new here.
* `NH-10` also made a pass reproducible from position alone, so a variation is
  reproducible for free -- including in a bounce, which covers a whole pass
  cycle because `passes_needed` counts variation divisors alongside the rest.
* `IN-03` generates the bars, so "double it" is its `euclidean` fill over the
  gaps rather than a second generator.

What is genuinely this item's own work is the page: choosing the divisor,
filling the gaps, saying which pass is next and what changes on it, and
bouncing a chosen number of passes rather than however many the arithmetic
implies.
"""

from __future__ import annotations

from .. import colors
from ..constants import BTN_BRIGHT, BTN_DIM, BTN_ON, DISPLAY_ROW_BOTTOM, ENCODER_TRACK, Btn
from ..history import SetVariation
from ..patterns import EUCLIDEAN, generate
from ..project import MAX_VARIATION_EVERY
from .base import Mode

#: Button that clears the variation.
CLEAR_BUTTON = DISPLAY_ROW_BOTTOM[7]
#: How many passes `Shift`+`Record` renders, and the bounds the encoder keeps.
DEFAULT_PASSES = 4
MIN_PASSES, MAX_BOUNCE_PASSES = 1, 8


class LivingMode(Mode):
    """One sample's arrangement, and what it does differently on some passes."""

    name = "living"

    @property
    def title(self) -> str:
        return f"LIVING {self.slot + 1}"

    def __init__(self, app, slot: int) -> None:
        super().__init__(app)
        self.slot = slot
        #: How many passes `Shift`+`Record` will render.
        self.passes = DEFAULT_PASSES

    @property
    def sample(self):
        return self.project[self.slot]

    def on_enter(self) -> None:
        sample = self.sample
        if sample is None:
            self.app.goto_library()
            return
        if not sample.triggers:
            self.app.notify("arrange the sample first, then come back to vary it")
            return
        self.app.notify(
            f"slot {self.slot + 1}: {self._summary(sample)}"
            "   encoder 1: how often   2: how much"
        )

    # -- the rule ----------------------------------------------------------
    def _summary(self, sample) -> str:
        every = sample.variation_every or 1
        if not sample.variation_bars or every <= 1:
            return "plays the same every pass"
        return (f"{len(sample.variation_bars)} extra bar(s) "
                f"every {every} passes")

    def _fill(self, sample, count: int) -> set:
        """`count` extra bars, spread evenly through the **gaps** (IN-03's job).

        The gaps, not the span, and that distinction was a bug before it was a
        docstring: spreading a euclidean pattern over the span a hat already
        occupies puts the new bars on top of the old ones -- for hats on bars
        1, 3, 5, 7 the fill landed on bar 1 and then subtracted away to nothing.
        So the free bars inside the part are listed first and the pattern
        chooses among *those*, which is also what "double it" means.

        Inside the part rather than across the page, so a fill lands where the
        music is.
        """
        if not sample.triggers or count <= 0:
            return set()
        low, high = min(sample.triggers), max(sample.triggers)
        free = [bar for bar in range(low, high + 1) if bar not in sample.triggers]
        if not free:
            # A solid block has no gaps to fill; extend past the end instead,
            # which is the only room left and is what a fill after a phrase is.
            free = [high + 1 + step for step in range(count)]
            free = [bar for bar in free if bar < self.project.song_bars]
        wanted = generate(EUCLIDEAN, min(count, len(free)), max(1, len(free)))
        return {free[index] for index in sorted(wanted) if index < len(free)}

    def _set(self, every: int, amount: int) -> None:
        """Install a variation, or clear it when there is nothing to vary."""
        sample = self.sample
        if sample is None:
            return
        every = max(0, min(MAX_VARIATION_EVERY, every))
        bars = self._fill(sample, amount) if every > 1 and amount > 0 else set()
        if bars == sample.variation_bars and every == sample.variation_every:
            return
        self.app.do(SetVariation(self.slot, bars, every,
                                 set(sample.variation_bars),
                                 sample.variation_every))
        self.app.notify(self._summary(sample))

    # -- input -------------------------------------------------------------
    def on_encoder(self, cc: int, delta: int) -> bool:
        sample = self.sample
        if sample is None:
            return False
        if cc == ENCODER_TRACK[0]:
            # How often: off, then every 2..8 passes.
            current = sample.variation_every or 1
            self._set(max(1, min(MAX_VARIATION_EVERY, current + delta)),
                      max(1, len(sample.variation_bars)))
            return True
        if cc == ENCODER_TRACK[1]:
            # How much: how many extra bars the fill adds.
            amount = max(0, len(sample.variation_bars) + delta)
            self._set(sample.variation_every or DEFAULT_PASSES, amount)
            return True
        if cc == ENCODER_TRACK[2]:
            self.passes = max(MIN_PASSES,
                              min(MAX_BOUNCE_PASSES, self.passes + delta))
            self.app.notify(f"Shift+Record renders {self.passes} pass(es)")
            return True
        return False

    def on_pad(self, index: int, pressed: bool, velocity: int) -> bool:
        """A pad toggles whether that bar is part of the variation.

        Only bars the arrangement does not already use: a bar that plays every
        pass is not a variation of anything, and letting a press mean two
        different things depending on what is underneath is how a grid stops
        being readable.
        """
        if not pressed:
            return True
        sample = self.sample
        if sample is None:
            return True
        bar = self.app.bar_at(index)
        if bar in sample.triggers:
            self.app.notify(f"bar {bar + 1} already plays every pass")
            return True
        bars = set(sample.variation_bars)
        bars.symmetric_difference_update({bar})
        every = sample.variation_every or DEFAULT_PASSES
        self.app.do(SetVariation(self.slot, bars, every if bars else 0,
                                 set(sample.variation_bars),
                                 sample.variation_every))
        return True

    def on_button(self, cc: int, pressed: bool) -> bool:
        if not pressed:
            return False
        sample = self.sample
        if cc == CLEAR_BUTTON and sample is not None:
            if not sample.variation_bars:
                self.app.notify("no variation to clear")
            else:
                self._set(0, 0)
            return True
        if cc == Btn.RECORD and self.app.shift:
            self._bounce()
            return True
        if cc in (Btn.CLIP, Btn.SESSION, Btn.LEFT, Btn.NOTE):
            self.app.pop_mode()
            return True
        return False

    def _bounce(self):
        """Freeze this many passes as audio (IN-05's one-button freeze).

        The count is chosen here rather than derived, which is the one place
        this item disagrees with `passes_needed`: that answers "how long before
        the song repeats", and what a person wants from a freeze is "give me
        four times round", which may be more or fewer.
        """
        if not self.app.start_bounce(passes=self.passes):
            return
        self.app.notify(f"freezing {self.passes} pass(es)...")

    # -- output ------------------------------------------------------------
    def render_pads(self, pads: list[int]) -> None:
        sample = self.sample
        if sample is None:
            return
        playhead = self.engine.current_bar if self.engine.is_playing else -1
        due = self._variation_due()
        coming = self._next_due() == 1
        for index in range(len(pads)):
            bar = self.app.bar_at(index)
            if bar in sample.triggers:
                pads[index] = colors.GREEN.index
            elif bar in sample.variation_bars:
                # Amber on the pass it plays, dim blue while it waits, and
                # *flashing* on the pass immediately before -- which is the
                # display of "what is about to change" the plan asked for.
                # Flashing whenever it was merely not due made "about to" and
                # "eventually" the same pixel.
                if due:
                    pads[index] = colors.AMBER.index
                elif coming and self.app.blink:
                    pads[index] = colors.AMBER.index
                else:
                    pads[index] = colors.BLUE_DIM.index
            if bar == playhead:
                pads[index] = colors.WHITE.index
        return

    def _variation_due(self) -> bool:
        """Whether the pass now running is one the variation plays on."""
        sample = self.sample
        every = (sample.variation_every or 1) if sample else 1
        if every <= 1:
            return True
        return self.engine.pass_number % every == 0

    def _next_due(self) -> int:
        """How many passes until the variation next plays; 0 when it is now."""
        sample = self.sample
        every = (sample.variation_every or 1) if sample else 1
        if every <= 1 or not sample.variation_bars:
            return 0
        return (-self.engine.pass_number) % every

    def render_buttons(self, buttons: dict) -> None:
        buttons[Btn.SESSION] = BTN_ON
        buttons[Btn.CLIP] = BTN_BRIGHT
        sample = self.sample
        has = bool(sample and sample.variation_bars)
        buttons[CLEAR_BUTTON] = BTN_ON if has else BTN_DIM
        buttons[Btn.RECORD] = colors.RED_DIM.index

    def status_lines(self) -> list[str]:
        sample = self.sample
        if sample is None:
            return ["LIVING", "nothing in that slot"]
        every = sample.variation_every or 1
        lines = [
            f"LIVING slot {self.slot + 1} {sample.name}"
            f"   {len(sample.triggers)} bar(s) always   "
            f"{len(sample.variation_bars)} sometimes",
            self._summary(sample),
        ]
        if sample.variation_bars and every > 1:
            due = self._next_due()
            when = ("this pass" if due == 0 else
                    "next pass" if due == 1 else f"in {due} passes")
            lines.append(
                f"pass {self.engine.pass_number}   "
                f"the extra bars play {when}"
            )
        else:
            lines.append("a pad adds a bar the variation plays on")
        lines.append(
            "encoder 1: how often   2: how much   "
            f"3: passes to freeze ({self.passes})"
        )
        lines.append(
            "green plays every pass   amber is about to play   "
            "dim blue waits its turn"
        )
        lines.append("Shift+Record: freeze it as audio   button 8: clear   Clip: leave")
        return lines
