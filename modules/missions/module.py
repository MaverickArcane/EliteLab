"""Read-only mission logistics. Market lookups run only on explicit requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from elitelab.core.commodity_sources import Sourcing, integer
from elitelab.core.gamedata import norm


def count(value):
    return value if type(value) is int and value >= 0 else None


def mission_kind(name):
    tokens = str(name or "").casefold().split("_")
    for token, kind in (("salvage", "salvage"), ("delivery", "delivery"),
                        ("collect", "source_return"), ("mining", "mining"), ("courier", "courier")):
        if token in tokens:
            return kind
    return "other"


def build_plan(state, now=None):
    now = now or datetime.now(timezone.utc)
    p, j = state.get("progression", {}), state.get("journal", {})
    cargo = p.get("cargo") or {}
    inventory = cargo.get("items", [])
    cargo_at = cargo.get("observed_at")
    current_cargo = bool(cargo_at and cargo_at >= (p.get("cargo_changed_at") or ""))
    pool, tagged, clean_tagged = {}, {}, {}
    for item in inventory:
        key = norm(item.get("Name") or "")
        qty = count(item.get("Count")) or 0
        mid = item.get("MissionID")
        if mid is not None:
            tagged[(str(mid), key)] = tagged.get((str(mid), key), 0) + qty
            clean_tagged[(str(mid), key)] = clean_tagged.get((str(mid), key), 0) + max(0, qty - (count(item.get("Stolen")) or 0))
        else:
            pool[key] = pool.get(key, 0) + max(0, qty - (count(item.get("Stolen")) or 0))
    rows, shopping, returns = [], {}, {}
    missions = sorted(p.get("active_missions", []), key=lambda r: (r.get("expiry") or "9999", str(r["mission_id"])))
    for m in missions:
        kind = mission_kind(m.get("name"))
        commodity = norm(m.get("commodity") or "")
        depot = m.get("depot", {})
        total = count(depot.get("TotalItemsToDeliver"))
        total = count(m.get("count")) if total is None else total
        delivered = count(depot.get("ItemsDelivered"))
        remaining = max(0, total - (delivered or 0)) if total is not None else None
        try:
            expired = datetime.fromisoformat(m["expiry"].replace("Z", "+00:00")) <= now
        except (KeyError, TypeError, ValueError):
            expired = False
        ready = m.get("status") == "ready_to_turn_in"
        # A depot delivery after the inventory snapshot must not count cargo twice.
        usable = current_cargo and cargo_at >= depot.get("observed_at", "")
        assigned_cargo = clean_tagged if kind == "source_return" else tagged
        aboard = min(remaining, assigned_cargo.get((str(m["mission_id"]), commodity), 0)) if usable and remaining is not None else None
        if kind == "source_return" and aboard is not None and not expired and not ready:
            assigned = min(max(0, remaining - aboard), pool.get(commodity, 0))
            pool[commodity] = pool.get(commodity, 0) - assigned
            aboard += assigned
        short = max(0, remaining - aboard) if aboard is not None else None
        target = {"system": m.get("destination_system"), "station": m.get("destination_station")}
        origin = {"system": m.get("origin_system"), "station": m.get("origin_station")}
        hand_in = origin if kind == "salvage" else target
        if kind == "source_return" and not hand_in["system"]:
            hand_in = origin
        action = "Check the mission's instructions in Transactions."
        if expired:
            action = "Recorded deadline has passed; check Transactions for the current outcome."
        elif ready or remaining == 0:
            action = "Return to the mission contact and claim the reward."
        elif kind == "source_return":
            action = "Check current cargo before buying; inventory is missing or predates a depot update." if short is None else "Deliver the allocated cargo through the mission depot." if short == 0 else f"Buy {short} more, then return to the mission depot."
        elif kind == "delivery":
            action = "Collect the mission's assigned cargo from its origin depot, then deliver it. Market-bought replacements do not count."
            if short == 0:
                action = "Deliver the assigned cargo through the destination mission depot."
        elif kind == "salvage":
            action = "Visit the destination system, scan its Nav Beacon, then collect mission-tagged cargo at the mission signal source and return to the issuer."
            if short == 0:
                action = "Return the mission-tagged salvage to the issuing station."
        elif kind == "mining":
            action = "Check the mining requirement in Transactions; this planner does not assume market goods qualify."
        elif kind == "courier":
            action = "Visit the destination mission contact; no commodity purchase is needed."
        row = {**m, "kind": kind, "commodity_key": commodity, "required": total,
               "delivered": delivered, "remaining_to_deliver": remaining, "aboard_allocated": aboard,
               "shortfall": short, "origin": origin, "destination": target, "hand_in": hand_in,
               "expired": expired, "next_action": action, "cargo_observed_at": cargo_at}
        if kind == "delivery":
            collected = count(depot.get("ItemsCollected"))
            row["remaining_at_origin_depot"] = max(0, total - collected) if total is not None and collected is not None else None
        rows.append(row)
        if not expired and not ready and kind == "source_return" and commodity and short:
            item = shopping.setdefault(commodity, {"commodity_key": commodity,
                "commodity": m.get("commodity_name") or commodity, "quantity": 0, "mission_ids": []})
            item["quantity"] += short
            item["mission_ids"].append(m["mission_id"])
        if not expired and hand_in["system"]:
            stop = returns.setdefault((hand_in["system"], hand_in["station"]), {**hand_in, "mission_ids": []})
            stop["mission_ids"].append(m["mission_id"])
    used = sum(count(i.get("Count")) or 0 for i in inventory) if current_cargo else None
    capacity = count(j.get("cargo_capacity"))
    free = max(0, capacity - used) if capacity is not None and used is not None else None
    needed = sum(i["quantity"] for i in shopping.values())
    return {"commander": p.get("commander"), "reference": j.get("system"), "missions": rows,
            "shopping_list": list(shopping.values()), "delivery_stops": list(returns.values()),
            "cargo_observed_at": cargo_at, "cargo_used": used, "cargo_capacity": capacity, "free_space": free,
            "cargo_current": current_cargo,
            "shopping_tonnes": needed, "fits_current_hold": needed <= free if free is not None else None,
            "mission_board_available": False,
            "notes": ["Cargo is allocated once, by earliest deadline; allocation is a planning estimate, not a reservation.",
                      "Only source-and-return shortages are market searches. Mission-tagged cargo stays with its mission.",
                      "Delivered is unknown until a depot report; an unreported delivery can overstate the shortage.",
                      "Reward choices, local commodity legality and docking permission are not verified here."]}


class Missions:
    def __init__(self, core):
        self.core = core
        for topic in ("state.progression.*", "state.journal.system", "state.journal.cargo_capacity"):
            core.bus.on(topic, self.publish)
        self.publish()

    def publish(self, *args):
        self.core.store.set("missions", "plan", build_plan(self.state()))

    def state(self):
        return {"progression": self.core.store.get("progression"), "journal": self.core.store.get("journal")}

    def plan(self, q):
        result = build_plan(self.state())
        if q.get("mission_id"):
            wanted = str(q["mission_id"])
            result["missions"] = [r for r in result["missions"] if str(r["mission_id"]) == wanted]
            # Keep the shared allocation: filtering must not allocate cargo a second time.
            result["shopping_list"] = [{"commodity_key": r["commodity_key"], "commodity": r.get("commodity_name") or r["commodity_key"],
                "quantity": r["shortfall"], "mission_ids": [r["mission_id"]]} for r in result["missions"]
                if r["kind"] == "source_return" and r["shortfall"] and not r["expired"] and r["status"] != "ready_to_turn_in"]
            result["delivery_stops"] = [dict(s, mission_ids=[int(wanted)]) for s in result["delivery_stops"] if wanted in map(str, s["mission_ids"])]
            result["shopping_tonnes"] = sum(i["quantity"] for i in result["shopping_list"])
            result["fits_current_hold"] = result["shopping_tonnes"] <= result["free_space"] if result["free_space"] is not None else None
        return result

    def sources(self, q):
        options = {"max_distance_ly": integer(q, "max_distance_ly", 25, 1, 500),
                   "max_days": integer(q, "max_days", 2, 1, 30), "limit": integer(q, "limit", 3, 1, 10),
                   "pad": str(q.get("pad", "L")).upper(), "carriers": q.get("carriers", "exclude")}
        if options["pad"] not in ("S", "M", "L") or options["carriers"] not in ("exclude", "include", "only"):
            raise ValueError("Invalid pad or carriers filter")
        result = self.plan(q)
        options["reference"] = q.get("reference") or result["reference"]
        finder = Sourcing(self.core)
        def lookup(item):
            try:
                report = finder.find({**options, "commodity": item["commodity"], "commodity_key": item["commodity_key"], "quantity": item["quantity"]})
                return {**item, **report}
            except Exception as ex:
                return {**item, "status": "lookup_failed", "error": str(ex), "sources": []}
        with ThreadPoolExecutor(max_workers=3) as pool:
            reports = list(pool.map(lookup, result["shopping_list"]))
        stops = {}
        for report in reports:
            if not report["sources"]:
                continue
            source = report["sources"][0]
            key = (source["system"], source["station"])
            stop = stops.setdefault(key, {"system": key[0], "station": key[1], "distance_ly": source["distance_ly"], "purchases": [], "estimated_cost": 0})
            stop["purchases"].append({"commodity": report["commodity"], "quantity": report["quantity"], "mission_ids": report["mission_ids"]})
            stop["estimated_cost"] += source["cost_for_quantity"]
        return {**result, "search": options, "supplies": reports,
                "suggested_buy_stops": sorted(stops.values(), key=lambda r: r["distance_ly"]),
                "search_note": "Nearest reported supplier per commodity, grouped by station; not an optimized route. Radius is never widened. Carrier access is unknown when carriers are enabled. Refresh after purchases."}


def setup(core, module):
    m = Missions(core)
    core.http.route("/api/missions/plan", m.plan, tool="get_mission_plan", module=module.name,
        description="Active missions, required commodities, allocated cargo, depot progress, shopping list and delivery stops. Distinguishes buying from assigned delivery cargo and salvage. No network requests.",
        params={"mission_id": {"type": "string", "description": "Optional mission ID; allocation still accounts for all active missions"}})
    core.http.route("/api/missions/sources", m.sources, tool="find_mission_sources", module=module.name,
        description="Find nearby sellers for active source-and-return shortages automatically. Groups nearest suppliers into buy stops. Defaults to stations, large pads, strict 25 Ly radius and reports under 2 days. Does not search salvage/delivery goods or buy anything.",
        params={"mission_id": {"type": "string"}, "reference": {"type": "string", "description": "Defaults to current ship system"},
                "max_distance_ly": {"type": "integer", "default": 25}, "max_days": {"type": "integer", "default": 2},
                "pad": {"type": "string", "enum": ["S", "M", "L"], "default": "L"},
                "carriers": {"type": "string", "enum": ["exclude", "include", "only"], "default": "exclude"},
                "limit": {"type": "integer", "default": 3, "description": "Alternatives per commodity, 1-10"}})
