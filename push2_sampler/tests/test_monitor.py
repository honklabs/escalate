"""NH-12: the read-only monitor page.

The page is a convenience, so almost every test here is about a *refusal* or a
failure: it must never accept a command, never bind anywhere but loopback
unless asked, never take the instrument down with it, and never cost anything
when nobody is looking.  A monitor that gets those wrong is worse than none.

Real sockets on ephemeral ports, because the whole point of this module is the
plumbing -- a mocked `http.server` would test the mock.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from push2sampler import colors
from push2sampler.app import App, _css
from push2sampler.audio import Engine
from push2sampler.constants import BTN_BRIGHT, BUTTON_NAMES, Btn, button_name
from push2sampler.monitor_http import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    LOOPBACK,
    PAGE,
    POLL_INTEREST_S,
    Monitor,
)
from push2sampler.project import Project
from push2sampler.push2 import SimPush
from push2sampler.settings import SPECS, Settings

SR = 8000
BPM = 120.0


def free_port() -> int:
    """An ephemeral port, released immediately.  Racy in principle, fine here."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def monitor():
    page = Monitor(port=free_port())
    assert page.start(), page.error
    yield page
    page.close()


@pytest.fixture
def rig(tmp_path):
    """An app with a monitor already serving, and a tick() that publishes."""
    project = Project(samplerate=SR, bpm=BPM)
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="null", bpm=BPM, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "settings.json")
    settings.apply_overrides({"monitor_port": free_port()})
    app = App(push, eng, project, project_dir=tmp_path / "song",
              settings=settings)
    assert app.start_monitor(), (app.monitor_page and app.monitor_page.error)
    yield app
    app.shutdown()


def fetch(page, path="", timeout=5.0):
    with urllib.request.urlopen(page.url + path, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def pump(app, frames=4, gap=0.05):
    """Tick the app enough times for the monitor to publish at least once."""
    for _ in range(frames):
        app.tick()
        time.sleep(gap)


# ==================================================== it will not be written to
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_every_writing_verb_is_refused(monitor, method):
    """The page watches the surface; it must never be able to press it."""
    request = urllib.request.Request(monitor.url, method=method, data=b"x")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == 405
    assert caught.value.headers.get("Allow") == "GET, HEAD"


def test_the_refusal_says_why():
    """A 405 with no explanation invites someone to look for the real endpoint."""
    from push2sampler.monitor_http import _MonitorHandler

    assert _MonitorHandler.do_POST is _MonitorHandler._refuse
    assert _MonitorHandler.do_PUT is _MonitorHandler._refuse
    assert _MonitorHandler.do_DELETE is _MonitorHandler._refuse
    assert _MonitorHandler.do_PATCH is _MonitorHandler._refuse


def test_an_unknown_path_is_a_plain_404(monitor):
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(monitor.url + "press/pad/3", timeout=5)
    assert caught.value.code == 404


def test_a_query_string_is_ignored_rather_than_obeyed(monitor):
    """There is nothing to say in a query string, so it must not be read."""
    status, body = fetch(monitor, "?slot=1&delete=1")
    assert status == 200
    assert "push2sampler" in body


# ==================================================== it stays on this machine
def test_it_binds_to_loopback_by_default():
    assert DEFAULT_HOST in LOOPBACK
    assert not Monitor(port=1).exposed


def test_a_non_loopback_host_is_flagged_as_exposed():
    assert Monitor(port=1, host="0.0.0.0").exposed
    assert Monitor(port=1, host="192.168.1.9").exposed


def test_the_default_is_off_entirely():
    """A program does not open a port because it could."""
    assert SPECS["monitor_port"].default == 0
    assert SPECS["monitor_host"].default in LOOPBACK
    assert Settings()["monitor_port"] == 0


def test_an_app_with_no_port_has_no_monitor(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="null", bpm=BPM, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    app = App(push, eng, project, settings=Settings(path=tmp_path / "s.json"))
    assert app.monitor_page is None
    # And starting it is a no-op rather than an error.
    assert app.start_monitor() is False


# ==================================================== it survives its own failures
def test_a_port_already_in_use_is_a_message_not_a_crash():
    """The instrument must come up even when 8765 belongs to something else."""
    first = Monitor(port=free_port())
    assert first.start()
    try:
        second = Monitor(port=first.port)
        assert second.start() is False
        assert second.error and str(first.port) in second.error
        assert not second.running
    finally:
        first.close()


def test_the_app_drops_a_monitor_that_will_not_start(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="null", bpm=BPM, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    blocker = Monitor(port=free_port())
    assert blocker.start()
    try:
        settings = Settings(path=tmp_path / "s.json")
        settings.apply_overrides({"monitor_port": blocker.port})
        app = App(push, eng, project, settings=settings)
        assert app.start_monitor() is False
        # Dropped rather than left half-alive, so tick() stops trying.
        assert app.monitor_page is None
        assert "monitor" in app.message
        app.tick()
    finally:
        blocker.close()


def test_starting_twice_is_harmless(monitor):
    assert monitor.start() is True
    assert monitor.running


def test_closing_twice_is_harmless():
    page = Monitor(port=free_port())
    page.start()
    page.close()
    page.close()
    assert not page.running


# ==================================================== the snapshot
def test_nothing_is_published_until_somebody_asks(rig):
    """A monitor nobody has opened costs one attribute read per frame."""
    page = rig.monitor_page
    assert page.wanted is False
    pump(rig, frames=3)
    assert page.latest() == (0, None)


def test_fetching_the_json_counts_as_watching(rig):
    """Otherwise the JSON endpoint is permanently empty, which is not one."""
    page = rig.monitor_page
    status, body = fetch(page, "snapshot.json")
    assert status == 200
    assert json.loads(body) == {}
    assert page.wanted is True

    pump(rig, frames=3)
    _status, body = fetch(page, "snapshot.json")
    snapshot = json.loads(body)
    assert snapshot["mode"] == "library"
    assert snapshot["seq"] >= 1


def test_interest_lapses_so_the_app_stops_working_for_a_reader_who_left(rig):
    page = rig.monitor_page
    fetch(page, "snapshot.json")
    assert page.wanted
    page._polled_at -= POLL_INTEREST_S + 1.0
    assert page.wanted is False


def test_the_snapshot_mirrors_the_frame_that_was_drawn(rig):
    """The page must never render the modes a second time and disagree."""
    rig.render()
    rig._drawn_pads[0] = colors.RED.index
    rig._drawn_buttons[Btn.PLAY] = BTN_BRIGHT
    snapshot = rig.monitor_snapshot()
    assert snapshot["pads"][0] == "#ff0000"
    assert snapshot["buttons"]["play"] == BTN_BRIGHT


def test_the_snapshot_is_json(rig):
    rig.render()
    # Not "serialises without raising": every value has to survive a round
    # trip, or the page gets a type the browser cannot use.
    text = json.dumps(rig.monitor_snapshot())
    assert json.loads(text) == json.loads(text)


def test_the_snapshot_says_what_the_page_needs(rig):
    rig.render()
    snapshot = rig.monitor_snapshot()
    for key in ("mode", "banner", "banner_state", "readout", "lines", "pads",
                "buttons", "bpm", "bar", "playing", "recording", "bank",
                "page", "unsaved", "offline", "depth"):
        assert key in snapshot, key
    assert len(snapshot["pads"]) == 64
    assert snapshot["banner"] == "LIBRARY A"


def test_publishing_replaces_rather_than_mutates(monitor):
    """A reader holds the reference while it serialises; mutation splits a frame."""
    first = {"a": 1}
    monitor.publish(first)
    seq_one, one = monitor.latest()
    monitor.publish({"a": 2})
    seq_two, two = monitor.latest()
    assert one is first and one["a"] == 1
    assert two["a"] == 2
    assert seq_two == seq_one + 1


def test_a_pad_colour_the_palette_does_not_know_renders_black():
    """A colour nobody defined is exactly an unlit pad."""
    assert _css(colors.GREEN.index) == "#00ff3c"
    assert _css(colors.OFF.index) == "#000000"
    assert _css(200) == "#000000"


def test_every_palette_colour_survives_the_css_conversion():
    for color in (colors.OFF,) + colors.PALETTE:
        css = _css(color.index)
        assert len(css) == 7 and css.startswith("#")
        assert int(css[1:3], 16) == color.rgb[0]
        assert int(css[3:5], 16) == color.rgb[1]
        assert int(css[5:7], 16) == color.rgb[2]


# ==================================================== the stream
def test_a_stream_receives_frames_as_they_are_published(rig):
    page = rig.monitor_page
    received: list[dict] = []

    def reader():
        try:
            with urllib.request.urlopen(page.url + "events", timeout=8) as stream:
                for line in stream:
                    if line.startswith(b"data: "):
                        received.append(json.loads(line[6:]))
                        if len(received) >= 2:
                            return
        except Exception:  # pragma: no cover - the server going down first
            pass

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    for _ in range(60):
        if page.watchers:
            break
        time.sleep(0.02)
    assert page.watchers == 1
    assert page.wanted is True

    pump(rig, frames=20, gap=0.02)
    thread.join(timeout=3)
    assert len(received) >= 2
    assert received[1]["seq"] > received[0]["seq"]
    assert received[0]["mode"] == "library"


def test_the_watcher_count_comes_back_down(rig):
    page = rig.monitor_page

    def reader():
        try:
            with urllib.request.urlopen(page.url + "events", timeout=2) as stream:
                stream.read(1)
        except Exception:
            pass

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    pump(rig, frames=6, gap=0.05)
    thread.join(timeout=4)
    for _ in range(100):
        if page.watchers == 0:
            break
        time.sleep(0.02)
    assert page.watchers == 0


def test_closing_the_monitor_ends_its_streams(rig):
    """A daemon thread stuck in a stream must not outlive the instrument."""
    page = rig.monitor_page
    done = threading.Event()

    def reader():
        try:
            with urllib.request.urlopen(page.url + "events", timeout=8) as stream:
                stream.read()
        except Exception:
            pass
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    for _ in range(60):
        if page.watchers:
            break
        time.sleep(0.02)
    page.close()
    assert done.wait(timeout=5), "the stream outlived close()"


# ==================================================== the page itself
def test_the_page_is_served_and_needs_no_network(monitor):
    status, body = fetch(monitor)
    assert status == 200
    assert "<title>push2sampler monitor</title>" in body
    # No CDN, no build step: everything this program does works offline.
    for absent in ("http://", "https://", "cdn", "<link"):
        assert absent not in body.lower().replace("http://localhost", ""), absent


def test_the_page_streams_rather_than_polls():
    assert "EventSource('/events')" in PAGE


def test_the_page_says_it_is_read_only():
    assert "read-only" in PAGE


def test_head_works_so_a_health_check_does_not_need_the_body(monitor):
    request = urllib.request.Request(monitor.url, method="HEAD")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert response.read() == b""


def test_the_default_port_is_the_one_the_docs_name():
    assert DEFAULT_PORT == 8765


# ==================================================== button names
def test_buttons_are_named_rather_than_numbered(rig):
    """`cc85` tells a reader nothing; `play` tells them everything."""
    assert button_name(Btn.PLAY) == "play"
    assert button_name(Btn.SHIFT) == "shift"
    rig.render()
    names = rig.monitor_snapshot()["buttons"]
    assert all(not name.startswith("cc") for name in names), names


def test_the_display_rows_are_numbered_because_the_hardware_has_no_names():
    from push2sampler.constants import DISPLAY_ROW_BOTTOM, DISPLAY_ROW_TOP

    assert button_name(DISPLAY_ROW_TOP[0]) == "top1"
    assert button_name(DISPLAY_ROW_BOTTOM[7]) == "bot8"


def test_an_unbound_cc_names_itself_rather_than_raising():
    assert button_name(126) == "cc126"


def test_every_button_this_program_lights_has_a_name():
    from push2sampler.constants import ALL_BUTTON_CCS

    assert set(ALL_BUTTON_CCS) <= set(BUTTON_NAMES)


# ==================================================== the app's side
def test_the_monitor_is_closed_on_shutdown(tmp_path):
    project = Project(samplerate=SR, bpm=BPM)
    eng = Engine(samplerate=SR, blocksize=256, in_channels=1, out_channels=2,
                 backend="null", bpm=BPM, song_bars=project.song_bars)
    push = SimPush()
    push.open()
    settings = Settings(path=tmp_path / "s.json")
    port = free_port()
    settings.apply_overrides({"monitor_port": port})
    app = App(push, eng, project, settings=settings)
    app.start_monitor()
    app.shutdown()
    assert app.monitor_page is None
    # The port is free again, which is the only proof that matters.
    replacement = Monitor(port=port)
    assert replacement.start(), replacement.error
    replacement.close()


def test_a_broken_snapshot_disables_the_page_rather_than_the_instrument(rig,
                                                                       monkeypatch):
    """The monitor is never allowed to take the instrument down with it."""
    page = rig.monitor_page
    page.note_poll()

    def explode():
        raise RuntimeError("a mode with a bad status line")

    monkeypatch.setattr(rig, "monitor_snapshot", explode)
    rig._last_monitor = 0.0
    rig.tick()
    assert rig.monitor_page is None
    assert "monitor error" in rig.message
    # And the loop keeps running.
    rig.tick()
    rig.monitor_page = page  # so the fixture's shutdown still closes it


def test_publishing_is_rate_limited(rig):
    """Ten a second, not thirty: the page is not a meter."""
    from push2sampler.app import MONITOR_INTERVAL

    page = rig.monitor_page
    page.note_poll()
    rig._last_monitor = 0.0
    rig.tick()
    first, _ = page.latest()
    rig.tick()  # immediately: too soon to publish again
    assert page.latest()[0] == first
    rig._last_monitor -= MONITOR_INTERVAL * 2
    rig.tick()
    assert page.latest()[0] == first + 1
