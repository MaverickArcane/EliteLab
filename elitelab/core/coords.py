"""EDSM system coordinates for a set of system names, shared by the modules that need them (loop, farming).

Fetched in a daemon thread (never on the watcher thread) with exponential back-off while EDSM is unreachable,
optionally cached on disk, and names EDSM does not know are remembered as None so nobody asks forever.
"""
import threading


class CoordCache:
    def __init__(self, core, label, cache_file=None, on_update=None):
        self.core = core
        self.label = label
        self.cache_file = cache_file
        self.on_update = on_update
        self.coords = (core.read_data(cache_file, default={}) or {}) if cache_file else {}
        self._wanted = set()
        self._lock = threading.Lock()
        self._retry = None
        self._fetching = False
        self._retry_delay = 5

    def get(self, name):
        """{x, y, z} or None (unknown, or not fetched yet)."""
        return self.coords.get(name)

    @property
    def ready(self):
        return any(v for v in self.coords.values())

    def request(self, names=()):
        """Ask for ``names`` (plus anything still pending). Returns at once; ``on_update()`` runs when results land."""
        with self._lock:
            self._wanted |= {n for n in names if n}
            if self.core.config.OFFLINE or self._fetching or not (self._wanted - self.coords.keys()):
                return
            if self._retry:
                self._retry.cancel()
                self._retry = None
            self._fetching = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        with self._lock:
            names = self._wanted - self.coords.keys()
        found, answered = {}, False
        try:
            found = self.core.services.edsm_coords(sorted(names))
            answered = True
        except Exception as ex:
            self.core.log.warning("%s: coords fetch failed: %s", self.label, ex)
        with self._lock:
            self.coords.update(found)
            if answered:
                for n in names - found.keys():
                    self.coords[n] = None
                    self.core.log.warning("%s: EDSM has no coordinates for %s", self.label, n)
                if self.cache_file:
                    self.core.write_data(self.coords, self.cache_file)
            self._fetching = False
            if self._wanted - self.coords.keys():
                self._retry = threading.Timer(self._retry_delay, self.request)
                self._retry.daemon = True
                self._retry.start()
                self._retry_delay = min(300, self._retry_delay * 2)
            else:
                self._retry_delay = 5
        if self.on_update:
            try:
                self.on_update()
            except Exception as ex:
                self.core.log.warning("%s: on_update failed: %s", self.label, ex)
