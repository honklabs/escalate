"""IN-08: how tight you played it.

The plan's three tests are the first three here, with the numbers it named. The
rest are about the two things the spec left implicit and that turned out to
matter more than the arithmetic:

**The grid is inferred, not assumed.** Measuring a sixteenth-note pattern
against quarter notes reports every other hit as 125 ms late at 120 BPM, which
is not a timing error -- it is the wrong question.

**Evenness and placement are separate facts.** The first version conflated them
into one verdict and produced "very tight: 20ms late", which is two statements
wearing one label. Playing *consistently* 20 ms behind the beat is a groove;
being 5 ms out at random is not. The report says both, separately.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler.analysis import (
    EVENNESS,
    GRID_DIVISIONS,
    ON_THE_BEAT_MS,
    onsets,
    timing_report,
)
from push2sampler.audio import Engine
from push2sampler.constants import DISPLAY_ROW_BOTTOM, Btn
from push2sampler.modes.info import SCATTER_MS, VIEW_SPECTRUM, VIEW_TIMING
from push2sampler.project import Project, Sample
from push2sampler.push2 import SimPush
from push2sampler.settings import SPECS, Settings

SR = 48000
BPM = 120.0
FRAMES_PER_BEAT = 60.0 / BPM * SR          # 24000


def at(offsets_ms, count=8, per_beat=1, jitter_ms=0.0, seed=9):
    """Onset frames `offsets_ms` from each grid line, cycling the list."""
    rng = np.random.default_rng(seed)
    step = FRAMES_PER_BEAT / per_beat
    out = []
    for i in range(count):
        offset = offsets_ms[i % len(offsets_ms)]
        jitter = rng.normal(0.0, jitter_ms) if jitter_ms else 0.0
        out.append(int(i * step + (offset + jitter) / 1000.0 * SR))
    return out


def take(offsets_ms, count=8, per_beat=1, jitter_ms=0.0):
    """Audible clicks at those offsets, so `onsets` has something to find."""
    # Clamped: an early first hit would otherwise be at a negative frame.
    positions = [max(0, p) for p in at(offsets_ms, count, per_beat, jitter_ms)]
    length = max(positions) + SR // 2
    audio = np.zeros((length, 1), dtype=np.float32)
    tail = np.arange(int(SR * 0.04)) / SR
    env = np.exp(-tail * 300)
    rng = np.random.default_rng(3)
    for start in positions:
        body = (rng.normal(0, 0.5, len(tail)) * env).astype(np.float32)
        end = min(length, start + len(body))
        audio[start:end, 0] += body[: end - start]
    return audio


# ==================================================== the plan's three tests
def test_a_take_twenty_milliseconds_late_reports_twenty():
    report = timing_report(at([20.0]), SR, BPM)
    assert report.count == 8
    assert report.mean_ms == pytest.approx(20.0, abs=2.0)
    assert "20ms behind the beat" in report.placement


def test_a_perfectly_aligned_take_reports_about_nothing():
    report = timing_report(at([0.0]), SR, BPM)
    assert abs(report.mean_ms) < 1.0
    assert report.spread_ms < 1.0
    assert report.placement == "on the beat"


def test_a_take_with_no_onsets_says_so_rather_than_dividing_by_zero():
    report = timing_report([], SR, BPM)
    assert report.count == 0
    assert report.mean_ms == 0.0
    assert report.spread_ms == 0.0
    assert "no onsets detected" in report.summary()


# ==================================================== early, late, even, not
def test_early_and_late_are_told_apart():
    late = timing_report(at([25.0]), SR, BPM)
    early = timing_report(at([-25.0]), SR, BPM)
    assert not late.early and "behind" in late.placement
    assert early.early and "ahead of" in early.placement


def test_a_consistent_offset_is_even_rather_than_sloppy():
    """The distinction the first version lost.

    Playing 20 ms behind the beat every single time is a groove.  Calling it
    "very tight: 20ms late" said two things with one label; "very even, 20ms
    behind the beat" says both.
    """
    groove = timing_report(at([20.0]), SR, BPM)
    assert groove.evenness == "very even"
    assert groove.placement == "20ms behind the beat"
    assert "very even" in groove.summary() and "behind" in groove.summary()


def test_random_error_is_uneven_even_when_it_averages_to_nothing():
    scattered = timing_report(at([40.0, -40.0]), SR, BPM)
    assert scattered.placement == "on the beat"   # the mean really is zero
    assert scattered.evenness == "uneven"         # and that is not the story
    assert scattered.spread_ms == pytest.approx(40.0, abs=2.0)


@pytest.mark.parametrize("spread,want", [
    (2.0, "very even"), (18.0, "even"), (35.0, "uneven"), (200.0, "all over the place"),
])
def test_evenness_follows_the_spread(spread, want):
    report = timing_report(at([spread, -spread]), SR, BPM)
    assert report.evenness == want, report.summary()


def test_the_thresholds_are_ordered_and_open_ended():
    limits = [limit for limit, _name in EVENNESS]
    assert limits == sorted(limits)
    assert limits[-1] == float("inf")     # nothing falls off the end


def test_on_the_beat_has_a_stated_tolerance():
    assert timing_report(at([ON_THE_BEAT_MS - 1]), SR, BPM).placement == "on the beat"
    assert timing_report(at([ON_THE_BEAT_MS + 5]), SR, BPM).placement != "on the beat"


def test_the_worst_hit_is_reported_separately_from_the_average():
    """One bad hit in eight should be findable, not averaged away."""
    positions = at([0.0], count=8)
    positions[4] += int(0.045 * SR)
    report = timing_report(positions, SR, BPM)
    assert report.worst_ms == pytest.approx(45.0, abs=3.0)
    assert abs(report.mean_ms) < 10.0


# ==================================================== the inferred grid
def test_sixteenths_are_measured_against_sixteenths():
    """Against quarter notes every other hit would read 125 ms late at 120 BPM.

    That is not a timing error, it is the wrong question -- which is why the
    grid is inferred rather than assumed.
    """
    report = timing_report(at([2.0], count=16, per_beat=4), SR, BPM)
    assert report.grid == "16ths"
    assert abs(report.mean_ms) < 5.0
    assert report.evenness == "very even"


def test_eighths_are_measured_against_eighths():
    report = timing_report(at([3.0], count=16, per_beat=2), SR, BPM)
    assert report.grid == "8ths"
    assert abs(report.mean_ms) < 5.0


def test_quarter_notes_are_not_promoted_to_a_finer_grid():
    """A finer grid always has a line nearer your hit; that must not win."""
    report = timing_report(at([0.0], count=8, per_beat=1), SR, BPM)
    assert report.grid == "beats"


def test_the_grid_stops_at_sixteenths():
    """Below that the lines are closer than human error and everything fits."""
    finest = min(beats for beats, _name in GRID_DIVISIONS)
    assert finest == 0.25
    assert all(name for _beats, name in GRID_DIVISIONS)


def test_the_grid_is_named_in_the_summary():
    assert "16ths" in timing_report(at([1.0], 16, 4), SR, BPM).summary()
    assert "beats" in timing_report(at([1.0], 8, 1), SR, BPM).summary()


# ==================================================== refusals
@pytest.mark.parametrize("kwargs", [
    {"samplerate": 0, "bpm": BPM},
    {"samplerate": SR, "bpm": 0.0},
    {"samplerate": SR, "bpm": -120.0},
])
def test_impossible_arguments_measure_nothing(kwargs):
    report = timing_report([100, 200, 300, 400], **kwargs)
    assert report.count == 0


def test_a_single_onset_still_reports_where_it_sits():
    report = timing_report([int(0.02 * SR)], SR, BPM)
    assert report.count == 1
    assert report.mean_ms == pytest.approx(20.0, abs=2.0)
    assert report.spread_ms == 0.0      # one hit has no spread


def test_it_works_on_real_detected_onsets_not_just_ideal_ones():
    """End to end: through the onset detector, which is where the error lives."""
    report = timing_report(onsets(take([20.0]), SR), SR, BPM)
    assert report.count >= 7
    assert report.mean_ms == pytest.approx(20.0, abs=4.0)


# ==================================================== the setting
def test_the_coach_is_off_by_default():
    """Being told how tight you are is discouraging when you did not ask."""
    assert SPECS["coach"].default is False
    assert Settings()["coach"] is False


def test_the_coach_is_editable_on_the_device():
    from push2sampler.settings import EDITABLE

    assert "coach" in EDITABLE


# ==================================================== the page
@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    project.install(0, Sample(slot=0, bars=4, audio=take([20.0]), name="late"))
    project.install(1, Sample(slot=1, bars=4, name="held",
                              audio=np.full((SR, 1), 0.3, dtype=np.float32)))
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=BPM, song_bars=project.song_bars)
    from push2sampler.app import App

    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


def pump(rig):
    app, push = rig[0], rig[1]
    for event in push.poll_events():
        app.handle(event)


def open_timing(rig, slot=0):
    app, push = rig[0], rig[1]
    app.goto_sample(slot)
    push.press_button(Btn.LAYOUT)
    pump(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[1])
    pump(rig)
    return app.mode


def test_button_two_switches_to_the_timing_view(rig):
    app, _push, _engine, _project = rig
    mode = open_timing(rig)
    assert mode.view == VIEW_TIMING
    assert "behind the beat" in app.message


def test_button_two_switches_back(rig):
    app, push, _engine, _project = rig
    mode = open_timing(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[1])
    pump(rig)
    assert mode.view == VIEW_SPECTRUM
    assert "spectrum" in app.message


def test_the_timing_view_reports_both_facts(rig):
    mode = open_timing(rig)
    text = " ".join(mode.status_lines())
    assert "TIMING" in text
    assert "even" in text
    assert "behind the beat" in text
    assert "against beats" in text or "beats" in text


def test_the_timing_view_says_it_never_quantizes(rig):
    """The spec's word is "purely informational", and the page has to say so."""
    mode = open_timing(rig)
    assert "nothing here is quantized" in " ".join(mode.status_lines())


def test_the_timing_view_explains_which_way_is_early(rig):
    mode = open_timing(rig)
    assert "above the line is early" in " ".join(mode.status_lines())


def test_a_take_with_no_attacks_says_there_is_nothing_to_measure(rig):
    mode = open_timing(rig, slot=1)
    text = " ".join(mode.status_lines())
    assert "no onsets detected" in text
    assert "held note" in text


def test_the_scatter_draws_the_centre_line_even_with_nothing_to_plot(rig):
    """A scatter with no axis is a scatter you cannot read."""
    from push2sampler import colors

    mode = open_timing(rig, slot=1)
    pads = [0] * 64
    mode.render_pads(pads)
    middle = 4 * 8
    assert all(pads[middle + column] == colors.WHITE_DIM.index
               for column in range(8))


def test_a_late_take_plots_below_the_line(rig):
    from push2sampler import colors

    mode = open_timing(rig)
    pads = [0] * 64
    mode.render_pads(pads)
    lit = [i for i, value in enumerate(pads)
           if value in (colors.GREEN.index, colors.AMBER.index, colors.RED.index)]
    assert lit, "nothing plotted"
    # Row 4 is the centre; late is below it.
    assert all(index // 8 > 4 for index in lit), [i // 8 for i in lit]


def test_an_early_take_plots_above_the_line(rig):
    from push2sampler import colors

    app, _push, _engine, project = rig
    project.install(0, Sample(slot=0, bars=4, audio=take([-25.0]), name="early"))
    mode = open_timing(rig)
    pads = [0] * 64
    mode.render_pads(pads)
    lit = [i for i, value in enumerate(pads)
           if value in (colors.GREEN.index, colors.AMBER.index, colors.RED.index)]
    assert lit
    assert all(index // 8 < 4 for index in lit), [i // 8 for i in lit]


def test_one_stray_hit_does_not_buy_a_finer_grid():
    """The case a test found, and the reason `GRID_OCCUPANCY` exists.

    Seven hits on the beat and one 90 ms late chose a *sixteenth* grid, because
    90 ms is near a sixteenth at 120 BPM -- and the report then described that
    90 ms error as 35 ms.  A coach understating your error is the one direction
    it must not fail in.  A finer grid is warranted when the playing is on it,
    not when a stray hit happens to fit.
    """
    positions = at([0.0], count=8)
    positions[3] += int(0.09 * SR)
    report = timing_report(positions, SR, BPM)
    assert report.grid == "beats"
    assert report.worst_ms == pytest.approx(90.0, abs=3.0)


def test_genuine_syncopation_does_buy_one():
    """Every hit on an off-beat eighth is eighth-note playing, not error."""
    positions = [int((i * 2 + 1) * FRAMES_PER_BEAT / 2) for i in range(8)]
    report = timing_report(positions, SR, BPM)
    assert report.grid == "8ths"
    assert report.placement == "on the beat"


def test_a_wild_hit_is_pinned_rather_than_rescaling_the_plot(rig):
    """One bad hit must not squash the other seven into the centre row."""
    app, _push, _engine, project = rig
    positions = at([0.0], count=8)
    positions[3] += int(0.09 * SR)
    project.install(0, Sample(slot=0, bars=4, name="wild",
                              audio=np.zeros((SR * 6, 1), dtype=np.float32)))
    mode = open_timing(rig)
    mode._timing = timing_report(positions, SR, BPM)
    assert mode._timing.worst_ms > SCATTER_MS
    pads = [0] * 64
    mode.render_pads(pads)
    # Clamped to the grid rather than scaled away or indexed out of range, so
    # the seven good hits still read.
    lit = [i for i, value in enumerate(pads) if value not in (0, 65)]
    assert lit and all(0 <= i < 64 for i in lit)
    assert len({i // 8 for i in lit}) >= 2


def test_the_scatter_colours_by_how_far_off_each_hit_is(rig):
    from push2sampler import colors

    app, _push, _engine, project = rig
    project.install(0, Sample(slot=0, bars=4, audio=take([0.0]), name="tight"))
    mode = open_timing(rig)
    pads = [0] * 64
    mode.render_pads(pads)
    assert colors.GREEN.index in pads          # within 10 ms

    project.install(0, Sample(slot=0, bars=4, audio=take([40.0]), name="off"))
    app.pop_mode()
    mode = open_timing(rig)
    pads = [0] * 64
    mode.render_pads(pads)
    assert colors.RED.index in pads            # beyond 25 ms


def test_the_timing_view_changes_nothing(rig):
    app, push, _engine, project = rig
    before = (project[0].name, set(project[0].triggers))
    open_timing(rig)
    for pad in (0, 30, 63):
        push.press_pad(pad)
        pump(rig)
    assert (project[0].name, set(project[0].triggers)) == before
    assert not app.history.can_undo


def test_the_report_is_measured_once(rig):
    mode = open_timing(rig)
    first = mode.timing
    assert mode.timing is first
    for _ in range(4):
        mode.render_pads([0] * 64)
    assert mode.timing is first


def test_the_spectrum_view_offers_the_timing_one(rig):
    app, push, _engine, _project = rig
    app.goto_sample(0)
    push.press_button(Btn.LAYOUT)
    pump(rig)
    assert "button 2: timing" in " ".join(app.mode.status_lines())


def test_the_page_survives_the_slot_emptying_under_it(rig):
    app, _push, _engine, project = rig
    mode = open_timing(rig)
    project.install(0, None)
    assert mode.status_lines()[0] == "ABOUT"
    mode.render_pads([0] * 64)          # must not raise
