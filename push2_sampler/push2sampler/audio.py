"""Audio engine: transport clock, bar scheduler, polyphonic mixer, recorder.

The engine owns a single duplex stream.  Everything musical happens inside
:meth:`Engine._process`, which is driven either by PortAudio (``backend=
"sounddevice"``), by a wall-clock thread (``backend="null"``, used by the
simulator), or directly by a caller (:meth:`Engine.process_offline`, used by
the tests).

Timing model
------------
``_pos`` is the transport position in frames.  It is allowed to be *negative*:
arming a recording rewinds to ``-count_in_beats`` worth of frames so the
metronome can count the player in, and frame 0 is both "bar 0" and "the first
recorded frame".

``_process`` walks the block in segments that never cross a beat, a bar, the
end of the song, or the end of a recording, so scheduled samples always start
on the exact frame of their bar rather than on a block boundary.

Threading model
---------------
The callback is the **only** writer of transport state (``_pos``, ``_voices``,
``_rec_*``, the boundary anchors).  The UI thread never takes a lock, which is
what keeps a slow UI pass from turning into an audible dropout: instead it

1. does any allocation up front (a take's buffer, a :class:`Voice`),
2. publishes an :class:`Intent` describing the state it is asking for, and
3. posts one command tuple, which the callback applies in full at the top of
   the next block.

Reads stay synchronous because the getters prefer the pending ``Intent`` over
the callback's state, so ``engine.play(); engine.is_playing`` is True right
away even though no audio has been rendered yet.  The callback clears the
intent once it has caught up, and only if the UI has not replaced it since.

Plain attributes the callback merely reads -- ``metronome``, ``loop``,
``monitor_gain``, ``play_while_recording`` -- are single words written
atomically by the UI thread.  A one-block-stale read of those is harmless, so
they are deliberately not commands.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass, replace

import numpy as np

#: Maximum simultaneously sounding voices; the oldest is faded out beyond this.
MAX_VOICES = 96
#: Extra voice slots reserved for voices that are fading out.
MAX_RELEASING = 16
#: Fade applied at the start and end of every voice, to stop edges clicking.
FADE_MS = 3.0
#: Longer fade used when a voice is cut short: Stop, a new take, voice stealing.
RELEASE_MS = 10.0
#: How fast the input peak meter falls back, per block.
METER_DECAY = 0.85

MONITOR_OFF = "off"
MONITOR_ON = "on"
#: Monitor only while a take is running, which is when a player needs to hear it.
MONITOR_AUTO = "auto"

#: Engine attributes :meth:`Engine.restart_stream` is allowed to change.
RESTARTABLE = ("input_device", "output_device", "blocksize", "in_channels", "out_channels")

IDLE = "idle"
COUNT_IN = "count_in"
RECORDING = "recording"


@dataclass
class Voice:
    """One sounding copy of a sample (or of the metronome click)."""

    buf: np.ndarray
    gain: float = 1.0
    slot: int = -1  # -1 for clicks, otherwise the sample slot
    pos: int = 0
    #: Frames of release fade applied so far; ``None`` while playing normally.
    releasing: int | None = None


@dataclass
class ScheduledSample:
    """An entry in the bar schedule handed to the engine."""

    slot: int
    buf: np.ndarray
    gain: float = 1.0


@dataclass(frozen=True)
class Intent:
    """Transport state the UI has asked for but the callback has not applied.

    Immutable, so publishing one is a single atomic attribute assignment.
    """

    running: bool
    rec_state: str
    pos: float
    bpm: float


@dataclass(frozen=True)
class Stats:
    """A snapshot of engine health, republished once per block."""

    #: Dropouts PortAudio has reported since the engine started.
    xruns: int = 0
    #: Peak absolute output sample in the last block.
    peak_out: float = 0.0
    #: Voices alive at the end of the last block.
    voices: int = 0
    #: Wall-clock time the last block took to render.
    callback_ms: float = 0.0
    #: Worst block so far; compare against the block's own duration as a budget.
    callback_ms_max: float = 0.0
    #: Input peak, with a slow fall-back so a meter is readable.
    input_peak: float = 0.0
    #: Input RMS over the last block.
    input_rms: float = 0.0


@dataclass
class Transport:
    samplerate: int = 48_000
    bpm: float = 120.0
    beats_per_bar: int = 4
    song_bars: int = 64

    @property
    def frames_per_beat(self) -> float:
        return 60.0 / self.bpm * self.samplerate

    @property
    def frames_per_bar(self) -> float:
        return self.frames_per_beat * self.beats_per_bar

    @property
    def song_frames(self) -> float:
        return self.frames_per_bar * self.song_bars


def make_click(samplerate: int, freq: float, channels: int, ms: float = 28.0,
               gain: float = 0.4) -> np.ndarray:
    """A short decaying sine used for the metronome and the count-in."""
    n = max(1, int(samplerate * ms / 1000.0))
    t = np.arange(n, dtype=np.float32) / samplerate
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * 45.0) * gain
    return np.repeat(wave.astype(np.float32)[:, None], channels, axis=1)


def make_fade(frames: int) -> tuple[np.ndarray, np.ndarray]:
    """Return matching ``(rise, fall)`` raised-cosine ramps of ``frames``.

    ``rise[0]`` is exactly 0 and ``fall[-1]`` is near 0, so a buffer faded with
    both starts and ends at silence.
    """
    phase = np.pi * np.arange(frames, dtype=np.float32) / max(1, frames)
    rise = (0.5 - 0.5 * np.cos(phase)).astype(np.float32)
    return rise, (1.0 - rise).astype(np.float32)


class Engine:
    """Transport, mixer and recorder.

    Public setters are safe to call from any thread: they post commands rather
    than touching the state the callback owns.  See the threading model above.
    """

    def __init__(
        self,
        samplerate: int = 48_000,
        blocksize: int = 256,
        in_channels: int = 1,
        out_channels: int = 2,
        input_device=None,
        output_device=None,
        backend: str = "sounddevice",
        bpm: float = 120.0,
        beats_per_bar: int = 4,
        song_bars: int = 64,
        rec_latency_ms: float = 0.0,
        play_while_recording: bool = True,
        monitor_gain: float = 1.0,
        monitor: str = MONITOR_OFF,
        null_input: str = "tone",
    ) -> None:
        self.transport = Transport(samplerate, bpm, beats_per_bar, song_bars)
        self.blocksize = blocksize
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.input_device = input_device
        self.output_device = output_device
        self.backend = backend
        self.rec_latency_frames = max(0, int(samplerate * rec_latency_ms / 1000.0))
        self.play_while_recording = play_while_recording
        self.monitor_gain = float(monitor_gain)
        #: off / on / auto -- see MONITOR_*.  Plain attribute: a stale read of it
        #: for one block is harmless.
        self.monitor = monitor
        #: Latches when the input clips; the UI clears it with take_clipped().
        self.input_clipped = False
        self.null_input = null_input

        self.events: queue.SimpleQueue = queue.SimpleQueue()
        self.metronome = False
        self.loop = True

        #: UI -> callback commands; drained at the top of every block.
        self._commands: queue.SimpleQueue = queue.SimpleQueue()
        self._intent: Intent | None = None
        self.stats = Stats()
        self._xruns = 0
        self._cb_ms_max = 0.0
        self._in_peak = 0.0
        self._in_rms = 0.0

        self._pos = 0.0
        self._running = False
        self._voices: list[Voice] = []
        self._schedule: tuple[tuple[ScheduledSample, ...], ...] = tuple(
            () for _ in range(song_bars)
        )
        self._last_beat: int | None = None
        self._last_bar: int | None = None

        self._rec_state = IDLE
        self._rec_buf: np.ndarray | None = None
        self._rec_written = 0
        self._rec_keep = 0
        self._rec_bars = 0

        self._click = make_click(samplerate, 1000.0, out_channels)
        self._click_accent = make_click(samplerate, 1600.0, out_channels, gain=0.5)
        self._null_phase = 0.0

        # Fade windows are built once; the callback only ever slices them.
        self._fade_frames = max(1, int(samplerate * FADE_MS / 1000.0))
        self._release_frames = max(1, int(samplerate * RELEASE_MS / 1000.0))
        self._fade_in, self._fade_out = make_fade(self._fade_frames)
        _, self._release_win = make_fade(self._release_frames)
        self._env_scratch = np.ones(blocksize, dtype=np.float32)

        self._stream = None
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        #: Slots heard in the most recent block; read by the UI for LED feedback.
        self.sounding: tuple[int, ...] = ()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.backend == "sounddevice":
            self._start_sounddevice()
        elif self.backend == "null":
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._null_loop, daemon=True)
            self._thread.start()
        elif self.backend == "offline":
            pass  # driven by process_offline()
        else:  # pragma: no cover
            raise ValueError(f"unknown audio backend {self.backend!r}")

    def _start_sounddevice(self) -> None:
        import sounddevice as sd

        self._stream = sd.Stream(
            samplerate=self.transport.samplerate,
            blocksize=self.blocksize,
            dtype="float32",
            channels=(self.in_channels, self.out_channels),
            device=(self.input_device, self.output_device),
            callback=self._sd_callback,
        )
        self._stream.start()

    def close(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._stop_stream()

    def _stop_stream(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # pragma: no cover - best effort
            pass
        self._stream = None

    def restart_stream(self, **changes) -> bool:
        """Reopen the stream with new devices, block size or channel counts.

        Returns True on success.  On failure the previous settings are put back,
        the old stream is reopened if it can be, and an ``("audio_error", msg)``
        event is raised: choosing a device that will not open must not take the
        instrument down with it.

        Sample rate is deliberately not changeable here -- every loaded take
        would need resampling first.
        """
        unknown = set(changes) - set(RESTARTABLE)
        if unknown:
            raise ValueError(f"cannot change {sorted(unknown)} on a running engine")
        previous = {name: getattr(self, name) for name in changes}
        if all(previous[name] == value for name, value in changes.items()):
            return True
        for name, value in changes.items():
            setattr(self, name, value)
        if self.backend != "sounddevice":
            return True  # nothing to reopen
        try:
            self._stop_stream()
            self._start_sounddevice()
            return True
        except Exception as exc:
            for name, value in previous.items():
                setattr(self, name, value)
            try:
                self._stop_stream()
                self._start_sounddevice()
            except Exception:  # pragma: no cover - the old device went away too
                pass
            self.events.put(("audio_error", str(exc)))
            return False

    def _sd_callback(self, indata, outdata, frames, _time, status):
        if status:
            self.note_status(status)
        self._process(outdata, indata, frames)

    def note_status(self, status) -> None:
        """Count a PortAudio status flag set as a dropout and announce it.

        Takes anything with the PortAudio flag attributes, so it is testable
        without a sound card.
        """
        flagged = any(
            getattr(status, name, False)
            for name in (
                "input_overflow",
                "input_underflow",
                "output_overflow",
                "output_underflow",
            )
        )
        if not flagged:
            return
        self._xruns += 1
        self.events.put(("xrun", self._xruns))

    def _null_loop(self) -> None:
        n = self.blocksize
        out = np.zeros((n, self.out_channels), dtype=np.float32)
        inp = np.zeros((n, self.in_channels), dtype=np.float32)
        period = n / self.transport.samplerate
        next_deadline = time.monotonic()
        while not self._stop_evt.is_set():
            self._fill_null_input(inp)
            self._process(out, inp, n)
            next_deadline += period
            delay = next_deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_deadline = time.monotonic()

    def _fill_null_input(self, inp: np.ndarray) -> None:
        """Synthesise stand-in input so simulated recordings are not silent."""
        if self.null_input != "tone":
            inp.fill(0.0)
            return
        n = inp.shape[0]
        sr = self.transport.samplerate
        step = 2 * np.pi * 220.0 / sr
        phase = self._null_phase + step * np.arange(n, dtype=np.float64)
        self._null_phase = float((phase[-1] + step) % (2 * np.pi))
        inp[:] = (np.sin(phase) * 0.25).astype(np.float32)[:, None]

    def process_offline(self, frames: int, indata: np.ndarray | None = None) -> np.ndarray:
        """Render ``frames`` frames synchronously; for tests and rendering."""
        out = np.zeros((frames, self.out_channels), dtype=np.float32)
        if indata is None:
            indata = np.zeros((frames, self.in_channels), dtype=np.float32)
        self._process(out, indata, frames)
        return out

    # ------------------------------------------------------------------
    # public state -- reads prefer a pending Intent over callback state
    # ------------------------------------------------------------------
    @property
    def bpm(self) -> float:
        intent = self._intent
        return intent.bpm if intent else self.transport.bpm

    @property
    def frames_per_beat(self) -> float:
        return 60.0 / self.bpm * self.transport.samplerate

    @property
    def frames_per_bar(self) -> float:
        return self.frames_per_beat * self.transport.beats_per_bar

    @property
    def song_frames(self) -> float:
        return self.frames_per_bar * self.transport.song_bars

    @property
    def is_playing(self) -> bool:
        intent = self._intent
        return intent.running if intent else self._running

    @property
    def rec_state(self) -> str:
        intent = self._intent
        return intent.rec_state if intent else self._rec_state

    @property
    def position_frames(self) -> float:
        intent = self._intent
        return intent.pos if intent else self._pos

    @property
    def current_bar(self) -> int:
        pos = self.position_frames
        if pos < 0:
            return -1
        return int(pos // self.frames_per_bar)

    @property
    def current_beat(self) -> int:
        """Beat index within the bar, or a negative count-in beat."""
        return int(math.floor(self.position_frames / self.frames_per_beat))

    @property
    def beat_phase(self) -> float:
        """Position inside the current beat, 0.0 -> 1.0."""
        return (self.position_frames / self.frames_per_beat) % 1.0

    @property
    def count_in_beats_left(self) -> int:
        if self.rec_state != COUNT_IN:
            return 0
        return max(0, int(math.ceil(-self.position_frames / self.frames_per_beat)))

    def set_schedule(self, schedule) -> None:
        """Install the bar -> samples map.  Replaced atomically by reference."""
        frozen = tuple(tuple(entries) for entries in schedule)
        if len(frozen) != self.transport.song_bars:
            raise ValueError("schedule must have one entry per song bar")
        self._schedule = frozen

    # ------------------------------------------------------------------
    # transport commands (UI thread: allocate, publish an intent, post)
    # ------------------------------------------------------------------
    def _post(self, command: tuple, intent: Intent | None = None) -> None:
        # The intent is published first so the callback can never clear an
        # intent it has not seen -- see _process.
        if intent is not None:
            self._intent = intent
        self._commands.put(command)

    def _intend(self, **changes) -> Intent:
        """An Intent like the current view of the engine, with ``changes``."""
        current = self._intent
        if current is None:
            current = Intent(
                running=self._running,
                rec_state=self._rec_state,
                pos=self._pos,
                bpm=self.transport.bpm,
            )
        return replace(current, **changes)

    def set_bpm(self, bpm: float) -> None:
        if self.rec_state != IDLE:
            return  # changing tempo mid-take would corrupt the take length
        bpm = max(40.0, min(240.0, float(bpm)))
        self._post(("bpm", bpm), self._intend(bpm=bpm))

    def play(self, from_bar: int = 0) -> None:
        pos = float(from_bar) * self.frames_per_bar
        self._post(("play", pos), self._intend(running=True, pos=pos))

    def stop(self) -> None:
        was_recording = self.rec_state != IDLE
        self._post(("stop",), self._intend(running=False, rec_state=IDLE, pos=0.0))
        if was_recording:
            self.events.put(("record_cancelled",))
        self.events.put(("stopped",))

    def toggle_play(self) -> None:
        if self.is_playing:
            self.stop()
        else:
            self.play(0)

    def arm_record(self, bars: int, count_in_beats: int = 4) -> None:
        """Rewind to the count-in and start capturing ``bars`` bars at bar 0."""
        bars = max(1, min(self.transport.song_bars, int(bars)))
        keep = int(round(bars * self.frames_per_bar))
        # The take buffer is allocated here, on the UI thread: it can be tens of
        # megabytes, which is exactly the work that must stay out of the callback.
        buf = np.zeros((keep + self.rec_latency_frames, self.in_channels), dtype=np.float32)
        count_in = max(0, int(count_in_beats))
        pos = -count_in * self.frames_per_beat
        state = COUNT_IN if count_in else RECORDING
        self._post(
            ("arm", bars, keep, buf, pos),
            self._intend(running=True, rec_state=state, pos=pos),
        )
        self.events.put(("record_armed", bars))

    def cancel_record(self) -> None:
        if self.rec_state == IDLE:
            return
        self._post(("cancel",), self._intend(running=False, rec_state=IDLE, pos=0.0))
        self.events.put(("record_cancelled",))

    def preview(self, buf: np.ndarray, gain: float = 1.0, slot: int = -1) -> None:
        """Play a one-shot outside the transport (auditioning a sample)."""
        self._post(("voice", Voice(buf, gain, slot=slot)))

    # ------------------------------------------------------------------
    # command application (callback thread only)
    # ------------------------------------------------------------------
    def _apply_commands(self) -> Intent | None:
        """Apply every queued command; return the intent we are satisfying."""
        seen = self._intent
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return seen
            self._apply(command)

    def _apply(self, command: tuple) -> None:
        kind = command[0]
        if kind == "play":
            self._pos = command[1]
            self._release_all(samples_only=True)
            self._arm_boundaries()
            self._running = True
        elif kind in ("stop", "cancel"):
            self._running = False
            self._rec_state = IDLE
            self._rec_buf = None
            self._pos = 0.0
            self._release_all()
            self._arm_boundaries()
        elif kind == "arm":
            _, bars, keep, buf, pos = command
            self._rec_bars = bars
            self._rec_keep = keep
            self._rec_buf = buf
            self._rec_written = 0
            self._pos = pos
            self._release_all()
            self._arm_boundaries()
            self._rec_state = COUNT_IN if pos < 0 else RECORDING
            self._running = True
        elif kind == "bpm":
            self.transport.bpm = command[1]
            self._reanchor()
        elif kind == "voice":
            self._add_voice(command[1])

    def _arm_boundaries(self) -> None:
        """Force the next processed segment to fire its beat and bar events."""
        self._last_beat = None
        self._last_bar = None

    def _reanchor(self) -> None:
        """Re-peg boundary tracking after a tempo change, so nothing retriggers."""
        self._last_beat = int(math.floor(self._pos / self.transport.frames_per_beat))
        self._last_bar = (
            int(self._pos // self.transport.frames_per_bar) if self._pos >= 0 else None
        )

    # ------------------------------------------------------------------
    # the audio callback
    # ------------------------------------------------------------------
    def _process(self, out: np.ndarray, inp: np.ndarray | None, frames: int) -> None:
        started = time.perf_counter()
        satisfying = self._apply_commands()
        out[:frames] = 0.0
        i = 0
        while i < frames:
            if self._running:
                self._fire_boundaries()
            n = min(frames - i, self._segment_limit(frames - i))
            seg = out[i : i + n]
            self._mix(seg, n)
            if inp is not None:
                if self._monitoring():
                    self._monitor(seg, inp[i : i + n])
                if self._rec_state == RECORDING:
                    self._capture(inp[i : i + n], n)
            if self._running:
                self._pos += n
                self._wrap_song()
            i += n
        np.clip(out[:frames], -1.0, 1.0, out=out[:frames])
        if inp is not None and frames:
            self._meter_input(inp[:frames])
        # Only drop the intent if the UI has not published a newer one since we
        # read it, which would otherwise lose that newer view for a block.
        if self._intent is satisfying:
            self._intent = None
        self._publish_stats(started, out[:frames])

    def _segment_limit(self, remaining: int) -> int:
        """How many frames we may render before the next musical boundary."""
        if not self._running:
            return remaining
        limit = remaining
        pos = self._pos
        fpb = self.transport.frames_per_beat
        next_beat = (math.floor(pos / fpb) + 1) * fpb
        limit = min(limit, max(1, int(math.ceil(next_beat - pos))))
        if pos < 0:
            limit = min(limit, max(1, int(math.ceil(-pos))))
        else:
            fpbar = self.transport.frames_per_bar
            next_bar = (math.floor(pos / fpbar) + 1) * fpbar
            limit = min(limit, max(1, int(math.ceil(next_bar - pos))))
            song = self.transport.song_frames
            if pos < song:
                limit = min(limit, max(1, int(math.ceil(song - pos))))
        if self._rec_state == RECORDING and self._rec_buf is not None:
            left = self._rec_buf.shape[0] - self._rec_written
            if left > 0:
                limit = min(limit, left)
        return max(1, limit)

    def _fire_boundaries(self) -> None:
        pos = self._pos
        fpb = self.transport.frames_per_beat
        beat = int(math.floor(pos / fpb))
        if beat != self._last_beat:
            self._last_beat = beat
            accent = beat % self.transport.beats_per_bar == 0
            if self.metronome or self._rec_state == COUNT_IN:
                self._add_voice(
                    Voice(self._click_accent if accent else self._click, 1.0, slot=-1)
                )
        if pos < 0:
            return
        fpbar = self.transport.frames_per_bar
        bar = int(pos // fpbar)
        if bar == self._last_bar:
            return
        self._last_bar = bar
        if self._rec_state == COUNT_IN:
            self._rec_state = RECORDING
            self.events.put(("record_started", self._rec_bars))
        if self._rec_state != IDLE and not self.play_while_recording:
            return
        if bar < len(self._schedule):
            for entry in self._schedule[bar]:
                self._add_voice(Voice(entry.buf, entry.gain, entry.slot))

    def _wrap_song(self) -> None:
        song = self.transport.song_frames
        if self._pos < song:
            return
        if self._rec_state != IDLE:
            return  # a take always runs to its full length first
        if self.loop:
            self._pos -= song
            self._last_beat = self._last_bar = None
        else:
            self._running = False
            self._pos = 0.0
            self._last_beat = self._last_bar = None
            self.events.put(("stopped",))

    def _add_voice(self, voice: Voice) -> None:
        if voice.buf is None or voice.buf.shape[0] == 0:
            return
        # These scans are bounded by MAX_VOICES + MAX_RELEASING and only run
        # when a voice starts -- a handful of times per bar, never per frame.
        if sum(1 for v in self._voices if v.releasing is None) >= MAX_VOICES:
            self._release_oldest()
        if len(self._voices) >= MAX_VOICES + MAX_RELEASING:
            del self._voices[0]  # the fade queue is full too: this one goes
        self._voices.append(voice)

    def _release_oldest(self) -> None:
        for voice in self._voices:
            if voice.releasing is None:
                voice.releasing = 0
                return

    def _release_all(self, samples_only: bool = False) -> None:
        """Fade every voice out instead of cutting it, which would click."""
        for voice in self._voices:
            if samples_only and voice.slot < 0:
                continue
            if voice.releasing is None:
                voice.releasing = 0

    def _mix(self, seg: np.ndarray, n: int) -> None:
        if not self._voices:
            self.sounding = ()
            return
        keep: list[Voice] = []
        sounding: set[int] = set()
        for voice in self._voices:
            buf = voice.buf
            total = buf.shape[0]
            k = min(n, total - voice.pos)
            if voice.releasing is not None:
                k = min(k, self._release_frames - voice.releasing)
            if k > 0:
                chunk = buf[voice.pos : voice.pos + k]
                if chunk.shape[1] > self.out_channels:
                    chunk = chunk[:, : self.out_channels]
                env = self._envelope(voice, k, total)
                # A mono (k, 1) chunk broadcasts across the output channels.
                if env is None:
                    seg[:k] += chunk * voice.gain
                else:
                    seg[:k] += chunk * (voice.gain * env[:, None])
                voice.pos += k
                if voice.releasing is not None:
                    voice.releasing += k
                if voice.slot >= 0:
                    sounding.add(voice.slot)
            if not self._voice_done(voice, total):
                keep.append(voice)
        self._voices = keep
        self.sounding = tuple(sorted(sounding))

    def _voice_done(self, voice: Voice, total: int) -> bool:
        if voice.pos >= total:
            return True
        return voice.releasing is not None and voice.releasing >= self._release_frames

    def _envelope(self, voice: Voice, k: int, total: int) -> np.ndarray | None:
        """Gain ramp for this segment, or ``None`` when the voice is at unity."""
        fade = self._fade_frames
        pos = voice.pos
        tail_start = total - fade
        rising = pos < fade
        falling = pos + k > tail_start
        releasing = voice.releasing
        if not rising and not falling and releasing is None:
            return None
        if self._env_scratch.shape[0] < k:
            self._env_scratch = np.ones(k, dtype=np.float32)
        env = self._env_scratch[:k]
        env[:] = 1.0
        if rising:
            end = min(fade, pos + k)
            env[: end - pos] *= self._fade_in[pos:end]
        if falling and releasing is None:
            start = max(pos, tail_start)
            env[start - pos :] *= self._fade_out[
                start - tail_start : pos + k - tail_start
            ]
        if releasing is not None:
            # A release overrides the buffer's own tail fade.
            env *= self._release_win[releasing : releasing + k]
        return env

    def _monitoring(self) -> bool:
        if self.monitor_gain <= 0.0:
            return False
        if self.monitor == MONITOR_ON:
            return True
        return self.monitor == MONITOR_AUTO and self._rec_state != IDLE

    def _monitor(self, seg: np.ndarray, inp: np.ndarray) -> None:
        chunk = inp[:, : self.out_channels]
        seg += chunk * self.monitor_gain

    def _meter_input(self, inp: np.ndarray) -> None:
        peak = float(np.abs(inp).max())
        if peak >= 1.0:
            self.input_clipped = True
        # Rise instantly, fall slowly, so a transient stays visible.
        self._in_peak = max(peak, self._in_peak * METER_DECAY)
        self._in_rms = float(np.sqrt(np.mean(np.square(inp, dtype=np.float64))))

    def take_clipped(self) -> bool:
        """Read and clear the clip latch."""
        clipped = self.input_clipped
        self.input_clipped = False
        return clipped

    def _capture(self, inp: np.ndarray, n: int) -> None:
        buf = self._rec_buf
        if buf is None:
            return
        k = min(n, buf.shape[0] - self._rec_written)
        if k > 0:
            buf[self._rec_written : self._rec_written + k] = inp[:k, : self.in_channels]
            self._rec_written += k
        if self._rec_written >= buf.shape[0]:
            self._finish_record()

    def _finish_record(self) -> None:
        buf = self._rec_buf
        lat = self.rec_latency_frames
        data = np.zeros((self._rec_keep, self.in_channels), dtype=np.float32)
        if buf is not None:
            take = buf[lat : lat + self._rec_keep]
            data[: take.shape[0]] = take
        bars = self._rec_bars
        self._rec_state = IDLE
        self._rec_buf = None
        self._running = False
        self._pos = 0.0
        self._release_all()
        self.sounding = ()
        self._last_beat = self._last_bar = None
        self.events.put(("record_done", bars, data))

    def _publish_stats(self, started: float, rendered: np.ndarray) -> None:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if elapsed_ms > self._cb_ms_max:
            self._cb_ms_max = elapsed_ms
        self.stats = Stats(
            xruns=self._xruns,
            peak_out=float(np.abs(rendered).max()) if rendered.shape[0] else 0.0,
            voices=len(self._voices),
            callback_ms=elapsed_ms,
            callback_ms_max=self._cb_ms_max,
            input_peak=self._in_peak,
            input_rms=self._in_rms,
        )

    # ------------------------------------------------------------------
    def poll_events(self) -> list[tuple]:
        out: list[tuple] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out
