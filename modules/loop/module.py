"""loop module: rare goods loops, computed server-side from the hold and position.

State ``loop``: id, name, note, origin, stations[{system, station, type, ls,
rares, keys, tons, in_hold, dist, docked_here, done, coords}], done_count,
tons_total, next, available.
"""
import json
import math
import os
import threading

from elitelab.core.coords import CoordCache
from modules.loop.evidence import workflow, xyz, timestamp, label

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
        self._lock = threading.Lock()
        self.arrived = None
        self.cargo_since = None
        self.commander = None
        self.coords = CoordCache(core, "loop", on_update=self.recompute)      # EDSM lookups off the watcher thread
        core.bus.on("state.journal.location", lambda n, v: self.recompute())
        core.bus.on("journal.replay.done", lambda n, v: self.recompute())
        core.bus.on("state.journal.market", lambda n, v: self.recompute())
        core.bus.on("state.journal.cargo_capacity", lambda n, v: self.recompute())
        core.bus.on("journal.*", self.event)
        self._request_coords()
        self.recompute()

    def _request_coords(self):
        self.coords.request({s["system"] for lp in self.loops.values() for s in lp["stations"]})

    def select(self, loop_id):
        if not isinstance(loop_id, str) or loop_id not in self.loops:
            raise ValueError("Choose one of the available rare loops.")
        with self._lock:
            self.core.write_data({"selected": loop_id}, "loop.json")
            self.selected = loop_id
        self.recompute()
        self._request_coords()
        return self.core.store.get(NS)

    def event(self, name, event):
        if not isinstance(event, dict):
            return
        kind = event.get("event")
        if kind in ("LoadGame", "Commander"):
            commander = label(event.get("FID")) or label(event.get("Commander") or event.get("Name"))
            if kind == "Commander" and commander == self.commander:
                return  # Journal file continuation is not a new game session.
            self.commander = commander
            observed = timestamp(event.get("timestamp"))
            self.cargo_since = observed if observed is not None else math.inf
        if kind in ("LoadGame", "Commander", "Undocked", "FSDJump", "CarrierJump", "Died") or (kind == "Location" and not event.get("Docked")):
            self.arrived = None
        elif kind == "Docked" or (kind == "Location" and event.get("Docked")):
            self.arrived = timestamp(event.get("timestamp"))
        else:
            return
        self.recompute()

    def recompute(self):
        with self._lock:
            j = self.core.store.get("journal") or {}
            evidence = workflow(j, self.arrived, self.cargo_since)
            items = (j.get("cargo") or {}).get("items") or []
            items = items[:256] if isinstance(items, list) and evidence["cargo_known"] else []
            ship = j.get("star_pos")
            lp = self.loops[self.selected]
            stations = []
            for s in lp["stations"]:
                keys = {r["key"].lower() for r in s["rares"]}
                names = {r["name"].lower() for r in s["rares"]}
                tons = sum(i["count"] for i in items if label(i.get("key")).lower() in keys or label(i.get("name")).lower() in names) if evidence["cargo_known"] else None
                c = self.coords.get(s["system"])
                c = {k:c[k] for k in "xyz"} if isinstance(c, dict) and xyz([c.get(k) for k in "xyz"]) else None
                dist = round(math.dist(ship, [c["x"], c["y"], c["z"]]), 1) if xyz(ship) and c else None
                stations.append({**s, "keys": sorted(keys), "tons": tons, "in_hold": bool(tons), "dist": dist,
                                 "docked_here": bool(j.get("docked") and label(j.get("system")).casefold() == s["system"].casefold() and label(j.get("station")).casefold() == s["station"].casefold()), "done": bool(tons),
                                 "coords": c})
            stations.sort(key=lambda s: (s["done"], s["dist"] if s["dist"] is not None else math.inf))
            nxt = next((s for s in stations if not s["done"]), None)
            self.core.store.update(NS, {
                "id": self.selected, "name": lp["name"], "note": lp.get("note"), "origin": lp.get("origin"), "stations": stations,
                "done_count": sum(1 for s in stations if s["done"]), "tons_total": sum(s["tons"] for s in stations) if evidence["cargo_known"] else None,
                "workflow": evidence,
                "next": {"system": nxt["system"], "station": nxt["station"], "dist": nxt["dist"]} if nxt else None,
                "complete": all(s["done"] for s in stations),
                "available": [{"id": k, "name": v["name"], "origin": v.get("origin")} for k, v in self.loops.items()],
            })


def setup(core, module):
    lp = Loop(core)
    core.http.route("/api/loop", lambda q: core.store.get(NS), tool="get_rares_loop", module=module.name,
                    description="The active rare goods loop: each station with its rares, tons already in the hold, distance from "
                                "the ship, exact station arrival, and the recommended next buy stop. Cargo presence marks a stop, not a verified purchase. "
                                "Unknown cargo yields null tons. workflow adds cargo_known/free_capacity and market snapshot status/source/time/rare stock. "
                                "A current_snapshot was recorded during this station visit; previous_station/previous_visit/undated/not_recorded are not current stock. "
                                "Manual visit marks and map selection stay browser-local. Selling and Powerplay eligibility require separate checks.")
    core.http.route("/api/loop/select", lambda q: lp.select(q.get("id")), tool="select_rares_loop", method="POST", module=module.name,
                    description="Switch the active rare goods loop.",
                    params={"id": {"type": "string", "description": "Loop id, see get_rares_loop.available", "required": True}})
