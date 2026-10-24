"""farming module: known material farm sites, nearest first, matched to the wishlist shortfalls.

sites.json is the table (system, body, surface coordinates, materials, method). System coordinates come from EDSM
once and are cached in data/farm_coords.json; distances are from ``journal.star_pos``. Sites with no system are
methods (High Grade Emissions by state, wake scans...) and always sort last.

State ``farming``: sites [...], coords_ready.
"""
import json
import math
import os
import threading

from elitelab.core import gamedata as gd

NS = "farming"
HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ["Raw", "Manufactured", "Encoded", "Guardian"]


class Farming:
    def __init__(self, core):
        self.core = core
        with open(os.path.join(HERE, "sites.json"), "r", encoding="utf-8") as f:
            self.sites = json.load(f)["sites"]
        self.coords = core.read_data("farm_coords.json", default={}) or {}
        self._lock = threading.Lock()
        self._retry = None
        self._fetching = False
        self._retry_delay = 5
        core.bus.on("state.journal.star_pos", lambda n, v: self.publish())
        core.bus.on("state.wishlist.needs", lambda n, v: self.publish())
        core.bus.on("journal.replay.done", lambda n, v: self.publish())
        self._request_coords()
        self.publish()

    # -- coordinates (same pattern as the loop module: never on the watcher thread) ------
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
            names = {s["system"] for s in self.sites if s.get("system")} - self.coords.keys()
        found = {}
        try:
            if names:
                found = self.core.services.edsm_coords(sorted(names))
        except Exception as ex:
            self.core.log.warning("farming: coords fetch failed: %s", ex)
        with self._lock:
            if found:
                # EDSM answered: names it left out are unknown to it; remember that (None) so we do not ask forever
                self.coords.update(found)
                for n in names - found.keys():
                    self.coords[n] = None
                    self.core.log.warning("farming: EDSM has no coordinates for %s", n)
                self.core.write_data(self.coords, "farm_coords.json")
            self._fetching = False
            if names - self.coords.keys():
                self._retry = threading.Timer(self._retry_delay, self._request_coords)
                self._retry.daemon = True
                self._retry.start()
                self._retry_delay = min(300, self._retry_delay * 2)
            else:
                self._retry_delay = 5
        self.publish()

    # -- rows ---------------------------------------------------------------------
    def rows(self, material=None, category=None, type_=None, max_dist=None, for_wishlist=False):
        pos = self.core.store.get("journal", "star_pos")
        jr = self.core.store.get("journal", "jump_range")
        short = {r["key"] for r in (self.core.store.get("wishlist", "needs") or []) if r.get("short")}
        want = None
        if material:
            want = gd.resolve_material(material)
            if not want:
                raise ValueError(f"unknown material '{material}'")
        out = []
        for s in self.sites:
            if want and want not in s["materials"]:
                continue
            if category and s["category"].lower() != category.lower():
                continue
            if type_ and type_.lower() not in s["type"].lower():
                continue
            c = self.coords.get(s["system"]) if s.get("system") else None
            dist = round(math.dist(pos, (c["x"], c["y"], c["z"])), 1) if (c and pos) else None
            if max_dist and (dist is None or dist > float(max_dist)):
                continue
            covers = [gd.material_name(k) for k in s["materials"] if k in short]
            if for_wishlist and not covers:
                continue
            out.append({**s, "material_names": [gd.material_name(k) for k in s["materials"]], "coords": c, "dist": dist,
                        "jumps": (math.ceil(dist / jr) if (dist and jr) else None), "covers": covers})
        out.sort(key=lambda r: (r["system"] is None, r["dist"] is None, r["dist"] or 0, r["name"]))
        return out

    def publish(self):
        try:
            self.core.store.update(NS, {"sites": self.rows(), "coords_ready": bool(self.coords)})
        except Exception as ex:                      # a bad store read must never kill the watcher thread
            self.core.log.warning("farming: publish failed: %s", ex)


def setup(core, module):
    f = Farming(core)

    def find(q):
        limit = max(1, min(int(q.get("limit", 30) or 30), 100))
        rows = f.rows(q.get("material") or None, q.get("category") or None, q.get("type") or None, q.get("max_dist") or None,
                      str(q.get("for_wishlist", "")).lower() in ("1", "true"))
        return {"count": len(rows), "ref": core.store.get("journal", "system"), "sites": rows[:limit],
                "note": "Sites are community-documented farm spots; entries without a system are methods. surface = [latitude, longitude]. "
                        "covers lists the wishlist shortfalls a site supplies."}

    core.http.route("/api/farming", find, tool="find_farm_sites", module=module.name,
                    description="Where to farm engineering materials: community-known sites (crystalline shards and brain trees for G4 raw, "
                                "Dav's Hope for manufactured, Jameson Crash Site for encoded, Guardian structures) and methods (High Grade "
                                "Emissions by system state, wake and ship scans), with system, body, surface coordinates and how-to, nearest "
                                "to the ship first. Filter by material to answer 'where do I get X'; for_wishlist=true returns only sites "
                                "that supply a current wishlist shortfall.",
                    params={"material": {"type": "string", "description": "Material name or key, e.g. 'tellurium' or 'Adaptive Encryptors Capture'"},
                            "category": {"type": "string", "description": "Raw, Manufactured, Encoded or Guardian", "enum": CATEGORIES},
                            "type": {"type": "string", "description": "Site type substring: crystal, brain, crash, settlement, guardian, emissions, wake, scan, prospecting"},
                            "max_dist": {"type": "number", "description": "Only sites within this many Ly (drops sites without a system)"},
                            "for_wishlist": {"type": "boolean", "description": "Only sites that supply a current engineering wishlist shortfall", "default": False},
                            "limit": {"type": "integer", "description": "Max sites (<=100)", "default": 30}})
