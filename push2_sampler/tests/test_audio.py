import numpy as np
import pytest

from push2sampler.audio import (
    FADE_MS,
    MAX_RELEASING,
    MAX_VOICES,
    Engine,
    ScheduledSample,
    Voice,
    make_fade,
)

SR = 8000  # small rate keeps the offline renders fast
#: Frames of the fade applied to both edges of every voice, at SR.
FADE = int(SR * FADE_MS / 1000.0)


def make_engine(**kwargs):
    kwargs.setdefault("samplerate", SR)
    kwargs.setdefault("backend", "offline")
    kwargs.setdefault("bpm", 120.0)
    kwargs.setdefault("song_bars", 4)
    return Engine(blocksize=64, in_channels=1, out_channels=2, **kwargs)


def dc(frames, value=1.0, channels=1):
    return np.full((frames, channels), value, dtype=np.float32)


def test_bar_and_beat_maths():
    engine = make_engine()
    # 120 BPM, 4/4 -> 0.5 s per beat, 2 s per bar.
    assert engine.frames_per_beat == pytest.approx(SR * 0.5)
    assert engine.frames_per_bar == pytest.approx(SR * 2.0)
    assert engine.song_frames == pytest.approx(SR * 8.0)


def test_sample_starts_on_the_exact_frame_of_its_bar():
    engine = make_engine()
    fpbar = int(engine.frames_per_bar)
    buf = dc(100)
    engine.set_schedule([(), (ScheduledSample(0, buf),), (), ()])
    engine.play(0)
    out = engine.process_offline(fpbar * 2)
    # Silence through bar 0, then the sample from the exact bar-1 boundary on.
    # The first frame is the start of the declick fade, so it is silent by
    # design; unity arrives once the fade completes.
    assert np.all(out[:fpbar] == 0)
    assert out[fpbar, 0] == 0.0
    assert 0.0 < out[fpbar + 1, 0] < 1.0
    assert out[fpbar + FADE, 0] == pytest.approx(1.0)
    assert out[fpbar + 99, 0] < 0.1  # fading out into the end of the buffer
    assert out[fpbar + 100, 0] == pytest.approx(0.0)


def test_overlapping_samples_sum():
    engine = make_engine()
    fpbar = int(engine.frames_per_bar)
    long_buf = dc(fpbar * 3, 0.25)  # spans three bars
    short_buf = dc(fpbar, 0.25)
    engine.set_schedule(
        [(ScheduledSample(0, long_buf),), (ScheduledSample(1, short_buf),), (), ()]
    )
    engine.play(0)
    out = engine.process_offline(fpbar * 2)
    assert out[FADE + 10, 0] == pytest.approx(0.25)
    # In bar 1 both samples sound at once.
    assert out[fpbar + FADE + 10, 0] == pytest.approx(0.5)
    assert set(engine.sounding) == {0, 1}


def test_output_is_clipped():
    engine = make_engine()
    buf = dc(1000, 0.9)
    engine.set_schedule([tuple(ScheduledSample(i, buf) for i in range(4)), (), (), ()])
    engine.play(0)
    out = engine.process_offline(500)
    assert out.max() == pytest.approx(1.0)


def test_loop_wraps_and_retriggers_bar_zero():
    engine = make_engine()
    fpbar = int(engine.frames_per_bar)
    buf = dc(200)
    engine.set_schedule([(ScheduledSample(0, buf),), (), (), ()])
    engine.loop = True
    engine.play(0)
    out = engine.process_offline(fpbar * 4 + 100)
    assert out[FADE + 10, 0] == pytest.approx(1.0)
    # ...and again just after the loop wraps to bar 0.
    assert out[fpbar * 4, 0] == 0.0
    assert out[fpbar * 4 + FADE + 10, 0] == pytest.approx(1.0)
    assert engine.is_playing


def test_no_loop_stops_at_the_end():
    engine = make_engine()
    engine.loop = False
    engine.play(0)
    engine.process_offline(int(engine.song_frames) + 10)
    assert not engine.is_playing
    assert ("stopped",) in engine.poll_events()


def test_count_in_then_exact_length_recording():
    engine = make_engine()
    fpb = int(engine.frames_per_beat)
    fpbar = int(engine.frames_per_bar)
    engine.arm_record(bars=2, count_in_beats=4)
    assert engine.rec_state == "count_in"
    assert engine.count_in_beats_left == 4
    assert engine.position_frames == pytest.approx(-4 * fpb)

    # Feed a ramp so we can tell exactly which input frames were captured.
    total = 4 * fpb + 2 * fpbar + 100
    ramp = np.arange(total, dtype=np.float32).reshape(-1, 1)
    engine.process_offline(total, ramp)

    events = dict((e[0], e) for e in engine.poll_events())
    assert "record_armed" in events
    assert "record_started" in events
    done = events["record_done"]
    bars, audio = done[1], done[2]
    assert bars == 2
    assert audio.shape == (2 * fpbar, 1)
    # Capture begins on the frame after the count-in, i.e. offset 4 beats.
    assert audio[0, 0] == pytest.approx(4 * fpb)
    assert audio[-1, 0] == pytest.approx(4 * fpb + 2 * fpbar - 1)
    # Recording stops the transport, as the workflow requires.
    assert not engine.is_playing
    assert engine.rec_state == "idle"


def test_count_in_clicks_are_audible_before_the_take():
    engine = make_engine()
    fpb = int(engine.frames_per_beat)
    engine.arm_record(bars=1, count_in_beats=4)
    out = engine.process_offline(4 * fpb)
    assert np.abs(out).max() > 0.1  # the four count-in clicks


def test_record_latency_compensation_shifts_the_take():
    lat_ms = 10.0
    engine = make_engine(rec_latency_ms=lat_ms)
    lat = int(SR * lat_ms / 1000.0)
    fpbar = int(engine.frames_per_bar)
    engine.arm_record(bars=1, count_in_beats=0)
    total = fpbar + lat + 10
    ramp = np.arange(total, dtype=np.float32).reshape(-1, 1)
    engine.process_offline(total, ramp)
    done = [e for e in engine.poll_events() if e[0] == "record_done"][0]
    audio = done[2]
    assert audio.shape == (fpbar, 1)
    assert audio[0, 0] == pytest.approx(lat)


def test_cancel_record_emits_event_and_stops():
    engine = make_engine()
    engine.arm_record(bars=4)
    engine.cancel_record()
    assert engine.rec_state == "idle"
    assert not engine.is_playing
    assert ("record_cancelled",) in engine.poll_events()


def test_play_while_recording_can_be_disabled():
    engine = make_engine(play_while_recording=False)
    engine.set_schedule([(ScheduledSample(0, dc(100)),), (), (), ()])
    engine.arm_record(bars=1, count_in_beats=0)
    out = engine.process_offline(200)
    assert np.all(out == 0)


def test_mono_sample_feeds_both_output_channels():
    engine = make_engine()
    engine.set_schedule([(ScheduledSample(0, dc(100, 0.5)),), (), (), ()])
    engine.play(0)
    out = engine.process_offline(100)
    assert out[:, 0] == pytest.approx(out[:, 1])
    assert out[50, 1] == pytest.approx(0.5)  # mid-buffer, clear of both fades


def test_stereo_sample_is_not_downmixed():
    engine = make_engine()
    buf = np.zeros((100, 2), dtype=np.float32)
    buf[:, 0] = 0.5
    engine.set_schedule([(ScheduledSample(0, buf),), (), (), ()])
    engine.play(0)
    out = engine.process_offline(100)
    assert out[50, 0] == pytest.approx(0.5)
    assert out[50, 1] == pytest.approx(0.0)


def test_tempo_change_rescales_bars():
    engine = make_engine()
    engine.set_bpm(240.0)
    assert engine.frames_per_bar == pytest.approx(SR)
    engine.arm_record(bars=1, count_in_beats=0)
    engine.set_bpm(120.0)  # refused mid-take
    assert engine.bpm == pytest.approx(240.0)


def test_set_schedule_validates_length():
    engine = make_engine()
    with pytest.raises(ValueError):
        engine.set_schedule([()] * 3)


def test_voice_count_is_bounded():
    engine = make_engine()
    buf = dc(10_000, 0.001)
    engine.set_schedule([tuple(ScheduledSample(0, buf) for _ in range(200)), (), (), ()])
    engine.play(0)
    engine.process_offline(64)
    # MAX_VOICES sound at once; the rest of the bound is the fade-out queue.
    assert len(engine._voices) <= MAX_VOICES + MAX_RELEASING
    assert sum(1 for v in engine._voices if v.releasing is None) <= MAX_VOICES


# ------------------------------------------------------------ declicking
def max_step(out):
    """Largest jump between consecutive frames: a click is a big jump."""
    return float(np.abs(np.diff(out[:, 0])).max())


def test_make_fade_shapes():
    rise, fall = make_fade(32)
    assert rise[0] == 0.0
    assert rise[-1] == pytest.approx(1.0, abs=0.01)
    assert fall[0] == pytest.approx(1.0)
    assert fall[-1] == pytest.approx(0.0, abs=0.01)
    assert (rise + fall) == pytest.approx(np.ones(32))


def test_voice_fades_in_and_out():
    engine = make_engine()
    engine.set_schedule([(ScheduledSample(0, dc(200)),), (), (), ()])
    engine.play(0)
    out = engine.process_offline(200)
    assert out[0, 0] == 0.0
    assert np.all(np.diff(out[:FADE, 0]) > 0)  # strictly rising through the fade
    assert out[FADE, 0] == pytest.approx(1.0)
    assert out[199, 0] < 0.05  # and back to silence at the end
    assert max_step(out) < 0.1  # no edge anywhere in the render


def test_stop_releases_voices_instead_of_cutting_them():
    engine = make_engine()
    engine.set_schedule([(ScheduledSample(0, dc(100_000)),), (), (), ()])
    engine.play(0)
    engine.process_offline(500)  # reach full amplitude
    engine.stop()
    release = engine._release_frames
    out = engine.process_offline(release + 50)
    assert out[0, 0] == pytest.approx(1.0)  # continuous with what came before
    assert max_step(out) < 0.1  # a decay, not a cliff
    assert out[release, 0] == 0.0  # silent once the release completes
    assert engine._voices == []


def test_voice_stealing_fades_the_oldest_rather_than_truncating_it():
    engine = make_engine()
    buf = dc(100_000, 0.001)
    for _ in range(MAX_VOICES):
        engine._add_voice(Voice(buf))
    assert all(v.releasing is None for v in engine._voices)

    engine._add_voice(Voice(buf))  # one too many
    assert engine._voices[0].releasing == 0  # fading, still in the mix
    assert len(engine._voices) == MAX_VOICES + 1

    for _ in range(MAX_RELEASING * 3):
        engine._add_voice(Voice(buf))
    assert len(engine._voices) <= MAX_VOICES + MAX_RELEASING


def test_a_new_take_releases_what_was_playing():
    # play_while_recording off and no count-in, so the only thing in the render
    # is the tail of the voice that was playing when the take was armed.
    engine = make_engine(play_while_recording=False)
    engine.set_schedule([(ScheduledSample(0, dc(100_000)),), (), (), ()])
    engine.play(0)
    engine.process_offline(500)
    engine.arm_record(bars=1, count_in_beats=0)
    out = engine.process_offline(engine._release_frames + 50)
    assert out[0, 0] == pytest.approx(1.0)
    assert max_step(out) < 0.1
    assert out[engine._release_frames, 0] == 0.0


# ------------------------------------------ command queue and stats (F-01)
class FakeStatus:
    """Stands in for sounddevice's CallbackFlags."""

    def __init__(self, **flags):
        self.__dict__.update(flags)

    def __bool__(self):
        return True


def test_a_command_is_applied_at_the_top_of_the_next_block():
    engine = make_engine()
    engine.play(2)
    # The UI sees its request immediately...
    assert engine.is_playing
    assert engine.current_bar == 2
    # ...but the callback has not touched transport state yet.
    assert engine._running is False
    assert engine._pos == 0.0

    engine.process_offline(64)
    assert engine._running is True
    assert engine._pos == pytest.approx(2 * engine.frames_per_bar + 64)
    assert engine._intent is None  # the callback has caught up


def test_the_newest_request_is_what_the_ui_reads():
    engine = make_engine()
    engine.play(0)
    engine.stop()  # before a single block has run
    assert engine.is_playing is False
    engine.process_offline(64)
    assert engine._running is False


def test_apply_commands_reports_the_intent_it_was_satisfying():
    # The callback clears the intent only if it is still the one it saw, which
    # is what stops a mid-block request from being lost.
    engine = make_engine()
    engine.play(0)
    first = engine._intent
    assert engine._apply_commands() is first
    engine.stop()
    assert engine._intent is not first
    assert engine._apply_commands() is engine._intent


def test_the_take_buffer_is_allocated_before_the_callback_sees_it():
    engine = make_engine()
    engine.arm_record(bars=2, count_in_beats=0)
    command = engine._commands.get_nowait()
    assert command[0] == "arm"
    buf = command[3]
    assert isinstance(buf, np.ndarray)
    assert buf.shape == (int(2 * engine.frames_per_bar), 1)


def test_a_tempo_change_does_not_retrigger_the_current_bar():
    engine = make_engine()
    # Nothing on bar 0, a sample on bar 1.
    engine.set_schedule([(), (ScheduledSample(0, dc(100_000)),), (), ()])
    engine.play(0)
    engine.process_offline(int(engine.frames_per_bar) - 1000)
    assert engine._voices == []

    # Doubling the tempo moves the playhead into bar 1 of the new grid; the
    # re-anchor must stop that counting as a fresh bar boundary.
    engine.set_bpm(240.0)
    engine.process_offline(64)
    assert engine._voices == []


def test_stats_are_published_every_block():
    engine = make_engine()
    engine.set_schedule([(ScheduledSample(0, dc(1000, 0.5)),), (), (), ()])
    engine.play(0)
    engine.process_offline(200)
    assert engine.stats.peak_out == pytest.approx(0.5, abs=0.01)
    assert engine.stats.voices == 1
    assert engine.stats.callback_ms > 0.0
    assert engine.stats.callback_ms_max >= engine.stats.callback_ms


def test_dropouts_are_counted_and_announced():
    engine = make_engine()
    engine.note_status(FakeStatus(input_overflow=True))
    assert ("xrun", 1) in engine.poll_events()
    engine.note_status(FakeStatus(output_underflow=True))
    assert ("xrun", 2) in engine.poll_events()
    engine.process_offline(64)
    assert engine.stats.xruns == 2


def test_a_status_without_a_dropout_flag_is_ignored():
    engine = make_engine()
    engine.note_status(FakeStatus(priming_output=True))
    assert engine.poll_events() == []
    engine.process_offline(64)
    assert engine.stats.xruns == 0


def test_the_portaudio_callback_renders_and_reports():
    # The one entry point a machine without a sound card never exercises, so
    # drive it directly with the arguments PortAudio would pass.
    engine = make_engine()
    engine.set_schedule([(ScheduledSample(0, dc(1000, 0.5)),), (), (), ()])
    engine.play(0)
    frames = 64
    outdata = np.zeros((frames, 2), dtype=np.float32)
    indata = np.zeros((frames, 1), dtype=np.float32)
    engine._sd_callback(indata, outdata, frames, None, FakeStatus(output_underflow=True))
    assert outdata[FADE + 10, 0] == pytest.approx(0.5)  # it rendered
    assert engine.stats.xruns == 1  # and noticed the dropout
    assert ("xrun", 1) in engine.poll_events()


# ------------------------------------- input metering and monitoring (F-07)
def test_the_input_meter_follows_the_signal():
    engine = make_engine()
    loud = np.full((64, 1), 0.5, dtype=np.float32)
    engine.process_offline(64, loud)
    assert engine.stats.input_peak == pytest.approx(0.5)
    assert engine.stats.input_rms == pytest.approx(0.5, abs=0.01)


def test_the_peak_meter_falls_back_slowly():
    engine = make_engine()
    engine.process_offline(64, np.full((64, 1), 0.8, dtype=np.float32))
    first = engine.stats.input_peak
    engine.process_offline(64)  # silence
    second = engine.stats.input_peak
    assert 0.0 < second < first  # decaying, not snapping to zero
    for _ in range(40):
        engine.process_offline(64)
    assert engine.stats.input_peak < 0.01


def test_clipping_latches_until_it_is_read():
    engine = make_engine()
    engine.process_offline(64, np.full((64, 1), 1.2, dtype=np.float32))
    assert engine.input_clipped is True
    engine.process_offline(64)  # a quiet block does not clear it
    assert engine.take_clipped() is True
    assert engine.take_clipped() is False  # reading clears the latch


def test_monitoring_off_keeps_the_input_out_of_the_output():
    engine = make_engine(monitor="off", monitor_gain=1.0)
    out = engine.process_offline(64, np.full((64, 1), 0.5, dtype=np.float32))
    assert np.all(out == 0.0)


def test_monitoring_on_passes_the_input_through_at_its_gain():
    engine = make_engine(monitor="on", monitor_gain=0.5)
    out = engine.process_offline(64, np.full((64, 1), 0.5, dtype=np.float32))
    assert out[0, 0] == pytest.approx(0.25)
    assert out[0, 1] == pytest.approx(0.25)


def test_auto_monitoring_only_while_a_take_runs():
    engine = make_engine(monitor="auto", monitor_gain=1.0)
    signal = np.full((64, 1), 0.5, dtype=np.float32)
    assert np.all(engine.process_offline(64, signal) == 0.0)  # idle: silent

    engine.arm_record(bars=1, count_in_beats=4)
    out = engine.process_offline(64, signal)
    assert out[0, 0] == pytest.approx(0.5)  # counting in: audible

    engine.stop()
    for _ in range(4):  # let the count-in click finish its release fade
        engine.process_offline(64, signal)
    assert np.all(engine.process_offline(64, signal) == 0.0)  # idle again


def test_a_zero_monitor_gain_still_means_silence():
    engine = make_engine(monitor="on", monitor_gain=0.0)
    assert np.all(engine.process_offline(64, np.full((64, 1), 0.5, np.float32)) == 0.0)
