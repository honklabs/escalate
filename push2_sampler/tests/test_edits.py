"""Non-destructive edits: trim, fades, pitch, reverse, normalise."""

import numpy as np
import pytest

from push2sampler.edits import (
    DEFAULT_EDITS,
    MIN_FRAMES,
    NORMALIZE_PEAK,
    Edits,
    pitch_ratio,
    render_edits,
)

SR = 8000


def ramp(frames=8000, channels=1):
    """0.0 rising to 1.0, so any reordering or trimming is visible."""
    return np.tile(np.linspace(0.0, 1.0, frames, dtype=np.float32)[:, None], (1, channels))


def flat(frames=8000, value=0.5):
    return np.full((frames, 1), value, dtype=np.float32)


def test_no_edits_returns_the_very_same_array():
    audio = flat()
    assert render_edits(audio, SR, DEFAULT_EDITS) is audio
    assert DEFAULT_EDITS.is_default


def test_trimming_cuts_from_each_end():
    audio = ramp(SR)  # one second
    out = render_edits(audio, SR, Edits(trim_start_ms=250, trim_end_ms=250))
    assert out.shape[0] == SR // 2
    assert out[0, 0] == pytest.approx(0.25, abs=0.01)
    assert out[-1, 0] == pytest.approx(0.75, abs=0.01)


def test_trims_cannot_eat_the_whole_take():
    audio = flat(1000)
    out = render_edits(audio, SR, Edits(trim_start_ms=5000, trim_end_ms=5000))
    assert out.shape[0] >= MIN_FRAMES


def test_reverse_turns_the_take_around():
    out = render_edits(ramp(1000), SR, Edits(reverse=True))
    assert out[0, 0] == pytest.approx(1.0)
    assert out[-1, 0] == pytest.approx(0.0)


def test_pitching_up_shortens_the_take_by_the_right_ratio():
    audio = flat(SR)
    out = render_edits(audio, SR, Edits(pitch_semitones=12))
    assert pitch_ratio(12) == pytest.approx(2.0)
    assert out.shape[0] == pytest.approx(SR / 2, rel=0.01)


def test_pitching_down_lengthens_it():
    out = render_edits(flat(SR), SR, Edits(pitch_semitones=-12))
    assert out.shape[0] == pytest.approx(SR * 2, rel=0.01)


def test_an_octave_up_doubles_the_frequency():
    t = np.arange(SR, dtype=np.float32) / SR
    tone = np.sin(2 * np.pi * 200 * t).astype(np.float32)[:, None]
    out = render_edits(tone, SR, Edits(pitch_semitones=12))

    def dominant(signal):
        spectrum = np.abs(np.fft.rfft(signal[:, 0]))
        return np.fft.rfftfreq(signal.shape[0], 1 / SR)[spectrum.argmax()]

    assert dominant(tone) == pytest.approx(200, abs=5)
    assert dominant(out) == pytest.approx(400, abs=10)


def test_fades_start_and_end_at_silence():
    out = render_edits(flat(SR), SR, Edits(fade_in_ms=100, fade_out_ms=100))
    assert out[0, 0] == pytest.approx(0.0)
    assert out[-1, 0] < 0.01
    assert out[SR // 2, 0] == pytest.approx(0.5)  # untouched in the middle


def test_a_fade_longer_than_the_take_does_not_overrun():
    out = render_edits(flat(100), SR, Edits(fade_in_ms=9999))
    assert out.shape[0] == 100
    assert np.isfinite(out).all()


def test_normalise_lifts_a_quiet_take_to_just_under_full_scale():
    out = render_edits(flat(1000, 0.1), SR, Edits(normalize=True))
    assert float(np.abs(out).max()) == pytest.approx(NORMALIZE_PEAK, abs=0.001)


def test_normalise_leaves_silence_alone():
    out = render_edits(np.zeros((100, 1), dtype=np.float32), SR, Edits(normalize=True))
    assert np.all(out == 0.0)


def test_edits_compose_in_a_fixed_order():
    # Trim to the back half, reverse it, pitch up an octave, then fade.
    audio = ramp(SR)
    out = render_edits(
        audio,
        SR,
        Edits(trim_start_ms=500, reverse=True, pitch_semitones=12, fade_out_ms=10),
    )
    assert out.shape[0] == pytest.approx(SR / 4, rel=0.02)
    assert out[0, 0] == pytest.approx(1.0, abs=0.02)  # reversed: loudest first
    assert out[-1, 0] < 0.2  # and faded out at the end


def test_a_stereo_take_keeps_its_channels():
    out = render_edits(ramp(1000, channels=2), SR, Edits(trim_start_ms=10, reverse=True))
    assert out.shape[1] == 2


def test_the_result_is_contiguous_float32():
    out = render_edits(ramp(1000), SR, Edits(reverse=True))
    assert out.dtype == np.float32
    assert out.flags["C_CONTIGUOUS"]  # reversing leaves a negative stride


def test_an_empty_take_survives_every_edit():
    empty = np.zeros((0, 1), dtype=np.float32)
    out = render_edits(empty, SR, Edits(trim_start_ms=10, reverse=True, normalize=True))
    assert out.shape[0] == 0


# ------------------------------------------------------------ persistence
def test_edits_round_trip_through_a_dict():
    edits = Edits(trim_start_ms=12.5, pitch_semitones=-3, reverse=True)
    assert Edits.from_dict(edits.as_dict()) == edits


def test_a_missing_or_broken_dict_gives_no_edits():
    assert Edits.from_dict(None) is DEFAULT_EDITS
    assert Edits.from_dict({}) is DEFAULT_EDITS
    assert Edits.from_dict({"nonsense": 1}) == DEFAULT_EDITS


def test_one_nonsense_value_does_not_take_the_others_down():
    edits = Edits.from_dict({"trim_start_ms": "soon", "reverse": True, "fade_in_ms": 5})
    assert edits.trim_start_ms == 0.0  # dropped, not stored as a string
    assert edits.reverse is True
    assert edits.fade_in_ms == 5.0


def test_a_value_from_a_file_is_a_number_not_whatever_was_written():
    # Stored unvalidated, a string would blow up much later, inside the render.
    edits = Edits.from_dict({"trim_start_ms": "12.5", "pitch_semitones": 3})
    assert isinstance(edits.trim_start_ms, float)
    assert render_edits(flat(8000), SR, edits).shape[0] > 0


def test_with_value_leaves_the_original_alone():
    edits = Edits()
    changed = edits.with_value("reverse", True)
    assert changed.reverse is True
    assert edits.reverse is False  # frozen, so it is safe to share
