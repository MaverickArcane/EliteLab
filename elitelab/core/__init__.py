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

from . import config
from .bus import EventBus
from .http import HttpServer, Router
from .loader import load_all
from .services import Services
from .store import Store
from .watcher import JournalWatcher, journal_files

log = logging.getLogger("elitelab.core")


class Core:
    def __init__(self):
        self.config = config
        self.log = log
        self.bus = EventBus()
        self.store = Store(self.bus)
        self.services = Services()
        self.http = Router()
        self.modules = {}
        self.watcher = JournalWatcher(self.bus)
        self._server = HttpServer(self)
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
        self.http.route("/api/health", lambda q: {"ok": True, "version": __version__, "journal_dir": config.JOURNAL_DIR,
                                                  "journal_found": bool(journal_files()), "modules": list(self.modules)},
                        tool="health", description="Server health, version, journal folder and loaded modules.")
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
    def start(self, host=None, port=None, *, open_browser=False):
        from .. import __version__
        load_all(self)
        self.watcher.start()
        host, port = host or config.HOST, port or config.PORT
        print(f"EliteLab {__version__} listening on http://{host}:{port}")
        print(f"Journal dir: {config.JOURNAL_DIR}  (found: {bool(journal_files())})")
        print(f"Modules: {', '.join(self.modules) or 'none'}")
        print("Ctrl+C to stop.")
        try:
            self._server.serve(host, port, open_browser=open_browser)
        except KeyboardInterrupt:
            pass
        finally:
            self.watcher.stop()
