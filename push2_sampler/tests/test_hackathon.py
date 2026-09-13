"""The v1.1 and v1.2 remainder: comforts, tooling, mixer, overdub, auto-takes.

One file per release train would be tidier, but these landed together and they
share a rig, so they are tested together.
"""

import json
import time

import numpy as np
import pytest

from push2sampler import analysis, calibrate, colors, doctor
from push2sampler.app import DELETE_ARM_S, PRESS_FLASH_S, App
from push2sampler.audio import Engine
from push2sampler.constants import (
    DISPLAY_ROW_BOTTOM,
    ENCODER_MASTER,
    ENCODER_TRACK,
    Btn,
)
from push2sampler.cli import build_parser, main
from push2sampler.project import FORMAT_VERSION, Project
from push2sampler.push2 import SimPush
from push2sampler.settings import Settings

SR = 8000


@pytest.fixture
def rig(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    engine = Engine(
        samplerate=SR, blocksize=64, in_channels=1, out_channels=2,
        backend="offline", bpm=120.0, song_bars=project.song_bars,
    )
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    app = App(push, engine, project, project_dir=tmp_path / "song", settings=settings)
    return app, push, engine, project


def pump(app):
    for event in app.push.poll_events():
        app.handle(event)
    for event in app.engine.poll_events():
        app.on_engine_event(event)
    app.mode.on_tick()
    app._supervise_surface()
    app.render()


def settle(app):
    time.sleep(PRESS_FLASH_S)
    pump(app)


def take(engine, bars=1, value=0.5):
    return np.full((int(bars * engine.frames_per_bar), 1), value, dtype=np.float32)


def record_take(app, engine, bars):
    frames = int(app.count_in_beats * engine.frames_per_beat)
    frames += int(bars * engine.frames_per_bar) + 64
    engine.process_offline(frames, np.full((frames, 1), 0.3, dtype=np.float32))
    pump(app)


# ------------------------------------------------ CC-03: destructive confirm
def test_deleting_an_unused_slot_needs_no_confirmation(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)  # filled but plays nowhere
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert project[0] is None


def test_deleting_a_used_slot_names_the_cost_and_waits(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    for bar in range(12):
        project[0].set_trigger(bar, True)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert project[0] is not None
    assert "plays on 12 bars" in app.message
    assert app.delete_armed  # still armed, waiting
    push.press_pad(0)
    pump(app)
    assert project[0] is None


def test_one_bar_is_singular(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(3, True)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(0)
    pump(app)
    assert "plays on 1 bar -" in app.message


def test_confirming_a_different_slot_starts_over(rig):
    app, push, engine, project = rig
    for slot in (0, 1):
        project.put(slot, take(engine), bars=1)
        project[slot].set_trigger(0, True)
    push.press_button(Btn.DELETE)
    pump(app)
    push.press_pad(0)
    pump(app)
    push.press_pad(1)  # a different pad: warns about that one instead
    pump(app)
    assert project[0] is not None and project[1] is not None
    assert "slot 2" in app.message


def test_the_delete_arm_expires(rig, monkeypatch):
    app, push, _, _ = rig
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.app.time.monotonic", lambda: clock[0])
    push.press_button(Btn.DELETE)
    pump(app)
    assert app.delete_armed
    clock[0] += DELETE_ARM_S + 0.1
    assert not app.delete_armed


def test_an_expired_arm_does_not_delete(rig, monkeypatch):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.app.time.monotonic", lambda: clock[0])
    push.press_button(Btn.DELETE)
    pump(app)
    clock[0] += DELETE_ARM_S + 0.1
    push.press_pad(0)
    pump(app)
    assert project[0] is not None


def test_shift_delete_on_a_used_sample_also_confirms(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    app.goto_sample(0)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.DELETE)
    pump(app)
    assert project[0] is not None
    push.press_button(Btn.DELETE)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert project[0] is None


# ---------------------------------------------------- CC-05: press feedback
def test_a_press_lights_its_own_button(rig):
    app, push, _, _ = rig
    push.press_button(Btn.ACCENT)  # the library ignores Accent entirely
    pump(app)
    assert push.button_leds[Btn.ACCENT] > 0


def test_the_flash_goes_out_again(rig):
    app, push, _, _ = rig
    push.press_button(Btn.ACCENT)
    pump(app)
    settle(app)
    assert push.button_leds[Btn.ACCENT] == 0


def test_the_flash_does_not_strand_a_led_on(rig):
    """A flashed button must end up in the bookkeeping that later clears it."""
    app, push, _, _ = rig
    push.press_button(Btn.SCALE)
    pump(app)
    assert Btn.SCALE in app._rendered_buttons
    settle(app)
    assert push.button_leds[Btn.SCALE] == 0


def test_the_flash_does_not_override_the_mode_afterwards(rig):
    app, push, _, _ = rig
    push.press_button(Btn.REPEAT)  # loop on: the mode wants this lit
    pump(app)
    settle(app)
    assert push.button_leds[Btn.REPEAT] > 0  # still lit, by the mode not the flash


# ------------------------------------------------------ CC-10: save indicator
def test_the_transport_line_marks_unsaved_changes(rig):
    app, push, engine, project = rig
    assert not any(line.endswith("*") for line in app.status_lines())
    project.put(0, take(engine), bars=1)
    app.save_soon()
    assert any(line.endswith("*") for line in app.status_lines())


def test_saving_clears_the_mark_and_says_so(rig):
    app, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.save_soon()
    assert app.save_now(announce=True)
    assert app.message == "saved"
    assert not app.unsaved


def test_a_failed_save_is_reported_and_does_not_raise(rig, monkeypatch):
    app, _, engine, project = rig
    project.put(0, take(engine), bars=1)

    def explode(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(project, "save", explode)
    app.save_soon()
    assert app.save_now() is False
    assert "no space left" in app.message
    # ...and it does not keep retrying every tick.
    assert app._save_at is None


def test_no_project_directory_means_nothing_is_ever_unsaved(tmp_path):
    project = Project(samplerate=SR)
    engine = Engine(samplerate=SR, blocksize=64, backend="offline", bpm=120.0,
                    song_bars=project.song_bars)
    push = SimPush()
    push.open()
    app = App(push, engine, project, project_dir=None, settings=Settings())
    project.dirty = True
    assert not app.unsaved
    assert app.save_now() is False


# --------------------------------------------------- CC-14: surviving unplug
class FlakyPush(SimPush):
    """A surface whose writes fail while ``broken`` is set."""

    def __init__(self):
        super().__init__()
        self.broken = False
        self.opens = 0

    def open(self):
        if self.broken:
            raise OSError("device not configured")
        self.opens += 1
        super().open()

    def _send_pad(self, index, value):
        if self.broken:
            raise OSError("write failed")
        super()._send_pad(index, value)

    def _send_button(self, cc, value):
        if self.broken:
            raise OSError("write failed")
        super()._send_button(cc, value)


@pytest.fixture
def flaky_rig(tmp_path):
    project = Project(samplerate=SR, bpm=120.0)
    engine = Engine(
        samplerate=SR, blocksize=64, in_channels=1, out_channels=2,
        backend="offline", bpm=120.0, song_bars=project.song_bars,
    )
    push = FlakyPush()
    push.open()
    app = App(push, engine, project, project_dir=tmp_path / "song",
              settings=Settings(path=tmp_path / "settings.json"))
    return app, push, engine, project


def test_a_write_failure_takes_the_surface_offline(flaky_rig):
    app, push, _, _ = flaky_rig
    push.broken = True
    app.render()
    assert push.offline
    pump(app)
    assert "surface offline" in app.message


def test_the_transport_keeps_running_while_the_surface_is_gone(flaky_rig):
    app, push, engine, project = flaky_rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    app.rebuild_schedule()
    engine.play(0)
    push.broken = True
    app.render()
    engine.process_offline(128, np.zeros((128, 1), dtype=np.float32))
    assert engine.is_playing
    assert engine.sounding == (0,)


def test_it_reconnects_and_relights_everything(flaky_rig, monkeypatch):
    app, push, _, _ = flaky_rig
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.app.time.monotonic", lambda: clock[0])
    push.broken = True
    app.render()
    pump(app)
    assert push.offline

    push.broken = False
    clock[0] += 3.0
    pump(app)
    assert not push.offline
    assert app.message == "surface back"
    # The cache was invalidated, so the whole grid was resent.
    app.render()
    assert push.pad_leds[0] == colors.WHITE_DIM.index


def test_a_failed_reconnect_just_tries_again_later(flaky_rig, monkeypatch):
    app, push, _, _ = flaky_rig
    clock = [1000.0]
    monkeypatch.setattr("push2sampler.app.time.monotonic", lambda: clock[0])
    push.broken = True
    app.render()
    pump(app)
    before = push.opens
    clock[0] += 3.0
    pump(app)  # still broken: reopen fails
    assert push.offline
    assert push.opens == before
    clock[0] += 3.0
    push.broken = False
    pump(app)
    assert not push.offline


def test_the_display_says_the_surface_is_offline(flaky_rig):
    app, push, _, _ = flaky_rig
    push.broken = True
    app.render()
    assert any("SURFACE OFFLINE" in line for line in app.status_lines())


def test_invalidating_leds_makes_every_pad_differ():
    push = SimPush()
    push.open()
    push.set_pad(0, colors.WHITE)
    push.invalidate_leds()
    push.sent.clear()
    push.set_pad(0, colors.WHITE)
    assert push.sent == [("pad", 0, colors.WHITE.index)]


# -------------------------------------------------------- CC-04: remembering
def test_the_bookmark_round_trips(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(path=path)
    settings.remember(project="/songs/one", mode="sample", slot=7,
                      loop=False, metronome=True)
    settings.save()
    loaded = Settings.load(path)
    assert loaded.ui["project"] == "/songs/one"
    assert loaded.ui["mode"] == "sample"
    assert loaded.ui["slot"] == 7
    assert loaded.ui["loop"] is False
    assert loaded.ui["metronome"] is True


def test_a_nonsense_bookmark_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"ui": {"slot": "seven", "mode": 3, "loop": "yes"}}))
    loaded = Settings.load(path)
    assert loaded.ui["slot"] is None
    assert loaded.ui["mode"] == "library"
    assert loaded.ui["loop"] is True


def test_the_bookmark_does_not_pollute_the_settings_page(tmp_path):
    from push2sampler.settings import EDITABLE

    settings = Settings(path=tmp_path / "settings.json")
    assert "ui" not in EDITABLE
    assert "ui" not in settings


def test_restoring_lands_on_the_remembered_sample_page(rig):
    app, _, engine, project = rig
    project.put(5, take(engine), bars=1)
    app.settings.remember(mode="sample", slot=5, loop=False, metronome=True)
    app.restore_ui_state()
    assert app.mode.name == "sample"
    assert app.mode.slot == 5
    assert engine.loop is False
    assert engine.metronome is True


def test_a_deleted_slot_falls_back_to_the_library(rig):
    app, _, _, _ = rig
    app.settings.remember(mode="sample", slot=5)  # nothing in slot 5
    app.restore_ui_state()
    assert app.mode.name == "library"


def test_a_transient_mode_is_never_restored(rig):
    app, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    app.settings.remember(mode="record", slot=0)
    app.restore_ui_state()
    assert app.mode.name == "library"


def test_opening_a_page_moves_the_bookmark(rig):
    app, _, engine, project = rig
    project.put(3, take(engine), bars=1)
    app.goto_sample(3)
    assert app.settings.ui["mode"] == "sample"
    assert app.settings.ui["slot"] == 3


def test_the_remembered_project_is_used_when_none_is_given(tmp_path):
    from push2sampler.cli import _resolve_project

    songs = tmp_path / "songs"
    songs.mkdir()
    args = build_parser().parse_args([])
    settings = Settings()
    settings.remember(project=str(songs))
    assert _resolve_project(args, settings) == str(songs)


def test_an_explicit_project_wins_over_the_bookmark(tmp_path):
    from push2sampler.cli import _resolve_project

    args = build_parser().parse_args(["asked-for"])
    settings = Settings()
    settings.remember(project=str(tmp_path))
    assert _resolve_project(args, settings) == "asked-for"


def test_a_vanished_project_falls_back_to_song():
    from push2sampler.cli import _resolve_project

    args = build_parser().parse_args([])
    settings = Settings()
    settings.remember(project="/definitely/not/here")
    assert _resolve_project(args, settings) == "song"


# --------------------------------------------------------- CC-16: the doctor
def test_the_doctor_prints_every_row_and_exits_zero(capsys):
    assert doctor.run("song") == 0
    text = capsys.readouterr().out
    for name, _, _, _ in doctor.PACKAGES:
        assert name in text
    assert "MIDI" in text and "audio" in text and "writable" in text or "settings" in text


def test_the_doctor_survives_everything_being_missing(monkeypatch):
    monkeypatch.setattr(doctor, "_import", lambda name: None)
    lines = doctor.report("song")
    assert any("missing" in line for line in lines)
    assert any("pip install" in line for line in lines)


def test_a_missing_fatal_package_is_marked_worse_than_an_optional_one(monkeypatch):
    monkeypatch.setattr(doctor, "_import", lambda name: None)
    rows = {row.what: row.state for row in doctor.packages()}
    assert rows["numpy"] == doctor.BAD
    assert rows["soundfile"] == doctor.WARN


def test_doctor_as_a_bare_word(capsys):
    assert main(["doctor"]) == 0
    assert "push2sampler" in capsys.readouterr().out


def test_version_prints_and_exits(capsys):
    from push2sampler import __version__

    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help_carries_worked_examples():
    text = build_parser().format_help()
    assert "examples:" in text
    assert "--bounce mix.wav" in text
    assert "--selftest" in text


# ----------------------------------------------------- CC-09: calibration
def delayed_loopback(delay_frames, noise=0.0, seed=0):
    """A fake sound card that returns what was played, ``delay_frames`` later."""
    rng = np.random.default_rng(seed)

    def playrec(outdata):
        frames = outdata.shape[0]
        captured = rng.normal(0.0, noise, (frames, 1)).astype(np.float32)
        played = outdata.mean(axis=1)
        keep = max(0, frames - delay_frames)
        captured[delay_frames:delay_frames + keep, 0] += played[:keep] * 0.5
        return captured

    return playrec


def test_a_synthetic_loopback_measures_its_own_delay():
    delay = 240  # frames
    value, note = calibrate.measure(delayed_loopback(delay), SR, channels=2)
    assert value == pytest.approx(delay / SR * 1000.0, abs=1.0)
    assert "rounds" in note


def test_noise_does_not_defeat_the_detection():
    delay = 160
    value, _ = calibrate.measure(delayed_loopback(delay, noise=0.02), SR, channels=2)
    assert value == pytest.approx(delay / SR * 1000.0, abs=1.0)


def test_silence_is_reported_rather_than_guessed():
    def deaf(outdata):
        return np.zeros((outdata.shape[0], 1), dtype=np.float32)

    value, note = calibrate.measure(deaf, SR, channels=2)
    assert value is None
    assert "heard nothing" in note


def test_an_absurd_measurement_is_refused():
    value, note = calibrate.summarise([400.0, 410.0, 405.0])
    assert value is None
    assert "too much to be latency" in note


def test_a_wide_spread_is_flagged_but_still_used():
    value, note = calibrate.summarise([10.0, 12.0, 40.0])
    assert value == pytest.approx(12.0)
    assert "quieter" in note


def test_detect_offset_needs_a_kernel_that_fits():
    assert calibrate.detect_offset(np.zeros((4, 1)), np.zeros((8, 1))) is None


def test_calibrate_writes_the_setting(tmp_path, capsys):
    settings = Settings(path=tmp_path / "settings.json")
    settings.set("samplerate", SR)
    delay = 200
    assert calibrate.run(settings, playrec=delayed_loopback(delay), say=lambda *a: None) == 0
    assert settings["rec_latency_ms"] == pytest.approx(delay / SR * 1000.0, abs=1.0)
    assert json.loads((tmp_path / "settings.json").read_text())["rec_latency_ms"] > 0


def test_calibrate_with_no_settings_does_not_write(tmp_path):
    settings = Settings(path=tmp_path / "settings.json")
    settings.set("samplerate", SR)
    said = []
    assert calibrate.run(settings, playrec=delayed_loopback(200), write=False,
                         say=said.append) == 0
    assert not (tmp_path / "settings.json").exists()
    assert any("Not writing" in line for line in said)


def test_calibrate_reports_a_failure_to_measure(tmp_path):
    settings = Settings(path=tmp_path / "settings.json")
    said = []
    assert calibrate.run(settings, playrec=lambda out: np.zeros((out.shape[0], 1)),
                         say=said.append) == 1
    assert any("Could not measure" in line for line in said)


# ------------------------------------------------- CC-15: better simulator
def test_a_script_drives_a_whole_flow_and_exits_zero(tmp_path):
    script = tmp_path / "demo.sim"
    # 240 BPM keeps the real-time wait for a 2-bar take down to ~3 seconds;
    # this test drives the actual program end to end, so it cannot be faked.
    script.write_text(
        "# record, arrange, play\n"
        "macro two p 0; p 1; record\n"
        "two\n"
        "wait 3.2\n"
        "p 0\n"
        "p 8\n"
        "play\n"
        "wait 0.5\n"
        "stop\n"
    )
    project_dir = tmp_path / "scripted"
    status = main([
        "--script", str(script), "--quiet", "--no-settings", "--bpm", "240",
        "--until-idle", str(project_dir),
    ])
    assert status == 0
    payload = json.loads((project_dir / "project.json").read_text())
    assert payload["slots"][0]["bars"] == 2
    assert payload["slots"][0]["triggers"] == [0, 8]


def test_a_bad_command_in_a_script_is_a_nonzero_exit(tmp_path):
    script = tmp_path / "bad.sim"
    script.write_text("p 0\nnonsense\n")
    status = main([
        "--script", str(script), "--quiet", "--no-settings",
        str(tmp_path / "s"),
    ])
    assert status == 1


def test_a_macro_cannot_shadow_a_real_command(tmp_path):
    from push2sampler import sim

    with pytest.raises(ValueError, match="already a command"):
        sim._run_line("macro play p 0", None, None, {})


def test_an_empty_macro_is_refused():
    from push2sampler import sim

    with pytest.raises(ValueError, match="at least one"):
        sim._run_line("macro thing", None, None, {})


def test_the_grid_can_be_coloured():
    from push2sampler import sim

    painted = sim.colorize("W.g")
    assert "\033[" in painted
    assert painted.count(sim.RESET) == 3


def test_colour_is_off_when_not_a_terminal():
    from push2sampler import sim

    class NotATty:
        def isatty(self):
            return False

    assert sim.use_color(NotATty()) is False


def test_no_color_is_honoured(monkeypatch):
    from push2sampler import sim

    class IsATty:
        def isatty(self):
            return True

    monkeypatch.setenv("NO_COLOR", "1")
    assert sim.use_color(IsATty()) is False


def test_the_help_command_prints_the_list(capsys):
    from push2sampler import sim

    assert sim._dispatch("?", None, None) is True
    assert "press and release pad" in capsys.readouterr().out


# ---------------------------------------------- NH-08: post-take processing
def test_leading_silence_is_found():
    audio = np.zeros((SR, 1), dtype=np.float32)
    audio[240:] = 0.5  # 30 ms in at 8 kHz
    assert analysis.first_transient(audio, SR) == 240


def test_a_take_that_starts_immediately_is_untouched():
    audio = np.full((SR, 1), 0.5, dtype=np.float32)
    assert analysis.first_transient(audio, SR) == 0


def test_silence_has_no_transient():
    assert analysis.first_transient(np.zeros((SR, 1), dtype=np.float32), SR) == 0


def test_the_search_stops_after_the_slack():
    audio = np.zeros((SR, 1), dtype=np.float32)
    audio[SR // 2:] = 0.5  # half a second in: that is a rest, not late timing
    assert analysis.first_transient(audio, SR) == 0


def test_shifting_keeps_the_length_exactly():
    audio = np.zeros((100, 1), dtype=np.float32)
    audio[10:] = 0.5
    shifted = analysis.shift_left(audio, 10)
    assert shifted.shape == audio.shape
    assert shifted[0, 0] == pytest.approx(0.5)
    assert shifted[-1, 0] == 0.0  # padded, not wrapped


def test_normalising_hits_the_target_peak():
    audio = np.full((100, 1), 0.2, dtype=np.float32)
    assert analysis.peak(analysis.normalize(audio)) == pytest.approx(
        analysis.TARGET_PEAK, abs=1e-4
    )


def test_normalising_silence_does_nothing():
    audio = np.zeros((100, 1), dtype=np.float32)
    assert analysis.peak(analysis.normalize(audio)) == 0.0


def test_fading_the_edges_starts_and_ends_quiet():
    audio = np.full((SR, 1), 0.5, dtype=np.float32)
    faded = analysis.fade_edges(audio, SR, ms=2.0)
    assert faded[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert faded[-1, 0] < 0.1
    assert faded[SR // 2, 0] == pytest.approx(0.5)


def test_process_take_does_nothing_by_default():
    audio = np.full((100, 1), 0.2, dtype=np.float32)
    out, notes = analysis.process_take(audio, SR)
    assert notes == []
    assert np.array_equal(out, audio)


def test_process_take_reports_what_it_did():
    audio = np.zeros((SR, 1), dtype=np.float32)
    audio[240:] = 0.2
    out, notes = analysis.process_take(audio, SR, trim=True, normalise=True)
    assert any("trimmed" in n for n in notes)
    assert any("normalised" in n for n in notes)
    assert out.shape == audio.shape


def test_a_recorded_take_is_processed_when_the_settings_ask(rig):
    app, push, engine, project = rig
    app.settings.set("auto_normalize", True)
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    record_take(app, engine, bars=1)
    assert project[0] is not None
    # The rig records a constant 0.3; normalising takes it to the target.
    assert analysis.peak(project[0].audio) == pytest.approx(
        analysis.TARGET_PEAK, abs=1e-3
    )
    assert "normalised" in app.message


def test_a_processed_take_still_fits_its_bars(rig):
    app, push, engine, project = rig
    app.settings.set("auto_trim", True)
    app.settings.set("auto_fade", True)
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    record_take(app, engine, bars=1)
    assert not project.mismatched(project[0])


def test_undoing_a_processed_take_restores_the_slot(rig):
    app, push, engine, project = rig
    app.settings.set("auto_normalize", True)
    push.press_pad(0)
    pump(app)
    push.press_button(Btn.RECORD)
    pump(app)
    record_take(app, engine, bars=1)
    app.undo()
    assert project[0] is None


# ------------------------------------------------------------ NH-01: mixer
def mixer_rig(rig, slots=(0, 1, 2)):
    app, push, engine, project = rig
    for slot in slots:
        project.put(slot, take(engine), bars=1)
        project[slot].set_trigger(0, True)
    app.rebuild_schedule()
    push.press_button(Btn.MIX)
    pump(app)
    return app, push, engine, project


def test_mix_opens_and_closes_the_mixer(rig):
    app, push, _, _ = mixer_rig(rig)
    assert app.mode.name == "mixer"
    push.press_button(Btn.MIX)
    pump(app)
    assert app.mode.name == "library"


def test_an_encoder_sets_a_slots_gain_and_the_schedule_follows(rig):
    app, push, engine, project = mixer_rig(rig)
    push.turn(ENCODER_TRACK[1], 5)
    pump(app)
    assert project[1].gain == pytest.approx(1.1)
    assert engine._schedule[0][1].gain == pytest.approx(1.1)


def test_a_button_below_mutes_its_strip(rig):
    app, push, engine, project = mixer_rig(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[2])
    pump(app)
    assert project[2].enabled is False
    assert 2 not in {entry.slot for entry in engine._schedule[0]}


def test_solo_leaves_mute_state_alone(rig):
    app, push, engine, project = mixer_rig(rig)
    project[1].enabled = False  # muted by hand
    push.press_button(Btn.SOLO)
    pump(app)
    push.press_button(DISPLAY_ROW_BOTTOM[0])
    pump(app)
    assert project.soloed == 0
    assert {entry.slot for entry in engine._schedule[0]} == {0}
    assert project[1].enabled is False  # untouched

    push.press_button(Btn.SOLO)  # clears the solo
    pump(app)
    assert project.soloed is None
    assert project[1].enabled is False  # still muted, as it was
    assert {entry.slot for entry in engine._schedule[0]} == {0, 2}


def test_the_master_encoder_scales_the_mix(rig):
    app, push, engine, project = mixer_rig(rig)
    push.turn(ENCODER_MASTER, -10)
    pump(app)
    assert project.master_gain == pytest.approx(0.8)
    assert engine.master_gain == pytest.approx(0.8)


def test_master_gain_is_undoable_and_reaches_the_engine(rig):
    app, push, engine, project = mixer_rig(rig)
    push.turn(ENCODER_MASTER, -10)
    pump(app)
    app.undo()
    assert project.master_gain == pytest.approx(1.0)
    assert engine.master_gain == pytest.approx(1.0)


def test_master_gain_actually_attenuates_the_output(rig):
    app, _, engine, project = rig
    project.put(0, take(engine, bars=1, value=0.5), bars=1)
    project[0].set_trigger(0, True)
    app.rebuild_schedule()
    engine.master_gain = 0.5
    engine.play(0)
    out = engine.process_offline(512, np.zeros((512, 1), dtype=np.float32))
    assert float(np.max(np.abs(out))) == pytest.approx(0.25, abs=0.02)


def test_master_gain_survives_a_save(rig, tmp_path):
    app, _, _, project = rig
    project.master_gain = 0.6
    project.save(tmp_path / "m")
    loaded = Project.load(tmp_path / "m", samplerate=SR)
    assert loaded.master_gain == pytest.approx(0.6)


def test_the_pads_meter_each_slot(rig):
    app, push, engine, project = mixer_rig(rig)
    engine.play(0)
    engine.process_offline(256, np.zeros((256, 1), dtype=np.float32))
    pump(app)
    assert engine.slot_peaks[0] > 0.0
    column = [push.pad_leds[row * 8 + 0] for row in range(8)]
    assert colors.GREEN.index in column  # the bottom of the meter is lit


def test_meters_decay_when_nothing_plays(rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].set_trigger(0, True)
    engine.set_schedule(project.build_schedule())
    engine.play(0)
    engine.process_offline(256, np.zeros((256, 1), dtype=np.float32))
    hot = engine.slot_peaks[0]
    engine.stop()
    for _ in range(40):
        engine.process_offline(256, np.zeros((256, 1), dtype=np.float32))
    assert engine.slot_peaks[0] < hot * 0.5


def test_up_and_down_change_the_row(rig):
    app, push, _, _ = mixer_rig(rig)
    assert app.mode.row == 0
    push.press_button(Btn.DOWN)
    pump(app)
    assert app.mode.row == 1
    assert list(app.mode.slots) == list(range(8, 16))
    push.press_button(Btn.UP)
    pump(app)
    assert app.mode.row == 0


def test_a_pad_press_picks_that_row(rig):
    app, push, _, _ = mixer_rig(rig)
    push.press_pad(3 * 8 + 5)
    pump(app)
    assert app.mode.row == 3


def test_soloing_an_empty_strip_says_so(rig):
    app, push, _, project = mixer_rig(rig)
    push.press_button(DISPLAY_ROW_BOTTOM[7])  # slot 8 is empty
    pump(app)
    assert "empty" in app.message


def test_a_bounce_respects_solo(rig, tmp_path):
    from push2sampler.render import render_song

    _, _, engine, project = rig
    for slot in (0, 1):
        project.put(slot, take(engine, bars=1, value=0.4), bars=1)
        project[slot].set_trigger(0, True)
    project.solo(0)
    mix = render_song(project)
    assert float(np.max(np.abs(mix))) == pytest.approx(0.4, abs=0.05)


# ---------------------------------------------------------- NH-04: overdub
def layered_rig(rig, bars=1):
    app, push, engine, project = rig
    project.put(0, take(engine, bars=bars, value=0.2), bars=bars)
    project[0].set_trigger(0, True)
    app.rebuild_schedule()
    app.goto_sample(0)
    pump(app)
    return app, push, engine, project


def test_a_fresh_take_has_one_layer(rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    assert project[0].layer_count == 1
    assert project[0].layers == []


def test_new_records_another_layer_and_sums_it(rig):
    app, push, engine, project = layered_rig(rig)
    push.press_button(Btn.NEW)
    pump(app)
    assert app.mode._layering
    record_take(app, engine, bars=1)
    sample = project[0]
    assert sample.layer_count == 2
    # The rig feeds a constant 0.3 in; 0.2 was already there.
    assert float(sample.audio[len(sample.audio) // 2, 0]) == pytest.approx(0.5, abs=0.01)


def test_two_layers_of_known_levels_sum_exactly(rig):
    _, _, engine, project = rig
    project.put(0, take(engine, value=0.1), bars=1)
    project[0].add_layer(take(engine, value=0.25))
    mid = len(project[0].audio) // 2
    assert float(project[0].audio[mid, 0]) == pytest.approx(0.35)


def test_removing_a_layer_restores_the_previous_sum_exactly(rig):
    _, _, engine, project = rig
    project.put(0, take(engine, value=0.1), bars=1)
    before = np.array(project[0].audio, copy=True)
    project[0].add_layer(take(engine, value=0.25))
    assert project[0].remove_layer()
    assert np.array_equal(project[0].audio, before)


def test_the_last_layer_cannot_be_removed(rig):
    _, _, engine, project = rig
    project.put(0, take(engine), bars=1)
    project[0].add_layer(take(engine))
    assert project[0].remove_layer() is True
    assert project[0].remove_layer() is False


def test_shift_new_removes_a_layer_undoably(rig):
    app, push, engine, project = layered_rig(rig)
    project[0].add_layer(take(engine, value=0.3))
    assert project[0].layer_count == 2
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.NEW)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert project[0].layer_count == 1
    app.undo()
    assert project[0].layer_count == 2


def test_shift_new_on_a_single_layer_says_so(rig):
    app, push, _, _ = layered_rig(rig)
    push.hold_button(Btn.SHIFT, True)
    push.press_button(Btn.NEW)
    pump(app)
    push.hold_button(Btn.SHIFT, False)
    assert "nothing to remove" in app.message


def test_undoing_a_layer_restores_the_audio(rig):
    app, push, engine, project = layered_rig(rig)
    before = np.array(project[0].audio, copy=True)
    push.press_button(Btn.NEW)
    pump(app)
    record_take(app, engine, bars=1)
    assert not np.array_equal(project[0].audio, before)
    app.undo()
    assert np.array_equal(project[0].audio, before)
    assert project[0].layer_count == 1


def test_a_layer_is_exactly_the_takes_bar_length(rig):
    app, push, engine, project = layered_rig(rig, bars=2)
    push.press_button(Btn.NEW)
    pump(app)
    record_take(app, engine, bars=2)
    sample = project[0]
    assert not project.mismatched(sample)
    assert all(layer.shape[0] == sample.audio.shape[0] for layer in sample.layers)


def test_layering_an_unarranged_take_warns(rig):
    app, push, engine, project = rig
    project.put(0, take(engine), bars=1)  # plays nowhere
    app.goto_sample(0)
    push.press_button(Btn.NEW)
    pump(app)
    assert "not arranged" in app.message


def test_new_twice_cancels_the_layer_take(rig):
    app, push, _, project = layered_rig(rig)
    push.press_button(Btn.NEW)
    pump(app)
    push.press_button(Btn.NEW)
    pump(app)
    assert not app.mode._layering
    assert project[0].layer_count == 1


def test_the_display_counts_the_layers(rig):
    app, _, engine, project = layered_rig(rig)
    project[0].add_layer(take(engine))
    assert any("2 layers" in line for line in app.status_lines())


def test_layers_round_trip_through_a_save(rig, tmp_path):
    _, _, engine, project = rig
    project.put(0, take(engine, value=0.1), bars=1)
    project[0].add_layer(take(engine, value=0.25))
    project.save(tmp_path / "layered")
    loaded = Project.load(tmp_path / "layered", samplerate=SR)
    assert loaded[0].layer_count == 2
    mid = len(loaded[0].audio) // 2
    assert float(loaded[0].audio[mid, 0]) == pytest.approx(0.35, abs=1e-3)
    # ...and can still be peeled back after a reload.
    assert loaded[0].remove_layer()
    assert float(loaded[0].audio[mid, 0]) == pytest.approx(0.1, abs=1e-3)


def test_a_take_with_missing_layer_files_still_loads(rig, tmp_path):
    _, _, engine, project = rig
    project.put(0, take(engine, value=0.1), bars=1)
    project[0].add_layer(take(engine, value=0.25))
    directory = tmp_path / "lossy"
    project.save(directory)
    for path in (directory / "samples").glob("slot_000_L*.wav"):
        path.unlink()
    loaded = Project.load(directory, samplerate=SR)
    assert loaded[0] is not None  # the take survives
    assert loaded[0].layers == []  # it just cannot be peeled back
    mid = len(loaded[0].audio) // 2
    assert float(loaded[0].audio[mid, 0]) == pytest.approx(0.35, abs=1e-3)


def test_applying_edits_forgets_the_layer_breakdown(rig):
    _, _, engine, project = rig
    project.put(0, take(engine, value=0.1), bars=1)
    project[0].add_layer(take(engine, value=0.25))
    project[0].set_edits(project[0].edits.with_value("reverse", True))
    project[0].apply_edits()
    assert project[0].layers == []
    assert project[0].layer_count == 1


def test_repairing_a_take_forgets_the_layer_breakdown(rig):
    _, _, engine, project = rig
    project.put(0, take(engine, value=0.1), bars=1)
    project[0].add_layer(take(engine, value=0.25))
    project.bpm = 90.0  # now the take no longer fits its bar
    assert project.repair(0)
    assert project[0].layers == []


def test_the_format_version_moved_for_layers():
    assert FORMAT_VERSION >= 5
