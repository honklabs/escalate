"""Command-line resolution: defaults, then the settings file, then the flags."""

import json

from push2sampler.cli import build_parser, resolve_settings


def resolve(*argv):
    return resolve_settings(build_parser().parse_args([*argv, "project"]))


def test_defaults_with_no_file_and_no_flags():
    settings = resolve("--no-settings")
    assert settings["samplerate"] == 48_000
    assert settings["count_in_beats"] == 4
    assert settings["monitor"] == "off"
    assert settings.warning is None


def test_a_flag_overrides_the_default():
    # 8000 is a perfectly good rate, and the one the test suite runs at; a
    # closed list of "allowed" rates used to throw it away silently.
    settings = resolve("--no-settings", "--samplerate", "8000")
    assert settings["samplerate"] == 8_000
    assert settings.warning is None


def test_flags_override_the_file_without_rewriting_it(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"count_in_beats": 8, "monitor": "on"}))
    settings = resolve("--settings", str(path), "--count-in", "2")
    assert settings["count_in_beats"] == 2  # the flag wins for this run
    assert settings["monitor"] == "on"  # and the file is still respected
    assert settings.dirty is False  # but nothing is written back
    assert json.loads(path.read_text())["count_in_beats"] == 8


def test_no_settings_ignores_the_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"count_in_beats": 9}))
    settings = resolve("--no-settings", "--settings", str(path))
    assert settings["count_in_beats"] == 4


def test_a_value_that_cannot_be_used_is_reported(tmp_path):
    settings = resolve("--no-settings", "--blocksize", "999")
    assert settings["blocksize"] == 256
    assert "blocksize=999 is not allowed" in settings.warning


def test_a_rejected_flag_does_not_hide_a_file_problem(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json")
    settings = resolve("--settings", str(path), "--blocksize", "999")
    assert "ignoring" in settings.warning  # the file
    assert "blocksize" in settings.warning  # and the flag


def test_an_int_flag_is_not_reported_as_refused():
    # 12 coerced to 12.0 is not a refusal; only a real change is.
    settings = resolve("--no-settings", "--rec-latency-ms", "12")
    assert settings["rec_latency_ms"] == 12.0
    assert settings.warning is None


def test_no_play_while_recording_is_an_override():
    assert resolve("--no-settings")["play_while_recording"] is True
    assert resolve("--no-settings", "--no-play-while-recording")[
        "play_while_recording"
    ] is False


def test_monitor_and_devices_come_through():
    settings = resolve(
        "--no-settings", "--monitor", "auto", "--monitor-gain", "0.5",
        "--input-device", "3", "--output-device", "4",
    )
    assert settings["monitor"] == "auto"
    assert settings["monitor_gain"] == 0.5
    assert settings["input_device"] == 3
    assert settings["output_device"] == 4
