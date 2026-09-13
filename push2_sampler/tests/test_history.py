import numpy as np
import pytest

from push2sampler.history import (
    MERGE_WINDOW_S,
    ClearTriggers,
    DeleteSample,
    History,
    PutSample,
    SetBpm,
    SetEnabled,
    SetGain,
    ToggleTrigger,
)
from push2sampler.project import Project


def tone(frames, value=0.5):
    return np.full((frames, 1), value, dtype=np.float32)


@pytest.fixture
def project():
    p = Project(samplerate=8000)
    p.put(0, tone(100), bars=1, triggers={2, 3})
    return p


def test_toggle_trigger_round_trips(project):
    history = History()
    assert history.do(project, ToggleTrigger(0, 9, True)) == "bar 10 on"
    assert project[0].triggers == {2, 3, 9}
    history.undo(project)
    assert project[0].triggers == {2, 3}
    history.redo(project)
    assert project[0].triggers == {2, 3, 9}


def test_toggling_off_round_trips(project):
    history = History()
    history.do(project, ToggleTrigger(0, 2, False))
    assert project[0].triggers == {3}
    history.undo(project)
    assert project[0].triggers == {2, 3}


def test_trigger_commands_still_validate_the_bar(project):
    with pytest.raises(ValueError):
        History().do(project, ToggleTrigger(0, 99, True))


def test_clear_triggers_remembers_every_bar(project):
    history = History()
    history.do(project, ClearTriggers(0))
    assert project[0].triggers == set()
    history.undo(project)
    assert project[0].triggers == {2, 3}


def test_set_enabled_round_trips(project):
    history = History()
    history.do(project, SetEnabled(0, False))
    assert project[0].enabled is False
    history.undo(project)
    assert project[0].enabled is True


def test_delete_restores_the_whole_take(project):
    original = project[0]
    history = History()
    history.do(project, DeleteSample(0))
    assert project[0] is None
    history.undo(project)
    # The same take, with its arrangement, mute state, gain and audio intact.
    assert project[0] is original
    assert project[0].triggers == {2, 3}


def test_put_sample_keeps_what_it_replaced(project):
    replaced = project[0]
    history = History()
    history.do(project, PutSample(0, tone(300, 0.25), bars=2))
    assert project[0] is not replaced
    assert project[0].frames == 300
    assert project[0].triggers == {2, 3}  # re-recording keeps the arrangement

    history.undo(project)
    assert project[0] is replaced
    assert np.array_equal(project[0].audio, tone(100))

    history.redo(project)
    assert project[0].frames == 300


def test_put_sample_into_an_empty_slot_undoes_to_empty(project):
    history = History()
    history.do(project, PutSample(7, tone(50), bars=1))
    assert project[7] is not None
    history.undo(project)
    assert project[7] is None


def test_set_bpm_round_trips(project):
    history = History()
    history.do(project, SetBpm(140.0, project.bpm))
    assert project.bpm == 140.0
    history.undo(project)
    assert project.bpm == 120.0


def test_gain_steps_coalesce_into_one_entry(project):
    history = History()
    history.do(project, SetGain(0, 1.02, 1.0))
    history.do(project, SetGain(0, 1.04, 1.02))
    history.do(project, SetGain(0, 1.06, 1.04))
    assert project[0].gain == pytest.approx(1.06)
    # One sweep of the encoder is one undo step, back to where it started.
    history.undo(project)
    assert project[0].gain == pytest.approx(1.0)
    assert history.can_undo is False


def test_a_later_gain_move_is_its_own_entry(project):
    history = History()
    history.do(project, SetGain(0, 1.02, 1.0))
    stale = SetGain(0, 1.5, 1.02)
    stale.at += MERGE_WINDOW_S + 1.0  # as if the hand came back much later
    history.do(project, stale)
    history.undo(project)
    assert project[0].gain == pytest.approx(1.02)
    history.undo(project)
    assert project[0].gain == pytest.approx(1.0)


def test_gain_on_another_slot_does_not_coalesce(project):
    project.put(1, tone(10), bars=1)
    history = History()
    history.do(project, SetGain(0, 1.1, 1.0))
    history.do(project, SetGain(1, 1.2, 1.0))
    history.undo(project)
    assert project[1].gain == pytest.approx(1.0)
    assert project[0].gain == pytest.approx(1.1)


def test_tempo_steps_coalesce(project):
    history = History()
    history.do(project, SetBpm(121.0, 120.0))
    history.do(project, SetBpm(122.0, 121.0))
    history.undo(project)
    assert project.bpm == 120.0
    assert history.can_undo is False


def test_a_new_edit_clears_the_redo_stack(project):
    history = History()
    history.do(project, ToggleTrigger(0, 10, True))
    history.undo(project)
    assert history.can_redo is True
    history.do(project, ToggleTrigger(0, 20, True))
    assert history.can_redo is False


def test_depth_is_bounded(project):
    history = History(depth=64)
    for bar in range(70):
        history.do(project, ToggleTrigger(0, bar % 64, True))
    assert len(history._done) == 64
    for _ in range(64):
        assert history.undo(project) is not None
    assert history.undo(project) is None


def test_undo_and_redo_are_no_ops_when_empty(project):
    history = History()
    assert history.undo(project) is None
    assert history.redo(project) is None
    assert history.can_undo is False
    assert history.can_redo is False


def test_edits_mark_the_project_dirty(project):
    history = History()
    project.dirty = False
    history.do(project, ToggleTrigger(0, 1, True))
    assert project.dirty is True
    project.dirty = False
    history.undo(project)
    assert project.dirty is True


def test_clear_forgets_everything(project):
    history = History()
    history.do(project, ToggleTrigger(0, 1, True))
    history.clear()
    assert history.can_undo is False
    assert history.can_redo is False


# ------------------------------------------------------ velocity (NF-10)
def test_a_trigger_with_a_velocity_round_trips(project):
    from push2sampler.history import SetVelocitySensitivity

    history = History()
    history.do(project, ToggleTrigger(0, 9, True, velocity=60))
    assert project[0].velocity_at(9) == 60
    history.undo(project)
    assert 9 not in project[0].triggers
    assert project[0].velocities == {}
    history.redo(project)
    assert project[0].velocity_at(9) == 60

    history.do(project, SetVelocitySensitivity(0, 1.0, 0.0))
    assert project[0].velocity_sensitivity == 1.0
    history.undo(project)
    assert project[0].velocity_sensitivity == 0.0


def test_undoing_a_toggle_restores_the_velocity_it_replaced(project):
    history = History()
    project[0].set_trigger(5, True, velocity=40)
    history.do(project, ToggleTrigger(0, 5, True, velocity=120))
    assert project[0].velocity_at(5) == 120
    history.undo(project)
    assert project[0].velocity_at(5) == 40  # the softer version is back


def test_clearing_and_erasing_keep_velocities_for_undo(project):
    from push2sampler.history import ClearBar

    history = History()
    project[0].set_trigger(2, True, velocity=30)
    history.do(project, ClearBar(2))
    assert 2 not in project[0].triggers
    history.undo(project)
    assert project[0].velocity_at(2) == 30

    history.do(project, ClearTriggers(0))
    assert project[0].velocities == {}
    history.undo(project)
    assert project[0].velocity_at(2) == 30
