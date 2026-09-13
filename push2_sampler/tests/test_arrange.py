"""Gestures that write many bars at once, and tempo tapping.

Painting a range, double-tapping a phrase, duplicating a block or a slot: all of
them are one undo step, and none of them may disturb a bar outside the block they
name.  That is what these tests are about.
"""

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.app import TAP_MINIMUM, App, _bpm_from_taps
from push2sampler.audio import Engine
from push2sampler.constants import ENCODER_TEMPO, Btn
from push2sampler.modes.sample import DOUBLE_TAP_S, PHRASE_BARS
from push2sampler.project import (
    BANK_SLOTS,
    FULL_VELOCITY,
    SLOT_COUNT,
    Project,
    format_bpm,
)
from push2sampler.push2 import SimPush
from push2sampler.settings import Settings

SR = 8000


@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    engine = Engine(
        samplerate=SR, blocksize=64, in_channels=1, out_channels=2,
        backend="offline", bpm=120.0, song_bars=project.song_bars,
    )
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    app = App(push, engine, project, project_dir=tmp_path / "song", settings=settings)
    return app, push, engine, project


def pump(app):
    for event in app.push.poll_events():
        app.handle(event)
    app.mode.on_tick()
    app.render()


def take(engine, bars=1, value=0.5):
    return np.full((int(bars * engine.frames_per_bar), 1), value, dtype=np.float32)


def on_page(rig, slot=0, bars=1, slots=()):
    """Open a sample's page, with optional extra filled slots alongside."""
    app, push, engine, project = rig
    for other in (slot, *slots):
        project.put(other, take(engine, bars=bars), bars=bars)
    app.rebuild_schedule()
    app.goto_sample(slot)
    pump(app)
    return app, push, engine, project


# ------------------------------------------------------------- CC-11: painting
def test_hold_a_bar_and_press_another_paints_the_range_on(rig):
    app, push, _, project = on_page(rig)
    push.inject_pad_press(3)  # hold bar 4: its own press turns it on
    pump(app)
    push.press_pad(11)  # ...and press bar 12
    pump(app)
    push.inject_pad_release(3)
    pump(app)
    assert project[0].triggers == set(range(3, 12))


def test_painting_is_one_undo_step_for_the_whole_range(rig):
    app, push, _, project = on_page(rig)
    push.inject_pad_press(3)
    pump(app)
    push.press_pad(11)
    pump(app)
    app.undo()
    # The range goes, but the held bar's own toggle is a separate step and stays.
    assert project[0].triggers == {3}
    app.undo()
    assert project[0].triggers == set()


def test_holding_an_already_on_bar_paints_off(rig):
    app, push, _, project = on_page(rig)
    for bar in range(0, 8):
        project[0].set_trigger(bar, True)
    push.inject_pad_press(2)  # bar 3 is on, so this press turns it off
    pump(app)
    push.press_pad(5)
    pump(app)
    assert project[0].triggers == {0, 1, 6, 7}


def test_painting_works_backwards(rig):
    app, push, _, project = on_page(rig)
    push.inject_pad_press(20)
    pump(app)
    push.press_pad(16)
    pump(app)
    assert project[0].triggers == set(range(16, 21))


def test_a_release_ends_the_paint_so_the_next_press_just_toggles(rig):
    app, push, _, project = on_page(rig)
    push.press_pad(3)  # press and release
    pump(app)
    push.press_pad(11)
    pump(app)
    assert project[0].triggers == {3, 11}


# --------------------------------------------------------- CC-12: double taps
def test_double_tapping_an_empty_bar_fills_the_phrase(rig):
    app, push, _, project = on_page(rig, bars=1)
    push.press_pad(8)
    pump(app)
    push.press_pad(8)
    pump(app)
    assert project[0].triggers == {8, 9, 10, 11}


def test_a_two_bar_take_fills_the_phrase_every_other_bar(rig):
    app, push, _, project = on_page(rig, bars=2)
    push.press_pad(8)
    pump(app)
    push.press_pad(8)
    pump(app)
    assert project[0].triggers == {8, 10}


def test_double_tapping_a_filled_bar_clears_the_phrase(rig):
    app, push, _, project = on_page(rig)
    for bar in range(8, 14):
        project[0].set_trigger(bar, True)
    push.press_pad(8)  # first tap turns bar 9 off
    pump(app)
    push.press_pad(8)  # second clears the rest of the phrase
    pump(app)
    assert project[0].triggers == {12, 13}


def test_two_slow_taps_are_two_toggles_not_a_fill(rig, monkeypatch):
    app, push, _, project = on_page(rig)
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.modes.sample.time.monotonic", lambda: clock[0])
    push.press_pad(8)
    pump(app)
    clock[0] += DOUBLE_TAP_S * 2
    push.press_pad(8)
    pump(app)
    assert project[0].triggers == set()


def test_a_fill_clipped_at_the_end_of_the_song_does_not_wrap(rig):
    app, push, _, project = on_page(rig)
    push.press_pad(63)
    pump(app)
    push.press_pad(63)
    pump(app)
    assert project[0].triggers == {63}


def test_filling_a_phrase_is_one_undo_step(rig):
    app, push, _, project = on_page(rig)
    push.press_pad(0)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert len(project[0].triggers) == PHRASE_BARS
    app.undo()
    assert project[0].triggers == {0}


# ------------------------------------------------ NH-05: duplicate a bar block
def arm_duplicate(app, push):
    push.press_button(Btn.DUPLICATE)
    pump(app)
    assert app.duplicate_armed


def test_duplicate_copies_a_block_the_length_of_the_gap(rig):
    app, push, _, project = on_page(rig)
    for bar in (0, 2, 3):
        project[0].set_trigger(bar, True)
    arm_duplicate(app, push)
    push.press_pad(0)  # block starts at bar 1
    pump(app)
    push.press_pad(4)  # ...and goes to bar 5, so it is 4 bars long
    pump(app)
    assert project[0].triggers == {0, 2, 3, 4, 6, 7}
    assert not app.duplicate_armed


def test_a_duplicated_block_clears_destination_bars_the_source_lacks(rig):
    app, push, _, project = on_page(rig)
    project[0].set_trigger(0, True)
    project[0].set_trigger(5, True)  # in the way of the copy
    arm_duplicate(app, push)
    push.press_pad(0)
    pump(app)
    push.press_pad(4)
    pump(app)
    assert project[0].triggers == {0, 4}


def test_duplicate_carries_velocities(rig):
    app, push, _, project = on_page(rig)
    project[0].set_trigger(0, True, velocity=40)
    arm_duplicate(app, push)
    push.press_pad(0)
    pump(app)
    push.press_pad(2)
    pump(app)
    assert project[0].velocity_at(2) == 40


def test_shift_on_the_second_press_moves_the_block(rig):
    app, push, _, project = on_page(rig)
    for bar in (0, 1):
        project[0].set_trigger(bar, True)
    arm_duplicate(app, push)
    push.press_pad(0)
    pump(app)
    push.hold_button(Btn.SHIFT, True)
    push.press_pad(2)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert project[0].triggers == {2, 3}


def test_a_block_copy_is_clipped_at_bar_64(rig):
    app, push, _, project = on_page(rig)
    project[0].set_trigger(60, True)
    arm_duplicate(app, push)
    push.press_pad(60)
    pump(app)
    push.press_pad(62)  # a 2-bar block onto 63, so bar 65 would be next
    pump(app)
    assert max(project[0].triggers) < 64


def test_duplicating_backwards_is_refused_with_a_reason(rig):
    app, push, _, project = on_page(rig)
    project[0].set_trigger(8, True)
    arm_duplicate(app, push)
    push.press_pad(8)
    pump(app)
    push.press_pad(4)
    pump(app)
    assert project[0].triggers == {8}
    assert "later bar" in app.message


def test_a_block_duplicate_is_one_undo_step(rig):
    app, push, _, project = on_page(rig)
    for bar in (0, 1):
        project[0].set_trigger(bar, True)
    arm_duplicate(app, push)
    push.press_pad(0)
    pump(app)
    push.press_pad(2)
    pump(app)
    assert project[0].triggers == {0, 1, 2, 3}
    app.undo()
    assert project[0].triggers == {0, 1}


def test_the_source_bar_is_marked_while_waiting_for_a_destination(rig):
    app, push, _, _ = on_page(rig)
    arm_duplicate(app, push)
    push.press_pad(8)
    pump(app)
    assert push.pad_leds[8] in (colors.BLUE.index, colors.WHITE.index)


# ---------------------------------------------------- NH-05: duplicate a slot
def test_duplicate_in_the_library_copies_a_slot_to_the_next_empty_one(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(4, True)
    app.rebuild_schedule()
    push.press_button(Btn.DUPLICATE)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert project[1] is not None
    assert project[1].triggers == {4}
    assert project[1].slot == 1


def test_a_duplicated_slot_shares_audio_but_not_edits(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    push.press_button(Btn.DUPLICATE)
    pump(app)
    push.press_pad(0)
    pump(app)
    original, copy = project[0], project[1]
    assert copy.audio is original.audio  # no second copy of the samples
    copy.set_edits(copy.edits.with_value("reverse", True))
    assert original.edits.is_default
    # And applying the copy's edits rebinds its array rather than writing through.
    copy.apply_edits()
    assert copy.audio is not original.audio
    assert np.allclose(original.audio, 0.5)


def test_shift_duplicate_moves_a_slot(rig):
    app, push, engine, project = rig
    project.put(3, take(engine), bars=1)
    push.press_button(Btn.DUPLICATE)
    pump(app)
    push.hold_button(Btn.SHIFT, True)
    push.press_pad(3)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert project[3] is None
    assert project[4] is not None


def test_undoing_a_slot_move_puts_it_back(rig):
    app, push, engine, project = rig
    project.put(3, take(engine), bars=1)
    push.press_button(Btn.DUPLICATE)
    pump(app)
    push.hold_button(Btn.SHIFT, True)
    push.press_pad(3)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    app.undo()
    assert project[3] is not None
    assert project[4] is None


def test_duplicating_into_a_full_library_says_so(rig):
    app, push, engine, project = rig
    for slot in range(SLOT_COUNT):
        project.put(slot, take(engine), bars=1)
    push.press_button(Btn.DUPLICATE)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert "no empty slot" in app.message


def test_duplicating_an_empty_slot_says_so(rig):
    app, push, _, _ = rig
    push.press_button(Btn.DUPLICATE)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert "nothing in that slot" in app.message
    assert app.mode.name == "library"  # and does not start a recording


def test_duplicate_arming_survives_nothing_else(rig):
    """Opening a page clears every armed modifier, duplicate included."""
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    push.press_button(Btn.DUPLICATE)
    pump(app)
    app.goto_sample(0)
    assert not app.duplicate_armed


# ------------------------------------------------------------- NH-07: tapping
def test_four_even_taps_set_the_tempo(rig):
    app, _, engine, _ = rig
    for index in range(TAP_MINIMUM):
        app.tap_tempo(now=1000.0 + index * 0.5)  # 0.5 s apart = 120 BPM
    assert abs(engine.bpm - 120.0) < 0.5


def test_taps_at_a_different_rate_set_a_different_tempo(rig):
    app, _, engine, _ = rig
    for index in range(TAP_MINIMUM):
        app.tap_tempo(now=1000.0 + index * 0.4)  # 150 BPM
    assert abs(engine.bpm - 150.0) < 0.5


def test_one_outlying_tap_is_ignored(rig):
    app, _, engine, _ = rig
    # Three good intervals of 0.5 s and one badly early tap between them.
    for now in (1000.0, 1000.5, 1000.55, 1001.05, 1001.55):
        app.tap_tempo(now=now)
    assert abs(engine.bpm - 120.0) < 1.0


def test_fewer_than_four_taps_only_counts(rig):
    app, _, engine, _ = rig
    before = engine.bpm
    for index in range(TAP_MINIMUM - 1):
        assert app.tap_tempo(now=1000.0 + index * 0.5) is None
    assert engine.bpm == before
    assert f"/{TAP_MINIMUM}" in app.message


def test_a_long_gap_starts_a_new_series(rig):
    app, _, engine, _ = rig
    app.tap_tempo(now=1000.0)
    app.tap_tempo(now=1010.0)  # far too late: series restarts here
    app.tap_tempo(now=1010.4)
    app.tap_tempo(now=1010.8)
    before = engine.bpm
    assert before == 120.0  # only three taps in the new series
    app.tap_tempo(now=1011.2)
    assert abs(engine.bpm - 150.0) < 0.5


def test_tapping_is_refused_during_a_take(rig):
    app, push, engine, project = rig
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    engine.process_offline(64, np.zeros((64, 1), dtype=np.float32))
    before = engine.bpm
    for index in range(TAP_MINIMUM + 1):
        app.tap_tempo(now=1000.0 + index * 0.4)
    assert engine.bpm == before
    assert "during a take" in app.message


def test_shift_tap_resets_the_series(rig):
    app, push, engine, _ = rig
    app.tap_tempo(now=1000.0)
    app.tap_tempo(now=1000.4)
    app.shift = True
    app.tap_tempo(now=1000.8)
    app.shift = False
    for index in range(TAP_MINIMUM):  # a fresh series at 120
        app.tap_tempo(now=2000.0 + index * 0.5)
    assert abs(engine.bpm - 120.0) < 0.5


def test_tapping_the_button_goes_through_the_surface(rig):
    app, push, engine, _ = rig
    for _ in range(TAP_MINIMUM):
        push.press_button(Btn.TAP_TEMPO)
        pump(app)
    # Real presses are milliseconds apart here, so the tempo lands at the top of
    # the range rather than anywhere musical; what matters is that it moved.
    assert engine.bpm != 120.0


def test_a_tempo_tap_is_undoable(rig):
    app, _, engine, _ = rig
    for index in range(TAP_MINIMUM):
        app.tap_tempo(now=1000.0 + index * 0.4)
    assert abs(engine.bpm - 150.0) < 0.5
    app.undo()
    assert abs(engine.bpm - 120.0) < 0.01


def test_holding_tap_makes_the_tempo_encoder_fine(rig):
    app, push, engine, _ = rig
    push.hold_button(Btn.TAP_TEMPO, True)
    pump(app)
    push.turn(ENCODER_TEMPO, 2)
    pump(app)
    assert abs(engine.bpm - 120.2) < 0.001
    push.hold_button(Btn.TAP_TEMPO, False)
    pump(app)
    push.turn(ENCODER_TEMPO, 2)
    pump(app)
    assert abs(engine.bpm - 122.2) < 0.001


def test_nudging_while_holding_tap_does_not_leave_a_stray_tap(rig):
    app, push, engine, _ = rig
    push.hold_button(Btn.TAP_TEMPO, True)
    pump(app)
    push.turn(ENCODER_TEMPO, 1)
    pump(app)
    assert app._taps == []


def test_bpm_from_taps_rejects_nonsense():
    assert _bpm_from_taps([1000.0]) is None
    assert _bpm_from_taps([1000.0, 1000.0]) is None


def test_a_fine_nudge_is_visible_in_the_undo_label(rig):
    app, push, _, _ = rig
    push.hold_button(Btn.TAP_TEMPO, True)
    pump(app)
    push.turn(ENCODER_TEMPO, 1)
    pump(app)
    assert "120.1" in app.message


# ------------------------------------------------------- the project helpers
def test_next_empty_wraps_round_the_grid(rig):
    _, _, engine, project = rig
    for slot in range(1, SLOT_COUNT):
        project.put(slot, take(engine), bars=1)
    assert project.next_empty(10) == 0


def test_next_empty_crosses_a_bank_boundary(rig):
    _, _, engine, project = rig
    for slot in range(0, BANK_SLOTS):
        project.put(slot, take(engine), bars=1)
    # Bank A is full, so the next empty slot is the first of bank B.
    assert project.next_empty(0) == BANK_SLOTS


def test_next_empty_is_none_when_the_library_is_full(rig):
    _, _, engine, project = rig
    for slot in range(SLOT_COUNT):
        project.put(slot, take(engine), bars=1)
    assert project.next_empty(0) is None


def test_copy_bar_range_computes_without_changing_anything(rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    changes = project.copy_bar_range(0, 0, 4, 4)
    assert changes == {4: FULL_VELOCITY, 5: None, 6: None, 7: None}
    assert project[0].triggers == {0}  # untouched


def test_copy_bar_range_of_an_empty_slot_is_empty(rig):
    _, _, _, project = rig
    assert project.copy_bar_range(0, 0, 4, 4) == {}


def test_moving_a_block_clears_only_the_bars_the_copy_missed(rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    for bar in (0, 1):
        project[0].set_trigger(bar, True)
    changes = project.copy_bar_range(0, 0, 1, 2, move=True)
    # Bar 2 is both a source and a destination, so it is written, not cleared.
    assert changes == {1: FULL_VELOCITY, 2: FULL_VELOCITY, 0: None}


# ------------------------------------------------------------ CC-02: stopping
def test_shift_stop_lets_the_bar_finish(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(1, True)
    app.rebuild_schedule()
    engine.play(0)
    engine.process_offline(int(engine.frames_per_bar * 0.25),
                           np.zeros((int(engine.frames_per_bar * 0.25), 1), dtype=np.float32))
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.STOP)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert engine.stop_pending
    assert engine.is_playing  # still running: the bar has not finished
    # Run to just before the bar line, then across it.
    short = int(engine.frames_per_bar * 0.5)
    engine.process_offline(short, np.zeros((short, 1), dtype=np.float32))
    assert engine.is_playing
    engine.process_offline(short, np.zeros((short, 1), dtype=np.float32))
    assert not engine.is_playing
    assert not engine.stop_pending


def test_a_deferred_stop_does_not_start_the_next_bar(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(1, True)  # the bar the stop lands on
    app.rebuild_schedule()
    engine.play(0)
    engine.stop(at_bar_end=True)
    frames = int(engine.frames_per_bar) + 64
    engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert not engine.is_playing
    assert engine.sounding == ()  # bar 2's sample never fired


def test_shift_stop_while_already_stopped_just_stops(rig):
    app, push, engine, _ = rig
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.STOP)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert not engine.stop_pending
    assert not engine.is_playing


def test_a_deferred_stop_is_refused_during_a_take(rig):
    app, push, engine, _ = rig
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    engine.process_offline(64, np.zeros((64, 1), dtype=np.float32))
    engine.stop(at_bar_end=True)
    assert not engine.stop_pending
    assert engine.rec_state == "idle"


def test_a_second_stop_clears_armed_modifiers(rig, monkeypatch):
    app, push, _, _ = rig
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.app.time.monotonic", lambda: clock[0])
    push.press_button(Btn.DELETE)
    pump(app)
    assert app.delete_armed
    push.press_button(Btn.STOP)
    pump(app)
    assert app.delete_armed  # one stop leaves the arm alone
    clock[0] += 0.2
    push.press_button(Btn.STOP)
    pump(app)
    assert not app.delete_armed
    assert app.message == "all clear"


def test_two_slow_stops_are_not_a_panic(rig, monkeypatch):
    app, push, _, _ = rig
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.app.time.monotonic", lambda: clock[0])
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_button(Btn.STOP)
    pump(app)
    clock[0] += 2.0
    push.press_button(Btn.STOP)
    pump(app)
    assert app.delete_armed


def test_a_pending_stop_shows_on_the_transport_line(rig, monkeypatch):
    app, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.rebuild_schedule()
    engine.play(0)
    engine.stop(at_bar_end=True)
    assert any("ENDING" in line for line in app.status_lines())


# ------------------------------------------------- CC-07: what comes in next
def test_the_library_dims_a_slot_that_comes_in_next_bar(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(1, True)  # plays on bar 2 only
    app.rebuild_schedule()
    engine.play(0)
    pump(app)
    assert push.pad_leds[0] == colors.AMBER_DIM.index


def test_a_sounding_slot_stays_bright(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    project[0].set_trigger(1, True)
    app.rebuild_schedule()
    engine.play(0)
    engine.process_offline(64, np.zeros((64, 1), dtype=np.float32))
    pump(app)
    assert push.pad_leds[0] == colors.AMBER.index


def test_the_hint_wraps_to_bar_one_when_looping(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    app.rebuild_schedule()
    engine.loop = True
    engine.play(project.song_bars - 1)  # the last bar
    pump(app)
    assert push.pad_leds[0] == colors.AMBER_DIM.index


def test_there_is_no_hint_past_the_end_without_a_loop(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    app.rebuild_schedule()
    engine.loop = False
    engine.play(project.song_bars - 1)
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index


def test_a_muted_slot_is_never_hinted(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(1, True)
    project[0].enabled = False
    app.rebuild_schedule()
    engine.play(0)
    pump(app)
    assert push.pad_leds[0] == colors.GREEN_DIM.index


def test_slots_at_bar_ignores_bars_outside_the_song(rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    assert project.slots_at_bar(0) == {0}
    assert project.slots_at_bar(-1) == set()
    assert project.slots_at_bar(project.song_bars) == set()


# ----------------------------------------------------------- tempo formatting
def test_a_whole_tempo_reads_without_a_decimal():
    assert format_bpm(120.0) == "120"
    assert format_bpm(240.0) == "240"


def test_a_nudged_tempo_shows_its_decimal():
    assert format_bpm(120.1) == "120.1"
    assert format_bpm(119.9) == "119.9"


def test_the_transport_line_shows_a_fine_tempo(rig):
    app, push, engine, _ = rig
    push.hold_button(Btn.TAP_TEMPO, True)
    pump(app)
    push.turn(ENCODER_TEMPO, 3)
    pump(app)
    assert any("120.3 BPM" in line for line in app.status_lines())
