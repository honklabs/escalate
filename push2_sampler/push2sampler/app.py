"""Application: wires the control surface, the audio engine and the modes."""

from __future__ import annotations

import time
from pathlib import Path

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
    BrowserMode,
    LibraryMode,
    MixerMode,
    Mode,
    PerformMode,
    RecordMode,
    SampleMode,
    SettingsMode,
    SongMode,
)
from .project import (
    BANK_SLOTS,
    PAGE_BARS,
    PROJECT_FILE,
    SLOT_COUNT,
    Project,
    format_bpm,
)
from .render import BounceJob, default_bounce_path
from .settings import ENGINE_SETTINGS, Settings
from .push2 import ButtonEvent, EncoderEvent, PadEvent, PushBase, SurfaceOffline

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
#: Taps further apart than this start a new tempo-tapping series.
TAP_GAP_S = 2.5
#: Taps needed before a tempo is set: three intervals, so one can be an outlier.
TAP_MINIMUM = 4
#: How far an interval may sit from the median before it is thrown away.
TAP_OUTLIER = 0.35
#: BPM per click of the tempo encoder while Tap Tempo is held.
TEMPO_FINE_STEP = 0.1
#: A second Stop this soon after the first is the "get me out of here" gesture.
DOUBLE_STOP_S = 0.5
#: How long `Delete` stays armed before disarming itself.  Every other armed
#: modifier is a mode you stay in; this one can destroy a take, so it lapses.
DELETE_ARM_S = 3.0
#: How long a pressed button's LED is forced bright, whatever the mode wanted.
PRESS_FLASH_S = 0.08
#: How often to try reopening a control surface that stopped answering.
RECONNECT_INTERVAL_S = 2.0
#: How long the grid flashes after a bank change, so you see where you landed.
BANK_FLASH_S = 0.25
#: Where the browser looks when there is no project directory to infer from.
DEFAULT_PROJECT_ROOT = "~/push2sampler"
#: What `Repeat` cycles through: this page, the whole song, or no looping.
LOOP_PAGE, LOOP_SONG, LOOP_OFF = "page", "song", "off"
LOOP_SCOPES = (LOOP_PAGE, LOOP_SONG, LOOP_OFF)


def _bpm_from_taps(taps: list[float]) -> float | None:
    """BPM from a series of tap times, with outlying intervals thrown away.

    One badly-placed tap in four should not move the tempo, so the median
    interval decides what "about right" is and anything far from it is dropped
    before averaging the rest.
    """
    intervals = [b - a for a, b in zip(taps, taps[1:]) if b > a]
    if not intervals:
        return None
    ordered = sorted(intervals)
    median = ordered[len(ordered) // 2]
    kept = [i for i in intervals if abs(i - median) <= median * TAP_OUTLIER]
    if not kept:
        return None
    mean = sum(kept) / len(kept)
    if mean <= 0:
        return None
    return 60.0 / mean


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
        self._delete_armed = False
        self._delete_armed_at = 0.0
        #: Slot whose deletion has been warned about and is awaiting a second
        #: press.  Cleared by anything else touching the surface.
        self._confirm_slot: int | None = None
        self.mute_armed = False
        self.duplicate_armed = False
        #: cc -> when it was pressed, for the press-feedback flash.
        self._flashes: dict[int, float] = {}
        self._reconnect_at = 0.0
        self._surface_message = ""
        #: Which 64 slots and which 64 bars the grid is showing.
        self.bank = 0
        self.page = 0
        self._bank_flash_until = 0.0
        #: page / song / off -- what `Repeat` cycles.
        self.loop_scope = LOOP_PAGE
        #: Tempo tapping: press times of the current series, and whether the
        #: held Tap button has been used as a fine-nudge modifier instead.
        self._taps: list[float] = []
        self._tap_held = False
        #: When Stop was last pressed, for spotting a double press.
        self._stopped_at = 0.0
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
        self.engine.master_gain = project.master_gain
        self.apply_loop_scope()
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
        self.snapshot_ui_state()

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
        self.snapshot_ui_state()
        return True

    def pop_mode(self) -> bool:
        """Close the top mode and return to the one underneath."""
        if self.depth <= 1:
            return False
        self.mode.on_exit()
        self._clear_modifiers()
        self._modes.pop()
        self.snapshot_ui_state()
        return True

    # ------------------------------------------------------------------
    # armed modifiers
    # ------------------------------------------------------------------
    @property
    def delete_armed(self) -> bool:
        """True while `Delete` is armed, which lapses after DELETE_ARM_S.

        Read as a property rather than expired on a timer so that nothing can
        observe it as still armed after the deadline, whatever order the event
        loop happens to run in.
        """
        if not self._delete_armed:
            return False
        if time.monotonic() - self._delete_armed_at >= DELETE_ARM_S:
            self._delete_armed = False
            self._confirm_slot = None
        return self._delete_armed

    @delete_armed.setter
    def delete_armed(self, value: bool) -> None:
        self._delete_armed = bool(value)
        self._delete_armed_at = time.monotonic()
        if not value:
            self._confirm_slot = None

    def confirm_delete(self, slot: int, what: str = "slot") -> bool:
        """Gate deleting a sample that is actually used in the song.

        An empty slot, or one that plays nowhere, goes straight away -- there is
        nothing to regret.  One that plays somewhere says what it would cost and
        waits for a second press on the same pad, because "12 bars" is the fact
        that decides whether you meant it.
        """
        sample = self.project[slot]
        if sample is None or not sample.triggers:
            return True
        if self._confirm_slot == slot:
            self._confirm_slot = None
            return True
        self._confirm_slot = slot
        bars = len(sample.triggers)
        self.notify(
            f"{what} {slot + 1} plays on {bars} bar{'s' if bars != 1 else ''}"
            " - press again"
        )
        return False

    def _clear_modifiers(self) -> None:
        self.delete_armed = False
        self.mute_armed = False
        self.duplicate_armed = False

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
    def dim_library(self) -> bool:
        return bool(self.settings.get("dim_library", True))

    @property
    def pre_roll_bars(self) -> int:
        return int(self.settings.get("pre_roll_bars", 0) or 0)

    @property
    def autosave_delay(self) -> float:
        return float(self.settings.get("autosave_delay_s", AUTOSAVE_DELAY))

    # ------------------------------------------------------------------
    # which 64 of the 256 the grid is showing
    # ------------------------------------------------------------------
    def slot_at(self, pad: int) -> int:
        """The library slot a pad means, in the bank currently on screen."""
        return self.bank * BANK_SLOTS + pad

    def pad_of_slot(self, slot: int) -> int | None:
        """Where a slot appears on the grid, or None if its bank is not shown."""
        pad = slot - self.bank * BANK_SLOTS
        return pad if 0 <= pad < BANK_SLOTS else None

    def bar_at(self, pad: int) -> int:
        """The song bar a pad means, on the page currently on screen."""
        return self.page * PAGE_BARS + pad

    def pad_of_bar(self, bar: int) -> int | None:
        pad = bar - self.page * PAGE_BARS
        return pad if 0 <= pad < PAGE_BARS else None

    @property
    def bank_letter(self) -> str:
        return "ABCD"[self.bank % 4]

    @property
    def page_letter(self) -> str:
        return "ABCD"[self.page % 4]

    def set_bank(self, bank: int, announce: bool = True) -> None:
        bank = max(0, min(self.project.banks - 1, bank))
        if bank == self.bank:
            return
        self.bank = bank
        # A full-grid flash on the way in, so you always know where you landed.
        self._bank_flash_until = time.monotonic() + BANK_FLASH_S
        if announce:
            filled = sum(
                1 for slot in range(bank * BANK_SLOTS, (bank + 1) * BANK_SLOTS)
                if self.project[slot] is not None
            )
            self.notify(f"bank {self.bank_letter}: {filled}/{BANK_SLOTS} filled")
        self.snapshot_ui_state()

    def set_page(self, page: int, announce: bool = True) -> None:
        page = max(0, min(self.project.pages - 1, page))
        if page == self.page:
            return
        self.page = page
        self.apply_loop_scope()
        if announce:
            first = page * PAGE_BARS + 1
            self.notify(f"song page {self.page_letter}: bars {first}-{first + PAGE_BARS - 1}")
        self.snapshot_ui_state()

    @property
    def bank_flashing(self) -> bool:
        return time.monotonic() < self._bank_flash_until

    # ------------------------------------------------------------------
    # what the loop covers
    # ------------------------------------------------------------------
    def apply_loop_scope(self) -> None:
        """Push the loop scope and the current page into the engine."""
        scope = self.loop_scope
        self.engine.loop = scope != LOOP_OFF
        if scope == LOOP_PAGE:
            start = self.page * PAGE_BARS
            self.engine.loop_range = (start, start + PAGE_BARS)
        else:
            self.engine.loop_range = (0, self.project.song_bars)

    def cycle_loop_scope(self) -> None:
        index = LOOP_SCOPES.index(self.loop_scope)
        self.loop_scope = LOOP_SCOPES[(index + 1) % len(LOOP_SCOPES)]
        self.apply_loop_scope()
        self.notify(f"loop {self.loop_label}")
        self.snapshot_ui_state()

    @property
    def loop_label(self) -> str:
        if self.loop_scope == LOOP_PAGE:
            return f"page {self.page_letter}"
        return "song" if self.loop_scope == LOOP_SONG else "off"

    # ------------------------------------------------------------------
    # where you were last time
    # ------------------------------------------------------------------
    def snapshot_ui_state(self) -> None:
        """Bookmark the session in the settings file."""
        self.settings.remember(
            project=str(self.project_dir) if self.project_dir else None,
            mode=self.mode.name,
            slot=getattr(self.mode, "slot", None),
            loop=bool(self.engine.loop),
            metronome=bool(self.engine.metronome),
        )
        self.save_soon()

    def restore_ui_state(self) -> None:
        """Put back what :meth:`snapshot_ui_state` remembered.

        Only the library and a sample page are restorable.  Coming back up
        inside a record arm, a bounce or the settings page would be hostile, and
        a slot that has since been deleted simply leaves you at home.
        """
        ui = self.settings.ui
        self.engine.loop = bool(ui.get("loop", True))
        self.engine.metronome = bool(ui.get("metronome", False))
        slot = ui.get("slot")
        if ui.get("mode") != "sample" or not isinstance(slot, int):
            return
        if 0 <= slot < PAD_COUNT and self.project[slot] is not None:
            self.goto_sample(slot)

    def open_perform(self) -> None:
        """Open perform mode and start the loop, so pads can be played live."""
        if self.mode.name == "perform":
            self.pop_mode()
            return
        if self.push_mode(PerformMode(self)) and not self.engine.is_playing:
            self.engine.play(0)

    # ------------------------------------------------------------------
    # switching projects, without leaving the device
    # ------------------------------------------------------------------
    @property
    def project_root(self):
        """Where the browser looks for projects: the folder ours lives in."""
        if self.project_dir is not None:
            return Path(self.project_dir).resolve().parent
        return Path(DEFAULT_PROJECT_ROOT).expanduser()

    @property
    def samples_root(self):
        """Where the import browser starts (NF-08).

        The setting when there is one, else the project's own folder -- which is
        usually where the takes you want to reuse already are.
        """
        configured = self.settings["samples_root"] if self.settings else ""
        if configured:
            return Path(configured).expanduser()
        if self.project_dir is not None:
            return Path(self.project_dir).resolve().parent
        return Path.home()

    def import_target(self) -> int | None:
        """Slot an import should land in: the first empty one, or None.

        Deliberately not "the slot you are looking at": a sample page only ever
        shows a *filled* slot, because ``goto_sample`` sends an empty one back
        to the library, so such a preference could never fire.  Choosing a
        particular slot is what ``--import --slot N`` is for.  An import never
        overwrites a take.
        """
        for slot in range(SLOT_COUNT):
            if self.project[slot] is None:
                return slot
        return None

    def open_import(self) -> None:
        from .modes.import_browser import ImportBrowserMode

        if self.mode.name == "import":
            self.pop_mode()
            return
        self.push_mode(ImportBrowserMode(self))

    def new_project_path(self):
        """A fresh directory name, dated and worded, needing no typing."""
        from .modes.browser import project_word

        root = self.project_root
        stamp = time.strftime("%m%d")
        for attempt in range(200):
            name = f"{stamp}-{project_word(int(time.time()) + attempt)}"
            if not (root / name).exists():
                return root / name
        return root / f"{stamp}-{int(time.time())}"

    def open_project(self, path, create: bool = False) -> bool:
        """Swap the project in place, keeping the audio stream running.

        The outgoing project is saved first: switching songs must never be the
        thing that loses one.  The stream is untouched, so the swap is silent --
        reopening the device would click, and would risk not reopening at all.
        """
        path = Path(path)
        if not create and not (path / PROJECT_FILE).exists():
            self.notify(f"{path.name} is not a project")
            return False
        if self.unsaved:
            self.save_now()
        self.engine.stop()
        try:
            if create:
                path.mkdir(parents=True, exist_ok=True)
                project = Project(samplerate=self.project.samplerate,
                                  bpm=self.project.bpm,
                                  beats_per_bar=self.project.beats_per_bar)
                project.save(path)
            else:
                project = Project.load(path, samplerate=self.project.samplerate)
        except OSError as exc:
            self.notify(f"could not open {path.name}: {exc}")
            return False
        self.project = project
        self.project_dir = path
        self.history.clear()  # the journal belonged to the other song
        self.bank = self.page = 0
        self.engine.set_bpm(project.bpm)
        self.engine.master_gain = project.master_gain
        self.apply_loop_scope()
        self.rebuild_schedule()
        if project.warning:
            self.notify(project.warning)
        self.goto_library()
        return True

    def duplicate_project(self, path):
        """Copy a project directory, audio and all.  Returns the new path."""
        import shutil

        source = Path(path)
        destination = self.new_project_path()
        try:
            shutil.copytree(source, destination)
        except OSError as exc:
            self.notify(f"could not copy {source.name}: {exc}")
            return None
        return destination

    def delete_project(self, path) -> bool:
        import shutil

        target = Path(path)
        if self.project_dir and target.resolve() == Path(self.project_dir).resolve():
            self.notify("cannot delete the project you have open")
            return False
        try:
            shutil.rmtree(target)
        except OSError as exc:
            self.notify(f"could not delete {target.name}: {exc}")
            return False
        return True

    def open_browser(self) -> None:
        if self.mode.name == "browser":
            self.pop_mode()
            return
        self.push_mode(BrowserMode(self))

    def open_song(self) -> None:
        if self.mode.name == "song":
            self.pop_mode()
            return
        self.push_mode(SongMode(self))

    def open_mixer(self) -> None:
        if self.mode.name == "mixer":
            self.pop_mode()
            return
        self.push_mode(MixerMode(self))

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
            elif setting in ("click_sound", "click_gain"):
                self.engine.set_click(
                    sound=values["click_sound"], gain=values["click_gain"],
                )
            elif setting == "click_when_recording":
                self.engine.click_while_recording_only = bool(values[setting])
            elif setting == "click_channel":
                # Out of range for this device means the main mix, rather than
                # a click routed into silence.
                channel = values[setting]
                usable = (
                    channel is not None and 0 <= int(channel) < self.engine.out_channels
                )
                self.engine.set_click(channel=int(channel) if usable else None)
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
        self.engine.master_gain = self.project.master_gain
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

    def save_now(self, announce: bool = False) -> bool:
        """Write the project.  False (with a visible reason) if it could not.

        A failure clears the pending save rather than retrying every tick: a
        read-only disk does not heal in 30 ms, and one message beats a hundred.
        """
        if self.project_dir is None:
            return False
        self.project.bpm = self.engine.bpm
        try:
            self.project.save(self.project_dir)
        except OSError as exc:
            self._save_at = None
            self.notify(f"could not save: {exc}")
            return False
        self._save_at = None
        if announce:
            self.notify("saved")
        return True

    @property
    def unsaved(self) -> bool:
        """True when there are changes not yet on disk."""
        return self.project_dir is not None and (
            self.project.dirty or self._save_at is not None
        )

    # ------------------------------------------------------------------
    # input
    # ------------------------------------------------------------------
    def handle(self, event) -> None:
        if isinstance(event, SurfaceOffline):
            self._surface_message = event.reason
            self.notify("surface offline - reconnecting")
            self._reconnect_at = time.monotonic() + RECONNECT_INTERVAL_S
            return
        if isinstance(event, PadEvent):
            self.mode.on_pad(event.index, event.pressed, event.velocity)
        elif isinstance(event, ButtonEvent):
            if event.pressed:
                # Every press lights its own LED briefly, whether or not the
                # mode does anything with it, so a dead button is obvious.
                self._flashes[event.cc] = time.monotonic()
            if event.cc == Btn.SHIFT:
                self.shift = event.pressed
                return
            if not self.mode.on_button(event.cc, event.pressed):
                self._global_button(event.cc, event.pressed)
        elif isinstance(event, EncoderEvent):
            if not self.mode.on_encoder(event.cc, event.delta):
                self._global_encoder(event.cc, event.delta)

    def _global_button(self, cc: int, pressed: bool) -> None:
        if cc == Btn.TAP_TEMPO:
            self._tap_held = pressed
            if pressed:
                self.tap_tempo()
            return
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
                # Start where the loop starts: with a page loop that is the page
                # you are working on, which is what you meant by Play.
                self.engine.play(self.engine.loop_range[0])
                self.notify("playing")
        elif cc == Btn.STOP:
            self._stop(pressed_at=time.monotonic())
        elif cc == Btn.METRONOME:
            if self.shift:
                self.cycle_monitor()
            else:
                self.engine.metronome = not self.engine.metronome
                self.notify(f"metronome {'on' if self.engine.metronome else 'off'}")
                self.snapshot_ui_state()
        elif cc == Btn.REPEAT:
            self.cycle_loop_scope()
        elif cc in (Btn.PAGE_LEFT, Btn.PAGE_RIGHT):
            step = -1 if cc == Btn.PAGE_LEFT else 1
            if self.shift:
                self.set_page(self.page + step)
            else:
                self.set_bank(self.bank + step)
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
        elif cc == Btn.MIX:
            self.open_mixer()
        elif cc == Btn.CLIP:
            self.open_song()
        elif cc == Btn.BROWSE:
            if self.shift:
                self.open_import()
            else:
                self.open_browser()
        elif cc == Btn.SETUP:
            if self.shift:
                self.save_now()
                self.notify("project saved")
            else:
                self.open_settings()

    def _global_encoder(self, cc: int, delta: int) -> None:
        if cc == ENCODER_TEMPO:
            if self._tap_held:
                # Holding Tap turns the encoder into a fine nudge for
                # beat-matching.  The press that is holding it is no longer part
                # of a tempo-tapping series, so drop it.
                self._taps.clear()
                step = TEMPO_FINE_STEP
            else:
                step = 10.0 if self.shift else 1.0
            previous = self.engine.bpm
            self.engine.set_bpm(previous + delta * step)
            if self.engine.bpm != previous:
                self.do(SetBpm(self.engine.bpm, previous))

    # ------------------------------------------------------------------
    # tempo tapping
    # ------------------------------------------------------------------
    def tap_tempo(self, now: float | None = None) -> float | None:
        """Record one tap; once there are enough, set the tempo from them.

        Returns the BPM that was set, or None while still collecting (or when
        the tempo cannot be changed).  ``now`` is injectable so the timing can be
        tested without sleeping.
        """
        if self.shift:
            self._taps.clear()
            self.notify("tap tempo reset")
            return None
        if self.engine.rec_state != "idle":
            # The engine refuses a tempo change mid-take; say so rather than
            # collecting taps that will be silently thrown away.
            self._taps.clear()
            self.notify("cannot change tempo during a take")
            return None
        now = time.monotonic() if now is None else now
        if self._taps and now - self._taps[-1] > TAP_GAP_S:
            self._taps.clear()  # too long a gap: this is a new series
        self._taps.append(now)
        if len(self._taps) > TAP_MINIMUM * 2:
            del self._taps[0]
        if len(self._taps) < TAP_MINIMUM:
            self.notify(f"tap {len(self._taps)}/{TAP_MINIMUM}")
            return None
        bpm = _bpm_from_taps(self._taps)
        if bpm is None:
            self.notify("taps too uneven")
            return None
        previous = self.engine.bpm
        self.engine.set_bpm(bpm)
        if self.engine.bpm != previous:
            self.do(SetBpm(self.engine.bpm, previous))
        return self.engine.bpm

    def _stop(self, pressed_at: float) -> None:
        """Stop, with two variants the hands can reach without thinking.

        `Shift`+`Stop` lets the bar finish.  A second `Stop` straight after the
        first is the panic gesture: whatever was armed is disarmed, so you can
        always get back to a surface that does nothing surprising.
        """
        double = pressed_at - self._stopped_at < DOUBLE_STOP_S
        self._stopped_at = pressed_at
        if double:
            armed = self.delete_armed or self.mute_armed or self.duplicate_armed
            self._clear_modifiers()
            self.engine.stop()
            self.notify("all clear" if armed else "stopped")
            return
        if self.shift and self.engine.is_playing:
            self.engine.stop(at_bar_end=True)
            self.notify("stopping at the end of the bar")
            return
        self.engine.stop()
        self.notify("stopped")

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
        flashing = self._apply_press_flash(buttons)
        for cc in self._rendered_buttons - set(buttons):
            self.push.set_button(cc, BTN_OFF)
        for cc, value in buttons.items():
            self.push.set_button(cc, value)
        # Flashed buttons the mode does not own are recorded as rendered, which
        # is exactly what makes a later frame turn them back off.
        self._rendered_buttons = set(buttons) | flashing

    def _apply_press_flash(self, buttons: dict[int, int]) -> set[int]:
        """Force recently-pressed buttons bright.  Returns which ones."""
        if not self._flashes:
            return set()
        now = time.monotonic()
        for cc, at in list(self._flashes.items()):
            if now - at >= PRESS_FLASH_S:
                del self._flashes[cc]
        for cc in self._flashes:
            buttons[cc] = BTN_BRIGHT
        return set(self._flashes)

    def _global_buttons(self, buttons: dict[int, int]) -> None:
        buttons[Btn.PLAY] = BTN_BRIGHT if self.engine.is_playing else BTN_DIM
        buttons[Btn.STOP] = BTN_BRIGHT if self.engine.stop_pending else BTN_DIM
        buttons[Btn.RECORD] = (
            colors.RED.index if self.input_clipping else colors.RED_DIM.index
        )
        buttons[Btn.METRONOME] = BTN_BRIGHT if self.engine.metronome else BTN_DIM
        buttons[Btn.TAP_TEMPO] = BTN_BRIGHT if self._taps else BTN_DIM
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

    def transport_readout(self) -> str:
        """The one line you should be able to read from across a room.

        Bar, beat within the bar, and tempo -- the three things you look up
        while playing.  Beats count from 1 because that is how anyone counts
        them out loud.
        """
        bar = self.engine.current_bar
        beat = self.engine.beat_in_bar
        page = self.page_letter if self.project.pages > 1 else ""
        where = f"BAR {bar + 1}" if bar >= 0 else "BAR -"
        if page:
            where += f"{page}"
        return f"{where} · {beat + 1} · {format_bpm(self.engine.bpm)} BPM"

    def status_lines(self) -> list[str]:
        lines = list(self.mode.status_lines())
        transport = "PLAY" if self.engine.is_playing else "STOP"
        if self.engine.stop_pending:
            transport = "ENDING"
        state = self.engine.rec_state
        if state != "idle":
            transport = state.upper()
        bar = self.engine.current_bar
        lines.append(
            f"{transport}  {format_bpm(self.engine.bpm)} BPM  bar "
            f"{bar + 1 if bar >= 0 else 0}/{self.project.song_bars}"
            f"  loop {self.loop_label}"
            f"{'  *' if self.unsaved else ''}"
        )
        lines.append(self._input_line())
        if self.push.offline:
            lines.append("SURFACE OFFLINE - check the cable; the audio is still running")
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
        self._supervise_surface()

        now = time.monotonic()
        if now - self._last_frame >= FRAME_INTERVAL:
            self._last_frame = now
            self.render()
        if self.display is not None and now - self._last_display >= 0.1:
            self._last_display = now
            try:
                self.display.draw(self.status_lines(), self.transport_readout())
            except Exception as exc:  # pragma: no cover - display is optional
                self.notify(f"display error: {exc}")
                self.display = None
        if self._save_at is not None and now >= self._save_at:
            # Announce only a real project write; a moved bookmark is not news.
            self.save_now(announce=self.project.dirty)
            self.save_settings()

    def _supervise_surface(self) -> None:
        """Keep trying to get an unplugged Push back, without stopping the music.

        The audio engine and the project are untouched by this: a cable moving
        must never cost a take.
        """
        if not self.push.offline:
            return
        now = time.monotonic()
        if now < self._reconnect_at:
            return
        self._reconnect_at = now + RECONNECT_INTERVAL_S
        if self.push.reopen():
            self._rendered_buttons = set()
            self._surface_message = ""
            self.notify("surface back")

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
        self.snapshot_ui_state()
        self.save_settings()
        if self.unsaved:
            # save_now reports its own failures, which is the point of CC-10:
            # a project that could not be written should say so, not print into
            # a terminal nobody is looking at.
            self.save_now()
        self.engine.close()
        self.push.clear()
        self.push.close()
        if self.display is not None:
            try:
                self.display.close()
            except Exception:  # pragma: no cover
                pass
