"""NH-10: per-trigger probability and follow actions.

The plan's four tests are here with its numbers. Everything else is about the
one word in the spec that turned out to carry the whole feature:
**"reproducible for bounce"**.

Two things had to be true for that, and only one of them was obvious.

The obvious one: the dice must be a **pure function** of where you are. A
stateful generator rolled once per trigger is reproducible only if you always
play from the same place -- start at bar 17 instead of bar 1 and every
subsequent roll differs, so what you bounced would not be what you heard.
`roll(seed, pass, bar, slot)` has no state to diverge.

The one a test found: a linear render never loops, so `pass_number` stayed 1
for ever and **a sample set to "every 2nd pass" was absent from the bounce
entirely**. You would hear the arrangement, bounce it, and part of it would be
gone. `passes_needed` is the fix.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler.audio import Engine, ScheduledSample, roll
from push2sampler.constants import ENCODER_TRACK, Btn
from push2sampler.project import (
    CERTAIN,
    MAX_EVERY_N,
    Project,
    Sample,
    _load_every_n,
    _load_probabilities,
    _load_seed,
)
from push2sampler.push2 import SimPush
from push2sampler.render import MAX_PASSES, passes_needed, render_song, render_stems
from push2sampler.settings import Settings

SR = 8000
BPM = 120.0
FPBAR = SR * 2


def engine(seed=0, bars=4, loop=True):
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=bars)
    eng.chance_seed = seed
    eng.loop = loop
    eng.pass_bars = bars
    return eng


def tone(frames=FPBAR // 2, value=0.5):
    return np.full((frames, 1), value, dtype=np.float32)


def fire_log(eng, passes=1, bars=4):
    """(bar, pass) for every attack over `passes` passes."""
    eng.play(0)
    seen, done, total = [], 0, int(FPBAR * bars * passes)
    while done < total:
        eng.process_offline(256)
        done += 256
        if eng.fired:
            seen.append((eng.current_bar, eng.pass_number))
    return seen


def scheduled(bars=4, **kwargs):
    return [[ScheduledSample(0, tone(), **kwargs)] for _ in range(bars)]


# ==================================================== the roll
def test_the_roll_is_a_pure_function_of_where_you_are():
    """The whole of the reproducibility claim.

    A stateful generator would give a different answer depending on how many
    triggers came before -- and so on where you started playing.
    """
    assert roll(7, 1, 5, 2) == roll(7, 1, 5, 2)
    assert roll(7, 1, 5, 2) != roll(7, 2, 5, 2)     # pass
    assert roll(7, 1, 5, 2) != roll(7, 1, 6, 2)     # bar
    assert roll(7, 1, 5, 2) != roll(7, 1, 5, 3)     # slot
    assert roll(7, 1, 5, 2) != roll(8, 1, 5, 2)     # seed


def test_the_roll_is_in_range_and_unbiased():
    values = [roll(s, p, b, 0)
              for s in range(4) for p in range(1, 9) for b in range(64)]
    assert all(0.0 <= value < 1.0 for value in values)
    assert abs(float(np.mean(values)) - 0.5) < 0.02
    # Ten buckets, none starved: a mixer that clumps would show here.
    counts, _edges = np.histogram(values, bins=10, range=(0.0, 1.0))
    assert min(counts) > len(values) / 20


@pytest.mark.parametrize("percent", [25, 50, 75])
def test_a_probability_fires_about_that_often(percent):
    hits = sum(1 for s in range(4) for p in range(1, 33) for b in range(64)
               if roll(s, p, b, 0) < percent / 100.0)
    total = 4 * 32 * 64
    assert abs(hits / total * 100 - percent) < 3.0


def test_negative_arguments_do_not_raise():
    assert 0.0 <= roll(0, -1, -5, -1) < 1.0


# ==================================================== the plan's tests
def test_probability_zero_never_fires():
    eng = engine()
    eng.set_schedule(scheduled(probability=0))
    assert fire_log(eng, passes=2) == []


def test_probability_one_hundred_always_fires():
    eng = engine()
    eng.set_schedule(scheduled(probability=100))
    assert len(fire_log(eng, passes=2)) == 8


def test_a_pass_is_reproducible_with_a_fixed_seed():
    """The plan's test, and the reason `roll` is pure."""
    def run(seed):
        eng = engine(seed)
        eng.set_schedule(scheduled(probability=50))
        return fire_log(eng, passes=8)

    assert run(7) == run(7)
    assert run(7) != run(11)


def test_every_n_two_fires_on_passes_two_four_six():
    """The plan's numbers exactly."""
    eng = engine()
    eng.set_schedule(scheduled(every_n=2))
    fired = fire_log(eng, passes=6)
    assert sorted({pass_number for _bar, pass_number in fired}) == [2, 4, 6]


# ==================================================== passes
def test_pressing_play_starts_the_variation_from_the_top():
    """Otherwise you could never hear the same variation twice."""
    eng = engine()
    eng.set_schedule(scheduled(probability=50))
    first = fire_log(eng, passes=3)
    second = fire_log(eng, passes=3)       # play() again
    assert first == second


def test_the_pass_advances_on_a_loop_wrap():
    eng = engine()
    eng.set_schedule(scheduled(probability=100))
    assert eng.pass_number == 1
    fired = fire_log(eng, passes=3)
    # Three passes were played...
    assert sorted({pass_number for _bar, pass_number in fired}) == [1, 2, 3]
    # ...and the last block landed exactly on the wrap, so we are already
    # standing at the top of the fourth. The count is of passes begun.
    assert eng.pass_number == 4


def test_the_pass_is_derived_when_there_is_no_loop_to_wrap():
    """With nothing to count, the pass has to come from the position.

    This is what a bounce relies on -- and without it a bounce was pass 1 for
    ever.
    """
    eng = engine(bars=16, loop=False)
    eng.pass_bars = 4
    eng.set_schedule([[ScheduledSample(0, tone(), probability=100)]
                      for _ in range(16)])
    fired = fire_log(eng, passes=1, bars=16)
    passes = [pass_number for _bar, pass_number in fired]
    assert passes == [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4]


def test_starting_from_a_later_bar_rolls_the_same_dice():
    """The reason a *stateful* generator was not good enough.

    Bar 6 of pass 1 has to come up the same whether you started at bar 0 or at
    bar 4 -- otherwise "reproducible for bounce" only holds when you happen to
    have played from the top.
    """
    eng = engine(seed=5, bars=8, loop=False)
    eng.pass_bars = 8
    eng.set_schedule([[ScheduledSample(0, tone(), probability=50)]
                      for _ in range(8)])
    eng.play(0)
    from_start = []
    for _ in range(int(FPBAR * 8) // 256):
        eng.process_offline(256)
        if eng.fired:
            from_start.append(eng.current_bar)

    eng2 = engine(seed=5, bars=8, loop=False)
    eng2.pass_bars = 8
    eng2.set_schedule([[ScheduledSample(0, tone(), probability=50)]
                       for _ in range(8)])
    eng2.play(4)
    from_middle = []
    for _ in range(int(FPBAR * 4) // 256):
        eng2.process_offline(256)
        if eng2.fired:
            from_middle.append(eng2.current_bar)

    assert [bar for bar in from_start if bar >= 4] == from_middle


# ==================================================== loops are not dropouts
def test_an_unlucky_bar_does_not_release_a_looping_voice():
    """Probability is about whether a sound *starts*.

    A looping sample whose bar came up unlucky must be renewed, not released:
    a loop that stuttered out because a die rolled low would sound like a
    dropout rather than like an arrangement.
    """
    from push2sampler.constants import LOOP

    eng = engine(seed=1, bars=8, loop=False)
    eng.pass_bars = 8
    entry = ScheduledSample(0, tone(FPBAR), play_mode=LOOP, probability=1)
    eng.set_schedule([[entry] for _ in range(8)])
    eng.play(0)
    # Force the first bar to start by making it certain, then let the rest be
    # near-impossible: the voice must survive them.
    eng._schedule = tuple(
        (ScheduledSample(0, tone(FPBAR), play_mode=LOOP,
                         probability=100 if bar == 0 else 1),)
        for bar in range(8)
    )
    for _ in range(int(FPBAR * 4) // 256):
        eng.process_offline(256)
    assert any(v.slot == 0 and v.releasing is None for v in eng._voices)


# ==================================================== the project
def test_a_probability_survives_a_save_and_load(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone())
    sample.set_trigger(3, True)
    sample.probabilities[3] = 40
    sample.every_n = 3
    project.install(0, sample)
    project.chance_seed = 17
    project.save(tmp_path)

    loaded = Project.load(tmp_path, samplerate=SR)
    assert loaded[0].probabilities == {3: 40}
    assert loaded[0].every_n == 3
    assert loaded.chance_seed == 17


def test_turning_a_bar_off_forgets_its_probability():
    """Otherwise a re-enabled bar would come back mysteriously uncertain."""
    sample = Sample(slot=0, bars=1, audio=tone())
    sample.set_trigger(5, True)
    sample.probabilities[5] = 50
    sample.set_trigger(5, False)
    assert 5 not in sample.probabilities


def test_junk_probabilities_in_a_project_file_are_dropped():
    """A hand-edited file must not put a string into the engine's dice."""
    assert _load_probabilities(None) == {}
    assert _load_probabilities({"x": 50}) == {}
    assert _load_probabilities({"3": "half"}) == {}
    assert _load_probabilities({"3": -10}) == {}
    assert _load_probabilities({"3": 0}) == {}        # that is a trigger, off
    assert _load_probabilities({"3": 100}) == {}      # certain stores nothing
    assert _load_probabilities({"9999": 50}) == {}
    assert _load_probabilities({"3": 50}) == {3: 50}


def test_junk_every_n_and_seed_are_clamped():
    assert _load_every_n("often") == 0
    assert _load_every_n(-4) == 0
    assert _load_every_n(999) == MAX_EVERY_N
    assert _load_every_n(3) == 3
    assert _load_seed(None) == 0
    assert _load_seed(-5) == 0
    assert _load_seed(12) == 12


def test_an_older_project_opens_certain(tmp_path):
    import json

    (tmp_path / "samples").mkdir()
    (tmp_path / "project.json").write_text(json.dumps({
        "version": 9, "samplerate": SR, "bpm": BPM, "slots": [],
    }))
    project = Project.load(tmp_path, samplerate=SR)
    assert project.chance_seed == 0


def test_the_schedule_carries_both():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(), every_n=2)
    sample.set_trigger(0, True)
    sample.probabilities[0] = 30
    project.install(0, sample)
    entry = project.build_schedule()[0][0]
    assert entry.probability == 30
    assert entry.every_n == 2


def test_an_ordinary_trigger_is_certain():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone())
    sample.set_trigger(0, True)
    project.install(0, sample)
    entry = project.build_schedule()[0][0]
    assert entry.probability == CERTAIN
    assert entry.every_n == 0


def test_a_copy_carries_the_chance_settings():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(), every_n=2)
    sample.set_trigger(0, True)
    sample.probabilities[0] = 60
    project.install(0, sample)
    copy = project.copy_slot(0, 1)
    assert copy.probabilities == {0: 60}
    assert copy.every_n == 2


# ==================================================== the bounce
def _song(every_n=0, probability=None, bars=8):
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR // 2), every_n=every_n)
    for bar in range(bars):
        sample.set_trigger(bar, True)
        if probability is not None:
            sample.probabilities[bar] = probability
    project.install(0, sample)
    return project


def test_every_n_is_not_lost_from_the_bounce():
    """The bug a test found, and the worst kind there is.

    Before `passes_needed`, a linear render never left pass 1, so a sample set
    to "every 2nd pass" was **absent from the file**: you heard the
    arrangement, bounced it, and part of it was gone.
    """
    audio = render_song(_song(every_n=2))
    assert float(np.abs(audio).max()) > 0.3


def test_the_bounce_covers_the_whole_variation_cycle():
    assert passes_needed(_song(every_n=2)) == 2
    assert passes_needed(_song(every_n=3)) == 3
    assert passes_needed(_song()) == 1


def test_passes_needed_is_the_lowest_common_multiple():
    """Two samples varying over 2 and 3 passes repeat together after 6."""
    project = _song(every_n=2)
    other = Sample(slot=1, bars=1, audio=tone(), every_n=3)
    other.set_trigger(0, True)
    project.install(1, other)
    assert passes_needed(project) == 6


def test_passes_needed_is_bounded():
    """Eight passes of a long song is already half an hour of render."""
    project = Project(samplerate=SR, bpm=BPM)
    for slot, every in enumerate((5, 7, 8), start=0):
        sample = Sample(slot=slot, bars=1, audio=tone(), every_n=every)
        sample.set_trigger(0, True)
        project.install(slot, sample)
    assert passes_needed(project) == MAX_PASSES


def test_a_muted_sample_does_not_lengthen_the_bounce():
    project = _song(every_n=4)
    project[0].enabled = False
    assert passes_needed(project) == 1


def test_a_sample_with_no_triggers_does_not_lengthen_the_bounce():
    project = _song(every_n=4, bars=0)
    assert passes_needed(project) == 1


def test_what_you_hear_is_what_you_bounce():
    """The spec's promise, tested as a promise rather than as a mechanism."""
    project = _song(probability=50)
    project.chance_seed = 31

    eng = engine(seed=31, bars=8, loop=False)
    eng.pass_bars = 8
    eng.set_schedule(project.build_schedule()[:8])
    eng.play(0)
    heard, done = [], 0
    while done < FPBAR * 8:
        eng.process_offline(256)
        done += 256
        if eng.fired:
            heard.append(eng.current_bar)

    audio = render_song(project)
    per_bar = int(project.frames_per_bar)
    bounced = [
        bar for bar in range(8)
        if float(np.abs(audio[bar * per_bar:bar * per_bar + per_bar // 2]).max()) > 0.1
    ]
    assert heard == bounced, (heard, bounced)


def test_a_stem_keeps_its_every_n_sample_too():
    stems = render_stems(_song(every_n=2))
    assert float(np.abs(stems[0]).max()) > 0.3


# ==================================================== the surface
@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR), name="kick")
    for bar in (0, 1, 2):
        sample.set_trigger(bar, True)
    project.install(0, sample)
    push = SimPush()
    push.open()
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=project.song_bars)
    from push2sampler.app import App

    app = App(push, eng, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, eng, project


def pump(rig):
    app, push = rig[0], rig[1]
    for event in push.poll_events():
        app.handle(event)


def select_bar(rig, pad=9):
    """Press a pad that is *off*, which turns it on and selects it."""
    app, push = rig[0], rig[1]
    app.goto_sample(0)
    push.press_pad(pad)
    pump(rig)
    return app.mode


def test_shift_encoder_two_sets_the_probability(rig):
    app, push, _eng, project = rig
    mode = select_bar(rig)
    assert mode._selected_bar == 9
    app.shift = True
    push.turn(ENCODER_TRACK[1], -4)
    pump(rig)
    app.shift = False
    assert project[0].probabilities == {9: 80}
    assert "80% chance" in app.message


def test_it_asks_for_a_bar_rather_than_choosing_one(rig):
    """Silently editing whichever bar was first would be worse than asking."""
    app, push, _eng, project = rig
    app.goto_sample(0)
    app.shift = True
    push.turn(ENCODER_TRACK[1], -2)
    pump(rig)
    app.shift = False
    assert project[0].probabilities == {}
    assert "press a bar first" in app.message


def test_turning_the_probability_back_up_stores_nothing(rig):
    """Certain is the absence of a probability, not a stored 100."""
    app, push, _eng, project = rig
    select_bar(rig)
    app.shift = True
    push.turn(ENCODER_TRACK[1], -4)
    pump(rig)
    push.turn(ENCODER_TRACK[1], 20)
    pump(rig)
    app.shift = False
    assert project[0].probabilities == {}
    assert "always plays" in app.message


def test_the_probability_is_clamped(rig):
    app, push, _eng, project = rig
    select_bar(rig)
    app.shift = True
    push.turn(ENCODER_TRACK[1], -100)
    pump(rig)
    assert project[0].probabilities[9] > 0
    push.turn(ENCODER_TRACK[1], 100)
    pump(rig)
    app.shift = False
    assert project[0].probabilities == {}


def test_the_probability_is_one_undo_step(rig):
    app, push, _eng, project = rig
    select_bar(rig)
    app.shift = True
    for _ in range(5):
        push.turn(ENCODER_TRACK[1], -1)
        pump(rig)
    app.shift = False
    assert project[0].probabilities == {9: 75}
    app.undo()
    assert project[0].probabilities == {}


def test_unshifted_encoder_two_is_still_the_nudge(rig):
    app, push, _eng, project = rig
    select_bar(rig)
    push.turn(ENCODER_TRACK[1], 3)
    pump(rig)
    assert project[0].nudge_ms > 0
    assert project[0].probabilities == {}


def test_shift_encoder_three_sets_every_n(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    app.shift = True
    push.turn(ENCODER_TRACK[2], 1)
    pump(rig)
    app.shift = False
    assert project[0].every_n == 2
    assert "every 2 passes" in app.message
    app.undo()
    assert project[0].every_n == 0


def test_every_n_is_clamped_and_one_means_every_pass(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    app.shift = True
    push.turn(ENCODER_TRACK[2], 100)
    pump(rig)
    assert project[0].every_n == MAX_EVERY_N
    push.turn(ENCODER_TRACK[2], -100)
    pump(rig)
    app.shift = False
    assert project[0].every_n == 0
    assert "every pass" in app.message


def test_shift_encoder_four_rerolls_the_dice(rig):
    """Without this the seed is 0 for ever and there is one variation."""
    app, push, eng, project = rig
    select_bar(rig)
    app.shift = True
    push.turn(ENCODER_TRACK[1], -4)
    pump(rig)
    push.turn(ENCODER_TRACK[3], 3)
    pump(rig)
    app.shift = False
    assert project.chance_seed == 3
    assert eng.chance_seed == 3
    assert "different variation" in app.message
    app.undo()
    assert project.chance_seed == 0


def test_rerolling_with_nothing_uncertain_says_so(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    app.shift = True
    push.turn(ENCODER_TRACK[3], 1)
    pump(rig)
    app.shift = False
    assert project.chance_seed == 0
    assert "nothing has a chance set" in app.message


def test_a_maybe_bar_flashes_rather_than_using_brightness(monkeypatch):
    """Brightness is already velocity; the plan wanted probability there too.

    The two would have been indistinguishable, and a pad that blinks says
    "this might not play" better than a shade nobody can calibrate by eye.
    """
    import push2sampler.app as app_module
    from push2sampler import colors

    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(), name="k")
    sample.set_trigger(0, True)
    sample.set_trigger(1, True)
    sample.probabilities[1] = 50
    project.install(0, sample)
    push = SimPush()
    push.open()
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="offline", bpm=BPM, song_bars=project.song_bars)
    from push2sampler.app import App

    app = App(push, eng, project, settings=Settings())
    app.goto_sample(0)

    phases = {}
    for name, now in (("on", 0.0), ("off", 0.25)):
        monkeypatch.setattr(app_module.time, "monotonic", lambda now=now: now)
        pads = [0] * 64
        app.mode.render_pads(pads)
        phases[name] = (pads[0], pads[1])
    # The certain bar is green in both phases; the maybe-bar goes dark.
    assert phases["on"][0] == phases["off"][0] == colors.GREEN.index
    assert phases["on"][1] == colors.GREEN.index
    assert phases["off"][1] == colors.OFF.index


def test_the_page_only_mentions_chance_when_something_is_set(rig):
    app, push, _eng, project = rig
    app.goto_sample(0)
    assert "maybe-bar" not in " ".join(app.mode.status_lines())
    select_bar(rig)
    app.shift = True
    push.turn(ENCODER_TRACK[1], -4)
    pump(rig)
    app.shift = False
    text = " ".join(app.mode.status_lines())
    assert "1 maybe-bar(s)" in text
    assert "dice 0" in text


def test_the_page_names_the_selected_bar_and_its_chance(rig):
    app, push, _eng, _project = rig
    mode = select_bar(rig)
    assert "bar 10 selected (always)" in " ".join(mode.status_lines())
    app.shift = True
    push.turn(ENCODER_TRACK[1], -4)
    pump(rig)
    app.shift = False
    assert "bar 10 selected (80%)" in " ".join(mode.status_lines())


def test_the_pass_shows_on_the_transport_only_when_it_matters(rig):
    """A pass counter on every song would be a number with nothing to say."""
    app, _push, _eng, project = rig
    assert "pass" not in app.transport_readout()
    project[0].every_n = 2
    assert "pass 1" in app.transport_readout()
