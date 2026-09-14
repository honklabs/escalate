"""IN-05: the song as a score that never plays the same way twice.

The plan's three tests are here, including the one it calls "the key property --
it is what makes this trustworthy": the live transport and a bounce of the same
pass range produce the same thing.

The interesting finding is how little of this item was left to build. "Every 4th
pass, double the hats" needed **no engine change at all**, because `NH-10`
already gave every trigger a pass divisor -- an extra bar that plays only on
every 4th pass *is* a trigger with ``every_n`` of 4. Reproducibility, correct
bouncing and a readable grid all came with it.

And one bug worth keeping: the first fill spread its pattern over the **span**
the sample occupies, so for hats on bars 1, 3, 5, 7 the new bars landed on top
of the old ones and subtracted away to nothing. A fill goes in the *gaps*.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from push2sampler import colors
from push2sampler.constants import ENCODER_TRACK, Btn
from push2sampler.history import SetVariation
from push2sampler.modes.living import CLEAR_BUTTON, DEFAULT_PASSES, LivingMode
from push2sampler.project import (
    MAX_VARIATION_EVERY,
    Project,
    _load_variation,
    _load_variation_every,
)
from push2sampler.render import passes_needed, render_song

SR = 8000
BPM = 120.0
FPBAR = SR * 2


def tone(value=0.4, frames=FPBAR // 2):
    return np.full((frames, 1), float(value), dtype=np.float32)


def project(bars=(0, 2, 4, 6)):
    proj = Project(samplerate=SR, bpm=BPM)
    proj.pages = 1
    sample = proj.put(0, tone(), 1)
    sample.name = "hat"
    for bar in bars:
        sample.set_trigger(bar, True)
    return proj, sample


def rig(tmp_path, bars=(0, 2, 4, 6)):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    proj, sample = project(bars)
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=BPM, song_bars=proj.song_bars)
    app = App(push, engine, proj, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    app.set_mode(LivingMode(app, 0))
    return app, sample


def bars_sounding(audio, pass_index, span=8):
    seg = audio[int(pass_index * span * FPBAR):int((pass_index + 1) * span * FPBAR), 0]
    return [
        bar + 1 for bar in range(span)
        if float(np.abs(seg[int(bar * FPBAR):int(bar * FPBAR) + 100]).max()) > 0.01
    ]


# ==================================================== the plan's tests
def test_two_renders_with_the_same_seed_are_identical():
    """The plan's test."""
    proj, sample = project()
    sample.variation_bars = {1, 3, 5}
    sample.variation_every = 4
    proj.chance_seed = 7
    first = render_song(proj, bars=8, tail=False)
    second = render_song(proj, bars=8, tail=False)
    assert np.array_equal(first, second)


def test_different_seeds_differ_when_anything_is_uncertain():
    """The plan's test.

    A variation alone is *arithmetic*, not chance, so the seed cannot change it
    -- which is a feature, not a gap.  So this asserts the pair the plan meant:
    a probability, which is what the seed exists for.
    """
    def render(seed):
        proj, sample = project()
        sample.variation_bars = {1, 3, 5}
        sample.variation_every = 2
        for bar in sample.triggers:
            sample.probabilities[bar] = 50
        proj.chance_seed = seed
        return render_song(proj, bars=8, tail=False)

    assert np.array_equal(render(3), render(3))
    assert not np.array_equal(render(3), render(11))


def test_a_variation_is_arithmetic_and_the_seed_cannot_move_it():
    """Stated as its own test, because it is easy to expect otherwise.

    "Every 4th pass" is a divisor.  Rolling dice over it would make the fill
    arrive at unpredictable times, which is not what "every 4th pass" says.
    """
    def render(seed):
        proj, sample = project()
        sample.variation_bars = {1, 3, 5}
        sample.variation_every = 4
        proj.chance_seed = seed
        return render_song(proj, bars=8, tail=False)

    assert np.array_equal(render(0), render(31))


def test_the_live_transport_and_a_bounce_agree():
    """The plan's key property, and the whole reason to trust a freeze.

    Played live and rendered offline, the same pass puts the same bars in the
    same places -- which holds because `NH-10` made a pass a function of
    *position* rather than of history.
    """
    from push2sampler.audio import Engine

    proj, sample = project()
    sample.variation_bars = {1, 3, 5}
    sample.variation_every = 4

    # Live: four passes round an 8-bar loop.
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=BPM, song_bars=proj.song_bars)
    engine.loop = True
    engine.loop_range = (0, 8)
    engine.pass_bars = 8
    engine.chance_seed = proj.chance_seed
    engine.set_schedule(proj.build_schedule())
    engine.play(0)
    heard = {}
    done = 0
    while done < FPBAR * 8 * 4:
        before = {id(voice) for voice in engine._voices}
        engine.process_offline(256)
        done += 256
        for voice in engine._voices:
            if id(voice) not in before and voice.slot >= 0:
                heard.setdefault(engine.pass_number, []).append(engine.current_bar + 1)

    bounced = render_song(proj, bars=8, tail=False)
    for pass_number in (1, 2, 3, 4):
        assert sorted(set(heard[pass_number])) == bars_sounding(bounced, pass_number - 1), \
            pass_number


def test_the_fill_arrives_on_the_pass_it_says_and_not_before():
    """The behaviour the whole item is for, read off a rendered file."""
    proj, sample = project()
    sample.variation_bars = {1, 3, 5}
    sample.variation_every = 4
    audio = render_song(proj, bars=8, tail=False)
    assert audio.shape[0] == int(FPBAR * 8 * 4)     # a whole cycle

    assert bars_sounding(audio, 0) == [1, 3, 5, 7]
    assert bars_sounding(audio, 1) == [1, 3, 5, 7]
    assert bars_sounding(audio, 2) == [1, 3, 5, 7]
    assert bars_sounding(audio, 3) == [1, 2, 3, 4, 5, 6, 7]


# ==================================================== the schedule
def test_a_variation_bar_is_scheduled_with_the_pass_divisor():
    """No engine change was needed: it is `NH-10`'s ``every_n``."""
    proj, sample = project()
    sample.variation_bars = {1}
    sample.variation_every = 4
    entry = proj.build_schedule()[1][0]
    assert entry.slot == 0
    assert entry.every_n == 4


def test_a_bar_in_both_belongs_to_the_arrangement():
    """A bar that plays every pass cannot also play only on some."""
    proj, sample = project()
    sample.variation_bars = {0, 1}       # bar 0 already plays
    sample.variation_every = 4
    assert [entry.every_n for entry in proj.build_schedule()[0]] == [0]
    assert [entry.every_n for entry in proj.build_schedule()[1]] == [4]


def test_a_variation_with_no_divisor_is_simply_not_scheduled():
    """"Every pass" is not a variation; it is the arrangement."""
    proj, sample = project()
    sample.variation_bars = {1}
    sample.variation_every = 1
    assert proj.build_schedule()[1] == ()


def test_a_variation_lengthens_a_bounce():
    """The third door onto `NH-10`'s vanished-from-the-file bug."""
    proj, sample = project()
    assert passes_needed(proj) == 1
    sample.variation_bars = {1, 3}
    sample.variation_every = 4
    assert passes_needed(proj) == 4


def test_a_muted_slot_s_variation_does_not_lengthen_a_bounce():
    proj, sample = project()
    sample.variation_bars = {1, 3}
    sample.variation_every = 4
    sample.enabled = False
    assert passes_needed(proj) == 1


def test_a_variation_combines_with_the_other_divisors():
    proj, sample = project()
    sample.variation_bars = {1}
    sample.variation_every = 3
    sample.every_n = 2
    assert passes_needed(proj) == 6


# ==================================================== the fill
def test_the_fill_goes_in_the_gaps_and_not_over_the_part(tmp_path):
    """The bug this exists for.

    Spreading the pattern over the *span* put the new bars on the old ones: for
    hats on 1, 3, 5, 7 the fill landed on bar 1 and subtracted away to nothing.
    """
    app, sample = rig(tmp_path)
    app.mode.on_encoder(ENCODER_TRACK[0], 3)       # every 4 passes
    app.mode.on_encoder(ENCODER_TRACK[1], 2)       # three extra bars

    assert sample.variation_bars
    assert not sample.variation_bars & sample.triggers
    assert sample.variation_bars == {1, 3, 5}


def test_the_fill_stays_inside_the_part(tmp_path):
    """So a fill lands where the music is, not across an empty page."""
    app, sample = rig(tmp_path, bars=(8, 10, 12, 14))
    app.mode.on_encoder(ENCODER_TRACK[0], 3)
    app.mode.on_encoder(ENCODER_TRACK[1], 2)
    assert min(sample.variation_bars) >= 8
    assert max(sample.variation_bars) <= 14


def test_a_solid_block_is_filled_past_its_end(tmp_path):
    """There are no gaps in a solid block; the only room left is after it."""
    app, sample = rig(tmp_path, bars=(0, 1, 2, 3))
    app.mode.on_encoder(ENCODER_TRACK[0], 3)
    app.mode.on_encoder(ENCODER_TRACK[1], 1)
    assert sample.variation_bars
    assert min(sample.variation_bars) >= 4
    assert not sample.variation_bars & sample.triggers


def test_a_fill_of_nothing_clears_the_variation(tmp_path):
    app, sample = rig(tmp_path)
    app.mode.on_encoder(ENCODER_TRACK[0], 3)
    app.mode.on_encoder(ENCODER_TRACK[1], 2)
    assert sample.variation_bars

    app.mode.on_encoder(ENCODER_TRACK[1], -9)
    assert sample.variation_bars == set()


# ==================================================== the surface
def test_shift_and_clip_opens_the_page_from_a_sample(tmp_path):
    from push2sampler.modes.sample import SampleMode

    app, _sample = rig(tmp_path)
    app.set_mode(SampleMode(app, 0))
    app.shift = True
    app.mode.on_button(Btn.CLIP, True)
    assert app.mode.name == "living"
    assert app.mode.slot == 0


def test_encoder_one_sets_how_often(tmp_path):
    app, sample = rig(tmp_path)
    app.mode.on_encoder(ENCODER_TRACK[0], 3)
    assert sample.variation_every == 4
    app.mode.on_encoder(ENCODER_TRACK[0], 99)
    assert sample.variation_every == MAX_VARIATION_EVERY


def test_a_pad_adds_a_bar_the_variation_plays_on(tmp_path):
    app, sample = rig(tmp_path)
    app.mode.on_pad(app.pad_of_bar(9), True, 127)
    assert 9 in sample.variation_bars
    assert sample.variation_every == DEFAULT_PASSES

    app.mode.on_pad(app.pad_of_bar(9), True, 127)
    assert 9 not in sample.variation_bars


def test_a_pad_on_a_bar_that_always_plays_says_so(tmp_path):
    """One press must not mean two things depending on what is underneath."""
    app, sample = rig(tmp_path)
    app.mode.on_pad(app.pad_of_bar(0), True, 127)
    assert 0 not in sample.variation_bars
    assert "already plays" in app.message


def test_the_grid_separates_always_from_sometimes(tmp_path):
    app, sample = rig(tmp_path)
    sample.variation_bars = {1, 3}
    sample.variation_every = 4

    pads = [colors.OFF.index] * 64
    app.mode.render_pads(pads)
    assert pads[app.pad_of_bar(0)] == colors.GREEN.index
    assert pads[app.pad_of_bar(1)] == colors.BLUE_DIM.index
    assert pads[app.pad_of_bar(7)] == colors.OFF.index


def test_the_grid_flashes_only_on_the_pass_before(tmp_path, monkeypatch):
    """"About to change" and "eventually" were the same pixel before this."""
    import push2sampler.app as app_module

    app, sample = rig(tmp_path)
    sample.variation_bars = {1}
    sample.variation_every = 4

    def phases():
        seen = set()
        for now in (0.0, 0.25):
            monkeypatch.setattr(app_module.time, "monotonic", lambda now=now: now)
            pads = [colors.OFF.index] * 64
            app.mode.render_pads(pads)
            seen.add(pads[app.pad_of_bar(1)])
        return seen

    app.engine.pass_number = 1          # three passes away: steady
    assert phases() == {colors.BLUE_DIM.index}

    app.engine.pass_number = 3          # next pass: flashing
    assert phases() == {colors.BLUE_DIM.index, colors.AMBER.index}

    app.engine.pass_number = 4          # this pass: steady amber
    assert phases() == {colors.AMBER.index}


def test_the_page_says_how_far_off_the_change_is(tmp_path):
    app, sample = rig(tmp_path)
    sample.variation_bars = {1}
    sample.variation_every = 4

    app.engine.pass_number = 4
    assert "this pass" in "\n".join(app.mode.status_lines())
    app.engine.pass_number = 3
    assert "next pass" in "\n".join(app.mode.status_lines())
    app.engine.pass_number = 1
    assert "in 3 passes" in "\n".join(app.mode.status_lines())


def test_the_clear_button_empties_the_variation(tmp_path):
    app, sample = rig(tmp_path)
    sample.variation_bars = {1, 3}
    sample.variation_every = 4

    app.mode.on_button(CLEAR_BUTTON, True)
    assert sample.variation_bars == set()
    app.undo()
    assert sample.variation_bars == {1, 3}


def test_clearing_nothing_says_so(tmp_path):
    app, _sample = rig(tmp_path)
    app.mode.on_button(CLEAR_BUTTON, True)
    assert "no variation" in app.message


def test_setting_a_variation_is_one_undo_step(tmp_path):
    app, sample = rig(tmp_path)
    app.mode.on_encoder(ENCODER_TRACK[0], 3)
    app.mode.on_encoder(ENCODER_TRACK[1], 2)
    bars = set(sample.variation_bars)
    assert bars

    app.undo()
    assert sample.variation_bars != bars
    app.redo()
    assert sample.variation_bars == bars


def test_encoder_three_chooses_how_many_passes_to_freeze(tmp_path):
    app, _sample = rig(tmp_path)
    assert app.mode.passes == DEFAULT_PASSES
    app.mode.on_encoder(ENCODER_TRACK[2], -2)
    assert app.mode.passes == 2
    app.mode.on_encoder(ENCODER_TRACK[2], -99)
    assert app.mode.passes == 1
    app.mode.on_encoder(ENCODER_TRACK[2], 99)
    assert app.mode.passes == 8


def test_shift_and_record_freezes_the_number_of_passes_asked_for(tmp_path):
    """Which is a different question from how long the song takes to repeat.

    `passes_needed` answers "when does it come round"; a freeze answers "give
    me four times round", and those need not be the same number.
    """
    app, sample = rig(tmp_path)
    sample.variation_bars = {1}
    sample.variation_every = 4
    assert passes_needed(app.project) == 4

    app.mode.passes = 2
    app.shift = True
    app.mode.on_button(Btn.RECORD, True)
    assert app.bounce is not None
    assert app.bounce.passes == 2
    assert "freezing 2" in app.message


def test_an_ordinary_bounce_still_derives_its_own_length(tmp_path):
    app, sample = rig(tmp_path)
    sample.variation_bars = {1}
    sample.variation_every = 4
    assert app.start_bounce() is True
    assert app.bounce.passes == 4


def test_the_page_refuses_gracefully_on_an_unarranged_slot(tmp_path):
    app, sample = rig(tmp_path, bars=())
    app.mode.on_enter()
    assert "arrange the sample first" in app.message
    app.mode.on_encoder(ENCODER_TRACK[0], 3)
    assert sample.variation_bars == set()


def test_leaving_the_page_goes_back(tmp_path):
    from push2sampler.modes.sample import SampleMode

    app, _sample = rig(tmp_path)
    app.set_mode(SampleMode(app, 0))
    app.shift = True
    app.mode.on_button(Btn.CLIP, True)
    app.shift = False
    assert app.mode.name == "living"
    app.mode.on_button(Btn.CLIP, True)
    assert app.mode.name == "sample"


# ==================================================== persistence
def test_a_variation_survives_a_save_and_load(tmp_path):
    proj, sample = project()
    sample.variation_bars = {1, 3, 5}
    sample.variation_every = 4
    proj.save(tmp_path)

    back = Project.load(tmp_path)[0]
    assert back.variation_bars == {1, 3, 5}
    assert back.variation_every == 4


def test_an_older_project_opens_without_a_variation(tmp_path):
    proj, _sample = project()
    proj.save(tmp_path)
    raw = json.loads((tmp_path / "project.json").read_text())
    for slot in raw["slots"]:
        slot.pop("variation_bars", None)
        slot.pop("variation_every", None)
    raw["version"] = 12
    (tmp_path / "project.json").write_text(json.dumps(raw))

    back = Project.load(tmp_path)[0]
    assert back.variation_bars == set()
    assert back.variation_every == 0


@pytest.mark.parametrize("junk", ["nonsense", None, 4, {}, [1, "x", -3, 9999]])
def test_junk_variation_bars_are_dropped(junk):
    loaded = _load_variation(junk)
    assert all(isinstance(bar, int) and bar >= 0 for bar in loaded)


@pytest.mark.parametrize("junk", ["nonsense", None, {}, -4, 99])
def test_a_junk_variation_divisor_is_clamped(junk):
    assert 0 <= _load_variation_every(junk) <= MAX_VARIATION_EVERY


def test_a_duplicated_slot_carries_its_variation():
    proj, sample = project()
    sample.variation_bars = {1, 3}
    sample.variation_every = 4
    copy = proj.copy_slot(0, 1)
    assert copy.variation_bars == {1, 3}
    assert copy.variation_every == 4
    # And it is a copy, not the same set.
    copy.variation_bars.add(5)
    assert 5 not in sample.variation_bars


def test_the_command_restores_both_halves():
    proj, sample = project()
    sample.variation_bars = {1}
    sample.variation_every = 2

    command = SetVariation(0, {3, 5}, 4, {1}, 2)
    command.apply(proj)
    assert sample.variation_bars == {3, 5} and sample.variation_every == 4
    command.revert(proj)
    assert sample.variation_bars == {1} and sample.variation_every == 2
