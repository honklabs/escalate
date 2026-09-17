"""IN-09: trimming a take by ear.

The plan's tests, plus the ones the build turned up.

Two findings worth reading before changing anything here. The first is that the
**window has to be asymmetric**: a start window runs forward from the point and
an end window runs back to it, so whichever edge is being judged is the one the
loop seam puts under your ear. The second is where the **fade** goes -- on the
edge that is *not* being judged. Fading the judged edge was the first version,
and it made every start sound clean whether or not it clipped the attack, which
is precisely the question the page exists to answer.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.audio import AUDITION_SLOT
from push2sampler.constants import ENCODER_TRACK, PAD_COUNT, Btn
from push2sampler.history import SetTrim
from push2sampler.modes.trim import (
    COARSE_MS,
    DEFAULT_WINDOW_MS,
    FINE_MS,
    HUNT_END,
    HUNT_START,
    MAX_WINDOW_MS,
    MIN_WINDOW_MS,
    SNAP_BUTTON,
    STEP_BUTTON,
    TUNE_END,
    TUNE_START,
    RESET_BUTTON,
    TrimMode,
    window,
)

SR = 8000
BPM = 120.0


def take(frames=SR, value=0.5):
    """A steady take, one second long at the test rate."""
    return np.full((frames, 1), float(value), dtype=np.float32)


def ramp(frames=SR):
    """A take whose sample value *is* its position, so slices identify themselves."""
    return (np.arange(frames, dtype=np.float32) / frames).reshape(-1, 1)


def rig(tmp_path, audio=None, bars=1):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.project import Project
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    proj = Project(samplerate=SR, bpm=BPM)
    proj.pages = 1
    sample = proj.put(0, take() if audio is None else audio, bars)
    sample.name = "loop"
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=BPM, song_bars=proj.song_bars)
    app = App(push, engine, proj, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    from push2sampler.modes.sample_edit import SampleEditMode

    # Pushed over the editor, the way the hardware gets here: TrimMode is a
    # transient, and `pop_mode` on a one-deep stack does nothing at all -- so a
    # rig that used `set_mode` would quietly make every "and leaves" assertion
    # untestable.
    app.set_mode(SampleEditMode(app, 0))
    mode = TrimMode(app, 0)
    app.push_mode(mode)
    return app, mode, sample


def press(mode, cc):
    mode.on_button(cc, True)


def turn(mode, which, delta):
    mode.on_encoder(ENCODER_TRACK[which], delta)


def live_audition(engine):
    """The audition voice that is actually sounding, or None."""
    for voice in engine._voices:
        if voice.slot == AUDITION_SLOT and voice.releasing is None:
            return voice
    return None


# ======================================================== the four stages
def test_the_sequence_advances_on_the_button_and_nowhere_else(tmp_path):
    """The plan's test: one button, four stages, in order."""
    _app, mode, _sample = rig(tmp_path)
    assert mode.stage == HUNT_START

    press(mode, STEP_BUTTON)
    assert mode.stage == TUNE_START
    press(mode, STEP_BUTTON)
    assert mode.stage == HUNT_END
    press(mode, STEP_BUTTON)
    assert mode.stage == TUNE_END


def test_the_last_press_commits_and_leaves(tmp_path):
    app, mode, sample = rig(tmp_path)
    for _ in range(3):
        press(mode, STEP_BUTTON)
    mode.start, mode.end = 1000, 6000
    press(mode, STEP_BUTTON)

    assert sample.edits.trim_start_ms == pytest.approx(125.0)
    # trim_end_ms counts from the END of the take, not from zero.
    assert sample.edits.trim_end_ms == pytest.approx(250.0)
    assert not isinstance(app.mode, TrimMode)


def test_a_pad_marks_the_point_while_hunting(tmp_path):
    """The plan's test, and the gesture the whole page is built around."""
    _app, mode, _sample = rig(tmp_path)
    mode._origin = 0
    mode.engine.audition_frame = 2400

    mode.on_pad(37, True, 100)
    assert mode.stage == TUNE_START
    assert mode.start == 2400


def test_a_pad_is_ignored_while_tuning(tmp_path):
    """A pad that meant two things would make the grid unreadable."""
    _app, mode, _sample = rig(tmp_path)
    press(mode, STEP_BUTTON)
    mode.start = 1000

    mode.on_pad(20, True, 100)
    assert mode.stage == TUNE_START      # did not advance
    assert mode.start == 1000            # and did not move the point


def test_any_pad_means_now_not_the_pad_under_the_playhead(tmp_path):
    """Tapping in time is not aiming, so which pad was hit must not matter."""
    marks = []
    for index in (0, 17, 63):
        _app, mode, _sample = rig(tmp_path)
        mode._origin = 0
        mode.engine.audition_frame = 3000
        mode.on_pad(index, True, 100)
        marks.append(mode.start)
    assert marks == [3000, 3000, 3000]


def test_hunting_the_end_starts_from_the_accepted_start(tmp_path):
    """The part already decided is not replayed: it wastes the listen."""
    _app, mode, _sample = rig(tmp_path, audio=ramp())
    mode.start = 4000
    mode.stage = HUNT_END
    buf, origin = mode._audition_buffer()

    assert origin == 4000
    assert buf.shape[0] == SR - 4000
    assert float(buf[0, 0]) == pytest.approx(0.5, abs=1e-3)


# ======================================================== the window
def test_the_start_window_runs_forward_and_the_end_window_back():
    """The plan's test. The judged edge is the one at the loop seam."""
    audio = ramp(1000)

    forward = window(audio, 500, 100, forward=True, fade_frames=0)
    assert float(forward[0, 0]) == pytest.approx(0.5)      # starts AT the point
    assert float(forward[-1, 0]) == pytest.approx(0.599)

    backward = window(audio, 500, 100, forward=False, fade_frames=0)
    assert float(backward[0, 0]) == pytest.approx(0.4)
    assert float(backward[-1, 0]) == pytest.approx(0.499)  # ends AT the point


def test_the_fade_is_on_the_edge_not_being_judged():
    """The plan's test, and the bug it was written for.

    Fading the judged edge makes a clipped attack sound clean, which is the one
    thing this page must never do.
    """
    audio = take(1000, 1.0)

    forward = window(audio, 0, 200, forward=True, fade_frames=40)
    assert float(forward[0, 0]) == pytest.approx(1.0)      # attack untouched
    assert float(forward[-1, 0]) == pytest.approx(0.0, abs=1e-6)

    backward = window(audio, 1000, 200, forward=False, fade_frames=40)
    assert float(backward[0, 0]) == pytest.approx(0.0, abs=1e-6)
    assert float(backward[-1, 0]) == pytest.approx(1.0)    # cut untouched


def test_a_window_longer_than_the_take_is_clamped_not_padded():
    """Silence on the end of the loop would read as a gap that is not there."""
    audio = take(300, 1.0)
    assert window(audio, 0, 5000, forward=True, fade_frames=0).shape[0] == 300
    assert window(audio, 300, 5000, forward=False, fade_frames=0).shape[0] == 300


def test_an_empty_take_gives_an_empty_window():
    empty = np.zeros((0, 1), dtype=np.float32)
    assert window(empty, 0, 100, forward=True, fade_frames=10).shape[0] == 0


def test_the_window_never_aliases_the_recording():
    """It is faded in place, so a view would fade the take itself."""
    audio = take(1000, 1.0)
    window(audio, 0, 500, forward=True, fade_frames=100)
    assert float(audio.min()) == pytest.approx(1.0)


# ======================================================== the knobs
def test_coarse_and_fine_move_by_different_amounts(tmp_path):
    """The plan's test."""
    _app, mode, _sample = rig(tmp_path)
    press(mode, STEP_BUTTON)
    mode.start = 4000

    turn(mode, 0, 1)
    coarse = mode.start - 4000
    mode.start = 4000
    turn(mode, 1, 1)
    fine = mode.start - 4000

    assert coarse == mode._frames(COARSE_MS)
    assert fine == mode._frames(FINE_MS)
    assert coarse > fine > 0


def test_the_knobs_do_nothing_while_hunting_and_say_so(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    turn(mode, 0, 5)
    assert mode.start == 0
    assert mode.stage == HUNT_START


def test_encoder_three_sets_how_much_you_hear_and_clamps(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    assert mode.window_ms == DEFAULT_WINDOW_MS

    turn(mode, 2, -1000)
    assert mode.window_ms == MIN_WINDOW_MS
    turn(mode, 2, 1000)
    assert mode.window_ms == MAX_WINDOW_MS


def test_the_points_can_never_cross(tmp_path):
    """The plan's test: a start at or past the end is a sample of no length."""
    _app, mode, _sample = rig(tmp_path)
    press(mode, STEP_BUTTON)          # tuning the start
    mode.end = 2000

    turn(mode, 0, 10_000)
    assert mode.start < mode.end

    mode.stage = TUNE_END
    mode.start = 5000
    mode.end = 6000
    turn(mode, 0, -10_000)
    assert mode.end > mode.start


def test_a_point_is_clamped_inside_the_take(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    mode.stage = TUNE_END
    turn(mode, 0, 10_000)
    assert mode.end <= mode.audio.shape[0]

    mode.stage = TUNE_START
    turn(mode, 0, -10_000)
    assert mode.start >= 0


# ======================================================== buttons
def test_snap_moves_the_point_to_the_nearest_attack(tmp_path):
    """The plan's test."""
    audio = np.zeros((SR, 1), dtype=np.float32)
    audio[4000:4400, 0] = 1.0        # one unmistakable hit
    _app, mode, _sample = rig(tmp_path, audio=audio)
    press(mode, STEP_BUTTON)         # tuning the start
    mode.start = 4100                # a hair late, as a person's tap would be

    press(mode, SNAP_BUTTON)
    assert mode.start == pytest.approx(4000, abs=200)


def test_snap_refuses_when_nothing_is_near(tmp_path):
    """Silence has no attacks, and a snap to nowhere is worse than none."""
    _app, mode, _sample = rig(tmp_path,
                              audio=np.zeros((SR, 1), dtype=np.float32))
    press(mode, STEP_BUTTON)
    mode.start = 3000
    press(mode, SNAP_BUTTON)
    assert mode.start == 3000


def test_snap_does_nothing_while_hunting(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    press(mode, SNAP_BUTTON)
    assert mode.stage == HUNT_START
    assert mode.start == 0


def test_reset_puts_this_stage_s_point_back_to_the_edge(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    press(mode, STEP_BUTTON)
    mode.start = 3000
    press(mode, RESET_BUTTON)
    assert mode.start == 0

    mode.stage = TUNE_END
    mode.end = 3000
    press(mode, RESET_BUTTON)
    assert mode.end == mode.audio.shape[0]


def test_delete_abandons_everything(tmp_path):
    """The plan's test: the take is exactly as it was."""
    app, mode, sample = rig(tmp_path)
    before = sample.edits
    for _ in range(3):
        press(mode, STEP_BUTTON)
    mode.start, mode.end = 1234, 5678

    press(mode, Btn.DELETE)
    assert sample.edits == before
    assert not isinstance(app.mode, TrimMode)


# ======================================================== the undo step
def test_the_commit_is_one_undo_step_and_restores_both_trims(tmp_path):
    """The plan's test. Two SetEdits would be two presses of Undo."""
    app, mode, sample = rig(tmp_path)
    for _ in range(3):
        press(mode, STEP_BUTTON)
    mode.start, mode.end = 800, 7000
    press(mode, STEP_BUTTON)

    assert sample.edits.trim_start_ms == pytest.approx(100.0)
    assert sample.edits.trim_end_ms == pytest.approx(125.0)

    app.undo()
    assert sample.edits.trim_start_ms == 0.0
    assert sample.edits.trim_end_ms == 0.0


def test_committing_an_unchanged_trim_adds_no_undo_step(tmp_path):
    """Nothing happened, so Undo must not have something to take back."""
    app, mode, sample = rig(tmp_path)
    depth = len(app.history._done)
    mode.stage = TUNE_END
    mode.start, mode.end = 0, sample.raw_frames     # exactly the take's edges

    press(mode, STEP_BUTTON)
    assert len(app.history._done) == depth


def test_marking_an_end_at_the_very_start_keeps_a_sliver_not_nothing(tmp_path):
    """Pressing straight through is a real gesture, and it must not zero the take.

    Found by a test that assumed pressing through four stages changed nothing:
    it changes plenty, because every hunting press marks the playhead, and with
    the transport idle the playhead is frame 0.  So "the end is here, at the
    beginning" has to mean the shortest legal take rather than an empty one --
    every later stage of the program would otherwise need an opinion about a
    sample of no length.
    """
    _app, mode, sample = rig(tmp_path)
    for _ in range(3):
        press(mode, STEP_BUTTON)                    # start 0, then end at 0
    assert mode.end > mode.start
    assert mode.end == mode._frames(10.0)           # MIN_KEEP_MS

    press(mode, STEP_BUTTON)
    assert sample.frames > 0


def test_set_trim_writes_and_reverts_both_fields_together():
    from push2sampler.project import Project

    proj = Project(samplerate=SR, bpm=BPM)
    proj.put(0, take(), 1)
    command = SetTrim(0, 50.0, 30.0, 0.0, 0.0)

    command.apply(proj)
    assert proj[0].edits.trim_start_ms == 50.0
    assert proj[0].edits.trim_end_ms == 30.0
    command.revert(proj)
    assert proj[0].edits.trim_start_ms == 0.0
    assert proj[0].edits.trim_end_ms == 0.0


def test_it_opens_on_the_trim_the_sample_already_has(tmp_path):
    """So a second visit refines the first one instead of discarding it."""
    from push2sampler.edits import Edits

    _app, mode, sample = rig(tmp_path)
    sample.set_edits(Edits(trim_start_ms=100.0, trim_end_ms=250.0))
    mode.on_enter()

    assert mode.start == mode._frames(100.0)
    assert mode.end == sample.raw_frames - mode._frames(250.0)


# ======================================================== the audition
def test_the_point_comes_from_the_engine_not_a_clock(tmp_path):
    """The plan's test.

    A page that timed the audition itself would be wrong by the stream's
    buffering, drift on every dropout, and have no idea where a loop wrapped.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(4000), 1.0)
    engine.process_offline(1024)
    engine.process_offline(1024)

    # The position at the start of the block just rendered, not the end of it:
    # see `test_the_published_playhead_is_behind_the_render_not_ahead`.
    assert engine.audition_frame == 1024
    mode._origin = 0
    assert mode.playhead == 1024

    mode.on_pad(0, True, 100)
    assert mode.start == 1024


def test_the_audition_survives_a_bar_line_with_the_transport_running(tmp_path):
    """The plan's test.

    The audition is on a negative slot precisely so the scheduler's gate and
    loop-renewal logic pass it by.  If it were a normal slot the first bar line
    would release it and the page would go silent mid-decision.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(2000), 1.0)
    engine.play(0)
    # Well past a bar line: two bars at 120 BPM and this samplerate.
    for _ in range(40):
        engine.process_offline(512)

    assert live_audition(engine) is not None


def test_leaving_stops_the_audition(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(2000), 1.0)
    engine.process_offline(256)
    assert live_audition(engine) is not None

    mode.on_exit()
    engine.process_offline(256)
    assert live_audition(engine) is None


def test_only_one_audition_sounds_at_a_time(tmp_path):
    """A new window replaces the old one; thirty of them must not pile up."""
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    for _ in range(5):
        engine.audition(take(2000), 1.0)
        engine.process_offline(256)
    live = [v for v in engine._voices
            if v.slot == AUDITION_SLOT and v.releasing is None]
    assert len(live) == 1


def test_a_tick_does_not_restart_the_loop_when_nothing_moved(tmp_path):
    """Re-posting at the render rate would play nothing but the loop's seam."""
    _app, mode, _sample = rig(tmp_path)
    mode.engine.process_offline(256)
    first = live_audition(mode.engine)
    assert first is not None

    for _ in range(10):
        mode.on_tick()
        mode.engine.process_offline(256)
    assert live_audition(mode.engine) is first


def test_a_tick_does_restart_the_loop_when_the_point_moved(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    press(mode, STEP_BUTTON)
    mode.on_tick()
    mode.engine.process_offline(256)
    before = live_audition(mode.engine)

    turn(mode, 0, 3)
    mode.on_tick()
    mode.engine.process_offline(256)
    assert live_audition(mode.engine) is not before


def test_the_audition_frame_is_zero_with_nothing_auditioning(tmp_path):
    """A stale frame would let a tap land where the sound no longer is."""
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(2000), 1.0)
    engine.process_offline(512)
    engine.process_offline(512)
    assert engine.audition_frame > 0

    engine.stop_audition()
    for _ in range(20):
        engine.process_offline(512)
    assert engine.audition_frame == 0


def test_the_audition_loops_rather_than_playing_once(tmp_path):
    """One pass and you have missed your chance to tap."""
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(1000), 1.0)
    for _ in range(6):
        engine.process_offline(512)     # 3072 frames through a 1000-frame loop
    assert live_audition(engine) is not None


# ======================================================== the grid
def test_the_grid_shows_the_whole_take_while_hunting(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    assert mode._view() == (0, SR)


def test_the_grid_magnifies_while_tuning(tmp_path):
    """A picture that cannot show what a knob does is a decoration."""
    _app, mode, _sample = rig(tmp_path)
    press(mode, STEP_BUTTON)
    mode.start = 4000
    low, high = mode._view()

    assert high - low < SR
    assert low <= 4000 <= high


def test_the_trimmed_away_part_is_marked_on_the_grid(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    mode.start, mode.end = SR // 4, SR // 2
    # Out of the way: the playhead legitimately draws over everything, so a
    # test that left it on pad 0 would be asserting about the playhead.
    mode._origin = 0
    mode.engine.audition_frame = SR // 3
    pads = [colors.OFF.index] * PAD_COUNT
    mode.render_pads(pads)

    assert pads[0] == colors.RED_DIM.index        # before the start
    assert pads[PAD_COUNT - 1] == colors.RED_DIM.index   # after the end
    assert colors.GREEN.index in pads             # the kept part is audible


def test_the_playhead_wins_over_the_point_marker(tmp_path):
    """They cross constantly, and a playhead that vanishes is not a playhead."""
    _app, mode, _sample = rig(tmp_path)
    mode.start, mode.end = 0, SR
    mode._origin = 0
    mode.engine.audition_frame = 0
    pads = [colors.OFF.index] * PAD_COUNT
    mode.render_pads(pads)
    assert pads[0] == colors.WHITE.index


def test_rendering_an_empty_take_lights_nothing(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    mode.sample.audio = np.zeros((0, 1), dtype=np.float32)
    pads = [colors.GREEN.index] * PAD_COUNT
    mode.render_pads(pads)
    assert set(pads) == {colors.OFF.index}


# ======================================================== the page itself
def test_the_status_lines_name_the_stage_and_never_overflow(tmp_path):
    _app, mode, _sample = rig(tmp_path)
    for stage in (HUNT_START, TUNE_START, HUNT_END, TUNE_END):
        mode.stage = stage
        lines = mode.status_lines()
        assert lines and all(isinstance(line, str) for line in lines)
        assert any("stage" in line for line in lines)


def test_the_step_button_is_lit_brightest(tmp_path):
    """It is the only button you need, so it has to look like it."""
    _app, mode, _sample = rig(tmp_path)
    buttons: dict[int, int] = {}
    mode.render_buttons(buttons)
    assert buttons[STEP_BUTTON] == max(buttons.values())


def test_the_tuning_buttons_are_dim_while_hunting(tmp_path):
    """They do nothing there, and a lit button that does nothing is a lie."""
    _app, mode, _sample = rig(tmp_path)
    hunting: dict[int, int] = {}
    mode.render_buttons(hunting)
    press(mode, STEP_BUTTON)
    tuning: dict[int, int] = {}
    mode.render_buttons(tuning)

    assert tuning[SNAP_BUTTON] > hunting[SNAP_BUTTON]
    assert tuning[RESET_BUTTON] > hunting[RESET_BUTTON]


def test_an_empty_slot_bounces_straight_back_out(tmp_path):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.project import Project
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    proj = Project(samplerate=SR, bpm=BPM)
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=BPM, song_bars=proj.song_bars)
    app = App(push, engine, proj, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    app.push_mode(TrimMode(app, 5))
    assert not isinstance(app.mode, TrimMode)


def test_the_editor_opens_it_with_the_button_that_drives_it(tmp_path):
    """The same key start to finish, which is the whole interaction."""
    from push2sampler.modes.sample_edit import SampleEditMode

    app, _mode, _sample = rig(tmp_path)
    app.set_mode(SampleEditMode(app, 0))
    app.mode.on_button(STEP_BUTTON, True)
    assert isinstance(app.mode, TrimMode)
    assert STEP_BUTTON == Btn.SELECT


def test_the_trim_it_writes_is_the_trim_the_editor_reads(tmp_path):
    """It writes Edits, so the editor's own encoders and picture still work."""
    from push2sampler.modes.sample_edit import PARAMS

    _app, mode, sample = rig(tmp_path)
    for _ in range(3):
        press(mode, STEP_BUTTON)
    mode.start, mode.end = 400, 7600
    press(mode, STEP_BUTTON)

    fields = [param.field for param in PARAMS]
    assert "trim_start_ms" in fields and "trim_end_ms" in fields
    assert sample.edits.trim_start_ms == pytest.approx(50.0)
    assert sample.edits.trim_end_ms == pytest.approx(50.0)
    # And the take that actually plays is shorter by both.
    assert sample.frames == pytest.approx(7200, abs=2)


# ================================ what the code review found
#
# Four bugs, all in the audition voice's lifetime and position reporting, and
# all four invisible to the tests above because those drive the mode directly
# and never involve anything *else* touching the engine.
def test_stop_does_not_silence_the_page_for_good(tmp_path):
    """`Engine._stop_now` releases every voice, negative slots included.

    Nothing was putting the audition back, so pressing Stop while trimming
    left the page silent with its published playhead frozen -- and the next
    tap then marked frame 0.  The engine now says whether one is sounding and
    `on_tick` re-posts when it stops being true.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    for _ in range(4):
        mode.on_tick()
        engine.process_offline(256)
    assert live_audition(engine) is not None

    engine.stop()
    engine.process_offline(256)
    assert live_audition(engine) is None      # Stop really did kill it

    for _ in range(4):
        mode.on_tick()
        engine.process_offline(256)
    assert live_audition(engine) is not None, "the page never got its loop back"


def test_arming_a_take_does_not_silence_the_page_for_good(tmp_path):
    """Same hole, different door: arming a recording releases everything too."""
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    for _ in range(4):
        mode.on_tick()
        engine.process_offline(256)

    engine.arm_record(1)
    engine.process_offline(256)
    for _ in range(4):
        mode.on_tick()
        engine.process_offline(256)
    assert live_audition(engine) is not None


def test_a_healed_audition_publishes_a_moving_playhead_again(tmp_path):
    """The frozen playhead is the part that would have corrupted a take.

    A silent page is obvious.  A silent page whose next tap marks frame 0 is
    not, and it writes a wrong trim.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    for _ in range(4):
        mode.on_tick()
        engine.process_offline(256)
    engine.stop()
    engine.process_offline(256)
    for _ in range(6):
        mode.on_tick()
        engine.process_offline(256)
    assert engine.audition_frame > 0


def test_nothing_can_bury_the_page_while_it_is_making_sound(tmp_path):
    """`push_mode` does not call `on_exit` on the mode it covers.

    So `Mix`, `Clip`, `Browse` and `Setup` used to open over this page with the
    loop still playing and no `on_tick` left to stop it.  This page claims the
    buttons it does not use rather than letting them through.
    """
    app, mode, _sample = rig(tmp_path)
    for cc in (Btn.MIX, Btn.CLIP, Btn.BROWSE, Btn.SETUP, Btn.SCALE, Btn.PLAY):
        assert mode.on_button(cc, True) is True, cc
        assert app.mode is mode, f"{cc} buried the page"


def test_the_leave_buttons_still_leave(tmp_path):
    """Claiming the surface must not also trap you in it."""
    from push2sampler.modes.trim import LEAVE_BUTTONS

    for cc in LEAVE_BUTTONS:
        app, mode, sample = rig(tmp_path)
        before = sample.edits
        press(mode, cc)
        assert not isinstance(app.mode, TrimMode), cc
        assert sample.edits == before, cc


def test_replacing_an_audition_near_its_end_still_fades(tmp_path):
    """A release has to keep wrapping, or it is cut off mid-fade.

    `_mix`'s looping branch used to require ``releasing is None``, so a
    released loop took the linear path and was dropped the moment ``pos``
    reached the end of its buffer -- truncating the 10 ms fade to whatever
    sample it had got to.  With a 40 ms window that is about a quarter of
    every encoder tick, and it clicks.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    loud = take(400, 1.0)
    engine.audition(loud, 1.0)
    engine.process_offline(256)          # 256 of 400 frames in: near the end

    engine.audition(take(400, 0.0), 1.0)  # replace it with silence
    out = engine.process_offline(256)
    # The outgoing voice is all that can be heard, so the block is its fade.
    # A truncated fade leaves a step down to zero; a complete one does not.
    tail = np.abs(out[:, 0])
    biggest_step = float(np.max(np.abs(np.diff(tail)))) if tail.size > 1 else 0.0
    assert biggest_step < 0.2, f"a step of {biggest_step:.3f} is a click"


def test_a_released_loop_gets_its_whole_release_not_what_is_left_in_the_buffer(tmp_path):
    """The same fix, stated as the property rather than as the symptom.

    Released 44 frames from the end of a 300-frame loop, the voice used to live
    for 44 more frames and then vanish at whatever level the ramp had reached.
    It should live for the full release instead, wrapping to get the audio.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(300, 1.0), 1.0)
    engine.process_offline(256)          # pos 256 of 300: 44 frames left
    engine.stop_audition()
    engine.process_offline(1)            # apply the release

    alive = 0
    for _ in range(200):
        engine.process_offline(1)
        if live_audition(engine) is None and not any(
                v.slot == AUDITION_SLOT for v in engine._voices):
            break
        alive += 1
    # RELEASE_MS is 10ms, which at this rate is 80 frames -- not the 44 that
    # were left in the buffer.
    assert alive > 60, f"released voice only lasted {alive} frames"


def test_the_published_playhead_is_behind_the_render_not_ahead(tmp_path):
    """It was read *after* the block was mixed, so it named unheard audio.

    A blocksize ahead of the speaker, and every tap therefore landed late --
    in the same direction as human reaction time, so the two errors added
    instead of being independent.  It is now the position at the *start* of
    the block that was rendered.
    """
    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.audition(take(8000), 1.0)

    engine.process_offline(256)
    assert engine.audition_frame == 0        # the first block starts at 0
    engine.process_offline(256)
    assert engine.audition_frame == 256
    engine.process_offline(256)
    assert engine.audition_frame == 512


def test_a_normal_looping_sample_is_unaffected_by_the_release_fix(tmp_path):
    """The looping branch now takes released voices too; a plain loop must not care."""
    from push2sampler.constants import LOOP
    from push2sampler.audio import ScheduledSample

    _app, mode, _sample = rig(tmp_path)
    engine = mode.engine
    engine.stop_audition()
    schedule = [() for _ in range(engine.transport.song_bars)]
    schedule[0] = (ScheduledSample(0, take(1000, 0.5), play_mode=LOOP),)
    engine.set_schedule(schedule)
    engine.play(0)
    for _ in range(20):
        engine.process_offline(256)
    # Still sounding after well over one buffer's length: it wrapped.
    assert 0 in engine.sounding
