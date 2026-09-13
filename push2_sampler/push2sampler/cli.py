"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .app import App
from .audio import Engine
from .project import Project
from .settings import Settings

EXAMPLES = """\
examples:
  python -m push2sampler my-song
      Play. Records into ./my-song, which is created if it does not exist.

  python -m push2sampler --sim --no-settings my-song
      No hardware at all: drive the whole program from this terminal, and
      leave the real settings file alone.

  python -m push2sampler --bounce mix.wav my-song
      Render the song to a WAV and exit. Needs no Push and no audio device.

first time with a Push 2 plugged in:
  python -m push2sampler doctor       what is installed, and what is missing
  python -m push2sampler --selftest   check this program's hardware guesses
  python -m push2sampler --calibrate  measure your input latency
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="push2sampler",
        description="Sample library / looper for the Ableton Push 2.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "project", nargs="?", default=None,
        help="project directory (created if missing; default: the last one "
             "used, else ./song).  The word 'doctor' runs the diagnostics.",
    )
    parser.add_argument(
        "--version", action="version", version=f"push2sampler {__version__}",
    )
    parser.add_argument("--bpm", type=float, default=None, help="tempo override")
    # Everything below defaults to None so that "not given on the command line"
    # is distinguishable from "given the same value as the settings file".
    parser.add_argument("--settings", default=None, help="settings file to use")
    parser.add_argument(
        "--no-settings", action="store_true",
        help="ignore the settings file: defaults plus whatever is on this command line",
    )
    parser.add_argument("--samplerate", type=int, default=None)
    parser.add_argument("--blocksize", type=int, default=None)
    parser.add_argument("--in-channels", type=int, default=None)
    parser.add_argument("--out-channels", type=int, default=None)
    parser.add_argument("--input-device", default=None, help="audio input device index")
    parser.add_argument("--output-device", default=None, help="audio output device index")
    parser.add_argument(
        "--rec-latency-ms", type=float, default=None,
        help="trim this much from the start of each take to compensate input latency",
    )
    parser.add_argument(
        "--monitor", choices=("off", "auto", "on"), default=None,
        help="hear the input: never, only while recording, or always. "
             "Default off -- on speakers rather than headphones it feeds back. "
             "Shift+Metronome cycles it on the device.",
    )
    parser.add_argument(
        "--monitor-gain", type=float, default=None,
        help="level the monitored input is mixed in at (default 1.0)",
    )
    parser.add_argument(
        "--count-in", type=int, default=None,
        help="count-in beats before recording starts (default: 4)",
    )
    parser.add_argument(
        "--no-play-while-recording", action="store_true",
        help="do not play the existing song during a take",
    )
    parser.add_argument("--no-display", action="store_true", help="skip the Push 2 screen")
    parser.add_argument("--no-save", action="store_true", help="never write to the project dir")
    parser.add_argument(
        "--sim", action="store_true",
        help="run the terminal simulator instead of talking to hardware",
    )
    parser.add_argument(
        "--script", metavar="FILE", default=None,
        help="feed FILE to the simulator and exit (implies --sim); '-' is stdin",
    )
    parser.add_argument(
        "--until-idle", action="store_true",
        help="with --script, wait for the transport to stop before quitting",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="with --script, do not print the grid after every command",
    )
    parser.add_argument(
        "--doctor", action="store_true",
        help="print what is installed and what is missing, then exit",
    )
    parser.add_argument(
        "--calibrate", action="store_true",
        help="measure input latency by playing a click and listening for it",
    )
    parser.add_argument(
        "--bounce", metavar="OUT.WAV", default=None,
        help="render the project's song to a WAV and exit (needs no hardware)",
    )
    parser.add_argument(
        "--stems", metavar="DIR", default=None,
        help="render one WAV per filled slot into DIR and exit",
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="walk through the hardware with a real Push 2 and write a report "
             "of what it actually does (see --report)",
    )
    parser.add_argument(
        "--report", default="hardware-report.json",
        help="where --selftest writes its findings (default: ./hardware-report.json)",
    )
    parser.add_argument(
        "--led-test", action="store_true",
        help="the pads stay dark: find out which layer is at fault, and write "
             "led-report.json",
    )
    parser.add_argument(
        "--midi-probe", action="store_true",
        help="nothing lit and nothing received: report the facts about the MIDI "
             "link (backend, USB bus, both ports, both directions) to "
             "midi-report.json",
    )
    parser.add_argument(
        "--midi-port", default=None, metavar="NAME",
        help="force the Push MIDI port to the one whose name contains NAME "
             "(e.g. 'live' or 'user'); by default the User port is preferred "
             "for output and every Push port is listened to for input",
    )
    parser.add_argument("--list-ports", action="store_true", help="list MIDI ports and exit")
    parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    return parser


def resolve_settings(args) -> Settings:
    """Defaults, then the settings file, then this command line.

    Command-line values are applied as overrides: they steer this run without
    being written back to the file.
    """
    path = None if args.no_settings else (Path(args.settings) if args.settings else None)
    settings = Settings() if args.no_settings else Settings.load(path)
    overrides = {
        "samplerate": args.samplerate,
        "blocksize": args.blocksize,
        "in_channels": args.in_channels,
        "out_channels": args.out_channels,
        "input_device": _device(args.input_device),
        "output_device": _device(args.output_device),
        "rec_latency_ms": args.rec_latency_ms,
        "monitor": args.monitor,
        "monitor_gain": args.monitor_gain,
        "count_in_beats": args.count_in,
    }
    given = {name: value for name, value in overrides.items() if value is not None}
    if args.no_play_while_recording:
        given["play_while_recording"] = False
    # Say so when a value cannot be used, rather than quietly substituting the
    # default and leaving someone to wonder why their flag did nothing.
    refused = [
        f"{name}={value!r} is not allowed, using {settings.spec(name).coerce(value)!r}"
        for name, value in given.items()
        if _differs(settings.spec(name).coerce(value), value)
    ]
    settings.apply_overrides(given)
    if refused:
        settings.warning = "; ".join(filter(None, [settings.warning, *refused]))
    return settings


def _resolve_project(args, settings) -> str:
    """The project to open: what was asked for, else the last one, else ./song.

    Resuming needs the remembered directory to still be there -- a project on a
    drive that is no longer mounted should land you in a fresh ./song rather
    than creating an empty tree at a path you have forgotten about.
    """
    if args.project is not None:
        return args.project
    remembered = settings.ui.get("project")
    if remembered and Path(remembered).is_dir():
        return remembered
    return "song"


def _differs(stored, asked) -> bool:
    if isinstance(stored, (int, float)) and isinstance(asked, (int, float)):
        return abs(float(stored) - float(asked)) > 1e-9
    return stored != asked


def _device(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # "doctor" reads better than a flag and is what the docs say, but the
    # project argument is positional, so accept it as either.
    if args.doctor or args.project == "doctor":
        from . import doctor

        return doctor.run(args.project if args.project != "doctor" else "song")
    if args.script:
        args.sim = True

    if args.bounce or args.stems:
        return _render(args)
    if args.midi_probe:
        from .midiprobe import run_midi_probe

        return run_midi_probe()
    if args.led_test:
        from .ledtest import run_led_test

        return run_led_test()
    if args.selftest:
        from .selftest import run_selftest

        return run_selftest(Path(args.report))
    if args.list_ports:
        return _list_ports()
    if args.list_devices:
        return _list_devices()
    if args.calibrate:
        from . import calibrate

        settings = resolve_settings(args)
        return calibrate.run(settings, write=not args.no_settings)

    settings = resolve_settings(args)
    if settings.warning:
        print(settings.warning, file=sys.stderr)

    project_dir = Path(_resolve_project(args, settings))
    project = Project.load(project_dir, samplerate=settings["samplerate"])
    if args.bpm is not None:
        project.bpm = args.bpm

    engine = Engine(
        samplerate=settings["samplerate"],
        blocksize=settings["blocksize"],
        in_channels=settings["in_channels"],
        out_channels=settings["out_channels"],
        input_device=settings["input_device"],
        output_device=settings["output_device"],
        backend="null" if args.sim else "sounddevice",
        bpm=project.bpm,
        beats_per_bar=project.beats_per_bar,
        song_bars=project.song_bars,
        rec_latency_ms=settings["rec_latency_ms"],
        play_while_recording=settings["play_while_recording"],
        monitor=settings["monitor"],
        monitor_gain=settings["monitor_gain"],
    )

    if args.sim:
        from .push2 import SimPush

        push = SimPush()
    else:
        from .push2 import Push2

        push = Push2(port_name=args.midi_port)

    try:
        push.open()
    except Exception as exc:
        print(f"could not open the Push 2: {exc}", file=sys.stderr)
        print("(run with --sim to use the terminal simulator)", file=sys.stderr)
        return 2
    try:
        engine.start()
    except Exception as exc:
        push.close()
        print(f"could not start audio: {exc}", file=sys.stderr)
        return 3

    display = None
    if not args.sim and not args.no_display:
        from .display import open_display

        display = open_display()

    app = App(
        push,
        engine,
        project,
        project_dir=None if args.no_save else project_dir,
        display=display,
        settings=settings,
        log=print if args.sim else None,
    )

    app.restore_ui_state()

    if args.sim:
        from . import sim

        if args.script:
            stream = sys.stdin if args.script == "-" else open(args.script)
            try:
                return sim.run(app, push, stream,
                               until_idle=args.until_idle, quiet=args.quiet)
            finally:
                if stream is not sys.stdin:
                    stream.close()
        sim.run(app, push)
        return 0

    print(f"push2sampler: project {project_dir}, {project.bpm:.0f} BPM. Ctrl-C to quit.")
    app.run()
    return 0


def _render(args) -> int:
    """Offline bounce: no MIDI, no PortAudio, no hardware."""
    from .render import bounce_to, stems_to

    settings = resolve_settings(args)
    project = Project.load(
        Path(_resolve_project(args, settings)), samplerate=settings["samplerate"]
    )
    if args.bpm is not None:
        project.bpm = args.bpm
    if not project.filled():
        print(f"{_resolve_project(args, settings)} has no samples to render",
              file=sys.stderr)
        return 1
    if args.bounce:
        path = bounce_to(project, args.bounce)
        print(f"wrote {path}")
    if args.stems:
        for path in stems_to(project, args.stems):
            print(f"wrote {path}")
    return 0


def _list_ports() -> int:
    try:
        import mido
    except Exception as exc:
        print(f"mido is not installed: {exc}", file=sys.stderr)
        return 2
    print("MIDI inputs:")
    for name in mido.get_input_names():
        print(f"  {name}")
    print("MIDI outputs:")
    for name in mido.get_output_names():
        print(f"  {name}")
    return 0


def _list_devices() -> int:
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"sounddevice is not installed: {exc}", file=sys.stderr)
        return 2
    print(sd.query_devices())
    return 0
