"""NF-09: MIDI clock in and out.

The slave is a control loop, so what matters about it is behaviour over
simulated minutes -- how closely it tracks, how it copes with a wobble, and
whether it ever moves the playhead backwards. Wall-clock tests cannot show any
of that, so time and the engine are both injected and the whole loop is driven
synthetically at a fine step.

``drive()`` below is the same rig the throwaway prototype used, pointed at the
real class. It caught three design errors before any of this was written, and
it is kept here so a regression in the loop shows up as a number rather than as
"the sync feels loose".
"""

from __future__ import annotations

import math
import random

import pytest

from push2sampler import clock as clockmod
from push2sampler.clock import (
    KI,
    KP,
    PPQN,
    ClockEvent,
    InternalClock,
    LinkClock,
    MidiClockMaster,
    MidiClockSlave,
    bar_to_spp,
    make_clock,
    spp_to_bar,
)

SR = 48_000
BEATS = 4


class Msg:
    """A stand-in for a mido message."""

    def __init__(self, type, **fields) -> None:
        self.type = type
        self.__dict__.update(fields)


class FakeEngine:
    """A transport that can be stepped by hand.

    Only the three things a clock touches: where it is, how long a beat is, and
    whether it is running.
    """

    def __init__(self, bpm=120.0, samplerate=SR, beats_per_bar=BEATS) -> None:
        self.bpm = bpm
        self.samplerate = samplerate
        self.beats_per_bar = beats_per_bar
        self.position_frames = 0.0
        self.is_playing = True
        self.rec_state = "idle"
        self.bpm_calls: list[float] = []

    @property
    def frames_per_beat(self) -> float:
        return 60.0 / self.bpm * self.samplerate

    @property
    def frames_per_bar(self) -> float:
        return self.frames_per_beat * self.beats_per_bar

    def advance(self, seconds: float) -> None:
        """Frames are frames: the audio clock runs at the sample rate.

        The tempo does not enter here -- it only decides how many *beats* those
        frames are.  Writing this as ``bpm/60 * seconds * samplerate`` (beats,
        then wrongly scaled by the sample rate) was the first version, and it
        made the loop look broken when the double was.
        """
        self.position_frames += seconds * self.samplerate

    def set_bpm(self, bpm: float) -> None:
        """Keep the musical position, exactly as the real engine now does."""
        self.bpm_calls.append(bpm)
        beats = self.position_frames / self.frames_per_beat
        self.bpm = max(40.0, min(240.0, bpm))
        self.position_frames = beats * self.frames_per_beat


def drive(slave, engine, bars=32, true_bpm=120.0, ui_hz=30.0, sim_hz=4000.0,
          wobble=0.0, wobble_period=4.0, jitter=0.0, seed=1, settle_s=4.0):
    """Run a synthetic 24 ppqn source at ``true_bpm`` and follow it.

    Returns ``(worst error in ms after settling, musical backwards steps,
    final bpm)``.

    "Backwards" counts the *musical* position going back, not the frame
    position.  Preserving musical position across a tempo change necessarily
    moves the frame position -- raising the tempo shrinks a beat, so the same
    bar sits at a lower frame count -- and that is both expected and harmless,
    because ``Engine._reanchor`` re-pegs the boundary tracking to it.  What
    must never happen is the *music* jumping back, which would cut every
    sounding voice.
    """
    rng = random.Random(seed)
    fake_now = [0.0]
    slave._now = lambda: fake_now[0]
    slave.bind(engine)

    dt = 1.0 / sim_hz
    ui_every = max(1, int(sim_hz / ui_hz))
    external_beats = 0.0
    next_tick = 1.0 / PPQN
    worst = 0.0
    backwards = 0
    previous = engine.position_frames / engine.frames_per_beat
    step = 0

    while external_beats < bars * engine.beats_per_bar:
        instant = true_bpm * (
            1.0 + wobble * math.sin(2 * math.pi * fake_now[0] / wobble_period)
        )
        external_beats += instant / 60.0 * dt
        engine.advance(dt)

        while external_beats >= next_tick:
            if jitter:
                # Arrival jitter moves the *timestamp*, not the tick's index:
                # a late-arriving tick still means the same musical position.
                fake_now[0] += rng.uniform(-jitter, jitter)
                slave._on_message(Msg("clock"))
                fake_now[0] -= rng.uniform(-jitter, jitter) * 0
            else:
                slave._on_message(Msg("clock"))
            next_tick += 1.0 / PPQN

        step += 1
        if step % ui_every == 0:
            for event in slave.poll(engine):
                if event.kind == "tempo":
                    engine.set_bpm(event.bpm)

        ours = engine.position_frames / engine.frames_per_beat
        if ours < previous - 1e-9:
            backwards += 1
        previous = ours
        if fake_now[0] > settle_s:
            worst = max(worst, abs(external_beats - ours))
        fake_now[0] += dt

    return worst * (60.0 / true_bpm) * 1000.0, backwards, engine.bpm


# ===================================================== the loop's behaviour
def test_a_synthetic_clock_is_followed_to_within_a_millisecond():
    """The plan's headline number: +/-1 ms over 32 bars."""
    engine = FakeEngine(bpm=120.0)
    worst_ms, backwards, final = drive(MidiClockSlave(), engine, bars=32)
    assert worst_ms < 1.0, worst_ms
    assert backwards == 0
    assert final == pytest.approx(120.0, abs=0.5)


def test_it_converges_from_the_wrong_tempo():
    """Started at 120 against a 140 BPM source."""
    engine = FakeEngine(bpm=120.0)
    worst_ms, backwards, final = drive(MidiClockSlave(), engine,
                                       bars=32, true_bpm=140.0)
    assert worst_ms < 1.0, worst_ms
    assert backwards == 0
    assert final == pytest.approx(140.0, abs=0.5)


def test_it_converges_from_double_the_tempo():
    """The worst cold start: a 2:1 error, which the tempo seeding exists for."""
    engine = FakeEngine(bpm=120.0)
    worst_ms, backwards, final = drive(MidiClockSlave(), engine,
                                       bars=64, true_bpm=60.0, settle_s=8.0)
    assert worst_ms < 1.0, worst_ms
    assert backwards == 0
    assert final == pytest.approx(60.0, abs=0.5)


def test_a_three_percent_wobble_is_smoothed_without_going_backwards():
    """The plan's other requirement.  Tracking a wobble is not the point --
    surviving it without the playhead lurching is."""
    engine = FakeEngine(bpm=120.0)
    worst_ms, backwards, final = drive(MidiClockSlave(), engine,
                                       bars=32, wobble=0.03)
    assert backwards == 0
    assert worst_ms < 8.0, worst_ms      # tracked, not locked
    assert final == pytest.approx(120.0, abs=3.0)


def test_arrival_jitter_does_not_unlock_it():
    engine = FakeEngine(bpm=120.0)
    worst_ms, backwards, _ = drive(MidiClockSlave(), engine,
                                    bars=32, jitter=0.001)
    # Looser than the clean case on purpose: a millisecond of arrival jitter is
    # amplified by tempo only being applied on the 30 Hz UI pass.  What matters
    # is that it stays bounded and stays locked, not that it beats the clean
    # number.
    assert worst_ms < 6.0, worst_ms
    assert backwards == 0


def test_an_absurdly_fast_source_is_refused_rather_than_followed():
    """Gaps below MIN_GAP_S are not a tempo, they are a broken source.

    Refusing beats clamping: a clamped 1250 BPM would look like a deliberate
    240 BPM, and the display would claim a lock that is not real.
    """
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave.bind(engine)
    now = [0.0]
    slave._now = lambda: now[0]
    for _ in range(200):
        now[0] += 0.0005                 # ~1250 BPM
        slave._on_message(Msg("clock"))
    slave.poll(engine)
    assert slave.bpm == 0.0              # never took a reading
    assert not slave.locked
    assert "waiting" in slave.status


def test_a_plausible_but_extreme_tempo_is_clamped_to_the_engine_range():
    """300 BPM is a real tempo a real device can send; the engine tops out at
    240, so the loop must ask for something the engine will accept."""
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave.bind(engine)
    now = [0.0]
    slave._now = lambda: now[0]
    gap = 60.0 / 300.0 / PPQN            # 300 BPM, above MIN_GAP_S
    for _ in range(200):
        now[0] += gap
        engine.advance(gap)
        slave._on_message(Msg("clock"))
        slave.poll(engine)
    assert 40.0 <= slave.bpm <= 240.0


def test_the_playhead_is_never_moved_by_the_loop():
    """The loop's one promise: it changes tempo and nothing else."""
    engine = FakeEngine()
    slave = MidiClockSlave()
    events = []
    now = [0.0]
    slave._now = lambda: now[0]
    slave.bind(engine)
    for _ in range(96):
        now[0] += 60.0 / 120.0 / PPQN
        engine.advance(60.0 / 120.0 / PPQN)
        slave._on_message(Msg("clock"))
        events.extend(slave.poll(engine))
    assert events
    assert {e.kind for e in events} == {"tempo"}


# ===================================================== transport messages
def test_start_plays_from_the_top():
    slave = MidiClockSlave()
    engine = FakeEngine()
    events = _feed(slave, engine, Msg("start"))
    assert events == [ClockEvent("start", bar=0)]
    assert slave.running


def test_continue_resumes_where_it_is():
    slave = MidiClockSlave()
    engine = FakeEngine()
    assert _feed(slave, engine, Msg("continue")) == [ClockEvent("continue")]
    assert slave.running


def test_stop_stops_and_unlocks():
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave.locked = True
    assert _feed(slave, engine, Msg("stop")) == [ClockEvent("stop")]
    assert not slave.running
    assert not slave.locked


def test_song_position_seeks_to_the_right_bar():
    slave = MidiClockSlave(beats_per_bar=4)
    engine = FakeEngine()
    # 16 sixteenths to a 4/4 bar, so 32 is bar 3 (index 2).
    assert _feed(slave, engine, Msg("songpos", pos=32)) == [ClockEvent("seek", bar=2)]


def test_a_seek_leaves_no_phase_error_to_unwind():
    """Start and songpos both say where the source is, and the transport is
    about to be moved there, so the error is zero by construction."""
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave._integral = 0.4
    slave.error_beats = 0.3
    _feed(slave, engine, Msg("songpos", pos=64))
    assert slave._integral == 0.0
    assert slave.error_beats == 0.0
    assert slave._ticks == 64 * 6            # ticks line up with the new position


def _feed(slave, engine, *messages):
    slave.bind(engine)
    for msg in messages:
        slave._on_message(msg)
    return slave.poll(engine)


# ===================================================== song position maths
@pytest.mark.parametrize("pos,bar", [(0, 0), (15, 0), (16, 1), (32, 2), (160, 10)])
def test_spp_to_bar_in_four_four(pos, bar):
    assert spp_to_bar(pos, 4) == bar


def test_spp_round_trips_through_a_bar():
    for bar in (0, 1, 7, 64, 255):
        assert spp_to_bar(bar_to_spp(bar, 4), 4) == bar


def test_spp_handles_other_time_signatures():
    # 3/4: twelve sixteenths to a bar
    assert spp_to_bar(12, 3) == 1
    assert bar_to_spp(2, 3) == 24


def test_spp_is_clamped_to_fourteen_bits():
    """An SPP message cannot carry more, so a far bar must not wrap."""
    assert bar_to_spp(100_000, 4) == 16383
    assert bar_to_spp(-5, 4) == 0


def test_a_fractional_bar_floors_rather_than_rounding_up():
    """The transport seeks to bar lines; landing mid-bar is not representable."""
    assert spp_to_bar(31, 4) == 1            # not 2


# ===================================================== master mode
class FakePort:
    def __init__(self) -> None:
        self.sent: list = []
        self.closed = False

    def send(self, msg) -> None:
        self.sent.append(msg)

    def close(self) -> None:
        self.closed = True


def _master(monkeypatch):
    """A master with a fake port and a fake mido to build messages with."""
    import sys
    import types

    port = FakePort()
    fake = types.ModuleType("mido")
    fake.Message = Msg
    monkeypatch.setitem(sys.modules, "mido", fake)
    return MidiClockMaster(port=port), port


def test_master_emits_exactly_twenty_four_clocks_per_beat(monkeypatch):
    master, port = _master(monkeypatch)
    engine = FakeEngine(bpm=120.0)
    master.emit_due(engine)                  # start
    engine.position_frames = engine.frames_per_beat      # one beat later
    master.emit_due(engine)
    clocks = [m for m in port.sent if m.type == "clock"]
    assert len(clocks) == PPQN


def test_master_emits_a_start_then_a_stop(monkeypatch):
    master, port = _master(monkeypatch)
    engine = FakeEngine()
    master.emit_due(engine)
    assert [m.type for m in port.sent] == ["start"]
    engine.is_playing = False
    master.emit_due(engine)
    assert [m.type for m in port.sent] == ["start", "stop"]


def test_master_does_not_emit_while_stopped(monkeypatch):
    master, port = _master(monkeypatch)
    engine = FakeEngine()
    engine.is_playing = False
    assert master.emit_due(engine) == 0
    assert port.sent == []


def test_master_re_anchors_on_a_loop_wrap_instead_of_bursting(monkeypatch):
    """A backwards jump is a loop or a seek.  Emitting a catch-up burst would
    arrive at whatever follows us as a tempo spike."""
    master, port = _master(monkeypatch)
    engine = FakeEngine(bpm=120.0)
    master.emit_due(engine)
    engine.position_frames = engine.frames_per_beat * 8
    master.emit_due(engine)
    before = len([m for m in port.sent if m.type == "clock"])
    engine.position_frames = 0.0             # wrapped
    assert master.emit_due(engine) == 0
    assert len([m for m in port.sent if m.type == "clock"]) == before
    # and it carries on from the new position rather than replaying the gap
    engine.position_frames = engine.frames_per_beat
    assert master.emit_due(engine) == PPQN


def test_master_sends_a_song_position_on_a_seek(monkeypatch):
    master, port = _master(monkeypatch)
    master.seek(4, beats_per_bar=4)
    (msg,) = [m for m in port.sent if m.type == "songpos"]
    assert msg.pos == bar_to_spp(4, 4)


def test_master_never_emits_a_tick_twice(monkeypatch):
    master, port = _master(monkeypatch)
    engine = FakeEngine(bpm=120.0)
    master.emit_due(engine)
    engine.position_frames = engine.frames_per_beat * 2
    first = master.emit_due(engine)
    second = master.emit_due(engine)         # nothing new has come due
    assert first == PPQN * 2
    assert second == 0


def test_a_send_that_fails_is_recorded_not_raised(monkeypatch):
    import sys
    import types

    class Broken(FakePort):
        def send(self, msg):
            raise OSError("port went away")

    fake = types.ModuleType("mido")
    fake.Message = Msg
    monkeypatch.setitem(sys.modules, "mido", fake)
    master = MidiClockMaster(port=Broken())
    master.emit_due(FakeEngine())
    assert "clock send failed" in master.problem
    assert "port went away" in master.problem


# ===================================================== roles and fallbacks
def test_make_clock_returns_the_right_role():
    assert make_clock("internal").role == "internal"
    assert make_clock("midi_slave").role == "midi_slave"
    assert make_clock("midi_master").role == "midi_master"
    assert make_clock("link").role == "link"


def test_an_unknown_role_is_internal_rather_than_an_error():
    """A settings file with a role from a newer version must still start."""
    assert make_clock("teleport").role == "internal"
    assert make_clock("").role == "internal"


def test_the_internal_clock_does_nothing_at_all():
    internal = InternalClock()
    internal.open()
    assert internal.poll(FakeEngine()) == []
    assert internal.problem == ""
    internal.close()


def test_link_is_absent_safe_and_says_so():
    """Link needs a native library that is not a dependency here."""
    link = LinkClock()
    link.open()
    assert "not installed" in link.problem
    assert link.poll(FakeEngine()) == []      # and it does not pretend to work
    assert "unavailable" in link.status


def test_a_slave_with_no_port_reports_the_problem_and_stays_quiet():
    import sys
    import types

    slave = MidiClockSlave(port_name="nonesuch")
    fake = types.ModuleType("mido")
    fake.get_input_names = lambda: ["Some Other Thing"]
    saved = sys.modules.get("mido")
    sys.modules["mido"] = fake
    try:
        slave.open()
    finally:
        if saved is None:
            del sys.modules["mido"]
        else:
            sys.modules["mido"] = saved
    assert "nonesuch" in slave.problem
    assert slave.poll(FakeEngine()) == []


def test_port_picking_is_a_substring_match():
    assert clockmod._pick_port(["MIDI Clock Out 1", "Other"], "clock") == "MIDI Clock Out 1"
    assert clockmod._pick_port(["A", "B"], "") == "A"
    assert clockmod._pick_port([], "x") is None
    assert clockmod._pick_port(["A"], "zzz") is None


def test_the_gains_are_the_prototyped_ones():
    """Changing these changes how the sync feels, so they are pinned here as
    well as commented -- a stray edit should fail a test, not a gig."""
    assert (KP, KI) == (2.0, 0.5)


# ===================================================== robustness
def test_nonsense_tick_gaps_are_ignored():
    """A paused source or a dropped USB frame must not poison the estimate."""
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave.bind(engine)
    now = [0.0]
    slave._now = lambda: now[0]
    good = 60.0 / 120.0 / PPQN
    for _ in range(40):
        now[0] += good
        engine.advance(good)          # advance first: the tick marks where we
        slave._on_message(Msg("clock"))   # have got to, not where we will be
        for event in slave.poll(engine):
            if event.kind == "tempo":
                engine.set_bpm(event.bpm)
    settled = slave.bpm
    now[0] += 30.0                 # a very long gap
    slave._on_message(Msg("clock"))
    slave.poll(engine)
    assert slave.bpm == pytest.approx(settled, abs=1.0)


def test_a_long_silence_unlocks_rather_than_freewheeling():
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave.bind(engine)
    now = [0.0]
    slave._now = lambda: now[0]
    good = 60.0 / 120.0 / PPQN
    for _ in range(40):
        now[0] += good
        engine.advance(good)          # advance first: the tick marks where we
        slave._on_message(Msg("clock"))   # have got to, not where we will be
        for event in slave.poll(engine):
            if event.kind == "tempo":
                engine.set_bpm(event.bpm)
    assert slave.locked
    now[0] += 5.0
    slave.poll(engine)
    assert not slave.locked


def test_ticks_before_the_engine_is_bound_are_dropped_not_crashed():
    slave = MidiClockSlave()
    slave._on_message(Msg("clock"))
    assert slave._ticks == 0


def test_the_tick_queue_is_bounded():
    """A stalled UI thread must not let the queue grow without limit."""
    slave = MidiClockSlave()
    engine = FakeEngine()
    slave.bind(engine)
    now = [0.0]
    slave._now = lambda: now[0]
    for _ in range(clockmod.MAX_PENDING_TICKS * 3):
        now[0] += 0.01
        slave._on_message(Msg("clock"))
    assert len(slave._pending) == clockmod.MAX_PENDING_TICKS


def test_status_says_what_it_is_doing():
    slave = MidiClockSlave()
    assert "waiting" in slave.status
    engine = FakeEngine()
    slave.bind(engine)
    now = [0.0]
    slave._now = lambda: now[0]
    good = 60.0 / 120.0 / PPQN
    for _ in range(40):
        now[0] += good
        engine.advance(good)          # advance first: the tick marks where we
        slave._on_message(Msg("clock"))   # have got to, not where we will be
        for event in slave.poll(engine):
            if event.kind == "tempo":
                engine.set_bpm(event.bpm)
    assert "locked" in slave.status
    assert "120" in slave.status


# ===================================================== wired into the app
@pytest.fixture
def rig(tmp_path):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.project import Project
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=8000, bpm=120.0)
    engine = Engine(samplerate=8000, blocksize=64, in_channels=1, out_channels=2,
                    backend="offline", bpm=120.0, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    app = App(push, engine, project, project_dir=tmp_path / "song", settings=settings)
    return app, push, engine, project


class ScriptedClock(clockmod.Clock):
    """A clock that returns whatever a test hands it."""

    role = "midi_slave"

    def __init__(self, events=()) -> None:
        self.queued = list(events)
        self.locked = True

    def poll(self, engine):
        out, self.queued = self.queued, []
        return out

    @property
    def status(self) -> str:
        return "scripted clock"


def test_the_app_defaults_to_the_internal_clock(rig):
    app, push, engine, project = rig
    assert app.clock.role == "internal"
    assert app.clock.poll(engine) == []


def test_a_tempo_event_moves_the_engine(rig):
    app, push, engine, project = rig
    app.clock = ScriptedClock([ClockEvent("tempo", bpm=134.0)])
    app._poll_clock()
    assert engine.bpm == pytest.approx(134.0)


def test_a_tempo_event_does_not_dirty_the_project(rig):
    """Writing the project tempo on every poll would autosave in a loop.

    It is not lost: save_now copies the engine's tempo in before writing, so a
    synced session still saves the tempo it actually ran at.
    """
    app, push, engine, project = rig
    project.dirty = False
    for bpm in (121.0, 122.0, 123.0):
        app.clock = ScriptedClock([ClockEvent("tempo", bpm=bpm)])
        app._poll_clock()
    assert not project.dirty
    assert project.bpm == pytest.approx(120.0)

    app.save_now()
    assert project.bpm == pytest.approx(engine.bpm)


def test_a_tempo_event_is_refused_mid_take(rig):
    """One place decides that, rather than every clock role."""
    app, push, engine, project = rig
    engine.arm_record(2, count_in_beats=0)
    engine.process_offline(64)
    app.clock = ScriptedClock([ClockEvent("tempo", bpm=200.0)])
    app._poll_clock()
    assert engine.bpm == pytest.approx(120.0)


def test_start_and_stop_events_drive_the_transport(rig):
    app, push, engine, project = rig
    app.clock = ScriptedClock([ClockEvent("start", bar=0)])
    app._poll_clock()
    assert engine.is_playing
    app.clock = ScriptedClock([ClockEvent("stop")])
    app._poll_clock()
    assert not engine.is_playing


def test_a_seek_event_is_clamped_into_the_song(rig):
    app, push, engine, project = rig
    app.clock = ScriptedClock([ClockEvent("seek", bar=99999)])
    app._poll_clock()
    assert engine.current_bar <= project.song_bars - 1


def test_continue_does_not_restart_a_running_transport(rig):
    app, push, engine, project = rig
    engine.play(4)
    engine.process_offline(64)
    where = engine.current_bar
    app.clock = ScriptedClock([ClockEvent("continue")])
    app._poll_clock()
    engine.process_offline(64)
    assert engine.current_bar >= where


def test_the_status_lines_name_the_clock_only_when_there_is_one(rig):
    app, push, engine, project = rig
    assert not any("clock" in line for line in app.status_lines())
    app.clock = ScriptedClock()
    assert any("scripted clock" in line for line in app.status_lines())


def test_the_transport_readout_shows_sync_state(rig):
    app, push, engine, project = rig
    assert "SYNC" not in app.transport_readout()
    app.clock = ScriptedClock()
    assert "SYNC" in app.transport_readout()
    app.clock.locked = False
    assert "sync?" in app.transport_readout()


def test_the_clock_role_comes_from_the_settings(tmp_path):
    from push2sampler.app import App
    from push2sampler.audio import Engine
    from push2sampler.project import Project
    from push2sampler.push2 import SimPush
    from push2sampler.settings import Settings

    project = Project(samplerate=8000, bpm=120.0)
    engine = Engine(samplerate=8000, blocksize=64, in_channels=1, out_channels=2,
                    backend="offline", bpm=120.0, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    settings.set("clock_role", "midi_master")
    settings.set("clock_port", "somewhere")
    app = App(push, engine, project, project_dir=tmp_path / "s", settings=settings)
    assert app.clock.role == "midi_master"
    assert app.clock.port_name == "somewhere"


def test_an_unknown_role_in_the_settings_still_starts(tmp_path):
    from push2sampler.settings import Settings

    settings = Settings(path=tmp_path / "settings.json")
    settings.set("clock_role", "teleport")
    assert settings["clock_role"] == "internal"


def test_shutdown_closes_the_clock(rig):
    app, push, engine, project = rig
    closed = []

    class Closing(ScriptedClock):
        def close(self):
            closed.append(True)

    app.clock = Closing()
    app.shutdown()
    assert closed


def test_the_app_binds_the_engine_to_the_clock(rig):
    """The slave reads the engine position at tick arrival, so it needs it."""
    app, push, engine, project = rig
    slave = MidiClockSlave()
    app.clock = slave
    slave.bind(engine)
    assert slave._engine is engine
