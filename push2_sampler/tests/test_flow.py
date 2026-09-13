"""End-to-end workflow tests driven through the simulated control surface."""

import json
import time

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.app import CLIP_WARNING_S, PRESS_FLASH_S, App
from push2sampler.audio import FADE_MS, Engine
from push2sampler.constants import (
    DISPLAY_ROW_BOTTOM,
    DISPLAY_ROW_TOP,
    ENCODER_TEMPO,
    ENCODER_TRACK,
    Btn,
)
from push2sampler.modes import Mode
from push2sampler.modes import library as library_mode
from push2sampler.project import PAGE_BARS, Project, Sample
from push2sampler.push2 import PadEvent, SimPush
from push2sampler.settings import EDITABLE, EDITABLE_PAGES, Settings

SR = 8000
FADE = int(SR * FADE_MS / 1000.0)


@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    engine = Engine(
        samplerate=SR,
        blocksize=64,
        in_channels=1,
        out_channels=2,
        backend="offline",
        bpm=120.0,
        song_bars=project.song_bars,
    )
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    app = App(push, engine, project, project_dir=tmp_path / "song", settings=settings)
    return app, push, engine, project


def pump(app):
    """One pass of App.tick(): events, the mode's own clock, then the LEDs."""
    for event in app.push.poll_events():
        app.handle(event)
    for event in app.engine.poll_events():
        app.on_engine_event(event)
    if app.engine.take_clipped():
        app._clip_until = time.monotonic() + CLIP_WARNING_S
        app.notify("input clipping")
    app.mode.on_tick()
    app.render()


def settle(app):
    """Let the press-feedback flash lapse, then render the mode's own value."""
    time.sleep(PRESS_FLASH_S)
    pump(app)


def take(engine, bars=1, value=0.5):
    """Audio of exactly ``bars`` bars, the way a real take comes out.

    Fabricating a "1 bar" sample out of 10 frames is the very thing the
    off-grid flag catches, so fixtures that stand in for takes use this.
    """
    return np.full((int(bars * engine.frames_per_bar), 1), value, dtype=np.float32)


def record_take(app, engine, bars):
    """Run a full count-in plus take of ``bars`` bars through the engine."""
    frames = int(app.count_in_beats * engine.frames_per_beat)
    frames += int(bars * engine.frames_per_bar) + 64
    engine.process_offline(frames, np.full((frames, 1), 0.3, dtype=np.float32))
    pump(app)


# ----------------------------------------------------------------- library
def test_library_starts_all_dim_white(rig):
    """Blank slots are dim by default (CC-13): 64 pads at full white is glare."""
    app, push, _, _ = rig
    pump(app)
    assert app.mode.name == "library"
    assert set(push.pad_leds) == {colors.WHITE_DIM.index}


def test_the_dimmer_can_be_turned_off(rig):
    app, push, _, _ = rig
    app.settings.set("dim_library", False)
    pump(app)
    assert set(push.pad_leds) == {colors.WHITE.index}


def test_filled_slots_are_green_blank_stay_white(rig):
    app, push, engine, project = rig
    project.put(5, take(engine), bars=1)
    app.rebuild_schedule()
    pump(app)
    assert push.pad_leds[5] == colors.GREEN.index
    assert push.pad_leds[4] == colors.WHITE_DIM.index


def test_muted_sample_is_dim_green(rig):
    app, push, engine, project = rig
    sample = project.put(0, take(engine), bars=1)
    sample.enabled = False
    pump(app)
    assert push.pad_leds[0] == colors.GREEN_DIM.index


# ------------------------------------------------------------------ record
def test_empty_pad_enters_record_mode(rig):
    app, push, _, _ = rig
    push.press_pad(9)
    pump(app)
    assert app.mode.name == "record"
    assert app.mode.slot == 9
    # Default selection is one bar: only the top-left pad is white.
    assert push.pad_leds[0] == colors.WHITE.index
    assert push.pad_leds[1] == colors.OFF.index


def test_length_selection_always_starts_at_top_left(rig):
    app, push, _, _ = rig
    push.press_pad(0)
    pump(app)
    push.press_pad(10)  # second row, third column -> 11 bars
    pump(app)
    assert app.mode.bars == 11
    assert all(push.pad_leds[i] == colors.WHITE.index for i in range(11))
    assert all(push.pad_leds[i] == colors.OFF.index for i in range(11, 64))


def test_record_button_runs_count_in_then_take(rig):
    app, push, engine, project = rig
    push.press_pad(3)
    pump(app)
    push.press_pad(1)  # two bars
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    assert engine.rec_state == "count_in"
    # Pads flash red while counting in, and the length can no longer change.
    push.press_pad(40)
    pump(app)
    assert app.mode.bars == 2

    record_take(app, engine, 2)

    sample = project[3]
    assert sample is not None
    assert sample.bars == 2
    assert sample.frames == int(2 * engine.frames_per_bar)
    assert np.allclose(sample.audio, 0.3)
    # ...and we land on that sample's own page.
    assert app.mode.name == "sample"
    assert app.mode.slot == 3
    assert not engine.is_playing


def test_recording_progress_is_shown_on_the_pads(rig):
    app, push, engine, _ = rig
    push.press_pad(0)
    pump(app)
    push.press_pad(3)  # four bars
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    # Run the count-in plus one and a half bars.
    frames = int(4 * engine.frames_per_beat + 1.5 * engine.frames_per_bar)
    engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    pump(app)
    assert engine.rec_state == "recording"
    assert push.pad_leds[0] == colors.RED_DIM.index  # captured
    assert push.pad_leds[1] == colors.RED.index  # capturing now
    assert push.pad_leds[2] == colors.WHITE.index  # still to come


def test_stop_cancels_a_take_and_leaves_the_slot_empty(rig):
    app, push, engine, project = rig
    push.press_pad(2)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    push.press_button(Btn.STOP)
    pump(app)
    assert engine.rec_state == "idle"
    assert project[2] is None
    assert app.mode.name == "record"
    push.press_button(Btn.STOP)  # a second stop backs out to the library
    pump(app)
    assert app.mode.name == "library"


def test_leaving_record_mode_cancels_the_take(rig):
    app, push, engine, _ = rig
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "library"
    assert engine.rec_state == "idle"


# ------------------------------------------------------------------ sample
def record_into(app, push, engine, slot, bars):
    push.press_pad(slot)
    pump(app)
    push.press_pad(bars - 1)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    record_take(app, engine, bars)


def test_pads_become_the_64_bars_of_the_song(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    assert app.mode.name == "sample"
    # No bar is enabled yet: only the faint phrase/section grid is lit.
    assert colors.GREEN.index not in push.pad_leds

    push.press_pad(0)
    pump(app)
    push.press_pad(8)
    pump(app)
    push.press_pad(63)
    pump(app)
    assert project[0].triggers == {0, 8, 63}
    assert push.pad_leds[0] == colors.GREEN.index
    assert push.pad_leds[8] == colors.GREEN.index
    assert push.pad_leds[63] == colors.GREEN.index
    assert push.pad_leds[1] == colors.OFF.index

    push.press_pad(8)  # toggles back off
    pump(app)
    assert project[0].triggers == {0, 63}


def test_other_samples_bars_are_shown_dim_blue(rig):
    app, push, engine, project = rig
    project.put(1, np.zeros((10, 1), dtype=np.float32), bars=1, triggers={4})
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(0)
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index
    assert push.pad_leds[4] == colors.BLUE_DIM.index


def test_mute_toggles_whether_the_sample_is_heard(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(0)
    pump(app)
    assert len(engine._schedule[0]) == 1

    push.press_button(Btn.MUTE)
    pump(app)
    assert project[0].enabled is False
    assert engine._schedule[0] == ()  # silenced while designing
    assert push.pad_leds[0] == colors.GREEN_DIM.index

    push.press_button(Btn.MUTE)
    pump(app)
    assert project[0].enabled is True
    assert len(engine._schedule[0]) == 1


def test_record_button_re_records_the_same_slot(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=6, bars=2)
    project[6].triggers.update({0, 9})
    push.press_button(Btn.RECORD)
    pump(app)
    assert app.mode.name == "record"
    assert app.mode.slot == 6
    assert app.mode.bars == 2  # the previous length is offered again

    push.press_button(Btn.RECORD)
    pump(app)
    record_take(app, engine, 2)
    assert app.mode.name == "sample"
    # Re-recording keeps the arrangement the sample already had.
    assert project[6].triggers == {0, 9}


def test_shift_delete_removes_the_sample(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.DELETE)
    pump(app)
    assert project[0] is None
    assert app.mode.name == "library"


def test_delete_then_pad_clears_the_arrangement(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(5)
    pump(app)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(20)
    pump(app)
    assert project[0].triggers == set()
    assert app.mode.name == "sample"


def test_gain_encoder_updates_the_schedule(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(0)
    pump(app)
    push.turn(ENCODER_TRACK[0], 10)
    pump(app)
    assert project[0].gain == pytest.approx(1.2)
    assert engine._schedule[0][0].gain == pytest.approx(1.2)


# --------------------------------------------------------------- transport
def test_play_triggers_the_arrangement_with_overlap(rig):
    app, push, engine, project = rig
    fpbar = int(engine.frames_per_bar)
    project.put(0, np.full((fpbar * 2, 1), 0.25, dtype=np.float32), bars=2, triggers={0})
    project.put(1, np.full((fpbar, 1), 0.25, dtype=np.float32), bars=1, triggers={1})
    app.rebuild_schedule()
    push.press_button(Btn.PLAY)
    pump(app)
    assert engine.is_playing
    out = engine.process_offline(fpbar * 2)
    assert out[FADE + 10, 0] == pytest.approx(0.25)
    # The two overlap in bar 1 (sampled clear of the declick fades).
    assert out[fpbar + FADE + 10, 0] == pytest.approx(0.5)

    push.press_button(Btn.PLAY)
    pump(app)
    assert not engine.is_playing


def test_playhead_is_shown_on_the_sample_page(rig):
    app, push, engine, project = rig
    fpbar = int(engine.frames_per_bar)
    project.put(0, np.zeros((10, 1), dtype=np.float32), bars=1, triggers={0})
    app.rebuild_schedule()
    app.goto_sample(0)
    push.press_button(Btn.PLAY)
    pump(app)
    engine.process_offline(fpbar + 10)
    pump(app)
    assert engine.current_bar == 1
    assert push.pad_leds[1] == colors.WHITE.index  # playhead
    assert push.pad_leds[0] == colors.GREEN.index


def test_library_shows_sounding_samples_in_amber(rig):
    app, push, engine, project = rig
    project.put(0, np.full((4000, 1), 0.2, dtype=np.float32), bars=1, triggers={0})
    app.rebuild_schedule()
    push.press_button(Btn.PLAY)
    pump(app)
    engine.process_offline(64)
    pump(app)
    assert push.pad_leds[0] == colors.AMBER.index


def test_tempo_encoder_and_metronome(rig):
    app, push, engine, _ = rig
    push.turn(ENCODER_TEMPO, 4)
    pump(app)
    assert engine.bpm == pytest.approx(124.0)
    push.hold_button(Btn.SHIFT, True)
    push.turn(ENCODER_TEMPO, -1)
    pump(app)
    assert engine.bpm == pytest.approx(114.0)
    push.hold_button(Btn.SHIFT, False)

    assert engine.metronome is False
    push.press_button(Btn.METRONOME)
    pump(app)
    assert engine.metronome is True


def test_loop_toggle(rig):
    """Repeat now cycles a scope rather than toggling a flag (NF-11)."""
    app, push, engine, project = rig
    assert engine.loop is True
    assert app.loop_scope == "page"
    assert engine.loop_range == (0, PAGE_BARS)  # the page you are on

    push.press_button(Btn.REPEAT)
    pump(app)
    assert app.loop_scope == "song"
    assert engine.loop is True
    assert engine.loop_range == (0, project.song_bars)  # all of it

    push.press_button(Btn.REPEAT)
    pump(app)
    assert app.loop_scope == "off"
    assert engine.loop is False

    push.press_button(Btn.REPEAT)
    pump(app)
    assert app.loop_scope == "page"  # and round again


def test_shift_pad_previews_a_sample_without_leaving_the_library(rig):
    app, push, engine, project = rig
    project.put(0, np.full((500, 1), 0.5, dtype=np.float32), bars=1)
    pump(app)
    push.hold_button(Btn.SHIFT, True)
    push.press_pad(0)
    pump(app)
    assert app.mode.name == "library"
    out = engine.process_offline(100)
    assert out[FADE + 10, 0] == pytest.approx(0.5)


def test_delete_from_the_library(rig):
    app, push, _, project = rig
    project.put(2, np.zeros((10, 1), dtype=np.float32), bars=1)
    pump(app)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(2)
    pump(app)
    assert project[2] is None
    assert app.delete_armed is False


def test_mute_shortcut_in_the_library(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1, triggers={0})
    app.rebuild_schedule()
    pump(app)
    push.press_button(Btn.MUTE)
    pump(app)
    assert app.mute_armed
    push.press_pad(0)
    pump(app)
    assert project[0].enabled is False
    assert app.engine._schedule[0] == ()
    push.press_pad(0)
    pump(app)
    assert project[0].enabled is True


def test_song_can_be_auditioned_from_record_mode(rig):
    app, push, engine, project = rig
    project.put(1, np.zeros((10, 1), dtype=np.float32), bars=1, triggers={0})
    app.rebuild_schedule()
    push.press_pad(0)
    pump(app)
    assert app.mode.name == "record"
    push.press_button(Btn.PLAY)
    pump(app)
    assert engine.is_playing
    # ...but Play is ignored once a take is running.
    push.press_button(Btn.RECORD)
    pump(app)
    assert engine.rec_state == "count_in"
    push.press_button(Btn.PLAY)
    pump(app)
    assert engine.rec_state == "count_in"


def test_autosave_skips_rewriting_unchanged_audio(rig, tmp_path):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    app.save_now()
    wav = tmp_path / "song" / "samples" / "slot_000.wav"
    mtime = wav.stat().st_mtime_ns
    push.press_pad(2)  # arrangement change only
    pump(app)
    app.save_now()
    assert wav.stat().st_mtime_ns == mtime
    assert json.loads((tmp_path / "song" / "project.json").read_text())["slots"][0][
        "triggers"
    ] == [2]


def test_autosave_round_trip(rig, tmp_path):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=4, bars=1)
    push.press_pad(3)
    pump(app)
    app.save_now()

    reloaded = Project.load(tmp_path / "song", samplerate=SR)
    assert reloaded[4] is not None
    assert reloaded[4].triggers == {3}
    assert reloaded[4].bars == 1
    assert reloaded[4].frames == project[4].frames


# --------------------------------------------------- hold to audition (CC-01)
def test_a_tap_on_a_filled_pad_opens_its_page(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    pump(app)
    push.press_pad(0)  # press and release in one pass: a tap
    pump(app)
    assert app.mode.name == "sample"
    assert app.mode.slot == 0


def test_holding_a_filled_pad_auditions_it_instead(rig, monkeypatch):
    app, push, engine, project = rig
    project.put(3, take(engine), bars=1)
    pump(app)
    monkeypatch.setattr(library_mode, "HOLD_PREVIEW_S", 0.0)

    push.inject_pad_press(3)
    pump(app)
    assert app.mode.name == "library"  # still here, and now sounding
    out = engine.process_offline(100)
    assert out[FADE + 10, 0] == pytest.approx(0.5)
    pump(app)  # LEDs follow the audio, so re-render after rendering audio
    assert push.pad_leds[3] == colors.AMBER.index  # the pad shows it playing

    push.inject_pad_release(3)
    pump(app)
    assert app.mode.name == "library"  # releasing does not navigate


def test_an_audition_stops_tracking_a_deleted_slot(rig, monkeypatch):
    app, push, _, project = rig
    project.put(0, np.zeros((100, 1), dtype=np.float32), bars=1)
    pump(app)
    monkeypatch.setattr(library_mode, "HOLD_PREVIEW_S", 10.0)
    push.inject_pad_press(0)
    pump(app)
    project.delete(0)
    pump(app)  # on_tick must not trip over the missing sample
    push.inject_pad_release(0)
    pump(app)
    assert app.mode.name == "library"


# ------------------------------------------------- phrase/section grid (CC-06)
def test_phrase_and_section_marks_on_the_sample_page(rig):
    app, push, engine, _ = rig
    record_into(app, push, engine, slot=0, bars=1)
    assert app.mode.name == "sample"
    assert push.pad_leds[0] == colors.WHITE_MID.index  # bar 1: a section start
    assert push.pad_leds[16] == colors.WHITE_MID.index  # bar 17
    assert push.pad_leds[4] == colors.WHITE_DIM.index  # bar 5: a phrase start
    assert push.pad_leds[60] == colors.WHITE_DIM.index  # bar 61
    assert push.pad_leds[1] == colors.OFF.index
    assert push.pad_leds[5] == colors.OFF.index


def test_triggers_and_the_playhead_win_over_the_grid_marks(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(4)  # a phrase-start bar
    pump(app)
    assert push.pad_leds[4] == colors.GREEN.index
    project.put(1, np.zeros((10, 1), dtype=np.float32), bars=1, triggers={16})
    app.rebuild_schedule()
    pump(app)
    assert push.pad_leds[16] == colors.BLUE_DIM.index  # another sample's bar


# ------------------------------------------------------------- undo (F-04)
def test_undo_brings_back_a_deleted_sample(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(5)  # play it on bar 6
    pump(app)
    original = project[0]

    push.press_button(Btn.SESSION)
    pump(app)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(0)
    pump(app)
    # It plays on a bar, so the first press names the cost and waits (CC-03).
    assert project[0] is not None
    assert "plays on 1 bar" in app.message
    push.press_pad(0)
    pump(app)
    assert project[0] is None
    assert engine._schedule[5] == ()

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0] is original  # same take, same audio
    assert project[0].triggers == {5}
    assert len(engine._schedule[5]) == 1  # and audible again


def test_undo_and_redo_a_bar_toggle(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(9)
    pump(app)
    assert project[0].triggers == {9}

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].triggers == set()
    assert push.pad_leds[9] == colors.OFF.index

    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.UNDO)  # Shift+Undo is redo
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert project[0].triggers == {9}
    assert push.pad_leds[9] == colors.GREEN.index


def test_undoing_a_recording_empties_the_slot_and_backs_out(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    assert app.mode.name == "sample"
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0] is None
    # The page we were on no longer has a sample, so we land back in the library.
    assert app.mode.name == "library"


def test_the_undo_button_shows_whether_there_is_anything_to_undo(rig):
    app, push, engine, _ = rig
    pump(app)
    assert push.button_leds[Btn.UNDO] == 0
    record_into(app, push, engine, slot=0, bars=1)
    assert push.button_leds[Btn.UNDO] > 0
    push.press_button(Btn.UNDO)
    pump(app)
    settle(app)
    assert push.button_leds[Btn.UNDO] == 0


def test_undo_with_nothing_to_undo_says_so(rig):
    app, push, _, _ = rig
    push.press_button(Btn.UNDO)
    pump(app)
    assert app.message == "nothing to undo"


def test_a_tempo_sweep_is_one_undo_step(rig):
    app, push, engine, project = rig
    for _ in range(5):
        push.turn(ENCODER_TEMPO, 1)
        pump(app)
    assert engine.bpm == pytest.approx(125.0)
    push.press_button(Btn.UNDO)
    pump(app)
    assert project.bpm == pytest.approx(120.0)
    assert engine.bpm == pytest.approx(120.0)  # the engine follows the undo
    assert app.history.can_undo is False


def test_a_gain_sweep_is_one_undo_step(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    for _ in range(4):
        push.turn(ENCODER_TRACK[0], 1)
        pump(app)
    assert project[0].gain == pytest.approx(1.08)
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].gain == pytest.approx(1.0)


def test_undo_restores_mute_state(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.MUTE)
    pump(app)
    assert project[0].enabled is False
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].enabled is True
    assert len(engine._schedule[0]) == 1


def test_undo_restores_a_cleared_arrangement(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    for bar in (1, 2, 3):
        push.press_pad(bar)
        pump(app)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(20)  # delete-armed: clears every bar
    pump(app)
    assert project[0].triggers == set()
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].triggers == {1, 2, 3}


# --------------------------------------------------------- dropouts (F-01)
def test_an_audio_dropout_is_surfaced_to_the_player(rig):
    app, push, engine, _ = rig
    engine.events.put(("xrun", 3))
    pump(app)
    assert "dropout" in app.message


# ------------------------------------------------- off-grid takes (F-09)
def test_an_off_grid_take_is_flagged_in_the_library_and_can_be_fixed(rig):
    app, push, engine, project = rig
    project.put(0, take(engine, bars=2), bars=2, triggers={0})
    app.rebuild_schedule()
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index

    # The same song at a new tempo: the take no longer fills two bars.
    push.hold_button(Btn.SHIFT, True)
    push.turn(ENCODER_TEMPO, 2)  # +20 BPM
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert engine.bpm == pytest.approx(140.0)
    assert project.mismatched(project[0]) is True
    assert push.pad_leds[0] == colors.YELLOW.index
    assert any("off the grid" in line for line in app.status_lines())

    # Open the slot: its page explains the problem and offers the fix.
    push.press_pad(0)
    pump(app)
    assert app.mode.name == "sample"
    assert any("OFF GRID" in line for line in app.status_lines())
    assert push.button_leds[DISPLAY_ROW_BOTTOM[0]] > 0

    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    assert project.mismatched(project[0]) is False
    assert project[0].frames == project.expected_frames(2)
    assert app.message == "repaired length"


def test_repairing_a_length_is_undoable(rig):
    app, push, engine, project = rig
    project.put(0, take(engine, bars=1), bars=1)
    project.bpm = 140.0  # the take no longer fits a bar
    original = project[0].audio
    app.goto_sample(0)
    pump(app)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    assert project[0].audio is not original

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].audio is original
    assert project[0].audio_saved is False  # the repaired WAV must be replaced


def test_the_repair_button_says_nothing_to_do_when_the_take_fits(rig):
    app, push, engine, project = rig
    project.put(0, take(engine, bars=1), bars=1)
    app.goto_sample(0)
    pump(app)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    assert app.message == "this take already fits its bars"


# ------------------------------------- metering and monitoring (F-07)
def test_shift_metronome_cycles_monitoring(rig):
    app, push, engine, _ = rig
    assert engine.monitor == "off"
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.METRONOME)
    pump(app)
    assert engine.monitor == "auto"
    push.press_button(Btn.METRONOME)
    pump(app)
    assert engine.monitor == "on"
    push.press_button(Btn.METRONOME)
    pump(app)
    assert engine.monitor == "off"
    push.hold_button(Btn.SHIFT, False)
    # Unshifted, it is still the click.
    push.press_button(Btn.METRONOME)
    pump(app)
    assert engine.metronome is True
    assert engine.monitor == "off"


def test_the_input_meter_lights_the_row_above_the_display(rig):
    app, push, engine, _ = rig
    pump(app)
    assert all(push.button_leds[cc] == 0 for cc in DISPLAY_ROW_TOP)
    engine.process_offline(64, np.full((64, 1), 0.5, dtype=np.float32))
    pump(app)
    lit = [cc for cc in DISPLAY_ROW_TOP if push.button_leds[cc] > 0]
    assert len(lit) == 4  # half scale
    assert any("in [####" in line for line in app.status_lines())


def test_clipping_is_shown_on_the_surface(rig):
    app, push, engine, _ = rig
    engine.process_offline(64, np.full((64, 1), 1.5, dtype=np.float32))
    pump(app)
    assert app.message == "input clipping"
    assert app.input_clipping is True
    assert push.button_leds[Btn.RECORD] == colors.RED.index
    assert any("CLIP" in line for line in app.status_lines())


# ---------------------------------------------------------- mode stack (F-03)
class Overlay(Mode):
    """A throwaway overlay, to test the stack without a real page."""

    name = "overlay"
    transient = True

    def __init__(self, app, tag="a"):
        super().__init__(app)
        self.tag = tag
        self.exits = 0

    def on_exit(self):
        self.exits += 1


def test_overlays_stack_and_pop_in_order(rig):
    app, _, _, _ = rig
    first, second = Overlay(app, "a"), Overlay(app, "b")
    assert app.depth == 1
    assert app.push_mode(first) is True
    assert app.push_mode(second) is True
    assert app.depth == 3
    assert app.mode is second

    assert app.pop_mode() is True
    assert app.mode is first
    assert second.exits == 1
    assert app.pop_mode() is True
    assert app.mode.name == "library"
    assert first.exits == 1
    assert app.pop_mode() is False  # the root never pops


def test_the_stack_is_capped(rig):
    app, _, _, _ = rig
    assert app.push_mode(Overlay(app)) is True
    assert app.push_mode(Overlay(app)) is True
    assert app.push_mode(Overlay(app)) is True
    assert app.depth == 4
    assert app.push_mode(Overlay(app)) is False  # no burying yourself
    assert app.message == "too many layers open"
    assert app.depth == 4


def test_going_home_unwinds_every_overlay(rig):
    app, _, _, _ = rig
    first, second = Overlay(app, "a"), Overlay(app, "b")
    app.push_mode(first)
    app.push_mode(second)
    app.goto_library()
    assert app.depth == 1
    assert app.mode.name == "library"
    assert first.exits == 1
    assert second.exits == 1


def test_session_closes_an_overlay_before_going_home(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    assert app.mode.name == "sample"
    app.push_mode(Overlay(app))
    push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "sample"  # back to the page underneath
    push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "library"


# ------------------------------------------------------ settings page (F-06)
def test_setup_opens_and_closes_the_settings_page(rig):
    app, push, _, _ = rig
    push.press_button(Btn.SETUP)
    pump(app)
    assert app.mode.name == "settings"
    assert app.depth == 2
    # The pads are dark, so there is no mistaking it for a page that edits audio.
    assert set(push.pad_leds) == {0}

    push.press_button(Btn.SETUP)
    pump(app)
    assert app.mode.name == "library"


def test_shift_setup_still_saves_the_project(rig):
    app, push, engine, _ = rig
    record_into(app, push, engine, slot=0, bars=1)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.SETUP)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert app.mode.name == "sample"  # no overlay opened
    assert app.message == "project saved"


def test_each_encoder_edits_its_own_setting(rig):
    app, push, engine, _ = rig
    push.press_button(Btn.SETUP)
    pump(app)

    push.turn(ENCODER_TRACK[0], 2)  # count-in
    pump(app)
    assert app.settings["count_in_beats"] == 6
    assert app.count_in_beats == 6

    push.turn(ENCODER_TRACK[1], 1)  # monitor
    pump(app)
    assert app.settings["monitor"] == "auto"
    assert engine.monitor == "auto"

    push.turn(ENCODER_TRACK[2], -4)  # monitor gain
    pump(app)
    assert app.settings["monitor_gain"] == pytest.approx(0.8)
    assert engine.monitor_gain == pytest.approx(0.8)

    push.turn(ENCODER_TRACK[3], 10)  # record latency
    pump(app)
    assert app.settings["rec_latency_ms"] == pytest.approx(10.0)
    assert engine.rec_latency_frames == int(SR * 10 / 1000)


def test_pressing_a_settings_button_cycles_its_value(rig):
    app, push, engine, _ = rig
    push.press_button(Btn.SETUP)
    pump(app)
    push.press_button(DISPLAY_ROW_BOTTOM[4])  # play while recording
    pump(app)
    assert app.settings["play_while_recording"] is False
    assert engine.play_while_recording is False
    assert app.message == "play while rec off"

    push.press_button(DISPLAY_ROW_BOTTOM[1])  # monitor: off -> auto
    pump(app)
    assert app.settings["monitor"] == "auto"


def test_the_count_in_setting_changes_the_next_take(rig):
    app, push, engine, project = rig
    push.press_button(Btn.SETUP)
    pump(app)
    push.turn(ENCODER_TRACK[0], -2)  # two beats of count-in
    pump(app)
    push.press_button(Btn.SETUP)
    pump(app)
    assert app.count_in_beats == 2

    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    assert engine.count_in_beats_left == 2
    record_take(app, engine, 1)
    assert project[0] is not None


def test_settings_are_written_when_the_page_closes(rig, tmp_path):
    app, push, _, _ = rig
    push.press_button(Btn.SETUP)
    pump(app)
    push.turn(ENCODER_TRACK[0], 1)
    pump(app)
    assert not (tmp_path / "settings.json").exists()  # not yet

    push.press_button(Btn.SETUP)
    pump(app)
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["count_in_beats"] == 5
    assert app.message == "settings saved"


def test_a_device_that_will_not_open_keeps_the_old_one(rig, monkeypatch):
    app, push, engine, _ = rig
    before = engine.blocksize
    engine.backend = "sounddevice"  # pretend there is a real stream to reopen
    monkeypatch.setattr(
        engine, "_start_sounddevice",
        lambda: (_ for _ in ()).throw(RuntimeError("no such device")),
    )
    push.press_button(Btn.SETUP)
    pump(app)
    push.turn(ENCODER_TRACK[7], 1)  # block size: needs a stream restart
    pump(app)
    # The engine names the real problem rather than a generic failure.
    assert app.message == "audio: no such device"
    assert engine.blocksize == before  # put back
    assert app.mode.name == "settings"  # and the instrument is still running


def test_editable_settings_all_fit_the_button_row(rig):
    app, push, _, _ = rig
    push.press_button(Btn.SETUP)
    pump(app)
    settle(app)  # the Setup press flashes its own LED, not the row's
    lit = [cc for cc in DISPLAY_ROW_BOTTOM if push.button_leds.get(cc, 0) > 0]
    assert len(lit) == len(EDITABLE_PAGES[0])
    lines = app.status_lines()
    assert lines[0].startswith("SETTINGS")
    assert any("count-in" in line for line in lines)


def test_the_settings_page_scrolls_to_reach_every_setting(rig):
    app, push, _, _ = rig
    push.press_button(Btn.SETUP)
    pump(app)
    seen = set()
    for _ in range(len(EDITABLE_PAGES)):
        seen |= set(app.mode.names)
        push.press_button(Btn.DOWN)
        pump(app)
    assert seen == set(EDITABLE)
    # ...and it wraps back to where it started.
    assert app.mode.page == 0


# ------------------------------------------------------ perform mode (NF-04)
def live_rig(rig, slots=(0, 1)):
    """A rig with a couple of playable samples and the loop running."""
    app, push, engine, project = rig
    for slot in slots:
        project.put(slot, take(engine, bars=1, value=0.5), bars=1)
    app.rebuild_schedule()
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.PLAY)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    return app, push, engine, project


def test_shift_play_opens_perform_mode_and_starts_the_loop(rig):
    app, push, engine, _ = live_rig(rig)
    assert app.mode.name == "perform"
    assert app.depth == 2  # an overlay over the library
    assert engine.is_playing


def test_a_pad_fires_its_sample_on_the_next_grid_line(rig):
    app, push, engine, _ = live_rig(rig)
    fpbar = int(engine.frames_per_bar)
    engine.process_offline(fpbar // 2)  # mid-bar

    push.press_pad(0)
    pump(app)
    out = engine.process_offline(fpbar)
    silence = fpbar - fpbar // 2
    assert np.all(out[: silence - 1] == 0.0)  # waits for the bar line
    assert out[silence + FADE, 0] > 0.0


def test_an_empty_pad_fires_nothing(rig):
    app, push, engine, _ = live_rig(rig)
    push.press_pad(40)
    pump(app)
    assert np.all(engine.process_offline(200) == 0.0)


def test_quantize_cycles_and_off_means_now(rig):
    app, push, engine, _ = live_rig(rig)
    assert app.mode.quantize_beats == 4.0
    push.press_button(Btn.FIXED_LENGTH)
    pump(app)
    assert app.mode.quantize_beats == 0.0
    assert app.message == "quantize off"

    push.press_pad(0)
    pump(app)
    out = engine.process_offline(200)
    assert out[FADE + 10, 0] > 0.0  # no waiting


def test_record_writes_what_you_play_into_the_song(rig):
    app, push, engine, project = live_rig(rig)
    fpbar = int(engine.frames_per_bar)
    push.press_button(Btn.RECORD)
    pump(app)
    assert app.mode.writing is True

    engine.process_offline(fpbar + fpbar // 2)  # half way through bar 1
    push.press_pad(0)
    pump(app)
    # Bar-quantised, so it sounds in bar 2 and that is where it is written.
    assert project[0].triggers == {2}
    assert len(engine._schedule[2]) == 1

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].triggers == set()


def test_playing_without_record_changes_nothing(rig):
    app, push, engine, project = live_rig(rig)
    push.press_pad(0)
    pump(app)
    assert project[0].triggers == set()
    assert app.history.can_undo is False


def test_replaying_a_bar_that_is_already_written_is_not_a_second_edit(rig):
    app, push, engine, project = live_rig(rig)
    push.press_button(Btn.RECORD)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert project[0].triggers == {0}
    push.press_pad(0)
    pump(app)
    assert "already plays" in app.message
    assert project[0].triggers == {0}


def test_delete_erases_bars_as_the_playhead_passes(rig):
    app, push, engine, project = live_rig(rig)
    fpbar = int(engine.frames_per_bar)
    project[0].triggers.update({0, 1, 2, 3})
    project[1].triggers.add(1)
    app.rebuild_schedule()

    push.press_button(Btn.DELETE)
    pump(app)
    assert app.delete_armed is True

    engine.process_offline(fpbar + 10)  # into bar 1
    pump(app)
    assert project[0].triggers == {0, 2, 3}  # bar 1 wiped, for every sample
    assert project[1].triggers == set()
    assert app.message == "erased bar 2"

    engine.process_offline(fpbar)  # into bar 2
    pump(app)
    assert project[0].triggers == {0, 3}

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].triggers == {0, 2, 3}


def test_erasing_stops_when_delete_is_unarmed(rig):
    app, push, engine, project = live_rig(rig)
    fpbar = int(engine.frames_per_bar)
    project[0].triggers.update({1, 2})
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_button(Btn.DELETE)  # unarmed again
    pump(app)
    engine.process_offline(fpbar + 10)
    pump(app)
    assert project[0].triggers == {1, 2}


def test_the_pads_show_what_is_playable_and_what_is_sounding(rig):
    app, push, engine, project = live_rig(rig)
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index
    assert push.pad_leds[40] == colors.WHITE_DIM.index  # empty: nothing to fire

    push.press_pad(0)
    pump(app)
    engine.process_offline(int(engine.frames_per_bar))
    pump(app)
    assert push.pad_leds[0] == colors.AMBER.index


def test_session_leaves_perform_mode_for_the_library(rig):
    app, push, _, _ = live_rig(rig)
    push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "library"
    assert app.depth == 1


def test_shift_play_again_closes_perform_mode(rig):
    app, push, _, _ = live_rig(rig)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.PLAY)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert app.mode.name == "library"


# ------------------------------------------------- velocity on the surface
def test_how_hard_you_hit_a_pad_sets_the_level(rig):
    app, push, engine, project = live_rig(rig)
    sample = project[0]
    sample.velocity_sensitivity = 1.0
    app.mode.quantize_index = 0  # fire immediately, so the level is easy to read

    push.inject(PadEvent(0, True, 64))
    push.inject(PadEvent(0, False, 0))
    pump(app)
    out = engine.process_offline(200)
    assert out[FADE + 10, 0] == pytest.approx(0.5 * 64 / 127, abs=0.01)


def test_velocity_is_ignored_until_the_sample_asks_for_it(rig):
    app, push, engine, project = live_rig(rig)
    app.mode.quantize_index = 0
    push.inject(PadEvent(0, True, 30))
    push.inject(PadEvent(0, False, 0))
    pump(app)
    out = engine.process_offline(200)
    assert out[FADE + 10, 0] == pytest.approx(0.5, abs=0.01)  # flat, as recorded


def test_a_played_in_arrangement_keeps_its_dynamics(rig):
    app, push, engine, project = live_rig(rig)
    project[0].velocity_sensitivity = 1.0
    push.press_button(Btn.RECORD)
    pump(app)
    push.inject(PadEvent(0, True, 55))
    push.inject(PadEvent(0, False, 0))
    pump(app)
    assert project[0].velocity_at(0) == 55
    # The schedule's gain is the sample's gain (1.0) scaled by the velocity --
    # the 0.5 in the fixture is the audio's amplitude, not its gain.
    assert engine._schedule[0][0].gain == pytest.approx(55 / 127, abs=0.01)


def test_accent_turns_velocity_on_for_a_sample(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    assert project[0].velocity_sensitivity == 0.0

    push.press_button(Btn.ACCENT)
    pump(app)
    assert project[0].velocity_sensitivity == 1.0
    assert app.message == "velocity on"
    assert push.button_leds[Btn.ACCENT] > 0

    push.press_button(Btn.ACCENT)
    pump(app)
    assert project[0].velocity_sensitivity == 0.0

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].velocity_sensitivity == 1.0


def test_the_sample_page_shows_how_hard_each_bar_was_played(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    sample = project[0]
    sample.velocity_sensitivity = 1.0
    sample.set_trigger(0, True, velocity=127)
    sample.set_trigger(1, True, velocity=70)
    sample.set_trigger(2, True, velocity=20)
    app.rebuild_schedule()
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index
    assert push.pad_leds[1] == colors.GREEN_MID.index
    assert push.pad_leds[2] == colors.GREEN_DIM.index


def test_without_velocity_every_bar_is_the_same_green(rig):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=0, bars=1)
    project[0].set_trigger(0, True, velocity=20)
    project[0].set_trigger(1, True)
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index
    assert push.pad_leds[1] == colors.GREEN.index


# --------------------------------------------------------- bouncing (NF-05)
def test_shift_record_bounces_the_song_to_a_file(rig, tmp_path):
    app, push, engine, project = rig
    project.put(0, take(engine, bars=1), bars=1, triggers={0, 1})
    app.rebuild_schedule()
    pump(app)

    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.RECORD)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert app.bounce is not None
    assert app.message == "bouncing..."
    # The grid becomes one progress bar while it renders.
    assert colors.AMBER_DIM.index in push.pad_leds
    assert any("BOUNCING" in line for line in app.status_lines())

    for _ in range(400):  # the event loop steps the render a chunk at a time
        app.tick()
        if app.bounce is None:
            break
    assert app.bounce is None
    bounces = list((tmp_path / "song" / "bounces").glob("*.wav"))
    assert len(bounces) == 1
    assert "bounced" in app.message

    from push2sampler import wavio

    audio, rate = wavio.read(bounces[0])
    assert rate == SR
    assert audio.shape[1] == 2
    assert np.abs(audio).max() > 0.4


def test_bouncing_an_empty_song_says_so(rig):
    app, push, _, _ = rig
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.RECORD)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert app.bounce is None
    assert app.message == "nothing to bounce yet"


def test_a_second_bounce_request_is_refused_while_one_runs(rig):
    app, push, engine, project = rig
    project.put(0, take(engine, bars=1), bars=1, triggers={0})
    app.rebuild_schedule()
    assert app.start_bounce() is True
    assert app.start_bounce() is False
    assert app.message == "already bouncing"


def test_recording_still_works_unshifted(rig):
    app, push, _, _ = rig
    push.press_button(Btn.RECORD)  # no Shift: the old meaning
    pump(app)
    assert app.mode.name == "record"
    assert app.bounce is None


# ----------------------------------------------------- sample editor (NF-03)
def open_editor(rig, slot=0):
    app, push, engine, project = rig
    record_into(app, push, engine, slot=slot, bars=1)
    push.press_button(Btn.DEVICE)
    pump(app)
    return app, push, engine, project


def test_device_opens_the_editor_over_the_sample_page(rig):
    app, push, _, _ = open_editor(rig)
    assert app.mode.name == "edit"
    # The sample page replaces the library rather than stacking on it, so the
    # editor is the only overlay: depth 2, not 3.
    assert app.depth == 2

    push.press_button(Btn.DEVICE)
    pump(app)
    assert app.mode.name == "sample"  # back to where it was opened from


def test_each_encoder_shapes_one_thing(rig):
    app, push, _, project = open_editor(rig)
    sample = project[0]

    push.turn(ENCODER_TRACK[0], 4)  # trim in
    pump(app)
    assert sample.edits.trim_start_ms == pytest.approx(20.0)
    assert app.message == "trim in 20ms"  # the page's wording, not the field name

    push.turn(ENCODER_TRACK[4], 3)  # pitch
    pump(app)
    assert sample.edits.pitch_semitones == pytest.approx(3.0)

    push.turn(ENCODER_TRACK[6], 1)  # reverse is a switch
    pump(app)
    assert sample.edits.reverse is True

    push.turn(ENCODER_TRACK[5], 4)  # gain is the sample's own, not an edit
    pump(app)
    assert sample.gain == pytest.approx(1.2)
    assert sample.edits.trim_start_ms == pytest.approx(20.0)


def test_an_edit_is_heard_without_touching_the_recording(rig):
    app, push, engine, project = open_editor(rig)
    sample = project[0]
    raw_frames = sample.raw_frames

    push.turn(ENCODER_TRACK[1], 20)  # trim 100ms off the end
    pump(app)
    assert sample.raw_frames == raw_frames
    assert sample.frames < raw_frames
    # ...and the scheduler picks up the shorter version.
    sample.set_trigger(0, True)
    app.rebuild_schedule()
    assert engine._schedule[0][0].buf.shape[0] == sample.frames


def test_a_button_under_the_display_puts_a_parameter_back(rig):
    app, push, _, project = open_editor(rig)
    push.turn(ENCODER_TRACK[2], 10)  # fade in
    pump(app)
    assert project[0].edits.fade_in_ms == pytest.approx(20.0)

    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(app)
    assert project[0].edits.fade_in_ms == 0.0

    push.press_button(DISPLAY_ROW_BOTTOM[2])  # already there
    pump(app)
    assert "already" in app.message


def test_a_switch_is_toggled_by_its_button(rig):
    app, push, _, project = open_editor(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[7])  # normalise
    pump(app)
    assert project[0].edits.normalize is True
    push.press_button(DISPLAY_ROW_BOTTOM[7])
    pump(app)
    assert project[0].edits.normalize is False


def test_an_encoder_sweep_is_one_undo_step(rig):
    app, push, _, project = open_editor(rig)
    for _ in range(5):
        push.turn(ENCODER_TRACK[0], 1)
        pump(app)
    assert project[0].edits.trim_start_ms == pytest.approx(25.0)
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].edits.trim_start_ms == 0.0


def test_shift_device_applies_the_edits_and_undo_takes_them_back(rig):
    app, push, _, project = open_editor(rig)
    sample = project[0]
    raw = sample.audio
    push.turn(ENCODER_TRACK[6], 1)  # reverse
    pump(app)

    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.DEVICE)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert sample.edits.is_default
    assert sample.audio is not raw
    assert app.message == "edits applied"

    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].audio is raw
    assert project[0].edits.reverse is True


def test_applying_nothing_says_so(rig):
    app, push, _, _ = open_editor(rig)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.DEVICE)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert app.message == "nothing to apply"


def test_the_grid_draws_the_take_and_what_is_being_trimmed(rig):
    app, push, engine, project = open_editor(rig)
    # A take that is loud in its first half and silent in its second.
    half = int(engine.frames_per_bar) // 2
    audio = np.zeros((half * 2, 1), dtype=np.float32)
    audio[:half] = 0.8
    project[0].audio = audio
    project[0].set_edits(project[0].edits)  # drop the cache
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index  # loud
    assert push.pad_leds[63] == colors.OFF.index  # silent

    push.turn(ENCODER_TRACK[0], 100)  # trim a long way in
    pump(app)
    assert push.pad_leds[0] == colors.RED_DIM.index  # cut away


def test_a_pad_auditions_from_that_point(rig):
    app, push, engine, project = open_editor(rig)
    push.press_pad(0)
    pump(app)
    out = engine.process_offline(200)
    assert np.abs(out).max() > 0.0


def test_the_editor_refuses_to_open_on_an_empty_slot(rig):
    from push2sampler.modes import SampleEditMode

    app, _, _, _ = rig
    app.push_mode(SampleEditMode(app, 9))  # slot 10 is empty
    assert app.mode.name == "library"  # it closed itself again
    assert app.depth == 1


# ============================================== NF-02: play modes and chokes
def a_sample(rig, slot=0, bars=1):
    """Put a take in a slot and open its page, the way recording would."""
    app, push, engine, project = rig
    project.install(slot, Sample(slot=slot, bars=bars, audio=take(engine, bars)))
    app.goto_sample(slot)
    pump(app)
    return project[slot]


def test_a_button_below_the_display_sets_each_play_mode(rig):
    from push2sampler.constants import ONE_SHOT, PLAY_MODES

    app, push, engine, project = rig
    sample = a_sample(rig)
    assert sample.play_mode == ONE_SHOT

    for index, mode in enumerate(PLAY_MODES):
        push.press_button(DISPLAY_ROW_BOTTOM[1 + index])
        pump(app)
        assert sample.play_mode == mode, mode


def test_the_current_play_mode_is_the_lit_button(rig):
    from push2sampler.constants import BTN_BRIGHT, BTN_DIM, GATE

    app, push, engine, project = rig
    a_sample(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[3])       # third mode: gate
    settle(app)
    assert project[0].play_mode == GATE
    lit = {cc: push.button_leds.get(cc) for cc in DISPLAY_ROW_BOTTOM[1:5]}
    assert lit[DISPLAY_ROW_BOTTOM[3]] == BTN_BRIGHT
    assert [v for cc, v in lit.items() if cc != DISPLAY_ROW_BOTTOM[3]] == [BTN_DIM] * 3


def test_setting_a_play_mode_is_one_undo_step(rig):
    from push2sampler.constants import LOOP, ONE_SHOT

    app, push, engine, project = rig
    a_sample(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])       # loop
    pump(app)
    assert project[0].play_mode == LOOP
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].play_mode == ONE_SHOT


def test_pressing_the_mode_already_set_says_so_and_does_not_stack_undo(rig):
    """A no-op should not consume an undo step someone may need."""
    app, push, engine, project = rig
    a_sample(rig)
    assert not app.history.can_undo
    push.press_button(DISPLAY_ROW_BOTTOM[1])       # one_shot, already set
    pump(app)
    assert not app.history.can_undo
    assert "already one shot" in " ".join(app.status_lines())


def test_the_last_button_cycles_the_choke_group(rig):
    from push2sampler.constants import CHOKE_GROUPS

    app, push, engine, project = rig
    sample = a_sample(rig)
    assert sample.choke_group is None
    for expected in range(1, CHOKE_GROUPS + 1):
        push.press_button(DISPLAY_ROW_BOTTOM[7])
        pump(app)
        assert sample.choke_group == expected
    push.press_button(DISPLAY_ROW_BOTTOM[7])       # past 8 wraps to off
    pump(app)
    assert sample.choke_group is None


def test_the_choke_group_is_undoable(rig):
    app, push, engine, project = rig
    a_sample(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[7])
    pump(app)
    assert project[0].choke_group == 1
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].choke_group is None


def test_the_display_names_the_mode_and_the_group(rig):
    app, push, engine, project = rig
    a_sample(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[3])       # gate
    pump(app)
    push.press_button(DISPLAY_ROW_BOTTOM[7])       # choke 1
    pump(app)
    lines = " ".join(app.mode.status_lines())
    assert "gate" in lines
    assert "choke 1" in lines


def test_play_mode_survives_a_save_and_load(rig, tmp_path):
    from push2sampler.constants import RETRIGGER

    app, push, engine, project = rig
    a_sample(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[4])       # retrigger
    pump(app)
    push.press_button(DISPLAY_ROW_BOTTOM[7])
    pump(app)
    project.save(tmp_path / "saved")

    reloaded = Project.load(tmp_path / "saved", samplerate=SR)
    assert reloaded[0].play_mode == RETRIGGER
    assert reloaded[0].choke_group == 1


def test_the_schedule_carries_the_mode_and_group(rig):
    from push2sampler.constants import GATE

    app, push, engine, project = rig
    sample = a_sample(rig)
    sample.play_mode = GATE
    sample.choke_group = 3
    sample.set_trigger(0, True)
    entry = project.build_schedule()[0][0]
    assert entry.play_mode == GATE
    assert entry.choke_group == 3


# ================================================== CC-19: swap two samples
def two_samples(rig):
    app, push, engine, project = rig
    project.install(0, Sample(slot=0, bars=1, audio=take(engine, 1, 0.25),
                              name="kick", color=1))
    project.install(1, Sample(slot=1, bars=1, audio=take(engine, 1, 0.75),
                              name="snare", color=6))
    pump(app)
    return project


def arm_swap(rig):
    app, push, engine, project = rig
    app.shift = True
    push.press_button(Btn.DUPLICATE)
    pump(app)
    app.shift = False
    return app


def test_shift_duplicate_arms_swap_and_plain_duplicate_still_copies(rig):
    app, push, engine, project = rig
    two_samples(rig)

    arm_swap(rig)
    assert app.swap_armed and not app.duplicate_armed

    push.press_button(Btn.DUPLICATE)      # no shift: the old gesture
    pump(app)
    assert app.duplicate_armed and not app.swap_armed


def test_two_presses_swap_the_slots(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)

    push.press_pad(0)
    pump(app)
    assert app.swap_armed                  # still waiting for the second
    assert project[0].name == "kick"

    push.press_pad(1)
    pump(app)
    assert not app.swap_armed
    assert project[0].name == "snare"
    assert project[1].name == "kick"
    assert "swapped 1 and 2" in app.message


def test_the_swap_is_one_undo_step(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    push.press_pad(0)
    pump(app)
    push.press_pad(1)
    pump(app)
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].name == "kick"
    assert project[1].name == "snare"


def test_pressing_the_same_slot_twice_cancels(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    push.press_pad(0)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert not app.swap_armed
    assert project[0].name == "kick"       # nothing moved
    assert "cancelled" in app.message


def test_shift_duplicate_again_cancels_before_any_press(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    arm_swap(rig)
    assert not app.swap_armed


def test_an_empty_first_slot_is_refused_with_a_reason(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    push.press_pad(40)                     # empty
    pump(app)
    assert app.swap_armed                  # still waiting
    assert "pick a filled one" in app.message


def test_an_empty_second_slot_is_a_move(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    push.press_pad(0)
    pump(app)
    push.press_pad(40)
    pump(app)
    assert project[0] is None
    assert project[40].name == "kick"
    assert "moved" in app.message


def test_the_picked_slot_holds_white_while_the_rest_flash(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    push.press_pad(0)
    settle(app)
    assert push.pad_leds[0] == colors.WHITE.index
    assert push.pad_leds[1] in (colors.USER_COLORS[1].index, colors.OFF.index)
    assert push.pad_leds[40] == colors.OFF.index      # empty: nothing to pick


def test_swap_arming_uses_a_different_colour_from_duplicate(rig):
    """Two arming states that look the same are worse than either."""
    app, push, engine, project = rig
    two_samples(rig)
    push.press_button(Btn.DUPLICATE)
    settle(app)
    duplicate_look = set(push.pad_leds[:2])
    push.press_button(Btn.DUPLICATE)       # off
    pump(app)
    arm_swap(rig)
    settle(app)
    swap_look = set(push.pad_leds[:2])
    assert duplicate_look != swap_look


def test_the_display_explains_the_swap_at_each_step(rig):
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    lines = " ".join(app.mode.status_lines())
    assert "SWAP" in lines
    assert "first slot" in lines

    push.press_pad(0)
    pump(app)
    lines = " ".join(app.mode.status_lines())
    assert "SWAP slot 1 kick" in lines
    assert "changes places with" in lines


def test_stop_stop_disarms_a_swap(rig):
    """The panic gesture has to clear every armed state, including new ones."""
    app, push, engine, project = rig
    two_samples(rig)
    arm_swap(rig)
    push.press_button(Btn.STOP)
    pump(app)
    push.press_button(Btn.STOP)
    pump(app)
    assert not app.swap_armed


# ============================ CC-20: the mode banner says where you are
def test_every_mode_has_a_banner_and_none_of_them_is_empty(rig):
    app, push, engine, project = rig
    project.install(0, Sample(slot=0, bars=1, audio=take(engine, 1), name="kick"))
    pump(app)

    seen = {}
    for opener in (lambda: app.goto_library(),
                   lambda: app.goto_sample(0),
                   lambda: app.goto_record(1, 2),
                   lambda: app.open_mixer(),
                   lambda: app.open_song(),
                   lambda: app.open_browser(),
                   lambda: app.open_settings(),
                   lambda: app.open_master()):
        app.goto_library()
        opener()
        pump(app)
        banner, state = app.mode_banner()
        assert banner and banner.strip(), app.mode.name
        # Starts with the page's own name, shouted.  Not "all upper case": the
        # transient form's "over" is a deliberate lowercase connector, and a
        # slot's own name keeps the case its owner gave it.
        assert banner[0].isupper(), banner
        seen[app.mode.name] = banner
    # Different pages say different things -- a banner that could sit on any
    # page is not a banner.
    assert len(set(seen.values())) == len(seen), seen


def test_a_mode_with_no_title_falls_back_to_its_name():
    from push2sampler.modes import Mode

    class Bare(Mode):
        name = "whatever"

    assert Bare(None).title == "WHATEVER"


def test_the_banner_names_what_a_transient_is_layered_over(rig):
    """The thing people get wrong about layered modes, said out loud."""
    app, push, engine, project = rig
    project.install(0, Sample(slot=0, bars=1, audio=take(engine, 1), name="kick"))
    app.goto_sample(0)
    pump(app)
    app.open_settings()
    pump(app)
    banner, _state = app.mode_banner()
    assert banner.startswith("SETUP")
    assert "over" in banner
    assert "SLOT 1" in banner


def test_a_page_that_replaced_another_does_not_say_over(rig):
    app, push, engine, project = rig
    project.install(0, Sample(slot=0, bars=1, audio=take(engine, 1)))
    app.goto_sample(0)
    pump(app)
    banner, _state = app.mode_banner()
    assert "over" not in banner


def test_the_banner_turns_recording_while_a_take_runs(rig):
    app, push, engine, project = rig
    app.goto_record(0, 1)
    pump(app)
    assert app.mode_banner()[1] == "normal"
    push.press_button(Btn.RECORD)
    pump(app)
    assert engine.rec_state != "idle"
    assert app.mode_banner()[1] == "recording"


def test_the_banner_turns_armed_when_something_destructive_is(rig):
    app, push, engine, project = rig
    project.install(0, Sample(slot=0, bars=1, audio=take(engine, 1)))
    pump(app)
    push.press_button(Btn.DELETE)
    pump(app)
    assert app.delete_armed
    assert app.mode_banner()[1] == "armed"


def test_the_banner_state_comes_from_the_transport_not_the_words(rig):
    """Colour is emphasis here, so it must be driven by state rather than by
    whatever the title happens to say."""
    app, push, engine, project = rig
    app.goto_record(0, 1)
    pump(app)
    title, state = app.mode_banner()
    assert "RECORD" in title            # the word says record...
    assert state == "normal"            # ...but nothing is recording yet


def test_the_banner_is_not_repeated_in_the_status_lines(rig):
    """The terminal simulator prints status lines, so a banner in both would
    show twice there."""
    app, push, engine, project = rig
    pump(app)
    banner, _state = app.mode_banner()
    assert banner not in app.status_lines()


def test_the_record_banner_counts_its_bars(rig):
    app, push, engine, project = rig
    app.goto_record(0, 1)
    pump(app)
    assert app.mode_banner()[0] == "RECORD 1 BAR"
    app.goto_record(0, 4)
    pump(app)
    assert app.mode_banner()[0] == "RECORD 4 BARS"


def test_the_library_banner_names_the_bank(rig):
    app, push, engine, project = rig
    pump(app)
    assert app.mode_banner()[0] == "LIBRARY A"
    push.press_button(Btn.PAGE_RIGHT)
    pump(app)
    assert app.mode_banner()[0] == "LIBRARY B"


def test_the_sample_banner_names_the_slot_and_its_name(rig):
    app, push, engine, project = rig
    project.install(0, Sample(slot=0, bars=1, audio=take(engine, 1), name="kick"))
    app.goto_sample(0)
    pump(app)
    assert app.mode_banner()[0] == 'SLOT 1 "kick"'
