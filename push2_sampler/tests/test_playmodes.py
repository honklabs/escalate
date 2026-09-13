"""NF-02: per-sample playback behaviour -- one-shot, loop, gate, retrigger.

Every one of these is about *when a voice stops*, which is the thing the engine
was worst at: before this, a sample played to the end of its audio no matter
what else happened, so a 4-bar pad bled over the chord that replaced it.

The tests drive the engine offline, where a block is rendered synchronously and
the frame a voice dies on is exactly reproducible.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler.audio import Engine, ScheduledSample
from push2sampler.constants import GATE, LOOP, ONE_SHOT, PLAY_MODES, RETRIGGER

SR = 8000
BPM = 120.0
BEATS = 4
#: 8000 * 60/120 * 4 = 16000 frames per bar at this tempo.
FPBAR = int(SR * (60.0 / BPM) * BEATS)


def engine(song_bars=8, **kwargs):
    return Engine(
        samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
        backend="offline", bpm=BPM, beats_per_bar=BEATS, song_bars=song_bars,
        **kwargs,
    )


def tone(frames, value=0.5):
    """A constant buffer, so "is it sounding" is a question about amplitude."""
    return np.full((frames, 1), value, dtype=np.float32)


def schedule(eng, entries_by_bar, song_bars=8):
    rows = [[] for _ in range(song_bars)]
    for bar, entries in entries_by_bar.items():
        rows[bar] = list(entries)
    eng.set_schedule(rows)


def render(eng, frames, chunk=256):
    """Render ``frames`` frames in blocks; returns the whole output."""
    out = []
    done = 0
    while done < frames:
        n = min(chunk, frames - done)
        out.append(np.array(eng.process_offline(n)))
        done += n
    return np.concatenate(out, axis=0)


def level(block):
    """Peak absolute level per frame, summed across channels."""
    return np.max(np.abs(block), axis=1)


def sounding_at(out, frame):
    return float(np.max(np.abs(out[frame])))


# -- the modes are a closed set -------------------------------------------
def test_the_four_modes_are_the_documented_ones():
    assert PLAY_MODES == (ONE_SHOT, LOOP, GATE, RETRIGGER)


# -- one_shot: unchanged behaviour ----------------------------------------
def test_one_shot_plays_its_whole_length_past_the_bar_line():
    """The old behaviour, pinned: a long take is not cut by a bar line."""
    eng = engine()
    long_take = tone(FPBAR * 2)
    schedule(eng, {0: [ScheduledSample(0, long_take, play_mode=ONE_SHOT)]})
    eng.play()
    out = render(eng, FPBAR * 2)
    # still sounding well past the first bar line
    assert sounding_at(out, FPBAR + 1000) > 0.1
    assert sounding_at(out, FPBAR * 2 - 2000) > 0.1


# -- gate: stops at the end of its own bar --------------------------------
def test_gate_is_cut_at_the_end_of_the_bar_it_started_in():
    eng = engine()
    long_take = tone(FPBAR * 4)
    schedule(eng, {0: [ScheduledSample(0, long_take, play_mode=GATE)]})
    eng.play()
    out = render(eng, FPBAR * 2)
    assert sounding_at(out, FPBAR - 2000) > 0.1        # sounding inside its bar
    release = eng._release_frames
    # Released at the bar line, so silent once the release has run out.
    assert sounding_at(out, FPBAR + release + 500) < 1e-4


def test_a_gate_shorter_than_a_bar_is_unaffected():
    """Nothing is cut that would have finished anyway."""
    eng = engine()
    short = tone(FPBAR // 4)
    schedule(eng, {0: [ScheduledSample(0, short, play_mode=GATE)]})
    eng.play()
    out = render(eng, FPBAR)
    assert sounding_at(out, 1000) > 0.1
    assert sounding_at(out, FPBAR // 4 + 500) < 1e-4   # ended on its own


def test_a_gate_retriggered_on_the_next_bar_keeps_sounding():
    """The new voice must not be cut by the same bar line that ends the old."""
    eng = engine()
    long_take = tone(FPBAR * 4)
    schedule(eng, {
        0: [ScheduledSample(0, long_take, play_mode=GATE)],
        1: [ScheduledSample(0, long_take, play_mode=GATE)],
    })
    eng.play()
    out = render(eng, FPBAR * 2)
    assert sounding_at(out, FPBAR + 3000) > 0.1        # bar 2's own voice
    # And the bar-1 voice really did go: only one is playing.
    playing = [v for v in eng._voices if v.slot == 0 and v.releasing is None]
    assert len(playing) == 1
    assert playing[0].start_bar == 1


# -- loop: repeats until a bar does not renew it --------------------------
def test_loop_repeats_across_the_end_of_its_audio():
    """A one-bar take set to loop covers a bar it is not triggered on."""
    eng = engine()
    one_bar = tone(FPBAR)
    schedule(eng, {
        0: [ScheduledSample(0, one_bar, play_mode=LOOP)],
        1: [ScheduledSample(0, one_bar, play_mode=LOOP)],
    })
    eng.play()
    out = render(eng, FPBAR * 2)
    # Second bar is the loop's second pass, not a second voice.
    assert sounding_at(out, FPBAR + 4000) > 0.1
    assert sounding_at(out, FPBAR * 2 - 4000) > 0.1


def test_loop_releases_on_a_bar_it_is_not_triggered_on():
    eng = engine()
    one_bar = tone(FPBAR)
    schedule(eng, {
        0: [ScheduledSample(0, one_bar, play_mode=LOOP)],
        1: [ScheduledSample(0, one_bar, play_mode=LOOP)],
    })
    eng.play()
    out = render(eng, FPBAR * 3)
    release = eng._release_frames
    assert sounding_at(out, FPBAR * 2 - 2000) > 0.1            # still looping
    assert sounding_at(out, FPBAR * 2 + release + 500) < 1e-4  # let go at bar 3


def test_a_renewed_loop_does_not_stack_a_second_voice():
    """Two triggers on consecutive bars are one continuous voice, not two."""
    eng = engine()
    one_bar = tone(FPBAR, 0.4)
    schedule(eng, {
        0: [ScheduledSample(0, one_bar, play_mode=LOOP)],
        1: [ScheduledSample(0, one_bar, play_mode=LOOP)],
        2: [ScheduledSample(0, one_bar, play_mode=LOOP)],
    })
    eng.play()
    out = render(eng, FPBAR * 3)
    # If a second voice had started, the level would have doubled.
    assert sounding_at(out, FPBAR + 4000) < 0.5
    assert sounding_at(out, FPBAR * 2 + 4000) < 0.5


def test_a_loop_shorter_than_a_segment_wraps_more_than_once():
    """The general fill path: a tiny loop must not leave the segment silent.

    A 300-frame buffer wraps three times inside one 1024-frame block, so this
    exercises the wrapping fill rather than the single-wrap case an on-grid take
    takes.
    """
    eng = engine()
    tiny = tone(300, 0.5)
    schedule(eng, {0: [ScheduledSample(0, tiny, play_mode=LOOP)]})
    eng.play()
    out = render(eng, 4000, chunk=1024)
    # Mid-pass frames, deliberately off the seams (which are multiples of 300).
    for frame in (150, 450, 1050, 2550, 3450):
        assert sounding_at(out, frame) > 0.4, frame


def test_the_loop_seam_is_a_fade_not_a_gap():
    """The documented trade-off, measured.

    The buffer's own 3 ms head and tail fades still apply at the loop point, so
    the seam is a brief dip rather than the click a hard splice would give.  It
    must be *brief*: bounded by those two fades and nothing more.  The cost of
    the wrapping fill being wrong instead would be silence to the end of the
    block, which is what this number would show.
    """
    eng = engine()
    tiny = tone(300, 0.5)
    schedule(eng, {0: [ScheduledSample(0, tiny, play_mode=LOOP)]})
    eng.play()
    out = render(eng, 4000, chunk=1024)
    quiet = level(out[600:1200]) < 0.4          # around the seams at 600 and 900
    longest = 0
    run = 0
    for is_quiet in quiet:
        run = run + 1 if is_quiet else 0
        longest = max(longest, run)
    fade = eng._fade_frames
    assert longest <= 2 * fade + 2, (longest, fade)


def test_looping_reports_the_slot_as_sounding():
    eng = engine()
    schedule(eng, {0: [ScheduledSample(3, tone(FPBAR), play_mode=LOOP)]})
    eng.play()
    render(eng, 2000)
    assert 3 in eng.sounding


# -- retrigger: one voice per slot ----------------------------------------
def test_retrigger_cuts_the_previous_voice_of_the_same_slot():
    eng = engine()
    long_take = tone(FPBAR * 4, 0.4)
    schedule(eng, {
        0: [ScheduledSample(0, long_take, play_mode=RETRIGGER)],
        1: [ScheduledSample(0, long_take, play_mode=RETRIGGER)],
    })
    eng.play()
    render(eng, FPBAR + 2000)
    playing = [v for v in eng._voices if v.slot == 0 and v.releasing is None]
    assert len(playing) == 1


def test_one_shot_layers_where_retrigger_would_cut():
    """The contrast that makes retrigger worth having."""
    eng = engine()
    long_take = tone(FPBAR * 4, 0.4)
    schedule(eng, {
        0: [ScheduledSample(0, long_take, play_mode=ONE_SHOT)],
        1: [ScheduledSample(0, long_take, play_mode=ONE_SHOT)],
    })
    eng.play()
    render(eng, FPBAR + 2000)
    playing = [v for v in eng._voices if v.slot == 0 and v.releasing is None]
    assert len(playing) == 2


# -- choke groups ----------------------------------------------------------
def test_two_samples_in_one_choke_group_never_sound_together():
    eng = engine()
    long_take = tone(FPBAR * 4, 0.4)
    schedule(eng, {
        0: [ScheduledSample(0, long_take, choke_group=1)],
        1: [ScheduledSample(1, long_take, choke_group=1)],
    })
    eng.play()
    render(eng, FPBAR + 2000)
    playing = {v.slot for v in eng._voices if v.releasing is None}
    assert playing == {1}


def test_different_choke_groups_do_not_interfere():
    eng = engine()
    long_take = tone(FPBAR * 4, 0.3)
    schedule(eng, {
        0: [ScheduledSample(0, long_take, choke_group=1)],
        1: [ScheduledSample(1, long_take, choke_group=2)],
    })
    eng.play()
    render(eng, FPBAR + 2000)
    playing = {v.slot for v in eng._voices if v.releasing is None}
    assert playing == {0, 1}


def test_a_slot_does_not_choke_its_own_voices():
    """Otherwise one_shot in a group would silently behave like retrigger.

    A sample's relationship with itself is play_mode's business; the group's
    business is with other samples.
    """
    eng = engine()
    long_take = tone(FPBAR * 4, 0.3)
    schedule(eng, {
        0: [ScheduledSample(0, long_take, play_mode=ONE_SHOT, choke_group=1)],
        1: [ScheduledSample(0, long_take, play_mode=ONE_SHOT, choke_group=1)],
    })
    eng.play()
    render(eng, FPBAR + 2000)
    playing = [v for v in eng._voices if v.slot == 0 and v.releasing is None]
    assert len(playing) == 2


def test_a_choke_does_not_cut_the_voice_it_just_started():
    """Ends run before starts, so ordering inside one bar line matters."""
    eng = engine()
    long_take = tone(FPBAR * 4, 0.3)
    schedule(eng, {
        0: [
            ScheduledSample(0, long_take, choke_group=1),
            ScheduledSample(1, long_take, choke_group=1),
        ],
    })
    eng.play()
    render(eng, 4000)
    playing = {v.slot for v in eng._voices if v.releasing is None}
    # The later entry in the same bar wins; the earlier one is choked.
    assert playing == {1}


def test_a_choke_cuts_a_loop_too():
    eng = engine()
    schedule(eng, {
        0: [ScheduledSample(0, tone(FPBAR, 0.4), play_mode=LOOP, choke_group=1)],
        1: [ScheduledSample(0, tone(FPBAR, 0.4), play_mode=LOOP, choke_group=1)],
        2: [ScheduledSample(1, tone(FPBAR * 2, 0.4), choke_group=1)],
    })
    eng.play()
    render(eng, FPBAR * 2 + 3000)
    playing = {v.slot for v in eng._voices if v.releasing is None}
    assert playing == {1}


# -- a gate is exact, not approximate -------------------------------------
@pytest.mark.parametrize("blocksize", [64, 256, 1024])
def test_a_gate_is_released_on_the_bar_frame_whatever_the_block_size(blocksize):
    """The reason ends happen at bar lines rather than by polling.

    Segments are split at every bar line, so the release starts on the exact
    frame of the line no matter where a block boundary falls.
    """
    eng = engine()
    schedule(eng, {0: [ScheduledSample(0, tone(FPBAR * 4), play_mode=GATE)]})
    eng.play()
    render(eng, FPBAR, chunk=blocksize)
    voice = next(v for v in eng._voices if v.slot == 0)
    # Exactly one bar rendered: the line has been reached but not yet crossed,
    # so nothing has been released.  Boundaries fire on entering a segment.
    assert voice.releasing is None
    assert voice.pos == FPBAR

    render(eng, 1, chunk=1)
    # One frame past the line, the release has consumed exactly that frame --
    # whatever the block size, because segments are cut at every bar line.
    assert voice.releasing == 1
