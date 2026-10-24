"""Shared services modules can use: a cached JSON fetcher and thin helpers for
the community APIs (Spansh, EDSM). Keeping these here means every module
shares one cache and one User-Agent, and no module hammers a volunteer API.
"""
import json
import threading
import time
import urllib.parse
import urllib.request

from . import config

SPANSH_STATIONS = "https://spansh.co.uk/api/stations/search"
SPANSH_SYSTEMS = "https://spansh.co.uk/api/systems/search"
EDSM_SYSTEMS = "https://www.edsm.net/api-v1/systems"

from .gamedata import POWERS  # noqa: F401  (re-exported for modules that import it from here)

STARPORT_TYPES = ["Coriolis Starport", "Orbis Starport", "Ocellus Starport", "Asteroid base", "Planetary Port"]
MEDIUM_TYPES = STARPORT_TYPES + ["Outpost", "Planetary Outpost"]
CACHE_MAX_ENTRIES = 400


class Services:
    def __init__(self):
        self._cache = {}        # key -> (stored_at, ttl, data)
        self._lock = threading.Lock()

    # -- generic -----------------------------------------------------------
    def fetch_json(self, url, body=None, ttl=None, method=None):
        """GET (or POST when ``body`` is given) and parse JSON, cached for ``ttl`` seconds."""
        if config.OFFLINE:
            raise RuntimeError("ELITELAB_OFFLINE is set; refusing network call to " + url)
        ttl = config.CACHE_TTL if ttl is None else ttl
        key = (url, json.dumps(body, sort_keys=True) if body is not None else None)
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < ttl:
                return hit[2]
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"User-Agent": config.USER_AGENT}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method or ("POST" if data else "GET"))
        with urllib.request.urlopen(req, timeout=40) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        with self._lock:
            self._cache[key] = (now, ttl, out)
            self._evict(now)
        return out

    def _evict(self, now):
        """Drop expired entries; if still over the cap, drop the oldest. Called under the lock."""
        for k in [k for k, (t, ttl, _) in self._cache.items() if now - t >= ttl]:
            del self._cache[k]
        if len(self._cache) > CACHE_MAX_ENTRIES:
            for k in sorted(self._cache, key=lambda k: self._cache[k][0])[: len(self._cache) - CACHE_MAX_ENTRIES]:
                del self._cache[k]

    # -- spansh ------------------------------------------------------------
    @staticmethod
    def pad(station):
        if station.get("has_large_pad"):
            return "L"
        return "M" if (station.get("medium_pads") or 0) > 0 else "S"

    def spansh_stations(self, filters, ref, size=40, sort="distance", ttl=None):
        body = {"filters": filters, "sort": [{sort: {"direction": "asc"}}], "size": size, "page": 0, "reference_system": ref}
        return self.fetch_json(SPANSH_STATIONS, body, ttl=ttl)

    def spansh_systems(self, filters, ref, size=10, sort="distance", ttl=None):
        """Spansh system search (filters such as allegiance, population, controlling_minor_faction_state), nearest ``ref`` first."""
        body = {"filters": filters, "sort": [{sort: {"direction": "asc"}}], "size": size, "page": 0, "reference_system": ref}
        return self.fetch_json(SPANSH_SYSTEMS, body, ttl=ttl)

    def spansh_system(self, name):
        d = self.fetch_json(SPANSH_SYSTEMS, {"filters": {"name": {"value": name}}, "size": 1, "page": 0})
        r = (d.get("results") or [None])[0]
        if not r:
            return {}
        return {"name": r.get("name"), "power_state": r.get("power_state"), "controlling_power": r.get("controlling_power"),
                "powers": r.get("power"), "population": r.get("population"), "allegiance": r.get("allegiance"),
                "x": r.get("x"), "y": r.get("y"), "z": r.get("z")}

    # -- edsm --------------------------------------------------------------
    def edsm_coords(self, names):
        """Batch coordinates. Returns {name: {x,y,z}} for systems EDSM knows."""
        names = [n for n in dict.fromkeys((n or "").strip() for n in names) if n]
        if not names:
            return {}
        qs = "&".join("systemName[]=" + urllib.parse.quote(n) for n in names) + "&showCoordinates=1"
        data = self.fetch_json(EDSM_SYSTEMS + "?" + qs, ttl=86400)
        out = {}
        for s in data or []:
            c = s.get("coords") or {}
            if "x" in c:
                out[s.get("name")] = {"x": c["x"], "y": c["y"], "z": c["z"]}
        return out
