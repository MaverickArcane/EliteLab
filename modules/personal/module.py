"""One-leg personal trades, using bounded Ardent/EDDN community reports."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
from urllib.parse import quote, urlencode

from elitelab.core.gamedata import is_rare


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def numeric(q, key, default, maximum, integer=False):
    try:
        value = q.get(key, default)
        n = float(value)
        if isinstance(value, bool) or not math.isfinite(n) or not 0 < n <= maximum or (integer and n != int(n)):
            raise ValueError()
        return int(n) if integer else n
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{key} must be a positive {'whole ' if integer else ''}number up to {maximum}.") from None


def system_name(value):
    if not isinstance(value, str) or len(value) > 160:
        raise ValueError("System names must be text up to 160 characters.")
    return value.strip()


class Personal:
    def __init__(self, core):
        self.core = core

    def coordinates(self, system, journal):
        if system.casefold() == (journal.get("system") or "").casefold() and journal.get("star_pos"):
            return journal["star_pos"]
        try:
            coords = self.core.services.edsm_coords([system]).get(system)
            if coords and all(type(coords.get(a)) in (int, float) and math.isfinite(coords[a]) for a in "xyz"):
                return [coords[a] for a in "xyz"]
        except Exception:
            pass
        raise ValueError(f"Coordinates unavailable for {system}. Check the system name or try again.")

    def quotes(self, key, side, settings, reference):
        params = urlencode({"minVolume": settings["quantity"], "maxDaysAgo": math.ceil(settings["hours"] / 24), "fleetCarriers": 0,
                            "maxDistance": math.ceil(settings["distance"])})
        base = "https://api.ardent-insight.com/v2/system/name/" + quote(settings["origin"], safe="")
        path = "/commodities/exports" if side == "exports" else "/commodity/name/" + quote(key, safe="") + "/nearby/imports"
        data = self.core.services.fetch_json(base + path + "?" + params, ttl=300)
        if not isinstance(data, list):
            raise ValueError("Unexpected market response.")
        rows = []
        clock = datetime.now(timezone.utc)
        buying = side == "exports"
        for r in (data if buying else data[:1000]):
            if not isinstance(r, dict):
                continue
            commodity = r.get("commodityName")
            if not isinstance(commodity, str) or not commodity.isascii() or not commodity.isalnum() or is_rare(commodity) or (key and commodity != key):
                continue
            price, volume = r.get("buyPrice" if buying else "sellPrice"), r.get("stock" if buying else "demand")
            if not positive(price) or not positive(volume) or volume < settings["quantity"]:
                continue
            if r.get("stationType") in ("FleetCarrier", "StrongholdCarrier") or r.get("maxLandingPadSize") not in (1, 2, 3) or r["maxLandingPadSize"] < settings["pad"]:
                continue
            if not r.get("marketId") or not r.get("stationName") or not r.get("systemName"):
                continue
            try:
                age = (clock - datetime.fromisoformat(r["updatedAt"].replace("Z", "+00:00"))).total_seconds()
                if not 0 <= age <= settings["hours"] * 3600:
                    continue
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            pos = [r.get("system" + a) for a in "XYZ"]
            if not all(type(n) in (int, float) and math.isfinite(n) for n in pos):
                continue
            if buying and r["systemName"].casefold() != settings["origin"].casefold():
                continue
            if not buying and settings["destination"] and r["systemName"].casefold() != settings["destination"].casefold():
                continue
            distance = math.dist(reference, pos)
            if distance > settings["distance"]:
                continue
            rows.append({"commodity": commodity, "station": r["stationName"], "system": r["systemName"], "market_id": r["marketId"],
                         "price": price, "volume": volume, "observed_at": r["updatedAt"],
                         "pad": {1: "S", 2: "M", 3: "L"}[r["maxLandingPadSize"]],
                         "arrival_ls": r.get("distanceToArrival"), "distance": distance})
        return rows

    def search(self, q):
        if self.core.config.OFFLINE:
            raise ValueError("Community route search is unavailable in offline mode.")
        j = self.core.store.get("journal")
        origin = system_name(q.get("origin") or j.get("system") or "")
        destination = system_name(q.get("destination", ""))
        if not origin:
            raise ValueError("Enter a starting system or wait for your journal location.")
        quantity = numeric(q, "quantity", j.get("cargo_capacity"), 1000000, True)
        hours = numeric(q, "hours", 24, 72, True)
        breadth = numeric(q, "breadth", 24, 48, True)
        pad = q.get("pad", "L")
        if pad not in ("S", "M", "L"):
            raise ValueError("Choose S, M or L for landing pad size.")
        mode = q.get("distance_mode", "ly")
        range_value = j.get("jump_range_laden")
        if not positive(range_value):
            range_value = None
        if mode == "jumps":
            jumps = numeric(q, "jumps", 2, 20, True)
            if range_value is None:
                raise ValueError("Fully laden ship range is unknown. Use a light-year distance until ship data is available.")
            distance = jumps * range_value
        elif mode == "ly":
            distance = numeric(q, "distance", 80, 500)
        else:
            raise ValueError("Choose light-years or estimated jumps.")
        if distance > 500:
            raise ValueError("Community search supports up to 500 Ly. Reduce the number of jumps.")
        selected = q.get("commodity", "")
        if not isinstance(selected, str) or len(selected) > 100 or (selected and (not selected.isascii() or not selected.isalnum())):
            raise ValueError("Use a commodity identifier from the market list.")
        reference = self.coordinates(origin, j)
        settings = {"origin": origin, "destination": destination, "quantity": quantity, "distance": distance,
                    "hours": hours, "pad": {"S": 1, "M": 2, "L": 3}[pad]}
        local = self.quotes("", "exports", settings, reference)
        catalog = self.core.services.fetch_json("https://api.ardent-insight.com/v2/commodities", ttl=3600)
        if not isinstance(catalog, list):
            raise ValueError("Could not retrieve the commodity catalog.")
        catalog = [r for r in catalog if isinstance(r, dict) and isinstance(r.get("commodityName"), str)
                   and r["commodityName"].isascii() and r["commodityName"].isalnum() and not is_rare(r["commodityName"])
                   and positive(r.get("minBuyPrice")) and positive(r.get("maxSellPrice"))]
        catalog.sort(key=lambda r: r["maxSellPrice"] - r["minBuyPrice"], reverse=True)
        # Rank locally available goods by potential spread, not galaxy-wide supply.
        highs = {r["commodityName"]: r["maxSellPrice"] for r in catalog}
        cheapest = {}
        for row in local:
            cheapest[row["commodity"]] = min(cheapest.get(row["commodity"], math.inf), row["price"])
        keys = sorted(cheapest, key=lambda k: (-(highs.get(k, cheapest[k]) - cheapest[k]), k))
        candidates = [selected] if selected else keys[:breadth]
        candidates = [k for k in candidates if k in cheapest]
        warnings, reports = [], {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {(key, "imports"): pool.submit(self.quotes, key, "imports", settings, reference) for key in candidates}
            for (key, side), future in futures.items():
                try:
                    reports[key, side] = future.result()
                except Exception:
                    reports[key, side] = []
                    warnings.append(f"Could not retrieve {side} for {key}.")
        rows = []
        for key in candidates:
            buys = [r for r in local if r["commodity"] == key]
            for sell in reports[key, "imports"]:
                suppliers = [b for b in buys if b["market_id"] != sell["market_id"] and b["price"] < sell["price"]]
                if not suppliers:
                    continue
                buy = min(suppliers, key=lambda b: b["price"])
                spread = sell["price"] - buy["price"]
                rows.append({"commodity": key, "buy": buy, "sell": sell, "distance": round(sell["distance"], 1),
                             "estimated_jumps": max(1, math.ceil(sell["distance"] / range_value)) if range_value and sell["distance"] else 0 if range_value else None,
                             "quantity": quantity, "per_ton": spread, "profit": spread * quantity, "cost": buy["price"] * quantity})
        rows.sort(key=lambda r: (-r["profit"], r["distance"]))
        return {"rows": rows[:30], "commodities": sorted(keys), "screened": len(candidates), "available": len(keys),
                "settings": settings, "laden_range": range_value, "ship_capacity": j.get("cargo_capacity"),
                "credits": j.get("credits"), "source": "Ardent / EDDN", "warnings": warnings,
                "queried_at": datetime.now(timezone.utc).isoformat(),
                "note": "Local supply matched to up to 1,000 nearby buyers per commodity, cached five minutes. Reports and the commodity shortlist are not exhaustive. Jump counts are straight-line estimates, not plotted routes. Profit excludes fuel, fees and bonuses."}


def setup(core, module):
    search = Personal(core)
    core.http.route("/api/personal/routes", search.search, tool="find_personal_trade_routes", module=module.name,
        description="Find ship-sized one-way buy/sell trades from Ardent/EDDN reports. Buy stops must be in origin (default current system); blank destination allows any system within distance (maximum 500 Ly). Local exports matched to up to 1,000 nearby buyers per commodity; not exhaustive. Jumps mode uses fully laden ship range as an approximate radius, not actual navigation. Returns up to 30 routes ranked by estimated load profit, excluding expenses. Reports cached five minutes. No game actions.",
        params={"origin": {"type": "string"}, "destination": {"type": "string", "default": ""},
                "quantity": {"type": "integer", "description": "Tonnes per load; defaults to current ship capacity."},
                "distance_mode": {"type": "string", "enum": ["ly", "jumps"], "default": "ly"},
                "distance": {"type": "number", "default": 80}, "jumps": {"type": "integer", "default": 2},
                "pad": {"type": "string", "enum": ["S", "M", "L"], "default": "L"},
                "hours": {"type": "integer", "default": 24}, "breadth": {"type": "integer", "default": 24},
                "commodity": {"type": "string", "default": ""}})
