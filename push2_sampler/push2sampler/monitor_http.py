"""A read-only monitor page, served on localhost (NH-12).

`--monitor-port 8765` opens a small web page showing the live grid, the
transport, the status lines and the button lamps -- the surface, mirrored, in
anything with a browser.  It exists for three things the device itself cannot
do: teaching (a class watching one Push), streaming (an overlay without a
camera pointed at your hands), and debugging the LED state without hardware at
all, since the simulator publishes the same snapshot.

Three rules hold the design up, and each one is a refusal:

**It never accepts a command.**  Every request but ``GET`` and ``HEAD`` is
refused with 405, and no path reads a query string.  A page that could press a
pad would mean a hole in the surface reachable by anything that can open a
socket; a page that can only watch is safe to leave running.

**It never touches the app.**  The render thread *publishes* a finished
snapshot -- a plain dict built once and never mutated -- and the request
threads only ever read the latest reference.  Python's attribute store gives us
that for free, so there is no lock anywhere in here, in a program whose whole
audio design is built on not having any.

**It binds to loopback unless told otherwise.**  A monitor is for you and the
room you are in.  Your slot names, your tempo and your song length are not
interesting to a network, and ``--monitor-host`` warns when you ask for one.

No dependency: `http.server`, `json` and a `<script>` tag.  The page holds one
`EventSource` open to ``/events`` and redraws from whatever arrives, so a
browser that has been asleep catches up on one message rather than replaying a
backlog.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: What `--monitor-port` uses when given no number.
DEFAULT_PORT = 8765
#: Interface to bind to.  Loopback: see the module docstring.
DEFAULT_HOST = "127.0.0.1"
#: Hosts that keep the page to this machine.  Anything else is a warning.
LOOPBACK = ("127.0.0.1", "::1", "localhost")
#: How often a streaming thread looks for a newer snapshot.
POLL_S = 0.05
#: A comment sent when nothing has changed, so a proxy does not time the
#: connection out and the browser does not think the instrument has died.
KEEPALIVE_S = 15.0
#: Requests dropped after this long with no snapshot at all, which only happens
#: if the app stopped ticking -- better to close than to hold a socket open.
STALE_S = 10.0
#: How often the accept loop checks whether it has been shut down.
SHUTDOWN_POLL_S = 0.05
#: How long a `/snapshot.json` fetch keeps the app publishing.  Long enough for
#: a script polling once a second to keep itself fed, short enough that one
#: curl does not leave the app working for a reader who has gone.
POLL_INTEREST_S = 5.0


class Monitor:
    """The server, its thread, and the one snapshot everybody reads.

    Built by the app when `monitor_port` is set, started once, and closed on
    shutdown.  :meth:`publish` is the only thing the app calls per frame, and
    it is deliberately a single attribute store: building the snapshot is the
    app's cost, and serialising it is the reader's.
    """

    def __init__(self, port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> None:
        self.port = int(port)
        self.host = host
        self.error: str | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._closing = threading.Event()
        #: The latest snapshot and a counter that says whether it is new.  A
        #: reader compares the counter rather than the dict, because comparing
        #: two 64-entry dicts thirty times a second to avoid sending 2 KB is
        #: the wrong trade.
        self._snapshot: dict | None = None
        self._seq = 0
        self._published_at = 0.0
        #: Streams currently open.  The app uses it to skip building a snapshot
        #: nobody is going to read.
        self._clients = 0
        #: When ``/snapshot.json`` was last fetched.  A script polling the JSON
        #: never opens a stream, so without this it would be told "nothing has
        #: been published" forever -- an endpoint that is permanently empty is
        #: not an endpoint.
        self._polled_at = 0.0

    # -- lifecycle ---------------------------------------------------------
    @property
    def url(self) -> str:
        host = "localhost" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}/"

    @property
    def exposed(self) -> bool:
        """True when the page is reachable from somewhere other than here."""
        return self.host not in LOOPBACK

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def watchers(self) -> int:
        return self._clients

    def start(self) -> bool:
        """Open the port.  False (with :attr:`error` set) if it cannot be.

        A port already in use is a message, not a crash: the monitor is a
        convenience and the instrument must come up without it.
        """
        if self._server is not None:
            return True
        monitor = self

        class Handler(_MonitorHandler):
            pass

        Handler.monitor = monitor
        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as exc:
            self.error = f"monitor port {self.port}: {exc.strerror or exc}"
            self._server = None
            return False
        # Daemon threads so a stuck stream can never hold the process open;
        # the streams themselves watch _closing and leave on their own.
        self._server.daemon_threads = True
        # A tighter poll than the 0.5 s default: shutdown() waits for the next
        # one, and half a second is a long time to hold up quitting.
        self._thread = threading.Thread(
            target=self._server.serve_forever, args=(SHUTDOWN_POLL_S,),
            name="monitor-http", daemon=True,
        )
        self._thread.start()
        return True

    def close(self) -> None:
        self._closing.set()
        server, self._server = self._server, None
        if server is None:
            return
        try:
            server.shutdown()
        except Exception:  # pragma: no cover - already down
            pass
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- the snapshot ------------------------------------------------------
    def publish(self, snapshot: dict) -> None:
        """Make `snapshot` the one readers see.  Called from the render thread.

        The dict must be freshly built and never touched again: readers hold
        the reference while they serialise it, and mutating it underneath them
        is how you get half of one frame and half of the next.
        """
        self._seq += 1
        snapshot["seq"] = self._seq
        self._published_at = time.monotonic()
        # Last: until this assignment lands, readers see the previous frame,
        # which is whole.  There is no window in which they see a partial one.
        self._snapshot = snapshot

    @property
    def wanted(self) -> bool:
        """Whether building a snapshot is worth the app's time.

        Nobody watching means nobody to read it, so the app skips the work
        entirely -- a monitor left enabled and unopened costs one attribute
        read per frame.  A recent ``/snapshot.json`` counts as watching, so
        polling the JSON works without holding a stream open.
        """
        if self._clients > 0:
            return True
        return time.monotonic() - self._polled_at < POLL_INTEREST_S

    def latest(self) -> tuple[int, dict | None]:
        return self._seq, self._snapshot

    def note_poll(self) -> None:
        """Record that someone fetched the JSON, so the app keeps publishing."""
        self._polled_at = time.monotonic()

    # -- bookkeeping for the handler ---------------------------------------
    def _opened(self) -> None:
        self._clients += 1

    def _closed(self) -> None:
        self._clients = max(0, self._clients - 1)

    @property
    def closing(self) -> threading.Event:
        return self._closing


class _MonitorHandler(BaseHTTPRequestHandler):
    """Three paths, all read-only.  Anything else is 404 or 405."""

    monitor: Monitor = None  # type: ignore[assignment]
    server_version = "push2sampler-monitor"
    #: HTTP/1.1 so the event stream can be chunk-free and kept open.
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D102 - silence the default log
        """Swallow the access log.

        It goes to stderr, and stderr is where the instrument's own messages
        go.  A page open in a browser would scroll the terminal forever.
        """

    # -- the only two verbs -----------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif path == "/snapshot.json":
            # Asking counts as watching: the next tick will publish, so a
            # second fetch has something in it even with no stream open.
            self.monitor.note_poll()
            _seq, snapshot = self.monitor.latest()
            body = json.dumps(snapshot or {}).encode("utf-8")
            self._send(200, "application/json", body)
        elif path == "/events":
            self._stream()
        else:
            self._send(404, "text/plain; charset=utf-8", b"no such page\n")

    def do_HEAD(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        known = path in ("/", "/index.html", "/snapshot.json", "/events")
        self.send_response(200 if known else 404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _refuse(self) -> None:
        """Every writing verb.  The monitor watches; it does not act."""
        self._send(
            405, "text/plain; charset=utf-8",
            b"the monitor is read-only: it can show you the surface, "
            b"not press it\n",
            extra={"Allow": "GET, HEAD"},
        )

    do_POST = do_PUT = do_DELETE = do_PATCH = _refuse

    # -- plumbing ----------------------------------------------------------
    def _send(self, code: int, content_type: str, body: bytes,
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _stream(self) -> None:
        """Server-sent events: one message per new snapshot, until you close it."""
        monitor = self.monitor
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        monitor._opened()
        sent = -1
        last_write = time.monotonic()
        try:
            while not monitor.closing.is_set():
                seq, snapshot = monitor.latest()
                now = time.monotonic()
                if snapshot is not None and seq != sent:
                    payload = json.dumps(snapshot)
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    sent = seq
                    last_write = now
                elif now - last_write >= KEEPALIVE_S:
                    # A comment: valid SSE, ignored by the browser, and enough
                    # to keep an idle connection from being reaped.
                    self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
                    last_write = now
                elif snapshot is None and now - last_write >= STALE_S:
                    break
                monitor.closing.wait(POLL_S)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # The browser closed the tab.  Not an error: it is how a stream ends.
            pass
        finally:
            monitor._closed()


#: The page.  One file, no build step, no CDN -- it has to work on a machine
#: with no network, because so does everything else here.
PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>push2sampler monitor</title>
<style>
  :root { color-scheme: dark; --ink: #e8e8ea; --dim: #8a8a92; --ground: #14141a; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 16px; background: var(--ground); color: var(--ink);
         font: 14px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  header { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline;
           margin-bottom: 14px; }
  h1 { font-size: 15px; font-weight: 600; letter-spacing: .12em; margin: 0;
       text-transform: uppercase; }
  #banner { font-size: 22px; font-weight: 700; letter-spacing: .06em; }
  #banner.recording { color: #ff5b5b; }
  #banner.armed { color: #ffb300; }
  #readout { font-size: 18px; color: var(--dim); }
  #link { margin-left: auto; color: var(--dim); font-size: 12px; }
  main { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }
  #grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px;
          width: min(72vw, 420px); flex: 0 0 auto; }
  #grid div { aspect-ratio: 1; border-radius: 4px; background: #07070a;
              box-shadow: inset 0 0 0 1px #2a2a33; transition: background .08s linear; }
  /* The pads carry the device's own RGB, and an LED at 14% looks brighter in a
     dark room than #242424 does on a lit screen.  Rather than lie about the
     colour, offer a lift: off by default, so what you see is what the Push is
     told, and one click away when you are reading dim states. */
  #grid.boost { filter: brightness(2.4) saturate(.9); }
  label#boost { color: var(--dim); font-size: 12px; cursor: pointer;
                user-select: none; }
  aside { flex: 1 1 260px; min-width: 240px; }
  pre { margin: 0 0 14px; white-space: pre-wrap; word-break: break-word; }
  h2 { font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
       color: var(--dim); margin: 0 0 6px; font-weight: 600; }
  #lamps { display: flex; flex-wrap: wrap; gap: 4px; }
  #lamps span { padding: 2px 6px; border-radius: 3px; font-size: 11px;
                background: #1f1f27; color: #5d5d66; }
  #lamps span.on { background: #3a3a48; color: var(--ink); }
  #lamps span.bright { background: var(--ink); color: #14141a; }
  #dead { display: none; color: #ff5b5b; margin-top: 12px; }
  body.offline #dead { display: block; }
  body.offline main { opacity: .35; }
</style>
</head><body>
<header>
  <h1>push2sampler</h1>
  <span id="banner">waiting</span>
  <span id="readout"></span>
  <label id="boost"><input type="checkbox" id="boostbox"> brighten dim pads</label>
  <span id="link">read-only</span>
</header>
<main>
  <div id="grid"></div>
  <aside>
    <h2>display</h2>
    <pre id="lines"></pre>
    <h2>buttons</h2>
    <div id="lamps"></div>
  </aside>
</main>
<p id="dead">connection lost &mdash; is the instrument still running?</p>
<script>
const grid = document.getElementById('grid');
const cells = [];
for (let i = 0; i < 64; i++) {
  const d = document.createElement('div');
  grid.appendChild(d);
  cells.push(d);
}
const lamps = document.getElementById('lamps');
const lampFor = {};

const box = document.getElementById('boostbox');
// Remembered per browser: a teacher who wants the lift wants it every lesson.
try { box.checked = localStorage.getItem('boost') === '1'; } catch (e) {}
function applyBoost() {
  grid.classList.toggle('boost', box.checked);
  try { localStorage.setItem('boost', box.checked ? '1' : '0'); } catch (e) {}
}
box.addEventListener('change', applyBoost);
applyBoost();

function draw(s) {
  document.body.classList.remove('offline');
  const b = document.getElementById('banner');
  b.textContent = s.banner || '';
  b.className = s.banner_state || 'normal';
  document.getElementById('readout').textContent = s.readout || '';
  document.getElementById('lines').textContent = (s.lines || []).join('\\n');
  const pads = s.pads || [];
  for (let i = 0; i < cells.length; i++) {
    cells[i].style.background = pads[i] || '#07070a';
  }
  for (const [name, level] of Object.entries(s.buttons || {})) {
    let el = lampFor[name];
    if (!el) {
      el = document.createElement('span');
      el.textContent = name;
      lamps.appendChild(el);
      lampFor[name] = el;
    }
    el.className = level >= 100 ? 'bright' : (level > 0 ? 'on' : '');
  }
  for (const [name, el] of Object.entries(lampFor)) {
    if (!(name in (s.buttons || {}))) el.className = '';
  }
}

// One EventSource, and the browser's own reconnection: if the instrument goes
// away and comes back, the page picks it up without being reloaded.
const source = new EventSource('/events');
source.onmessage = (e) => draw(JSON.parse(e.data));
source.onerror = () => document.body.classList.add('offline');
</script>
</body></html>
"""
