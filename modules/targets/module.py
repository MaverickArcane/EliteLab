"""targets module: Powerplay acquisition sell targets via Spansh.

Defaults are live: power = the pledged power, ref = the current system.
"""
import math

from elitelab.core.services import MEDIUM_TYPES, POWERS, STARPORT_TYPES

NS = "targets"


def setup(core, module):
    svc = core.services
    core.store.set(NS, "last", None)

    def defaults(q):
        power = q.get("power") or core.store.get("powerplay", "power") or "Edmund Mahon"
        ref = q.get("ref") or core.store.get("journal", "system") or "Leesti"
        return power, ref

    def find(q):
        power, ref = defaults(q)
        pad = (q.get("pad") or "L").upper()
        dmin, dmax = q.get("min"), q.get("max")
        filters = {"system_power": {"value": [power]}, "system_power_state": {"value": ["Unoccupied"]},
                   "has_market": {"value": True}, "type": {"value": STARPORT_TYPES if pad == "L" else MEDIUM_TYPES}}
        if pad == "L":
            filters["has_large_pad"] = {"value": True}
        if dmin or dmax:
            filters["distance"] = {"min": str(dmin or 0), "max": str(dmax or 500)}
        data = svc.spansh_stations(filters, ref, size=min(int(q.get("limit", 40) or 40), 100))
        jr = core.store.get("journal", "jump_range")
        results = [{
            "system": s.get("system_name"), "station": s.get("name"), "dist": round(s.get("distance", 0), 1),
            "jumps": (math.ceil(s.get("distance", 0) / jr) if jr else None),
            "ls": round(s.get("distance_to_arrival") or 0), "type": s.get("type"), "pad": svc.pad(s),
            "pop": s.get("system_population"), "updated": s.get("market_updated_at"),
            "x": s.get("system_x"), "y": s.get("system_y"), "z": s.get("system_z"), "economy": s.get("system_primary_economy"),
        } for s in data.get("results", [])]
        out = {"count": data.get("count"), "results": results, "ref": ref, "power": power, "min": dmin, "max": dmax, "pad": pad,
               "jump_range": jr, "jumps_note": "jumps = ceil(distance / max unladen jump range); a laden ship needs more"}
        core.store.set(NS, "last", out)
        return out

    def compare(q):
        _, ref = defaults(q)
        out = []
        for p in POWERS:
            try:
                d = svc.spansh_stations({"system_power": {"value": [p]}, "system_power_state": {"value": ["Unoccupied"]},
                                         "has_market": {"value": True}, "has_large_pad": {"value": True},
                                         "type": {"value": STARPORT_TYPES}}, ref, size=3, ttl=1800)
                out.append({"power": p, "count": d.get("count"),
                            "nearest": [{"system": r.get("system_name"), "dist": round(r.get("distance", 0))} for r in d.get("results", [])]})
            except Exception as ex:
                out.append({"power": p, "error": str(ex)})
        return {"ref": ref, "powers": out}

    core.http.route("/api/targets", find, tool="find_sell_targets", module=module.name,
                    description="Stations with a market in Unoccupied systems that a power can acquire (where Powerplay trade "
                                "and rare goods sales earn merits), nearest the reference system first. Rare goods pay best "
                                "125-165 Ly from where they were bought. Includes market data age so stale stations can be avoided.",
                    params={"power": {"type": "string", "description": "Power name; default = the pledged power", "enum": POWERS},
                            "ref": {"type": "string", "description": "Reference system; default = current system"},
                            "min": {"type": "number", "description": "Minimum distance in Ly"},
                            "max": {"type": "number", "description": "Maximum distance in Ly"},
                            "pad": {"type": "string", "description": "L = large starports only (default), M = include outposts", "enum": ["L", "M"], "default": "L"},
                            "limit": {"type": "integer", "description": "Max results (<=100)", "default": 40}})
    core.http.route("/api/powers", compare, tool="compare_powers", module=module.name,
                    description="For every Powerplay power: how many large-pad acquisition starports exist and the three nearest "
                                "to the reference system. Use it to choose a power to pledge to. Slow on first call (~20 s).",
                    params={"ref": {"type": "string", "description": "Reference system; default = current system"}})
    core.http.route("/api/system", lambda q: svc.spansh_system(q.get("name") or core.store.get("journal", "system")),
                    tool="get_system_info", module=module.name,
                    description="Spansh summary of a system: controlling power, Powerplay state, powers present, population, allegiance, coordinates.",
                    params={"name": {"type": "string", "description": "System name; default = current system"}})
