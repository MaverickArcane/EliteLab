"""farming module: known material farm sites, nearest first, matched to the wishlist shortfalls.

sites.json is the table (system, body, surface coordinates, materials, method). System coordinates come from EDSM
once and are cached in data/farm_coords.json; distances are from ``journal.star_pos``. Sites with no system are
methods (High Grade Emissions by state, wake scans...) and always sort last.

State ``farming``: sites [...], coords_ready.
"""
import json
import math
import os

from elitelab.core import gamedata as gd
from elitelab.core.coords import CoordCache

NS = "farming"
HERE = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = ["Raw", "Manufactured", "Encoded", "Guardian"]


class Farming:
    def __init__(self, core):
        self.core = core
        with open(os.path.join(HERE, "sites.json"), "r", encoding="utf-8") as f:
            self.sites = json.load(f)["sites"]
        self.coords = CoordCache(core, "farming", cache_file="farm_coords.json", on_update=self.publish)
        core.bus.on("state.journal.star_pos", lambda n, v: self.publish())
        core.bus.on("state.wishlist.needs", lambda n, v: self.publish())
        core.bus.on("journal.replay.done", lambda n, v: self.publish())
        self.coords.request({s["system"] for s in self.sites if s.get("system")})
        self.publish()

    # -- rows ---------------------------------------------------------------------
    def rows(self, material=None, category=None, type_=None, max_dist=None, for_wishlist=False):
        pos = self.core.store.get("journal", "star_pos")
        jr = self.core.store.get("journal", "jump_range_now") or self.core.store.get("journal", "jump_range")
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
            self.core.store.update(NS, {"sites": self.rows(), "coords_ready": self.coords.ready})
        except Exception as ex:                      # a bad store read must never kill the watcher thread
            self.core.log.warning("farming: publish failed: %s", ex)


STATES = ["Boom", "Civil Unrest", "War", "Civil War", "Outbreak", "Expansion", "Election", "Investment", "None"]
ALLEGIANCES = ["Empire", "Federation", "Alliance", "Independent"]


def setup(core, module):
    f = Farming(core)

    def systems(q):
        """Nearest populated systems whose controlling faction state / allegiance match: where High Grade Emissions for a
        given material spawn. Spansh data, so a few hours old; confirm the state on the galaxy map before relogging."""
        site = next((s for s in f.sites if s["id"] == q.get("site")), None) if q.get("site") else None
        query = dict((site or {}).get("spansh") or {})
        if q.get("state"):
            query["state"] = [s.strip() for s in str(q["state"]).split(",") if s.strip()]
        if q.get("allegiance"):
            query["allegiance"] = [str(q["allegiance"]).strip()]
        if not query:
            raise ValueError("give a site id (an HGE entry from find_farm_sites), a state, or an allegiance")
        bad = [s for s in query.get("state", []) if s not in STATES]
        if bad:
            raise ValueError(f"unknown state {bad}; use {STATES}")
        ref = q.get("ref") or core.store.get("journal", "system") or "Sol"
        limit = max(1, min(int(q.get("limit", 8) or 8), 30))
        min_pop = int(q.get("min_pop", 1000000) or 0)
        filters = {"population": {"comparison": "<=>", "value": [min_pop, 100000000000]}}
        if query.get("state"):
            filters["controlling_minor_faction_state"] = {"value": query["state"]}
        if query.get("allegiance"):
            filters["allegiance"] = {"value": query["allegiance"]}
        jr = core.store.get("journal", "jump_range_now") or core.store.get("journal", "jump_range")
        d = core.services.spansh_systems(filters, ref, size=limit, ttl=1800)
        rows = [{"system": s.get("name"), "dist": round(s.get("distance", 0), 1), "jumps": (math.ceil(s.get("distance", 0) / jr) if jr else None),
                 "population": s.get("population"), "state": s.get("controlling_minor_faction_state"), "allegiance": s.get("allegiance"),
                 "government": s.get("government"), "economy": s.get("primary_economy"), "updated": s.get("updated_at"),
                 "x": s.get("x"), "y": s.get("y"), "z": s.get("z")} for s in d.get("results", [])]
        return {"site": (site or {}).get("id"), "materials": [gd.material_name(k) for k in (site or {}).get("materials", [])], "query": query,
                "ref": ref, "count": d.get("count"), "systems": rows,
                "note": "Controlling-faction state and allegiance from Spansh (hours old). HGE spawn in populated systems; bigger "
                        "populations spawn more signals. Check the state on the galaxy map before you relog-farm."}

    core.http.route("/api/farming/systems", systems, tool="find_hge_systems", module=module.name,
                    description="Nearest populated systems where High Grade Emissions for a material would spawn: pass the HGE site id "
                                "from find_farm_sites (hge-boom, hge-war, hge-empire...) or a state/allegiance directly. Returns systems "
                                "with distance, jumps, population, controlling faction state and allegiance (Spansh data).",
                    params={"site": {"type": "string", "description": "HGE site id from find_farm_sites, e.g. hge-boom"},
                            "state": {"type": "string", "description": "Controlling faction state(s), comma-separated", "enum": STATES},
                            "allegiance": {"type": "string", "description": "Superpower allegiance", "enum": ALLEGIANCES},
                            "ref": {"type": "string", "description": "Reference system; default = current system"},
                            "min_pop": {"type": "integer", "description": "Minimum population", "default": 1000000},
                            "limit": {"type": "integer", "description": "Max systems (<=30)", "default": 8}})

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
