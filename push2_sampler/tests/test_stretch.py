"""NH-09: making a take fit a tempo it was not recorded at.

The plan's tests are here with its assertions. The rest are the five prototype
rounds, written down so the numbers cannot move quietly.

**The first version ended every stretch with a click.** Running out of input
left the tail silent: a 2-second tone stretched to 1.5x finished with 615 frames
of nothing and a 0.488 step into them, against a source whose largest
sample-to-sample step was 0.063. Clamping the read position fixed it, and
``test_a_stretch_does_not_end_in_a_click`` is the measurement.

**Normalised cross-correlation was measured and rejected.** The textbook choice
for the similarity search, it ran 4x slower and scored *worse* on a chord
(0.953 against 0.957). A plain dot product it is.

**The search had to be vectorised, not merely optimised.** As a Python loop over
candidates a 30-second take took 2.2 seconds; as one `np.correlate` call it
takes 0.33, and the two are bit-for-bit identical.

**And the plan's own assertion is only valid for one note.** "The dominant
frequency is unchanged" is right for a tone and meaningless for a chord, whose
three near-equal partials make `argmax` pick whichever is momentarily loudest --
so the chord is checked partial by partial instead.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from push2sampler import dsp
from push2sampler.dsp import (
    RATE_MAX,
    RATE_MIN,
    STRETCH_MODES,
    STRETCH_OFF,
    STRETCH_RESAMPLE,
    STRETCH_WSOLA,
    StretchJob,
    resample,
    stretch,
    stretch_rate,
    suggested_mode,
    wsola,
)
from push2sampler.project import Project, _load_stretch_mode

SR = 22050
RATES = (0.5, 0.75, 1.25, 1.5, 2.0)


def tone(freq=440.0, seconds=2.0, channels=1):
    t = np.arange(int(seconds * SR)) / SR
    mono = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


def chord(freqs=(261.6, 329.6, 392.0), seconds=2.0):
    t = np.arange(int(seconds * SR)) / SR
    out = sum(0.3 * np.sin(2 * np.pi * f * t) for f in freqs)
    return (out / np.abs(out).max()).astype(np.float32)[:, None]


def drums(seconds=2.0, seed=2):
    rng = np.random.default_rng(seed)
    frames = int(seconds * SR)
    out = np.zeros(frames)
    for start in range(0, frames, int(0.25 * SR)):
        d = np.arange(min(int(0.2 * SR), frames - start)) / SR
        out[start:start + len(d)] += np.sin(
            2 * np.pi * (80 - 30 * d / 0.2) * d) * np.exp(-d * 20)
    for start in range(int(0.125 * SR), frames, int(0.25 * SR)):
        d = np.arange(min(int(0.05 * SR), frames - start)) / SR
        out[start:start + len(d)] += rng.normal(0, 1, len(d)) * np.exp(-d * 80) * 0.4
    return (out / np.abs(out).max()).astype(np.float32)[:, None]


def dominant(buf):
    mono = buf[:, 0] if buf.ndim > 1 else buf
    n = min(len(mono), 8192)
    spectrum = np.abs(np.fft.rfft(mono[:n] * np.hanning(n)))
    return float(np.fft.rfftfreq(n, 1.0 / SR)[int(np.argmax(spectrum))])


def worst_step(buf):
    mono = buf[:, 0] if buf.ndim > 1 else buf
    return float(np.abs(np.diff(mono)).max()) if mono.size > 1 else 0.0


def partial_strength(buf, freq, span=0.03):
    """How much energy sits within `span` of `freq`, relative to the loudest."""
    mono = buf[:, 0] if buf.ndim > 1 else buf
    n = 16384
    spectrum = np.abs(np.fft.rfft(mono[:n] * np.hanning(min(n, len(mono)))[:len(mono[:n])],
                                  n=n))
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    band = (freqs > freq * (1 - span)) & (freqs < freq * (1 + span))
    return float(spectrum[band].max() / spectrum.max())


# ==================================================== the plan's tests
@pytest.mark.parametrize("rate", RATES)
def test_wsola_changes_the_length_and_not_the_pitch(rate):
    """The plan's assertion, for the case it is valid in: one note."""
    src = tone(440.0)
    out = wsola(src, rate)
    assert out.shape[0] == int(round(src.shape[0] * rate))
    assert dominant(out) == pytest.approx(dominant(src), abs=2.0)


@pytest.mark.parametrize("rate", RATES)
def test_resample_changes_the_length_and_the_pitch_with_it(rate):
    """The plan's other assertion: `resample` scales the pitch by 1/rate."""
    src = tone(440.0)
    out = resample(src, int(round(src.shape[0] * rate)))
    assert out.shape[0] == int(round(src.shape[0] * rate))
    assert dominant(out) == pytest.approx(dominant(src) / rate, rel=0.03)


def test_the_cache_is_invalidated_by_a_tempo_change():
    """The plan's test."""
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_WSOLA

    project.bpm = 90.0
    assert project.pending_stretches() == [sample]
    StretchJob(project).step()
    assert project.pending_stretches() == []
    first = project.playable_audio(sample)

    project.bpm = 150.0
    assert project.pending_stretches() == [sample]   # the old one no longer fits
    assert project.playable_audio(sample) is not first


def test_the_callback_never_sees_a_half_written_buffer():
    """The plan's concern, met by there being nothing to half-write.

    A stretch is computed into a fresh array and *then* rebound in one
    assignment, and the schedule the engine plays is rebuilt once the whole job
    has finished -- so what the engine holds is always some complete array, and
    never one being filled in.
    """
    project = Project(samplerate=SR, bpm=120.0)
    for slot in range(3):
        sample = project.put(slot, tone(220.0 * (slot + 1)), 2)
        sample.stretch_mode = STRETCH_WSOLA
        sample.set_trigger(0, True)
    project.bpm = 90.0

    job = StretchJob(project)
    seen = []
    while True:
        # Whatever the schedule says mid-job, every buffer in it is a whole
        # array of the length it claims.
        for entries in project.build_schedule():
            for entry in entries:
                seen.append(entry.buf)
                assert entry.buf.ndim == 2
                assert entry.buf.shape[0] > 0
                assert np.isfinite(entry.buf).all()
        if not job.step():
            break
    assert seen        # the schedule was inspected at least once mid-job


# ==================================================== the click
@pytest.mark.parametrize("rate", RATES)
def test_a_stretch_does_not_end_in_a_click(rate):
    """The bug the tail clamp exists for, as a measurement.

    Before it, a tone stretched to 1.5x ended in 615 silent frames with a 0.488
    step into them, against a source whose worst step is 0.063.
    """
    src = tone(440.0)
    out = wsola(src, rate)
    assert worst_step(out) == pytest.approx(worst_step(src), abs=0.01)
    # And the tail is not silence.
    tail = out[-256:, 0]
    assert float(np.abs(tail).max()) > 0.1


def test_the_whole_output_is_filled():
    """No silent gap anywhere, not only at the end."""
    out = wsola(tone(440.0), 1.5)[:, 0]
    whole = (out.size // 512) * 512
    chunks = out[:whole].reshape(-1, 512)
    quietest = float(np.abs(chunks).max(axis=1).min())
    assert quietest > 0.1


# ==================================================== what survives
@pytest.mark.parametrize("rate", RATES)
def test_a_chord_keeps_all_of_its_partials(rate):
    """The plan's assertion restated for polyphony.

    `argmax` on a chord picks whichever of three near-equal partials is
    momentarily loudest, so "the dominant frequency" says nothing.  Each partial
    separately does.
    """
    src = chord()
    out = wsola(src, rate)
    for freq in (261.6, 329.6, 392.0):
        assert partial_strength(out, freq) > 0.8, freq


def test_percussion_is_the_case_wsola_is_worst_at():
    """Why `suggested_mode` sends drums to `resample`.

    Not a preference: a stretched drum loop's spectrum survives measurably less
    well than a chord's, because a transient is exactly what overlap-add smears.
    """
    def similarity(src, out):
        n = 8192
        a = np.abs(np.fft.rfft(src[:n, 0], n=n))
        b = np.abs(np.fft.rfft(out[:n, 0], n=n))
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    tonal = similarity(chord(), wsola(chord(), 1.5))
    percussive = similarity(drums(), wsola(drums(), 1.5))
    assert tonal > 0.9
    assert percussive < tonal


# ==================================================== stereo
def test_the_stereo_image_survives_a_stretch():
    """The search runs on the channel sum, so both channels move together.

    Searching per channel would pick different offsets left and right, which
    smears the image -- a worse artefact than the one being fixed.
    """
    src = tone(440.0, channels=2)
    out = wsola(src, 1.5)
    assert out.shape[1] == 2
    assert float(np.abs(out[:, 0] - out[:, 1]).max()) == 0.0


def test_resample_keeps_every_channel_in_step():
    src = tone(440.0, channels=2)
    out = resample(src, src.shape[0] * 2)
    assert float(np.abs(out[:, 0] - out[:, 1]).max()) == 0.0


def test_a_one_dimensional_buffer_comes_back_two_dimensional():
    """Every buffer in this program is (frames, channels)."""
    flat = tone()[:, 0]
    assert wsola(flat, 1.5).ndim == 2
    assert resample(flat, 100).ndim == 2
    assert stretch(flat, 1.5, STRETCH_WSOLA).ndim == 2


# ==================================================== the refusals
@pytest.mark.parametrize("mode", [STRETCH_OFF, "nonsense", "", None])
def test_a_mode_that_is_not_a_stretch_returns_the_input_untouched(mode):
    src = tone()
    assert stretch(src, 1.5, mode) is src


@pytest.mark.parametrize("rate", [1.0, 1.0 + 1e-9, float("nan"), float("inf"),
                                  RATE_MIN / 2, RATE_MAX * 2, 0.0, -1.0])
def test_a_rate_not_worth_stretching_returns_the_input_untouched(rate):
    """Including the out-of-range ones: past those the result is not the take.

    The library's off-grid warning is the better answer there, and it is still
    shown, because `mismatched` only stops flagging a rate stretching can do.
    """
    src = tone()
    assert stretch(src, rate, STRETCH_WSOLA) is src


def test_a_take_too_short_to_overlap_add_is_resampled_instead():
    """Below two windows there is nothing to overlap; the length still matters.

    At that size -- under 100 ms -- the pitch move is not audible anyway.
    """
    short = tone(440.0, seconds=0.05)
    out = wsola(short, 1.5)
    assert out.shape[0] == int(round(short.shape[0] * 1.5))


def test_resample_to_nothing_is_empty_rather_than_an_error():
    assert resample(tone(), 0).shape == (0, 1)
    assert resample(np.zeros((0, 2), dtype=np.float32), 10).shape == (10, 2)


# ==================================================== the rate
@pytest.mark.parametrize("source,target,expected", [
    (120.0, 90.0, 4 / 3),          # slower song, longer take
    (120.0, 240.0, 0.5),
    (120.0, 120.0, 1.0),
])
def test_the_rate_is_the_ratio_of_the_two_tempos(source, target, expected):
    assert stretch_rate(source, target) == pytest.approx(expected)


@pytest.mark.parametrize("source,target", [(0, 120), (120, 0), ("x", 120),
                                           (None, 120), (-10, 120)])
def test_a_missing_tempo_means_nothing_to_do(source, target):
    assert stretch_rate(source, target) == 0.0


# ==================================================== the suggestion
@pytest.mark.parametrize("role", ["bass", "tone"])
def test_pitched_material_is_offered_the_pitch_preserving_stretch(role):
    assert suggested_mode(role) == STRETCH_WSOLA


@pytest.mark.parametrize("role", ["low drum", "bright drum", "drum", "noise"])
def test_percussion_is_offered_resample(role):
    """A break played faster *is* pitched up, and that is a sound."""
    assert suggested_mode(role) == STRETCH_RESAMPLE


def test_nothing_heard_means_no_suggestion():
    assert suggested_mode(None) == STRETCH_OFF
    assert suggested_mode("") == STRETCH_OFF


# ==================================================== the project
def test_a_stretching_slot_is_not_flagged_off_grid():
    """The length is being handled, so the yellow pad would be a lie."""
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    project.bpm = 90.0
    assert project.mismatched(sample) is True      # as before the feature

    sample.stretch_mode = STRETCH_WSOLA
    assert project.mismatched(sample) is False


def test_a_tempo_change_too_large_to_stretch_is_still_flagged():
    """Because then it genuinely is not handled."""
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_WSOLA
    project.bpm = 20.0                              # rate 6, past RATE_MAX
    assert project.stretch_rate_for(sample) > RATE_MAX
    assert project.mismatched(sample) is True


def test_playable_audio_falls_back_rather_than_blocking():
    """A tempo change is audible at the old length and settles to the new one.

    Computing on demand here would put a 400 ms pass inside whatever asked --
    possibly the thing building a schedule.  Playing something beats playing
    nothing.
    """
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_WSOLA
    project.bpm = 90.0

    before = project.playable_audio(sample)
    assert before is sample.effective_audio(SR)     # not stretched yet
    StretchJob(project).step()
    after = project.playable_audio(sample)
    assert after.shape[0] > before.shape[0]


def test_the_schedule_carries_the_stretched_audio():
    project = Project(samplerate=SR, bpm=120.0)
    project.pages = 1
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_WSOLA
    sample.set_trigger(0, True)
    project.bpm = 90.0
    while StretchJob(project).step():
        pass

    entry = project.build_schedule()[0][0]
    assert entry.buf.shape[0] == int(round(sample.raw_frames * 4 / 3))


def test_an_off_slot_is_never_stretched():
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    project.bpm = 90.0
    assert project.pending_stretches() == []
    assert project.playable_audio(sample) is sample.effective_audio(SR)


def test_an_edit_invalidates_the_stretch():
    """`stretch_key` is the edited audio, so an edit is a new thing to stretch."""
    from push2sampler.edits import Edits

    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_WSOLA
    project.bpm = 90.0
    StretchJob(project).step()
    assert project.pending_stretches() == []

    sample.set_edits(Edits(trim_start_ms=100.0))
    assert project.pending_stretches() == [sample]


# ==================================================== the job
def test_the_job_does_one_slot_per_step():
    """So a frame's work is bounded by the longest single take."""
    project = Project(samplerate=SR, bpm=120.0)
    for slot in range(4):
        sample = project.put(slot, tone(220.0), 2)
        sample.stretch_mode = STRETCH_WSOLA
    project.bpm = 90.0

    job = StretchJob(project)
    assert job.total == 4
    for expected in (1, 2, 3, 4):
        job.step()
        assert job.finished == expected
    assert job.done


def test_a_job_with_nothing_to_do_is_done_immediately():
    """Which is what lets every tempo change simply ask."""
    project = Project(samplerate=SR, bpm=120.0)
    project.put(0, tone(220.0), 2)
    job = StretchJob(project)
    assert job.done is True
    assert job.total == 0
    assert job.progress == 1.0
    assert job.step() is False


def test_the_job_survives_the_slot_going_away_under_it():
    """A delete or a re-record mid-job must not crash it."""
    project = Project(samplerate=SR, bpm=120.0)
    for slot in range(3):
        sample = project.put(slot, tone(220.0), 2)
        sample.stretch_mode = STRETCH_WSOLA
    project.bpm = 90.0

    job = StretchJob(project)
    job.step()
    project.delete(1)
    project.delete(2)
    while job.step():
        pass
    assert job.done


def test_progress_runs_from_zero_to_one():
    project = Project(samplerate=SR, bpm=120.0)
    for slot in range(2):
        sample = project.put(slot, tone(220.0), 2)
        sample.stretch_mode = STRETCH_WSOLA
    project.bpm = 90.0
    job = StretchJob(project)
    assert job.progress == 0.0
    job.step()
    assert job.progress == 0.5
    job.step()
    assert job.progress == 1.0


# ==================================================== persistence
def test_the_stretch_mode_survives_a_save_and_load(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_RESAMPLE
    project.save(tmp_path)

    back = Project.load(tmp_path)[0]
    assert back.stretch_mode == STRETCH_RESAMPLE


def test_an_older_project_opens_with_stretching_off(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    project.put(0, tone(220.0), 2)
    project.save(tmp_path)
    raw = json.loads((tmp_path / "project.json").read_text())
    for slot in raw["slots"]:
        slot.pop("stretch_mode", None)
    raw["version"] = 11
    (tmp_path / "project.json").write_text(json.dumps(raw))

    back = Project.load(tmp_path)[0]
    assert back.stretch_mode == STRETCH_OFF


@pytest.mark.parametrize("junk", ["nonsense", "", None, 3, {}, True])
def test_a_junk_stretch_mode_becomes_off(junk):
    assert _load_stretch_mode(junk) == STRETCH_OFF


def test_a_duplicated_slot_carries_its_stretch_mode():
    project = Project(samplerate=SR, bpm=120.0)
    sample = project.put(0, tone(220.0), 2)
    sample.stretch_mode = STRETCH_WSOLA
    assert project.copy_slot(0, 1).stretch_mode == STRETCH_WSOLA


# ==================================================== the surface
def rig(tmp_path, bpm=120.0):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=SR, bpm=bpm)
    project.pages = 1
    bass = project.put(0, tone(110.0), 2)
    bass.name = "bass"
    bass.set_trigger(0, True)
    break_ = project.put(1, drums(), 2)
    break_.name = "break"
    break_.set_trigger(0, True)
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=bpm, song_bars=project.song_bars)
    return App(push, engine, project, project_dir=tmp_path / "song",
               settings=Settings(path=tmp_path / "settings.json"))


def open_sample(app, slot=0):
    from push2sampler.modes.sample import SampleMode

    app.set_mode(SampleMode(app, slot))
    return app.mode


def test_the_button_offers_the_mode_the_material_wants_first(tmp_path):
    """`IN-02` already knows whether this is a drum; it decides which comes first."""
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    open_sample(app, 0).on_button(STRETCH_BUTTON, True)
    assert app.project[0].stretch_mode == STRETCH_WSOLA      # a bass tone

    open_sample(app, 1).on_button(STRETCH_BUTTON, True)
    assert app.project[1].stretch_mode == STRETCH_RESAMPLE   # a drum loop


def test_the_button_then_walks_all_three_modes(tmp_path):
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    mode = open_sample(app, 0)
    seen = []
    for _ in range(4):
        mode.on_button(STRETCH_BUTTON, True)
        seen.append(app.project[0].stretch_mode)
    # off -> the likely mode -> the other -> off.  All three are reachable,
    # which walking the plain list did not manage: the suggestion sat in the
    # list twice and a tonal slot could never get to `resample`.
    assert set(seen) == set(STRETCH_MODES)
    assert seen[0] == STRETCH_WSOLA     # a bass tone: pitch held first
    assert seen[1] == STRETCH_RESAMPLE
    assert seen[2] == STRETCH_OFF
    assert seen[3] == seen[0]           # and it comes back round


def test_setting_the_mode_is_one_undo_step(tmp_path):
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    open_sample(app, 0).on_button(STRETCH_BUTTON, True)
    assert app.project[0].stretch_mode != STRETCH_OFF
    app.undo()
    assert app.project[0].stretch_mode == STRETCH_OFF


def test_a_tempo_change_starts_the_job_by_itself(tmp_path):
    """Every path that can change a stretch ends at `rebuild_schedule`."""
    from push2sampler.history import SetBpm
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    for slot in (0, 1):
        open_sample(app, slot).on_button(STRETCH_BUTTON, True)
    assert app.stretching is None            # nothing to do at this tempo

    app.engine.set_bpm(90.0)
    app.do(SetBpm(90.0, 120.0))
    assert app.stretching is not None
    assert app.stretching.total == 2

    while app.stretching is not None:
        app._step_stretch()
    assert "stretched 2" in app.message
    for slot in (0, 1):
        sample = app.project[slot]
        assert app.project.playable_audio(sample).shape[0] > sample.frames


def test_turning_stretching_on_at_the_wrong_tempo_starts_the_job(tmp_path):
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path, bpm=120.0)
    app.project.bpm = 90.0
    app.engine.set_bpm(90.0)
    open_sample(app, 0).on_button(STRETCH_BUTTON, True)
    assert app.stretching is not None


def test_the_page_says_what_the_tempo_is_doing_to_the_take(tmp_path):
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    mode = open_sample(app, 0)
    assert "tempo:" not in "\n".join(mode.status_lines())   # it fits; say nothing

    app.project.bpm = 90.0
    app.engine.set_bpm(90.0)
    lines = "\n".join(mode.status_lines())
    assert "recorded at 120 BPM" in lines                   # off, and off-grid
    assert "button 6" in lines

    mode.on_button(STRETCH_BUTTON, True)
    lines = "\n".join(mode.status_lines())
    assert "x1.333" in lines
    assert "90 BPM" in lines


def test_the_button_is_lit_only_when_stretching_is_on(tmp_path):
    from push2sampler.constants import BTN_DIM
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    mode = open_sample(app, 0)
    buttons: dict = {}
    mode.render_buttons(buttons)
    assert buttons[STRETCH_BUTTON] == BTN_DIM

    mode.on_button(STRETCH_BUTTON, True)
    buttons = {}
    mode.render_buttons(buttons)
    assert buttons[STRETCH_BUTTON] > BTN_DIM


def test_the_role_is_measured_once_per_take(tmp_path):
    """An FFT per press would be fine; an FFT per frame would not."""
    import push2sampler.modes.sample as page
    from push2sampler.modes.sample import STRETCH_BUTTON

    app = rig(tmp_path)
    mode = open_sample(app, 0)
    described = []
    real_describe = page.describe

    def counted(buf, samplerate, **kwargs):
        described.append(1)
        return real_describe(buf, samplerate, **kwargs)

    page.describe = counted
    try:
        for _ in range(6):
            mode.on_button(STRETCH_BUTTON, True)
    finally:
        page.describe = real_describe
    assert len(described) == 1
