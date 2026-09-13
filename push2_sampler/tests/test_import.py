"""NF-08: importing audio you already own.

The two things worth guarding are both refusals: it must not stretch audio to
fit the grid, and it must not pretend to read a format the machine has no codec
for. Both would be silent, and both would be wrong.
"""

from __future__ import annotations

import numpy as np
import pytest

from push2sampler import importer, wavio
from push2sampler.constants import DISPLAY_ROW_BOTTOM, Btn
from push2sampler.history import ImportSample
from push2sampler.project import Project

SR = 8000
BPM = 120.0
#: One bar at 120 BPM in 4/4 is two seconds.
FPBAR = int(SR * 2)


@pytest.fixture
def library(tmp_path):
    """A samples folder with a nested directory and a few files."""
    root = tmp_path / "samples"
    (root / "drums").mkdir(parents=True)
    wavio.write(root / "two_bars.wav", tone(FPBAR * 2), SR)
    wavio.write(root / "drums" / "kick.wav", tone(FPBAR // 8), SR)
    wavio.write(root / "odd.wav", tone(int(FPBAR * 3.5)), SR)
    (root / "notes.txt").write_text("not audio")
    (root / ".hidden.wav").write_bytes(b"nope")
    return root


def tone(frames, value=0.4):
    return np.full((frames, 1), value, dtype=np.float32)


def project():
    return Project(samplerate=SR, bpm=BPM)


# -- probing ---------------------------------------------------------------
def test_probe_reads_a_header_without_loading_the_audio(library):
    info = importer.probe(library / "two_bars.wav")
    assert info.readable
    assert info.frames == FPBAR * 2
    assert info.samplerate == SR
    assert info.channels == 1
    assert f"{info.seconds:.2f}" == "4.00"
    assert "two_bars.wav" in info.label


def test_probe_names_the_problem_rather_than_raising(tmp_path):
    missing = importer.probe(tmp_path / "gone.wav")
    assert not missing.readable
    assert "no such file" in missing.problem

    text = importer.probe(tmp_path / "notes.txt")
    assert not text.readable
    assert "not an audio file" in text.problem


def test_a_broken_file_is_a_problem_not_a_traceback(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"RIFFnot really a wave at all")
    info = importer.probe(broken)
    assert not info.readable
    assert info.problem            # some one-line reason
    assert "\n" not in info.problem


def test_a_missing_codec_says_so_and_names_the_fix(tmp_path, monkeypatch):
    """Without soundfile, a .flac is honestly unreadable."""
    monkeypatch.setattr(wavio, "_soundfile", lambda: None)
    flac = tmp_path / "pad.flac"
    flac.write_bytes(b"fLaC" + b"\0" * 64)
    info = importer.probe(flac)
    assert not info.readable
    assert "soundfile" in info.problem
    assert "pip install" in info.problem


def test_the_suffix_lists_do_not_overlap():
    assert not set(importer.NATIVE_SUFFIXES) & set(importer.SOUNDFILE_SUFFIXES)
    assert ".wav" in importer.ALL_SUFFIXES


# -- listing ---------------------------------------------------------------
def test_listing_separates_folders_from_audio_and_skips_the_rest(library):
    dirs, files = importer.listing(library)
    assert [d.name for d in dirs] == ["drums"]
    assert [f.name for f in files] == ["odd.wav", "two_bars.wav"]
    # notes.txt is not audio, and .hidden.wav is hidden
    assert all("notes" not in f.name for f in files)
    assert all(not f.name.startswith(".") for f in files)


def test_listing_a_missing_directory_is_empty_not_an_error(tmp_path):
    assert importer.listing(tmp_path / "nowhere") == ([], [])


# -- bar arithmetic --------------------------------------------------------
def test_bars_for_rounds_to_the_nearest_whole_bar():
    assert importer.bars_for(FPBAR * 2, BPM, SR) == (2, 2.0)
    claimed, exact = importer.bars_for(int(FPBAR * 3.5), BPM, SR)
    assert (claimed, round(exact, 2)) == (4, 3.5)


def test_a_very_short_file_still_claims_one_bar():
    """Zero-bar slots are not a thing, so a hit rounds up to one."""
    claimed, exact = importer.bars_for(200, BPM, SR)
    assert claimed == 1
    assert exact < 0.1


# -- importing -------------------------------------------------------------
def test_import_resamples_to_the_session_rate(tmp_path):
    """A 44.1k file in a 48k session: the frame count has to change."""
    src = tmp_path / "foreign.wav"
    wavio.write(src, tone(44100 * 4), 44100)      # 4 seconds
    proj = Project(samplerate=48_000, bpm=BPM)
    sample = importer.make_sample(proj, src, 0)
    assert sample.audio.shape[0] == pytest.approx(48_000 * 4, rel=0.001)
    assert sample.bars == 2                        # 4 s at 120 BPM
    assert not proj.mismatched(sample)


def test_an_off_grid_file_is_flagged_not_stretched(library):
    proj = project()
    sample = importer.make_sample(proj, library / "odd.wav", 0)
    proj.install(0, sample)
    assert sample.bars == 4                        # nearest whole bar
    assert sample.audio.shape[0] == int(FPBAR * 3.5)   # audio untouched
    assert proj.mismatched(sample)                 # and said so


def test_the_name_comes_from_the_file_stem(library):
    sample = importer.make_sample(project(), library / "two_bars.wav", 3)
    assert sample.name == "two_bars"
    assert sample.slot == 3


def test_a_long_file_name_is_trimmed_for_the_display(tmp_path):
    src = tmp_path / ("x" * 60 + ".wav")
    wavio.write(src, tone(FPBAR), SR)
    sample = importer.make_sample(project(), src, 0)
    assert len(sample.name) <= 16


def test_import_claims_the_session_tempo_as_its_source(library):
    """So the off-grid check compares against this session, not a tempo it
    never had."""
    proj = project()
    sample = importer.make_sample(proj, library / "two_bars.wav", 0)
    assert sample.source_bpm == proj.bpm
    assert sample.source_samplerate == proj.samplerate


def test_an_empty_file_is_refused_with_a_reason(tmp_path):
    src = tmp_path / "silent.wav"
    wavio.write(src, np.zeros((0, 1), dtype=np.float32), SR)
    with pytest.raises(ImportError) as caught:
        importer.make_sample(project(), src, 0)
    assert "no audio" in str(caught.value)


def test_load_raises_import_error_for_a_missing_codec(tmp_path, monkeypatch):
    monkeypatch.setattr(wavio, "_soundfile", lambda: None)
    flac = tmp_path / "pad.flac"
    flac.write_bytes(b"fLaC")
    with pytest.raises(ImportError) as caught:
        importer.load(flac, SR)
    assert "soundfile" in str(caught.value)


# -- undo ------------------------------------------------------------------
def test_an_import_is_undoable_and_redoable(library):
    from push2sampler.history import History

    proj = project()
    history = History()
    sample = importer.make_sample(proj, library / "two_bars.wav", 5)
    history.do(proj, ImportSample(5, sample, source=str(library / "two_bars.wav")))
    assert proj[5] is sample

    history.undo(proj)
    assert proj[5] is None

    history.redo(proj)
    assert proj[5] is sample       # the same object, not a re-read


def test_undoing_an_import_over_a_slot_puts_the_old_take_back(library):
    from push2sampler.history import History
    from push2sampler.project import Sample

    proj = project()
    existing = Sample(slot=2, bars=1, audio=tone(FPBAR))
    proj.install(2, existing)
    history = History()
    fresh = importer.make_sample(proj, library / "two_bars.wav", 2)
    history.do(proj, ImportSample(2, fresh))
    assert proj[2] is fresh
    history.undo(proj)
    assert proj[2] is existing


def test_the_import_label_names_the_slot(library):
    sample = importer.make_sample(project(), library / "two_bars.wav", 7)
    assert "slot 8" in ImportSample(7, sample).label
    assert "two_bars" in ImportSample(7, sample).label


# -- the browser, driven through the surface -------------------------------
@pytest.fixture
def rig(tmp_path, library):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    proj = project()
    engine = Engine(samplerate=SR, blocksize=64, in_channels=1, out_channels=2,
                    backend="offline", bpm=BPM, song_bars=proj.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    settings.set("samples_root", str(library))
    app = App(push, engine, proj, project_dir=tmp_path / "song", settings=settings)
    return app, push, engine, proj, library


def pump(app):
    for event in app.push.poll_events():
        app.handle(event)
    app.mode.on_tick()
    app.render()


def open_import(rig):
    app, push, engine, proj, library = rig
    app.shift = True
    push.press_button(Btn.BROWSE)
    pump(app)
    app.shift = False
    return app


def test_shift_browse_opens_the_import_browser(rig):
    app = open_import(rig)
    assert app.mode.name == "import"
    assert app.mode.directory == rig[4]


def test_browse_without_shift_still_opens_the_project_browser(rig):
    app, push, engine, proj, library = rig
    push.press_button(Btn.BROWSE)
    pump(app)
    assert app.mode.name == "browser"


def test_folders_are_white_and_audio_files_blue(rig):
    from push2sampler import colors

    app = open_import(rig)
    pads = app.push.pad_leds
    # entries are folders first, then files: drums, odd.wav, two_bars.wav
    assert pads[0] in (colors.WHITE.index, colors.WHITE_DIM.index)
    assert pads[1] in (colors.BLUE.index, colors.BLUE_DIM.index)
    assert pads[2] in (colors.BLUE.index, colors.BLUE_DIM.index)
    assert pads[3] == colors.OFF.index


def test_two_presses_enter_a_folder(rig):
    app = open_import(rig)
    app.push.press_pad(0)          # highlight "drums"
    pump(app)
    app.push.press_pad(0)          # and enter
    pump(app)
    assert app.mode.directory.name == "drums"
    assert [f.name for f in app.mode.files] == ["kick.wav"]


def test_two_presses_import_a_file_and_land_on_its_page(rig):
    app, push, engine, proj, library = rig
    open_import(rig)
    index = [e.name for e in app.mode.entries].index("two_bars.wav")
    push.press_pad(index)
    pump(app)
    push.press_pad(index)
    pump(app)
    assert app.mode.name == "sample"
    assert proj[0] is not None
    assert proj[0].name == "two_bars"
    assert proj[0].bars == 2


def test_importing_off_grid_audio_says_so_on_the_display(rig):
    app, push, engine, proj, library = rig
    open_import(rig)
    index = [e.name for e in app.mode.entries].index("odd.wav")
    push.press_pad(index)
    pump(app)
    push.press_pad(index)
    pump(app)
    assert "OFF GRID" in app.message


def test_the_import_is_one_undo_step(rig):
    app, push, engine, proj, library = rig
    open_import(rig)
    index = [e.name for e in app.mode.entries].index("two_bars.wav")
    push.press_pad(index)
    pump(app)
    push.press_pad(index)
    pump(app)
    assert proj[0] is not None
    push.press_button(Btn.UNDO)
    pump(app)
    assert proj[0] is None


def test_button_2_goes_up_a_directory(rig):
    app = open_import(rig)
    app.push.press_pad(0)
    pump(app)
    app.push.press_pad(0)          # into drums
    pump(app)
    assert app.mode.directory.name == "drums"
    app.push.press_button(DISPLAY_ROW_BOTTOM[1])
    pump(app)
    assert app.mode.directory == rig[4]


def test_button_3_returns_to_the_samples_root(rig):
    app = open_import(rig)
    app.push.press_button(DISPLAY_ROW_BOTTOM[4])   # home
    pump(app)
    assert app.mode.directory != rig[4]
    app.push.press_button(DISPLAY_ROW_BOTTOM[2])   # samples root
    pump(app)
    assert app.mode.directory == rig[4]


def test_session_leaves_the_import_browser(rig):
    app = open_import(rig)
    app.push.press_button(Btn.SESSION)
    pump(app)
    assert app.mode.name == "library"


def test_the_display_describes_the_highlighted_file(rig):
    app = open_import(rig)
    index = [e.name for e in app.mode.entries].index("two_bars.wav")
    app.push.press_pad(index)
    pump(app)
    lines = " ".join(app.mode.status_lines())
    assert "two_bars.wav" in lines
    assert "4.00s" in lines
    assert f"{SR} Hz" in lines
    assert "mono" in lines


def test_an_unreadable_file_does_not_import_and_says_why(rig, monkeypatch):
    app, push, engine, proj, library = rig
    (library / "pad.flac").write_bytes(b"fLaC" + b"\0" * 32)
    monkeypatch.setattr(wavio, "_soundfile", lambda: None)
    open_import(rig)
    app.mode.refresh()
    index = [e.name for e in app.mode.entries].index("pad.flac")
    push.press_pad(index)
    pump(app)
    push.press_pad(index)
    pump(app)
    assert proj.filled() == []                 # nothing imported
    assert "soundfile" in app.message
    assert app.mode.name == "import"           # and we are still here


def test_an_empty_folder_says_so(rig, tmp_path):
    app, push, engine, proj, library = rig
    empty = library / "empty"
    empty.mkdir()
    open_import(rig)
    app.mode._go(empty)
    pump(app)
    assert "nothing to import" in app.message


def test_import_target_is_the_first_empty_slot(rig):
    """Not "the slot you are on": a sample page only ever shows a filled slot,
    since goto_sample sends an empty one back to the library."""
    app, push, engine, proj, library = rig
    assert app.import_target() == 0


def test_import_target_skips_a_filled_slot(rig):
    from push2sampler.project import Sample

    app, push, engine, proj, library = rig
    proj.install(0, Sample(slot=0, bars=1, audio=tone(FPBAR)))
    assert app.import_target() == 1


# -- the command line ------------------------------------------------------
def test_cli_import_writes_the_project(tmp_path, library):
    from push2sampler.cli import main

    song = tmp_path / "cli-song"
    code = main([
        "--import", str(library / "two_bars.wav"),
        "--no-settings", "--samplerate", str(SR), str(song),
    ])
    assert code == 0
    reloaded = Project.load(song, samplerate=SR)
    assert reloaded[0] is not None
    assert reloaded[0].name == "two_bars"


def test_cli_import_honours_an_explicit_slot(tmp_path, library):
    from push2sampler.cli import main

    song = tmp_path / "cli-song"
    code = main([
        "--import", str(library / "two_bars.wav"), "--slot", "7",
        "--no-settings", "--samplerate", str(SR), str(song),
    ])
    assert code == 0
    assert Project.load(song, samplerate=SR)[6] is not None


def test_cli_import_refuses_an_out_of_range_slot(tmp_path, library, capsys):
    from push2sampler.cli import main

    code = main([
        "--import", str(library / "two_bars.wav"), "--slot", "9999",
        "--no-settings", str(tmp_path / "s"),
    ])
    assert code == 2
    assert "must be 1-" in capsys.readouterr().err


def test_cli_import_refuses_to_overwrite_a_filled_slot(tmp_path, library, capsys):
    from push2sampler.cli import main

    song = tmp_path / "cli-song"
    args = ["--import", str(library / "two_bars.wav"), "--slot", "1",
            "--no-settings", "--samplerate", str(SR), str(song)]
    assert main(args) == 0
    assert main(args) == 1
    assert "already holds" in capsys.readouterr().err


def test_cli_import_reports_a_bad_file(tmp_path, capsys):
    from push2sampler.cli import main

    code = main(["--import", str(tmp_path / "nope.wav"), "--no-settings",
                 str(tmp_path / "s")])
    assert code == 1
    assert "cannot import" in capsys.readouterr().err


def test_cli_import_mentions_off_grid_audio(tmp_path, library, capsys):
    from push2sampler.cli import main

    code = main(["--import", str(library / "odd.wav"), "--no-settings",
                 "--samplerate", str(SR), str(tmp_path / "s")])
    assert code == 0
    out = capsys.readouterr().out
    assert "off grid" in out
    assert "3.50 bars" in out


def test_the_first_press_never_acts_even_on_the_top_left_pad(rig):
    """A default selection of 0 made pad 0 import on a single press.

    Every other pad took two, and the action can be an import -- so the
    inconsistency was also the dangerous direction.
    """
    app, push, engine, proj, library = rig
    open_import(rig)
    assert app.mode.selected is None
    push.press_pad(0)                       # "drums", the first entry
    pump(app)
    assert app.mode.name == "import"        # highlighted, not entered
    assert app.mode.selected == 0
    assert app.mode.directory == library
    push.press_pad(0)
    pump(app)
    assert app.mode.directory.name == "drums"


def test_entering_a_folder_disarms_the_pad(rig):
    """Otherwise the pad under your finger acts again in the new folder."""
    app, push, engine, proj, library = rig
    open_import(rig)
    push.press_pad(0)
    pump(app)
    push.press_pad(0)                       # into drums
    pump(app)
    assert app.mode.selected is None


def test_nothing_is_highlighted_before_you_press(rig):
    from push2sampler import colors

    app = open_import(rig)
    pads = app.push.pad_leds
    assert colors.WHITE.index not in pads[:len(app.mode.entries)]
    assert colors.BLUE.index not in pads[:len(app.mode.entries)]
    assert "press a pad" in " ".join(app.mode.status_lines())


def test_moving_with_the_arrows_arms_from_nothing(rig):
    app = open_import(rig)
    app.push.press_button(Btn.DOWN)
    pump(app)
    assert app.mode.selected == 0
