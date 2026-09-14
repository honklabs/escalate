"""IN-03: generated trigger patterns.

The pattern functions are pure, so they are tested as arithmetic: against
Toussaint's published table of Euclidean rhythms, and then exhaustively for the
properties that table is only a sample of.

`CANONICAL` below is the reference, and getting it right was itself the
interesting part. Eighteen of its twenty-one entries matched a plain Bjorklund
implementation. The three that did not -- E(3,4), E(5,6), E(7,8) -- are all the
single-rest case, where the grouping loop ends before it can interleave and the
rest lands last instead of second. Handling that then contradicted E(2,3),
which had been written down from memory as `xx.`; the memory was wrong, and two
independent derivations agree on `x.x`. The moral is in the exhaustive tests:
a published example is a spot check, and the *property* is what you test.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from push2sampler.audio import Engine
from push2sampler.constants import DISPLAY_ROW_BOTTOM, ENCODER_TRACK, Btn
from push2sampler.modes.pattern import (
    DEFAULT_DENSITY,
    DEFAULT_SPAN,
    MIN_SPAN,
    PatternMode,
)
from push2sampler.patterns import (
    ALGORITHM_LABELS,
    ALGORITHMS,
    EUCLIDEAN,
    EVERY,
    MIRROR,
    RANDOM,
    SEEDS,
    bjorklund,
    euclidean,
    every_n,
    generate,
    random_bars,
    rotate,
    tile,
)
from push2sampler.project import PAGE_BARS, Project, Sample
from push2sampler.push2 import SimPush
from push2sampler.settings import Settings

#: Toussaint 2005, *The Euclidean Algorithm Generates Traditional Musical
#: Rhythms*: E(k, n) and the rhythm it is.  E(3,8) is the Cuban tresillo and
#: E(5,8) the cinquillo, which is the point -- these are not arbitrary.
CANONICAL = [
    (2, 3, "x.x"),
    (2, 5, "x.x.."),
    (3, 4, "x.xx"),
    (3, 5, "x.x.x"),
    (3, 8, "x..x..x."),                        # tresillo
    (4, 7, "x.x.x.x"),
    (4, 9, "x.x.x.x.."),
    (4, 11, "x..x..x..x."),
    (5, 6, "x.xxxx"),
    (5, 7, "x.xx.xx"),
    (5, 8, "x.xx.xx."),                        # cinquillo
    (5, 9, "x.x.x.x.x"),
    (5, 11, "x.x.x.x.x.."),
    (5, 12, "x..x.x..x.x."),
    (5, 16, "x..x..x..x..x..."),
    (7, 8, "x.xxxxxx"),
    (7, 12, "x.xx.x.xx.x."),
    (7, 16, "x..x.x.x..x.x.x."),
    (9, 16, "x.xx.x.x.xx.x.x."),
    (11, 24, "x..x.x.x.x.x..x.x.x.x.x."),
    (13, 24, "x.xx.x.x.x.x.xx.x.x.x.x."),
]

SR = 8000


def show(bars, span: int) -> str:
    return "".join("x" if i in bars else "." for i in range(span))


# ==================================================== euclidean, against the table
@pytest.mark.parametrize("hits,steps,want", CANONICAL,
                         ids=[f"E({k},{n})" for k, n, _ in CANONICAL])
def test_euclidean_matches_the_published_rhythm(hits, steps, want):
    assert show(euclidean(hits, steps), steps) == want


def test_bjorklund_and_euclidean_agree():
    """One is the bits and the other the set; they must not drift apart."""
    for steps in range(1, 33):
        for hits in range(0, steps + 1):
            bits = bjorklund(hits, steps)
            assert euclidean(hits, steps) == {i for i, b in enumerate(bits) if b}


# ==================================================== the properties, exhaustively
@pytest.mark.parametrize("steps", list(range(1, 65)))
def test_bjorklund_is_the_right_length_and_count(steps):
    """A published example is a spot check; this is the property."""
    for hits in range(0, steps + 1):
        bits = bjorklund(hits, steps)
        assert len(bits) == steps
        assert sum(bits) == hits


def test_a_pattern_with_hits_always_starts_on_one():
    """Otherwise the downbeat is silent and the rotation control is a lie."""
    for steps in range(1, 65):
        for hits in range(1, steps + 1):
            assert bjorklund(hits, steps)[0] == 1, (hits, steps)


def test_euclidean_is_maximally_even():
    """The gaps between consecutive hits differ by at most one step.

    This is what "maximally even" *means*, and it holds for every (k, n) the
    page can produce -- which the twenty-one published examples cannot show.
    """
    uneven = []
    for steps in range(2, 65):
        for hits in range(2, steps):
            positions = sorted(euclidean(hits, steps))
            gaps = [(positions[(i + 1) % hits] - positions[i]) % steps
                    for i in range(hits)]
            if max(gaps) - min(gaps) > 1:
                uneven.append((hits, steps, sorted(set(gaps))))
    assert uneven == []


@pytest.mark.parametrize("hits,steps", [(0, 8), (0, 0), (8, 8), (9, 8), (-1, 8),
                                        (3, 0), (3, -4)])
def test_degenerate_arguments_do_not_raise(hits, steps):
    """These run behind an encoder, so they answer rather than throw."""
    bits = bjorklund(hits, steps)
    assert all(bit in (0, 1) for bit in bits)


# ==================================================== the other algorithms
def test_every_n_is_a_fixed_interval():
    assert show(every_n(4, 16), 16) == "x...x...x...x..."
    assert show(every_n(2, 8), 8) == "x...x..."
    assert show(every_n(8, 8), 8) == "xxxxxxxx"
    assert every_n(0, 16) == set()


def test_every_n_and_euclid_agree_when_the_division_is_exact():
    """4 in 16 is unambiguous; the two should not differ on the easy cases."""
    for hits, steps in ((2, 8), (4, 16), (8, 32), (1, 4)):
        assert every_n(hits, steps) == euclidean(hits, steps), (hits, steps)


def test_the_same_seed_gives_the_same_pattern():
    """The plan's test, and what makes `random` usable rather than a dice roll."""
    for seed in range(8):
        first = random_bars(5, 16, seed)
        assert first == random_bars(5, 16, seed)
        assert len(first) == 5


def test_different_seeds_give_different_patterns():
    patterns = {frozenset(random_bars(5, 16, seed)) for seed in range(SEEDS)}
    # Not all 64 need differ, but a handful of duplicates would mean the seed
    # is barely doing anything.
    assert len(patterns) > SEEDS * 0.8


def test_random_does_not_touch_the_global_generator():
    """Seeding the module-level RNG would reach into the whole process."""
    random.seed(1)
    before = random.random()
    random_bars(5, 16, 42)
    random.seed(1)
    assert random.random() == before


def test_mirror_copies_and_clips():
    assert generate(MIRROR, 0, 16, source={1, 5, 9}) == {1, 5, 9}
    assert generate(MIRROR, 0, 8, source={1, 5, 99}) == {1, 5}
    assert generate(MIRROR, 0, 16, source=None) == set()


def test_an_unknown_algorithm_is_empty_rather_than_an_exception():
    assert generate("harmonium", 4, 16) == set()


# ==================================================== rotation and tiling
def test_rotation_is_a_cyclic_shift():
    """The plan's test.  The *shape* has to survive, or it is not a rotation."""
    tresillo = euclidean(3, 8)
    assert show(rotate(tresillo, 1, 8), 8) == ".x..x..x"
    assert show(rotate(tresillo, 2, 8), 8) == "x.x..x.."
    assert rotate(tresillo, 8, 8) == tresillo
    assert rotate(tresillo, -1, 8) == rotate(tresillo, 7, 8)


def test_rotation_never_changes_how_many_bars_there_are():
    for span in (4, 8, 12, 16, 64):
        for hits in range(1, span):
            bars = euclidean(hits, span)
            for amount in range(span):
                assert len(rotate(bars, amount, span)) == hits


def test_tiling_repeats_the_pattern():
    """The control the plan did not ask for, and the page is useless without.

    Three bars spread over a whole 64-bar page is one hit every twenty-one
    bars.  Three over eight, repeated, is the tresillo eight times.
    """
    assert show(tile(euclidean(3, 8), 8, 32), 32) == (
        "x..x..x." * 4
    )
    assert len(tile(euclidean(3, 8), 8, 64)) == 24
    # And the ungenerous case the page can reach:
    assert show(tile(euclidean(3, 64), 64, 64), 32) == (
        "x" + "." * 20 + "x" + "." * 10
    )


def test_tiling_a_span_that_does_not_divide_the_page_stops_at_the_edge():
    """64 is not a multiple of 12; the last repeat is cut, not wrapped."""
    bars = tile({0, 5}, 12, 64)
    assert max(bars) < 64
    assert 60 in bars          # the sixth repeat's first bar
    assert 65 not in bars


def test_tiling_degenerate_spans():
    assert tile({0}, 0, 16) == set(range(16))   # span clamps to 1
    assert tile({0, 3}, 8, 0) == set()
    assert tile({0, 99}, 8, 16) == {0, 8}       # out-of-span bars dropped


# ==================================================== the page
@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    per_bar = int(project.frames_per_bar)
    audio = np.full((per_bar, 1), 0.4, dtype=np.float32)
    kick = Sample(slot=0, bars=1, audio=audio, name="kick")
    kick.set_trigger(3, True)
    kick.set_trigger(17, True, velocity=64)
    project.install(0, kick)
    snare = Sample(slot=1, bars=1, audio=audio.copy(), name="snare")
    for bar in (2, 6, 10, 14):
        snare.set_trigger(bar, True)
    project.install(1, snare)

    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=120.0, song_bars=project.song_bars)
    from push2sampler.app import App

    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


def pump(rig):
    app, push = rig[0], rig[1]
    for event in push.poll_events():
        app.handle(event)


def open_pattern(rig, slot=0):
    app, push = rig[0], rig[1]
    app.goto_sample(slot)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    return app.mode


def test_automate_on_a_sample_page_opens_the_pattern_page(rig):
    mode = open_pattern(rig)
    assert isinstance(mode, PatternMode)
    assert mode.title == "PATTERN 1"


def test_automate_does_nothing_on_an_empty_slot(rig):
    app, push, _engine, _project = rig
    app.goto_library()
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert app.mode.name == "library"


def test_the_page_opens_on_something_ordinary(rig):
    """Four hits in sixteen bars, repeating: a bar every four."""
    mode = open_pattern(rig)
    assert mode.span == DEFAULT_SPAN
    assert mode.density == DEFAULT_DENSITY
    assert mode.algorithm == EUCLIDEAN
    assert len(mode.bars) == 16
    assert sorted(mode.bars)[:4] == [0, 4, 8, 12]


def test_the_preview_changes_nothing(rig):
    """The whole point of a preview, asserted rather than assumed."""
    app, push, _engine, project = rig
    before = (set(project[0].triggers), dict(project[0].velocities))
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[0], 5)
    pump(rig)
    push.turn(ENCODER_TRACK[2], 1)
    pump(rig)
    push.turn(ENCODER_TRACK[4], -8)
    pump(rig)
    for pad in (0, 12, 63):
        push.press_pad(pad)
        pump(rig)
    mode.render_pads([0] * 64)
    assert (set(project[0].triggers), dict(project[0].velocities)) == before
    assert not app.history.can_undo


def test_a_pad_press_says_the_grid_is_a_preview(rig):
    """Editing a bar here would be wiped by the next encoder click."""
    app, push, _engine, _project = rig
    open_pattern(rig)
    push.press_pad(0)
    pump(rig)
    assert "preview" in app.message


def test_the_density_encoder_changes_how_many_bars(rig):
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[0], -1)
    pump(rig)
    assert mode.density == 3
    assert "3 of every 16" in app.message


def test_density_is_clamped_to_the_pattern_length(rig):
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[0], 100)
    pump(rig)
    assert mode.density == mode.span
    push.turn(ENCODER_TRACK[0], -100)
    pump(rig)
    assert mode.density == 0
    assert mode.bars == set()


def test_shortening_the_pattern_clamps_the_density_with_it(rig):
    """A density of 12 inside a span of 4 would silently mean "every bar"."""
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[0], 8)
    pump(rig)
    assert mode.density == 12
    push.turn(ENCODER_TRACK[4], -12)
    pump(rig)
    assert mode.span == 4
    assert mode.density == 4


def test_the_length_encoder_makes_it_a_rhythm(rig):
    """The difference this control makes, as a number."""
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    mode.density = 3
    mode.span = PAGE_BARS
    sparse = len(mode.bars)
    mode.span = 8
    repeating = len(mode.bars)
    assert sparse == 3
    assert repeating == 24


def test_the_length_encoder_is_clamped(rig):
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[4], -100)
    pump(rig)
    assert mode.span == MIN_SPAN
    push.turn(ENCODER_TRACK[4], 500)
    pump(rig)
    assert mode.span == PAGE_BARS


def test_rotation_wraps_within_the_pattern_not_the_page(rig):
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[4], -8)          # span 8
    pump(rig)
    push.turn(ENCODER_TRACK[1], 8)
    pump(rig)
    assert mode.rotation == 0                 # a full turn of an 8-bar pattern


def test_the_algorithm_encoder_cycles_all_four(rig):
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    seen = [mode.algorithm]
    for _ in range(3):
        push.turn(ENCODER_TRACK[2], 1)
        pump(rig)
        seen.append(mode.algorithm)
    assert set(seen) == set(ALGORITHMS)
    push.turn(ENCODER_TRACK[2], 1)
    pump(rig)
    assert mode.algorithm == seen[0]          # and wraps


def test_button_one_also_cycles_the_algorithm(rig):
    """The encoder is exact; a button is what a hand reaches for."""
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    before = mode.algorithm
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    assert mode.algorithm != before


def test_the_fourth_encoder_is_the_seed_for_random(rig):
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    mode.algorithm = RANDOM
    push.turn(ENCODER_TRACK[3], 3)
    pump(rig)
    assert mode.seed == 3
    assert "seed 3" in app.message
    first = set(mode.bars)
    push.turn(ENCODER_TRACK[3], -3)
    pump(rig)
    push.turn(ENCODER_TRACK[3], 3)
    pump(rig)
    assert set(mode.bars) == first            # the same seed, the same bars


def test_the_fourth_encoder_says_when_it_does_nothing(rig):
    """It drives two things and neither applies to euclid."""
    app, push, _engine, _project = rig
    mode = open_pattern(rig)
    assert mode.algorithm == EUCLIDEAN
    push.turn(ENCODER_TRACK[3], 2)
    pump(rig)
    assert mode.seed == 0
    assert "no seed" in app.message


def test_mirror_starts_on_a_filled_slot_and_copies_it(rig):
    """"Answer the thing I just made" is the reason to mirror at all."""
    app, push, _engine, project = rig
    mode = open_pattern(rig)
    assert mode.mirror_slot == 1
    mode.algorithm = MIRROR
    assert mode.bars == set(project[1].triggers)


def test_mirror_ignores_the_length_control(rig):
    """Tiling someone else's rhythm would be inventing one, not answering it."""
    app, _push, _engine, project = rig
    mode = open_pattern(rig)
    mode.algorithm = MIRROR
    mode.span = 4
    assert mode.bars == set(project[1].triggers)


def test_mirror_walks_to_the_next_filled_slot(rig):
    app, push, _engine, project = rig
    project.install(5, Sample(slot=5, bars=1, name="clap",
                              audio=np.zeros((100, 1), dtype=np.float32)))
    mode = open_pattern(rig)
    mode.algorithm = MIRROR
    push.turn(ENCODER_TRACK[3], 1)
    pump(rig)
    assert mode.mirror_slot == 5
    assert "clap" in app.message


def test_mirror_with_nothing_else_filled_says_so(rig):
    app, push, _engine, project = rig
    project.install(1, None)
    mode = open_pattern(rig)
    assert mode.mirror_slot == 0              # itself: nothing else is filled
    mode.algorithm = MIRROR
    assert mode.bars == set()
    push.turn(ENCODER_TRACK[3], 1)
    pump(rig)
    assert "no other filled slot" in app.message


# ==================================================== committing
def test_automate_keeps_the_pattern_as_one_undo_step(rig):
    app, push, _engine, project = rig
    open_pattern(rig)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert sorted(project[0].triggers)[:4] == [0, 4, 8, 12]
    assert len(project[0].triggers) == 16
    assert app.mode.name == "sample"
    app.undo()
    assert set(project[0].triggers) == {3, 17}


def test_undo_restores_the_velocities_too(rig):
    """A generated pattern has no opinion about velocity; undo must not lose it."""
    app, push, _engine, project = rig
    assert project[0].velocities.get(17) == 64
    open_pattern(rig)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    app.undo()
    assert project[0].velocities.get(17) == 64


def test_committing_replaces_rather_than_adds(rig):
    """Otherwise the preview is a lie: you would see 16 bars and get 18."""
    app, push, _engine, project = rig
    mode = open_pattern(rig)
    previewed = set(mode.bars)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert set(project[0].triggers) == previewed


def test_committing_leaves_the_other_pages_alone(rig):
    """Patterning page A must not silently rewrite page D."""
    app, push, _engine, project = rig
    project.pages = 4
    project[0].set_trigger(200, True)
    open_pattern(rig)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert 200 in project[0].triggers


def test_session_discards(rig):
    app, push, _engine, project = rig
    open_pattern(rig)
    push.press_button(Btn.SESSION)
    pump(rig)
    assert set(project[0].triggers) == {3, 17}
    assert app.mode.name == "sample"
    assert "discarded" in app.message


def test_committing_the_pattern_that_is_already_there_says_so(rig):
    app, push, _engine, project = rig
    open_pattern(rig)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    open_pattern(rig)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert "already the pattern" in app.message


def test_an_empty_pattern_is_committable(rig):
    """Density zero is a legitimate answer: it clears the page."""
    app, push, _engine, project = rig
    mode = open_pattern(rig)
    push.turn(ENCODER_TRACK[0], -100)
    pump(rig)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert set(project[0].triggers) == set()
    app.undo()
    assert set(project[0].triggers) == {3, 17}


# ==================================================== rendering
def test_the_preview_flashes_so_it_is_not_mistaken_for_the_arrangement(rig,
                                                                       monkeypatch):
    """Steady green would be indistinguishable from bars that are stored.

    `App.blink` is a 2 Hz square wave off the clock, so the two phases are
    driven by moving the clock rather than by waiting a quarter of a second --
    a test that sleeps is a test that is sometimes flaky.
    """
    from push2sampler import colors
    import push2sampler.app as app_module

    app, _push, _engine, _project = rig
    mode = open_pattern(rig)
    phases = {}
    for name, now in (("on", 0.0), ("off", 0.25)):
        monkeypatch.setattr(app_module.time, "monotonic", lambda now=now: now)
        assert app.blink is (name == "on")
        pads = [0] * 64
        mode.render_pads(pads)
        phases[name] = pads[0]
    assert phases["on"] == colors.GREEN.index
    assert phases["off"] == colors.GREEN_DIM.index


def test_bars_about_to_be_cleared_are_shown(rig):
    """So you see what you are replacing rather than discovering it after."""
    from push2sampler import colors

    app, _push, _engine, _project = rig
    mode = open_pattern(rig)
    pads = [0] * 64
    mode.render_pads(pads)
    # Bar 3 is a hand-made trigger and is not in the default pattern.
    assert 3 not in mode.bars
    assert pads[3] == colors.RED_DIM.index


def test_the_status_lines_name_every_control(rig):
    app, _push, _engine, _project = rig
    mode = open_pattern(rig)
    text = " ".join(mode.status_lines())
    for word in ("density", "rotate", "algorithm", "length", "Automate", "Session"):
        assert word in text, word
    assert "replaces 2 bar(s)" in text


def test_the_shape_line_reads_as_the_rhythm(rig):
    app, _push, _engine, _project = rig
    mode = open_pattern(rig)
    mode.span, mode.density = 8, 3
    assert "[x..x..x.x..x..x.]" in mode._shape_line(mode.bars)


def test_the_page_survives_the_slot_emptying_under_it(rig):
    app, push, _engine, project = rig
    mode = open_pattern(rig)
    project.install(0, None)
    assert mode.status_lines()[0] == "PATTERN"
    mode.render_pads([0] * 64)
    push.press_button(Btn.AUTOMATE)
    pump(rig)
    assert "empty" in app.message


def test_every_algorithm_has_a_label(rig):
    assert set(ALGORITHM_LABELS) == set(ALGORITHMS)
    for name in ALGORITHMS:
        assert ALGORITHM_LABELS[name]
