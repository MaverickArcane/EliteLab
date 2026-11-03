"""Bounded Powerplay target comparison and journal purchase-origin evidence."""
import datetime as dt
import math
import threading
import time

from elitelab.core.gamedata import POWERS, RARES
from .pricing import age, coords, estimate, label, number, param, rare_key

ORBITAL = ("Coriolis Starport", "Orbis Starport", "Ocellus Starport", "Dodec Starport", "Asteroid base", "Outpost")


class Targets:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.serial = 0
        self.origins = {}
        self.exposed = set()
        self.pledge = None
        self.commander = None
        self.fid = None
        core.store.update("targets", {"last":None, "origins":{}, "pledge":None, "evidence_revision":0})
        core.bus.on("journal.*", self.event)
        for key in ("cargo", "system", "cmdr", "jump_range_laden", "jump_range_now"):
            core.bus.on("state.journal." + key, self.invalidate)
        core.bus.on("state.loop.stations", self.invalidate)

    def invalidate(self, name, value):
        with self.lock:
            self.serial += 1
            self.core.store.update("targets", {"last":None, "evidence_revision":self.serial})

    def event(self, name, event):
        if not isinstance(event, dict):
            return
        kind = event.get("event")
        with self.lock:
            if kind == "LoadGame":
                self.origins, self.exposed, self.pledge = {}, set(), None
                self.commander, self.fid = event.get("Commander"), event.get("FID")
            elif kind == "Commander":
                commander, fid = event.get("Name"), event.get("FID")
                if ((commander and commander != self.commander) or (fid and fid != self.fid)):
                    self.origins, self.exposed, self.pledge = {}, set(), None
                self.commander, self.fid = commander or self.commander, fid or self.fid
            elif kind in ("Powerplay", "PowerplayJoin", "PowerplayDefect", "PowerplayLeave"):
                power = event.get("ToPower") if kind == "PowerplayDefect" else event.get("Power")
                self.pledge = power if power in POWERS and kind != "PowerplayLeave" else None
            elif kind == "MarketBuy":
                key = rare_key(event.get("Type"))
                if key:
                    j = self.core.store.get("journal") or {}
                    if j.get("station_type") == "FleetCarrier":
                        self.exposed.add(key)
                    elif not j.get("station_type"):
                        self.origins[key] = {"system":"", "coords":None, "basis":"purchase location unknown"}
                    else:
                        origin = {"system":label(j.get("system")), "coords":coords(j.get("star_pos")), "basis":"journal purchase"}
                        old = self.origins.get(key)
                        self.origins[key] = origin if old is None or old == origin else {"system":"", "coords":None, "basis":"conflicting purchases"}
            elif kind == "CargoTransfer":
                transfers = event.get("Transfers")
                for transfer in (transfers[:256] if isinstance(transfers, list) else []):
                    if isinstance(transfer, dict) and (key := rare_key(transfer.get("Type"))):
                        self.exposed.add(key)
            elif kind in ("Died", "Resurrect"):
                self.origins = {}
            else:
                return
            self.serial += 1
            self.core.store.update("targets", {"last":None, "origins":dict(self.origins), "pledge":self.pledge, "evidence_revision":self.serial})

    def snapshot(self):
        j = self.core.store.get("journal") or {}
        with self.lock:
            origins, exposed, pledge = dict(self.origins), set(self.exposed), self.pledge
        catalog = {}
        # Read the loop's published catalogue; never import another module or
        # mistake the commander's current/search system for every rare's origin.
        for stop in (self.core.store.get("loop", "stations") or [])[:64]:
            for rare in (stop.get("rares") or [])[:32]:
                c = stop.get("coords") or {}
                catalog[rare.get("key")] = {"system":stop.get("system"), "coords":coords([c.get(k) for k in "xyz"]), "basis":"rare loop catalogue"}
        cargo = []
        counts = {}
        for index, raw in enumerate(((j.get("cargo") or {}).get("items") or [])[:256]):
            if not isinstance(raw, dict):
                continue
            key = rare_key(raw.get("key")) or rare_key(raw.get("name"))
            if not key and raw.get("rare") is True:
                key = f"unmapped-{index}"
            if not key:
                continue
            tons = number(raw.get("count"), 1000000)
            if tons == 0:
                continue
            counts.setdefault(key, {"tons":0, "stolen":False, "name":RARES.get(key) or label(raw.get("name")) or "Unknown rare"})
            counts[key]["tons"] = counts[key]["tons"] + int(tons) if counts[key]["tons"] is not None and tons is not None and tons == int(tons) else None
            counts[key]["stolen"] |= bool(raw.get("stolen"))
        for key, count in sorted(counts.items()):
            origin = origins.get(key) or catalog.get(key) or {}
            cargo.append({"key":key, **count, "origin":origin.get("system") or None,
                          "origin_coords":origin.get("coords"), "origin_basis":origin.get("basis", "unknown"),
                          "carrier_exposed":key in exposed})
        context = {k:j.get(k) for k in ("system", "cmdr", "jump_range_laden", "jump_range_now", "cargo")}
        context.update(cargo_model=cargo, pledge=pledge)
        return j, cargo, pledge, context

    def find(self, q):
        j, cargo, pledge, context = self.snapshot()
        power, ref = q.get("power", pledge), q.get("ref", j.get("system"))
        if not isinstance(power, str) or power not in POWERS:
            raise ValueError("Pledged power unknown. Select a known power explicitly.")
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 160:
            raise ValueError("Enter a reference system (up to 160 characters).")
        ref = ref.strip()
        lo, hi = param(q, "min", 125, 500), param(q, "max", 200, 500, 0.01)
        if lo > hi:
            raise ValueError("min must not exceed max.")
        limit = param(q, "limit", 40, 100, 1, True)
        hours = param(q, "hours", 24, 168, 0.01)
        pad, sort, mode = q.get("pad", "L"), q.get("sort", "merits_per_jump"), q.get("rate_mode", "unknown")
        if pad not in ("L", "M") or sort not in ("distance", "merits", "merits_per_jump") or mode not in ("unknown", "mahon_observed", "custom"):
            raise ValueError("Choose a valid pad, sort and merit-rate mode.")
        if mode == "mahon_observed" and power != "Edmund Mahon":
            raise ValueError("The Mahon observation cannot be applied to another power. Choose unknown or supply your own rate.")
        rate = param(q, "credits_per_merit", None, 1000000000, 0.01) if mode == "custom" else 667 if mode == "mahon_observed" else None
        curve = q.get("interpolate", False)
        if not (type(curve) is bool or (isinstance(curve, str) and curve in ("true", "false"))):
            raise ValueError("interpolate must be true or false.")
        curve = curve in (True, "true")
        if self.core.config.OFFLINE:
            raise ValueError("Community target searches are unavailable in offline mode.")
        with self.lock:
            self.serial += 1
            serial = self.serial
            self.core.store.set("targets", "last", None)
        filters = {"system_power":{"value":[power]}, "system_power_state":{"value":["Unoccupied"]},
                   "has_market":{"value":True}, "type":{"value":list(ORBITAL)}, "distance":{"min":lo, "max":hi}}
        if pad == "L":
            filters["has_large_pad"] = {"value":True}
        raw, available, partial = [], None, False
        for page in range(4):
            try:
                data = self.core.services.fetch_json("https://www.spansh.co.uk/api/stations/search",
                    {"filters":filters, "reference_system":ref, "sort":[{"distance":{"direction":"asc"}}], "size":25, "page":page}, ttl=300)
                if not isinstance(data, dict) or data.get("error") or not isinstance(data.get("results"), list):
                    raise ValueError()
            except Exception as exc:
                if not raw:
                    raise ValueError("Spansh target search unavailable. Check the system name and retry.") from exc
                partial = True
                break
            batch = data["results"][:25]
            raw.extend(batch)
            available = number(data.get("count"))
            if len(batch) < 25 or available is None or len(raw) >= available:
                break
        now, rows, seen = time.time(), [], set()
        laden, current = number(j.get("jump_range_laden"), 1000), number(j.get("jump_range_now"), 1000)
        jump = min(laden, current) if laden and current else None
        for station in raw:
            if not isinstance(station, dict):
                continue
            powers = station.get("system_power")
            powers = powers if isinstance(powers, list) else [powers]
            if power not in powers or station.get("system_power_state") != "Unoccupied" or station.get("has_market") is not True or station.get("type") not in ORBITAL or station.get("is_planetary") or station.get("carrier_name"):
                continue
            actual_pad = "L" if station.get("has_large_pad") is True else "M" if number(station.get("medium_pads")) else None
            distance = number(station.get("distance"), hi)
            identity = (label(station.get("system_name")), label(station.get("name")))
            if actual_pad is None or (pad == "L" and actual_pad != "L") or distance is None or distance < lo or not all(identity) or identity in seen:
                continue
            seen.add(identity)
            pos = coords([station.get("system_" + k) for k in "xyz"])
            fresh = age(station.get("market_updated_at"), now)
            market = station.get("market")
            indexed = {}
            for entry in (market[:1000] if isinstance(market, list) else []):
                if isinstance(entry, dict) and (key := rare_key(entry.get("commodity"))):
                    # Duplicate entries cannot silently select a favorable quote.
                    indexed[key] = entry if key not in indexed else {}
            goods = {}
            for item in cargo:
                entry = indexed.get(item["key"])
                d = math.dist(item["origin_coords"], pos) if item["origin_coords"] and pos else None
                status, price, demand = "not_reported", None, None
                if fresh is None or fresh > hours:
                    status = "stale_or_undated"
                elif item["tons"] is None:
                    status = "quantity_unknown"
                elif entry is not None:
                    price, demand = number(entry.get("sell_price"), 10**9), number(entry.get("demand"))
                    status = "prohibited" if entry.get("is_prohibited") else "demand_unknown" if demand is None else "insufficient_demand" if demand < item["tons"] else "reported" if price else "price_unknown"
                    if status != "reported":
                        price = None
                goods[item["key"]] = {"name":item["name"], "tons":item["tons"], "origin":item["origin"],
                    "source_distance":round(d, 4) if d is not None else None, "price":price, "demand":demand, "status":status}
            refuses = [v["name"] for v in goods.values() if v["status"] == "prohibited"]
            unknown = [v["name"] for v in goods.values() if v["status"] not in ("reported", "price_unknown", "prohibited")]
            rows.append({"system":identity[0], "station":identity[1], "dist":distance, "jumps":math.ceil(distance / jump) if jump else None,
                         "ls":number(station.get("distance_to_arrival")), "type":station.get("type"), "pad":actual_pad,
                         "updated":label(station.get("market_updated_at")) or None, "age_hours":fresh,
                         "x":pos[0] if pos else None, "y":pos[1] if pos else None, "z":pos[2] if pos else None,
                         "goods":goods, "refuses":refuses, "unknown_goods":unknown, "accepts_all":False if refuses else None if unknown or not cargo else True})
        curves = estimate(rows, cargo, rate, curve)
        metric = "estimated_merits" if sort == "merits" else "merits_per_jump"
        rows.sort(key=lambda r: (r[metric] is None, -(r[metric] or 0), r["dist"], r["station"]) if sort != "distance" else (r["dist"], r["station"]))
        out = {"request_id":serial, "results":rows[:limit], "count":available, "stations_checked":len(raw), "matched":len(rows),
               "ref":ref, "power":power, "min":lo, "max":hi, "pad":pad, "hours":hours, "sort":sort, "jump_range":jump,
               "manual_origin":ref.casefold() != label(j.get("system")).casefold(), "cargo":cargo, "hold_rares":[r["name"] for r in cargo],
               "curves":curves, "rate_mode":mode, "credits_per_merit":rate, "interpolate":curve, "partial":partial,
               "fetched_at":dt.datetime.now(dt.timezone.utc).isoformat(),
               "rate_note":"Conditional conversion: assumes the selected Cr-per-merit rate and current game eligibility. "
                           + ("667 is an October 2026 Mahon-with-bonus observation, not a universal rate." if mode == "mahon_observed" else "Custom rates are user assumptions." if rate else "No rate selected; merit estimates remain unknown."),
               "note":"Ranks at most 100 reported orbital markets in the chosen band; not a galaxy-wide optimum. "
                      "Per-good distance is from that rare's source; travel distance is from the search origin. "
                      "Jumps use unboosted laden/current range and straight-line distance, not a plotted route; merits/jump is optimistic. "
                      "Incomplete loads are not ranked as complete totals. Missing listings do not prove refusal. "
                      "Reported prices/demand and power control may change; verify local activities and cargo provenance. "
                      "Carrier-exposed, stolen or same-origin goods cannot produce a merit forecast. Planning never changes recorded gains. "
                      + ("A provider page failed; coverage is partial." if partial else "")}
        with self.lock:
            if serial != self.serial or self.snapshot()[3] != context:
                raise ValueError("Cargo, ship, pledge or location changed, or a newer search started. Search again.")
            self.core.store.set("targets", "last", out)
        return out
