"""IN-06: take comping and round-robin alternates.

The plan's four tests are here with its numbers. The rest are about the two
things that turned out to be load-bearing and were not in the spec.

**The alternates need their own dice stream.** "Did this bar play?" is
``roll(...) < chance``, so on a 60 % bar *every* trigger you hear has a roll
below 0.6 -- and reusing that number to index three takes would put every one
of them in the first two thirds. The third take would never sound at all.
Measured: 55.8 / 44.2 / **0.0**. `_TAKE_SALT` is the fix, and
``test_the_take_dice_are_a_different_stream_from_the_chance_dice`` is the proof.

**A cycling slot is a pass divisor, exactly like `every_n`.** Three takes on
`cycle` mean the song does not repeat until pass three, so a one-pass bounce
would write take 1 and silently discard the other two -- the same bug `NH-10`
had, arriving through a different door. `passes_needed` now counts both.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from push2sampler.audio import Engine, ScheduledSample, _TAKE_SALT, roll
from push2sampler.constants import DISPLAY_ROW_BOTTOM, ENCODER_TRACK, Btn
from push2sampler.history import (
    AddTake,
    RemoveTake,
    SetActiveTake,
    SetTakeMode,
)
from push2sampler.project import (
    MAX_TAKES,
    TAKE_CYCLE,
    TAKE_FIXED,
    TAKE_MODES,
    TAKE_RANDOM,
    Project,
    _load_active_take,
    _load_take_mode,
)
from push2sampler.push2 import SimPush
from push2sampler.render import MAX_PASSES, passes_needed, render_song, render_stems
from push2sampler.settings import Settings

SR = 8000
BPM = 120.0
FPBAR = SR * 2
TAKE_BUTTON = DISPLAY_ROW_BOTTOM[6]


def tone(value, frames=FPBAR // 2):
    """A flat buffer, so "which take sounded" is readable as a peak level."""
    return np.full((frames, 1), float(value), dtype=np.float32)


THREE = (tone(0.1), tone(0.2), tone(0.3))


def engine(seed=0, bars=4, loop=True):
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=bars)
    eng.chance_seed = seed
    eng.loop = loop
    eng.pass_bars = bars
    return eng


def scheduled(mode=TAKE_FIXED, takes=THREE, bars=4, **kwargs):
    return [
        [ScheduledSample(0, takes[0], alternates=takes, take_mode=mode, **kwargs)]
        for _ in range(bars)
    ]


def sounded(eng, passes=1, bars=4, from_bar=0):
    """(pass, bar, peak) for every voice that started, so takes are nameable."""
    eng.play(from_bar)
    seen, done = [], 0
    while done < FPBAR * bars * passes:
        before = {id(voice) for voice in eng._voices}
        eng.process_offline(256)
        done += 256
        for voice in eng._voices:
            if id(voice) not in before and voice.slot >= 0:
                seen.append((eng.pass_number, eng.current_bar,
                             round(float(np.max(np.abs(voice.buf))), 2)))
    return seen


def peaks(eng, passes=1, bars=4, from_bar=0):
    return [peak for _pass, _bar, peak in sounded(eng, passes, bars, from_bar)]


def project(takes=2, mode=TAKE_FIXED, bars=1, triggers=(0,)):
    proj = Project(samplerate=SR, bpm=BPM)
    proj.pages = 1
    sample = proj.put(0, tone(0.1, FPBAR * bars), bars)
    for index in range(1, takes):
        sample.add_take(tone(0.1 * (index + 1), FPBAR * bars))
    sample.take_mode = mode
    for bar in triggers:
        sample.set_trigger(bar, True)
    return proj, sample


# ==================================================== the plan's tests
def test_three_takes_cycle_in_order_across_three_passes():
    """The plan's test, with its numbers."""
    eng = engine()
    eng.set_schedule(scheduled(TAKE_CYCLE))
    fired = sounded(eng, passes=3)
    by_pass = {}
    for pass_number, _bar, peak in fired:
        by_pass.setdefault(pass_number, set()).add(peak)
    # One take per pass, and the list walked in order.
    assert by_pass == {1: {0.1}, 2: {0.2}, 3: {0.3}}


def test_random_with_a_fixed_seed_is_reproducible():
    """The plan's test.  Reproducible because `roll` is pure, as for chance."""
    def run(seed):
        eng = engine(seed)
        eng.set_schedule(scheduled(TAKE_RANDOM))
        return peaks(eng, passes=3)

    assert run(4) == run(4)
    assert run(4) != run(17)


def test_an_older_project_migrates_to_a_one_take_slot(tmp_path):
    """The plan's test: a single-buffer project is a slot with one take."""
    proj, _sample = project(takes=1)
    proj.save(tmp_path)
    raw = json.loads((tmp_path / "project.json").read_text())
    for slot in raw["slots"]:
        for key in ("takes", "active_take", "take_mode"):
            slot.pop(key, None)
    raw["version"] = 9
    (tmp_path / "project.json").write_text(json.dumps(raw))

    back = Project.load(tmp_path)[0]
    assert back.take_count == 1
    assert back.takes == []          # one alternate is no alternate
    assert back.take_mode == TAKE_FIXED
    assert back.audio.shape[0] > 0   # and the take itself is still there


def test_deleting_a_take_keeps_the_others_intact():
    """The plan's test."""
    _proj, sample = project(takes=3)
    sample.set_active_take(1)
    kept = [float(sample.takes[0][0, 0]), float(sample.takes[2][0, 0])]

    assert sample.remove_take() is True
    assert sample.take_count == 2
    assert [float(take[0, 0]) for take in sample.takes] == kept


# ==================================================== the dice streams
def test_the_take_dice_are_a_different_stream_from_the_chance_dice():
    """The bug this salt exists for, stated as a measurement.

    Reusing the probability roll to index the takes conditions the index on the
    bar having played -- so on a 60 % bar the last of three takes is
    unreachable.  Not merely biased: *never*.
    """
    def spread(salted):
        counts = np.zeros(3, int)
        for seed in range(8):
            for pass_number in range(1, 129):
                for bar in range(64):
                    chance = roll(seed, pass_number, bar, 0)
                    if chance >= 0.6:
                        continue                      # this bar did not play
                    pick = (roll(seed ^ _TAKE_SALT, pass_number, bar, 0)
                            if salted else chance)
                    counts[min(2, int(pick * 3))] += 1
        return counts / counts.sum()

    reused = spread(salted=False)
    assert reused[2] == 0.0                      # the third take never sounds
    salted = spread(salted=True)
    assert all(abs(share - 1 / 3) < 0.02 for share in salted)


def test_random_spreads_evenly_over_the_takes():
    picks = [
        int(roll(seed ^ _TAKE_SALT, pass_number, bar, 0) * 3)
        for seed in range(4) for pass_number in range(1, 33) for bar in range(64)
    ]
    shares = np.bincount(picks, minlength=3) / len(picks)
    assert all(abs(share - 1 / 3) < 0.02 for share in shares)


def test_random_picks_per_trigger_and_cycle_per_pass():
    """The difference between the two modes, as behaviour rather than prose."""
    eng = engine(seed=4)
    eng.set_schedule(scheduled(TAKE_CYCLE))
    per_pass = {}
    for pass_number, _bar, peak in sounded(eng, passes=2):
        per_pass.setdefault(pass_number, set()).add(peak)
    assert all(len(takes) == 1 for takes in per_pass.values())

    eng = engine(seed=4)
    eng.set_schedule(scheduled(TAKE_RANDOM))
    within = set()
    for pass_number, _bar, peak in sounded(eng, passes=2):
        if pass_number == 1:
            within.add(peak)
    assert len(within) > 1          # a different take within the one pass


# ==================================================== the engine
def test_fixed_always_plays_the_selected_take():
    eng = engine()
    eng.set_schedule(scheduled(TAKE_FIXED))
    assert set(peaks(eng, passes=3)) == {0.1}


def test_a_slot_with_one_take_ignores_the_mode_entirely():
    """Nothing to choose, so every mode is `fixed` and none of them can fail."""
    for mode in TAKE_MODES:
        eng = engine()
        eng.set_schedule(scheduled(mode, takes=(tone(0.4),)))
        assert set(peaks(eng, passes=2)) == {0.4}


def test_an_entry_with_no_alternates_plays_its_own_buffer():
    """Every project that has never asked for alternates is this case."""
    eng = engine()
    eng.set_schedule([[ScheduledSample(0, tone(0.7))] for _ in range(4)])
    assert set(peaks(eng, passes=2)) == {0.7}


def test_the_take_is_chosen_when_the_sample_sounds_not_at_the_bar_line():
    """A nudged entry resolves its take with its play mode, at sounding time."""
    eng = engine()
    eng.set_schedule(scheduled(TAKE_CYCLE, nudge=SR * 0.05))
    fired = sounded(eng, passes=2)
    assert {peak for pass_number, _bar, peak in fired if pass_number == 1} == {0.1}
    assert {peak for pass_number, _bar, peak in fired if pass_number == 2} == {0.2}


def test_starting_from_a_later_pass_gives_the_same_takes():
    """The reproducibility claim, for takes rather than for chance."""
    eng = engine(seed=5, bars=16, loop=False)
    eng.pass_bars = 4
    eng.set_schedule([
        [ScheduledSample(0, THREE[0], alternates=THREE, take_mode=TAKE_RANDOM)]
        for _ in range(16)
    ])
    from_the_top = peaks(eng, passes=1, bars=16)

    eng = engine(seed=5, bars=16, loop=False)
    eng.pass_bars = 4
    eng.set_schedule([
        [ScheduledSample(0, THREE[0], alternates=THREE, take_mode=TAKE_RANDOM)]
        for _ in range(16)
    ])
    # Drop in at bar 9, which is pass 3 of a 4-bar pass.
    dropped_in = peaks(eng, passes=1, bars=8, from_bar=8)
    assert dropped_in == from_the_top[8:]


# ==================================================== the model
def test_the_first_alternate_promotes_the_existing_recording():
    """Take 1 is what was already there, the way layer 1 is."""
    _proj, sample = project(takes=1)
    original = sample.audio
    assert sample.add_take(tone(0.9)) is True
    assert sample.take_count == 2
    assert np.array_equal(sample.takes[0], original)
    assert sample.active_take == 1            # you are listening to the new one
    assert np.array_equal(sample.audio, sample.takes[1])


def test_the_audio_is_always_the_selected_take():
    """The invariant everything else in this file relies on."""
    _proj, sample = project(takes=3)
    for index in range(3):
        sample.set_active_take(index)
        assert sample.audio is sample.takes[index]


def test_one_alternate_is_no_alternate():
    """Two representations of one state is how invariants rot."""
    _proj, sample = project(takes=2)
    assert sample.remove_take() is True
    assert sample.takes == []
    assert sample.take_count == 1
    assert sample.active_take == 0


def test_the_last_take_cannot_be_removed():
    _proj, sample = project(takes=1)
    assert sample.remove_take() is False
    assert sample.take_count == 1


def test_a_slot_holds_no_more_than_max_takes():
    """Refused rather than dropping the oldest, which would lose a recording."""
    _proj, sample = project(takes=1)
    for index in range(MAX_TAKES - 1):
        assert sample.add_take(tone(0.05 * index)) is True
    assert sample.take_count == MAX_TAKES
    assert sample.add_take(tone(0.99)) is False
    assert sample.take_count == MAX_TAKES


def test_selecting_the_take_already_selected_changes_nothing():
    _proj, sample = project(takes=3)
    sample.set_active_take(2)
    assert sample.set_active_take(2) is False


def test_an_out_of_range_selection_is_clamped():
    _proj, sample = project(takes=2)
    sample.set_active_take(99)
    assert sample.active_take == 1
    sample.set_active_take(-5)
    assert sample.active_take == 0


def test_alternates_and_layers_never_coexist():
    """Adding an alternate flattens the layer breakdown.

    A layer list describes one take.  The audio is the layers' sum either way,
    so nothing audible is lost -- only the ability to peel back an overdub.
    """
    _proj, sample = project(takes=1)
    sample.add_layer(tone(0.2))
    assert sample.layer_count == 2

    sample.add_take(tone(0.5))
    assert sample.layers == []
    assert sample.layer_count == 1
    assert sample.remove_layer() is False


def test_overdubbing_a_slot_with_alternates_overdubs_the_selected_one():
    _proj, sample = project(takes=3)
    sample.set_active_take(1)
    before = [float(take[0, 0]) for take in sample.takes]

    sample.add_layer(tone(0.5))
    after = [float(take[0, 0]) for take in sample.takes]
    assert sample.take_count == 3
    assert after[1] == pytest.approx(before[1] + 0.5)
    assert after[0] == before[0] and after[2] == before[2]
    assert np.array_equal(sample.audio, sample.takes[1])


def test_applying_the_edits_folds_them_into_every_take():
    """Otherwise switching alternates would change the trim."""
    from push2sampler.edits import Edits

    _proj, sample = project(takes=3, bars=2)
    lengths = {take.shape[0] for take in sample.takes}
    assert len(lengths) == 1

    sample.set_edits(Edits(trim_start_ms=100.0, trim_end_ms=100.0))
    assert sample.apply_edits() is True
    assert sample.take_count == 3
    trimmed = {take.shape[0] for take in sample.takes}
    assert len(trimmed) == 1                      # all of them, equally
    assert trimmed.pop() < lengths.pop()
    assert sample.edits.is_default
    assert np.array_equal(sample.audio, sample.takes[sample.active_take])


def test_repairing_an_off_grid_take_fits_every_alternate():
    """A part that is two bars long is two bars long in all of its takes."""
    proj, sample = project(takes=3, bars=2)
    proj.bpm = 90.0                               # the takes no longer fit
    assert proj.mismatched(sample)

    assert proj.repair(0) is True
    target = proj.expected_frames(sample.bars)
    assert sample.take_count == 3
    assert all(take.shape[0] == target for take in sample.takes)
    assert not proj.mismatched(sample)


def test_re_recording_a_slot_replaces_rather_than_adding():
    """`Record` and `Shift`+`Record` are different gestures for a reason."""
    proj, sample = project(takes=3)
    proj.put(0, tone(0.8), 1)
    assert proj[0].take_count == 1


def test_a_duplicated_slot_carries_its_alternates():
    proj, sample = project(takes=3, mode=TAKE_CYCLE)
    sample.set_active_take(2)
    copy = proj.copy_slot(0, 1)
    assert copy.take_count == 3
    assert copy.active_take == 2
    assert copy.take_mode == TAKE_CYCLE
    assert np.array_equal(copy.audio, copy.takes[2])


def test_the_edits_render_once_per_take_and_are_cached():
    _proj, sample = project(takes=3)
    first = sample.effective_takes(SR)
    assert len(first) == 3
    assert sample.effective_takes(SR) is first    # cached

    sample.set_active_take(1)
    assert sample.effective_takes(SR) is not first


def test_a_single_take_slot_still_gives_a_one_tuple():
    """So the schedule builder needs no special case."""
    _proj, sample = project(takes=1)
    rendered = sample.effective_takes(SR)
    assert len(rendered) == 1
    assert np.array_equal(rendered[0], sample.effective_audio(SR))


# ==================================================== the schedule
def test_the_schedule_carries_the_alternates_only_when_there_are_some():
    proj, sample = project(takes=3, mode=TAKE_RANDOM)
    entry = proj.build_schedule()[0][0]
    assert len(entry.alternates) == 3
    assert entry.take_mode == TAKE_RANDOM

    proj, _sample = project(takes=1)
    entry = proj.build_schedule()[0][0]
    assert entry.alternates == ()


def test_the_scheduled_buffer_is_the_selected_take():
    proj, sample = project(takes=3)
    sample.set_active_take(2)
    entry = proj.build_schedule()[0][0]
    assert np.array_equal(entry.buf, sample.effective_audio(SR))
    assert float(entry.buf[0, 0]) == pytest.approx(0.3)


# ==================================================== the bounce
def test_a_cycling_slot_is_a_pass_divisor():
    """`every_n`'s bug, arriving through a different door."""
    proj, sample = project(takes=3, mode=TAKE_CYCLE)
    assert passes_needed(proj) == 3

    sample.take_mode = TAKE_FIXED
    assert passes_needed(proj) == 1


def test_random_is_not_a_pass_divisor():
    """It never repeats, so there is no cycle to cover."""
    proj, _sample = project(takes=8, mode=TAKE_RANDOM)
    assert passes_needed(proj) == 1


def test_the_cycle_and_every_n_divisors_combine():
    proj, sample = project(takes=3, mode=TAKE_CYCLE)
    sample.every_n = 2
    assert passes_needed(proj) == 6


def test_the_pass_cycle_stays_bounded():
    proj, sample = project(takes=7, mode=TAKE_CYCLE)
    sample.every_n = 5
    assert passes_needed(proj) == MAX_PASSES


def test_a_muted_cycling_slot_does_not_stretch_the_bounce():
    """A slot you cannot hear must not multiply your file length."""
    proj, sample = project(takes=5, mode=TAKE_CYCLE)
    sample.enabled = False
    assert passes_needed(proj) == 1


def test_every_take_of_a_cycling_slot_reaches_the_file():
    """Bounce the song and find all three takes in it, in order.

    Each take is a different frequency, so "which one is in this pass" is a
    measurement rather than a guess.
    """
    def sine(freq, frames):
        t = np.arange(frames) / SR
        return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)[:, None]

    proj = Project(samplerate=SR, bpm=BPM)
    proj.pages = 1
    sample = proj.put(0, sine(200, FPBAR * 2), 2)
    sample.add_take(sine(400, FPBAR * 2))
    sample.add_take(sine(800, FPBAR * 2))
    sample.take_mode = TAKE_CYCLE
    sample.set_trigger(0, True)

    audio = render_song(proj, bars=4, tail=False)
    assert audio.shape[0] == int(FPBAR * 4 * 3)   # three passes, not one

    found = []
    for index in range(3):
        start = int(index * 4 * FPBAR)
        window = audio[start:start + FPBAR * 2, 0]
        spectrum = np.abs(np.fft.rfft(window * np.hanning(len(window))))
        bins = np.fft.rfftfreq(len(window), 1 / SR)
        found.append(round(float(bins[int(np.argmax(spectrum))]), -1))
    assert found == [200.0, 400.0, 800.0]


def test_a_stem_covers_the_same_pass_cycle_as_the_mix():
    """Stems have to sum back to the mix, so they cannot be shorter."""
    proj, _sample = project(takes=3, mode=TAKE_CYCLE, bars=1, triggers=(0,))
    mix = render_song(proj, tail=False)
    stems = render_stems(proj)
    assert stems[0].shape[0] >= mix.shape[0] - 1


# ==================================================== persistence
def test_the_alternates_survive_a_save_and_load(tmp_path):
    proj, sample = project(takes=3, mode=TAKE_CYCLE)
    sample.set_active_take(1)
    levels = [round(float(take[0, 0]), 2) for take in sample.takes]
    proj.save(tmp_path)

    back = Project.load(tmp_path)[0]
    assert back.take_count == 3
    assert back.active_take == 1
    assert back.take_mode == TAKE_CYCLE
    assert [round(float(take[0, 0]), 2) for take in back.takes] == levels
    assert np.array_equal(back.audio, back.takes[1])


def test_a_take_file_per_alternate_is_written(tmp_path):
    proj, _sample = project(takes=3)
    proj.save(tmp_path)
    names = sorted(path.name for path in (tmp_path / "samples").iterdir())
    assert names == ["slot_000.wav", "slot_000_T1.wav",
                     "slot_000_T2.wav", "slot_000_T3.wav"]


def test_a_slot_whose_take_files_have_gone_still_plays(tmp_path):
    """Losing the breakdown must not lose the take -- as with layers."""
    proj, sample = project(takes=3)
    proj.save(tmp_path)
    for path in (tmp_path / "samples").glob("slot_000_T*.wav"):
        path.unlink()

    back = Project.load(tmp_path)[0]
    assert back.take_count == 1
    assert back.audio.shape[0] > 0


def test_a_take_index_past_the_end_is_clamped_on_load(tmp_path):
    """An out-of-range index would break the audio-is-the-take invariant."""
    proj, _sample = project(takes=3)
    proj.save(tmp_path)
    raw = json.loads((tmp_path / "project.json").read_text())
    raw["slots"][0]["active_take"] = 99
    (tmp_path / "project.json").write_text(json.dumps(raw))

    back = Project.load(tmp_path)[0]
    assert back.active_take == 2
    assert np.array_equal(back.audio, back.takes[2])


@pytest.mark.parametrize("junk", ["nonsense", "", None, 3, {}, True])
def test_a_junk_take_mode_becomes_fixed(junk):
    assert _load_take_mode(junk) == TAKE_FIXED


@pytest.mark.parametrize("junk", ["nonsense", None, {}, -4, 3.7])
def test_a_junk_take_index_becomes_zero(junk):
    assert _load_active_take(junk, 3) in range(3)
    assert _load_active_take(junk, 0) == 0


# ==================================================== undo
def rig(tmp_path):
    from push2sampler.app import App

    proj = Project(samplerate=SR, bpm=BPM)
    proj.pages = 1
    push = SimPush()
    push.open()
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=proj.song_bars)
    return App(push, eng, proj, project_dir=tmp_path / "song",
               settings=Settings(path=tmp_path / "settings.json"))


def test_adding_a_take_is_one_undo_step():
    proj, sample = project(takes=1)
    original = sample.audio
    command = AddTake(0, tone(0.6))
    command.apply(proj)
    assert proj[0].take_count == 2

    command.revert(proj)
    assert proj[0].take_count == 1
    assert np.array_equal(proj[0].audio, original)


def test_undoing_an_added_take_restores_the_layer_breakdown():
    """`add_take` flattens the layers, so undo has to put them back."""
    proj, sample = project(takes=1)
    sample.add_layer(tone(0.2))
    assert sample.layer_count == 2

    command = AddTake(0, tone(0.6))
    command.apply(proj)
    assert proj[0].layers == []

    command.revert(proj)
    assert proj[0].layer_count == 2
    assert proj[0].takes == []


def test_undoing_a_refused_take_changes_nothing():
    proj, sample = project(takes=1)
    for index in range(MAX_TAKES - 1):
        sample.add_take(tone(0.01 * index))
    command = AddTake(0, tone(0.99))
    command.apply(proj)
    assert proj[0].take_count == MAX_TAKES

    command.revert(proj)
    assert proj[0].take_count == MAX_TAKES     # the refusal was not an edit


def test_removing_a_take_is_one_undo_step():
    proj, sample = project(takes=3)
    sample.set_active_take(1)
    levels = [round(float(take[0, 0]), 2) for take in sample.takes]

    command = RemoveTake(0)
    command.apply(proj)
    assert proj[0].take_count == 2

    command.revert(proj)
    assert proj[0].take_count == 3
    assert [round(float(take[0, 0]), 2) for take in proj[0].takes] == levels
    assert proj[0].active_take == 1


def test_selecting_a_take_is_undoable_and_encoder_sweeps_merge():
    proj, sample = project(takes=3)
    first = SetActiveTake(0, 1, 0)
    first.apply(proj)
    assert first.merge(SetActiveTake(0, 2, 1)) is True
    first.apply(proj)
    assert proj[0].active_take == 2

    first.revert(proj)
    assert proj[0].active_take == 0


def test_a_sweep_of_a_different_slot_does_not_merge():
    command = SetActiveTake(0, 1, 0)
    assert command.merge(SetActiveTake(1, 1, 0)) is False


def test_the_take_mode_is_undoable():
    proj, _sample = project(takes=3)
    command = SetTakeMode(0, TAKE_RANDOM, TAKE_FIXED)
    command.apply(proj)
    assert proj[0].take_mode == TAKE_RANDOM
    command.revert(proj)
    assert proj[0].take_mode == TAKE_FIXED


# ==================================================== the surface
def surface(tmp_path, takes=3, mode=TAKE_FIXED):
    from push2sampler.modes.sample import SampleMode

    app = rig(tmp_path)
    sample = app.project.put(0, tone(0.1, FPBAR), 1)
    for index in range(1, takes):
        sample.add_take(tone(0.1 * (index + 1), FPBAR))
    sample.take_mode = mode
    sample.set_trigger(0, True)
    app.set_mode(SampleMode(app, 0))
    return app, sample


def test_encoder_three_picks_the_take(tmp_path):
    app, sample = surface(tmp_path)
    sample.set_active_take(0)
    app.mode.on_encoder(ENCODER_TRACK[2], 1)
    assert sample.active_take == 1
    app.mode.on_encoder(ENCODER_TRACK[2], -1)
    assert sample.active_take == 0


def test_encoder_three_clamps_to_the_takes_that_exist(tmp_path):
    app, sample = surface(tmp_path)
    app.mode.on_encoder(ENCODER_TRACK[2], 9)
    assert sample.active_take == 2
    app.mode.on_encoder(ENCODER_TRACK[2], -9)
    assert sample.active_take == 0


def test_encoder_four_sets_the_take_mode(tmp_path):
    app, sample = surface(tmp_path)
    app.mode.on_encoder(ENCODER_TRACK[3], 1)
    assert sample.take_mode == TAKE_CYCLE
    app.mode.on_encoder(ENCODER_TRACK[3], 1)
    assert sample.take_mode == TAKE_RANDOM
    app.mode.on_encoder(ENCODER_TRACK[3], 1)
    assert sample.take_mode == TAKE_RANDOM      # clamped, not wrapped


def test_shift_keeps_the_chance_controls_on_encoders_three_and_four(tmp_path):
    """The unshifted turns are new; the shifted ones must not have moved."""
    app, sample = surface(tmp_path)
    app.shift = True
    app.mode.on_encoder(ENCODER_TRACK[2], 1)
    assert sample.every_n == 2
    assert sample.take_mode == TAKE_FIXED       # not touched

    app.mode.on_encoder(ENCODER_TRACK[3], 3)
    assert app.project.chance_seed == 3
    assert sample.active_take == 2              # unchanged by the shifted turn


def test_a_single_take_slot_says_how_to_make_another(tmp_path):
    app, sample = surface(tmp_path, takes=1)
    app.mode.on_encoder(ENCODER_TRACK[2], 1)
    assert "Shift+Record" in app.message
    app.mode.on_encoder(ENCODER_TRACK[3], 1)
    assert "Shift+Record" in app.message
    assert sample.take_mode == TAKE_FIXED


def test_button_seven_cycles_the_mode_and_wraps(tmp_path):
    app, sample = surface(tmp_path)
    for expected in (TAKE_CYCLE, TAKE_RANDOM, TAKE_FIXED):
        app.mode.on_button(TAKE_BUTTON, True)
        assert sample.take_mode == expected


def test_shift_and_button_seven_removes_the_take(tmp_path):
    app, sample = surface(tmp_path)
    app.shift = True
    app.mode.on_button(TAKE_BUTTON, True)
    assert sample.take_count == 2
    app.undo()
    assert sample.take_count == 3


def test_the_take_button_is_dark_when_there_is_nothing_to_choose(tmp_path):
    app, _sample = surface(tmp_path, takes=1)
    buttons: dict[int, int] = {}
    app.mode.render_buttons(buttons)
    assert buttons[TAKE_BUTTON] == 0

    app, _sample = surface(tmp_path, takes=2)
    buttons = {}
    app.mode.render_buttons(buttons)
    assert buttons[TAKE_BUTTON] > 0


def test_the_status_lines_name_the_take_and_the_mode(tmp_path):
    app, sample = surface(tmp_path, takes=3, mode=TAKE_CYCLE)
    sample.set_active_take(1)
    lines = "\n".join(app.mode.status_lines())
    assert "take 2/3" in lines
    assert "takes cycle" in lines
    assert "enc 3: pick" in lines


def test_an_ordinary_slot_says_nothing_about_takes(tmp_path):
    """One line of "take 1/1" on every sample would be noise."""
    app, _sample = surface(tmp_path, takes=1)
    lines = "\n".join(app.mode.status_lines())
    assert "take 1/1" not in lines
    assert "Shift+Record" in lines           # how to get one, instead


def test_peeling_a_layer_off_a_slot_with_takes_says_why_it_cannot(tmp_path):
    app, sample = surface(tmp_path, takes=3)
    app.shift = True
    app.mode.on_button(Btn.NEW, True)
    assert "no layers" in app.message
    assert sample.take_count == 3


def test_shift_record_opens_record_mode_for_an_alternate(tmp_path):
    app, sample = surface(tmp_path, takes=1)
    app.shift = True
    app.mode.on_button(Btn.RECORD, True)
    assert app.mode.name == "record"
    assert app.mode.alternate is True
    assert app.mode.bars == sample.bars


def test_record_without_shift_still_re_records(tmp_path):
    app, _sample = surface(tmp_path, takes=1)
    app.mode.on_button(Btn.RECORD, True)
    assert app.mode.name == "record"
    assert app.mode.alternate is False


def test_an_alternate_cannot_be_recorded_into_an_empty_slot(tmp_path):
    """There is nothing for it to be an alternate of."""
    app = rig(tmp_path)
    app.goto_record(5, 2, alternate=True)
    assert app.mode.alternate is False


def test_an_alternate_take_keeps_the_length_of_the_original(tmp_path):
    """Otherwise switching takes would change the arrangement."""
    from push2sampler.modes.record import RecordMode

    app, sample = surface(tmp_path, takes=1)
    app.set_mode(RecordMode(app, 0, sample.bars, alternate=True))
    app.mode.on_pad(15, True, 127)
    assert app.mode.bars == sample.bars
    app.mode.on_encoder(ENCODER_TRACK[0], 4)
    assert app.mode.bars == sample.bars


def test_a_full_slot_refuses_another_alternate(tmp_path):
    from push2sampler.modes.record import RecordMode

    app, sample = surface(tmp_path, takes=MAX_TAKES)
    app.set_mode(RecordMode(app, 0, sample.bars, alternate=True))
    assert app.mode.full is True
    app.mode.on_button(Btn.RECORD, True)
    assert app.engine.rec_state == "idle"       # never armed


def test_the_record_page_says_it_is_recording_an_alternate(tmp_path):
    from push2sampler.modes.record import RecordMode

    app, sample = surface(tmp_path, takes=2)
    app.set_mode(RecordMode(app, 0, sample.bars, alternate=True))
    assert "TAKE" in app.mode.title
    assert "another take" in app.message
