import numpy as np
import pytest

from push2sampler.audio import Engine, ScheduledSample

SR = 8000  # small rate keeps the offline renders fast


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
    assert engine.transport.frames_per_beat == pytest.approx(SR * 0.5)
    assert engine.transport.frames_per_bar == pytest.approx(SR * 2.0)
    assert engine.transport.song_frames == pytest.approx(SR * 8.0)


def test_sample_starts_on_the_exact_frame_of_its_bar():
    engine = make_engine()
    fpbar = int(engine.transport.frames_per_bar)
    buf = dc(100)
    engine.set_schedule([(), (ScheduledSample(0, buf),), (), ()])
    engine.play(0)
    out = engine.process_offline(fpbar * 2)
    # Silence through bar 0, then the sample exactly at the bar-1 boundary.
    assert np.all(out[:fpbar] == 0)
    assert out[fpbar, 0] == pytest.approx(1.0)
    assert out[fpbar + 99, 0] == pytest.approx(1.0)
    assert out[fpbar + 100, 0] == pytest.approx(0.0)


def test_overlapping_samples_sum():
    engine = make_engine()
    fpbar = int(engine.transport.frames_per_bar)
    long_buf = dc(fpbar * 3, 0.25)  # spans three bars
    short_buf = dc(fpbar, 0.25)
    engine.set_schedule(
        [(ScheduledSample(0, long_buf),), (ScheduledSample(1, short_buf),), (), ()]
    )
    engine.play(0)
    out = engine.process_offline(fpbar * 2)
    assert out[10, 0] == pytest.approx(0.25)
    # In bar 1 both samples sound at once.
    assert out[fpbar + 10, 0] == pytest.approx(0.5)
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
    fpbar = int(engine.transport.frames_per_bar)
    buf = dc(50)
    engine.set_schedule([(ScheduledSample(0, buf),), (), (), ()])
    engine.loop = True
    engine.play(0)
    out = engine.process_offline(fpbar * 4 + 60)
    assert out[0, 0] == pytest.approx(1.0)
    assert out[fpbar * 4, 0] == pytest.approx(1.0)  # start of the next pass
    assert engine.is_playing


def test_no_loop_stops_at_the_end():
    engine = make_engine()
    engine.loop = False
    engine.play(0)
    engine.process_offline(int(engine.transport.song_frames) + 10)
    assert not engine.is_playing
    assert ("stopped",) in engine.poll_events()


def test_count_in_then_exact_length_recording():
    engine = make_engine()
    fpb = int(engine.transport.frames_per_beat)
    fpbar = int(engine.transport.frames_per_bar)
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
    fpb = int(engine.transport.frames_per_beat)
    engine.arm_record(bars=1, count_in_beats=4)
    out = engine.process_offline(4 * fpb)
    assert np.abs(out).max() > 0.1  # the four count-in clicks


def test_record_latency_compensation_shifts_the_take():
    lat_ms = 10.0
    engine = make_engine(rec_latency_ms=lat_ms)
    lat = int(SR * lat_ms / 1000.0)
    fpbar = int(engine.transport.frames_per_bar)
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
    assert out[0, 1] == pytest.approx(0.5)


def test_stereo_sample_is_not_downmixed():
    engine = make_engine()
    buf = np.zeros((100, 2), dtype=np.float32)
    buf[:, 0] = 0.5
    engine.set_schedule([(ScheduledSample(0, buf),), (), (), ()])
    engine.play(0)
    out = engine.process_offline(100)
    assert out[0, 0] == pytest.approx(0.5)
    assert out[0, 1] == pytest.approx(0.0)


def test_tempo_change_rescales_bars():
    engine = make_engine()
    engine.set_bpm(240.0)
    assert engine.transport.frames_per_bar == pytest.approx(SR)
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
    assert len(engine._voices) <= 96
