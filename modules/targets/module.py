"""targets module: Powerplay acquisition sell targets via Spansh.

Defaults are live: power = the pledged power, ref = the current system.
"""
from concurrent.futures import ThreadPoolExecutor

from elitelab.core.gamedata import POWERS
from elitelab.core.services import STARPORT_TYPES
from modules.targets.planner import Targets
from modules.targets.pricing import label, number

NS = "targets"


def setup(core, module):
    svc = core.services
    core.store.set(NS, "last", None)

    def defaults(q):
        power = q.get("power") or core.store.get("targets", "pledge")
        ref = q.get("ref", core.store.get("journal", "system"))
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 160:
            raise ValueError("Enter a reference system (up to 160 characters).")
        return power, ref.strip()

    planner = Targets(core)
    find = planner.find

    def compare(q):
        _, ref = defaults(q)

        def one(p):
            try:
                d = svc.spansh_stations({"system_power": {"value": [p]}, "system_power_state": {"value": ["Unoccupied"]},
                                         "has_market": {"value": True}, "has_large_pad": {"value": True},
                                         "type": {"value": STARPORT_TYPES}}, ref, size=3, ttl=1800)
                rows = d.get("results")
                return {"power": p, "count": number(d.get("count")),
                        "nearest": [{"system": label(r.get("system_name")), "dist": number(r.get("distance"))}
                                    for r in (rows[:3] if isinstance(rows, list) else []) if isinstance(r, dict)]}
            except Exception:
                return {"power": p, "error": "Community power comparison unavailable."}

        with ThreadPoolExecutor(max_workers=6) as pool:       # 12 Spansh calls in parallel instead of ~20 s in series
            out = list(pool.map(one, POWERS))
        return {"ref": ref, "powers": out}

    core.http.route("/api/targets", find, tool="find_sell_targets", module=module.name,
                    description="Compare up to 100 reported acquisition orbital markets for rare goods currently aboard. "
                                "Ranks conditional estimated merits per lower-bound laden jump, total merits or distance. "
                                "Missing pledge/location are errors. No merit rate is assumed: explicitly choose mahon_observed "
                                "(667 Cr/merit, October 2026 Mahon bonus observation only) or custom credits_per_merit. "
                                "Fresh legal quotes with demand covering each rare supply sale estimates; incomplete cargo totals stay null. "
                                "Optional interpolate uses a per-rare observed distance-price curve only between known points, never extrapolates "
                                "or invents market acceptance. Curves use each rare's source, not ref. Unknown origin/provenance remains visible. "
                                "Known carrier-exposed/stolen/same-origin goods block merits. All forecasts are conditional, never recorded gains. "
                                "Results and curves publish to targets.last for the dashboard; cargo/ship/pledge changes during I/O reject stale results.",
                    params={"power": {"type":"string", "description":"Power; defaults to current session's observed pledge", "enum":POWERS},
                            "ref": {"type":"string", "description":"Search/travel origin; defaults to current system, not rare purchase origin"},
                            "min": {"type":"number", "default":125, "description":"Minimum travel distance, 0-500 Ly"},
                            "max": {"type":"number", "default":200, "description":"Maximum travel distance, up to 500 Ly"},
                            "pad": {"type":"string", "enum":["L","M"], "default":"L"},
                            "limit": {"type":"integer", "default":40, "description":"Results shown, 1-100; ranking evaluates up to 100 stations"},
                            "hours": {"type":"number", "default":24, "description":"Maximum usable quote age, up to 168 hours"},
                            "sort": {"type":"string", "default":"merits_per_jump", "enum":["merits_per_jump","merits","distance"]},
                            "rate_mode": {"type":"string", "default":"unknown", "enum":["unknown","mahon_observed","custom"]},
                            "credits_per_merit": {"type":"number", "description":"Required for custom rate; positive Cr per merit, up to 1e9"},
                            "interpolate": {"type":"boolean", "default":False, "description":"Opt in to linear price interpolation between fresh quotes for listed legal goods with adequate demand"}})
    core.http.route("/api/powers", compare, tool="compare_powers", module=module.name,
                    description="For every Powerplay power: how many large-pad acquisition starports exist and the three nearest "
                                "to the reference system. Use it to choose a power to pledge to. Slow on first call (~20 s).",
                    params={"ref": {"type": "string", "description": "Reference system; default = current system"}})
    core.http.route("/api/system", lambda q: svc.spansh_system(q.get("name") or core.store.get("journal", "system")),
                    tool="get_system_info", module=module.name,
                    description="Spansh summary of a system: controlling power, Powerplay state, powers present, population, allegiance, coordinates.",
                    params={"name": {"type": "string", "description": "System name; default = current system"}})
