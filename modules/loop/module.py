"""loop module: rare goods loops, computed server-side from the hold and position.

State ``loop``: id, name, note, origin, stations[{system, station, type, ls,
rares, keys, tons, in_hold, dist, docked_here, done, coords}], done_count,
tons_total, next, available.
"""
import json
import math
import os
import threading

NS = "loop"
HERE = os.path.dirname(os.path.abspath(__file__))


class Loop:
    def __init__(self, core):
        self.core = core
        with open(os.path.join(HERE, "loops.json"), "r", encoding="utf-8") as f:
            self.loops = json.load(f)
        self.selected = (core.read_data("loop.json", default={}) or {}).get("selected")
        if self.selected not in self.loops:          # stale or missing selection must never stop the server
            self.selected = next(iter(self.loops))
        self.coords = {}
        self._lock = threading.Lock()
        self._retry = None
        self._fetching = False
        self._retry_delay = 5
        core.bus.on("state.journal.location", lambda n, v: self.recompute())
        core.bus.on("journal.replay.done", lambda n, v: self.recompute())
        self._request_coords()
        self.recompute()

    def _request_coords(self):
        if self.core.config.OFFLINE:
            return
        with self._lock:
            if self._fetching:
                return
            if self._retry:
                self._retry.cancel()
                self._retry = None
            self._fetching = True
        threading.Thread(target=self._fetch_coords, daemon=True).start()

    def _fetch_coords(self):
        with self._lock:
            names = {s["system"] for lp in self.loops.values() for s in lp["stations"]} - self.coords.keys()
        found = {}
        try:
            found = self.core.services.edsm_coords(sorted(names))
        except Exception as ex:
            self.core.log.warning("loop: coords fetch failed: %s", ex)
        with self._lock:
            self.coords.update(found)
            if found:                                   # EDSM answered; names it left out are unknown, do not ask forever
                for n in names - found.keys():
                    self.coords[n] = None
                    self.core.log.warning("loop: EDSM has no coordinates for %s", n)
            self._fetching = False
            if names - self.coords.keys():
                self._retry = threading.Timer(self._retry_delay, self._request_coords)
                self._retry.daemon = True
                self._retry.start()
                self._retry_delay = min(300, self._retry_delay * 2)
            else:
                self._retry_delay = 5
        self.recompute()

    def select(self, loop_id):
        if loop_id not in self.loops:
            raise ValueError(f"unknown loop '{loop_id}'; available: {list(self.loops)}")
        self.selected = loop_id
        self.core.write_data({"selected": loop_id}, "loop.json")
        self.recompute()
        self._request_coords()
        return self.core.store.get(NS)

    def recompute(self):
        with self._lock:
            j = {k: self.core.store.get("journal", k) for k in ("cargo", "system", "docked", "star_pos")}
            items = (j.get("cargo") or {}).get("items") or []
            ship = j.get("star_pos")
            lp = self.loops[self.selected]
            stations = []
            for s in lp["stations"]:
                keys = {r["key"].lower() for r in s["rares"]}
                names = {r["name"].lower() for r in s["rares"]}
                tons = sum((i.get("count") or 0) for i in items if (i.get("key") or "").lower() in keys or (i.get("name") or "").lower() in names)
                c = self.coords.get(s["system"])
                dist = round(math.dist(ship, [c["x"], c["y"], c["z"]]), 1) if (ship and c) else None
                stations.append({**s, "keys": sorted(keys), "tons": tons, "in_hold": tons > 0, "dist": dist,
                                 "docked_here": bool(j.get("docked") and j.get("system") == s["system"]), "done": tons > 0,
                                 "coords": c})
            stations.sort(key=lambda s: (s["done"], s["dist"] if s["dist"] is not None else 9999))
            nxt = next((s for s in stations if not s["done"]), None)
            self.core.store.update(NS, {
                "id": self.selected, "name": lp["name"], "note": lp.get("note"), "origin": lp.get("origin"), "stations": stations,
                "done_count": sum(1 for s in stations if s["done"]), "tons_total": sum(s["tons"] for s in stations),
                "next": {"system": nxt["system"], "station": nxt["station"], "dist": nxt["dist"]} if nxt else None,
                "complete": all(s["done"] for s in stations),
                "available": [{"id": k, "name": v["name"], "origin": v.get("origin")} for k, v in self.loops.items()],
            })


def setup(core, module):
    lp = Loop(core)
    core.http.route("/api/loop", lambda q: core.store.get(NS), tool="get_rares_loop", module=module.name,
                    description="The active rare goods loop: each station with its rares, tons already in the hold, distance from "
                                "the ship, whether docked there, and the recommended next stop. Stations tick done when their rare is aboard.")
    core.http.route("/api/loop/select", lambda q: lp.select(q.get("id")), tool="select_rares_loop", method="POST", module=module.name,
                    description="Switch the active rare goods loop.",
                    params={"id": {"type": "string", "description": "Loop id, see get_rares_loop.available", "required": True}})
