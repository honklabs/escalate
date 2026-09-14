"""IN-04: harmonic awareness.

The plan's four tests are here. The rest are the eight prototype rounds it took
to get here, written down as assertions so the numbers cannot quietly move.

**The key is the unreliable half.** The plan said "key detection via chroma",
and naming a tonic from pitch-class weights turned out to be a guess about
emphasis: a held Cmaj7 reads "E minor" (correctly noting those four notes also
sit in E minor), and a C triad with twelve harmonics reads "E minor" too. The
chroma underneath was right on all ten signals. So the colours come from the
pitch classes and the key is shown labelled as a guess — and
``test_the_key_name_is_wrong_on_a_seventh_chord`` pins the known failure
rather than hiding it.

**Two gates are needed, and each catches what the other misses.** A kick reads
`low drum` but its chroma is peaked enough (0.077) to pass a peak test; white
noise sometimes reads as `tone` but its chroma is flat (0.007). Neither gate
alone was sufficient.

**A 60 Hz chroma floor called a bass part clashing with its own key.** At 22 kHz
a 4096-point window is more than a semitone wide down there, so the note smears
into neighbours it never played. 90 Hz fixes it; the bottom octave still cannot
do better than "close".
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler import analysis as a
from push2sampler.modes.harmony import ACCEPT_BUTTON
from push2sampler.analysis import (
    CLASH_NEAR,
    CLASH_SAME,
    FIT_CLASH,
    FIT_NEAR,
    FIT_SAME,
    FIT_UNPITCHED,
    chroma,
    chroma_peak,
    clash,
    fit,
    harmony,
    key_name,
    pitch_classes,
    suggest_transpose,
)

SR = 22050
NAMES = a.NOTE_NAMES


def hz(name, octave=4):
    return 440.0 * 2 ** ((NAMES.index(name) + 12 * (octave + 1) - 69) / 12.0)


def seq(chords, seconds=1.0, octave=4, harmonics=(1.0, 0.5, 0.3, 0.2)):
    """Material in a key I chose, so the expected answer is known."""
    t = np.arange(int(seconds * SR)) / SR
    parts = []
    for names in chords:
        out = np.zeros_like(t)
        for name in names:
            for index, amp in enumerate(harmonics, start=1):
                out += amp * np.sin(2 * np.pi * hz(name, octave) * index * t)
        parts.append(out)
    mono = np.concatenate(parts)
    return (mono / np.abs(mono).max()).astype(np.float32)[:, None]


def kick(seconds=2.0):
    t = np.arange(int(seconds * SR)) / SR
    out = np.zeros_like(t)
    for beat in range(4):
        start = int(beat * 0.5 * SR)
        d = np.arange(min(int(0.2 * SR), len(t) - start)) / SR
        out[start:start + len(d)] += np.sin(
            2 * np.pi * (90 - 40 * d / 0.2) * d
        ) * np.exp(-d * 18)
    return (out / np.abs(out).max()).astype(np.float32)[:, None]


def hats(seconds=2.0, seed=11):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    out = np.zeros_like(t)
    for start in range(0, len(t), int(0.125 * SR)):
        d = np.arange(min(int(0.05 * SR), len(t) - start)) / SR
        out[start:start + len(d)] += rng.normal(0, 1, len(d)) * np.exp(-d * 90)
    return (out / np.abs(out).max()).astype(np.float32)[:, None]


C_MAJOR = seq([["C", "E", "G"], ["F", "A", "C"], ["G", "B", "D"]])
A_MINOR = seq([["A", "C", "E"], ["D", "F", "A"], ["E", "G", "B"]])
G_MAJOR = seq([["G", "B", "D"], ["C", "E", "G"], ["D", "F#", "A"]])
D_MAJOR = seq([["D", "F#", "A"], ["G", "B", "D"], ["A", "C#", "E"]])
EB_MAJOR = seq([["D#", "G", "A#"], ["G#", "C", "D#"], ["A#", "D", "F"]])
FS_MAJOR = seq([["F#", "A#", "C#"], ["B", "D#", "F#"], ["C#", "F", "G#"]])
C_TRIAD = seq([["C", "E", "G"]], seconds=3.0)
CMAJ7 = seq([["C", "E", "G", "B"]], seconds=3.0)
CS_TRIAD = seq([["C#", "F", "G#"]], seconds=3.0)
C_SCALE = seq([[n] for n in ("C", "D", "E", "F", "G", "A", "B")], seconds=0.5)
CHROMATIC = seq([[n] for n in NAMES], seconds=0.35)
NOISE = (np.random.default_rng(2).normal(0, 0.3, SR * 2)
         ).astype(np.float32)[:, None]
SILENCE = np.zeros((SR, 1), dtype=np.float32)


def read(buf):
    return harmony(buf, SR)


# ==================================================== the plan's tests
def test_c_major_and_a_minor_read_as_compatible():
    """The plan's test.

    They are the same seven notes, which is *why* -- and why the shared-note
    count is the right measure and the circle of fifths is not: these two sit
    three fifths apart.
    """
    assert fit(read(A_MINOR), read(C_MAJOR)) == FIT_SAME
    assert fit(read(C_MAJOR), read(A_MINOR)) == FIT_SAME


def test_c_and_f_sharp_read_as_clashing():
    """The plan's test: the tritone, which shares almost nothing."""
    assert fit(read(FS_MAJOR), read(C_MAJOR)) == FIT_CLASH


@pytest.mark.parametrize("label,buf", [("kick", kick()), ("hats", hats()),
                                       ("noise", NOISE)])
def test_percussion_reads_as_unpitched(label, buf):
    """The plan's test, for three kinds of unpitched."""
    reading = read(buf)
    assert reading.tonal is False
    assert fit(reading, read(C_MAJOR)) == FIT_UNPITCHED
    assert reading.note_names == ""


def test_a_suggested_transpose_applied_twice_is_idempotent():
    """The plan's test, and a property of searching by rotation.

    After the shift, the best rotation *is* the one you are on -- so the second
    answer is 0 without anything having to remember the first.
    """
    reference = read(C_MAJOR)
    for buf in (D_MAJOR, EB_MAJOR, FS_MAJOR, CS_TRIAD):
        subject = read(buf)
        shift = suggest_transpose(subject, reference)
        assert shift != 0
        moved = _rolled(subject, shift)
        assert fit(moved, reference) == FIT_SAME
        assert suggest_transpose(moved, reference) == 0


def _rolled(reading, shift):
    values = np.roll(reading.chroma, shift % 12)
    return a.Harmony(chroma=values, classes=pitch_classes(values), tonal=True,
                     peak=reading.peak, key="", key_confidence=0.0,
                     role=reading.role)


# ==================================================== the chroma
def test_the_chroma_sums_to_one_and_has_twelve_classes():
    values = chroma(C_MAJOR, SR)
    assert values.shape == (12,)
    assert float(values.sum()) == pytest.approx(1.0)


def test_silence_and_a_too_short_take_give_an_empty_chroma():
    assert float(chroma(SILENCE, SR).sum()) == 0.0
    assert float(chroma(np.zeros((16, 1), dtype=np.float32), SR).sum()) == 0.0
    assert float(chroma(None, SR).sum()) == 0.0


def test_a_c_lands_on_pitch_class_zero():
    """A4 = 440 is class 9, so the arithmetic has to put C at 0."""
    values = chroma(seq([["C"]], seconds=2.0), SR)
    assert int(np.argmax(values)) == 0
    values = chroma(seq([["A"]], seconds=2.0), SR)
    assert int(np.argmax(values)) == 9


def test_octaves_fold_together():
    """"Is there a C in this" is the question; which C belongs to the pitch."""
    low = chroma(seq([["C"]], seconds=2.0, octave=3), SR)
    high = chroma(seq([["C"]], seconds=2.0, octave=5), SR)
    assert int(np.argmax(low)) == int(np.argmax(high)) == 0


def test_a_triad_names_its_own_notes():
    reading = read(C_TRIAD)
    for note in ("C", "E", "G"):
        assert NAMES.index(note) in reading.classes
    assert "C" in reading.note_names and "G" in reading.note_names


# ==================================================== the clash measure
def test_the_measured_clash_values_are_where_the_thresholds_assume():
    """The measurement the two thresholds were placed from.

    Compatible material at or below 0.06, a neighbouring key at 0.14, a
    clashing one at 0.50 and up.  If these move, the thresholds need moving
    with them, and this test is how you find out.
    """
    reference = chroma(C_MAJOR, SR)
    measured = {
        label: clash(chroma(buf, SR), reference)
        for label, buf in (("self", C_MAJOR), ("A minor", A_MINOR),
                           ("C triad", C_TRIAD), ("Cmaj7", CMAJ7),
                           ("G major", G_MAJOR), ("D major", D_MAJOR),
                           ("Eb major", EB_MAJOR), ("F# major", FS_MAJOR))
    }
    for label in ("self", "A minor", "C triad", "Cmaj7", "G major"):
        assert measured[label] < CLASH_SAME, (label, measured[label])
    assert CLASH_SAME <= measured["D major"] < CLASH_NEAR
    for label in ("Eb major", "F# major"):
        assert measured[label] >= CLASH_NEAR, (label, measured[label])
    # And the gap the thresholds sit in is real, not marginal.
    assert measured["F# major"] - measured["D major"] > 0.3


def test_clash_is_asymmetric_on_purpose():
    """"Does adding this to what I have work" is a directed question.

    A three-note pad inside a seven-note progression fits; the progression laid
    over the pad introduces four notes the pad never plays.
    """
    progression = chroma(C_MAJOR, SR)
    triad = chroma(C_TRIAD, SR)
    assert clash(triad, progression) < clash(progression, triad)


def test_clash_against_nothing_is_zero_not_an_error():
    assert clash(chroma(C_MAJOR, SR), np.zeros(12)) == 0.0
    assert clash(np.zeros(12), chroma(C_MAJOR, SR)) == 0.0
    assert clash(np.zeros(3), np.zeros(12)) == 0.0


def test_a_sample_always_fits_itself():
    for buf in (C_MAJOR, A_MINOR, FS_MAJOR, C_TRIAD):
        reading = read(buf)
        assert fit(reading, reading) == FIT_SAME
        assert suggest_transpose(reading, reading) == 0


# ==================================================== the two gates
def test_the_role_gate_catches_a_kick_the_peak_gate_would_pass():
    """Finding: a kick's chroma is peaked enough to look tonal."""
    reading = read(kick())
    assert reading.role == "low drum"
    assert reading.peak >= a.CHROMA_PEAK_MIN      # the peak gate would pass it
    assert reading.tonal is False                 # the role gate does not


def test_the_peak_gate_catches_keyless_material_the_role_gate_would_pass():
    """Finding: a chromatic run is a `tone` with no key in it at all."""
    reading = read(CHROMATIC)
    assert reading.role in a.TONAL_ROLES          # the role gate would pass it
    assert reading.peak < a.CHROMA_PEAK_MIN       # the peak gate does not
    assert reading.tonal is False


def test_a_seven_note_melody_is_still_tonal():
    """The case that sets where the peak floor can go.

    A melody spreading its energy over seven classes is inherently flatter than
    a triad -- measured at 0.106, against 0.398 for a plain C triad.  It is the
    least peaked thing that must still count as having a key, so the floor has
    to sit below it.
    """
    reading = read(C_SCALE)
    assert reading.tonal is True
    assert reading.peak < read(C_TRIAD).peak
    assert reading.peak > a.CHROMA_PEAK_MIN
    assert fit(reading, read(C_MAJOR)) == FIT_SAME


def test_the_peak_floor_sits_in_the_gap_it_was_measured_into():
    """Below everything with a key in it, above everything without one.

    Keyless material is two orders of magnitude flatter (0.001-0.008) than the
    flattest thing with a key (0.106), so the floor is not a close call.  What
    *is* a close call is the kick at 0.077, which is why the role gate rather
    than this one is what rejects drums.
    """
    tonal = [read(buf).peak for buf in (C_MAJOR, C_TRIAD, C_SCALE, CMAJ7)]
    keyless = [read(buf).peak for buf in (CHROMATIC, NOISE, hats())]
    assert min(tonal) > a.CHROMA_PEAK_MIN > max(keyless)
    assert read(kick()).peak > a.CHROMA_PEAK_MIN   # too close to separate on


def test_chroma_peak_is_zero_for_flat_and_high_for_one_note():
    assert chroma_peak(np.ones(12)) == pytest.approx(0.0)
    one = np.zeros(12)
    one[0] = 1.0
    assert chroma_peak(one) == pytest.approx(1.0)
    assert chroma_peak(np.zeros(12)) == 0.0
    assert chroma_peak(np.ones(5)) == 0.0          # not a chroma at all


def test_silence_is_unpitched_rather_than_an_error():
    reading = read(SILENCE)
    assert reading.tonal is False
    assert reading.key == ""
    assert suggest_transpose(reading, read(C_MAJOR)) == 0


# ==================================================== the low end
def test_the_chroma_floor_is_high_enough_not_to_fail_a_bass_part():
    """The finding that moved the floor from 60 Hz to 90.

    At 60 a C-G-C bass figure in octave 1 read as **clashing with C major** --
    an in-key part called wrong, which is the one mistake this page must not
    make.  Both octaves now come back no worse than "close".
    """
    reference = read(C_MAJOR)
    for octave in (1, 2, 3):
        bass = read(seq([["C"], ["G"], ["C"]], octave=octave))
        assert fit(bass, reference) != FIT_CLASH, octave


def test_the_bottom_octave_is_honestly_only_close():
    """Stated as a test so the limitation cannot be forgotten.

    A 4096-point window at 22 kHz is more than a semitone wide near 60 Hz, so a
    very low note smears across classes it never played.  It reads "close", not
    "fits", and the docs say so rather than the page implying more resolution
    than it has.
    """
    bass = read(seq([["C"], ["G"], ["C"]], octave=1))
    assert fit(bass, read(C_MAJOR)) == FIT_NEAR


# ==================================================== the key name
def test_a_key_is_named_for_plain_material():
    assert key_name(chroma(C_MAJOR, SR))[0] == "C major"
    assert key_name(chroma(A_MINOR, SR))[0] == "A minor"
    assert key_name(chroma(G_MAJOR, SR))[0] == "G major"
    assert key_name(chroma(FS_MAJOR, SR))[0] == "F# major"


def test_the_key_name_is_wrong_on_a_seventh_chord():
    """The known failure, pinned rather than hidden.

    C-E-G-B also sits in E minor, and nothing in the pitch-class weights says
    which note is the tonic.  This is why the *colour* is not computed from a
    key name -- and the page labels the key a guess.
    """
    named, confidence = key_name(chroma(CMAJ7, SR))
    assert named == "E minor"
    assert confidence > 0.8                 # confidently wrong, hence the label
    # And the verdict is right anyway, because it does not use the name.
    assert fit(read(CMAJ7), read(C_MAJOR)) == FIT_SAME


def test_no_key_is_named_for_something_with_no_notes():
    assert key_name(np.zeros(12)) == ("", 0.0)
    assert key_name(np.ones(3)) == ("", 0.0)
    assert read(kick()).key == ""


# ==================================================== the transpose
def test_the_smallest_equally_good_shift_wins():
    """A C# triad was told to go up four semitones when down one was as good.

    Up four lands it on F, which does fit C major -- but a hand expects the
    small move, so ties go to the smaller shift.
    """
    shift = suggest_transpose(read(CS_TRIAD), read(C_MAJOR))
    assert shift == -1


def test_material_that_already_fits_is_offered_nothing():
    reference = read(C_MAJOR)
    for buf in (C_MAJOR, A_MINOR, G_MAJOR, C_TRIAD, CMAJ7):
        assert suggest_transpose(read(buf), reference) == 0


def test_no_transpose_is_suggested_for_unpitched_material():
    assert suggest_transpose(read(kick()), read(C_MAJOR)) == 0
    assert suggest_transpose(read(C_MAJOR), read(kick())) == 0


def test_a_suggested_shift_is_within_an_octave():
    reference = read(C_MAJOR)
    for buf in (D_MAJOR, EB_MAJOR, FS_MAJOR, CS_TRIAD):
        assert -6 <= suggest_transpose(read(buf), reference) <= 6


def test_fit_and_transpose_tolerate_a_missing_reading():
    assert fit(None, read(C_MAJOR)) == FIT_UNPITCHED
    assert fit(read(C_MAJOR), None) == FIT_UNPITCHED
    assert fit(None, None) == FIT_UNPITCHED
    assert suggest_transpose(None, read(C_MAJOR)) == 0
    assert suggest_transpose(read(C_MAJOR), None) == 0


def test_the_role_can_be_passed_in_to_save_a_second_pass():
    """A caller holding a Description has already paid for the role."""
    given = harmony(C_MAJOR, SR, role="tone")
    derived = harmony(C_MAJOR, SR)
    assert given.tonal == derived.tonal
    assert given.role == derived.role == "tone"
    assert np.allclose(given.chroma, derived.chroma)


def test_a_role_passed_in_is_believed():
    """So a caller can ask "and if this were a drum?" without lying to itself."""
    assert harmony(C_MAJOR, SR, role="low drum").tonal is False


# ==================================================== the page
def rig(tmp_path, library=None):
    """An app with a library of known keys and the harmony page open on slot 1."""
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.modes.harmony import HarmonyMode
    from push2sampler.project import Project
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    library = library if library is not None else [
        ("Cmaj", C_MAJOR), ("Amin", A_MINOR), ("Dmaj", D_MAJOR),
        ("F#maj", FS_MAJOR), ("kick", kick()),
    ]
    project = Project(samplerate=SR, bpm=120.0)
    project.pages = 1
    for slot, (name, buf) in enumerate(library):
        sample = project.put(slot, buf, 2)
        sample.name = name
        sample.set_trigger(0, True)
    push = SimPush()
    push.open()
    engine = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                    backend="offline", bpm=120.0, song_bars=project.song_bars)
    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    app.set_mode(HarmonyMode(app, 0))
    return app


def test_scale_from_a_sample_page_opens_the_harmony_view(tmp_path):
    from push2sampler.constants import Btn
    from push2sampler.modes.sample import SampleMode

    app = rig(tmp_path)
    app.set_mode(SampleMode(app, 3))
    app.mode.on_button(Btn.SCALE, True)
    assert app.mode.name == "harmony"
    assert app.mode.slot == 3            # compared against the page you left


def test_scale_in_the_library_opens_against_the_first_filled_slot(tmp_path):
    from push2sampler.constants import Btn
    from push2sampler.modes.library import LibraryMode

    app = rig(tmp_path)
    app.set_mode(LibraryMode(app))
    app.mode.on_button(Btn.SCALE, True)
    assert app.mode.name == "harmony"
    assert app.mode.slot == 0


def test_scale_on_an_empty_library_says_so(tmp_path):
    from push2sampler.constants import Btn
    from push2sampler.modes.library import LibraryMode

    app = rig(tmp_path, library=[])
    app.set_mode(LibraryMode(app))
    app.mode.on_button(Btn.SCALE, True)
    assert app.mode.name == "library"     # no page opened
    assert "nothing to compare" in app.message


def test_the_grid_colours_each_slot_by_how_it_fits(tmp_path):
    from push2sampler import colors
    from push2sampler.modes.harmony import FIT_COLORS

    app = rig(tmp_path)
    pads = [0] * 64
    app.mode.render_pads(pads)
    assert pads[1] == FIT_COLORS[FIT_SAME].index        # A minor
    assert pads[2] == FIT_COLORS[FIT_NEAR].index        # D major
    assert pads[3] == FIT_COLORS[FIT_CLASH].index       # F# major
    assert pads[4] == FIT_COLORS[FIT_UNPITCHED].index   # the kick
    assert pads[5] == colors.OFF.index                  # empty


def test_the_reference_pad_flashes_so_you_know_what_you_are_comparing_to(
        tmp_path, monkeypatch):
    """`App.blink` is a square wave off the clock, so drive the clock.

    A test that sleeps a quarter of a second to see the other phase is a test
    that is sometimes flaky.
    """
    from push2sampler import colors
    import push2sampler.app as app_module

    app = rig(tmp_path)
    phases = {}
    for name, now in (("on", 0.0), ("off", 0.25)):
        monkeypatch.setattr(app_module.time, "monotonic", lambda now=now: now)
        pads = [0] * 64
        app.mode.render_pads(pads)
        phases[name] = pads[0]
    assert phases["on"] == colors.WHITE.index
    assert phases["off"] == colors.GREEN.index


def test_picking_a_pad_reads_it_out_and_offers_the_move(tmp_path):
    app = rig(tmp_path)
    app.mode.on_pad(3, True, 127)
    assert app.mode.picked == 3
    assert "clashes" in app.message
    assert "button 1" in app.message


def test_picking_an_empty_pad_says_so(tmp_path):
    app = rig(tmp_path)
    app.mode.on_pad(40, True, 127)
    assert app.mode.picked is None
    assert "empty" in app.message


def test_picking_the_reference_says_what_it_is(tmp_path):
    app = rig(tmp_path)
    app.mode.on_pad(0, True, 127)
    assert app.mode.picked is None
    assert "compared to" in app.message


def test_accepting_applies_the_editor_s_own_pitch_edit(tmp_path):
    """Not a new field: "move this up two semitones" is what the editor does."""
    app = rig(tmp_path)
    app.mode.on_pad(3, True, 127)
    shift = app.mode.shift_for(3)
    app.mode.on_button(ACCEPT_BUTTON, True)

    assert app.project[3].edits.pitch_semitones == pytest.approx(shift)
    assert app.mode.verdict(3) == FIT_SAME
    assert "fits" in app.message


def test_accepting_twice_is_a_no_op_through_the_page(tmp_path):
    """The plan's idempotence test, but driven the way a hand would."""
    app = rig(tmp_path)
    app.mode.on_pad(3, True, 127)
    app.mode.on_button(ACCEPT_BUTTON, True)
    after = app.project[3].edits.pitch_semitones

    app.mode.on_button(ACCEPT_BUTTON, True)
    assert app.project[3].edits.pitch_semitones == after
    assert "already fits" in app.message


def test_accepting_is_one_undo_step(tmp_path):
    app = rig(tmp_path)
    app.mode.on_pad(3, True, 127)
    app.mode.on_button(ACCEPT_BUTTON, True)
    assert app.project[3].edits.pitch_semitones != 0

    app.undo()
    assert app.project[3].edits.pitch_semitones == 0
    assert app.mode.verdict(3) == FIT_CLASH     # and the reading followed


def test_accepting_with_nothing_picked_asks_for_a_pad(tmp_path):
    app = rig(tmp_path)
    app.mode.on_button(ACCEPT_BUTTON, True)
    assert "pick a pad" in app.message


def test_the_accept_button_is_dark_when_there_is_nothing_to_accept(tmp_path,
                                                                   monkeypatch):
    import push2sampler.app as app_module

    app = rig(tmp_path)
    buttons: dict = {}
    app.mode.render_buttons(buttons)
    assert buttons[ACCEPT_BUTTON] == 0          # nothing picked

    app.mode.on_pad(1, True, 127)               # A minor already fits
    buttons = {}
    app.mode.render_buttons(buttons)
    assert buttons[ACCEPT_BUTTON] == 0

    app.mode.on_pad(3, True, 127)               # F# major does not
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 0.0)
    buttons = {}
    app.mode.render_buttons(buttons)
    assert buttons[ACCEPT_BUTTON] > 0


def test_shift_and_a_pad_re_references_without_leaving(tmp_path):
    """"And against *that* one?" is the second question anybody asks."""
    app = rig(tmp_path)
    app.shift = True
    app.mode.on_pad(3, True, 127)
    assert app.mode.slot == 3
    assert app.mode.picked is None
    # And the verdicts invert: what clashed with C major is now the reference.
    assert app.mode.verdict(0) == FIT_CLASH


def test_the_status_lines_count_the_verdicts_and_flag_the_key_as_a_guess(tmp_path):
    app = rig(tmp_path)
    lines = "\n".join(app.mode.status_lines())
    assert "a guess" in lines
    assert "1 fit" in lines and "1 close" in lines
    assert "1 clash" in lines and "1 unpitched" in lines


def test_an_unpitched_reference_explains_itself_rather_than_colouring(tmp_path):
    """A kick is a perfectly good slot; it is just not a question about keys."""
    app = rig(tmp_path, library=[("kick", kick()), ("Cmaj", C_MAJOR)])
    lines = "\n".join(app.mode.status_lines())
    assert "no key" in lines
    assert "low drum" in app.message or "not a pitched part" in app.message


def test_a_reading_is_measured_once_per_slot(tmp_path):
    """An FFT per filled slot is a button-press cost, not a per-frame one."""
    app = rig(tmp_path)
    calls = []
    real = a.harmony

    def counted(buf, samplerate, role=None):
        calls.append(samplerate)
        return real(buf, samplerate, role)

    import push2sampler.modes.harmony as page
    page.harmony = counted
    try:
        app.mode._harmonies.clear()
        for _ in range(5):
            pads = [0] * 64
            app.mode.render_pads(pads)
    finally:
        page.harmony = real
    assert len(calls) == 5          # one per filled slot, not per frame


def test_the_reading_follows_an_edit_made_somewhere_else(tmp_path):
    """The staleness a test caught, in the general form.

    The page cannot see an undo, a re-record, an overdub, or an edit applied on
    the editor page -- none of them go through it.  So the reading is keyed on
    the audio rather than on the slot, and all four cases fix themselves.
    """
    app = rig(tmp_path)
    assert app.mode.verdict(3) == FIT_CLASH

    # An edit made anywhere: here, straight on the sample.
    app.project[3].set_edits(app.project[3].edits.with_value("pitch_semitones", -6.0))
    assert app.mode.verdict(3) == FIT_SAME

    app.project[3].set_edits(app.project[3].edits.with_value("pitch_semitones", 0.0))
    assert app.mode.verdict(3) == FIT_CLASH
