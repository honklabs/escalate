import json

import numpy as np
import pytest

from push2sampler.project import Project, Sample
from push2sampler import wavio


def tone(frames, value=0.5, channels=1):
    return np.full((frames, channels), value, dtype=np.float32)


def test_slots_start_empty():
    project = Project()
    assert project.filled() == []
    assert project.first_empty() == 0
    assert project[0] is None


def test_put_and_delete():
    project = Project()
    sample = project.put(7, tone(100), bars=2)
    assert sample.slot == 7
    assert sample.name == "S08"
    assert project.first_empty() == 0
    assert project.dirty
    project.delete(7)
    assert project[7] is None


def test_re_record_keeps_arrangement_mute_and_gain():
    project = Project()
    sample = project.put(0, tone(100), bars=1)
    sample.triggers.update({1, 2})
    sample.enabled = False
    sample.gain = 0.5
    replaced = project.put(0, tone(200), bars=2)
    assert replaced.triggers == {1, 2}
    assert replaced.enabled is False
    assert replaced.gain == 0.5
    assert replaced.frames == 200


def test_toggle_bar():
    sample = Sample(slot=0, bars=1, audio=tone(10))
    assert sample.toggle(5) is True
    assert sample.triggers == {5}
    assert sample.toggle(5) is False
    assert sample.triggers == set()
    with pytest.raises(ValueError):
        sample.toggle(64)


def test_build_schedule_places_samples_on_their_bars():
    project = Project()
    a = project.put(0, tone(10), bars=1, triggers={0, 3})
    b = project.put(1, tone(20), bars=1, triggers={3})
    schedule = project.build_schedule()
    assert len(schedule) == 64
    assert [e.slot for e in schedule[0]] == [0]
    assert sorted(e.slot for e in schedule[3]) == [0, 1]
    assert schedule[1] == ()

    a.enabled = False
    schedule = project.build_schedule()
    assert [e.slot for e in schedule[3]] == [1]
    assert schedule[0] == ()
    assert project.bars_in_use() == {3}
    assert b is project[1]


def test_schedule_ignores_out_of_range_bars():
    project = Project()
    project.put(0, tone(10), bars=1, triggers={0, 99})
    schedule = project.build_schedule()
    assert sum(len(entries) for entries in schedule) == 1


def test_save_and_load_round_trip(tmp_path):
    project = Project(samplerate=8000, bpm=96.0)
    audio = (np.linspace(-1.0, 1.0, 500, dtype=np.float32)).reshape(-1, 1)
    sample = project.put(3, audio, bars=4, triggers={0, 5, 63})
    sample.enabled = False
    sample.gain = 0.75
    sample.name = "kick"
    project.save(tmp_path)
    assert not project.dirty

    payload = json.loads((tmp_path / "project.json").read_text())
    assert payload["bpm"] == 96.0
    assert payload["slots"][0]["triggers"] == [0, 5, 63]

    loaded = Project.load(tmp_path, samplerate=8000)
    assert loaded.bpm == 96.0
    reloaded = loaded[3]
    assert reloaded.bars == 4
    assert reloaded.triggers == {0, 5, 63}
    assert reloaded.enabled is False
    assert reloaded.gain == 0.75
    assert reloaded.name == "kick"
    assert reloaded.frames == 500
    # 16-bit PCM is the fallback encoding, so allow a quantisation step.
    assert np.allclose(reloaded.audio, audio, atol=1e-4)


def test_load_missing_directory_gives_an_empty_project(tmp_path):
    project = Project.load(tmp_path / "nope", samplerate=8000)
    assert project.filled() == []
    assert project.samplerate == 8000


def test_load_skips_slots_whose_audio_is_missing(tmp_path):
    project = Project(samplerate=8000)
    project.put(1, tone(50), bars=1)
    project.save(tmp_path)
    (tmp_path / "samples" / "slot_01.wav").unlink()
    assert Project.load(tmp_path, samplerate=8000).filled() == []


def test_wav_round_trip_stereo(tmp_path):
    data = np.zeros((300, 2), dtype=np.float32)
    data[:, 0] = 0.5
    data[:, 1] = -0.5
    path = tmp_path / "s.wav"
    wavio.write(path, data, 8000)
    back, rate = wavio.read(path)
    assert rate == 8000
    assert back.shape == (300, 2)
    assert np.allclose(back, data, atol=1e-4)


def test_resample_changes_length():
    data = np.zeros((100, 1), dtype=np.float32)
    out = wavio.resample(data, 8000, 16000)
    assert out.shape[0] == 200
    assert wavio.resample(data, 8000, 8000) is data


def test_load_resamples_foreign_rates(tmp_path):
    data = np.full((100, 1), 0.25, dtype=np.float32)
    (tmp_path / "samples").mkdir(parents=True)
    wavio.write(tmp_path / "samples/slot_00.wav", data, 8000)
    (tmp_path / "project.json").write_text(
        json.dumps(
            {
                "version": 1,
                "samplerate": 8000,
                "bpm": 120,
                "slots": [
                    {"slot": 0, "bars": 1, "triggers": [], "audio": "samples/slot_00.wav"}
                ],
            }
        )
    )
    project = Project.load(tmp_path, samplerate=16000)
    assert project.samplerate == 16000
    assert project[0].frames == 200


# -------------------------------------------------- length truth (F-09)
def bar_frames(project, bars=1):
    return int(bars * project.frames_per_bar)


def test_a_recorded_take_fits_its_bars():
    project = Project(samplerate=8000, bpm=120.0)
    sample = project.put(0, tone(bar_frames(project, 2)), bars=2)
    assert project.length_error(sample) == pytest.approx(0.0)
    assert project.mismatched(sample) is False
    # Provenance is recorded so the UI can explain a later mismatch.
    assert sample.source_bpm == 120.0
    assert sample.source_samplerate == 8000


def test_a_take_from_another_tempo_is_flagged_not_silently_wrong():
    project = Project(samplerate=8000, bpm=120.0)
    sample = project.put(0, tone(bar_frames(project, 2)), bars=2)
    frames_before = sample.frames

    project.bpm = 140.0  # same song opened at a new tempo
    assert project.mismatched(sample) is True
    assert project.length_error(sample) > 0  # too long for the faster grid
    assert sample.frames == frames_before  # the audio is untouched
    assert sample.bars_at(project.bpm, project.samplerate) == pytest.approx(2 * 140 / 120)
    assert project.mismatched_slots() == [0]


def test_a_short_take_is_flagged_as_too_short():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)  # nowhere near a bar
    assert project.mismatched(sample) is True
    assert project.length_error(sample) < 0


def test_tolerance_allows_a_rounding_frame():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(bar_frames(project) + 1), bars=1)
    assert project.mismatched(sample) is False


def test_repair_pads_a_short_take_to_exactly_its_bars():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(1000, 0.5), bars=1)
    assert project.repair(0) is True
    assert sample.frames == project.expected_frames(1)
    assert np.allclose(sample.audio[:1000], 0.5)
    assert np.all(sample.audio[1000:] == 0.0)  # padded with silence
    assert project.mismatched(sample) is False
    assert sample.audio_saved is False  # the WAV has to be rewritten
    assert sample.source_bpm == project.bpm


def test_repair_trims_a_long_take():
    project = Project(samplerate=8000)
    target = project.expected_frames(1)
    sample = project.put(0, tone(target + 5000), bars=1)
    assert project.repair(0) is True
    assert sample.frames == target


def test_repair_leaves_a_fitting_take_alone():
    project = Project(samplerate=8000)
    project.put(0, tone(bar_frames(project)), bars=1)
    assert project.repair(0) is False
    assert project.repair(9) is False  # empty slot


def test_provenance_round_trips(tmp_path):
    project = Project(samplerate=8000, bpm=100.0)
    project.put(2, tone(bar_frames(project)), bars=1)
    project.save(tmp_path)
    payload = json.loads((tmp_path / "project.json").read_text())
    assert payload["version"] == 2
    assert payload["slots"][0]["source_bpm"] == 100.0
    assert payload["slots"][0]["source_samplerate"] == 8000

    loaded = Project.load(tmp_path, samplerate=8000)
    assert loaded[2].source_bpm == 100.0
    assert loaded.mismatched(loaded[2]) is False


def test_a_format_1_project_infers_its_provenance(tmp_path):
    # Written before takes carried a tempo: assume the project's own, so an
    # existing song does not open covered in warnings.
    (tmp_path / "samples").mkdir(parents=True)
    project = Project(samplerate=8000, bpm=90.0)
    wavio.write(tmp_path / "samples/slot_00.wav", tone(bar_frames(project)), 8000)
    (tmp_path / "project.json").write_text(
        json.dumps(
            {
                "version": 1,
                "samplerate": 8000,
                "bpm": 90.0,
                "slots": [
                    {"slot": 0, "bars": 1, "triggers": [1], "audio": "samples/slot_00.wav"}
                ],
            }
        )
    )
    loaded = Project.load(tmp_path, samplerate=8000)
    assert loaded[0].source_bpm == 90.0
    assert loaded[0].source_samplerate == 8000
    assert loaded.mismatched(loaded[0]) is False
    assert loaded[0].triggers == {1}
