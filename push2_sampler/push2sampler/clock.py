"""NF-09: playing in time with something else.

Three roles, chosen in settings:

``internal``
    Our own tempo, which is everything that came before this module.
``midi_slave``
    Follow MIDI clock, start/stop/continue and song position from another
    device on its own MIDI port -- separate from the Push's surface port.
``midi_master``
    Emit 24 ppqn clock, start/stop and song position for someone else to
    follow.

Ableton Link sits behind :class:`LinkClock`, which imports its library lazily
and is absent-safe: with no ``link`` module installed, asking for it says so
and falls back to internal rather than failing to start.

Two decisions worth knowing about, because they are what makes slaving usable
rather than merely present:

**We never move the playhead to correct phase.** Jumping ``_pos`` to match an
incoming clock would make the transport stutter and could move it *backwards*,
cutting every sounding voice. Instead the tempo is nudged, and the position
converges on its own. So the engine needs no changes at all for this: the
slave only ever calls ``set_bpm``, which already refuses mid-take and already
clamps to a sane range.

**Phase is compared at tick arrival, not on our own clock tick.** When tick *n*
arrives the external source is at exactly ``n / 24`` beats -- an exact figure,
not a quantised one. Comparing on our 30 Hz UI tick instead would mean reading
a position quantised to 1/24 beat, which is 21 ms at 120 BPM and so can never
meet the 1 ms the plan asks for. The MIDI callback thread therefore samples the
engine position and the clock, and the arithmetic happens later on the UI
thread; nothing is computed on the callback thread but a timestamp.

The PLL was prototyped before any of this was written, as the plan told it to
be, and the prototype caught three wrong turns: comparing against a quantised
position, mixing an additive integral with a multiplicative proportional term
(which leaves a standing tempo offset -- 120 BPM settling at 122), and an
integral not scaled by the tick interval (which makes the loop half as fast at
half the tempo). The constants below are the ones that survived it.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

#: MIDI clock resolution: twenty-four ticks to the quarter note, by the standard.
PPQN = 24

#: Song-position-pointer units are sixteenth notes, six clock ticks each.
SPP_TICKS = 6

ROLES: tuple[str, ...] = ("internal", "midi_slave", "midi_master")

#: Proportional and integral gains on *phase* error, in beats.
#:
#: Validated against a synthetic 24 ppqn source: 0.2 ms steady-state at 120 BPM,
#: 0.17 ms after a cold start at the wrong tempo, 1.1 ms through a +/-3 % tempo
#: wobble, and never a backwards step.  Raising them tightens the wobble case
#: and costs a little jitter rejection.
KP = 2.0
KI = 0.5

#: How fast the free-running tempo estimate follows the measured tick interval.
INTERVAL_SMOOTHING = 0.15

#: Tick gaps outside this range are nonsense -- a paused source, a dropped USB
#: frame -- and are not fed to the estimator.
MIN_GAP_S = 0.002
MAX_GAP_S = 0.5

#: A silence longer than this means the source stopped; the next tick re-seeds
#: the tempo estimate instead of being smoothed into a stale one.
RESEED_AFTER_S = 1.0

#: Bound on the tick queue.  At 240 BPM that is about two seconds of clock, far
#: more than one UI tick's worth, and it cannot grow without limit if the UI
#: thread stalls.
MAX_PENDING_TICKS = 512

#: How often the master's thread looks for ticks that have come due.  One
#: millisecond of jitter on an emitted clock is well inside what a hardware
#: slave smooths out, and it costs a sleep rather than a spin.
MASTER_POLL_S = 0.001


@dataclass(frozen=True)
class ClockEvent:
    """Something the app should do about the clock.

    ``tempo`` carries a bpm; ``seek`` carries a bar; the transport events carry
    neither.  Returned rather than acted on so the clock never touches the
    engine itself -- the app owns that, and owns saying no.
    """

    kind: str          # "start" | "continue" | "stop" | "seek" | "tempo"
    bpm: float = 0.0
    bar: int = 0


class Clock:
    """The interface every role implements.  This one is the internal clock."""

    role = "internal"

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def bind(self, engine) -> None:
        """Hand over the engine, for clocks that read it off the UI thread."""
        pass

    def poll(self, engine) -> list[ClockEvent]:
        """Called on the UI tick.  Returns what the transport should do."""
        return []

    @property
    def status(self) -> str:
        """One short line for the display."""
        return "internal"

    @property
    def problem(self) -> str:
        """Why this clock is not doing its job, or empty when it is."""
        return ""


class InternalClock(Clock):
    """Our own tempo.  Explicit, so ``make_clock`` always returns something."""


# ---------------------------------------------------------------------------
# following someone else
# ---------------------------------------------------------------------------
class MidiClockSlave(Clock):
    """Follow MIDI clock with a phase-locked loop on tempo alone."""

    role = "midi_slave"

    def __init__(self, port_name: str = "", port=None, beats_per_bar: int = 4,
                 kp: float = KP, ki: float = KI,
                 smoothing: float = INTERVAL_SMOOTHING, engine=None,
                 now=time.monotonic) -> None:
        self.port_name = port_name
        self._engine = engine
        #: Where "now" comes from.  Injectable so the loop can be driven
        #: deterministically in tests -- the whole point of this class is its
        #: behaviour over simulated minutes, which wall-clock tests cannot show.
        self._now = now
        self.beats_per_bar = beats_per_bar
        self.kp, self.ki, self.smoothing = kp, ki, smoothing
        self._port = port
        self._problem = ""
        #: (tick index, arrival time, engine position in beats) from the MIDI
        #: thread; drained on the UI thread.
        self._pending: deque = deque(maxlen=MAX_PENDING_TICKS)
        self._transport: deque = deque(maxlen=64)
        self._lock = threading.Lock()
        self._ticks = 0
        self._interval = 0.0
        self._seeded = False
        self._integral = 0.0
        self._last_arrival: float | None = None
        self.bpm = 0.0
        self.locked = False
        self.error_beats = 0.0
        self.running = False

    # -- lifecycle ---------------------------------------------------------
    def bind(self, engine) -> None:
        self._engine = engine

    def open(self) -> None:
        if self._port is not None:
            return
        try:
            import mido
        except Exception as exc:
            self._problem = f"mido is not available: {exc}"
            return
        names = list(mido.get_input_names())
        chosen = _pick_port(names, self.port_name)
        if chosen is None:
            self._problem = (
                f"no MIDI input matching {self.port_name!r}"
                if self.port_name else "no MIDI input to take clock from"
            )
            return
        try:
            self._port = mido.open_input(chosen, callback=self._on_message)
        except Exception as exc:
            self._problem = f"could not open {chosen}: {exc}"
            return
        self.port_name = chosen

    def close(self) -> None:
        port, self._port = self._port, None
        if port is not None:
            try:
                port.close()
            except Exception:  # pragma: no cover - the port is already gone
                pass

    # -- the MIDI thread ---------------------------------------------------
    def _on_message(self, msg) -> None:
        """Timestamp and queue.  Deliberately does no arithmetic.

        Runs on the MIDI callback thread, so the only engine access is one
        float read -- the same kind of read the UI thread already makes of the
        transport -- and everything derived from it happens in ``poll``.
        """
        kind = getattr(msg, "type", "")
        if kind == "clock":
            now = self._now()
            beats = self._our_beats()
            if beats is None:
                return          # nothing to compare against yet
            with self._lock:
                self._ticks += 1
                self._pending.append((self._ticks, now, beats))
            return
        if kind in ("start", "continue", "stop", "songpos"):
            with self._lock:
                self._transport.append(msg)

    def _our_beats(self) -> float | None:
        """Where the transport is, read at tick arrival.

        Two attribute reads on the engine, from the MIDI callback thread.  That
        is sound for the same reason the UI thread's reads are: the callback is
        the sole writer of transport state, and an ``Intent`` is immutable and
        published by a single assignment, so a reader sees one coherent value
        or the other and never a torn one.

        Reading it *here* rather than caching it on the UI tick is the point.
        A value refreshed at 30 Hz is up to 33 ms stale, which is far larger
        than the error being measured -- it would make the loop chase its own
        sampling delay.
        """
        engine = self._engine
        if engine is None:
            return None
        frames_per_beat = engine.frames_per_beat or 1.0
        return engine.position_frames / frames_per_beat

    # -- the UI thread -----------------------------------------------------
    def poll(self, engine) -> list[ClockEvent]:
        self._engine = engine
        with self._lock:
            ticks = list(self._pending)
            self._pending.clear()
            transport = list(self._transport)
            self._transport.clear()

        events: list[ClockEvent] = []
        for msg in transport:
            events.extend(self._transport_event(msg))

        for index, arrival, our_beats in ticks:
            self._advance(index, arrival, our_beats)
        if ticks and self.bpm:
            events.append(ClockEvent("tempo", bpm=self.bpm))
        if self._last_arrival is not None:
            if self._now() - self._last_arrival > RESEED_AFTER_S:
                # The source went quiet.  Stay where we are rather than
                # freewheeling on a stale estimate.
                self.locked = False
        return events

    def _transport_event(self, msg) -> list[ClockEvent]:
        kind = getattr(msg, "type", "")
        if kind == "start":
            self._reset_phase()
            self.running = True
            return [ClockEvent("start", bar=0)]
        if kind == "continue":
            self.running = True
            return [ClockEvent("continue")]
        if kind == "stop":
            self.running = False
            self.locked = False
            return [ClockEvent("stop")]
        if kind == "songpos":
            pos = int(getattr(msg, "pos", 0))
            bar = spp_to_bar(pos, self.beats_per_bar)
            self._reset_phase(ticks=pos * SPP_TICKS)
            return [ClockEvent("seek", bar=bar)]
        return []

    def _reset_phase(self, ticks: int = 0) -> None:
        """Line the tick count up with a known position, without a jump.

        Start and song-position both say where the external source *is*, which
        the transport is about to be moved to anyway, so the phase error after
        one of these is zero by construction rather than something to unwind.
        """
        with self._lock:
            self._ticks = ticks
            self._pending.clear()
        self._integral = 0.0
        self.error_beats = 0.0

    def _advance(self, index: int, arrival: float, our_beats: float) -> None:
        """One tick's worth of the loop.  This is the whole PLL.

        ``index`` is *that tick's* number, not the latest one.  A UI pass
        usually drains one or two ticks but can drain more, and comparing every
        one of them against the current tick count overstates where the
        external source was for all but the last -- which showed up as a
        constant 15 mbeat offset the integrator could not remove, because it
        was not an error the loop could act on.
        """
        last = self._last_arrival
        self._last_arrival = arrival
        if last is not None:
            gap = arrival - last
            if MIN_GAP_S < gap < MAX_GAP_S:
                if self._seeded and gap < RESEED_AFTER_S:
                    self._interval += self.smoothing * (gap - self._interval)
                else:
                    # First measurement, or the first after a silence: take it
                    # outright.  Crawling toward it from a stale tempo is what
                    # made a cold start at double the true tempo take fifteen
                    # ticks to converge, and that is tens of milliseconds of
                    # error at slow tempos.
                    self._interval = gap
                    self._seeded = True
            elif gap >= MAX_GAP_S:
                self._seeded = False
        if not self._seeded or self._interval <= 0:
            return

        free_bpm = 60.0 / (self._interval * PPQN)
        error = index / PPQN - our_beats
        self.error_beats = error
        # Scaled by the tick interval so the loop behaves the same at any
        # tempo, instead of being half as fast at half the tempo.
        self._integral = _clamp(
            self._integral + error * self._interval * PPQN * 0.5, -0.5, 0.5
        )
        # Both corrections multiplicative, so both vanish at zero error.  An
        # additive integral leaves a standing tempo offset: 120 BPM settled at
        # 122 in the prototype.
        self.bpm = _clamp(
            free_bpm * (1.0 + self.kp * error + self.ki * self._integral), 40.0, 240.0
        )
        self.locked = abs(error) < 0.01

    # -- reporting ---------------------------------------------------------
    @property
    def status(self) -> str:
        if self._problem:
            return f"clock slave: {self._problem}"
        if not self._seeded:
            return "clock slave: waiting for clock"
        state = "locked" if self.locked else "chasing"
        return f"clock slave {state} {self.bpm:.1f} BPM ({self.error_beats * 1000:+.0f} mbeat)"

    @property
    def problem(self) -> str:
        return self._problem


# ---------------------------------------------------------------------------
# being followed
# ---------------------------------------------------------------------------
class MidiClockMaster(Clock):
    """Emit 24 ppqn, start/stop, and a song position on each seek.

    Ticks are emitted from a thread that watches the engine's *own* position
    rather than the wall clock, so the clock we send follows the audio device's
    tempo exactly and cannot drift away from what is actually being heard.
    Sending MIDI from the audio callback would be the only more accurate
    option, and it is not an option: it allocates and it does IO.
    """

    role = "midi_master"

    def __init__(self, port_name: str = "", port=None) -> None:
        self.port_name = port_name
        self._port = port
        self._problem = ""
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sent = 0
        self._was_playing = False
        self.ticks_sent = 0

    def open(self) -> None:
        if self._port is None:
            try:
                import mido
            except Exception as exc:
                self._problem = f"mido is not available: {exc}"
                return
            names = list(mido.get_output_names())
            chosen = _pick_port(names, self.port_name)
            if chosen is None:
                self._problem = (
                    f"no MIDI output matching {self.port_name!r}"
                    if self.port_name else "no MIDI output to send clock to"
                )
                return
            try:
                self._port = mido.open_output(chosen)
            except Exception as exc:
                self._problem = f"could not open {chosen}: {exc}"
                return
            self.port_name = chosen

    def start_thread(self, engine) -> None:
        """Begin emitting.  Separate from ``open`` so tests can step it by hand."""
        if self._port is None or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(engine,), name="push2-clock", daemon=True
        )
        self._thread.start()

    def _run(self, engine) -> None:  # pragma: no cover - exercised by hand
        while not self._stop.is_set():
            try:
                self.emit_due(engine)
            except Exception:
                pass       # a clock that dies must not take the audio with it
            self._stop.wait(MASTER_POLL_S)

    def close(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=1.0)
        port, self._port = self._port, None
        if port is not None:
            try:
                port.close()
            except Exception:  # pragma: no cover
                pass

    # -- emitting ----------------------------------------------------------
    def emit_due(self, engine) -> int:
        """Send every tick the engine's position has reached.  Returns how many."""
        if self._port is None:
            return 0
        playing = bool(engine.is_playing)
        if playing and not self._was_playing:
            self._send("start")
            self._sent = self._tick_index(engine)
            self._was_playing = True
        elif not playing and self._was_playing:
            self._send("stop")
            self._was_playing = False
            return 0
        if not playing:
            return 0

        target = self._tick_index(engine)
        if target < self._sent:
            # The transport moved backwards -- a loop wrap or a seek.  Re-anchor
            # rather than emitting a burst to catch up, which would arrive as a
            # tempo spike at whatever is following us.
            self._sent = target
            return 0
        due = target - self._sent
        for _ in range(due):
            self._send("clock")
        self._sent = target
        self.ticks_sent += due
        return due

    def seek(self, bar: int, beats_per_bar: int = 4) -> None:
        """Tell whoever is following that the position moved."""
        if self._port is None:
            return
        self._send("songpos", pos=bar_to_spp(bar, beats_per_bar))

    def _tick_index(self, engine) -> int:
        frames_per_beat = engine.frames_per_beat or 1.0
        beats = max(0.0, engine.position_frames) / frames_per_beat
        return int(beats * PPQN)

    def _send(self, kind: str, **fields) -> None:
        try:
            import mido

            self._port.send(mido.Message(kind, **fields))
        except Exception as exc:
            self._problem = f"clock send failed: {exc}"

    @property
    def status(self) -> str:
        if self._problem:
            return f"clock master: {self._problem}"
        where = self.port_name or "no port"
        return f"clock master -> {where}"

    @property
    def problem(self) -> str:
        return self._problem


# ---------------------------------------------------------------------------
# Ableton Link
# ---------------------------------------------------------------------------
class LinkClock(Clock):
    """Ableton Link, when a ``link`` binding happens to be installed.

    Deliberately thin, and deliberately honest.  Link needs a native library
    that is not a dependency of this program and has never been available in
    any environment this code has run in, so what is here is the lazy import,
    the absent-safe fallback and the seam to build the rest behind -- not a
    tested Link implementation.  ``problem`` says so, rather than pretending.
    """

    role = "link"

    def __init__(self, bpm: float = 120.0, quantum: float = 4.0) -> None:
        self.bpm = bpm
        self.quantum = quantum
        self._link = None
        self._problem = ""

    def open(self) -> None:
        try:
            import link  # type: ignore
        except Exception as exc:
            self._problem = (
                f"Ableton Link is not installed ({exc}); "
                "staying on the internal clock"
            )
            return
        try:
            self._link = link.Link(self.bpm)
            self._link.enabled = True
        except Exception as exc:  # pragma: no cover - needs the library
            self._problem = f"Link would not start: {exc}"
            self._link = None

    def close(self) -> None:  # pragma: no cover - needs the library
        if self._link is not None:
            try:
                self._link.enabled = False
            except Exception:
                pass
        self._link = None

    def poll(self, engine) -> list[ClockEvent]:  # pragma: no cover - needs the library
        if self._link is None:
            return []
        state = self._link.captureAppSessionState()
        tempo = float(state.tempo())
        if abs(tempo - engine.transport.bpm) > 0.01:
            return [ClockEvent("tempo", bpm=tempo)]
        return []

    @property
    def status(self) -> str:
        if self._problem:
            return "link unavailable"
        return f"link {self.bpm:.1f} BPM"       # pragma: no cover

    @property
    def problem(self) -> str:
        return self._problem


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _pick_port(names: list[str], wanted: str):
    """A port whose name contains ``wanted``, else the first one, else None.

    Substring and case-insensitive, so "clock" finds "MIDI Clock Out 1".  Not
    an exact match: port names carry indices and vendor prefixes that nobody
    wants to type.
    """
    if not names:
        return None
    if wanted:
        for name in names:
            if wanted.lower() in name.lower():
                return name
        return None
    return names[0]


def spp_to_bar(pos: int, beats_per_bar: int = 4) -> int:
    """Song-position-pointer value to a bar index.

    SPP counts sixteenth notes, so a 4/4 bar is sixteen of them.  Fractions of
    a bar are floored: the transport seeks to bar lines, and landing mid-bar is
    not something it can represent.
    """
    per_bar = max(1, 4 * beats_per_bar)
    return max(0, int(pos) // per_bar)


def bar_to_spp(bar: int, beats_per_bar: int = 4) -> int:
    """The inverse, clamped to the 14 bits an SPP message carries."""
    per_bar = max(1, 4 * beats_per_bar)
    return _clamp_int(max(0, int(bar)) * per_bar, 0, 16383)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def make_clock(role: str, port_name: str = "", beats_per_bar: int = 4,
               bpm: float = 120.0) -> Clock:
    """The clock for a role name.  An unknown role is internal, not an error."""
    if role == "midi_slave":
        return MidiClockSlave(port_name=port_name, beats_per_bar=beats_per_bar)
    if role == "midi_master":
        return MidiClockMaster(port_name=port_name)
    if role == "link":
        return LinkClock(bpm=bpm)
    return InternalClock()
