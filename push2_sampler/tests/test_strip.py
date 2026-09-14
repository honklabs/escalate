"""IN-07: the grid as a clock, the strip as a scrubber.

The plan's three tests are here. What is *not* here, and cannot be, is any
evidence that the touch strip exists: that it speaks pitch bend at all comes
from Ableton's *Push 2 MIDI and Display Interface* document and has never been
seen on a device. `--selftest` has a step for it and has never been completed.

So the decoding is tested against the document's claim, and everything
downstream is written to be inert rather than wrong if the claim is false -- a
strip that sends something else simply never reaches `App._strip`, and nothing
else depends on it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.constants import BEAT_COLUMN, RING, index_to_xy
from push2sampler.push2 import StripEvent, translate_midi

SR = 22050
BPM = 120.0


@dataclass
class Msg:
    type: str
    pitch: int = 0
    note: int = 0
    velocity: int = 0
    control: int = 0


def rig(tmp_path, bpm=BPM, pages=1):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.project import Project
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=SR, bpm=bpm)
    project.pages = pages
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=bpm, song_bars=project.song_bars)
    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


# ==================================================== the plan's tests
def test_the_bottom_of_the_strip_is_bar_one_and_the_top_is_the_last_bar(tmp_path):
    """The plan's test."""
    app, _push, engine, project = rig(tmp_path)
    app.handle(StripEvent(0.0))
    assert engine.current_bar == 0

    app.handle(StripEvent(1.0))
    assert engine.current_bar == project.song_bars - 1


def test_the_strip_is_monotonic_between_the_ends(tmp_path):
    """The plan's test."""
    app, _push, engine, _project = rig(tmp_path)
    bars = []
    for step in range(21):
        app.handle(StripEvent(step / 20.0))
        bars.append(engine.current_bar)
    assert bars == sorted(bars)
    assert bars[0] == 0
    assert bars[-1] > bars[0]


def test_the_count_in_ring_lights_one_pad_per_sixteenth(tmp_path):
    """The plan's test: sixteen pads for a bar of count-in."""
    from push2sampler.modes.record import RecordMode

    app, _push, engine, _project = rig(tmp_path)
    app.set_mode(RecordMode(app, 0, 4))
    engine.arm_record(4, 4, pre_roll_bars=0)

    filled_at = {}
    done = 0
    limit = engine.frames_per_beat * 8
    while engine.rec_state == "count_in" and done < limit:
        engine.process_offline(256)
        done += 256
        elapsed, total = engine.count_in_sixteenths
        if elapsed not in filled_at:
            pads = [colors.OFF.index] * 64
            app.mode.render_pads(pads)
            filled_at[elapsed] = sum(1 for v in pads if v == colors.RED.index)

    # A four-beat count-in is sixteen sixteenths, and each one fills one pad.
    assert max(filled_at) == 15
    assert filled_at == {step: step for step in range(16)}


def test_the_pulse_never_overwrites_a_mode_s_own_pad(tmp_path):
    """The plan's test: when they collide, the mode wins.

    A metronome you can see out of the corner of your eye is worth having; one
    that lies about the arrangement is not.
    """
    app, _push, engine, project = rig(tmp_path)
    engine.play(0)
    engine.process_offline(256)

    claimed = colors.GREEN.index
    for beat in range(len(BEAT_COLUMN)):
        pads = [colors.OFF.index] * 64
        pads[BEAT_COLUMN[beat]] = claimed
        app._beat_pulse(pads)
        assert pads[BEAT_COLUMN[beat]] == claimed


# ==================================================== the strip's decoding
def test_the_document_s_claim_about_the_strip(tmp_path):
    """What the strip is *said* to send, which is all anyone here knows."""
    assert translate_midi(Msg("pitchwheel", pitch=-8192)) == StripEvent(0.0, True)
    assert translate_midi(Msg("pitchwheel", pitch=8191)) == StripEvent(1.0, True)


def test_a_finger_leaving_the_strip_is_not_a_request(tmp_path):
    """The spring back to centre must not read as "the middle of the song"."""
    app, _push, engine, _project = rig(tmp_path)
    app.handle(StripEvent(0.75))
    landed = engine.current_bar
    app.handle(StripEvent(0.5, touched=False))
    assert engine.current_bar == landed


def test_a_position_outside_the_range_is_clamped(tmp_path):
    app, _push, engine, project = rig(tmp_path)
    app.handle(StripEvent(-5.0))
    assert engine.current_bar == 0
    app.handle(StripEvent(5.0))
    assert engine.current_bar == project.song_bars - 1


# ==================================================== scrubbing
def test_scrubbing_only_works_while_stopped(tmp_path):
    """A finger brushing the strip mid-phrase must not move the playhead."""
    app, _push, engine, _project = rig(tmp_path)
    engine.play(0)
    engine.process_offline(256)
    before = engine.current_bar

    app.handle(StripEvent(0.9))
    assert engine.current_bar == before
    assert "stopped" in app.message


def test_scrubbing_is_refused_during_a_take(tmp_path):
    app, _push, engine, _project = rig(tmp_path)
    engine.arm_record(4, 4)
    app.handle(StripEvent(0.9))
    assert "stopped" in app.message


def test_scrubbing_leaves_the_transport_stopped(tmp_path):
    """It is a scrub, not a "play from here"."""
    app, _push, engine, _project = rig(tmp_path)
    app.handle(StripEvent(0.5))
    engine.process_offline(256)
    assert engine.is_playing is False


def test_scrubbing_follows_the_page_the_playhead_landed_on(tmp_path):
    """Otherwise the grid shows one part of the song and the transport another."""
    from push2sampler.project import PAGE_BARS

    app, _push, engine, project = rig(tmp_path, pages=4)
    app.handle(StripEvent(0.99))
    assert engine.current_bar // PAGE_BARS == app.page
    app.handle(StripEvent(0.0))
    assert app.page == 0


# ==================================================== the loop range
def test_shift_and_the_strip_pick_a_loop_range(tmp_path):
    """One gesture picks a musical range: here to the end of that page."""
    from push2sampler.app import LOOP_SONG
    from push2sampler.project import PAGE_BARS

    app, _push, engine, project = rig(tmp_path, pages=4)
    app.shift = True
    app.handle(StripEvent(0.1))

    start = int(0.1 * project.song_bars)
    assert engine.loop_range == (start, PAGE_BARS)
    assert engine.loop is True
    assert app.loop_scope == LOOP_SONG
    assert "loop bars" in app.message


def test_a_loop_range_never_ends_before_it_starts(tmp_path):
    """The far end of the strip is inside the last page, not past it."""
    app, _push, engine, project = rig(tmp_path, pages=4)
    app.shift = True
    for position in (0.0, 0.25, 0.5, 0.75, 0.99, 1.0):
        app.handle(StripEvent(position))
        start, end = engine.loop_range
        assert 0 <= start < end <= project.song_bars, position


def test_a_loop_range_sets_the_pass_length(tmp_path):
    """`NH-10`'s pass counter is derived from it, so it has to be right."""
    app, _push, engine, _project = rig(tmp_path, pages=4)
    app.shift = True
    app.handle(StripEvent(0.1))
    start, end = engine.loop_range
    assert engine.pass_bars == end - start


def test_shift_and_the_strip_does_not_move_the_playhead(tmp_path):
    """Picking a range and jumping to it are two different requests."""
    app, _push, engine, _project = rig(tmp_path, pages=4)
    app.handle(StripEvent(0.0))
    before = engine.current_bar
    app.shift = True
    app.handle(StripEvent(0.6))
    assert engine.current_bar == before


# ==================================================== the ring
def test_the_ring_is_the_border_of_the_grid_clockwise():
    """A shape you can feel filling, and one that leaves the middle alone."""
    assert len(RING) == 28
    assert len(set(RING)) == 28
    # Starts top-left, runs along the top row, then down the right side.
    assert [index_to_xy(pad) for pad in RING[:3]] == [(0, 0), (1, 0), (2, 0)]
    assert index_to_xy(RING[7]) == (7, 0)
    assert index_to_xy(RING[8]) == (7, 1)
    # Every pad on it is on an edge, and no pad off an edge is on it.
    for pad in RING:
        col, row = index_to_xy(pad)
        assert 0 in (col, row) or 7 in (col, row)
    assert all(index_to_xy(pad) != (3, 3) for pad in RING)


def test_the_pre_roll_flashes_the_ring_rather_than_filling_it(tmp_path):
    """Nothing is being counted yet.

    A ring that started filling during the run-up would arrive at the top a bar
    early, which is worse than not starting.
    """
    from push2sampler.modes.record import RecordMode

    app, _push, engine, _project = rig(tmp_path)
    app.set_mode(RecordMode(app, 0, 4))
    engine.arm_record(4, 4, pre_roll_bars=1)
    engine.process_offline(256)
    assert engine.in_pre_roll is True
    assert engine.count_in_sixteenths[0] == 0

    pads = [colors.OFF.index] * 64
    app.mode.render_pads(pads)
    lit = {value for value in pads if value != colors.OFF.index}
    assert lit <= {colors.RED_DIM.index}      # dim, or off on the other phase


def test_the_next_sixteenth_is_shown_before_it_lands(tmp_path):
    """So the downbeat is visible arriving, not only once it has arrived."""
    from push2sampler.modes.record import RecordMode

    app, _push, engine, _project = rig(tmp_path)
    app.set_mode(RecordMode(app, 0, 4))
    engine.arm_record(4, 4, pre_roll_bars=0)
    engine.process_offline(256)

    pads = [colors.OFF.index] * 64
    app.mode.render_pads(pads)
    dim = [i for i, v in enumerate(pads) if v == colors.RED_DIM.index]
    assert len(dim) == 1
    assert dim[0] in RING


def test_the_engine_reports_no_count_in_when_there_is_none(tmp_path):
    _app, _push, engine, _project = rig(tmp_path)
    assert engine.count_in_sixteenths == (0, 0)
    engine.play(0)
    engine.process_offline(256)
    assert engine.count_in_sixteenths == (0, 0)


def test_a_count_in_of_a_different_length_still_fills_the_ring(tmp_path):
    """Two beats is eight sixteenths, not sixteen."""
    from push2sampler.modes.record import RecordMode

    app, _push, engine, _project = rig(tmp_path)
    app.set_mode(RecordMode(app, 0, 2))
    engine.arm_record(2, 2, pre_roll_bars=0)
    engine.process_offline(256)
    assert engine.count_in_sixteenths[1] == 8


# ==================================================== the pulse
def test_the_pulse_marks_the_beat_up_the_rightmost_column(tmp_path):
    app, _push, engine, _project = rig(tmp_path)
    engine.play(0)
    engine.process_offline(256)

    pads = [colors.OFF.index] * 64
    app._beat_pulse(pads)
    lit = [i for i, v in enumerate(pads) if v != colors.OFF.index]
    assert lit == [BEAT_COLUMN[0]]
    # The downbeat is the bright one, so "where in the bar" reads too.
    assert pads[BEAT_COLUMN[0]] == colors.WHITE.index


def test_the_pulse_is_a_pulse_and_not_a_lit_pad(tmp_path):
    """Lit for a third of the beat: enough to catch the eye, not a steady lamp."""
    app, _push, engine, _project = rig(tmp_path)
    engine.play(0)
    seen_lit = seen_dark = False
    done = 0
    while done < engine.frames_per_beat * 2:
        engine.process_offline(256)
        done += 256
        pads = [colors.OFF.index] * 64
        app._beat_pulse(pads)
        if any(v != colors.OFF.index for v in pads):
            seen_lit = True
        else:
            seen_dark = True
    assert seen_lit and seen_dark


def test_there_is_no_pulse_when_the_transport_is_not_running(tmp_path):
    app, _push, engine, _project = rig(tmp_path)
    pads = [colors.OFF.index] * 64
    app._beat_pulse(pads)
    assert all(v == colors.OFF.index for v in pads)


def test_the_pulse_walks_the_bar(tmp_path):
    """Beat 1 at the bottom of the column, beat 4 three pads up."""
    app, _push, engine, _project = rig(tmp_path)
    engine.play(0)
    seen = {}
    done = 0
    while done < engine.frames_per_beat * 4.5:
        engine.process_offline(256)
        done += 256
        pads = [colors.OFF.index] * 64
        app._beat_pulse(pads)
        lit = [i for i, v in enumerate(pads) if v != colors.OFF.index]
        if lit:
            seen[engine.beat_in_bar] = lit[0]
    assert [seen[beat] for beat in sorted(seen)] == list(BEAT_COLUMN[:len(seen)])


def test_the_beat_column_runs_bottom_to_top():
    """Beat one at the bottom, because that is how a level meter reads."""
    assert len(BEAT_COLUMN) == 8
    assert index_to_xy(BEAT_COLUMN[0]) == (7, 7)
    assert index_to_xy(BEAT_COLUMN[-1]) == (7, 0)
    assert all(index_to_xy(pad)[0] == 7 for pad in BEAT_COLUMN)


# ==================================================== the simulator
def test_the_simulator_can_move_the_strip(tmp_path):
    """So a script can reach it, even though no hand has."""
    from push2sampler.push2 import SimPush

    push = SimPush()
    push.open()
    push.touch_strip(0.25)
    events = list(push.poll_events())
    assert events == [StripEvent(0.25, True)]

    push.touch_strip(0.5, touched=False)
    assert list(push.poll_events()) == [StripEvent(0.5, False)]


def test_the_simulator_clamps_what_a_script_asks_for(tmp_path):
    from push2sampler.push2 import SimPush

    push = SimPush()
    push.open()
    push.touch_strip(9.0)
    assert list(push.poll_events())[0].position == 1.0


# ==================================================== the seek
def test_the_engine_gained_a_seek_because_stop_rewinds(tmp_path):
    """The bug a test caught: scrubbing cannot be play-then-stop.

    `stop` rewinds to bar 1 on purpose -- it is the "back to the top" gesture --
    so every scrub landed on bar 1.  `seek` is the missing third thing: a
    position change on a transport that stays stopped.
    """
    _app, _push, engine, _project = rig(tmp_path)
    engine.play(8)
    engine.stop()
    engine.process_offline(256)
    assert engine.current_bar == 0          # stop rewinds, as it should

    engine.seek(8)
    engine.process_offline(256)
    assert engine.current_bar == 8
    assert engine.is_playing is False


def test_a_seek_is_refused_while_running_or_recording(tmp_path):
    """Moving the playhead under a take is never what anybody meant."""
    _app, _push, engine, _project = rig(tmp_path)
    engine.play(0)
    engine.process_offline(256)
    engine.seek(20)
    engine.process_offline(256)
    assert engine.current_bar < 20

    engine.stop()
    engine.arm_record(4, 4)
    engine.process_offline(256)
    engine.seek(20)
    engine.process_offline(256)
    assert engine.current_bar < 20


def test_a_seek_never_goes_negative(tmp_path):
    """A negative position is the count-in's, and not a place to scrub to."""
    _app, _push, engine, _project = rig(tmp_path)
    engine.seek(-5)
    engine.process_offline(256)
    assert engine.position_frames >= 0


def test_playing_after_a_seek_starts_from_there(tmp_path):
    """Otherwise scrubbing to a spot and pressing Play would be two ideas."""
    _app, _push, engine, _project = rig(tmp_path)
    engine.seek(6)
    engine.process_offline(256)
    assert engine.current_bar == 6
