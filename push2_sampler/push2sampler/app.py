"""Application: wires the control surface, the audio engine and the modes."""

from __future__ import annotations

import time

from . import colors, wavio
from .audio import MONITOR_AUTO, MONITOR_OFF, MONITOR_ON
from .constants import (
    BTN_BRIGHT,
    BTN_DIM,
    BTN_OFF,
    BTN_ON,
    DISPLAY_ROW_TOP,
    ENCODER_TEMPO,
    PAD_COUNT,
    Btn,
)
from .history import Command, History, SetBpm
from .modes import (
    LibraryMode,
    Mode,
    PerformMode,
    RecordMode,
    SampleMode,
    SettingsMode,
)
from .project import Project
from .render import BounceJob, default_bounce_path
from .settings import ENGINE_SETTINGS, Settings
from .push2 import ButtonEvent, EncoderEvent, PadEvent, PushBase

#: Seconds between LED refreshes.  Only changed pads are actually sent.
FRAME_INTERVAL = 1.0 / 30.0
#: Quiet period after a change before the project is written to disk, when the
#: settings do not say otherwise.
AUTOSAVE_DELAY = 2.0
#: How long a clipped input stays flagged on the surface.
CLIP_WARNING_S = 1.5
#: Monitoring cycles through these in order.
MONITOR_CYCLE = (MONITOR_OFF, MONITOR_AUTO, MONITOR_ON)
#: How deep overlay modes may stack.  Kept shallow on purpose: you should never
#: be more than a couple of presses from knowing where you are.
MAX_MODE_DEPTH = 4


class App:
    def __init__(
        self,
        push: PushBase,
        engine,
        project: Project,
        project_dir=None,
        display=None,
        settings: Settings | None = None,
        log=None,
    ) -> None:
        self.push = push
        self.engine = engine
        self.project = project
        self.project_dir = project_dir
        self.display = display
        self.settings = settings if settings is not None else Settings()
        self._log = log

        self.history = History()
        self.shift = False
        self.delete_armed = False
        self.mute_armed = False
        self.running = False
        self.message = ""
        self._message_at = 0.0
        self._save_at: float | None = None
        self._clip_until = 0.0
        #: A render in progress, stepped a chunk at a time by tick().
        self.bounce: BounceJob | None = None
        self._last_frame = 0.0
        self._last_display = 0.0
        self._rendered_buttons: set[int] = set()

        #: Mode stack; the root is always the library, overlays sit on top.
        self._modes: list[Mode] = [LibraryMode(self)]
        self.engine.set_bpm(project.bpm)
        self.rebuild_schedule()
        self.mode.on_enter()

    # ------------------------------------------------------------------
    # mode transitions
    # ------------------------------------------------------------------
    @property
    def mode(self) -> Mode:
        """The mode on top of the stack: the one the surface belongs to."""
        return self._modes[-1]

    @property
    def depth(self) -> int:
        return len(self._modes)

    def set_mode(self, mode: Mode) -> None:
        """Replace the mode on top of the stack."""
        self.mode.on_exit()
        self._clear_modifiers()
        self._modes[-1] = mode
        mode.on_enter()

    def push_mode(self, mode: Mode) -> bool:
        """Open ``mode`` over the current one; ``pop_mode`` returns here.

        Refused once the stack is MAX_MODE_DEPTH deep, so no amount of
        button-pressing can bury you.
        """
        if self.depth >= MAX_MODE_DEPTH:
            self.notify("too many layers open")
            return False
        self._clear_modifiers()
        self._modes.append(mode)
        mode.on_enter()
        return True

    def pop_mode(self) -> bool:
        """Close the top mode and return to the one underneath."""
        if self.depth <= 1:
            return False
        self.mode.on_exit()
        self._clear_modifiers()
        self._modes.pop()
        return True

    def _clear_modifiers(self) -> None:
        self.delete_armed = False
        self.mute_armed = False

    def goto_library(self) -> None:
        """Unwind every overlay and land on a fresh library."""
        while self.depth > 1:
            self.mode.on_exit()
            self._modes.pop()
        self.set_mode(LibraryMode(self))

    def goto_record(self, slot: int, bars: int | None = None) -> None:
        existing = self.project[slot]
        if bars is None:
            bars = existing.bars if existing is not None else 1
        self.set_mode(RecordMode(self, slot, bars))

    def goto_sample(self, slot: int) -> None:
        if self.project[slot] is None:
            self.goto_library()
            return
        self.set_mode(SampleMode(self, slot))

    def next_filled_slot(self, start: int, step: int) -> int | None:
        for offset in range(1, PAD_COUNT + 1):
            candidate = (start + step * offset) % PAD_COUNT
            if self.project[candidate] is not None:
                return candidate
        return None

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------
    @property
    def count_in_beats(self) -> int:
        return int(self.settings["count_in_beats"])

    @property
    def autosave_delay(self) -> float:
        return float(self.settings.get("autosave_delay_s", AUTOSAVE_DELAY))

    def open_perform(self) -> None:
        """Open perform mode and start the loop, so pads can be played live."""
        if self.mode.name == "perform":
            self.pop_mode()
            return
        if self.push_mode(PerformMode(self)) and not self.engine.is_playing:
            self.engine.play(0)

    def open_settings(self) -> None:
        if self.mode.name == "settings":
            self.pop_mode()
            return
        self.push_mode(SettingsMode(self))

    def apply_settings(self, name: str | None = None) -> bool:
        """Push settings into the engine; False if one could not be applied.

        ``name`` limits the work to a single setting, which is what the settings
        page does as each encoder moves.  A failure is not described here: the
        engine raises an ``audio_error`` event naming the actual problem, which
        is more use than anything this could invent.
        """
        names = (name,) if name is not None else ENGINE_SETTINGS
        values = self.settings
        for setting in names:
            if values.spec(setting).restarts_audio:
                continue  # handled below, in one restart
            if setting == "monitor":
                self.engine.monitor = values[setting]
            elif setting == "monitor_gain":
                self.engine.monitor_gain = float(values[setting])
            elif setting == "play_while_recording":
                self.engine.play_while_recording = bool(values[setting])
            elif setting == "rec_latency_ms":
                samplerate = self.engine.transport.samplerate
                self.engine.rec_latency_frames = max(
                    0, int(samplerate * values[setting] / 1000.0)
                )
        changes = {n: values[n] for n in names if values.spec(n).restarts_audio}
        if changes:
            return self.engine.restart_stream(**changes)
        return True

    # ------------------------------------------------------------------
    # bouncing
    # ------------------------------------------------------------------
    def start_bounce(self) -> bool:
        """Begin rendering the song to a file, without blocking the surface."""
        if self.bounce is not None:
            self.notify("already bouncing")
            return False
        if not self.project.bars_in_use():
            self.notify("nothing to bounce yet")
            return False
        if self.project_dir is None:
            self.notify("no project directory to bounce into")
            return False
        self.bounce = BounceJob(self.project)
        self.notify("bouncing...")
        return True

    def _step_bounce(self) -> None:
        job = self.bounce
        if job is None:
            return
        if job.step():
            return
        self.bounce = None
        try:
            path = default_bounce_path(self.project_dir)
            wavio.write(path, job.result(), self.project.samplerate)
        except OSError as exc:
            self.notify(f"bounce failed: {exc}")
            return
        seconds = job.result().shape[0] / max(1, self.project.samplerate)
        self.notify(f"bounced {seconds:.0f}s to {path.name}")

    def save_settings(self) -> bool:
        if not self.settings.dirty:
            return False
        try:
            return self.settings.save() is not None
        except OSError as exc:
            self.notify(f"could not save settings: {exc}")
            return False

    # ------------------------------------------------------------------
    # shared plumbing
    # ------------------------------------------------------------------
    def rebuild_schedule(self) -> None:
        self.engine.set_schedule(self.project.build_schedule())

    def do(self, command: Command) -> None:
        """Apply an undoable edit and refresh everything that depends on it."""
        label = self.history.do(self.project, command)
        self.rebuild_schedule()
        self.save_soon()
        self.notify(label)

    def undo(self) -> None:
        label = self.history.undo(self.project)
        if label is None:
            self.notify("nothing to undo")
            return
        self._after_undo(f"undo: {label}")

    def redo(self) -> None:
        label = self.history.redo(self.project)
        if label is None:
            self.notify("nothing to redo")
            return
        self._after_undo(f"redo: {label}")

    def _after_undo(self, message: str) -> None:
        self.engine.set_bpm(self.project.bpm)
        self.rebuild_schedule()
        self.save_soon()
        self.notify(message)
        # An undo can empty the slot whose page we are on.
        slot = getattr(self.mode, "slot", None)
        if slot is not None and self.mode.name == "sample" and self.project[slot] is None:
            self.goto_library()

    def notify(self, message: str) -> None:
        self.message = message
        self._message_at = time.monotonic()
        if self._log is not None:
            self._log(message)

    def save_soon(self) -> None:
        if self.project_dir is not None:
            self._save_at = time.monotonic() + self.autosave_delay

    def save_now(self) -> None:
        if self.project_dir is None:
            return
        self.project.bpm = self.engine.bpm
        self.project.save(self.project_dir)
        self._save_at = None

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------
    def handle(self, event) -> None:
        if isinstance(event, PadEvent):
            self.mode.on_pad(event.index, event.pressed, event.velocity)
        elif isinstance(event, ButtonEvent):
            if event.cc == Btn.SHIFT:
                self.shift = event.pressed
                return
            if not self.mode.on_button(event.cc, event.pressed):
                self._global_button(event.cc, event.pressed)
        elif isinstance(event, EncoderEvent):
            if not self.mode.on_encoder(event.cc, event.delta):
                self._global_encoder(event.cc, event.delta)

    def _global_button(self, cc: int, pressed: bool) -> None:
        if not pressed:
            return
        if cc == Btn.PLAY:
            if self.shift:
                self.open_perform()
                return
            if self.engine.is_playing:
                self.engine.stop()
                self.notify("stopped")
            else:
                self.engine.play(0)
                self.notify("playing")
        elif cc == Btn.STOP:
            self.engine.stop()
            self.notify("stopped")
        elif cc == Btn.METRONOME:
            if self.shift:
                self.cycle_monitor()
            else:
                self.engine.metronome = not self.engine.metronome
                self.notify(f"metronome {'on' if self.engine.metronome else 'off'}")
        elif cc == Btn.REPEAT:
            self.engine.loop = not self.engine.loop
            self.notify(f"loop {'on' if self.engine.loop else 'off'}")
        elif cc == Btn.DELETE:
            self.delete_armed = not self.delete_armed
            self.mute_armed = False
            self.notify("delete armed: press a pad" if self.delete_armed else "delete off")
        elif cc == Btn.UNDO:
            self.redo() if self.shift else self.undo()
        elif cc in (Btn.SESSION, Btn.NOTE, Btn.LEFT):
            # An overlay closes back to what was underneath; otherwise home.
            if not self.pop_mode():
                self.goto_library()
        elif cc == Btn.SETUP:
            if self.shift:
                self.save_now()
                self.notify("project saved")
            else:
                self.open_settings()

    def _global_encoder(self, cc: int, delta: int) -> None:
        if cc == ENCODER_TEMPO:
            step = 10.0 if self.shift else 1.0
            previous = self.engine.bpm
            self.engine.set_bpm(previous + delta * step)
            if self.engine.bpm != previous:
                self.do(SetBpm(self.engine.bpm, previous))

    def cycle_monitor(self) -> None:
        current = self.engine.monitor
        index = MONITOR_CYCLE.index(current) if current in MONITOR_CYCLE else 0
        self.engine.monitor = MONITOR_CYCLE[(index + 1) % len(MONITOR_CYCLE)]
        self.notify(f"monitor {self.engine.monitor}")

    @property
    def input_clipping(self) -> bool:
        return time.monotonic() < self._clip_until

    def on_engine_event(self, event: tuple) -> None:
        if event[0] == "xrun":
            self.notify(f"audio dropout ({event[1]})")
        elif event[0] == "audio_error":
            self.notify(f"audio: {event[1]}")
        self.mode.on_engine_event(event)

    # ------------------------------------------------------------------
    # output
    # ------------------------------------------------------------------
    @property
    def blink(self) -> bool:
        """A 2 Hz square wave shared by everything that flashes."""
        return int(time.monotonic() * 4) % 2 == 0

    def render(self) -> None:
        pads = [colors.OFF.index] * PAD_COUNT
        self.mode.render_pads(pads)
        for i, value in enumerate(pads):
            self.push.set_pad(i, value)

        buttons: dict[int, int] = {}
        self._global_buttons(buttons)
        self.mode.render_buttons(buttons)
        for cc in self._rendered_buttons - set(buttons):
            self.push.set_button(cc, BTN_OFF)
        for cc, value in buttons.items():
            self.push.set_button(cc, value)
        self._rendered_buttons = set(buttons)

    def _global_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.PLAY] = BTN_BRIGHT if self.engine.is_playing else BTN_DIM
        buttons[Btn.STOP] = BTN_DIM
        buttons[Btn.RECORD] = (
            colors.RED.index if self.input_clipping else colors.RED_DIM.index
        )
        buttons[Btn.METRONOME] = BTN_BRIGHT if self.engine.metronome else BTN_DIM
        self._render_input_meter(buttons)
        buttons[Btn.REPEAT] = BTN_ON if self.engine.loop else BTN_DIM
        buttons[Btn.DELETE] = BTN_BRIGHT if self.delete_armed else BTN_DIM
        buttons[Btn.UNDO] = BTN_ON if self.history.can_undo else BTN_OFF
        buttons[Btn.SHIFT] = BTN_DIM
        buttons[Btn.SESSION] = BTN_DIM
        buttons[Btn.SETUP] = BTN_DIM
        buttons[Btn.MUTE] = BTN_OFF

    def _render_input_meter(self, buttons: dict[int, int]) -> None:
        """Show the input level on the eight buttons above the display."""
        peak = self.engine.stats.input_peak
        lit = min(len(DISPLAY_ROW_TOP), int(peak * len(DISPLAY_ROW_TOP) + 0.5))
        for i, cc in enumerate(DISPLAY_ROW_TOP):
            if i >= lit:
                buttons[cc] = BTN_OFF
            elif i >= len(DISPLAY_ROW_TOP) - 2:
                buttons[cc] = BTN_BRIGHT  # the hot end of the meter
            else:
                buttons[cc] = BTN_ON

    def status_lines(self) -> list[str]:
        lines = list(self.mode.status_lines())
        transport = "PLAY" if self.engine.is_playing else "STOP"
        state = self.engine.rec_state
        if state != "idle":
            transport = state.upper()
        bar = self.engine.current_bar
        lines.append(
            f"{transport}  {self.engine.bpm:.0f} BPM  bar "
            f"{bar + 1 if bar >= 0 else 0}/{self.project.song_bars}"
            f"  {'loop' if self.engine.loop else 'once'}"
        )
        lines.append(self._input_line())
        if self.message and time.monotonic() - self._message_at < 3.0:
            lines.append(self.message)
        return lines

    def _input_line(self) -> str:
        peak = self.engine.stats.input_peak
        filled = min(12, int(peak * 12 + 0.5))
        meter = "#" * filled + "." * (12 - filled)
        state = f"mon {self.engine.monitor}"
        clip = "  CLIP" if self.input_clipping else ""
        return f"in [{meter}] {state}{clip}"

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def tick(self) -> None:
        """One pass of the event loop: input, engine events, LEDs, autosave."""
        for event in self.push.poll_events():
            self.handle(event)
        for event in self.engine.poll_events():
            self.on_engine_event(event)
        if self.engine.take_clipped():
            self._clip_until = time.monotonic() + CLIP_WARNING_S
            self.notify("input clipping")
        self.mode.on_tick()
        self._step_bounce()

        now = time.monotonic()
        if now - self._last_frame >= FRAME_INTERVAL:
            self._last_frame = now
            self.render()
        if self.display is not None and now - self._last_display >= 0.1:
            self._last_display = now
            try:
                self.display.draw(self.status_lines())
            except Exception as exc:  # pragma: no cover - display is optional
                self.notify(f"display error: {exc}")
                self.display = None
        if self._save_at is not None and now >= self._save_at:
            self.save_now()

    def run(self) -> None:
        self.running = True
        try:
            while self.running:
                self.tick()
                time.sleep(0.002)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def stop(self) -> None:
        self.running = False

    def shutdown(self) -> None:
        try:
            self.engine.stop()
        except Exception:  # pragma: no cover
            pass
        self.save_settings()
        if self.project_dir is not None and (self.project.dirty or self._save_at):
            try:
                self.save_now()
            except Exception as exc:  # pragma: no cover
                print(f"could not save project: {exc}")
        self.engine.close()
        self.push.clear()
        self.push.close()
        if self.display is not None:
            try:
                self.display.close()
            except Exception:  # pragma: no cover
                pass
