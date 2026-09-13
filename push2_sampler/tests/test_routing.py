"""NH-11: sending a slot to its own output pair.

Two things carry the feature, and both are failure modes rather than features:
a slot routed to a pair the device does not have must **fall back** rather than
go silent, and a routed slot must still light its pad and move its meter --
it is playing, it is just not coming out of the main outputs.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler.audio import Engine, ScheduledSample
from push2sampler.constants import (
    DISPLAY_ROW_BOTTOM,
    OUTPUT_PAIRS,
    Btn,
    pair_first_channel,
    pair_label,
)
from push2sampler.project import Project, Sample

SR = 8000
BPM = 120.0
FPBAR = int(SR * 2)


def engine(out_channels=4, song_bars=64):
    return Engine(samplerate=SR, blocksize=256, in_channels=1,
                  out_channels=out_channels, backend="offline", bpm=BPM,
                  song_bars=song_bars)


def tone(frames, value=0.5, channels=1):
    return np.full((frames, channels), value, dtype=np.float32)


def schedule(eng, entries, song_bars=64):
    rows = [[] for _ in range(song_bars)]
    rows[0] = list(entries)
    eng.set_schedule(rows)


def render(eng, frames, chunk=256):
    out = []
    done = 0
    while done < frames:
        n = min(chunk, frames - done)
        out.append(np.array(eng.process_offline(n)))
        done += n
    return np.concatenate(out, axis=0)


def peak(block, channel):
    return float(np.abs(block[:, channel]).max())


# ============================================================ the pair maths
def test_pair_zero_is_the_main_mix_not_channels_one_and_two():
    """The main path applies master gain and is what a bounce renders, so
    "route to pair 0" has to be the absence of routing."""
    assert pair_first_channel(0) is None
    assert pair_first_channel(1) == 2
    assert pair_first_channel(2) == 4
    assert pair_first_channel(3) == 6


def test_pair_labels_count_outputs_from_one():
    assert pair_label(0) == "main"
    assert pair_label(1) == "3/4"
    assert pair_label(2) == "5/6"
    assert pair_label(3) == "7/8"


# ============================================================ the engine
def test_a_routed_slot_is_silent_on_the_main_pair_and_present_on_its_own():
    eng = engine(out_channels=4)
    schedule(eng, [ScheduledSample(0, tone(FPBAR), channel=2)])
    eng.play()
    out = render(eng, 4000)

    assert peak(out, 0) < 1e-6      # main left
    assert peak(out, 1) < 1e-6      # main right
    assert peak(out, 2) > 0.3       # cue left
    assert peak(out, 3) > 0.3       # cue right


def test_an_unrouted_slot_is_on_the_main_pair_only():
    eng = engine(out_channels=4)
    schedule(eng, [ScheduledSample(0, tone(FPBAR))])
    eng.play()
    out = render(eng, 4000)
    assert peak(out, 0) > 0.3
    assert peak(out, 2) < 1e-6


def test_two_slots_can_go_to_different_pairs_at_once():
    eng = engine(out_channels=6)
    schedule(eng, [
        ScheduledSample(0, tone(FPBAR, 0.5)),
        ScheduledSample(1, tone(FPBAR, 0.5), channel=2),
        ScheduledSample(2, tone(FPBAR, 0.5), channel=4),
    ])
    eng.play()
    out = render(eng, 4000)
    for channel in (0, 2, 4):
        assert peak(out, channel) > 0.3, channel


def test_a_pair_the_device_does_not_have_falls_back_to_the_main_mix():
    """The spec's requirement, and the important one: a slot you cannot hear
    at all is harder to diagnose than a slot in the wrong socket."""
    eng = engine(out_channels=2)
    schedule(eng, [ScheduledSample(0, tone(FPBAR), channel=2)])
    eng.play()
    out = render(eng, 4000)
    assert out.shape[1] == 2
    assert peak(out, 0) > 0.3       # heard, on the main mix
    assert peak(out, 1) > 0.3


def test_a_routed_slot_still_counts_as_sounding():
    """Otherwise it vanishes from the library's amber pad and the mixer meter."""
    eng = engine(out_channels=4)
    schedule(eng, [ScheduledSample(3, tone(FPBAR), channel=2)])
    eng.play()
    render(eng, 2000)
    assert 3 in eng.sounding
    assert eng.slot_peaks[3] > 0.1


def test_a_routed_slot_still_flashes_in_master_playback():
    eng = engine(out_channels=4)
    schedule(eng, [ScheduledSample(5, tone(FPBAR), channel=2)])
    eng.play()
    eng.process_offline(256)
    assert eng.fired == (5,)


def test_a_stereo_take_keeps_its_stereo_when_routed():
    """The click is mono and duplicates across its pair; a stereo take must
    not be folded down on the way to a cue pair."""
    eng = engine(out_channels=4)
    stereo = np.zeros((FPBAR, 2), dtype=np.float32)
    stereo[:, 0] = 0.6
    stereo[:, 1] = 0.2
    schedule(eng, [ScheduledSample(0, stereo, channel=2)])
    eng.play()
    out = render(eng, 4000)
    assert peak(out, 2) == pytest.approx(0.6, abs=0.05)
    assert peak(out, 3) == pytest.approx(0.2, abs=0.05)


def test_a_mono_take_is_duplicated_across_its_pair():
    eng = engine(out_channels=4)
    schedule(eng, [ScheduledSample(0, tone(FPBAR, 0.4), channel=2)])
    eng.play()
    out = render(eng, 4000)
    assert peak(out, 2) == pytest.approx(peak(out, 3), abs=0.01)


def test_routing_survives_a_loop_wrap():
    """The looping mix path is a second place routing has to be honoured."""
    from push2sampler.constants import LOOP

    eng = engine(out_channels=4)
    schedule(eng, [ScheduledSample(0, tone(300, 0.5), play_mode=LOOP, channel=2)])
    eng.play()
    out = render(eng, 4000, chunk=1024)
    assert peak(out, 2) > 0.3
    assert peak(out, 0) < 1e-6


def test_a_routed_slot_is_not_in_the_bounce(tmp_path):
    """A cue pair is exactly what a bounce should not carry."""
    from push2sampler.render import bounce_to

    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR, 0.5), output=1)
    sample.set_trigger(0, True)
    project.install(0, sample)
    path = bounce_to(project, tmp_path / "mix.wav")

    from push2sampler import wavio

    data, _rate = wavio.read(path)
    assert float(np.abs(data).max()) < 1e-3


def test_an_unrouted_slot_is_in_the_bounce(tmp_path):
    from push2sampler.render import bounce_to

    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR, 0.5))
    sample.set_trigger(0, True)
    project.install(0, sample)
    path = bounce_to(project, tmp_path / "mix.wav")

    from push2sampler import wavio

    data, _rate = wavio.read(path)
    assert float(np.abs(data).max()) > 0.3


def test_a_routed_slot_is_still_in_its_own_stem():
    """A stem is what the slot played, not where you were listening to it."""
    from push2sampler.render import render_stems

    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR, 0.5), output=1)
    sample.set_trigger(0, True)
    project.install(0, sample)

    stems = render_stems(project)
    assert float(np.abs(stems[0]).max()) > 0.3


def test_a_muted_slot_is_in_neither_the_mix_nor_its_stem():
    """Documented in docs/reference.md, and the opposite of routing.

    Muting says the take does not belong in the song; routing says only that
    you are listening to it somewhere else.  So a mute silences the stem and
    a route does not -- the table in the Bouncing section says exactly this.
    """
    from push2sampler.render import render_song, render_stems

    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR, 0.5), enabled=False)
    sample.set_trigger(0, True)
    project.install(0, sample)

    assert float(np.abs(render_song(project)).max()) < 1e-6
    stems = render_stems(project)
    # The file is still written -- it is simply silence.
    assert 0 in stems
    assert float(np.abs(stems[0]).max()) < 1e-6


# ============================================================ the project
def test_the_schedule_carries_the_routing():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR), output=2)
    sample.set_trigger(0, True)
    project.install(0, sample)
    entry = project.build_schedule()[0][0]
    assert entry.channel == 4


def test_the_main_mix_is_scheduled_with_no_channel():
    project = Project(samplerate=SR, bpm=BPM)
    sample = Sample(slot=0, bars=1, audio=tone(FPBAR))
    sample.set_trigger(0, True)
    project.install(0, sample)
    assert project.build_schedule()[0][0].channel is None


def test_routing_survives_a_save_and_load(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR), output=3))
    project.save(tmp_path / "song")
    assert Project.load(tmp_path / "song", samplerate=SR)[0].output == 3


def test_junk_routing_in_a_project_file_defaults_to_the_main_mix(tmp_path):
    import json

    project = Project(samplerate=SR, bpm=BPM)
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR), output=1))
    project.save(tmp_path / "song")
    path = tmp_path / "song" / "project.json"
    payload = json.loads(path.read_text())
    payload["slots"][0]["output"] = "the blue one"
    path.write_text(json.dumps(payload))

    assert Project.load(tmp_path / "song", samplerate=SR)[0].output == 0


def test_an_out_of_range_pair_in_a_project_file_defaults_too(tmp_path):
    import json

    project = Project(samplerate=SR, bpm=BPM)
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR), output=1))
    project.save(tmp_path / "song")
    path = tmp_path / "song" / "project.json"
    payload = json.loads(path.read_text())
    payload["slots"][0]["output"] = OUTPUT_PAIRS + 5
    path.write_text(json.dumps(payload))
    assert Project.load(tmp_path / "song", samplerate=SR)[0].output == 0


def test_a_copy_carries_the_routing():
    project = Project(samplerate=SR, bpm=BPM)
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR), output=2))
    assert project.copy_slot(0, 1).output == 2


def test_a_swap_carries_the_routing():
    project = Project(samplerate=SR, bpm=BPM)
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR), output=1))
    project.install(1, Sample(slot=1, bars=1, audio=tone(FPBAR), output=3))
    project.swap_slots(0, 1)
    assert (project[0].output, project[1].output) == (3, 1)


# ============================================================ the mixer
@pytest.fixture
def rig(tmp_path):
    from push2sampler.app import App
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=SR, bpm=BPM)
    eng = engine(out_channels=4, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    app = App(push, eng, project, project_dir=tmp_path / "song", settings=settings)
    return app, push, eng, project


def pump(app):
    for event in app.push.poll_events():
        app.handle(event)
    app.mode.on_tick()
    app.render()


def open_mixer(rig, slots=(0,)):
    app, push, eng, project = rig
    for slot in slots:
        project.install(slot, Sample(slot=slot, bars=1, audio=tone(FPBAR),
                                     name=f"s{slot}"))
    app.open_mixer()
    pump(app)
    return app


def test_shift_and_a_strip_button_cycles_the_output_pair(rig):
    app, push, eng, project = rig
    open_mixer(rig)
    app.shift = True
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    app.shift = False
    assert project[0].output == 1
    assert "3/4" in app.message


def test_it_cycles_only_through_the_pairs_the_device_has(rig):
    """Offering a choice that would fall back to the main mix anyway is worse
    than not offering it."""
    app, push, eng, project = rig
    open_mixer(rig)
    assert eng.out_channels == 4          # main plus one cue pair
    for expected in (1, 0, 1, 0):
        app.shift = True
        push.press_button(DISPLAY_ROW_BOTTOM[0])
        pump(app)
        app.shift = False
        assert project[0].output == expected


def test_a_two_channel_device_says_there_is_nowhere_to_route_to(tmp_path):
    from push2sampler.app import App
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=SR, bpm=BPM)
    eng = engine(out_channels=2, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    app = App(push, eng, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR)))
    app.open_mixer()
    pump(app)

    app.shift = True
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    app.shift = False
    assert project[0].output == 0
    assert "nowhere to route" in app.message


def test_a_plain_strip_button_still_mutes(rig):
    app, push, eng, project = rig
    open_mixer(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    assert not project[0].enabled
    assert project[0].output == 0


def test_routing_is_one_undo_step(rig):
    app, push, eng, project = rig
    open_mixer(rig)
    app.shift = True
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    app.shift = False
    assert project[0].output == 1
    push.press_button(Btn.UNDO)
    pump(app)
    assert project[0].output == 0


def test_the_mixer_only_mentions_routing_when_something_is_routed(rig):
    app, push, eng, project = rig
    open_mixer(rig)
    assert not any(line.startswith("out ") for line in app.mode.status_lines())

    app.shift = True
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    app.shift = False
    lines = app.mode.status_lines()
    assert any(line.startswith("out ") and "1:3/4" in line for line in lines)


def test_the_mixer_flags_a_slot_routed_beyond_the_device(tmp_path):
    from push2sampler.app import App
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=SR, bpm=BPM)
    eng = engine(out_channels=2, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    app = App(push, eng, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    # A project made on a bigger interface, opened on a small one.
    project.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR), output=3))
    app.open_mixer()
    pump(app)
    lines = " ".join(app.mode.status_lines())
    assert "7/8!" in lines
    assert "fall back to the main mix" in lines
