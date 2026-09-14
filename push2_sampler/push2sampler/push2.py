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
    ALL_BUTTON_CCS,
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
class StripEvent:
    """The touch strip moved (IN-07).

    ``position`` is 0.0 at the bottom of the strip and 1.0 at the top, from the
    14-bit pitch bend the strip sends.  ``touched`` is False for the
    spring-back-to-centre message the strip sends when a finger leaves it, which
    must not be read as "you asked for the middle of the song".

    **Unverified against hardware.**  That the strip speaks pitch bend at all
    comes from Ableton's document rather than from a device; `--selftest` has a
    step for it and has never been completed.  Everything downstream is written
    so that a strip which turns out to send something else is inert rather than
    wrong.
    """

    position: float
    touched: bool = True


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
        #: Set by program_palette; the simulator and the tests read it.
        self.palette_programmed = False
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

    def send_pad_raw(self, index: int, value: int, channel: int = 0) -> None:
        """Light a pad *now*, bypassing the dedupe cache, on any MIDI channel.

        The cache in :meth:`set_pad` is what makes a 30 Hz refresh cheap, but a
        diagnostic has to be able to send the same value twice and to try
        channels other than the static one -- see ``ledtest.py``.  Nothing in
        the normal render path should use this.
        """
        self.pad_leds[index] = -1
        try:
            self._send_pad_on(index, value, channel)
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

    def all_off(self) -> None:
        """Blank the whole surface, including LEDs this process never lit.

        :meth:`clear` can only turn off buttons it has a record of lighting,
        which in a fresh process is none of them.  So a run that crashed, or a
        diagnostic that lit things and exited, left LEDs on that nothing could
        reach.  This sends an explicit off to every pad and every button CC we
        know about, so starting the program always gives a clean surface.
        """
        self.invalidate_leds()
        for i in range(PAD_COUNT):
            self.set_pad(i, colors.OFF)
        for cc in ALL_BUTTON_CCS:
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

    def _send_pad_on(self, index: int, value: int, channel: int) -> None:
        """Like :meth:`_send_pad` but on an explicit channel.

        The default ignores the channel, which is right for every stand-in: only
        real hardware distinguishes them.
        """
        self._send_pad(index, value)

    def program_palette(self) -> None:
        """Upload the private palette entries.  A no-op with no hardware.

        Defined here rather than only on :class:`Push2` because callers reach
        for it polymorphically -- ``ledtest`` re-uploads mid-run, and a missing
        attribute there looked exactly like a device refusing the SysEx.
        """
        self.palette_programmed = True

    def _send_button(self, cc: int, value: int) -> None:  # pragma: no cover
        pass


class Push2(PushBase):
    """Real hardware, reached over the Push 2 *User* MIDI port."""

    def __init__(self, port_hint: str = "Push 2", prefer_user_port: bool = True,
                 port_name: str | None = None, listen_all: bool = True) -> None:
        super().__init__()
        self.port_hint = port_hint
        self.prefer_user_port = prefer_user_port
        #: Substring that forces one port, from ``--midi-port``.  Overrides the
        #: User-port preference in both directions.
        self.port_name = port_name
        #: Move output to whichever port the surface turns out to be on.
        #:
        #: Input tells us which port the device is using; output has no such
        #: signal, and guessing wrong means a surface that receives fine and
        #: stays dark (F-08 finding 8).  So when input arrives on a port we are
        #: not sending to, we follow it.  Off when ``port_name`` pins a port by
        #: hand -- an explicit choice is not something to second-guess.
        self.follow_input = port_name is None
        #: Count of messages seen per input port, for the reports.
        self.input_seen: dict[str, int] = {}
        self._pending_output: str | None = None
        #: Set when output has followed the input port, so it can be reported.
        self.followed_output: str | None = None
        #: Read from *every* Push input port rather than only the chosen one.
        #:
        #: A Push 2 routes its surface to one port or the other depending on
        #: which mode it is in, and on a device in Live mode the User port
        #: carries no input at all -- observed, not assumed (F-08 finding 5).
        #: Listening to both costs nothing, since only one of them sends, and
        #: it means the program works in either mode without being told which.
        self.listen_all = listen_all
        self._inports: list = []
        self._outport = None
        #: Port names actually opened, for the hardware report.
        self.chosen_input: str | None = None
        self.chosen_inputs: list[str] = []
        self.chosen_output: str | None = None

    @property
    def _inport(self):
        """The first input port.  Kept for callers that expect a single one."""
        return self._inports[0] if self._inports else None

    # -- lifecycle ---------------------------------------------------------
    def open(self, program_palette: bool = True) -> None:
        """Open the ports and upload our palette.

        ``program_palette=False`` is for the LED diagnostic, which has to see
        what the pads do *before* we touch the palette -- otherwise a broken
        upload and a dead surface are indistinguishable.
        """
        import mido  # imported lazily so the simulator needs no MIDI stack

        inputs = list(mido.get_input_names())
        in_name = self._pick(inputs, "input")
        out_name = self._pick(mido.get_output_names(), "output")
        self.chosen_input, self.chosen_output = in_name, out_name
        self._outport = mido.open_output(out_name)

        # Preferred port first, so chosen_input stays meaningful, then any
        # other Push port -- see listen_all.
        names = [in_name]
        if self.listen_all:
            names += [n for n in self._matches(inputs) if n != in_name]
        self._inports = []
        self.chosen_inputs = []
        for name in names:
            try:
                self._inports.append(
                    mido.open_input(
                        name,
                        # Bind the port name so we know where a message came
                        # from, which is the only signal for which port the
                        # surface is on.
                        callback=lambda msg, port=name: self._on_midi_from(port, msg),
                    )
                )
            except Exception:
                # One unopenable port is not a reason to fail: the other may be
                # the one carrying the surface.
                continue
            self.chosen_inputs.append(name)
        if not self._inports:
            raise RuntimeError(f"could not open any Push 2 MIDI input port from {names}")
        if program_palette:
            self.program_palette()
        # all_off, not clear: whatever lit the surface last may have been a
        # different process, and its LEDs are still on.
        self.all_off()

    def close(self) -> None:
        try:
            self.clear()
        except Exception:  # pragma: no cover - best effort on shutdown
            pass
        for port in [*self._inports, self._outport]:
            if port is not None:
                try:
                    port.close()
                except Exception:  # pragma: no cover
                    pass
        self._inports = []
        self._outport = None

    def _matches(self, names: list[str]) -> list[str]:
        return [n for n in names if self.port_hint.lower() in n.lower()]

    def _pick(self, names: list[str], kind: str) -> str:
        matches = self._matches(names)
        if not matches:
            raise RuntimeError(
                f"no Push 2 MIDI {kind} port found (looked for {self.port_hint!r} in {names})"
            )
        if self.port_name:
            wanted = [n for n in matches if self.port_name.lower() in n.lower()]
            if not wanted:
                raise RuntimeError(
                    f"no Push 2 MIDI {kind} port matching {self.port_name!r} "
                    f"(have {matches})"
                )
            return wanted[0]
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
        # Channel 1 (mido channel 0) means "static colour, no animation".
        self._send_pad_on(index, value, 0)

    def _send_pad_on(self, index: int, value: int, channel: int) -> None:
        if self._outport is None:
            return
        import mido

        self._outport.send(
            mido.Message(
                "note_on", channel=channel, note=index_to_note(index), velocity=value
            )
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
        self.palette_programmed = True

    def _on_midi_from(self, port_name: str, msg) -> None:
        """Inbound message, tagged with the port it arrived on."""
        self.input_seen[port_name] = self.input_seen.get(port_name, 0) + 1
        if self.follow_input and port_name != self.chosen_output:
            # Requested here, applied in poll_events: this runs on the MIDI
            # callback thread, and swapping the output port under the renderer
            # would race with it.
            self._pending_output = port_name
        self._on_midi(msg)

    def poll_events(self):
        """Apply any pending output switch, then drain as usual.

        Done here because this is called from the same thread as the rendering,
        so the swap cannot race with a write in progress.
        """
        pending, self._pending_output = self._pending_output, None
        if pending and pending != self.chosen_output:
            self._switch_output(pending)
        return super().poll_events()

    def _switch_output(self, name: str) -> None:
        """Send to ``name`` from now on, and repaint everything."""
        import mido

        try:
            port = mido.open_output(name)
        except Exception:
            return  # keep the one we have; it is no worse than before
        old, self._outport = self._outport, port
        if old is not None:
            try:
                old.close()
            except Exception:  # pragma: no cover
                pass
        self.chosen_output = name
        self.followed_output = name
        # A port we have never sent to has never had our palette, and knows
        # nothing of what we think is lit.
        self.program_palette()
        self.invalidate_leds()

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
    if kind == "pitchwheel":
        # The touch strip (IN-07).  mido reports pitch as -8192..8191, so the
        # strip's own range maps onto 0..1 with the centre at 0.5.
        raw = int(getattr(msg, "pitch", 0))
        position = (raw + 8192) / 16383.0
        return StripEvent(max(0.0, min(1.0, position)), touched=raw != 0)
    # polytouch (pad aftertouch), clock, ... ignored
    return None


class SimPush(PushBase):
    """Offline stand-in for the hardware; used by tests and ``--sim``."""

    def __init__(self) -> None:
        super().__init__()
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

    def touch_strip(self, position: float, touched: bool = True) -> None:
        """Move the touch strip, 0.0 at the bottom to 1.0 at the top (IN-07)."""
        self.inject(StripEvent(max(0.0, min(1.0, float(position))), touched))

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
