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
"""

from __future__ import annotations

import math
import queue
import threading
import time
from dataclasses import dataclass

import numpy as np

#: Maximum simultaneously sounding voices; the oldest is faded out beyond this.
MAX_VOICES = 96
#: Extra voice slots reserved for voices that are fading out.
MAX_RELEASING = 16
#: Fade applied at the start and end of every voice, to stop edges clicking.
FADE_MS = 3.0
#: Longer fade used when a voice is cut short: Stop, a new take, voice stealing.
RELEASE_MS = 10.0

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
    """Transport, mixer and recorder.  Thread-safe for the few public setters."""

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
        monitor_gain: float = 0.0,
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
        self.null_input = null_input

        self.events: queue.SimpleQueue = queue.SimpleQueue()
        self.metronome = False
        self.loop = True

        self._lock = threading.RLock()
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
        self._count_in_beats = 0

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
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # pragma: no cover - best effort
                pass
            self._stream = None

    def _sd_callback(self, indata, outdata, frames, _time, _status):  # pragma: no cover
        with self._lock:
            self._process(outdata, indata, frames)

    def _null_loop(self) -> None:
        n = self.blocksize
        out = np.zeros((n, self.out_channels), dtype=np.float32)
        inp = np.zeros((n, self.in_channels), dtype=np.float32)
        period = n / self.transport.samplerate
        next_deadline = time.monotonic()
        while not self._stop_evt.is_set():
            self._fill_null_input(inp)
            with self._lock:
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
        with self._lock:
            self._process(out, indata, frames)
        return out

    # ------------------------------------------------------------------
    # public state
    # ------------------------------------------------------------------
    @property
    def bpm(self) -> float:
        return self.transport.bpm

    def set_bpm(self, bpm: float) -> None:
        with self._lock:
            if self._rec_state != IDLE:
                return  # changing tempo mid-take would corrupt the take length
            self.transport.bpm = max(40.0, min(240.0, float(bpm)))
            # Re-anchor boundary tracking so the new grid does not retrigger.
            self._last_beat = int(math.floor(self._pos / self.transport.frames_per_beat))
            self._last_bar = (
                int(self._pos // self.transport.frames_per_bar) if self._pos >= 0 else None
            )

    @property
    def is_playing(self) -> bool:
        return self._running

    @property
    def rec_state(self) -> str:
        return self._rec_state

    @property
    def position_frames(self) -> float:
        return self._pos

    @property
    def current_bar(self) -> int:
        pos = self._pos
        if pos < 0:
            return -1
        return int(pos // self.transport.frames_per_bar)

    @property
    def current_beat(self) -> int:
        """Beat index within the bar, or a negative count-in beat."""
        return int(math.floor(self._pos / self.transport.frames_per_beat))

    @property
    def beat_phase(self) -> float:
        """Position inside the current beat, 0.0 -> 1.0."""
        fpb = self.transport.frames_per_beat
        return (self._pos / fpb) % 1.0

    @property
    def count_in_beats_left(self) -> int:
        if self._rec_state != COUNT_IN:
            return 0
        fpb = self.transport.frames_per_beat
        return max(0, int(math.ceil(-self._pos / fpb)))

    def set_schedule(self, schedule) -> None:
        """Install the bar -> samples map.  Replaced atomically by reference."""
        frozen = tuple(tuple(entries) for entries in schedule)
        if len(frozen) != self.transport.song_bars:
            raise ValueError("schedule must have one entry per song bar")
        self._schedule = frozen

    # ------------------------------------------------------------------
    # transport commands
    # ------------------------------------------------------------------
    def play(self, from_bar: int = 0) -> None:
        with self._lock:
            self._pos = float(from_bar) * self.transport.frames_per_bar
            self._release_all(samples_only=True)
            self._arm_boundaries()
            self._running = True

    def stop(self) -> None:
        with self._lock:
            was = self._rec_state
            self._running = False
            self._rec_state = IDLE
            self._rec_buf = None
            self._pos = 0.0
            self._release_all()
            self.sounding = ()
            self._last_beat = self._last_bar = None
        if was != IDLE:
            self.events.put(("record_cancelled",))
        self.events.put(("stopped",))

    def toggle_play(self) -> None:
        if self._running:
            self.stop()
        else:
            self.play(0)

    def arm_record(self, bars: int, count_in_beats: int = 4) -> None:
        """Rewind to the count-in and start capturing ``bars`` bars at bar 0."""
        bars = max(1, min(self.transport.song_bars, int(bars)))
        keep = int(round(bars * self.transport.frames_per_bar))
        total = keep + self.rec_latency_frames
        with self._lock:
            self._rec_bars = bars
            self._rec_keep = keep
            self._rec_buf = np.zeros((total, self.in_channels), dtype=np.float32)
            self._rec_written = 0
            self._count_in_beats = max(0, int(count_in_beats))
            self._pos = -self._count_in_beats * self.transport.frames_per_beat
            self._release_all()
            self._arm_boundaries()
            self._rec_state = COUNT_IN if self._count_in_beats else RECORDING
            self._running = True
        self.events.put(("record_armed", bars))

    def cancel_record(self) -> None:
        with self._lock:
            if self._rec_state == IDLE:
                return
            self._rec_state = IDLE
            self._rec_buf = None
            self._running = False
            self._pos = 0.0
            self._release_all()
            self._last_beat = self._last_bar = None
        self.events.put(("record_cancelled",))

    def preview(self, buf: np.ndarray, gain: float = 1.0, slot: int = -1) -> None:
        """Play a one-shot outside the transport (auditioning a sample)."""
        with self._lock:
            self._add_voice(Voice(buf, gain, slot=slot))

    def _arm_boundaries(self) -> None:
        """Force the next processed segment to fire its beat and bar events."""
        self._last_beat = None
        self._last_bar = None

    # ------------------------------------------------------------------
    # the audio callback
    # ------------------------------------------------------------------
    def _process(self, out: np.ndarray, inp: np.ndarray | None, frames: int) -> None:
        out[:frames] = 0.0
        i = 0
        while i < frames:
            if self._running:
                self._fire_boundaries()
            n = min(frames - i, self._segment_limit(frames - i))
            seg = out[i : i + n]
            self._mix(seg, n)
            if inp is not None:
                if self.monitor_gain > 0.0:
                    self._monitor(seg, inp[i : i + n])
                if self._rec_state == RECORDING:
                    self._capture(inp[i : i + n], n)
            if self._running:
                self._pos += n
                self._wrap_song()
            i += n
        np.clip(out[:frames], -1.0, 1.0, out=out[:frames])

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

    def _monitor(self, seg: np.ndarray, inp: np.ndarray) -> None:
        chunk = inp[:, : self.out_channels]
        seg += chunk * self.monitor_gain

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

    # ------------------------------------------------------------------
    def poll_events(self) -> list[tuple]:
        out: list[tuple] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out
