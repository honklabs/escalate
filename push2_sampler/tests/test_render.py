"""Bouncing the song to audio, offline."""

import numpy as np
import pytest

from push2sampler.project import Project
from push2sampler.render import (
    BounceJob,
    default_bounce_path,
    render_song,
    render_stems,
    stems_to,
)

SR = 8000


def song(**kwargs):
    project = Project(samplerate=SR, bpm=120.0, **kwargs)
    project.song_bars = 4  # a short song keeps the renders quick
    return project


def tone(project, bars=1, value=0.5):
    return np.full((project.expected_frames(bars), 1), value, dtype=np.float32)


def test_a_bounce_puts_each_sample_on_its_own_bars():
    project = song()
    project.put(0, tone(project), bars=1, triggers={0, 2})
    audio = render_song(project)
    fpbar = int(project.frames_per_bar)
    assert audio.shape[1] == 2  # stereo mix
    assert audio.shape[0] >= fpbar * 4
    # Bars 0 and 2 sound; bars 1 and 3 are silent.
    assert np.abs(audio[fpbar // 2]).max() > 0.4
    assert np.abs(audio[fpbar + fpbar // 2]).max() == pytest.approx(0.0)
    assert np.abs(audio[2 * fpbar + fpbar // 2]).max() > 0.4
    assert np.abs(audio[3 * fpbar + fpbar // 2]).max() == pytest.approx(0.0)


def test_overlapping_samples_sum_in_the_bounce():
    project = song()
    project.put(0, tone(project, bars=2, value=0.25), bars=2, triggers={0})
    project.put(1, tone(project, bars=1, value=0.25), bars=1, triggers={1})
    audio = render_song(project)
    fpbar = int(project.frames_per_bar)
    assert audio[fpbar // 2, 0] == pytest.approx(0.25, abs=0.01)
    assert audio[fpbar + fpbar // 2, 0] == pytest.approx(0.5, abs=0.01)


def test_a_muted_sample_is_left_out_of_the_mix():
    project = song()
    sample = project.put(0, tone(project), bars=1, triggers={0})
    sample.enabled = False
    assert np.all(render_song(project) == 0.0)


def test_velocity_is_honoured_in_the_bounce():
    project = song()
    sample = project.put(0, tone(project), bars=1)
    sample.velocity_sensitivity = 1.0
    sample.set_trigger(0, True, velocity=64)
    sample.set_trigger(2, True, velocity=127)
    audio = render_song(project)
    fpbar = int(project.frames_per_bar)
    soft = np.abs(audio[fpbar // 2]).max()
    loud = np.abs(audio[2 * fpbar + fpbar // 2]).max()
    assert soft == pytest.approx(0.5 * 64 / 127, abs=0.01)
    assert loud == pytest.approx(0.5, abs=0.01)


def test_the_tail_of_a_sample_that_overruns_the_song_is_kept():
    project = song()
    long_take = np.full((project.expected_frames(2), 1), 0.5, dtype=np.float32)
    project.put(0, long_take, bars=2, triggers={3})  # starts on the last bar
    audio = render_song(project)
    fpbar = int(project.frames_per_bar)
    assert audio.shape[0] > fpbar * 4  # rendered past the end for the tail
    assert np.abs(audio[fpbar * 4 + 100]).max() > 0.4


def test_the_tail_can_be_refused():
    project = song()
    project.put(0, np.full((project.expected_frames(2), 1), 0.5, np.float32),
                bars=2, triggers={3})
    audio = render_song(project, tail=False)
    assert audio.shape[0] == int(4 * project.frames_per_bar)


def test_a_shorter_range_can_be_bounced():
    project = song()
    project.put(0, tone(project), bars=1, triggers={0, 3})
    audio = render_song(project, bars=2, tail=False)
    assert audio.shape[0] == int(2 * project.frames_per_bar)


def test_stems_are_one_per_slot_and_sum_to_the_mix():
    project = song()
    project.put(0, tone(project, value=0.25), bars=1, triggers={0})
    project.put(1, tone(project, value=0.25), bars=1, triggers={0, 1})
    stems = render_stems(project)
    assert sorted(stems) == [0, 1]
    mix = render_song(project)
    total = np.zeros_like(mix)
    for audio in stems.values():
        total[: audio.shape[0]] += audio[: total.shape[0]]
    assert np.allclose(total, mix, atol=1e-5)


def test_a_stem_only_contains_its_own_slot():
    project = song()
    project.put(0, tone(project), bars=1, triggers={0})
    project.put(1, tone(project), bars=1, triggers={1})
    stem = render_stems(project)[0]
    fpbar = int(project.frames_per_bar)
    assert np.abs(stem[fpbar // 2]).max() > 0.4
    assert np.abs(stem[fpbar + fpbar // 2]).max() == pytest.approx(0.0)


def test_a_job_reports_progress_as_it_goes():
    project = song()
    project.put(0, tone(project), bars=1, triggers={0})
    job = BounceJob(project)
    assert job.progress == 0.0
    job.step()
    assert 0.0 < job.progress <= 1.0
    while job.step():
        pass
    assert job.done is True
    assert job.progress == 1.0
    assert job.result().shape[0] > 0


def test_an_empty_song_renders_silence_not_a_crash():
    audio = render_song(song())
    assert audio.shape[0] == int(4 * song().frames_per_bar)
    assert np.all(audio == 0.0)


def test_bouncing_does_not_disturb_the_project():
    project = song()
    project.put(0, tone(project), bars=1, triggers={0})
    before = project.build_schedule()
    render_song(project)
    assert [len(bar) for bar in project.build_schedule()] == [len(b) for b in before]


def test_stems_are_written_with_readable_names(tmp_path):
    project = song()
    project.put(3, tone(project), bars=1, triggers={0})
    project[3].name = "kick"
    written = stems_to(project, tmp_path)
    assert [p.name for p in written] == ["slot_03_kick.wav"]
    assert written[0].exists()


def test_the_default_bounce_path_is_inside_the_project(tmp_path):
    path = default_bounce_path(tmp_path)
    assert path.parent == tmp_path / "bounces"
    assert path.suffix == ".wav"
