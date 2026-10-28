"""Paired buy/sell routes from fresh community market reports.

Prices are EDDN reports served by Ardent, never described as Inara data.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import threading
from urllib.parse import quote, urlencode

from elitelab.core.gamedata import is_rare

PROFILES = [{"id": "route", "name": "Buy / sell route", "description": "Low-priced supply near high-paying buyers."}]



def stamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return 0


class MarketProfiles:
    def __init__(self, core, desk):
        self.core, self.desk = core, desk
        self.lock = threading.Lock()
        self.results = {}  # bounded query cache, also the IDs accepted by plan selection

    def price_reference(self, q):
        key = q.get("commodity", "")
        if not isinstance(key, str) or not key.isascii() or not key.isalnum() or len(key)>100:
            raise ValueError("Choose a commodity before refreshing carrier pricing.")
        observed = []
        now = datetime.now(timezone.utc).timestamp()
        with self.desk.lock:
            for market in self.desk.data["markets"].values():
                for item in market["items"]:
                    if item["key"] == key and type(item.get("mean_price")) is int and item["mean_price"]>0:
                        observed.append({"mean_price":item["mean_price"],"observed_at":market["timestamp"],"source":"Local market journal"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(self.core.services.fetch_json,
                "https://api.ardent-insight.com/v2/commodity/name/"+quote(key,safe="")+"/"+side+"?minVolume=1&maxDaysAgo=1&fleetCarriers=0",ttl=300)
                for side in ("exports","imports")]
            for future in pending:
                try:
                    for row in future.result():
                        if type(row.get("meanPrice")) is int and row["meanPrice"]>0:
                            observed.append({"mean_price":row["meanPrice"],"observed_at":row.get("updatedAt"),"source":"Ardent / EDDN"})
                except Exception:
                    pass
        recent = [r for r in observed if 0 <= now-stamp(r["observed_at"]) <= 86400]
        if not recent:
            raise ValueError("No recent 100% price reference is available. Open a commodity market in game or enter its 100% price under Adjust operation.")
        return {"commodity":key, **max(recent,key=lambda r:stamp(r["observed_at"]))}

    def context(self):
        j = self.core.store.get("journal")
        carrier = j.get("carrier") or {}
        with self.desk.lock:
            inventory = self.desk.data["inventory"].copy()
            orders = self.desk.data["orders"].copy()
        historical_total = sum(r.get("stock") or 0 for r in inventory.values() if stamp(r.get("updated_at")) <= stamp(carrier.get("stats_time")))
        conflict = carrier.get("cargo") is not None and historical_total > carrier["cargo"]
        free = carrier.get("free_space")
        reserved = carrier.get("reserved_space") or 0
        return {"carrier": carrier.get("name"), "callsign": carrier.get("callsign"), "system": carrier.get("system") or j.get("system"),
                "free_space": free + reserved if free is not None else None, "unreserved_space": free, "reserved_space": reserved, "reported_cargo": carrier.get("cargo"), "stats_time": carrier.get("stats_time"),
                "ship_capacity": j.get("cargo_capacity"), "inventory": inventory, "orders": orders, "inventory_conflict": conflict,
                "power": self.core.store.get("powerplay", "power"), "rank": self.core.store.get("powerplay", "rank")}

    def signature(self, context):
        return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[:20]

    def quotes(self, key, side, settings, reference):
        params = urlencode({"minVolume": settings["min_volume"], "maxDaysAgo": max(1, math.ceil(settings["hours"] / 24)), "fleetCarriers": 0})
        url = "https://api.ardent-insight.com/v2/commodity/name/" + quote(key, safe="") + ("/exports?" if side == "buy" else "/imports?") + params
        data = self.core.services.fetch_json(url, ttl=300)
        if not isinstance(data, list):
            raise ValueError("Unexpected market report format.")
        out, clock = [], datetime.now(timezone.utc).timestamp()
        for r in data[:100]:
            age = clock - stamp(r.get("updatedAt"))
            price, volume = r.get("buyPrice" if side == "buy" else "sellPrice"), r.get("stock" if side == "buy" else "demand")
            if not isinstance(price, (int, float)) or not isinstance(volume, (int, float)) or not math.isfinite(price) or not math.isfinite(volume) or price <= 0 or volume < settings["min_volume"]:
                continue
            if not 0 <= age <= settings["hours"] * 3600 or (r.get("maxLandingPadSize") or 0) < settings["pad"] or r.get("stationType") == "FleetCarrier":
                continue
            arrival = r.get("distanceToArrival")
            if settings["arrival"] and (arrival is None or arrival > settings["arrival"]):
                continue
            pos = [r.get("system" + axis) for axis in "XYZ"]
            pos = pos if all(isinstance(n, (int, float)) and math.isfinite(n) for n in pos) else None
            distance = math.dist(reference, pos) if reference and pos else None
            if settings["radius"] and (distance is None or distance > settings["radius"]):
                continue
            out.append({"market_id": r.get("marketId"), "station": r.get("stationName"), "system": r.get("systemName"),
                        "price": price, "volume": volume, "mean_price": r.get("meanPrice"), "observed_at": r.get("updatedAt"), "distance": round(distance, 1) if distance is not None else None,
                        "arrival_ls": arrival, "pad": {1: "S", 2: "M", 3: "L"}.get(r.get("maxLandingPadSize")), "pos": pos})
        return sorted(out, key=lambda r: r["price"] if side == "buy" else -r["price"])

    def query(self, q):
        if self.core.config.OFFLINE:
            raise ValueError("Market reports are unavailable in offline mode. Your carrier inventory remains available.")
        profile = q.get("profile", "route")
        if profile != "route":
            raise ValueError("Use the buy/sell route search. Refresh the dashboard to update old profiles.")
        try:
            hours = int(q.get("hours", 6))
            radius = int(q.get("radius", 100))
            route_distance = int(q.get("route_distance", 100))
            min_volume = int(q.get("min_volume", 0))
            sell_percent = int(q.get("sell_percent", 80))
            breadth = int(q.get("breadth", 24))
            arrival = int(q.get("arrival", 10000))
            if (hours not in (3, 6, 12, 24, 72) or radius not in (0, 25, 50, 100, 250, 500, 1000)
                    or route_distance not in (25, 50, 100, 250, 500) or not 0 <= min_volume <= 1000000
                    or sell_percent not in (0, 80, 90, 95) or breadth not in (24, 48, 96)
                    or arrival not in (0, 2000, 10000, 50000)):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Choose supported route filters and a positive minimum volume.") from None
        pad = q.get("pad", "L")
        if pad not in ("L", "M", "S"):
            raise ValueError("Choose a landing pad size.")
        key = q.get("commodity", "")
        if not isinstance(key, str) or len(key) > 100:
            raise ValueError("Invalid commodity selection.")
        ctx = self.context()
        volume_mode = "carrier" if min_volume == 0 else "manual"
        if volume_mode == "carrier":
            capacity = ctx["free_space"]
            min_volume = max(1, math.ceil(capacity or 0))
        signature = self.signature(ctx)
        settings = {"hours": hours, "radius": radius, "route_distance": route_distance,
                    "min_volume": min_volume, "volume_mode": volume_mode, "sell_percent": sell_percent, "breadth": breadth,
                    "arrival": arrival, "pad": {"S": 1, "M": 2, "L": 3}[pad]}
        cache_key = json.dumps([signature, settings, key], sort_keys=True)
        clock = datetime.now(timezone.utc).timestamp()
        # Serialize requests: auto-refresh and other tabs reuse the same completed query.
        with self.lock:
            hit = self.results.get(cache_key)
            if hit and clock - stamp(hit["queried_at"]) < 300:
                return self.with_current_context(hit)
            result = self.search(ctx, settings, key)
            result.update(signature=signature, profile=profile, context=ctx, settings=settings,
                          queried_at=datetime.now(timezone.utc).isoformat(), source="Ardent / EDDN", source_url="https://ardent-insight.com/",
                          note="Reported prices, cached five minutes. Market observation times are shown per result. Carrier stock is reconstructed evidence.")
            for row in result["rows"]:
                row["id"] = hashlib.sha256(json.dumps([signature, profile, row], sort_keys=True).encode()).hexdigest()[:24]
            self.results[cache_key] = result
            while len(self.results) > 12:
                del self.results[next(iter(self.results))]
            return self.with_current_context(result)

    def with_current_context(self, result):
        # A journal update during network I/O must not look like current advice.
        return {**result, "outdated": result["signature"] != self.signature(self.context())}

    def search(self, ctx, settings, selected):
        inv, orders = ctx["inventory"], ctx["orders"]
        catalog = self.core.services.fetch_json("https://api.ardent-insight.com/v2/commodities", ttl=3600)
        if not isinstance(catalog, list):
            raise ValueError("Could not read the commodity list.")
        # Use reported internal identifiers, never guess them from display names.
        catalog = [r for r in catalog if isinstance(r.get("commodityName"), str)
                   and r["commodityName"].isascii() and r["commodityName"].isalnum()
                   and not is_rare(r["commodityName"]) and (r.get("totalStock") or 0) >= settings["min_volume"]]
        catalog.sort(key=lambda r: -((r.get("maxSellPrice") or 0) - (r.get("minBuyPrice") or 0)))
        names = {r["commodityName"]: inv.get(r["commodityName"], {}).get("name") or r["commodityName"] for r in catalog}
        for k in sorted(set(inv) | set(orders)):
            if not is_rare(k):
                names.setdefault(k, inv.get(k, {}).get("name") or orders.get(k, {}).get("name") or k)
        commodities = [{"key": k, "name": name} for k, name in sorted(names.items())]
        if selected and selected not in names:
            raise ValueError("Choose a commodity from the market list or your carrier inventory.")
        candidates = [selected] if selected else list(names)[:settings["breadth"]]
        warnings = []
        if ctx.get("reserved_space"):
            warnings.append(f"Load sizing includes {ctx['reserved_space']:,} t reserved by existing buy orders. Cancel or resize those orders in game before placing a replacement order; clearing an EliteLab trade does not release them.")
        if not ctx["free_space"]:
            warnings.append("Browsing routes without a load size: carrier capacity is unknown or full. Update Carrier Management in game before preparing a new load.")
        meta = {"commodities": commodities, "available": len(names), "screened": len(candidates)}
        reference = None
        j = self.core.store.get("journal")
        if ctx["system"] == j.get("system"):
            reference = j.get("star_pos")
        elif ctx["system"]:
            try:
                coords = self.core.services.edsm_coords([ctx["system"]]).get(ctx["system"])
                reference = [coords[a] for a in "xyz"] if coords else None
            except Exception:
                pass
        if settings["radius"] and reference is None:
            return {**meta, "rows": [], "warnings": ["Carrier coordinates are unavailable. Set search distance to Any to browse without a radius."]}
        jobs = [(k, side) for k in candidates for side in ("buy", "sell")]
        reports = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = {(k, side): pool.submit(self.quotes, k, side, settings, reference) for k, side in jobs}
            for (k, side), future in pending.items():
                try:
                    reports[k, side] = future.result()
                except Exception:
                    reports[k, side] = []
                    warnings.append(f"Could not retrieve {side} reports for {k}.")
        rows = []
        for k in candidates:
            buys, sells = reports[k, "buy"], reports[k, "sell"]
            high = max((r["price"] for r in sells), default=0)
            references = [r for r in buys+sells if type(r.get("mean_price")) is int and r["mean_price"] > 0]
            reference = max(references, key=lambda r:stamp(r["observed_at"]), default={})
            for sell in sells:
                if not sell["pos"] or not sell["market_id"] or sell["price"] < high * settings["sell_percent"] / 100:
                    continue
                eligible = []
                for buy in buys:
                    if not buy["pos"] or not buy["market_id"] or buy["market_id"] == sell["market_id"] or sell["price"] <= buy["price"]:
                        continue
                    distance = math.dist(buy["pos"], sell["pos"])
                    if distance <= settings["route_distance"]:
                        eligible.append((buy, distance))
                if not eligible:
                    continue
                # Cheapest qualifying supplier for this buyer, then the shortest leg.
                buy, distance = min(eligible, key=lambda pair: (pair[0]["price"], pair[1], -pair[0]["volume"]))
                market_qty = min(buy["volume"], sell["volume"])
                qty = min(market_qty, max(0, ctx["free_space"])) if ctx["free_space"] is not None else None
                margin = sell["price"] - buy["price"]
                stock = inv.get(k, {}).get("stock")
                needs_check = ctx["inventory_conflict"] and stamp(inv.get(k, {}).get("updated_at")) <= stamp(ctx["stats_time"])
                rows.append({"commodity": k, "name": names[k], "buy": buy, "sell": sell,
                    "mean_price": reference.get("mean_price"), "mean_price_at": reference.get("observed_at"),
                    "route_distance": round(distance, 1), "reported_high": high, "sell_percent": round(100 * sell["price"] / high, 1),
                    "per_ton": margin, "return_percent": round(100 * margin / buy["price"], 1),
                    "stock": stock, "stock_needs_check": needs_check, "order": orders.get(k),
                    "quantity": qty, "market_quantity": market_qty, "value": margin * qty if qty is not None else None,
                    "value_label": "Gross spread", "purchase_cost": buy["price"] * qty if qty is not None else None,
                    "runs": math.ceil(qty / ctx["ship_capacity"]) if qty is not None and ctx["ship_capacity"] else None})
        rows.sort(key=lambda r: (-r["per_ton"], r["buy"]["price"], r["route_distance"], -(r["quantity"] or 0)))
        return {**meta, "rows": rows[:18], "warnings": warnings}

    def select(self, q):
        if self.core.store.get("party", "mode") == "member":
            raise ValueError("Only the carrier owner selects the shared route.")
        identity = q.get("id")
        with self.lock:
            found = next(((result, row) for result in self.results.values() for row in result["rows"] if row["id"] == identity), None)
        if found is None:
            raise ValueError("Refresh the trade results before selecting this operation.")
        result, row = found
        with self.desk.lock:
            if result["signature"] != self.signature(self.context()):
                raise ValueError("Carrier inventory or context changed. Refresh the results before selecting.")
            if datetime.now(timezone.utc).timestamp() - stamp(result["queried_at"]) > 600:
                raise ValueError("These results are over ten minutes old. Refresh before selecting.")
            if (self.desk.data.get("operation") or {}).get("stage") in ("loading", "transit", "unloading"):
                raise ValueError("Finish or cancel the current trade before selecting another route.")
            if row["stock"] is None or row["stock_needs_check"]:
                if "stock" not in q:
                    raise ValueError("Reconcile this commodity's current carrier stock before planning its target.")
                self.desk.reconcile({"commodity": row["commodity"], "stock": q["stock"]})
                row = {**row, "stock": self.desk.data["inventory"][row["commodity"]]["stock"], "stock_needs_check": False}
            if not row["quantity"]:
                raise ValueError("A positive reported carrier free capacity is required to size this load.")
            buy, sell = row["buy"], row["sell"]
            loading = True
            order = result["context"]["orders"].get(row["commodity"], {})
            return self.desk.plan({"crew_enabled": q.get("crew_enabled", False),
                "carrier_mean_price": row.get("mean_price") or 0, "carrier_mean_source":"Ardent / EDDN", "carrier_mean_at":row.get("mean_price_at") or "",
                "crew_load_percent": q.get("crew_load_percent", 25), "crew_unload_percent": q.get("crew_unload_percent", 25),
                "source_market_id": buy["market_id"], "destination_market_id": sell["market_id"],
                "carrier_market_id": self.desk.data["carrier_id"], "planned_quantity": row["quantity"], "commodity": row["commodity"], "mode": "load" if loading else "unload",
                "target": row["stock"] + row["quantity"] if loading else max(0, row["stock"] - row["quantity"]),
                "source": f"{buy['station']} / {buy['system']}" if buy else "Carrier stock",
                "destination": f"{sell['station']} / {sell['system']}" if sell else result["context"]["callsign"] or "Carrier",
                "source_price": buy["price"] if buy else 0, "destination_price": sell["price"] if sell else 0,
                "carrier_price": order.get("price", 0), "carrier_price_known": bool(order.get("active") and order.get("side") == ("buy" if loading else "sell")),
                "price_basis": "known" if buy and sell else "unknown acquisition" if not buy else "unknown resale"})
