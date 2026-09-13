"""NH-02: swing, and laying a sample back behind the beat.

The plan asked for swing on 8th notes. **There are no 8th notes in the
arrangement**: every trigger lands on a bar line, and swinging bar lines is not
swing -- the plan's own test list said "swing does not shift bar-aligned
triggers", which in a bar-addressed sequencer means it shifts nothing at all.

So the item ships as two halves, and the split is the point:

* **Swing** applies to what you play by **hand** in perform mode, at a quantize
  finer than a beat -- the only place sub-beat time exists here. Two such
  divisions were added to `QUANTIZE_BEATS` to give it somewhere to live.
* **Nudge** is what "groove" means when your grid is bars: a per-sample offset
  that lays one take behind the beat. Late only, per sample, saved with the
  song.

Everything here is about frames, so the tests measure frames.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler.audio import QUANTIZE_BEATS, Engine, ScheduledSample
from push2sampler.constants import (
    ENCODER_SWING,
    ENCODER_TRACK,
    NUDGE_MAX_MS,
    SWING_MAX,
)
from push2sampler.project import Project, Sample

SR = 8000
BPM = 120.0
FPBEAT = SR * 60.0 / BPM          # 4000 frames
FPBAR = FPBEAT * 4                # 8000 frames


def engine(swing: float = 0.0, song_bars: int = 8) -> Engine:
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=song_bars)
    eng.swing = swing
    eng.loop = False
    return eng


def tone(frames: int = 4000, value: float = 0.5) -> np.ndarray:
    return np.full((frames, 1), value, dtype=np.float32)


def render(eng: Engine, frames: int, chunk: int = 64) -> np.ndarray:
    """Render in small chunks, so a start frame is not hidden inside a block."""
    out, done = [], 0
    while done < frames:
        n = min(chunk, frames - done)
        out.append(np.array(eng.process_offline(n)))
        done += n
    return np.concatenate(out, axis=0)


def onset(block: np.ndarray) -> int | None:
    """First audible frame.  A voice fades in over 3 ms, so this is +/- a frame."""
    loud = np.nonzero(np.abs(block[:, 0]) > 1e-4)[0]
    return int(loud[0]) if len(loud) else None


def scheduled(nudge_frames: float = 0.0, bars: int = 8):
    rows = [[] for _ in range(bars)]
    rows[0] = [ScheduledSample(0, tone(), nudge=nudge_frames)]
    return rows


# ==================================================== nudge: the frames
@pytest.mark.parametrize("ms", [0.0, 5.0, 25.0, 120.0])
def test_a_nudge_delays_the_start_by_exactly_that_many_milliseconds(ms):
    eng = engine()
    eng.set_schedule(scheduled(ms / 1000.0 * SR))
    eng.play(0)
    got = onset(render(eng, int(FPBAR)))
    assert got is not None
    # Within two frames: the envelope's first frame is 0 by construction.
    assert abs(got - ms / 1000.0 * SR) <= 2


def test_a_nudge_is_frame_accurate_whatever_the_block_size():
    """The engine splits blocks at a pending start, so the block cannot matter."""
    starts = []
    for chunk in (17, 64, 256, 1024):
        eng = engine()
        eng.set_schedule(scheduled(25.0 / 1000.0 * SR))
        eng.play(0)
        starts.append(onset(render(eng, int(FPBAR), chunk=chunk)))
    assert max(starts) - min(starts) <= 1, starts


def test_an_unnudged_sample_still_starts_on_the_bar_line():
    eng = engine()
    eng.set_schedule(scheduled(0.0))
    eng.play(0)
    assert onset(render(eng, int(FPBAR))) <= 2


def test_the_longest_nudge_still_lands_inside_a_bar_at_the_fastest_tempo():
    """240 BPM is the clamp, so a bar is never shorter than 1 s.

    120 ms of nudge can therefore never spill past the bar line it belongs to,
    which is what makes the pending start safe without any wrap handling.
    """
    eng = engine()
    eng.set_bpm(10_000.0)  # clamped
    assert eng.bpm <= 240.0
    frames_per_bar = eng.transport.frames_per_bar
    assert NUDGE_MAX_MS / 1000.0 * SR < frames_per_bar


def test_a_nudge_survives_a_loop_wrap():
    eng = engine(song_bars=2)
    eng.set_schedule(scheduled(25.0 / 1000.0 * SR, bars=2))
    eng.loop = True
    eng.play(0)
    out = render(eng, int(FPBAR * 4), chunk=256)
    loud = np.nonzero(np.abs(out[:, 0]) > 1e-4)[0]
    # Two passes through a two-bar loop: the sample fires twice, and nothing is
    # left waiting to start.
    starts = [int(f) for i, f in enumerate(loud)
              if i == 0 or f - loud[i - 1] > 10]
    assert len(starts) == 2
    assert all(abs(s % (FPBAR * 2) - 200) <= 2 for s in starts), starts
    assert eng._pending == []


def test_a_stop_discards_a_nudge_that_had_not_started():
    eng = engine()
    eng.set_schedule(scheduled(120.0 / 1000.0 * SR))
    eng.play(0)
    render(eng, 100)  # inside the nudge, before the voice exists
    assert eng._pending
    eng.stop()
    render(eng, 64)
    assert eng._pending == []


def test_a_nudged_retrigger_cuts_the_previous_voice_when_it_sounds():
    """The play mode is resolved at the start, not at the bar line it missed.

    Deciding at the bar line would cut the previous voice up to 120 ms before
    its replacement began -- an audible hole where a retrigger should be seamless.
    """
    from push2sampler.constants import RETRIGGER

    eng = engine()
    rows = [[] for _ in range(8)]
    entry = ScheduledSample(0, tone(int(FPBAR * 2)), play_mode=RETRIGGER,
                            nudge=120.0 / 1000.0 * SR)
    rows[0] = [entry]
    rows[1] = [entry]
    eng.set_schedule(rows)
    eng.play(0)
    render(eng, int(FPBAR) + 10)
    sounding = [v for v in eng._voices if v.releasing is None and v.slot == 0]
    assert len(sounding) == 1  # the first is still going, not yet cut
    assert eng._pending  # and the replacement is waiting
    render(eng, 200)
    sounding = [v for v in eng._voices if v.releasing is None and v.slot == 0]
    assert len(sounding) == 1  # cut and replaced in the same moment


# ==================================================== nudge: the project
def test_the_schedule_carries_the_nudge_in_frames():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(), nudge_ms=25.0)
    sample.set_trigger(0, True)
    project.install(0, sample)
    assert project.build_schedule()[0][0].nudge == pytest.approx(0.025 * SR)


def test_a_nudge_survives_a_save_and_load(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(), nudge_ms=35.0)
    sample.set_trigger(0, True)
    project.install(0, sample)
    project.save(tmp_path)
    assert Project.load(tmp_path, samplerate=SR)[0].nudge_ms == 35.0


def test_junk_or_out_of_range_nudge_in_a_project_file_becomes_zero(tmp_path):
    """A hand-edited file must not put NaN into a start frame."""
    from push2sampler.project import _load_nudge

    assert _load_nudge(None) == 0.0
    assert _load_nudge("late") == 0.0
    assert _load_nudge(float("nan")) == 0.0
    assert _load_nudge(-50.0) == 0.0
    assert _load_nudge(9999.0) == NUDGE_MAX_MS
    assert _load_nudge(30) == 30.0


def test_a_copy_carries_the_nudge():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(), nudge_ms=40.0)
    project.install(0, sample)
    assert project.copy_slot(0, 1).nudge_ms == 40.0


# ==================================================== swing: the frames
def test_swing_is_impossible_to_hear_without_a_sub_beat_quantize():
    """The reason this item is shaped the way it is, asserted rather than claimed."""
    sub_beat = [beats for beats in QUANTIZE_BEATS if 0 < beats < 1.0]
    assert sub_beat, "swing has nowhere to live without a division finer than a beat"
    assert 0.5 in QUANTIZE_BEATS  # an 8th note in 4/4


def _trigger_onset(swing: float, quantize_beats: float, at: int = 100) -> int:
    """Absolute frame a live trigger starts on, fired `at` frames into the song."""
    eng = engine(swing)
    eng.set_schedule([() for _ in range(8)])
    eng.play(0)
    render(eng, at)
    eng.trigger(tone(2000), quantize_beats=quantize_beats)
    out = render(eng, int(FPBEAT * 4))
    return at + onset(out)


@pytest.mark.parametrize("swing", [0.0, 0.25, 0.5, SWING_MAX])
def test_swing_pushes_the_offbeat_late_by_that_fraction_of_the_grid(swing):
    grid = 0.5 * FPBEAT  # an 8th: the first grid line after frame 100 is line 1
    got = _trigger_onset(swing, 0.5)
    assert abs(got - (grid + swing * grid)) <= 2, got


def test_swing_leaves_the_downbeat_alone():
    """Line 2 of a half-beat grid is a beat, and a beat does not move."""
    grid = 0.5 * FPBEAT
    straight = _trigger_onset(0.0, 0.5, at=int(grid) + 100)
    swung = _trigger_onset(0.5, 0.5, at=int(grid) + 100)
    assert abs(straight - 2 * grid) <= 2
    assert abs(swung - 2 * grid) <= 2


def test_swing_does_nothing_at_a_whole_beat_or_coarser():
    """Pushing every other beat back is not a groove, it is a wrong tempo."""
    for beats in (1.0, 2.0, 4.0):
        straight = _trigger_onset(0.0, beats)
        swung = _trigger_onset(0.5, beats)
        assert abs(straight - swung) <= 2, beats


def test_swing_does_nothing_to_the_arrangement():
    """Every arrangement trigger is a bar line, and bar lines never swing."""
    eng = engine(swing=SWING_MAX)
    eng.set_schedule(scheduled(0.0))
    eng.play(0)
    assert onset(render(eng, int(FPBAR))) <= 2


def test_swing_is_clamped_in_the_engine_too():
    """The UI clamps, and so does the engine: neither trusts the other."""
    eng = engine(swing=10.0)
    eng.set_schedule([() for _ in range(8)])
    eng.play(0)
    render(eng, 100)
    eng.trigger(tone(2000), quantize_beats=0.5)
    got = 100 + onset(render(eng, int(FPBEAT * 4)))
    grid = 0.5 * FPBEAT
    assert abs(got - (grid + SWING_MAX * grid)) <= 2


def test_an_unquantized_trigger_is_not_swung():
    """Quantize off means now, and swing cannot make "now" later."""
    eng = engine(swing=0.5)
    eng.set_schedule([() for _ in range(8)])
    eng.play(0)
    render(eng, 100)
    eng.trigger(tone(2000), quantize_beats=0.0)
    assert onset(render(eng, 2000)) <= 2


# ==================================================== swing: the project
def test_swing_survives_a_save_and_load(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    project.swing = 0.33
    project.save(tmp_path)
    assert Project.load(tmp_path, samplerate=SR).swing == pytest.approx(0.33)


def test_junk_swing_in_a_project_file_becomes_straight():
    from push2sampler.project import _load_swing

    assert _load_swing(None) == 0.0
    assert _load_swing("shuffle") == 0.0
    assert _load_swing(float("nan")) == 0.0
    assert _load_swing(-1.0) == 0.0
    assert _load_swing(99.0) == SWING_MAX


def test_an_older_project_opens_straight_and_on_the_beat(tmp_path):
    import json

    (tmp_path / "samples").mkdir()
    (tmp_path / "project.json").write_text(json.dumps({
        "version": 8, "samplerate": SR, "bpm": BPM, "slots": [],
    }))
    project = Project.load(tmp_path, samplerate=SR)
    assert project.swing == 0.0


# ==================================================== the surface
@pytest.fixture
def rig(tmp_path):
    from push2sampler.app import App
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone())
    sample.set_trigger(0, True)
    project.install(0, sample)
    push = SimPush()
    push.open()
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=project.song_bars)
    app = App(push, eng, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, eng, project


def pump(rig_tuple):
    app, push = rig_tuple[0], rig_tuple[1]
    for event in push.poll_events():
        app.handle(event)


def test_the_swing_encoder_sets_swing_from_anywhere(rig):
    app, push, eng, project = rig
    push.turn(ENCODER_SWING, 5)
    pump(rig)
    assert project.swing == pytest.approx(0.10)
    assert eng.swing == pytest.approx(0.10)


def test_the_swing_encoder_stops_at_the_maximum(rig):
    app, push, eng, project = rig
    for _ in range(50):
        push.turn(ENCODER_SWING, 5)
        pump(rig)
    assert project.swing == pytest.approx(SWING_MAX)
    assert eng.swing == pytest.approx(SWING_MAX)


def test_turning_swing_down_says_straight_rather_than_zero_percent(rig):
    app, push, eng, project = rig
    push.turn(ENCODER_SWING, 5)
    pump(rig)
    push.turn(ENCODER_SWING, -100)
    pump(rig)
    assert project.swing == 0.0
    assert app.message == "straight"


def test_the_swing_message_says_where_swing_applies(rig):
    """A knob that appears to do nothing is worse than no knob."""
    app, push, _eng, _project = rig
    push.turn(ENCODER_SWING, 5)
    pump(rig)
    assert "perform" in app.message


def test_swing_is_one_undo_step(rig):
    app, push, eng, project = rig
    for _ in range(6):
        push.turn(ENCODER_SWING, 2)
        pump(rig)
    assert project.swing > 0
    app.undo()
    assert project.swing == 0.0
    # And the engine is put back with it, or the audio would disagree.
    assert eng.swing == 0.0


def test_perform_mode_says_when_swing_cannot_reach_it(rig):
    from push2sampler.modes.perform import QUANTIZE_LABELS

    app, push, _eng, project = rig
    project.swing = 0.3
    app.open_perform()
    assert app.mode.quantize_beats >= 1.0  # a fresh page is a one-bar grid
    assert not app.mode.swinging
    assert "sub-beat" in app.mode.status_lines()[0]

    from push2sampler.constants import Btn

    while app.mode.quantize_beats not in (0.25, 0.5):
        app.mode.on_button(Btn.FIXED_LENGTH, True)
    assert app.mode.swinging
    line = app.mode.status_lines()[0]
    assert "swing 30%" in line
    assert QUANTIZE_LABELS[app.mode.quantize_index] in line


def test_a_fresh_perform_page_is_still_a_one_bar_grid(rig):
    """Adding finer divisions must not change where the cycle starts."""
    app, _push, _eng, _project = rig
    app.open_perform()
    assert app.mode.quantize_beats == 4.0


def test_the_nudge_encoder_lays_a_sample_back(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    push.turn(ENCODER_TRACK[1], 4)
    pump(rig)
    assert project[0].nudge_ms == pytest.approx(20.0)
    assert "behind the beat" in app.message


def test_the_nudge_encoder_will_not_go_early(rig):
    """Late only, and turning it down past zero is zero rather than -5."""
    app, push, _eng, project = rig
    app.goto_sample(0)
    push.turn(ENCODER_TRACK[1], -10)
    pump(rig)
    assert project[0].nudge_ms == 0.0


def test_the_nudge_encoder_stops_at_the_maximum(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    push.turn(ENCODER_TRACK[1], 100)
    pump(rig)
    assert project[0].nudge_ms == NUDGE_MAX_MS


def test_nudging_is_one_undo_step(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    for _ in range(5):
        push.turn(ENCODER_TRACK[1], 1)
        pump(rig)
    assert project[0].nudge_ms == pytest.approx(25.0)
    app.undo()
    assert project[0].nudge_ms == 0.0


def test_the_sample_page_shows_a_nudge_only_when_there_is_one(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    assert not any("ms" in line for line in app.mode.status_lines()[:2])
    push.turn(ENCODER_TRACK[1], 4)
    pump(rig)
    assert any("+20ms" in line for line in app.mode.status_lines())


def test_the_gain_encoder_still_only_changes_gain(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    push.turn(ENCODER_TRACK[0], 3)
    pump(rig)
    assert project[0].gain > 1.0
    assert project[0].nudge_ms == 0.0
