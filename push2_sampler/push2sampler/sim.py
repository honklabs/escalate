"""Terminal simulator: drive the whole program without a Push 2 attached.

The app runs in a background thread exactly as it does with hardware; this REPL
injects control-surface events and prints the pad grid, so the mode logic,
transport and recorder can all be exercised (and demoed) on any machine.

Commands::

    p 12        press and release pad 12 (or "p 3,4" for col,row)
    hold 12     press pad 12 and keep holding   rel 12   release it
    hold tap    hold a button down (hold/rel take a button name too)
    b play      press a button by name (or just "play"; see BUTTONS)
    b1 .. b8    press the buttons under the display (claimed per mode)
    b undo      take back the last edit (shift on; b undo = redo)
    shift on    hold/release the Shift modifier
    t +4        turn the tempo encoder
    k +1        turn track encoder 1 (length / gain)
    k 3 +2      turn track encoder 3 (settings page: one per parameter)
    g           print the pad grid        s   print status
    wait 2.5    let the transport run for 2.5 seconds
    macro NAME cmd; cmd   define a sequence, then run it by NAME
    ?           print this list
    q           quit

Run a file of these instead of typing them with ``--script FILE``, and add
``--until-idle`` to wait for the sound to finish before quitting.
"""

from __future__ import annotations

import os
import shlex
import sys
import threading
import time

from .constants import (
    DISPLAY_ROW_BOTTOM,
    ENCODER_TEMPO,
    ENCODER_TRACK,
    Btn,
    xy_to_index,
)
from .push2 import SimPush

BUTTONS = {
    "play": Btn.PLAY,
    "stop": Btn.STOP,
    "record": Btn.RECORD,
    "rec": Btn.RECORD,
    "metronome": Btn.METRONOME,
    "click": Btn.METRONOME,
    "repeat": Btn.REPEAT,
    "loop": Btn.REPEAT,
    "mute": Btn.MUTE,
    "delete": Btn.DELETE,
    "session": Btn.SESSION,
    "library": Btn.SESSION,
    "back": Btn.SESSION,
    "left": Btn.LEFT,
    "up": Btn.UP,
    "down": Btn.DOWN,
    "setup": Btn.SETUP,
    "undo": Btn.UNDO,
    "quantize": Btn.FIXED_LENGTH,
    "accent": Btn.ACCENT,
    "device": Btn.DEVICE,
    "edit": Btn.DEVICE,
    "convert": Btn.CONVERT,
    "slice": Btn.CONVERT,
    "automate": Btn.AUTOMATE,
    "pattern": Btn.AUTOMATE,
    "scale": Btn.SCALE,
    "harmony": Btn.SCALE,
    "layout": Btn.LAYOUT,
    "about": Btn.LAYOUT,
    "info": Btn.LAYOUT,
    "duplicate": Btn.DUPLICATE,
    "dup": Btn.DUPLICATE,
    "tap": Btn.TAP_TEMPO,
    "new": Btn.NEW,
    "layer": Btn.NEW,
    "mix": Btn.MIX,
    "mixer": Btn.MIX,
    "solo": Btn.SOLO,
    "pageleft": Btn.PAGE_LEFT,
    "pageright": Btn.PAGE_RIGHT,
    "pl": Btn.PAGE_LEFT,
    "pr": Btn.PAGE_RIGHT,
    "clip": Btn.CLIP,
    "song": Btn.CLIP,
    "browse": Btn.BROWSE,
    "select": Btn.SELECT,
    "tag": Btn.SELECT,
    # IN-09.  The same button all the way through, so the alias reads the same
    # whether it is opening trim-by-ear or stepping it on.
    "trim": Btn.SELECT,
    "velocity": Btn.ACCENT,
    "fixed": Btn.FIXED_LENGTH,
    # Contextual buttons under the display, claimed per mode.
    "repair": DISPLAY_ROW_BOTTOM[0],
    "fit": DISPLAY_ROW_BOTTOM[0],
    **{f"b{i + 1}": cc for i, cc in enumerate(DISPLAY_ROW_BOTTOM)},
}

#: Every glyph ``SimPush.grid`` can print, so the grid is readable without
#: having to look up the palette.  Upper case is bright, lower case dim.
LEGEND = (
    "W m w white  G h g green  A a amber  R r red  B b blue  Y yellow  . off"
)

#: ANSI foreground per glyph, so the grid reads at a glance like the hardware
#: does.  Dim variants use the same hue at half intensity.
ANSI = {
    "W": "97", "m": "37", "w": "90",
    "G": "92", "h": "32", "g": "2;32",
    "A": "93", "a": "33",
    "R": "91", "r": "31",
    "B": "94", "b": "34",
    "Y": "93",
    ".": "90",
}
RESET = "\033[0m"

#: Longest --until-idle will wait.  A 64-bar loop never stops by itself, so this
#: is the difference between "waits for the sound to finish" and "hangs".
IDLE_LIMIT_S = 60.0


def colorize(grid: str) -> str:
    """Paint a grid of glyphs with ANSI colour."""
    out = []
    for char in grid:
        code = ANSI.get(char)
        out.append(f"\033[{code}m{char}{RESET}" if code else char)
    return "".join(out)


def use_color(stream=None) -> bool:
    """Colour only when it will be read by eyes, and when nobody said not to."""
    if os.environ.get("NO_COLOR"):
        return False
    stream = stream or sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:  # pragma: no cover - exotic streams
        return False


def _pad_index(token: str) -> int:
    if "," in token:
        col, row = (int(part) for part in token.split(",", 1))
        return xy_to_index(col, row)
    index = int(token)
    if not 0 <= index < 64:
        raise ValueError(f"pad index out of range: {index}")
    return index


def print_state(push: SimPush, app, color: bool | None = None) -> None:
    grid = push.grid()
    print()
    print(colorize(grid) if (use_color() if color is None else color) else grid)
    print(LEGEND)
    for line in app.status_lines():
        print(f"  {line}")
    sys.stdout.flush()


def run(app, push: SimPush, stream=None, until_idle: bool = False,
        quiet: bool = False) -> int:
    """Run the REPL until EOF or ``q``.  ``app`` must not be running yet.

    Returns a process exit status, so ``--script`` can be used in CI: 0 unless a
    command failed.  ``until_idle`` waits for the transport to stop once the
    script has run out, so a scripted demo need not end in a guessed ``wait``.
    """
    stream = stream or sys.stdin
    color = use_color()
    macros: dict[str, list[str]] = {}
    failures = 0
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    time.sleep(0.1)
    if not quiet:
        print(__doc__.split("Commands::")[1])
        print_state(push, app, color)
    try:
        for raw in stream:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                if not _run_line(line, app, push, macros):
                    break
            except Exception as exc:
                print(f"error: {exc}")
                failures += 1
                continue
            time.sleep(0.12)  # let the app thread react before we print
            if not quiet:
                print_state(push, app, color)
        if until_idle:
            _wait_for_idle(app)
            if not quiet:
                print_state(push, app, color)
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        thread.join(timeout=2.0)
    return 1 if failures else 0


def _wait_for_idle(app, limit_s: float = IDLE_LIMIT_S) -> bool:
    """Block until the transport stops, so a script need not guess a final wait.

    Applied once the script has run out, not between its lines -- a take
    finishing mid-script is not the end of the script.  Bounded, because a
    looping transport never goes idle on its own; returns whether it did.
    """
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        if not app.engine.is_playing and app.engine.rec_state == "idle":
            return True
        time.sleep(0.05)
    return False


def _run_line(line: str, app, push: SimPush, macros: dict[str, list[str]]) -> bool:
    """One input line, which may define or expand a macro."""
    parts = shlex.split(line)
    name = parts[0].lower()
    if name == "macro":
        if len(parts) < 2:
            raise ValueError("macro NAME cmd; cmd")
        label = parts[1].lower()
        body = [c.strip() for c in " ".join(parts[2:]).split(";") if c.strip()]
        if not body:
            raise ValueError(f"macro {label} needs at least one command")
        if label in BUTTONS or label in RESERVED:
            raise ValueError(f"{label!r} is already a command")
        macros[label] = body
        print(f"macro {label}: {len(body)} command(s)")
        return True
    if name in macros:
        for command in macros[name]:
            if not _run_line(command, app, push, macros):
                return False
            time.sleep(0.12)
        return True
    return _dispatch(line, app, push)


#: Command words a macro may not shadow.
RESERVED = frozenset({
    "p", "hold", "rel", "b", "shift", "t", "k", "g", "grid", "s", "status",
    "wait", "q", "quit", "exit", "macro", "?", "help",
})


def _dispatch(line: str, app, push: SimPush) -> bool:
    """Run one command; return False to quit."""
    parts = shlex.split(line)
    cmd, args = parts[0].lower(), parts[1:]
    if cmd in ("q", "quit", "exit"):
        return False
    if cmd in ("?", "help"):
        print(__doc__.split("Commands::")[1])
        return True
    if cmd == "p":
        push.press_pad(_pad_index(args[0]))
    elif cmd in ("hold", "rel"):
        # "hold 12" is a pad, "hold tap" a button -- the gestures that need a
        # button held down (Tap + tempo encoder) are otherwise unreachable here.
        name = args[0].lower()
        if name in BUTTONS:
            push.hold_button(BUTTONS[name], cmd == "hold")
        elif cmd == "hold":
            push.inject_pad_press(_pad_index(args[0]))
        else:
            push.inject_pad_release(_pad_index(args[0]))
    elif cmd == "b":
        name = args[0].lower()
        if name not in BUTTONS:
            raise ValueError(f"unknown button {name!r}; try: {', '.join(sorted(BUTTONS))}")
        push.press_button(BUTTONS[name])
    elif cmd == "shift":
        push.hold_button(Btn.SHIFT, args[0].lower() in ("on", "1", "true", "down"))
    elif cmd == "t":
        push.turn(ENCODER_TEMPO, int(args[0]))
    elif cmd == "k":
        if len(args) >= 2:
            which, delta = int(args[0]) - 1, int(args[1])
        else:
            which, delta = 0, int(args[0])
        if not 0 <= which < len(ENCODER_TRACK):
            raise ValueError(f"track encoder out of range: {which + 1}")
        push.turn(ENCODER_TRACK[which], delta)
    elif cmd in ("strip", "x"):
        # 0 at the bottom of the strip, 1 at the top; "strip off" is a finger
        # leaving it, which is a different thing from touching the middle.
        if args and args[0].lower() in ("off", "release", "up"):
            push.touch_strip(0.5, touched=False)
        else:
            push.touch_strip(float(args[0]))
    elif cmd in ("g", "grid", "s", "status"):
        pass  # state is printed after every command anyway
    elif cmd == "wait":
        time.sleep(max(0.0, float(args[0])))
    elif cmd in BUTTONS:
        push.press_button(BUTTONS[cmd])  # a bare button name works too: "play"
    else:
        raise ValueError(f"unknown command {cmd!r}")
    return True
