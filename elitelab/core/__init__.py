"""The EliteLab core: bus + store + services + http + module loader + journal watcher.

Modules receive the ``Core`` instance in ``setup(core, module)`` and use:

    core.bus.on("journal.FSDJump", fn)            react to game events
    core.store.set("myns", "key", value)          publish state (pushed to the UI via SSE)
    core.store.get("journal", "system")           read another module's state
    core.http.route("/api/x", fn, tool="x", ...)  expose an endpoint that is also an AI tool
    core.services.fetch_json(url, body)           cached HTTP
    core.data_path("myns", "file.json")           a persistent file under the data dir
"""
import json
import logging
import os
import threading
import time

from . import config
from .bus import EventBus
from .http import HttpServer, Router
from .loader import load_all
from .services import Services
from .store import Store
from .watcher import JournalWatcher, journal_files

log = logging.getLogger("elitelab.core")
_SOURCE_TEXT = {"flag": "command line flag", "env": "environment variable", "file": "settings file", "default": "default"}


class Core:
    def __init__(self):
        self.config = config
        self.log = log
        self.bus = EventBus()
        self.store = Store(self.bus)
        self.services = Services()
        self.http = Router()
        self.ready = False
        self.modules = {}
        self.shutdown_callbacks = []
        self.watcher = JournalWatcher(self.bus)
        self._server = HttpServer(self)
        self.ready = False
        self.restart_requested = False
        self._register_builtin_routes()

    # -- helpers for modules ---------------------------------------------------
    def data_path(self, *parts):
        os.makedirs(config.DATA_DIR, exist_ok=True)
        return os.path.join(config.DATA_DIR, *parts)

    def read_data(self, *parts, default=None):
        try:
            with open(self.data_path(*parts), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def write_data(self, value, *parts):
        p = self.data_path(*parts)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2)
        os.replace(tmp, p)

    # -- built-in routes -----------------------------------------------------------
    def _register_builtin_routes(self):
        from .. import __version__
        self.http.route("/api/health", lambda q: {"ok": True, "application":"EliteLab", "ready":self.ready, "pid":os.getpid(), "source_dir":config.ROOT,
                                                  "version": __version__, "journal_dir": config.JOURNAL_DIR,
                                                  "journal_found": bool(journal_files()), "modules": list(self.modules)},
                        tool="health", description="Server health, version, journal folder and loaded modules.")
        self.http.route("/api/shutdown", self.shutdown, method="POST", tool="stop_elitelab",
                        description="Stop this local EliteLab instance, close its party and release its ports. Does not change saved jobs or inventories.")
        self.http.route("/api/state", lambda q: self.store.snapshot(),
                        tool="get_state", description="Full live state snapshot: every module namespace (journal, powerplay, loop, materials...). Large; prefer the specific tools when you only need one thing.")
        self.http.route("/api/modules", lambda q: [m.to_json() for m in sorted(self.modules.values(), key=lambda m: (m.order, m.name))],
                        tool="list_modules", description="Loaded modules with what they require/provide and their UI cards.")
        self.http.route("/api/schema", lambda q: {"version": __version__, "tools": [r.schema() for r in self.http.tools.values()]},
                        tool="list_tools", description="Every API route that is exposed as an AI tool, with parameter schemas.")
        self.http.route("/api/events", lambda q: self._recent_events(q),
                        tool="get_recent_events", description="Most recent raw journal events (newest first). Useful to see exactly what the game just did.",
                        params={"limit": {"type": "integer", "description": "How many events (max 200)", "default": 30},
                                "event": {"type": "string", "description": "Only this event type, e.g. MarketSell"}})
        self._ring = []
        self._ring_lock = threading.Lock()
        self.bus.on("journal.*", self._remember_event)

    def _remember_event(self, name, ev):
        if name.startswith("journal.file.") or name == "journal.replay.done":
            return
        with self._ring_lock:
            self._ring.append(ev)
            if len(self._ring) > 500:
                del self._ring[:-500]

    def _recent_events(self, q):
        limit = max(1, min(int(q.get("limit", 30) or 30), 200))
        with self._ring_lock:
            ring = list(self._ring)
        evs = [e for e in reversed(ring) if not q.get("event") or e.get("event") == q["event"]]
        return [{k: v for k, v in e.items() if k != "_replay"} for e in evs[:limit]]

    # -- lifecycle -----------------------------------------------------------
    def shutdown(self, q=None):
        # Reply before the main loop closes sockets and notifies party members.
        timer = threading.Timer(.1, self._server.stop)
        timer.daemon = True
        timer.start()
        return {"stopping": True}

    def request_restart(self):
        """Ask the running server to stop and make start() return RESTART_EXIT_CODE."""
        self.restart_requested = True
        t = threading.Timer(0.1, self._server.stop)
        t.daemon = True
        t.start()

    def _open_browser(self, host, port, path="/"):
        """Open only after this process answers a ready health probe; stop cancels pending work."""
        from ..window import open_dashboard
        from ..instance import health
        url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}/"

        def open_when_ready():
            deadline = time.monotonic() + 10
            while self.ready and time.monotonic() < deadline:
                state = health(url, config.AUTH_TOKEN)
                if state and state.get("ready") and state.get("pid") == os.getpid():
                    if self.ready:
                        open_dashboard(url + path.lstrip("/"), config)
                    return
                time.sleep(.1)
            if self.ready:
                log.warning("Browser readiness check timed out; open %s%s", url, path.lstrip("/"))

        t = threading.Timer(0.1, open_when_ready)
        t.daemon = True
        t.start()
        return t

    def start(self, host=None, port=None, *, open_browser=False, browser_path="/"):
        """Serve until stopped. Returns RESTART_EXIT_CODE if a restart was requested, 1 if the address could not be
        bound (after printing one line naming the host, port, their sources and the settings file), else 0.
        With open_browser, browser_path opens only after this process answers a ready health probe."""
        from .. import __version__
        host, port = host or config.HOST, port if port is not None else config.PORT
        browser = None
        try:
            try:
                self._server.bind(host, port)
            except OSError as e:
                src = {k: _SOURCE_TEXT.get(config.SOURCES.get(k), "default") for k in ("host", "port")}
                print(f"EliteLab could not listen on {host}:{port} ({e.strerror or e}); host from {src['host']}, "
                      f"port from {src['port']}; settings file: {config.SETTINGS_PATH}")
                return 1
            load_all(self)
            self.watcher.start()
            port = self._server.srv.server_port          # the real port, also when 0 asked the OS to pick one
            print(f"EliteLab {__version__} listening on http://{host}:{port}")
            print(f"Journal dir: {config.JOURNAL_DIR}  (found: {bool(journal_files())})")
            print(f"Modules: {', '.join(self.modules) or 'none'}")
            print("Ctrl+C to stop.")
            if browser_path == "/setup/":
                print(f"Setup: http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}/setup/")
            self.ready = True
            if open_browser:
                browser = self._open_browser(host, port, browser_path)
            self._server.serve()
        except KeyboardInterrupt:
            pass
        finally:
            self.ready = False
            if browser:
                browser.cancel()        # a stop requested before serve() returns at once; do not open a closing server
            self.close()
        return config.RESTART_EXIT_CODE if self.restart_requested else 0

    def close(self):
        """Stop watching journals and run module shutdown callbacks (flush writer
        threads, leave parties). Safe before start() and safe to call twice."""
        self.ready = False
        self.watcher.stop()
        if self._server.srv is not None:
            self._server.srv.server_close()
        callbacks, self.shutdown_callbacks = list(self.shutdown_callbacks), []
        for callback in reversed(callbacks):
            try:
                callback()
            except Exception:
                log.exception("Shutdown cleanup failed")
