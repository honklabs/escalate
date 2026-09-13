"""NF-12: master playback mode, and the engine signal it needed.

The interesting part is the difference between *starting* and *sounding*. A
four-bar pad is sounding for four bars; a view that lit its pad for all of them
would say nothing about the music. So the engine publishes the attack
separately, and these tests are mostly about that distinction holding.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.app import App
from push2sampler.audio import Engine, ScheduledSample
from push2sampler.constants import PAD_COUNT, Btn
from push2sampler.modes.master import FLASH_PEAK, FLASH_S, MasterMode
from push2sampler.project import Project, Sample
from push2sampler.push2 import SimPush
from push2sampler.settings import Settings

SR = 8000
BPM = 120.0
FPBAR = int(SR * 2)          # one bar at 120 BPM in 4/4


def engine(song_bars=64):
    return Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                  backend="offline", bpm=BPM, song_bars=song_bars)


def tone(frames, value=0.4):
    return np.full((frames, 1), value, dtype=np.float32)


def schedule(eng, by_bar, song_bars=64):
    rows = [[] for _ in range(song_bars)]
    for bar, entries in by_bar.items():
        rows[bar] = list(entries)
    eng.set_schedule(rows)


def render(eng, frames, chunk=256):
    done = 0
    while done < frames:
        n = min(chunk, frames - done)
        eng.process_offline(n)
        done += n


# ================================================ the engine's "fired" signal
def test_fired_reports_the_attack_not_the_duration():
    """The whole reason this exists: a long sample fires once."""
    eng = engine()
    schedule(eng, {0: [ScheduledSample(3, tone(FPBAR * 4))]})
    eng.play()

    eng.process_offline(256)                 # the block containing bar 1
    assert eng.fired == (3,)
    assert 3 in eng.sounding

    eng.process_offline(256)                 # the very next block
    assert eng.fired == ()                   # attack is over
    assert 3 in eng.sounding                 # but it is still playing


def test_fired_is_empty_in_a_block_with_no_bar_line():
    eng = engine()
    schedule(eng, {0: [ScheduledSample(0, tone(FPBAR))]})
    eng.play()
    render(eng, 256)
    eng.process_offline(256)
    assert eng.fired == ()


def test_fired_carries_every_slot_that_started_on_the_same_bar():
    eng = engine()
    schedule(eng, {0: [ScheduledSample(1, tone(FPBAR)),
                       ScheduledSample(5, tone(FPBAR)),
                       ScheduledSample(9, tone(FPBAR))]})
    eng.play()
    eng.process_offline(256)
    assert eng.fired == (1, 5, 9)


def test_fired_survives_a_bar_line_mid_block():
    """Published once per block, accumulated across its segments -- otherwise a
    caller polling at 30 Hz misses an attack in an early segment."""
    eng = engine()
    schedule(eng, {0: [ScheduledSample(0, tone(FPBAR))],
                   1: [ScheduledSample(1, tone(FPBAR))]})
    eng.play()
    # One block spanning the bar-1 line, so both bar lines land inside it and
    # both attacks have to survive to the end of the block.
    eng.process_offline(FPBAR + 64)
    assert eng.fired == (0, 1)
    render(eng, 64)
    assert eng.fired == ()


def test_fired_includes_a_sample_played_by_hand():
    """Every attack goes through _add_voice, so perform mode counts too."""
    eng = engine()
    eng.preview(tone(FPBAR), 1.0, slot=7)
    eng.process_offline(256)
    assert eng.fired == (7,)


def test_fired_ignores_the_metronome():
    eng = engine()
    eng.metronome = True
    eng.play()
    eng.process_offline(256)
    assert eng.fired == ()                   # clicks are slot -1


def test_fired_does_not_grow_without_bound():
    eng = engine()
    schedule(eng, {bar: [ScheduledSample(bar, tone(FPBAR))] for bar in range(8)})
    eng.play()
    for _ in range(8):
        render(eng, FPBAR)
    assert len(eng.fired) <= 8


# ============================================================== the mode
@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    eng = engine(project.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    app = App(push, eng, project, project_dir=tmp_path / "song", settings=settings)
    return app, push, eng, project


def pump(app):
    for event in app.push.poll_events():
        app.handle(event)
    app.mode.on_tick()
    app.render()


def filled(project, slot, bars=1, color=None):
    project.install(slot, Sample(slot=slot, bars=bars, audio=tone(FPBAR * bars),
                                 color=color))
    return project[slot]


def open_master(rig):
    app, push, eng, project = rig
    app.shift = True
    push.press_button(Btn.SESSION)
    pump(app)
    app.shift = False
    return app


def test_shift_session_opens_master_playback(rig):
    app = open_master(rig)
    assert app.mode.name == "master"


def test_session_alone_still_goes_back(rig):
    app, push, eng, project = rig
    filled(project, 0)
    app.goto_sample(0)
    pump(app)
    push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "library"


def test_shift_session_again_returns_to_the_library(rig):
    app = open_master(rig)
    app.shift = True
    app.push.press_button(Btn.SESSION)
    pump(app)
    app.shift = False
    assert app.mode.name == "library"


def test_master_is_not_an_overlay(rig):
    """It replaces the page rather than layering, so Session means "leave"
    rather than "back to what I was editing"."""
    app, push, eng, project = rig
    filled(project, 0)
    app.goto_sample(0)
    pump(app)
    open_master(rig)
    assert app.depth == 1
    push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "library"


def test_a_filled_slot_rests_in_its_own_colour(rig):
    app, push, eng, project = rig
    filled(project, 0, color=3)
    open_master(rig)
    pump(app)
    assert push.pad_leds[0] == colors.slot_color(3)


def test_an_empty_slot_is_dark(rig):
    app, push, eng, project = rig
    filled(project, 0)
    open_master(rig)
    pump(app)
    assert push.pad_leds[1] == colors.OFF.index


def test_a_muted_slot_rests_dim_and_never_flashes(rig):
    app, push, eng, project = rig
    sample = filled(project, 0)
    sample.enabled = False
    app_mode = open_master(rig)
    app_mode.mode._hits[0] = time.monotonic()
    pump(app)
    assert push.pad_leds[0] == colors.GREEN_DIM.index


def test_a_fired_slot_flashes_white_then_mid_then_rests(rig):
    app, push, eng, project = rig
    filled(project, 0)
    mode = open_master(rig).mode
    now = time.monotonic()

    mode._hits[0] = now
    pump(app)
    assert push.pad_leds[0] == colors.WHITE.index

    mode._hits[0] = now - FLASH_S * FLASH_PEAK - 0.001
    pump(app)
    assert push.pad_leds[0] == colors.WHITE_MID.index

    mode._hits[0] = now - FLASH_S - 0.001
    pump(app)
    assert push.pad_leds[0] == colors.slot_color(None)


def test_the_flash_is_driven_by_the_engines_fired_set(rig):
    app, push, eng, project = rig
    sample = filled(project, 0)
    sample.set_trigger(0, True)
    project.install(0, sample)
    eng.set_schedule(project.build_schedule())
    open_master(rig)
    eng.play()
    eng.process_offline(256)
    assert eng.fired == (0,)
    pump(app)
    assert push.pad_leds[0] == colors.WHITE.index


def test_a_long_sample_flashes_once_rather_than_staying_lit(rig):
    """The bug this mode would have had if it read `sounding`."""
    app, push, eng, project = rig
    sample = filled(project, 0, bars=4)
    sample.set_trigger(0, True)
    eng.set_schedule(project.build_schedule())
    mode = open_master(rig).mode
    eng.play()
    eng.process_offline(256)
    pump(app)
    assert push.pad_leds[0] == colors.WHITE.index

    # A whole bar later it is still sounding, but no longer flashing.
    for _ in range(int(FPBAR / 256)):
        eng.process_offline(256)
    mode._hits.clear()
    pump(app)
    assert 0 in eng.sounding
    assert push.pad_leds[0] == colors.slot_color(None)


def test_stale_flashes_are_dropped_so_the_dict_stays_small(rig):
    app, push, eng, project = rig
    mode = open_master(rig).mode
    old = time.monotonic() - FLASH_S - 1.0
    mode._hits = {slot: old for slot in range(64)}
    mode.on_tick()
    assert mode._hits == {}


def test_pressing_a_filled_pad_auditions_it(rig):
    app, push, eng, project = rig
    filled(project, 2)
    open_master(rig)
    push.press_pad(2)
    pump(app)
    # preview posts a command; it starts when the callback next runs.
    eng.process_offline(256)
    assert eng.fired == (2,)
    assert 2 in eng.sounding
    assert "auditioning" in app.message


def test_pressing_an_empty_pad_does_nothing(rig):
    app, push, eng, project = rig
    open_master(rig)
    before = app.message
    push.press_pad(40)
    pump(app)
    assert app.message == before
    assert app.mode.name == "master"


def test_nothing_destructive_can_be_armed_from_here(rig):
    """The one page where you are listening, not deciding."""
    app, push, eng, project = rig
    filled(project, 0)
    open_master(rig)
    for cc in (Btn.DELETE, Btn.MUTE, Btn.DUPLICATE):
        push.press_button(cc)
        pump(app)
        assert not app.delete_armed
        assert not app.mute_armed
        assert not app.duplicate_armed
        assert app.mode.name == "master"
    assert project[0] is not None


def test_the_transport_still_works(rig):
    app, push, eng, project = rig
    filled(project, 0)
    open_master(rig)
    push.press_button(Btn.PLAY)
    pump(app)
    assert eng.is_playing
    push.press_button(Btn.STOP)
    pump(app)
    assert not eng.is_playing


def test_the_grid_follows_the_bank(rig):
    app, push, eng, project = rig
    filled(project, 64, color=5)        # first slot of bank B
    open_master(rig)
    pump(app)
    assert push.pad_leds[0] == colors.OFF.index
    push.press_button(Btn.PAGE_RIGHT)
    pump(app)
    app._bank_flash_until = 0.0          # skip the bank-change flash
    pump(app)
    assert app.bank == 1
    assert push.pad_leds[0] == colors.slot_color(5)


def test_the_display_counts_what_fired_this_bar(rig):
    app, push, eng, project = rig
    for slot in (0, 1, 2):
        sample = filled(project, slot)
        sample.set_trigger(0, True)
    eng.set_schedule(project.build_schedule())
    open_master(rig)
    eng.play()
    eng.process_offline(256)
    pump(app)
    lines = " ".join(app.mode.status_lines())
    assert "3 fired this bar" in lines


def test_the_bar_count_resets_on_a_new_bar(rig):
    app, push, eng, project = rig
    sample = filled(project, 0)
    sample.set_trigger(0, True)          # bar 1 only
    eng.set_schedule(project.build_schedule())
    mode = open_master(rig).mode
    eng.play()
    eng.process_offline(256)
    pump(app)
    assert len(mode._bar_slots) == 1
    for _ in range(int(FPBAR / 256) + 1):
        eng.process_offline(256)
    pump(app)
    assert mode._bar_slots == set()


def test_the_display_names_the_mode_and_the_bank(rig):
    app, push, eng, project = rig
    open_master(rig)
    lines = app.mode.status_lines()
    assert "MASTER PLAYBACK" in lines[0]
    assert "bank A" in lines[0]
