"""Generated trigger patterns: turn an encoder until the bars are right (IN-03).

Pure functions from a handful of numbers to a set of bar indices. Nothing here
touches a project, a sample or the engine, which is what lets the pattern page
preview live without writing anything: the preview and the commit call the same
function, so what you hear is exactly what gets stored.

Every pattern is a **deterministic function of its settings**. The same
`(algorithm, density, rotation, seed, span)` always gives the same bars, on any
machine, in any session -- so a pattern you liked is reproducible from four
numbers rather than from luck, and `random` is a *seeded* choice rather than a
dice roll you cannot get back.

Four algorithms
---------------
`euclidean` spreads the hits as evenly as the arithmetic allows -- Bjorklund's
algorithm, which is where nearly every traditional rhythm comes from. `every`
places them at a fixed interval, which is the plain answer and often the right
one. `random` picks with a seed. `mirror` copies another slot's bars, so a snare
can answer a kick.

On Bjorklund and the published tables
------------------------------------
"Matches the canonical output" is only a test if the canonical output is
written down, so `tests/test_patterns.py` checks against Toussaint's table from
*The Euclidean Algorithm Generates Traditional Musical Rhythms* -- the one that
names E(3,8) as the Cuban tresillo and E(5,8) as the cinquillo.

Eighteen of twenty-one matched immediately. The three that did not -- E(3,4),
E(5,6), E(7,8) -- are all the case where there is exactly **one rest**: the
grouping loop ends before it can interleave anything, so raw Bjorklund emits
`xxx.` where the table has `x.xx`. Both are the same maximally even *set*,
rotated, but the table is the reference, so that case is handled explicitly.

Fixing it then contradicted a twenty-first entry, E(2,3), which had been
written down from memory as `xx.`. That entry was the error, not the code: the
single-rest family puts its rest second throughout, and an independent
derivation -- a hit at step `i` iff `floor(i*k/n)` differs from
`floor((i-1)*k/n)` -- also gives `x.x`. Two derivations agreeing against one
recollection is the right way round.
"""

from __future__ import annotations

import random as _random

#: The algorithms, in the order the encoder cycles them.
EUCLIDEAN = "euclid"
EVERY = "every"
RANDOM = "random"
MIRROR = "mirror"
ALGORITHMS = (EUCLIDEAN, EVERY, RANDOM, MIRROR)

#: What each is called on the display.
ALGORITHM_LABELS = {
    EUCLIDEAN: "euclid",
    EVERY: "every n",
    RANDOM: "random",
    MIRROR: "mirror",
}

#: Seeds available.  A small set on purpose: the encoder should walk through
#: every one of them in a few turns, so "the one I liked" is findable again.
SEEDS = 64


def bjorklund(hits: int, steps: int) -> list[int]:
    """Maximally even distribution of `hits` over `steps`, as 1s and 0s.

    Checked exhaustively for every ``0 <= hits <= steps <= 64``: the result is
    always `steps` long, holds exactly `hits` ones, starts on a hit whenever
    there is one, and the gaps between consecutive hits never differ by more
    than one step -- which is what "maximally even" means and is the property
    worth testing, rather than only the published examples.
    """
    if steps <= 0 or hits <= 0:
        return [0] * max(0, steps)
    if hits >= steps:
        return [1] * steps
    if steps - hits == 1:
        # One rest: the grouping below ends before interleaving anything and
        # would put the rest last.  The canonical tables put it second.
        return [1, 0] + [1] * (hits - 1)

    groups = [[1] for _ in range(hits)]
    remainder = [[0] for _ in range(steps - hits)]
    while len(remainder) > 1:
        pairs = min(len(groups), len(remainder))
        merged = [groups[i] + remainder[i] for i in range(pairs)]
        leftover = groups[pairs:] if len(groups) > pairs else remainder[pairs:]
        groups, remainder = merged, leftover
        if len(groups) <= 1:
            break
    return [bit for group in groups + remainder for bit in group]


def euclidean(density: int, span: int) -> set[int]:
    """`density` bars spread as evenly as `span` allows."""
    bits = bjorklund(max(0, density), max(0, span))
    return {i for i, bit in enumerate(bits) if bit}


def every_n(density: int, span: int) -> set[int]:
    """`density` bars at a fixed interval, starting at 0.

    The plain answer, and frequently the right one: "every fourth bar" is what
    a person means more often than a maximally even seven-in-sixteen.  The
    interval comes from the density so that one encoder still drives it -- two
    knobs for one idea would be worse.
    """
    density = max(0, min(density, span))
    if density <= 0 or span <= 0:
        return set()
    step = span / density
    return {int(i * step) for i in range(density)}


def random_bars(density: int, span: int, seed: int) -> set[int]:
    """`density` bars chosen by `seed`, the same every time.

    Its own `Random` instance rather than the module's: seeding the global one
    would reach into anything else in the process that uses randomness, and
    this is called on every encoder click.
    """
    density = max(0, min(density, max(0, span)))
    if density <= 0 or span <= 0:
        return set()
    rng = _random.Random(int(seed))
    return set(rng.sample(range(span), density))


def rotate(bars, amount: int, span: int) -> set[int]:
    """Shift a pattern round the span, wrapping.

    A cyclic shift, so the *shape* is preserved: rotating a tresillo gives the
    same rhythm starting somewhere else, which is exactly what you want when
    the pattern is right but the downbeat is wrong.
    """
    if span <= 0:
        return set()
    return {(bar + amount) % span for bar in bars}


def tile(bars, span: int, total: int) -> set[int]:
    """Repeat a `span`-long pattern until it fills `total` bars.

    This is what makes the page musical rather than arithmetic.  Spread three
    bars evenly over a whole 64-bar page and you get a hit every twenty-one
    bars, which is not a rhythm -- it is a rounding error with a downbeat.
    Spread three over eight and repeat it and you get the tresillo, eight
    times, which is what a person turning a density encoder means.
    """
    span = max(1, int(span))
    total = max(0, int(total))
    kept = {bar for bar in bars if 0 <= bar < span}
    return {start + bar
            for start in range(0, total, span)
            for bar in kept
            if start + bar < total}


def generate(algorithm: str, density: int, span: int, rotation: int = 0,
             seed: int = 0, source: set[int] | None = None) -> set[int]:
    """One pattern, from its settings.  The whole public surface.

    `source` is the slot being mirrored, and is required only by `mirror`.
    Anything unknown returns an empty set rather than raising: this runs behind
    an encoder, and a bad algorithm name should not take the page down.
    """
    span = max(0, int(span))
    if span <= 0:
        return set()
    density = max(0, min(int(density), span))
    if algorithm == EUCLIDEAN:
        bars = euclidean(density, span)
    elif algorithm == EVERY:
        bars = every_n(density, span)
    elif algorithm == RANDOM:
        bars = random_bars(density, span, seed)
    elif algorithm == MIRROR:
        bars = {bar for bar in (source or set()) if 0 <= bar < span}
    else:
        return set()
    return rotate(bars, int(rotation), span)
