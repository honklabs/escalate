"""MIDI transport for the Push 2 control surface.

Two implementations of the same small interface are provided:

* :class:`Push2` talks to real hardware through ``mido`` / ``python-rtmidi``.
* :class:`SimPush` pretends to be a Push 2.  It records the LED state and lets
  events be injected, which is what the terminal simulator and the unit tests
  use.

Both deliver input as :class:`PadEvent` / :class:`ButtonEvent` /
:class:`EncoderEvent` objects through :meth:`PushBase.poll_events`, so the
application never sees raw MIDI.

Set :attr:`PushBase.capture_raw` to also keep the untranslated messages in
:attr:`PushBase.raw`.  The hardware probe uses that to learn what the device
really sends, rather than trusting the maps in :mod:`push2sampler.constants`.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass

from . import colors
from .constants import (
    ENCODER_CCS,
    ENCODER_TOUCH_NOTES,
    PAD_COUNT,
    SYSEX_PREFIX,
    SYSEX_REAPPLY_PALETTE,
    SYSEX_SET_PALETTE_ENTRY,
    encoder_delta,
    index_to_note,
    is_pad_note,
    note_to_index,
)


@dataclass(frozen=True)
class PadEvent:
    index: int
    pressed: bool
    velocity: int = 0


@dataclass(frozen=True)
class ButtonEvent:
    cc: int
    pressed: bool


@dataclass(frozen=True)
class EncoderEvent:
    cc: int
    delta: int


@dataclass(frozen=True)
class SurfaceOffline:
    """Queued when a write to the surface fails, so the app can say so.

    It travels the same queue as the input events because that is the one thing
    the app already drains every tick, and a failed write is news about the
    surface just as much as a button press is.
    """

    reason: str = ""


class PushBase:
    """Common behaviour: LED state caching plus an inbound event queue."""

    def __init__(self) -> None:
        self._events: queue.SimpleQueue = queue.SimpleQueue()
        self.pad_leds: list[int] = [0] * PAD_COUNT
        self.button_leds: dict[int, int] = {}
        #: When True, every inbound message is also queued on ``raw`` untouched.
        self.capture_raw = False
        self.raw: queue.SimpleQueue = queue.SimpleQueue()
        #: True once a write has failed.  The app keeps playing and retries; see
        #: ``App._supervise_surface``.
        self.offline = False

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:  # pragma: no cover - overridden
        pass

    def close(self) -> None:  # pragma: no cover - overridden
        pass

    def reopen(self) -> bool:
        """Try to get the surface back.  True once it is usable again."""
        try:
            self.close()
        except Exception:  # pragma: no cover - the port is already gone
            pass
        try:
            self.open()
        except Exception:
            return False
        self.invalidate_leds()
        self.offline = False
        return True

    def invalidate_leds(self) -> None:
        """Forget what we think is lit, so the next render sends everything.

        The dedupe in :meth:`set_pad` is what makes a 30 Hz refresh cheap, but a
        reconnected Push has dark LEDs and a stale cache would leave most of the
        grid black.  -1 is not a palette index, so every pad differs.
        """
        self.pad_leds = [-1] * PAD_COUNT
        self.button_leds = {}

    # -- output ------------------------------------------------------------
    def set_pad(self, index: int, color: int | colors.Color) -> None:
        """Light pad ``index`` with a palette entry (no-op if unchanged)."""
        value = int(color)
        if self.pad_leds[index] == value:
            return
        self.pad_leds[index] = value
        try:
            self._send_pad(index, value)
        except Exception as exc:
            self._went_offline(exc)

    def set_button(self, cc: int, value: int) -> None:
        """Set a button LED (no-op if unchanged)."""
        value = int(value)
        if self.button_leds.get(cc) == value:
            return
        self.button_leds[cc] = value
        try:
            self._send_button(cc, value)
        except Exception as exc:
            self._went_offline(exc)

    def _went_offline(self, exc: Exception) -> None:
        """A write failed: stop trying until someone reconnects us.

        The cache is invalidated here rather than on reconnect as well, because
        the write we just lost had already updated it -- leaving it would mean
        that pad never being resent.
        """
        self.invalidate_leds()
        if not self.offline:
            self.offline = True
            self._events.put(SurfaceOffline(str(exc)))

    def clear(self) -> None:
        """Turn every pad and every button LED we have touched off."""
        for i in range(PAD_COUNT):
            self.set_pad(i, colors.OFF)
        for cc in list(self.button_leds):
            self.set_button(cc, 0)

    # -- input -------------------------------------------------------------
    def poll_events(self) -> list[PadEvent | ButtonEvent | EncoderEvent]:
        """Drain and return every event received since the last call."""
        out: list[PadEvent | ButtonEvent | EncoderEvent] = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                return out

    def inject(self, event: PadEvent | ButtonEvent | EncoderEvent) -> None:
        """Queue an event as if it came from the hardware."""
        self._events.put(event)

    def next_raw(self, timeout: float = 0.0):
        """Pop one untranslated message, or None if none arrives in time."""
        try:
            return self.raw.get(timeout=timeout) if timeout else self.raw.get_nowait()
        except queue.Empty:
            return None

    def drain_raw(self) -> None:
        while self.next_raw() is not None:
            pass

    # -- subclass hooks ----------------------------------------------------
    def _send_pad(self, index: int, value: int) -> None:  # pragma: no cover
        pass

    def _send_button(self, cc: int, value: int) -> None:  # pragma: no cover
        pass


class Push2(PushBase):
    """Real hardware, reached over the Push 2 *User* MIDI port."""

    def __init__(self, port_hint: str = "Push 2", prefer_user_port: bool = True) -> None:
        super().__init__()
        self.port_hint = port_hint
        self.prefer_user_port = prefer_user_port
        self._inport = None
        self._outport = None
        #: Port names actually opened, for the hardware report.
        self.chosen_input: str | None = None
        self.chosen_output: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        import mido  # imported lazily so the simulator needs no MIDI stack

        in_name = self._pick(mido.get_input_names(), "input")
        out_name = self._pick(mido.get_output_names(), "output")
        self.chosen_input, self.chosen_output = in_name, out_name
        self._outport = mido.open_output(out_name)
        self._inport = mido.open_input(in_name, callback=self._on_midi)
        self.program_palette()
        self.clear()

    def close(self) -> None:
        try:
            self.clear()
        except Exception:  # pragma: no cover - best effort on shutdown
            pass
        for port in (self._inport, self._outport):
            if port is not None:
                try:
                    port.close()
                except Exception:  # pragma: no cover
                    pass
        self._inport = self._outport = None

    def _pick(self, names: list[str], kind: str) -> str:
        matches = [n for n in names if self.port_hint.lower() in n.lower()]
        if not matches:
            raise RuntimeError(
                f"no Push 2 MIDI {kind} port found (looked for {self.port_hint!r} in {names})"
            )
        if self.prefer_user_port:
            user = [n for n in matches if "user" in n.lower()]
            if user:
                return user[0]
            live = [n for n in matches if "live" in n.lower()]
            if live and len(matches) > len(live):
                return next(n for n in matches if n not in live)
        return matches[0]

    # -- output ------------------------------------------------------------
    def _send_pad(self, index: int, value: int) -> None:
        if self._outport is None:
            return
        import mido

        # Channel 1 (mido channel 0) means "static colour, no animation".
        self._outport.send(
            mido.Message("note_on", channel=0, note=index_to_note(index), velocity=value)
        )

    def _send_button(self, cc: int, value: int) -> None:
        if self._outport is None:
            return
        import mido

        self._outport.send(mido.Message("control_change", channel=0, control=cc, value=value))

    def program_palette(self) -> None:
        """Upload our private palette entries, then ask Push to apply them."""
        if self._outport is None:
            return
        import mido

        for color in colors.PALETTE:
            r, g, b = color.rgb
            data = [*SYSEX_PREFIX, SYSEX_SET_PALETTE_ENTRY, color.index]
            for component in (r, g, b, 0):  # 0 = unused white LED component
                data += [component & 0x7F, (component >> 7) & 0x01]
            self._outport.send(mido.Message("sysex", data=data))
        self._outport.send(
            mido.Message("sysex", data=[*SYSEX_PREFIX, SYSEX_REAPPLY_PALETTE])
        )

    # -- input -------------------------------------------------------------
    def _on_midi(self, msg) -> None:
        """``mido`` callback; runs on the rtmidi thread, so only queue work."""
        if self.capture_raw:
            self.raw.put(msg)
        event = translate_midi(msg)
        if event is not None:
            self._events.put(event)


def translate_midi(msg) -> PadEvent | ButtonEvent | EncoderEvent | None:
    """Turn one inbound ``mido`` message into an event, or ``None`` to ignore."""
    kind = msg.type
    if kind in ("note_on", "note_off"):
        if not is_pad_note(msg.note):
            # Encoder touch and the touch strip also arrive as notes.
            if msg.note in ENCODER_TOUCH_NOTES:
                return None
            return None
        pressed = kind == "note_on" and msg.velocity > 0
        return PadEvent(note_to_index(msg.note), pressed, msg.velocity)
    if kind == "control_change":
        if msg.control in ENCODER_CCS:
            delta = encoder_delta(msg.value)
            return EncoderEvent(msg.control, delta) if delta else None
        return ButtonEvent(msg.control, msg.value > 0)
    # polytouch (pad aftertouch), pitchwheel (touch strip), clock, ... ignored
    return None


class SimPush(PushBase):
    """Offline stand-in for the hardware; used by tests and ``--sim``."""

    def __init__(self) -> None:
        super().__init__()
        self.palette_programmed = False
        self.sent: list[tuple[str, int, int]] = []

    def open(self) -> None:
        self.palette_programmed = True

    def _send_pad(self, index: int, value: int) -> None:
        self.sent.append(("pad", index, value))

    def _send_button(self, cc: int, value: int) -> None:
        self.sent.append(("button", cc, value))

    # -- convenience for tests/REPL ---------------------------------------
    def feed_raw(self, msg) -> None:
        """Deliver a pretend inbound message, translated like the real thing."""
        if self.capture_raw:
            self.raw.put(msg)
        event = translate_midi(msg)
        if event is not None:
            self.inject(event)

    def press_pad(self, index: int, velocity: int = 100) -> None:
        self.inject_pad_press(index, velocity)
        self.inject_pad_release(index)

    def inject_pad_press(self, index: int, velocity: int = 100) -> None:
        self.inject(PadEvent(index, True, velocity))

    def inject_pad_release(self, index: int) -> None:
        self.inject(PadEvent(index, False, 0))

    def press_button(self, cc: int) -> None:
        self.inject(ButtonEvent(cc, True))
        self.inject(ButtonEvent(cc, False))

    def hold_button(self, cc: int, pressed: bool = True) -> None:
        self.inject(ButtonEvent(cc, pressed))

    def turn(self, cc: int, delta: int) -> None:
        self.inject(EncoderEvent(cc, delta))

    def grid(self) -> str:
        """Render the pad LEDs as eight lines of glyphs (top row first)."""
        rows = []
        for row in range(8):
            rows.append(
                " ".join(
                    colors.SIM_GLYPHS.get(self.pad_leds[row * 8 + col], "?")
                    for col in range(8)
                )
            )
        return "\n".join(rows)
