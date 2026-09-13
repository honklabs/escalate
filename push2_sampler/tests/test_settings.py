import json

import pytest

from push2sampler.settings import (
    EDITABLE,
    EDITABLE_PAGES,
    SPECS,
    Settings,
    default_path,
)


def test_defaults_are_the_specs():
    settings = Settings()
    for name, spec in SPECS.items():
        assert settings[name] == spec.default
    assert settings.dirty is False
    assert settings.warning is None


def test_every_editable_setting_has_a_spec_and_a_label():
    for name in EDITABLE:
        assert name in SPECS
        assert SPECS[name].label


def test_each_settings_page_fits_the_button_row():
    for page in EDITABLE_PAGES:
        assert 0 < len(page) <= 8  # one per button under the display


def test_no_setting_appears_on_two_pages():
    assert len(EDITABLE) == len(set(EDITABLE))


def test_values_are_clamped_and_nonsense_falls_back():
    settings = Settings()
    assert settings.set("count_in_beats", 99) == 16  # clamped to the maximum
    assert settings.set("count_in_beats", -4) == 0
    assert settings.set("monitor_gain", "loud") == 1.0  # not a number: default
    assert settings.set("monitor", "sideways") == "off"  # not a choice: default
    assert settings.set("blocksize", 300) == 256  # not a choice: default


def test_numbers_are_coerced_to_their_kind():
    settings = Settings()
    assert settings.set("count_in_beats", 4.7) == 4
    assert isinstance(settings["count_in_beats"], int)
    assert settings.set("monitor_gain", "0.5") == pytest.approx(0.5)


def test_setting_marks_dirty_but_overrides_do_not():
    settings = Settings()
    settings.set("count_in_beats", 2)
    assert settings.dirty is True

    fresh = Settings()
    fresh.apply_overrides({"count_in_beats": 2, "monitor": "on"})
    assert fresh["count_in_beats"] == 2
    assert fresh["monitor"] == "on"
    assert fresh.dirty is False  # a command-line run does not rewrite the file


def test_unknown_names_are_ignored():
    settings = Settings()
    settings.apply({"nonsense": 3, "count_in_beats": 1})
    assert settings["count_in_beats"] == 1
    assert "nonsense" not in settings


def test_nudging_numbers_choices_and_flags():
    settings = Settings()
    spec = settings.spec("count_in_beats")
    assert spec.nudge(4, 2) == 6
    assert spec.nudge(0, -5) == 0  # floors at its minimum

    monitor = settings.spec("monitor")
    assert monitor.nudge("off", 1) == "auto"
    assert monitor.nudge("off", 9) == "on"  # stops at the end of the list
    assert monitor.cycle("on") == "off"  # pressing wraps

    flag = settings.spec("play_while_recording")
    assert flag.cycle(True) is False
    assert flag.nudge(True, 1) is False
    assert flag.nudge(True, 0) is True

    gain = settings.spec("monitor_gain")
    assert gain.nudge(1.0, 2) == pytest.approx(1.1)  # two 0.05 steps


def test_a_device_index_steps_up_from_default():
    spec = SPECS["input_device"]
    assert spec.format(None) == "default"
    assert spec.nudge(None, 1) == 0
    assert spec.nudge(0, 2) == 2
    assert spec.nudge(2, -1) == 1


def test_labels_read_like_a_display_line():
    settings = Settings()
    assert settings.label("count_in_beats") == "count-in 4 beats"
    assert settings.label("monitor") == "monitor off"
    assert settings.label("play_while_recording") == "play while rec on"
    assert settings.label("monitor_gain") == "mon gain 1"
    assert settings.label("input_device") == "in dev default"


# ----------------------------------------------------------------- files
def test_load_without_a_file_gives_defaults(tmp_path):
    settings = Settings.load(tmp_path / "nope.json")
    assert settings["count_in_beats"] == 4
    assert settings.warning is None
    assert settings.dirty is False


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings.load(path)
    settings.set("count_in_beats", 8)
    settings.set("monitor", "auto")
    assert settings.save() == path
    assert settings.dirty is False

    payload = json.loads(path.read_text())
    assert payload["count_in_beats"] == 8

    reloaded = Settings.load(path)
    assert reloaded["count_in_beats"] == 8
    assert reloaded["monitor"] == "auto"
    assert reloaded.dirty is False


def test_a_broken_file_falls_back_with_a_warning(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json at all")
    settings = Settings.load(path)
    assert settings["count_in_beats"] == 4  # defaults, not an exception
    assert settings.warning is not None
    assert "settings.json" in settings.warning


def test_a_file_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2, 3]")
    settings = Settings.load(path)
    assert settings.warning is not None
    assert settings["monitor"] == "off"


def test_bad_values_in_a_good_file_are_repaired(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"count_in_beats": 500, "monitor": "???", "junk": 1}))
    settings = Settings.load(path)
    assert settings["count_in_beats"] == 16
    assert settings["monitor"] == "off"
    assert settings.warning is None  # repairable, so not worth shouting about


def test_save_is_a_no_op_without_a_path():
    assert Settings().save() is None


def test_default_path_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_path() == tmp_path / "push2sampler" / "settings.json"
