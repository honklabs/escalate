"""End-to-end workflow tests driven through the simulated control surface."""

import json

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.app import App
from push2sampler.audio import Engine
from push2sampler.constants import Btn, ENCODER_TEMPO, ENCODER_TRACK
from push2sampler.project import Project
from push2sampler.push2 import SimPush

SR = 8000


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
    app = App(push, engine, project, project_dir=tmp_path / "song")
    return app, push, engine, project


def pump(app):
    """Deliver queued surface/engine events and refresh the LEDs."""
    for event in app.push.poll_events():
        app.handle(event)
    for event in app.engine.poll_events():
        app.on_engine_event(event)
    app.render()


def record_take(app, engine, bars):
    """Run a full count-in plus take of ``bars`` bars through the engine."""
    frames = int(app.count_in_beats * engine.transport.frames_per_beat)
    frames += int(bars * engine.transport.frames_per_bar) + 64
    engine.process_offline(frames, np.full((frames, 1), 0.3, dtype=np.float32))
    pump(app)


# ----------------------------------------------------------------- library
def test_library_starts_all_white(rig):
    app, push, _, _ = rig
    pump(app)
    assert app.mode.name == "library"
    assert set(push.pad_leds) == {colors.WHITE.index}


def test_filled_slots_are_green_blank_stay_white(rig):
    app, push, _, project = rig
    project.put(5, np.zeros((100, 1), dtype=np.float32), bars=1)
    app.rebuild_schedule()
    pump(app)
    assert push.pad_leds[5] == colors.GREEN.index
    assert push.pad_leds[4] == colors.WHITE.index


def test_muted_sample_is_dim_green(rig):
    app, push, _, project = rig
    sample = project.put(0, np.zeros((10, 1), dtype=np.float32), bars=1)
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
    assert sample.frames == int(2 * engine.transport.frames_per_bar)
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
    frames = int(4 * engine.transport.frames_per_beat + 1.5 * engine.transport.frames_per_bar)
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
    assert all(v == colors.OFF.index for v in push.pad_leds)

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
    fpbar = int(engine.transport.frames_per_bar)
    project.put(0, np.full((fpbar * 2, 1), 0.25, dtype=np.float32), bars=2, triggers={0})
    project.put(1, np.full((fpbar, 1), 0.25, dtype=np.float32), bars=1, triggers={1})
    app.rebuild_schedule()
    push.press_button(Btn.PLAY)
    pump(app)
    assert engine.is_playing
    out = engine.process_offline(fpbar * 2)
    assert out[10, 0] == pytest.approx(0.25)
    assert out[fpbar + 10, 0] == pytest.approx(0.5)  # the two overlap in bar 1

    push.press_button(Btn.PLAY)
    pump(app)
    assert not engine.is_playing


def test_playhead_is_shown_on_the_sample_page(rig):
    app, push, engine, project = rig
    fpbar = int(engine.transport.frames_per_bar)
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
    app, push, engine, _ = rig
    assert engine.loop is True
    push.press_button(Btn.REPEAT)
    pump(app)
    assert engine.loop is False


def test_shift_pad_previews_a_sample_without_leaving_the_library(rig):
    app, push, engine, project = rig
    project.put(0, np.full((500, 1), 0.5, dtype=np.float32), bars=1)
    pump(app)
    push.hold_button(Btn.SHIFT, True)
    push.press_pad(0)
    pump(app)
    assert app.mode.name == "library"
    out = engine.process_offline(100)
    assert out[0, 0] == pytest.approx(0.5)


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
    app, push, _, project = rig
    project.put(0, np.zeros((10, 1), dtype=np.float32), bars=1, triggers={0})
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
    wav = tmp_path / "song" / "samples" / "slot_00.wav"
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
