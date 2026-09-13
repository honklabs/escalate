import json

import numpy as np
import pytest

from push2sampler.project import (
    FORMAT_VERSION,
    SONG_BARS,
    Project,
    Sample,
)
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
        sample.toggle(SONG_BARS)  # one past the last bar of the last page


def test_build_schedule_places_samples_on_their_bars():
    project = Project()
    a = project.put(0, tone(10), bars=1, triggers={0, 3})
    b = project.put(1, tone(20), bars=1, triggers={3})
    schedule = project.build_schedule()
    assert len(schedule) == SONG_BARS
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
    project.put(0, tone(10), bars=1, triggers={0, SONG_BARS + 5})
    schedule = project.build_schedule()
    assert sum(len(entries) for entries in schedule) == 1


def test_a_bar_on_the_last_page_is_scheduled():
    project = Project()
    project.put(0, tone(10), bars=1, triggers={200})
    schedule = project.build_schedule()
    assert len(schedule[200]) == 1


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
    (tmp_path / "samples" / "slot_001.wav").unlink()
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
    assert payload["version"] == FORMAT_VERSION
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


# ------------------------------------------------------ velocity (NF-10)
def test_a_trigger_remembers_how_hard_it_was_played():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.set_trigger(4, True, velocity=70)
    assert sample.triggers == {4}
    assert sample.velocity_at(4) == 70
    # A bar nobody played softly is simply full.
    sample.set_trigger(5, True)
    assert 5 not in sample.velocities
    assert sample.velocity_at(5) == 127


def test_turning_a_bar_off_forgets_its_velocity():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.set_trigger(4, True, velocity=70)
    sample.set_trigger(4, False)
    assert sample.velocities == {}  # no stale entries to drift out of step


def test_full_velocity_is_not_stored():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.set_trigger(1, True, velocity=127)
    assert sample.velocities == {}


def test_velocity_does_nothing_until_the_sample_asks_for_it():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.set_trigger(0, True, velocity=20)
    assert sample.velocity_scale(0) == 1.0  # sensitivity 0: flat, as recorded

    sample.velocity_sensitivity = 1.0
    assert sample.velocity_scale(0) == pytest.approx(20 / 127)
    sample.velocity_sensitivity = 0.5
    assert sample.velocity_scale(0) == pytest.approx(0.5 + 0.5 * 20 / 127)
    assert sample.velocity_scale(9) == 1.0  # an untouched bar is still full


def test_the_schedule_carries_the_velocity_as_gain():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.gain = 0.8
    sample.velocity_sensitivity = 1.0
    sample.set_trigger(0, True, velocity=64)
    sample.set_trigger(1, True)
    schedule = project.build_schedule()
    assert schedule[0][0].gain == pytest.approx(0.8 * 64 / 127)
    assert schedule[1][0].gain == pytest.approx(0.8)


def test_velocities_survive_a_round_trip(tmp_path):
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.velocity_sensitivity = 0.75
    sample.set_trigger(2, True, velocity=40)
    sample.set_trigger(3, True)
    project.save(tmp_path)

    loaded = Project.load(tmp_path, samplerate=8000)[0]
    assert loaded.triggers == {2, 3}
    assert loaded.velocities == {2: 40}
    assert loaded.velocity_sensitivity == 0.75


def test_a_format_2_project_loads_with_velocity_off(tmp_path):
    project = Project(samplerate=8000)
    project.put(0, tone(bar_frames(project)), bars=1, triggers={1})
    project.save(tmp_path)
    payload = json.loads((tmp_path / "project.json").read_text())
    payload["version"] = 2
    del payload["slots"][0]["velocities"]
    del payload["slots"][0]["velocity_sensitivity"]
    (tmp_path / "project.json").write_text(json.dumps(payload))

    loaded = Project.load(tmp_path, samplerate=8000)[0]
    assert loaded.triggers == {1}
    assert loaded.velocities == {}
    assert loaded.velocity_sensitivity == 0.0


def test_re_recording_keeps_the_dynamics(tmp_path):
    project = Project(samplerate=8000)
    sample = project.put(0, tone(100), bars=1)
    sample.velocity_sensitivity = 1.0
    sample.set_trigger(0, True, velocity=50)
    replaced = project.put(0, tone(200), bars=1)
    assert replaced.velocities == {0: 50}
    assert replaced.velocity_sensitivity == 1.0


# --------------------------------------------------- the editor (NF-03)
def test_a_take_with_no_edits_plays_the_recording_itself():
    project = Project(samplerate=8000)
    sample = project.put(0, tone(1000), bars=1)
    assert sample.effective_audio(8000) is sample.audio
    assert sample.frames == sample.raw_frames == 1000


def test_edits_change_what_plays_but_not_the_recording():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000)
    sample = project.put(0, tone(8000), bars=1)
    raw = sample.audio
    sample.set_edits(Edits(trim_start_ms=250, trim_end_ms=250))
    assert sample.frames == 4000  # what plays
    assert sample.raw_frames == 8000  # what was recorded
    assert sample.audio is raw


def test_the_rendered_audio_is_cached_until_something_changes():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000)
    sample = project.put(0, tone(8000), bars=1)
    sample.set_edits(Edits(reverse=True))
    first = sample.effective_audio(8000)
    assert sample.effective_audio(8000) is first  # same object, no re-render

    sample.set_edits(Edits(reverse=True, normalize=True))
    assert sample.effective_audio(8000) is not first


def test_a_new_recording_invalidates_the_cache():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000)
    sample = project.put(0, tone(8000), bars=1)
    sample.set_edits(Edits(reverse=True))
    before = sample.effective_audio(8000)
    sample.audio = tone(4000, 0.25)
    after = sample.effective_audio(8000)
    assert after is not before
    assert after.shape[0] == 4000


def test_the_schedule_plays_the_edited_audio():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000)
    sample = project.put(0, tone(8000), bars=1, triggers={0})
    sample.set_edits(Edits(trim_end_ms=500))
    entry = project.build_schedule()[0][0]
    assert entry.buf.shape[0] == 4000
    assert entry.buf is sample.effective_audio(8000)


def test_trimming_a_take_makes_it_off_grid():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000, bpm=120.0)
    sample = project.put(0, tone(bar_frames(project)), bars=1)
    assert project.mismatched(sample) is False
    sample.set_edits(Edits(trim_end_ms=500))  # now half a second short
    assert project.mismatched(sample) is True


def test_applying_edits_folds_them_into_the_recording():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000)
    sample = project.put(0, tone(8000), bars=1)
    sample.audio_saved = True
    sample.set_edits(Edits(trim_end_ms=500, reverse=True))
    assert sample.apply_edits() is True
    assert sample.raw_frames == 4000  # the recording is the edit now
    assert sample.edits.is_default
    assert sample.audio_saved is False  # so the WAV gets rewritten
    assert sample.apply_edits() is False  # nothing left to apply


def test_edits_survive_a_round_trip(tmp_path):
    from push2sampler.edits import Edits

    project = Project(samplerate=8000)
    sample = project.put(0, tone(1000), bars=1)
    sample.set_edits(Edits(trim_start_ms=10, fade_out_ms=25, pitch_semitones=-2,
                           reverse=True, normalize=True))
    project.save(tmp_path)
    loaded = Project.load(tmp_path, samplerate=8000)[0]
    assert loaded.edits == sample.edits
    assert loaded.raw_frames == 1000


def test_a_format_3_project_loads_with_no_edits(tmp_path):
    project = Project(samplerate=8000)
    project.put(0, tone(bar_frames(project)), bars=1, triggers={0})
    project.save(tmp_path)
    payload = json.loads((tmp_path / "project.json").read_text())
    payload["version"] = 3
    del payload["slots"][0]["edits"]
    (tmp_path / "project.json").write_text(json.dumps(payload))
    loaded = Project.load(tmp_path, samplerate=8000)[0]
    assert loaded.edits.is_default
    assert loaded.triggers == {0}


def test_repairing_a_length_folds_the_edits_in():
    from push2sampler.edits import Edits

    project = Project(samplerate=8000, bpm=120.0)
    sample = project.put(0, tone(bar_frames(project)), bars=1)
    sample.set_edits(Edits(trim_end_ms=500, reverse=True))
    assert project.repair(0) is True
    assert sample.frames == project.expected_frames(1)
    assert sample.edits.is_default  # fitting is destructive, so it commits them


# ============================================== CC-19: swapping two slots
def _sample(slot, value=0.3, **kw):
    import numpy as np

    from push2sampler.project import Sample

    fields = dict(slot=slot, bars=1,
                  audio=np.full((8000, 1), value, dtype=np.float32))
    fields.update(kw)
    return Sample(**fields)


def test_every_sample_field_is_either_copied_or_listed_as_not_copied():
    """The guard that stops the next field being forgotten.

    Colour tags, overdub layers, play modes and choke groups each arrived in a
    different release, and none of them updated ``copy_slot`` -- so duplicating
    a slot quietly lost all four.  A field added from now on has to be either
    carried by the copy or named in NOT_COPIED on purpose.
    """
    import dataclasses

    from push2sampler.project import Project, Sample

    project = Project(samplerate=8000, bpm=120.0)
    source = _sample(0, color=5, play_mode="gate", choke_group=2, gain=0.7,
                     velocity_sensitivity=1.0, source_bpm=98.0,
                     source_samplerate=8000, name="kick")
    source.triggers = {0, 4}
    source.velocities = {4: 90}
    project.install(0, source)
    copy = project.copy_slot(0, 1)

    for f in dataclasses.fields(Sample):
        if f.name in Project.NOT_COPIED:
            continue
        mine, theirs = getattr(copy, f.name), getattr(source, f.name)
        if isinstance(theirs, np.ndarray):
            # The audio array is shared by design, not duplicated -- nothing
            # here mutates a take's samples in place.
            assert mine is theirs, f"copy_slot dropped {f.name}"
        elif isinstance(theirs, list):
            assert [a.shape for a in mine] == [a.shape for a in theirs], f.name
        else:
            assert mine == theirs, f"copy_slot dropped {f.name}"


def test_copy_slot_carries_the_colour_mode_and_group():
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(0, _sample(0, color=4, play_mode="retrigger", choke_group=3))
    copy = project.copy_slot(0, 1)
    assert (copy.color, copy.play_mode, copy.choke_group) == (4, "retrigger", 3)


def test_copy_slot_carries_the_layers_without_sharing_the_list():
    import numpy as np

    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    source = _sample(0)
    source.add_layer(np.full((8000, 1), 0.1, dtype=np.float32))
    project.install(0, source)
    copy = project.copy_slot(0, 1)
    assert copy.layer_count == source.layer_count == 2
    copy.add_layer(np.zeros((8000, 1), dtype=np.float32))
    assert source.layer_count == 2      # the lists are not the same object


def test_swap_exchanges_contents_and_keeps_the_slot_numbers():
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(0, _sample(0, name="kick", color=1))
    project.install(9, _sample(9, name="snare", color=6))
    assert project.swap_slots(0, 9)

    assert project[0].name == "snare"
    assert project[9].name == "kick"
    # The slot number is identity everywhere else, so it stays with the slot.
    assert project[0].slot == 0
    assert project[9].slot == 9
    assert (project[0].color, project[9].color) == (6, 1)


def test_swap_carries_the_arrangement():
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    first = _sample(0, name="a")
    first.triggers = {0, 2, 4}
    second = _sample(1, name="b")
    second.triggers = {8}
    project.install(0, first)
    project.install(1, second)
    project.swap_slots(0, 1)
    assert project[0].triggers == {8}
    assert project[1].triggers == {0, 2, 4}


def test_swapping_with_an_empty_slot_is_a_move():
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(3, _sample(3, name="lead"))
    assert project.swap_slots(3, 40)
    assert project[3] is None
    assert project[40].name == "lead"
    assert project[40].slot == 40


def test_swapping_two_empty_slots_does_nothing():
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    assert project.swap_slots(2, 3) is False


def test_swapping_a_slot_with_itself_is_refused():
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(0, _sample(0))
    assert project.swap_slots(0, 0) is False


def test_swapping_out_of_range_is_refused():
    from push2sampler.project import Project, SLOT_COUNT

    project = Project(samplerate=8000, bpm=120.0)
    project.install(0, _sample(0))
    assert project.swap_slots(0, SLOT_COUNT) is False
    assert project.swap_slots(-1, 0) is False
    assert project[0] is not None


def test_a_swap_marks_the_audio_unsaved_so_the_wavs_are_rewritten():
    """The WAV's filename comes from the slot number, so both have to be
    written again under their new names."""
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    for slot in (0, 1):
        sample = _sample(slot)
        sample.audio_saved = True
        project.install(slot, sample)
    project.swap_slots(0, 1)
    assert not project[0].audio_saved
    assert not project[1].audio_saved


def test_a_swap_survives_a_save_and_load(tmp_path):
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(0, _sample(0, name="kick", value=0.25))
    project.install(1, _sample(1, name="snare", value=0.75))
    project.swap_slots(0, 1)
    project.save(tmp_path / "song")

    reloaded = Project.load(tmp_path / "song", samplerate=8000)
    assert reloaded[0].name == "snare"
    assert reloaded[1].name == "kick"
    # And the audio went with the names, not just the metadata.
    assert float(abs(reloaded[0].audio).max()) == pytest.approx(0.75, abs=0.01)
    assert float(abs(reloaded[1].audio).max()) == pytest.approx(0.25, abs=0.01)


def test_the_swap_command_undoes_by_applying_itself_again():
    from push2sampler.history import History, SwapSlots
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(0, _sample(0, name="kick"))
    project.install(1, _sample(1, name="snare"))
    history = History()

    history.do(project, SwapSlots(0, 1))
    assert project[0].name == "snare"
    history.undo(project)
    assert project[0].name == "kick"
    history.redo(project)
    assert project[0].name == "snare"


def test_undoing_a_swap_into_an_empty_slot_puts_it_back():
    from push2sampler.history import History, SwapSlots
    from push2sampler.project import Project

    project = Project(samplerate=8000, bpm=120.0)
    project.install(5, _sample(5, name="pad"))
    history = History()
    history.do(project, SwapSlots(5, 20))
    assert project[5] is None and project[20].name == "pad"
    history.undo(project)
    assert project[5].name == "pad" and project[20] is None
    assert project[5].slot == 5
