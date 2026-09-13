"""IN-01: one take becomes a kit.

Two halves, tested differently.

The **detector** is measured against signals whose onset frames were chosen
rather than guessed, so "within 5 ms" is a fact. Those tests are the record of
what five rounds of prototyping established, and each of the negative ones
(silence, white noise, a held tone) is a bug the first version actually had.

The **page** is tested through the surface, because every interesting thing
about it is a refusal: not enough free slots, nothing worth slicing, a
sensitivity encoder that does nothing in two of the three modes.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler import analysis
from push2sampler.analysis import (
    MAX_SLICES,
    STRUCTURE_MIN,
    even_slices,
    novelty,
    onsets,
    slice_buffers,
)
from push2sampler.audio import Engine
from push2sampler.constants import DISPLAY_ROW_BOTTOM, ENCODER_TRACK, Btn
from push2sampler.modes.slice import BY_BARS, BY_BEATS, BY_TRANSIENTS, SliceMode
from push2sampler.project import SLOT_COUNT, Project, Sample
from push2sampler.push2 import SimPush
from push2sampler.settings import Settings

SR = 48000


# ==================================================== signals with known onsets
def clicks(positions, length, sr=SR, decay=400.0, level=1.0):
    """Noise bursts at exactly `positions`: a drum take, near enough."""
    out = np.zeros((length, 1), dtype=np.float32)
    tail = np.arange(int(sr * 0.05)) / sr
    env = np.exp(-tail * decay)
    rng = np.random.default_rng(7)
    for p in positions:
        hit = (rng.normal(0, 0.4, len(tail)) * env * level).astype(np.float32)
        end = min(length, p + len(tail))
        out[p:end, 0] += hit[: end - p]
    return out


def worst_error(truth, found, sr=SR):
    """Milliseconds, matching each true onset to its nearest detection."""
    remaining = list(found)
    worst = 0.0
    for p in truth:
        if not remaining:
            return float("inf")
        best = min(remaining, key=lambda f: abs(f - p))
        remaining.remove(best)
        worst = max(worst, abs(best - p) / sr * 1000.0)
    return worst


# ==================================================== the detector
def test_a_click_train_is_found_within_five_milliseconds():
    """The plan's own acceptance test, and the reason refinement exists.

    Before the frame index was refined against the signal, every onset came
    back 10-15 ms EARLY -- the analysis window's start rather than the hit
    inside it -- so this could not have passed at any setting.
    """
    length = int(SR * 4)
    step = int(SR * 0.125)
    truth = [i * step for i in range(1, 32)]
    found = onsets(clicks(truth, length), SR)
    assert len(found) == len(truth)
    assert worst_error(truth, found) <= 5.0


def test_a_quiet_take_is_found_just_as_well():
    """The threshold is relative, so level must not change the answer."""
    length = int(SR * 4)
    step = int(SR * 0.125)
    truth = [i * step for i in range(1, 32)]
    quiet = clicks(truth, length, level=0.2)
    quiet = quiet + np.random.default_rng(1).normal(
        0, 0.01, quiet.shape
    ).astype(np.float32)
    found = onsets(quiet, SR)
    assert len(found) == len(truth)
    assert worst_error(truth, found) <= 5.0


def test_a_ghost_note_is_not_lost():
    """A hit at a tenth the level is a ghost note, not noise.

    This is the test that killed a global prominence floor: it would have made
    the quiet hit vanish, and losing a ghost note is the one thing a drum
    slicer must not do.
    """
    length = int(SR * 4)
    step = int(SR * 0.125)
    truth = [i * step for i in range(1, 9)]
    loud = clicks([p for i, p in enumerate(truth) if i != 3], length)
    ghost = clicks([truth[3]], length, level=0.1)
    for sensitivity in (0.0, 0.5, 1.0):
        found = onsets(loud + ghost, SR, sensitivity=sensitivity)
        assert worst_error(truth, found) <= 5.0, sensitivity


def test_two_hits_fifty_milliseconds_apart_are_two_hits():
    length = int(SR * 4)
    truth = [int(SR * 0.9), int(SR * 0.95)]
    found = onsets(clicks(truth, length), SR)
    assert len(found) == 2
    assert worst_error(truth, found) <= 5.0


def test_hits_closer_than_the_minimum_gap_are_one_hit():
    """Below about 30 ms a flam is one attack, and two slices would be wrong."""
    length = int(SR * 2)
    found = onsets(clicks([int(SR * 0.5), int(SR * 0.5) + 200], length), SR)
    assert len(found) == 1


@pytest.mark.parametrize("what", ["silence", "noise", "tone"])
def test_material_with_no_attacks_yields_no_onsets(what):
    """A held 440 Hz tone produced 59 onsets before STRUCTURE_MIN existed.

    A sine that is not bin-centred leaks, the leakage wobbles frame to frame,
    and dividing the flux curve by its own maximum turned that wobble into
    full-scale signal.
    """
    length = int(SR * 3)
    if what == "silence":
        buf = np.zeros((length, 1), dtype=np.float32)
    elif what == "noise":
        buf = np.random.default_rng(4).normal(0, 0.1, (length, 1)).astype(np.float32)
    else:
        buf = np.sin(
            2 * np.pi * 440 * np.arange(length) / SR
        ).astype(np.float32).reshape(-1, 1)
    assert onsets(buf, SR) == []


def test_the_structure_gate_separates_a_tone_from_a_take():
    """The numbers STRUCTURE_MIN sits between, so moving it is a decision."""
    length = int(SR * 3)
    tone = np.sin(2 * np.pi * 440 * np.arange(length) / SR).astype(np.float32)
    drums = clicks([int(SR * 0.2 * i) for i in range(1, 14)], length)

    def ratio(buf):
        curve = novelty(buf)
        return float(curve.max()) / max(float(np.median(curve)), 1e-9)

    assert ratio(tone.reshape(-1, 1)) < STRUCTURE_MIN
    assert ratio(drums) > STRUCTURE_MIN


def test_sensitivity_trades_missed_hits_for_false_ones():
    """The knob has to actually turn, in the direction it says."""
    length = int(SR * 4)
    truth = [int(SR * 0.2 * i) for i in range(1, 19)]
    buf = clicks(truth, length, level=0.3)
    strict = len(onsets(buf, SR, sensitivity=0.0))
    loose = len(onsets(buf, SR, sensitivity=1.0))
    assert strict <= loose


@pytest.mark.parametrize("buf", [
    None,
    np.zeros((0, 1), dtype=np.float32),
    np.zeros((1, 1), dtype=np.float32),
    np.zeros((3, 2), dtype=np.float32),
])
def test_a_degenerate_buffer_returns_nothing_rather_than_raising(buf):
    """This is called from a UI: "nothing" is usable, an exception is not."""
    assert onsets(buf, SR) == []


def test_mono_and_stereo_agree():
    length = int(SR * 2)
    truth = [int(SR * 0.25 * i) for i in range(1, 8)]
    mono = clicks(truth, length)
    stereo = np.repeat(mono, 2, axis=1)
    assert onsets(mono, SR) == onsets(stereo, SR)
    # And a plain 1-D array, which is what a bare recording looks like.
    assert onsets(mono[:, 0], SR) == onsets(mono, SR)


def test_the_limit_keeps_the_loudest_but_in_time_order():
    """A kit from the *first* 64 of 200 hits would stop halfway through."""
    length = int(SR * 6)
    truth = [int(SR * 0.05 * i) for i in range(1, 100)]
    found = onsets(clicks(truth, length), SR, limit=8)
    assert len(found) <= 8
    assert found == sorted(found)
    # Spread across the take rather than bunched at the front.
    assert found[-1] > length * 0.5


def test_the_default_limit_is_a_gridful():
    assert MAX_SLICES == 64


# ==================================================== even slicing
def test_equal_slicing_of_eight_bars_gives_eight_of_the_same_length():
    """The plan's second acceptance test."""
    project = Project(samplerate=SR, bpm=120.0)
    per_bar = int(project.frames_per_bar)
    audio = np.zeros((per_bar * 8, 1), dtype=np.float32)
    pieces = slice_buffers(audio, even_slices(audio.shape[0], 8))
    assert len(pieces) == 8
    assert {len(p) for p in pieces} == {per_bar}


def test_even_slices_cannot_drift_off_the_end():
    """Rounded from the exact division each time, never accumulated."""
    for total in (1000, 44_100, 999_983):
        for count in (3, 7, 64):
            points = even_slices(total, count)
            assert len(points) == count
            assert points[0] == 0
            assert points[-1] < total


def test_even_slices_survives_nonsense():
    assert even_slices(0, 4) == [0]
    assert even_slices(100, 0) == [0]
    assert even_slices(-5, 3) == [0]


def test_slicing_keeps_every_sample_exactly_once():
    audio = np.arange(1000, dtype=np.float32).reshape(-1, 1)
    pieces = slice_buffers(audio, [0, 250, 700])
    assert [len(p) for p in pieces] == [250, 450, 300]
    assert np.array_equal(np.concatenate(pieces), audio)


def test_slicing_tolerates_duplicate_and_out_of_range_points():
    audio = np.arange(10, dtype=np.float32).reshape(-1, 1)
    pieces = slice_buffers(audio, [0, 0, 5, 9999, -3])
    assert [len(p) for p in pieces] == [5, 5]


def test_slices_are_views_until_something_writes():
    """Slicing an eight-bar take must not cost eight copies of it."""
    audio = np.arange(100, dtype=np.float32).reshape(-1, 1)
    pieces = slice_buffers(audio, [0, 50])
    assert all(p.base is not None for p in pieces)


def test_the_post_take_helpers_still_work():
    """analysis.py is shared with NH-08 and this must not have disturbed it."""
    audio = np.zeros((SR, 1), dtype=np.float32)
    audio[480:] = 0.5
    assert analysis.first_transient(audio, SR) == 480
    assert analysis.peak(audio) == pytest.approx(0.5)
    assert analysis.normalize(audio).max() == pytest.approx(analysis.TARGET_PEAK)


# ==================================================== the page
RIG_SR = 8000


@pytest.fixture
def rig(tmp_path):
    """A project holding one eight-bar take of quarter-note hits."""
    project = Project(samplerate=RIG_SR, bpm=120.0)
    per_bar = int(project.frames_per_bar)
    beat = per_bar // project.beats_per_bar
    audio = np.zeros((per_bar * 8, 1), dtype=np.float32)
    tail = np.arange(int(RIG_SR * 0.04)) / RIG_SR
    env = np.exp(-tail * 300)
    rng = np.random.default_rng(3)
    for i in range(32):
        start = i * beat
        hit = (rng.normal(0, 0.5, len(tail)) * env).astype(np.float32)
        end = min(len(audio), start + len(tail))
        audio[start:end, 0] += hit[: end - start]
    sample = Sample(slot=0, bars=8, audio=audio, name="kit", gain=1.3, color=3)
    sample.set_trigger(0, True)
    project.install(0, sample)

    push = SimPush()
    push.open()
    engine = Engine(samplerate=RIG_SR, blocksize=256, in_channels=1,
                    out_channels=2, backend="offline", bpm=120.0,
                    song_bars=project.song_bars)
    from push2sampler.app import App

    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


def pump(rig):
    app, push = rig[0], rig[1]
    for event in push.poll_events():
        app.handle(event)


def open_slice(rig, slot=0):
    app, push = rig[0], rig[1]
    app.goto_sample(slot)
    push.press_button(Btn.CONVERT)
    pump(rig)
    return app.mode


def test_convert_on_a_sample_page_opens_the_slice_page(rig):
    mode = open_slice(rig)
    assert isinstance(mode, SliceMode)
    assert mode.name == "slice"
    assert mode.title == "SLICE 1"


def test_convert_does_nothing_on_an_empty_slot(rig):
    app, push, _engine, project = rig
    project.install(0, None)
    app.goto_library()
    push.press_button(Btn.CONVERT)
    pump(rig)
    assert app.mode.name == "library"


def test_eight_bars_slices_into_eight(rig):
    mode = open_slice(rig)
    assert mode.how == BY_BARS
    assert len(mode.slices) == 8


def test_beats_slices_into_thirty_two(rig):
    app, push = rig[0], rig[1]
    mode = open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[1])
    pump(rig)
    assert mode.how == BY_BEATS
    assert len(mode.slices) == 32


def test_transients_finds_the_hits_that_are_there(rig):
    app, push = rig[0], rig[1]
    mode = open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(rig)
    assert mode.how == BY_TRANSIENTS
    assert len(mode.slices) == 32  # one per quarter note, which is what is in it


def test_a_one_bar_take_opens_on_beats(rig):
    """Opening on `bars` would land you on a page that refuses to do anything."""
    app, _push, _engine, project = rig
    project.install(1, Sample(slot=1, bars=1, name="hit",
                              audio=np.full((int(project.frames_per_bar), 1),
                                            0.4, dtype=np.float32)))
    mode = open_slice(rig, slot=1)
    assert mode.how == BY_BEATS
    assert len(mode.slices) == 4


def test_the_first_slice_always_starts_at_zero(rig):
    """Otherwise the head of the take is silently thrown away."""
    app, push = rig[0], rig[1]
    mode = open_slice(rig)
    for index in range(3):
        push.press_button(DISPLAY_ROW_BOTTOM[index])
        pump(rig)
        assert mode.points[0] == 0, mode.how


def test_a_pad_auditions_the_slice_it_falls_in(rig):
    app, push, engine, _project = rig
    mode = open_slice(rig)
    push.press_pad(5)
    pump(rig)
    assert mode.previewing == 0
    assert "slice 1/8" in app.message
    push.press_pad(63)
    pump(rig)
    assert mode.previewing == 7


def test_a_pad_press_changes_nothing_in_the_song(rig):
    """This page is for listening; the commit is the only thing that writes."""
    app, push, _engine, project = rig
    before = sorted(s.slot for s in project.filled())
    open_slice(rig)
    for pad in (0, 17, 63):
        push.press_pad(pad)
        pump(rig)
    assert sorted(s.slot for s in project.filled()) == before
    assert not app.history.can_undo


def test_committing_writes_the_slices_into_the_slots_after_the_source(rig):
    app, push, _engine, project = rig
    open_slice(rig)
    push.press_button(Btn.CONVERT)
    pump(rig)
    assert sorted(s.slot for s in project.filled()) == list(range(9))
    assert app.mode.name == "sample"  # back where you were


def test_a_slice_is_one_bar_whatever_its_length(rig):
    """A slice is a hit, not a bar of music.

    Giving each slice its real length in bars would have the off-grid
    machinery flag all eight yellow for not fitting -- see the reference.
    """
    app, push, _engine, project = rig
    open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])   # transients: uneven lengths
    pump(rig)
    push.press_button(Btn.CONVERT)
    pump(rig)
    assert {project[s].bars for s in range(1, 33)} == {1}


def test_slices_carry_the_sound_and_not_the_arrangement(rig):
    app, push, _engine, project = rig
    open_slice(rig)
    push.press_button(Btn.CONVERT)
    pump(rig)
    for slot in range(1, 9):
        piece = project[slot]
        assert piece.gain == pytest.approx(1.3)
        assert piece.color == 3
        # Where the source played is not where its pieces play.
        assert piece.triggers == set()
        assert piece.name.startswith("kit/")


def test_the_original_is_kept_by_default(rig):
    app, push, _engine, project = rig
    open_slice(rig)
    push.press_button(Btn.CONVERT)
    pump(rig)
    assert project[0] is not None
    assert "kept" in app.message


def test_shift_convert_consumes_the_original(rig):
    app, push, _engine, project = rig
    open_slice(rig)
    app.shift = True
    push.press_button(Btn.CONVERT)
    pump(rig)
    app.shift = False
    assert project[0] is None
    assert sorted(s.slot for s in project.filled()) == list(range(1, 9))


def test_the_whole_conversion_is_one_undo_step(rig):
    """Sixteen presses to take back one decision would be absurd."""
    app, push, _engine, project = rig
    open_slice(rig)
    push.press_button(Btn.CONVERT)
    pump(rig)
    app.undo()
    assert sorted(s.slot for s in project.filled()) == [0]
    app.redo()
    assert sorted(s.slot for s in project.filled()) == list(range(9))


def test_undoing_a_consuming_slice_brings_the_original_back(rig):
    app, push, _engine, project = rig
    open_slice(rig)
    app.shift = True
    push.press_button(Btn.CONVERT)
    pump(rig)
    app.shift = False
    app.undo()
    assert project[0] is not None
    assert project[0].name == "kit"
    assert sorted(s.slot for s in project.filled()) == [0]


def test_slicing_over_something_is_reversible(rig):
    """Destinations are empty slots, but undo must restore them regardless."""
    from push2sampler.history import SliceTake

    app, _push, _engine, project = rig
    occupant = Sample(slot=3, bars=1, name="keep",
                      audio=np.full((100, 1), 0.2, dtype=np.float32))
    project.install(3, occupant)
    built = [Sample(slot=3, bars=1, name="new",
                    audio=np.zeros((50, 1), dtype=np.float32))]
    app.do(SliceTake(built, [3], source=0))
    assert project[3].name == "new"
    app.undo()
    assert project[3] is occupant


def test_not_enough_free_slots_refuses_and_says_how_many(rig):
    app, push, _engine, project = rig
    for slot in range(4, SLOT_COUNT):
        project.install(slot, Sample(slot=slot, bars=1,
                                     audio=np.zeros((10, 1), dtype=np.float32)))
    open_slice(rig)
    push.press_button(Btn.CONVERT)
    pump(rig)
    assert "need 8 empty slots" in app.message
    assert "there are 3" in app.message
    # Still on the page, so you can switch to fewer slices instead.
    assert app.mode.name == "slice"


def test_one_slice_is_nothing_to_do_and_says_so(rig):
    app, push, _engine, project = rig
    project.install(1, Sample(slot=1, bars=1, name="hit",
                              audio=np.full((100, 1), 0.4, dtype=np.float32)))
    mode = open_slice(rig, slot=1)
    mode.how = BY_BARS          # 1 bar by bars: one slice
    mode.invalidate()
    push.press_button(Btn.CONVERT)
    pump(rig)
    assert "one slice is the take you have" in app.message
    assert sorted(s.slot for s in project.filled()) == [0, 1]


def test_transients_on_silence_says_to_turn_sensitivity_up(rig):
    """"1 slice" on its own would look like a bug rather than an answer."""
    app, push, _engine, project = rig
    project[0].audio = np.zeros((int(project.frames_per_bar) * 8, 1),
                                dtype=np.float32)
    open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(rig)
    assert "no clear hits" in app.message


def test_the_sensitivity_encoder_says_when_it_does_not_apply(rig):
    """It does nothing in two of three modes, so it must not turn silently."""
    app, push, _engine, _project = rig
    mode = open_slice(rig)
    push.turn(ENCODER_TRACK[0], 3)
    pump(rig)
    assert mode.sensitivity == 0.5
    assert "transient" in app.message


def test_the_sensitivity_encoder_changes_the_cuts(rig):
    app, push, _engine, _project = rig
    mode = open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(rig)
    push.turn(ENCODER_TRACK[0], 4)
    pump(rig)
    assert mode.sensitivity == pytest.approx(0.7)
    assert "sensitivity 0.70" in app.message


def test_sensitivity_is_clamped_both_ways(rig):
    app, push, _engine, _project = rig
    mode = open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(rig)
    push.turn(ENCODER_TRACK[0], 100)
    pump(rig)
    assert mode.sensitivity == 1.0
    push.turn(ENCODER_TRACK[0], -100)
    pump(rig)
    assert mode.sensitivity == 0.0


def test_pressing_the_mode_you_are_in_says_so(rig):
    app, push, _engine, _project = rig
    open_slice(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    assert "already slicing by bars" in app.message


def test_session_leaves_without_writing_anything(rig):
    app, push, _engine, project = rig
    open_slice(rig)
    push.press_button(Btn.SESSION)
    pump(rig)
    assert app.mode.name == "sample"
    assert sorted(s.slot for s in project.filled()) == [0]


def test_the_points_are_cached_rather_than_recomputed_per_frame(rig):
    """Transient mode runs an FFT; thirty a second is not the place for it."""
    app, _push, _engine, _project = rig
    mode = open_slice(rig)
    mode.how = BY_TRANSIENTS
    mode.invalidate()
    calls = []
    real = mode._compute

    def counted():
        calls.append(1)
        return real()

    mode._compute = counted
    for _ in range(5):
        mode.render_pads([0] * 64)
        _ = mode.points
    assert len(calls) == 1


def test_the_grid_marks_every_cut(rig):
    from push2sampler import colors

    app, _push, _engine, _project = rig
    mode = open_slice(rig)
    pads = [0] * 64
    mode.render_pads(pads)
    marks = [i for i, value in enumerate(pads)
             if value in (colors.WHITE.index, colors.AMBER.index)]
    # Eight even slices across 64 pads: a mark every eighth pad.
    assert marks == [0, 8, 16, 24, 32, 40, 48, 56]


def test_the_status_lines_say_what_the_controls_do(rig):
    app, _push, _engine, _project = rig
    mode = open_slice(rig)
    text = " ".join(mode.status_lines())
    assert "8 slices" in text
    assert "bars / beats / transients" in text
    assert "Convert" in text


def test_the_page_says_the_slot_is_empty_rather_than_crashing(rig):
    app, _push, _engine, project = rig
    mode = open_slice(rig)
    project.install(0, None)
    assert mode.status_lines()[0] == "SLICE"
    mode.render_pads([0] * 64)          # must not raise
    assert mode.slices == []
