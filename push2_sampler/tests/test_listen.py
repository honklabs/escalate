"""IN-02: what the instrument can say about a take, and how sure it is.

The spec asked for six roles. **Five is what the features support**, and
proving that was the first result of six rounds of prototyping, so the tests
here are as much about the *limits* as the successes: a snare classifying as a
"bright drum" is recorded as expected behaviour, because band energy and
envelope genuinely cannot tell it from a hat and a label the instrument cannot
defend is worse than a coarser one it can.

Every signal here has a known answer. Where the answer is a number -- a pitch,
a tempo -- the test names the number rather than checking that something came
back, because "it returned a float" is what let a note-naming helper be an
octave wrong through three rounds.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler import analysis
from push2sampler.analysis import (
    PITCH_FLOOR_HZ,
    ROLE_BASS,
    ROLE_BRIGHT_DRUM,
    ROLE_DRUM,
    ROLE_LOW_DRUM,
    ROLE_NOISE,
    ROLE_TONE,
    ROLES,
    TEMPO_MIN_CONFIDENCE,
    bands,
    centroid,
    describe,
    harmonicity,
    loudness,
    note_name,
    sustain,
    tempo,
)
from push2sampler.audio import Engine
from push2sampler.constants import DISPLAY_ROW_BOTTOM, Btn
from push2sampler.modes.info import InfoMode
from push2sampler.project import Project, Sample
from push2sampler.push2 import SimPush
from push2sampler.settings import Settings

SR = 48000


# ==================================================== material with known answers
def sine(hz: float, seconds: float = 2.0, sr: int = SR, level: float = 0.5):
    t = np.arange(int(sr * seconds)) / sr
    return (np.sin(2 * np.pi * hz * t) * level).astype(np.float32).reshape(-1, 1)


def chord(hz_list, seconds: float = 2.0, sr: int = SR):
    t = np.arange(int(sr * seconds)) / sr
    out = sum(np.sin(2 * np.pi * hz * t) for hz in hz_list) / len(hz_list)
    return (out * 0.5).astype(np.float32).reshape(-1, 1)


def kick(hits: int = 8, gap: float = 0.5, sr: int = SR):
    """A low struck sound: a downward pitch sweep with a fast decay."""
    out = np.zeros((int(sr * gap * hits), 1), dtype=np.float32)
    t = np.arange(int(sr * 0.15)) / sr
    body = (np.sin(2 * np.pi * (60 * np.exp(-t * 20) + 40) * t)
            * np.exp(-t * 12)).astype(np.float32)
    for i in range(hits):
        start = int(i * gap * sr)
        end = min(len(out), start + len(body))
        out[start:end, 0] += body[: end - start]
    return out


def hat(hits: int = 16, gap: float = 0.25, sr: int = SR):
    """A bright struck sound: high-passed noise with a very fast decay."""
    out = np.zeros((int(sr * gap * hits), 1), dtype=np.float32)
    t = np.arange(int(sr * 0.04)) / sr
    rng = np.random.default_rng(2)
    body = np.diff(rng.normal(0, 0.4, len(t)), prepend=0.0).astype(np.float32)
    body = body * np.exp(-t * 90).astype(np.float32)
    for i in range(hits):
        start = int(i * gap * sr)
        end = min(len(out), start + len(body))
        out[start:end, 0] += body[: end - start]
    return out


def snare(hits: int = 8, gap: float = 0.5, sr: int = SR):
    """Band-limited noise over a 200 Hz body, which is a snare's shape."""
    out = np.zeros((int(sr * gap * hits), 1), dtype=np.float32)
    t = np.arange(int(sr * 0.12)) / sr
    rng = np.random.default_rng(5)
    noise = np.convolve(np.diff(rng.normal(0, 0.25, len(t)), prepend=0.0),
                        np.ones(6) / 6, "same")
    body = ((noise * 1.5 + np.sin(2 * np.pi * 200 * t) * 0.5)
            * np.exp(-t * 22)).astype(np.float32)
    for i in range(hits):
        start = int(i * gap * sr)
        end = min(len(out), start + len(body))
        out[start:end, 0] += body[: end - start]
    return out


def click_loop(bpm: float = 120.0, per_beat: int = 2, bars: int = 2, sr: int = SR):
    """A loop with *crisp* attacks, which is what a tempo can be read from."""
    per_bar = int(sr * 60.0 / bpm * 4)
    out = np.zeros((per_bar * bars, 1), dtype=np.float32)
    t = np.arange(int(sr * 0.04)) / sr
    rng = np.random.default_rng(3)
    env = np.exp(-t * 300)
    step = per_bar // (4 * per_beat)
    for i in range(bars * 4 * per_beat):
        start = i * step
        body = (rng.normal(0, 0.5, len(t)) * env).astype(np.float32)
        end = min(len(out), start + len(body))
        out[start:end, 0] += body[: end - start]
    return out


def noise(seconds: float = 2.0, sr: int = SR):
    return np.random.default_rng(1).normal(
        0, 0.2, (int(sr * seconds), 1)
    ).astype(np.float32)


# ==================================================== note names
@pytest.mark.parametrize("hz,want", [
    (27.5, "A0"), (55.0, "A1"), (110.0, "A2"), (220.0, "A3"),
    (440.0, "A4"), (880.0, "A5"), (1760.0, "A6"),
    (261.63, "C4"), (329.63, "E4"), (493.88, "B4"),
])
def test_a_pitch_is_named_correctly(hz, want):
    """440 Hz came back as "A3" for three rounds.

    It was caught only because the test named the notes it expected instead of
    checking that a string came back -- which is the whole argument for writing
    the expectation down.
    """
    assert note_name(hz) == want


def test_no_pitch_is_no_name():
    assert note_name(0.0) == ""
    assert note_name(-5.0) == ""


# ==================================================== pitch
@pytest.mark.parametrize("hz", [55.0, 82.41, 110.0, 146.83, 220.0, 329.63,
                                440.0, 880.0])
def test_a_sine_is_pitched_within_two_percent(hz):
    """A semitone is 5.95%, so a note name needs better than that.

    Taking the band centre left the estimate up to 4% low; taking the nearest
    bin left it up to one bin out, which at 110 Hz is 10%.  Parabolic
    interpolation across the peak is what brings it inside a semitone.
    """
    f0, confidence = harmonicity(sine(hz), SR)
    assert abs(f0 - hz) / hz < 0.02, f0
    assert confidence > 0.3
    assert note_name(f0) == note_name(hz)


def test_a_pure_tone_is_more_harmonic_than_noise():
    """Scoring the *mean* harmonic strength inverted this.

    A sine has energy in harmonic 1 only, so its mean was max/8 -- it scored
    0.13 while white noise, with all eight bands equally full, scored 0.54.
    Tones became noise and noise became tones.
    """
    _f, tone_score = harmonicity(sine(440.0), SR)
    _f, noise_score = harmonicity(noise(), SR)
    assert tone_score > 0.5
    assert noise_score < 0.2
    assert tone_score > noise_score * 3


def test_a_chord_is_tonal_but_not_confidently_one_note():
    """A third of a chord's energy lies on any one harmonic series.

    That low score is *correct*, not a failure: a chord is not one note.  The
    response to an uncertain measurement is a low confidence, not a different
    label -- an earlier version flipped a chord to "noise".
    """
    f0, confidence = harmonicity(chord([220.0, 277.18, 329.63]), SR)
    assert 0.15 < confidence < 0.6, confidence
    assert describe(chord([220.0, 277.18, 329.63]), SR).role == ROLE_TONE


def test_the_pitch_floor_is_stated_rather_than_pretended():
    """Below about 60 Hz a short take has nothing to resolve.

    55 Hz was not resolvable at all in the onset detector's 1024-point window
    -- 47 Hz bins -- which is why pitch has its own longer one.
    """
    assert PITCH_FLOOR_HZ >= 50.0
    f0, _c = harmonicity(sine(30.0), SR)
    assert f0 == 0.0 or f0 >= PITCH_FLOOR_HZ


# ==================================================== roles
@pytest.mark.parametrize("name,buf,accept", [
    ("kick", kick(), {ROLE_LOW_DRUM}),
    ("hat", hat(), {ROLE_BRIGHT_DRUM}),
    # A snare is a noise burst with a body, and band energy cannot tell that
    # from a hat -- finding 1, and the reason the vocabulary is five not six.
    ("snare", snare(), {ROLE_BRIGHT_DRUM, ROLE_DRUM}),
    ("bass 110", sine(110.0), {ROLE_BASS}),
    ("tone 440", sine(440.0), {ROLE_TONE}),
    ("chord", chord([220.0, 277.18, 329.63]), {ROLE_TONE}),
    ("white noise", noise(), {ROLE_NOISE}),
])
def test_a_take_is_classified(name, buf, accept):
    reading = describe(buf, SR)
    assert reading.role in accept, f"{name}: {reading.role} ({reading.detail})"
    assert reading.role in ROLES
    assert 0.0 <= reading.confidence <= 1.0


def test_white_noise_is_not_a_hat():
    """It classified as one, 0.92 confident, before the envelope gate.

    Band energy alone cannot tell them apart -- both are mostly high.  What
    does is that a struck sound decays and noise does not.
    """
    assert describe(noise(), SR).role == ROLE_NOISE
    assert sustain(hat()) < 0.2
    assert sustain(noise()) > 0.3


def test_silence_says_nothing_at_all():
    reading = describe(np.zeros((SR, 1), dtype=np.float32), SR)
    assert reading.role is None
    assert reading.confidence == 0.0
    assert reading.suggested_name == ""
    assert reading.detail == "silent"


@pytest.mark.parametrize("buf", [
    None,
    np.zeros((0, 1), dtype=np.float32),
    np.zeros((1, 1), dtype=np.float32),
    np.zeros((10, 2), dtype=np.float32),
])
def test_a_degenerate_buffer_is_described_rather_than_raising(buf):
    """This runs behind a button press, so it has to answer, not throw."""
    reading = describe(buf, SR)
    assert reading.role is None


def test_a_bass_and_a_tone_are_told_apart_by_pitch():
    assert describe(sine(80.0), SR).role == ROLE_BASS
    assert describe(sine(600.0), SR).role == ROLE_TONE


# ==================================================== tempo
@pytest.mark.parametrize("bpm", [90.0, 120.0, 140.0, 170.0])
@pytest.mark.parametrize("per_beat", [1, 2, 4])
def test_a_loop_built_at_a_tempo_reads_that_tempo(bpm, per_beat):
    """The plan's acceptance test: 120 BPM reads 120 +/- 2.

    With the session tempo as a reference, because tempo has an unresolvable
    octave ambiguity from onsets alone -- 90 BPM in eighths and 180 BPM in
    quarters are the same recording, and measured, the eighths read 180 at full
    confidence.  A sampler knows its own tempo; a general analyser does not.
    """
    buf = click_loop(bpm, per_beat)
    reading = describe(buf, SR, reference_bpm=bpm)
    assert reading.bpm_confidence > 0.5
    assert abs(reading.bpm - bpm) <= 2.0, reading.bpm


def test_without_a_reference_an_octave_is_still_a_fair_answer():
    """Documented, not silently wrong: the figure is an octave of the truth."""
    got = describe(click_loop(90.0, per_beat=2), SR).bpm
    assert any(abs(got - 90.0 * 2 ** n) <= 2.0 for n in (-1, 0, 1)), got


def test_smeared_attacks_report_no_tempo_rather_than_a_wrong_one():
    """A synthesised kick whose body sweeps for 150 ms reads 20-80 BPM out.

    Measured at minimum onset gaps of 30, 60 and 100 ms, it was wrong at all
    three, so a coarser gap is not the fix.  The confidence was honest
    throughout (0.00-0.24), and acting on it is: "no clear tempo" beats "about
    98 BPM" when the answer is 120.
    """
    reading = describe(kick(), SR)
    assert reading.bpm == 0.0
    assert reading.bpm_confidence < TEMPO_MIN_CONFIDENCE


def test_sustained_material_has_no_tempo_to_read():
    reading = describe(sine(440.0), SR)
    assert reading.bpm == 0.0
    assert reading.onsets == []


def test_too_few_onsets_is_not_a_tempo():
    assert tempo([0, 48_000], SR) == (0.0, 0.0)
    assert tempo([], SR) == (0.0, 0.0)


# ==================================================== the other readings
def test_brightness_orders_the_way_ears_do():
    assert centroid(sine(100.0), SR) < centroid(sine(1000.0), SR)
    assert centroid(sine(1000.0), SR) < centroid(hat(), SR)


def test_the_bands_sum_to_one_and_put_energy_where_it_is():
    low, mid, high = bands(sine(80.0), SR)
    assert low > 0.9 and abs(low + mid + high - 1.0) < 0.01
    low, mid, high = bands(hat(), SR)
    assert high > 0.9


def test_loudness_is_rms_and_peak():
    rms, peak = loudness(sine(440.0, level=0.5))
    assert peak == pytest.approx(0.5, abs=0.01)
    assert rms == pytest.approx(0.5 / np.sqrt(2), abs=0.01)
    assert loudness(np.zeros((0, 1), dtype=np.float32)) == (0.0, 0.0)


def test_density_is_hits_per_second():
    reading = describe(click_loop(120.0, per_beat=1), SR)
    # Two bars of quarter notes at 120 BPM is 8 hits in 4 seconds.
    assert reading.density == pytest.approx(2.0, abs=0.3)


def test_the_post_take_helpers_are_undisturbed():
    """analysis.py is shared with NH-08 and IN-01; neither may be broken."""
    audio = np.zeros((SR, 1), dtype=np.float32)
    audio[480:] = 0.5
    assert analysis.first_transient(audio, SR) == 480
    assert len(analysis.onsets(click_loop(120.0), SR)) > 4
    assert analysis.even_slices(800, 8)[1] == 100


# ==================================================== name suggestions
@pytest.mark.parametrize("buf,want", [
    (kick(), "kick"),
    (hat(), "hat"),
    (sine(110.0), "bass A2"),
    (sine(440.0), "tone A4"),
    (noise(), "noise"),
])
def test_a_name_is_suggested_from_what_was_heard(buf, want):
    assert describe(buf, SR).suggested_name == want


def test_a_suggestion_is_generic_about_everything_but_the_pitch():
    """The measurements know it is a low struck thing, not that it is an 808.

    The note is the exception because the note is the one specific thing that
    was actually measured.
    """
    assert describe(kick(), SR).suggested_name == "kick"
    assert describe(sine(220.0), SR).suggested_name == "tone A3"


# ==================================================== the page
RIG_SR = 48000


@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=RIG_SR, bpm=120.0)
    project.install(0, Sample(slot=0, bars=2, audio=kick(), name="S01"))
    project.install(1, Sample(slot=1, bars=2, audio=sine(440.0, 4.0), name="S02"))
    push = SimPush()
    push.open()
    engine = Engine(samplerate=RIG_SR, blocksize=256, in_channels=1,
                    out_channels=2, backend="offline", bpm=120.0,
                    song_bars=project.song_bars)
    from push2sampler.app import App

    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


def pump(rig):
    app, push = rig[0], rig[1]
    for event in push.poll_events():
        app.handle(event)


def open_info(rig, slot=0):
    app, push = rig[0], rig[1]
    app.goto_sample(slot)
    push.press_button(Btn.LAYOUT)
    pump(rig)
    return app.mode


def test_layout_on_a_sample_page_opens_the_info_page(rig):
    mode = open_info(rig)
    assert isinstance(mode, InfoMode)
    assert mode.title == "ABOUT 1"


def test_layout_does_nothing_on_an_empty_slot(rig):
    app, push, _engine, project = rig
    app.goto_library()
    push.press_button(Btn.LAYOUT)
    pump(rig)
    assert app.mode.name == "library"


def test_the_page_reports_what_it_heard(rig):
    mode = open_info(rig)
    text = " ".join(mode.status_lines())
    assert "low drum" in text
    assert "peak" in text


def test_a_pitched_take_gets_its_note_on_the_page(rig):
    mode = open_info(rig, slot=1)
    text = " ".join(mode.status_lines())
    assert "A4" in text
    assert "tone" in text


def test_every_reading_carries_its_confidence(rig):
    """The whole design: a guess stated confidently is worse than no guess."""
    mode = open_info(rig)
    text = " ".join(mode.status_lines())
    assert "measurement, not a fact" in text
    # A parenthesised confidence next to the role.
    assert "(" in mode._sound_line(mode.described)


def test_a_weak_reading_says_it_is_unsure(rig):
    from push2sampler.modes.info import UNSURE

    mode = open_info(rig)
    strong = analysis.Description(role="tone", confidence=0.9, detail="440 Hz",
                                  note="A4", f0=440.0, pitch_confidence=0.9)
    weak = analysis.Description(role="tone", confidence=0.1, detail="440 Hz",
                                note="A4", f0=440.0, pitch_confidence=0.1)
    assert "not sure" not in mode._sound_line(strong)
    assert "not sure" in mode._sound_line(weak)
    assert UNSURE > 0.0


def test_no_tempo_is_said_plainly(rig):
    mode = open_info(rig, slot=1)
    assert "no tempo to read" in " ".join(mode.status_lines())


def test_button_one_accepts_the_suggested_name(rig):
    app, push, _engine, project = rig
    open_info(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    assert project[0].name == "kick"
    assert "kick" in app.message


def test_accepting_a_name_is_one_undo_step(rig):
    app, push, _engine, project = rig
    open_info(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    app.undo()
    assert project[0].name == "S01"


def test_a_second_suggestion_of_the_same_name_is_suffixed(rig):
    """Two kicks in a library are normal; two slots called "kick" are not."""
    app, push, _engine, project = rig
    project.install(2, Sample(slot=2, bars=2, audio=kick(), name="kick"))
    open_info(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    assert project[0].name == "kick 2"


def test_accepting_the_name_it_already_has_says_so(rig):
    app, push, _engine, project = rig
    open_info(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(rig)
    assert "already called" in app.message
    assert project[0].name == "kick"


def test_nothing_else_on_the_page_changes_the_project(rig):
    """A page whose job is to tell you what it thinks must not act on it."""
    app, push, _engine, project = rig
    open_info(rig)
    before = (project[0].name, set(project[0].triggers), project[0].gain)
    for pad in (0, 31, 63):
        push.press_pad(pad)
        pump(rig)
    for cc in DISPLAY_ROW_BOTTOM[1:]:
        push.press_button(cc)
        pump(rig)
    assert (project[0].name, set(project[0].triggers), project[0].gain) == before


def test_a_pad_auditions_the_take(rig):
    app, push, engine, _project = rig
    open_info(rig)
    push.press_pad(20)
    pump(rig)
    # The preview is a queued command; rendering a block applies it and the
    # voice appears.  Asserting the queue is non-empty would pass on an empty
    # queue too, which is how a test ends up checking nothing.
    engine.process_offline(256)
    assert any(v.slot == 0 for v in engine._voices)


def test_the_grid_is_a_spectrogram_with_low_at_the_bottom(rig):
    """A kick belongs along the bottom; a hat along the top."""
    app, _push, _engine, project = rig
    mode = open_info(rig)
    cells = mode._spectrogram()
    bottom = sum(cells[56:64])
    top = sum(cells[0:8])
    assert bottom > top, (bottom, top)

    project.install(0, Sample(slot=0, bars=2, audio=hat(), name="h"))
    app.pop_mode()
    mode = open_info(rig)
    cells = mode._spectrogram()
    assert sum(cells[0:8]) > sum(cells[56:64])


def test_the_spectrogram_is_computed_once(rig):
    """An FFT of the whole take is not a per-frame cost."""
    app, _push, _engine, _project = rig
    mode = open_info(rig)
    first = mode._spectrogram()
    assert mode._spectrogram() is first
    for _ in range(5):
        mode.render_pads([0] * 64)
    assert mode._spectrogram() is first


def test_the_page_survives_the_slot_emptying_under_it(rig):
    app, _push, _engine, project = rig
    mode = open_info(rig)
    project.install(0, None)
    assert mode.status_lines()[0] == "ABOUT"
    mode.render_pads([0] * 64)          # must not raise


def test_layout_closes_the_page(rig):
    app, push, _engine, _project = rig
    open_info(rig)
    push.press_button(Btn.LAYOUT)
    pump(rig)
    assert app.mode.name == "sample"
