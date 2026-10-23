"""combat module: find systems where combat pays merits for the pledged power.

Powerplay 2.0 rules this encodes (community-documented, see docs/AI.md sources):
- Acquisition systems (Unoccupied, your power contesting): bounty hunting pays merits on the kill, +5% since the April 2025 patch.
- Contested acquisition systems (two or more powers with conflict progress): Powerplay combat zones spawn here. Merits on kill.
- Undermining (systems controlled by a rival): killing ships aligned to the controlling power pays merits ("power kills").
- Reinforcement (systems your power controls): bounty hunting pays merits with a 35% penalty.
"""
import math

NS = "combat"
KINDS = ["contested", "acquisition", "undermining", "reinforcement"]
# A system is "contested" (and spawns Powerplay combat zones) only once two or more powers have each passed the
# conflict threshold: ~35,000 of the 120,000 control points needed to acquire, i.e. ~29% progress.
CONFLICT_THRESHOLD = 0.29
HINTS = {
    "contested": "Powerplay combat zones spawn only where your power AND a rival have both passed ~29% acquisition progress. Merits per kill, paid on the kill. Find the zone in the nav panel (Points of Interest filter) or via the nav beacon; they can be slow to populate.",
    "acquisition": "Bounty hunting here pays merits on each kill (+5%). Pick a system with a ringed planet (Res sites) or sit at the nav beacon.",
    "undermining": "Kill ships pledged to the controlling power (they show the power's name in the target panel). Pirates here do not count.",
    "reinforcement": "Your own systems: bounty hunting pays merits but with a 35% penalty. Only worth it if it is where you already are.",
}


def setup(core, module):
    svc = core.services
    core.store.set(NS, "last", None)

    def find(q):
        power = q.get("power") or core.store.get("powerplay", "power") or "Edmund Mahon"
        ref = q.get("ref") or core.store.get("journal", "system") or "Leesti"
        kind = (q.get("kind") or "contested").lower()
        if kind not in KINDS + ["all"]:
            raise ValueError(f"kind must be one of {KINDS + ['all']}")
        radius = float(q.get("max") or 60)
        limit = min(int(q.get("limit") or 25), 100)
        jr = core.store.get("journal", "jump_range")
        kinds = KINDS if kind == "all" else [kind]
        rows = []
        for k in kinds:
            filters = {"distance": {"min": "0", "max": str(radius)}}
            if k in ("contested", "acquisition"):
                filters["power_state"] = {"value": ["Unoccupied"]}
                filters["power"] = {"value": [power]}
            elif k == "undermining":
                filters["power_state"] = {"value": ["Exploited", "Fortified", "Stronghold"]}
            else:
                filters["controlling_power"] = {"value": [power]}
            # Contested systems are rare, so page through everything in range (up to 2,500 systems); other kinds take the nearest 100.
            results = []
            for page in range(25 if k == "contested" else 1):
                body = {"filters": filters, "sort": [{"distance": {"direction": "asc"}}], "size": 100, "page": page, "reference_system": ref}
                data = svc.fetch_json("https://spansh.co.uk/api/systems/search", body, ttl=1800)
                chunk = data.get("results", [])
                results.extend(chunk)
                if len(chunk) < 100:
                    break
            for s in results:
                conf = s.get("power_conflict_progress") or []
                mine = next((c.get("progress", 0) for c in conf if c.get("power") == power), None)
                rivals = [c for c in conf if c.get("power") != power and (c.get("progress") or 0) > 0]
                hot_rivals = [c for c in rivals if (c.get("progress") or 0) >= CONFLICT_THRESHOLD]
                zone_likely = bool(mine is not None and mine >= CONFLICT_THRESHOLD and hot_rivals)
                if k == "contested" and not zone_likely:
                    continue
                if k == "undermining" and s.get("controlling_power") in (None, power):
                    continue
                if not s.get("population"):
                    continue
                rows.append({
                    "kind": k, "system": s.get("name"), "dist": round(s.get("distance", 0), 1),
                    "jumps": (math.ceil(s.get("distance", 0) / jr) if jr else None),
                    "state": s.get("power_state"), "controlling_power": s.get("controlling_power"),
                    "security": s.get("security"), "population": s.get("population"), "allegiance": s.get("allegiance"),
                    "my_progress": round(mine, 3) if mine is not None else None, "zone_likely": zone_likely,
                    "conflict": [{"power": c.get("power"), "progress": round(c.get("progress") or 0, 3)} for c in conf],
                    "x": s.get("x"), "y": s.get("y"), "z": s.get("z"),
                })
        # contested first by how live the fight is (both sides have progress), then distance
        def score(r):
            live = 0
            if r["kind"] == "contested":
                top = max((c["progress"] for c in r["conflict"]), default=0)
                live = -(top if top < 1 else 0)
            return (KINDS.index(r["kind"]), live, r["dist"])
        rows.sort(key=score)
        out = {"power": power, "ref": ref, "kind": kind, "radius": radius, "jump_range": jr, "results": rows[:limit],
               "hints": {k: HINTS[k] for k in kinds}, "conflict_threshold": CONFLICT_THRESHOLD,
               "note": "zone_likely = your power and at least one rival are both past the conflict threshold; only then do Powerplay combat zones exist in the system"}
        core.store.set(NS, "last", out)
        return out

    core.http.route("/api/combat", find, tool="find_combat_systems", module=module.name,
                    description="Systems near the reference where combat earns Powerplay merits for the pledged power. kind=contested: "
                                "acquisition systems where your power AND a rival have both passed the ~29% conflict threshold, which is the "
                                "only place Powerplay combat zones spawn (zone_likely=true); acquisition: bounty "
                                "hunting pays +5%; undermining: rival-controlled systems where killing the controlling power's ships pays; "
                                "reinforcement: your own systems (-35%). Includes security, population, conflict progress per power, distance and jumps.",
                    params={"kind": {"type": "string", "description": "contested (default), acquisition, undermining, reinforcement or all", "enum": KINDS + ["all"], "default": "contested"},
                            "ref": {"type": "string", "description": "Reference system; default = current system"},
                            "power": {"type": "string", "description": "Power; default = pledged power"},
                            "max": {"type": "number", "description": "Search radius in Ly", "default": 60},
                            "limit": {"type": "integer", "description": "Max results (<=100)", "default": 25}})
