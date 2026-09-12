"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app import App
from .audio import Engine
from .modes import COUNT_IN_BEATS
from .project import Project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="push2sampler",
        description="Sample library / looper for the Ableton Push 2.",
    )
    parser.add_argument(
        "project", nargs="?", default="song",
        help="project directory (created if missing; default: ./song)",
    )
    parser.add_argument("--bpm", type=float, default=None, help="tempo override")
    parser.add_argument("--samplerate", type=int, default=48_000)
    parser.add_argument("--blocksize", type=int, default=256)
    parser.add_argument("--in-channels", type=int, default=1)
    parser.add_argument("--out-channels", type=int, default=2)
    parser.add_argument("--input-device", default=None, help="audio input device name or index")
    parser.add_argument("--output-device", default=None, help="audio output device name or index")
    parser.add_argument(
        "--rec-latency-ms", type=float, default=0.0,
        help="trim this much from the start of each take to compensate input latency",
    )
    parser.add_argument(
        "--monitor", choices=("off", "auto", "on"), default="off",
        help="hear the input: never, only while recording, or always. "
             "Default off -- on speakers rather than headphones it feeds back. "
             "Shift+Metronome cycles it on the device.",
    )
    parser.add_argument(
        "--monitor-gain", type=float, default=1.0,
        help="level the monitored input is mixed in at (default 1.0)",
    )
    parser.add_argument(
        "--count-in", type=int, default=COUNT_IN_BEATS,
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
    parser.add_argument("--list-ports", action="store_true", help="list MIDI ports and exit")
    parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    return parser


def _device(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_ports:
        return _list_ports()
    if args.list_devices:
        return _list_devices()

    project_dir = Path(args.project)
    project = Project.load(project_dir, samplerate=args.samplerate)
    if args.bpm is not None:
        project.bpm = args.bpm

    engine = Engine(
        samplerate=args.samplerate,
        blocksize=args.blocksize,
        in_channels=args.in_channels,
        out_channels=args.out_channels,
        input_device=_device(args.input_device),
        output_device=_device(args.output_device),
        backend="null" if args.sim else "sounddevice",
        bpm=project.bpm,
        beats_per_bar=project.beats_per_bar,
        song_bars=project.song_bars,
        rec_latency_ms=args.rec_latency_ms,
        play_while_recording=not args.no_play_while_recording,
        monitor=args.monitor,
        monitor_gain=args.monitor_gain,
    )

    if args.sim:
        from .push2 import SimPush

        push = SimPush()
    else:
        from .push2 import Push2

        push = Push2()

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
        count_in_beats=args.count_in,
        log=print if args.sim else None,
    )

    if args.sim:
        from . import sim

        sim.run(app, push)
        return 0

    print(f"push2sampler: project {project_dir}, {project.bpm:.0f} BPM. Ctrl-C to quit.")
    app.run()
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
