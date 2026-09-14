"""v1.3 — a whole song: banks, pages, the song overview, scenes, the browser.

Banks and pages widened the model from 64 slots over 64 bars to 256 over 256,
so a good half of this file is about the seams: that identity round-trips, that
the grid is a window rather than the whole thing, and that an old project still
opens.
"""

import json
import time

import numpy as np
import pytest

from push2sampler import colors, names
from push2sampler.app import App
from push2sampler.audio import CLICK_SOUNDS, Engine, make_click
from push2sampler.constants import DISPLAY_ROW_BOTTOM, GRID_W, PAD_COUNT, Btn
from push2sampler.modes.song import CELL_BARS, CELL_SLOTS, DENSITY, density_step
from push2sampler.project import (
    BANK_SLOTS,
    FORMAT_VERSION,
    PAGE_BARS,
    SCENE_COUNT,
    SLOT_COUNT,
    SONG_BARS,
    SONG_PAGES,
    Project,
    ProjectSummary,
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
    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


def pump(app):
    for event in app.push.poll_events():
        app.handle(event)
    for event in app.engine.poll_events():
        app.on_engine_event(event)
    app.mode.on_tick()
    app.render()


def take(engine, bars=1, value=0.5):
    return np.full((int(bars * engine.frames_per_bar), 1), value, dtype=np.float32)


# ============================================================ NF-07: banks
def test_the_library_holds_four_banks_of_sixty_four():
    project = Project(samplerate=SR)
    assert len(project.slots) == SLOT_COUNT == 4 * BANK_SLOTS
    assert project.banks == 4


def test_a_pad_means_a_different_slot_in_each_bank(rig):
    app, push, engine, project = rig
    assert app.slot_at(0) == 0
    app.set_bank(2)
    assert app.slot_at(0) == 2 * BANK_SLOTS
    assert app.bank_letter == "C"


def test_pressing_a_pad_in_bank_b_records_into_bank_b(rig):
    app, push, engine, project = rig
    app.set_bank(1)
    push.press_pad(0)
    pump(app)
    assert app.mode.name == "record"
    assert app.mode.slot == BANK_SLOTS


def test_the_library_renders_each_bank_independently(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)           # bank A, pad 0
    project.put(BANK_SLOTS + 1, take(engine), bars=1)  # bank B, pad 1
    app.rebuild_schedule()
    pump(app)
    assert push.pad_leds[0] == colors.GREEN.index
    assert push.pad_leds[1] == colors.WHITE_DIM.index

    app.set_bank(1)
    app._bank_flash_until = 0.0  # skip the change flash
    pump(app)
    assert push.pad_leds[0] == colors.WHITE_DIM.index
    assert push.pad_leds[1] == colors.GREEN.index


def test_a_bank_change_flashes_the_grid(rig):
    app, push, _, _ = rig
    app.set_bank(1)
    assert app.bank_flashing
    pump(app)
    assert set(push.pad_leds) == {colors.BLUE_DIM.index}


def test_page_buttons_change_the_bank(rig):
    app, push, _, _ = rig
    push.press_button(Btn.PAGE_RIGHT)
    pump(app)
    assert app.bank == 1
    push.press_button(Btn.PAGE_LEFT)
    pump(app)
    assert app.bank == 0


def test_the_bank_does_not_run_off_either_end(rig):
    app, _, _, project = rig
    app.set_bank(-5)
    assert app.bank == 0
    app.set_bank(99)
    assert app.bank == project.banks - 1


def test_a_trigger_in_bank_c_is_in_the_schedule(rig):
    _, _, engine, project = rig
    slot = 2 * BANK_SLOTS + 7
    project.put(slot, take(engine), bars=1)
    project[slot].set_trigger(3, True)
    schedule = project.build_schedule()
    assert [entry.slot for entry in schedule[3]] == [slot]


def test_slot_identity_survives_a_save(rig, tmp_path):
    _, _, engine, project = rig
    slot = 3 * BANK_SLOTS + 12  # bank D
    project.put(slot, take(engine), bars=1)
    project[slot].set_trigger(200, True)
    project.save(tmp_path / "banked")
    loaded = Project.load(tmp_path / "banked", samplerate=SR)
    assert loaded[slot] is not None
    assert loaded[slot].slot == slot
    assert loaded[slot].triggers == {200}


def test_first_empty_and_next_empty_cross_bank_boundaries(rig):
    _, _, engine, project = rig
    for slot in range(BANK_SLOTS):
        project.put(slot, take(engine), bars=1)
    assert project.first_empty() == BANK_SLOTS
    assert project.next_empty(BANK_SLOTS - 1) == BANK_SLOTS


def test_the_mixer_strips_follow_the_bank(rig):
    app, push, engine, project = rig
    app.set_bank(1)
    push.press_button(Btn.MIX)
    pump(app)
    assert list(app.mode.slots)[0] == BANK_SLOTS


# ============================================================ NF-11: pages
def test_a_song_is_four_pages_of_sixty_four_bars():
    project = Project(samplerate=SR)
    assert project.pages == SONG_PAGES
    assert project.song_bars == SONG_BARS == SONG_PAGES * PAGE_BARS


def test_a_pad_means_a_different_bar_on_each_page(rig):
    app, _, _, _ = rig
    assert app.bar_at(0) == 0
    app.set_page(3)
    assert app.bar_at(0) == 3 * PAGE_BARS
    assert app.page_letter == "D"


def test_shift_page_changes_the_song_page(rig):
    app, push, _, _ = rig
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.PAGE_RIGHT)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert app.page == 1
    assert app.bank == 0  # ...and not the bank


def test_toggling_on_page_b_writes_an_absolute_bar(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.goto_sample(0)
    app.set_page(1)
    push.press_pad(0)
    pump(app)
    assert project[0].triggers == {PAGE_BARS}


def test_a_sample_triggered_at_bar_two_hundred_plays(rig):
    _, _, engine, project = rig
    project.put(0, take(engine, bars=1, value=0.5), bars=1)
    project[0].set_trigger(200, True)
    engine.set_schedule(project.build_schedule())
    engine.loop = False
    engine.play(200)
    out = engine.process_offline(256, np.zeros((256, 1), dtype=np.float32))
    assert float(np.max(np.abs(out))) > 0.4


def test_the_loop_range_honours_the_page(rig):
    app, _, engine, _ = rig
    app.set_page(2)
    assert engine.loop_range == (2 * PAGE_BARS, 3 * PAGE_BARS)


def test_the_playhead_wraps_at_the_loop_range_not_the_song_end(rig):
    app, _, engine, project = rig
    app.set_page(1)  # loop bars 65-128
    engine.play(engine.loop_range[0])
    fpbar = engine.frames_per_bar
    # Run a whole page plus a bit, and we should be just past its start again.
    frames = int(PAGE_BARS * fpbar + fpbar // 2)
    engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert PAGE_BARS <= engine.current_bar < PAGE_BARS + 2


def test_looping_the_whole_song_covers_every_page(rig):
    app, _, engine, project = rig
    app.loop_scope = "song"
    app.apply_loop_scope()
    assert engine.loop_range == (0, project.song_bars)
    assert engine.loop is True


def test_with_the_loop_off_playback_stops_at_the_end(rig):
    app, _, engine, _ = rig
    app.loop_scope = "off"
    app.apply_loop_scope()
    assert engine.loop is False
    engine.play(engine.transport.song_bars - 1)
    frames = int(2 * engine.frames_per_bar)
    engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert not engine.is_playing


def test_play_starts_where_the_loop_starts(rig):
    app, push, engine, _ = rig
    app.set_page(2)
    push.press_button(Btn.PLAY)
    pump(app)
    assert engine.current_bar == 2 * PAGE_BARS


def test_a_loop_range_can_never_be_empty_or_backwards(rig):
    _, _, engine, _ = rig
    engine.loop_range = (10, 10)
    start, end = engine.loop_frames
    assert end > start
    engine.loop_range = (50, 3)
    start, end = engine.loop_frames
    assert end > start


def test_the_transport_line_names_the_loop_scope(rig):
    app, _, _, _ = rig
    assert any("loop page A" in line for line in app.status_lines())
    app.loop_scope = "song"
    assert any("loop song" in line for line in app.status_lines())


# --------------------------------------------------- loading older projects
def write_legacy(directory, payload):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "samples").mkdir(exist_ok=True)
    (directory / "project.json").write_text(json.dumps(payload))


def test_a_one_page_project_loads_as_one_page(tmp_path, rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project.save(tmp_path / "old")
    # Rewrite it as a pre-v6 manifest: song_bars, no pages.
    payload = json.loads((tmp_path / "old" / "project.json").read_text())
    payload["version"] = 5
    payload.pop("pages")
    payload["song_bars"] = 64
    (tmp_path / "old" / "project.json").write_text(json.dumps(payload))

    loaded = Project.load(tmp_path / "old", samplerate=SR)
    assert loaded.pages == 1
    assert loaded.song_bars == PAGE_BARS
    assert loaded[0] is not None  # and its take came with it


def test_a_trigger_past_the_last_page_is_dropped_with_a_warning(tmp_path, rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project.save(tmp_path / "old")
    payload = json.loads((tmp_path / "old" / "project.json").read_text())
    payload["pages"] = 1  # one page, so only bars 0-63 exist
    payload["slots"][0]["triggers"] = [0, 5, 200]
    (tmp_path / "old" / "project.json").write_text(json.dumps(payload))

    loaded = Project.load(tmp_path / "old", samplerate=SR)
    assert loaded[0].triggers == {0, 5}
    assert loaded.warning and "dropped 1 trigger" in loaded.warning


def test_a_slot_outside_the_library_is_dropped(tmp_path, rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project.save(tmp_path / "old")
    payload = json.loads((tmp_path / "old" / "project.json").read_text())
    payload["slots"][0]["slot"] = 9999
    (tmp_path / "old" / "project.json").write_text(json.dumps(payload))

    loaded = Project.load(tmp_path / "old", samplerate=SR)
    assert loaded.filled() == []
    assert loaded.warning and "outside" in loaded.warning


def test_the_format_version_tracks_what_a_slot_carries():
    """9 nudge, 10 probability, 11 takes, 12 tempo stretch, 13 variations.

    Every one is additive and every older format still loads -- see the loader
    tests.  The number is asserted here so bumping it is a deliberate act.
    """
    assert FORMAT_VERSION == 13


# ====================================================== NF-01: song overview
def open_song(rig):
    app, push, engine, project = rig
    push.press_button(Btn.CLIP)
    pump(app)
    return app, push, engine, project


def test_clip_opens_and_closes_the_song_page(rig):
    app, push, _, _ = open_song(rig)
    assert app.mode.name == "song"
    push.press_button(Btn.CLIP)
    pump(app)
    assert app.mode.name == "library"


@pytest.mark.parametrize("count,step", [(0, 0), (1, 1), (2, 2), (3, 2), (5, 3), (9, 4)])
def test_the_density_ramp_has_a_rung_per_band(count, step):
    assert density_step(count) == step


def test_a_cell_is_coloured_by_how_many_triggers_it_holds(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    for bar in range(3):  # three triggers in the first cell
        project[0].set_trigger(bar, True)
    app.rebuild_schedule()
    open_song(rig)
    assert push.pad_leds[0] == DENSITY[density_step(3)]
    assert push.pad_leds[1] == DENSITY[0]  # nothing in the next cell


def test_every_cell_maps_to_its_own_bars_and_slots(rig):
    app, push, _, _ = open_song(rig)
    seen = set()
    for row in range(8):
        for column in range(8):
            bar, slot = app.mode.cell_origin(column, row)
            assert bar == column * CELL_BARS
            assert slot == row * CELL_SLOTS
            seen.add((bar, slot))
    assert len(seen) == PAD_COUNT  # all 64 cells distinct


def test_zooming_in_maps_each_pad_to_one_bar_of_one_slot(rig):
    app, push, _, _ = open_song(rig)
    push.press_pad(2 * GRID_W + 3)  # column 3, row 2
    pump(app)
    assert app.mode.zoomed
    assert app.mode.zoom_target(0) == (3 * CELL_BARS, 2 * CELL_SLOTS)
    assert app.mode.zoom_target(1) == (3 * CELL_BARS + 1, 2 * CELL_SLOTS)
    assert app.mode.zoom_target(GRID_W) == (3 * CELL_BARS, 2 * CELL_SLOTS + 1)


def test_toggling_in_the_zoom_edits_the_same_triggers(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.rebuild_schedule()
    open_song(rig)
    push.press_pad(0)  # zoom into bars 1-8, slots 1-8
    pump(app)
    push.press_pad(5)  # bar 6 of slot 1
    pump(app)
    assert project[0].triggers == {5}
    push.press_pad(5)
    pump(app)
    assert project[0].triggers == set()


def test_zooming_into_an_empty_slot_says_so(rig):
    app, push, _, _ = open_song(rig)
    push.press_pad(0)
    pump(app)
    push.press_pad(GRID_W)  # row 1 = slot 2, which is empty
    pump(app)
    assert "empty" in app.message


def test_clip_steps_back_out_of_the_zoom_before_leaving(rig):
    app, push, _, _ = open_song(rig)
    push.press_pad(0)
    pump(app)
    assert app.mode.zoomed
    push.press_button(Btn.CLIP)
    pump(app)
    assert app.mode.name == "song" and not app.mode.zoomed


def test_the_playhead_column_is_brightened(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(16, True)  # one trigger, in column 2
    app.rebuild_schedule()
    open_song(rig)
    assert push.pad_leds[2] == DENSITY[1]
    engine.play(16)
    pump(app)
    # Same cell, one rung brighter, because the playhead is in that column.
    assert push.pad_leds[2] == DENSITY[2]


def test_the_overview_only_counts_the_visible_page_and_bank(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    project.put(BANK_SLOTS, take(engine), bars=1)
    project[BANK_SLOTS].set_trigger(0, True)
    app.rebuild_schedule()
    open_song(rig)
    counts = app.mode._cell_counts()
    assert counts[0][0] == 1  # only bank A's trigger
    app.set_bank(1)
    assert app.mode._cell_counts()[0][0] == 1  # and only bank B's


def test_delete_clears_a_whole_cell(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    for bar in range(CELL_BARS):
        project[0].set_trigger(bar, True)
    app.rebuild_schedule()
    open_song(rig)
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.DELETE)
    pump(app)
    assert project[0].triggers == set()


def test_page_buttons_move_the_zoom(rig):
    app, push, _, _ = open_song(rig)
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.PAGE_RIGHT)
    pump(app)
    assert app.mode.cell == (1, 0)
    assert app.bank == 0  # the bank did not move with it


# ============================================================ NH-06: scenes
def scene_rig(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    project.put(1, take(engine), bars=1)
    project[1].set_trigger(4, True)
    app.rebuild_schedule()
    return app, push, engine, project


def test_a_project_starts_with_eight_empty_scenes():
    project = Project(samplerate=SR)
    assert len(project.scenes) == SCENE_COUNT
    assert not any(project.scene_filled(i) for i in range(SCENE_COUNT))


def test_store_change_recall_restores_exactly(rig):
    app, push, engine, project = scene_rig(rig)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert project.scene_filled(0)

    project[0].set_trigger(9, True)
    project[1].enabled = False
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    assert project[0].triggers == {0}
    assert project[1].enabled is True


def test_recalling_an_empty_scene_says_so(rig):
    app, push, _, _ = scene_rig(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[3])
    pump(app)
    assert "is empty" in app.message


def test_a_recall_is_undoable(rig):
    app, push, engine, project = scene_rig(rig)
    app.project.store_scene(0)
    project[0].set_trigger(9, True)
    from push2sampler.history import RecallScene

    app.do(RecallScene(0))
    assert project[0].triggers == {0}
    app.undo()
    assert project[0].triggers == {0, 9}


def test_a_scene_does_not_touch_the_audio_or_the_gain(rig):
    app, _, engine, project = scene_rig(rig)
    project.store_scene(0)
    project[0].gain = 0.25
    audio = project[0].audio
    project.recall_scene(0)
    assert project[0].gain == 0.25  # a mix decision, not an arrangement one
    assert project[0].audio is audio


def test_scenes_survive_a_save(rig, tmp_path):
    _, _, engine, project = scene_rig(rig)
    project.store_scene(2)
    project.save(tmp_path / "scened")
    loaded = Project.load(tmp_path / "scened", samplerate=SR)
    assert loaded.scene_filled(2)
    loaded[0].set_trigger(30, True)
    loaded.recall_scene(2)
    assert loaded[0].triggers == {0}


def test_a_malformed_scene_is_dropped_not_fatal(tmp_path, rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project.save(tmp_path / "bad")
    payload = json.loads((tmp_path / "bad" / "project.json").read_text())
    payload["scenes"] = ["nonsense", {"slots": "not a dict"}, None]
    (tmp_path / "bad" / "project.json").write_text(json.dumps(payload))
    loaded = Project.load(tmp_path / "bad", samplerate=SR)
    assert not any(loaded.scene_filled(i) for i in range(SCENE_COUNT))
    assert loaded[0] is not None


def test_a_slot_recorded_after_the_snapshot_is_left_alone(rig):
    app, _, engine, project = scene_rig(rig)
    project.store_scene(0)
    project.put(9, take(engine), bars=1)
    project[9].set_trigger(2, True)
    project.recall_scene(0)
    # A scene is a variation, not a rollback of the whole library.
    assert project[9] is not None
    assert project[9].triggers == {2}


def test_the_scene_buttons_light_when_filled(rig):
    app, push, _, project = scene_rig(rig)
    pump(app)
    assert push.button_leds[DISPLAY_ROW_BOTTOM[0]] == 12  # BTN_DIM
    project.store_scene(0)
    pump(app)
    assert push.button_leds[DISPLAY_ROW_BOTTOM[0]] == 60  # BTN_ON


# ========================================= NH-03: metronome and count-in
def count_clicks(audio, samplerate, min_gap_ms=60.0):
    """How many separate clicks are in a buffer.

    A click is a decaying tone, so its waveform crosses any amplitude threshold
    dozens of times -- counting threshold crossings counts oscillations, not
    clicks.  Bursts separated by a real gap of silence are what to count.
    """
    loud = np.flatnonzero(np.abs(np.asarray(audio)[:, 0]) > 0.05)
    if loud.size == 0:
        return 0
    gap = int(samplerate * min_gap_ms / 1000.0)
    return 1 + int(np.sum(np.diff(loud) > gap))


@pytest.mark.parametrize("beats", [0, 1, 2, 4, 8])
def test_each_count_in_length_clicks_that_many_times(rig, beats):
    app, _, engine, _ = rig
    app.settings.set("count_in_beats", beats)
    engine.metronome = False  # so only the count-in can make a click
    engine.arm_record(1, beats)
    frames = int(max(1, beats) * engine.frames_per_beat)
    out = engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert count_clicks(out, SR) == beats


def test_a_pre_roll_plays_the_song_before_the_count_in(rig):
    app, _, engine, project = rig
    engine.arm_record(1, count_in_beats=4, pre_roll_bars=2)
    # Two bars of pre-roll plus four beats of count-in, all before frame 0.
    expected = -(2 * engine.frames_per_bar + 4 * engine.frames_per_beat)
    assert engine.position_frames == pytest.approx(expected)
    assert engine.in_pre_roll


def test_the_click_waits_until_the_count_in_during_a_pre_roll(rig):
    _, _, engine, _ = rig
    engine.metronome = False
    engine.arm_record(1, count_in_beats=2, pre_roll_bars=1)
    # Render the pre-roll only; nothing should click yet.
    frames = int(engine.frames_per_bar - 2 * engine.frames_per_beat)
    out = engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert float(np.max(np.abs(out))) < 0.01


@pytest.mark.parametrize("sound", CLICK_SOUNDS)
def test_every_click_sound_makes_a_sound(sound):
    click = make_click(SR, 1000.0, 2, sound=sound)
    assert click.shape[1] == 2
    assert float(np.max(np.abs(click))) > 0.05


def test_the_click_level_is_a_setting(rig):
    app, _, engine, _ = rig
    app.settings.set("click_gain", 0.25)
    app.apply_settings("click_gain")
    quiet = float(np.max(np.abs(engine._click)))
    app.settings.set("click_gain", 2.0)
    app.apply_settings("click_gain")
    assert float(np.max(np.abs(engine._click))) > quiet * 3


def test_click_only_while_recording(rig):
    app, _, engine, _ = rig
    app.settings.set("click_when_recording", True)
    app.apply_settings("click_when_recording")
    engine.metronome = True
    engine.play(0)
    frames = int(2 * engine.frames_per_beat)
    out = engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert float(np.max(np.abs(out))) < 0.01  # playing, not recording: silent


def test_a_separate_click_output_keeps_the_main_mix_clean():
    engine = Engine(samplerate=SR, blocksize=64, in_channels=1, out_channels=4,
                    backend="offline", bpm=120.0, song_bars=SONG_BARS)
    engine.set_click(channel=2)
    engine.metronome = True
    engine.play(0)
    frames = int(2 * engine.frames_per_beat)
    out = engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert float(np.max(np.abs(out[:, :2]))) < 0.01   # main pair is click-free
    assert float(np.max(np.abs(out[:, 2:]))) > 0.05   # the cue pair has it


def test_a_click_channel_the_device_lacks_falls_back_to_the_mix(rig):
    app, _, engine, _ = rig
    app.settings.set("click_channel", 9)  # this engine only has two outputs
    app.apply_settings("click_channel")
    assert engine.click_channel is None


# ============================================ CC-08: big transport readout
def test_the_readout_names_bar_beat_and_tempo(rig):
    app, _, engine, _ = rig
    engine.play(16)
    readout = app.transport_readout()
    assert "BAR 17" in readout
    assert "120 BPM" in readout


def test_the_readout_counts_beats_from_one(rig):
    app, _, engine, _ = rig
    engine.play(0)
    assert " · 1 · " in app.transport_readout()
    frames = int(engine.frames_per_beat * 1.5)
    engine.process_offline(frames, np.zeros((frames, 1), dtype=np.float32))
    assert " · 2 · " in app.transport_readout()


def test_the_readout_names_the_page_when_there_is_more_than_one(rig):
    app, _, engine, _ = rig
    app.set_page(2)
    engine.play(2 * PAGE_BARS)
    assert "BAR 129C" in app.transport_readout()


def test_status_lines_still_work_with_no_display(rig):
    app, _, _, _ = rig
    assert app.display is None
    assert app.status_lines()  # and nothing raises
    assert app.transport_readout()


def test_the_display_reserves_room_for_the_big_line():
    from push2sampler.display import BIG_LINE_HEIGHT, HEIGHT

    assert 0 < BIG_LINE_HEIGHT < HEIGHT


# ==================================================== CC-17 / CC-18: naming
def tagged(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.rebuild_schedule()
    app.goto_sample(0)
    push.press_button(Btn.SELECT)
    pump(app)
    return app, push, engine, project


def test_select_opens_the_namer(rig):
    app, push, _, _ = tagged(rig)
    assert app.mode.name == "tag"


def test_the_word_list_is_eight_categories_of_eight():
    assert len(names.CATEGORIES) == 8
    for _, words in names.CATEGORIES:
        assert len(words) == 8


def test_picking_a_word_names_the_slot_undoably(rig):
    app, push, _, project = tagged(rig)
    push.press_pad(0)  # first word of the first category
    pump(app)
    assert project[0].name == names.words(0)[0]
    app.undo()
    assert project[0].name == "S01"


def test_a_second_kick_names_itself(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].name = "kick"
    project.put(1, take(engine), bars=1)
    app.goto_sample(1)
    push.press_button(Btn.SELECT)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert project[1].name == "kick 2"


def test_a_name_persists(rig, tmp_path):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].name = "snare"
    project.save(tmp_path / "named")
    assert Project.load(tmp_path / "named", samplerate=SR)[0].name == "snare"


def test_the_category_buttons_move_the_word_rows(rig):
    app, push, _, _ = tagged(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(app)
    assert app.mode.category == 2
    assert names.word_at(2, 0) == names.CATEGORIES[2][1][0]


def test_picking_a_colour_tags_the_slot(rig):
    app, push, _, project = tagged(rig)
    push.press_pad(names.ROWS * GRID_W + 3)  # bottom row, fourth swatch
    pump(app)
    assert project[0].color == 3
    app.undo()
    assert project[0].color is None


def test_pressing_the_same_colour_clears_it(rig):
    app, push, _, project = tagged(rig)
    pad = names.ROWS * GRID_W + 5
    push.press_pad(pad)
    pump(app)
    assert project[0].color == 5
    push.press_pad(pad)
    pump(app)
    assert project[0].color is None


def test_the_library_renders_a_slot_in_its_own_colour(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].color = 4
    app.rebuild_schedule()
    app.goto_library()
    pump(app)
    assert push.pad_leds[0] == colors.USER_COLORS[4].index


def test_muted_and_sounding_still_win_over_the_colour(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].color = 4
    project[0].enabled = False
    app.goto_library()
    pump(app)
    assert push.pad_leds[0] == colors.GREEN_DIM.index

    project[0].enabled = True
    project[0].set_trigger(0, True)
    app.rebuild_schedule()
    engine.play(0)
    engine.process_offline(64, np.zeros((64, 1), dtype=np.float32))
    pump(app)
    assert push.pad_leds[0] == colors.AMBER.index


def test_an_unset_colour_is_green(rig):
    assert colors.slot_color(None) == colors.GREEN.index
    assert colors.slot_color(0) == colors.GREEN.index
    assert colors.slot_color(99) == colors.GREEN.index


def test_a_colour_persists(rig, tmp_path):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].color = 6
    project.save(tmp_path / "coloured")
    assert Project.load(tmp_path / "coloured", samplerate=SR)[0].color == 6


def test_a_nonsense_colour_in_a_file_is_ignored(tmp_path, rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project.save(tmp_path / "bad")
    payload = json.loads((tmp_path / "bad" / "project.json").read_text())
    payload["slots"][0]["color"] = "blue"
    (tmp_path / "bad" / "project.json").write_text(json.dumps(payload))
    assert Project.load(tmp_path / "bad", samplerate=SR)[0].color is None


def test_every_palette_index_is_unique_and_has_a_glyph():
    indices = [c.index for c in colors.PALETTE]
    assert len(indices) == len(set(indices))
    assert all(c.index in colors.SIM_GLYPHS for c in colors.PALETTE)


# ======================================================== CC-13: dim library
def test_blank_slots_are_dim_by_default(rig):
    app, push, _, _ = rig
    pump(app)
    assert push.pad_leds[0] == colors.WHITE_DIM.index


def test_the_playhead_keeps_the_brightest_white(rig):
    """The dimmer exists so the brightest white means something."""
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.goto_sample(0)
    engine.play(3)
    pump(app)
    assert push.pad_leds[3] == colors.WHITE.index


# ====================================================== NF-06: the browser
def make_project(root, name, bpm=120.0, slots=1):
    project = Project(samplerate=SR, bpm=bpm)
    for slot in range(slots):
        project.put(slot, np.full((int(project.frames_per_bar), 1), 0.5,
                                  dtype=np.float32), bars=1)
    project.save(root / name)
    return root / name


def test_scan_reads_metadata_without_loading_audio(tmp_path):
    make_project(tmp_path, "one", bpm=90.0, slots=2)
    make_project(tmp_path, "two", bpm=140.0, slots=0)
    (tmp_path / "not-a-project").mkdir()

    found = Project.scan(tmp_path)
    assert [s.name for s in found] == ["one", "two"]
    assert found[0].bpm == 90.0 and found[0].slots == 2
    assert found[0].has_audio and not found[1].has_audio


def test_scan_of_a_missing_root_is_empty(tmp_path):
    assert Project.scan(tmp_path / "nope") == []


def test_a_project_with_a_broken_manifest_is_still_listed(tmp_path):
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "project.json").write_text("{not json")
    summary = ProjectSummary.read(directory)
    assert summary is not None
    assert summary.slots == 0  # honestly empty rather than a crash


def test_the_browser_lists_projects_on_the_pads(rig, tmp_path):
    app, push, _, _ = rig
    root = app.project_root
    make_project(root, "alpha")
    make_project(root, "beta", slots=0)
    push.press_button(Btn.BROWSE)
    pump(app)
    assert app.mode.name == "browser"
    assert len(app.mode.entries) >= 2


def test_opening_a_project_saves_the_one_you_were_in(rig, tmp_path):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.save_soon()
    other = make_project(app.project_root, "other", bpm=101.0)

    assert app.open_project(other)
    assert app.project_dir == other
    assert app.project.bpm == 101.0
    assert app.mode.name == "library"
    # The outgoing project was written before the swap.
    assert (tmp_path / "song" / "project.json").exists()


def test_opening_a_project_resets_the_view_and_the_journal(rig):
    app, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.bank, app.page = 2, 3
    other = make_project(app.project_root, "next")
    app.open_project(other)
    assert (app.bank, app.page) == (0, 0)
    assert not app.history.can_undo


def test_opening_a_project_does_not_restart_the_stream(rig):
    app, _, engine, _ = rig
    before = engine.blocksize
    other = make_project(app.project_root, "quiet")
    app.open_project(other)
    assert engine.blocksize == before
    assert not engine.is_playing  # stopped, but the stream is untouched


def test_opening_something_that_is_not_a_project_is_refused(rig, tmp_path):
    app, _, _, _ = rig
    empty = tmp_path / "empty"
    empty.mkdir()
    assert app.open_project(empty) is False
    assert "not a project" in app.message


def test_a_new_project_is_created_and_opened(rig):
    app, _, _, _ = rig
    path = app.new_project_path()
    assert app.open_project(path, create=True)
    assert (path / "project.json").exists()
    assert app.project.filled() == []


def test_duplicating_a_project_makes_an_independent_copy(rig):
    app, _, engine, project = rig
    source = make_project(app.project_root, "source", bpm=99.0)
    copy = app.duplicate_project(source)
    assert copy is not None and copy != source

    # Change the copy; the original must not move.
    app.open_project(copy)
    app.project.bpm = 150.0
    app.save_now()
    assert Project.load(source, samplerate=SR).bpm == 99.0


def test_deleting_a_project_needs_the_button_held(rig, monkeypatch):
    app, push, _, _ = rig
    target = make_project(app.project_root, "doomed")
    make_project(app.project_root, "keeper")
    push.press_button(Btn.BROWSE)
    pump(app)
    app.mode.selected = [e.name for e in app.mode.entries].index("doomed")

    clock = [1000.0]
    monkeypatch.setattr("push2sampler.modes.browser.time.monotonic", lambda: clock[0])
    push.hold_button(DISPLAY_ROW_BOTTOM[4], True)
    pump(app)
    assert target.exists()  # a tap is not enough
    clock[0] += 2.0
    pump(app)
    assert not target.exists()


def test_releasing_the_delete_button_cancels_it(rig, monkeypatch):
    app, push, _, _ = rig
    target = make_project(app.project_root, "spared")
    push.press_button(Btn.BROWSE)
    pump(app)
    app.mode.selected = [e.name for e in app.mode.entries].index("spared")

    clock = [1000.0]
    monkeypatch.setattr("push2sampler.modes.browser.time.monotonic", lambda: clock[0])
    push.hold_button(DISPLAY_ROW_BOTTOM[4], True)
    pump(app)
    push.hold_button(DISPLAY_ROW_BOTTOM[4], False)
    pump(app)
    clock[0] += 2.0
    pump(app)
    assert target.exists()


def test_the_open_project_cannot_be_deleted(rig):
    app, _, _, _ = rig
    app.project.save(app.project_dir)
    assert app.delete_project(app.project_dir) is False
    assert "cannot delete" in app.message


def test_a_project_summary_knows_when_it_changed(tmp_path):
    path = make_project(tmp_path, "dated")
    summary = ProjectSummary.read(path)
    assert summary.modified <= time.time() + 1
