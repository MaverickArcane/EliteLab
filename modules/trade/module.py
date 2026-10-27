"""A carrier ledger: orders are commitments, never cargo already in storage.

Stock is partial evidence, not a full inventory API. Absolute stock comes from
an owner reconciliation or SaleOrder; observed local transfers adjust it.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode

from elitelab.core.gamedata import norm
from elitelab.core.watcher import journal_files
from modules.trade.market import MarketProfiles, PROFILES, stamp as timestamp_seconds
from modules.trade.profit import split_profit, preview
from modules.trade.operations import Operations, operation_view, ACTIVE
from modules.trade.workload import Workloads
from modules.trade.audit import Diagnostics

NS = "trade"


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def number(value, label, maximum=10**12):
    try:
        n = float(value)
        if isinstance(value, bool) or not math.isfinite(n) or n < 0 or n > maximum or n != int(n):
            raise ValueError()
        return int(n)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{label} must be a whole number from 0 to {maximum}.") from None


def text(value, label, required=False):
    if not isinstance(value, str) or len(value) > 160 or (required and not value.strip()):
        raise ValueError(f"{label} must be {'non-empty ' if required else ''}text, up to 160 characters.")
    return value.strip()


class Trade:
    def __init__(self, core, archive=False):
        self.core = core
        self.archive = archive
        self.lock = threading.RLock()
        self.data = {} if archive else (core.read_data("trade.json", default={}) or {})
        for k, v in {"carrier_id": None, "inventory": {}, "orders": {}, "markets": {}, "plan": None, "operation": None, "seen": []}.items():
            self.data.setdefault(k, v)
        self.data.setdefault("baselines", {k: copy.deepcopy(v) for k, v in self.data["inventory"].items() if v.get("source") == "manual count"})
        self.docked_id = None
        self.inventory_scan = "idle"
        if archive:
            return
        core.bus.on("journal.*", self.event)
        core.bus.on("state.journal.cargo", lambda n, v: self.publish())
        core.bus.on("state.journal.cargo_capacity", lambda n, v: self.publish())
        core.bus.on("state.powerplay.power", lambda n, v: self.publish())
        core.bus.on("state.powerplay.rank", lambda n, v: self.publish())
        core.bus.on("journal.replay.done", self.backfill)
        self.publish()

    def commit(self, candidate):
        if not self.archive:
            self.core.write_data(candidate, "trade.json")
        self.data = candidate
        self.publish()

    def publish(self):
        if self.archive:
            return
        with self.lock:
            state = {k: copy.deepcopy(v) for k, v in self.data.items() if k not in ("seen", "markets", "baselines")}
            state["market_count"] = len(self.data["markets"])
            state["operation"] = operation_view(self.data.get("operation"))
            if state.get("previous_operation"):
                state["previous_operation"]["operation"] = operation_view(self.data["previous_operation"]["operation"])
            state["calculation"] = self.calculate()
            state["buy_commitment"] = sum(o["quantity"] * o["price"] for o in self.data["orders"].values() if o["side"] == "buy")
            state["inventory_scan"] = self.inventory_scan
            # Publish plan, stage and totals together. Party readers must never
            # combine the new plan with an old operation during an update.
            state["job"] = {"plan": copy.deepcopy(state.get("plan")),
                            "operation": copy.deepcopy(state["operation"]),
                            "workload": copy.deepcopy(state.get("workload")),
                            "calculation": copy.deepcopy(state["calculation"])}
            self.core.store.update(NS, state)

    def backfill(self, name, payload):
        with self.lock:
            if self.inventory_scan != "idle":
                return
            self.inventory_scan = "reading"
            self.publish()
        if self.core.watcher.is_alive():
            threading.Thread(target=self.scan_archive, name="trade-inventory-history", daemon=True).start()
        else:
            self.scan_archive()

    def scan_archive(self):
        """Rebuild chronologically, then merge with newer live/manual evidence.

        Replaying old snapshots straight into the live ledger cannot establish a
        missing baseline after a newer transfer; rebuild that timeline separately.
        """
        wanted = {"CarrierStats", "CarrierTradeOrder", "CargoTransfer", "MarketBuy", "MarketSell",
                  "Docked", "Undocked", "Location", "FSDJump", "CarrierJump", "LoadGame"}
        try:
            with self.lock:
                scan_cutoff = self.data.get("history_since")
            events = []
            for path in journal_files():
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            ev = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(ev, dict) and ev.get("event") in wanted and ev.get("timestamp"):
                            events.append(ev)
            events.sort(key=lambda e: e["timestamp"])
            owner = next((e.get("CarrierID") for e in reversed(events) if e["event"] == "CarrierStats" and e.get("CarrierID")), None)
            archive = Trade(self.core, archive=True)
            archive.data["carrier_id"] = owner
            archive.data["history_since"] = scan_cutoff
            def apply_baseline(key, baseline):
                archive.data["inventory"][key] = baseline
                order = archive.data["orders"].get(key)
                if order and order["side"] == "sell" and order.get("active", bool(order["quantity"])):
                    order.update(quantity=baseline["stock"], updated_at=baseline["updated_at"])
            with self.lock:
                baselines = sorted(copy.deepcopy(self.data["baselines"]).items(), key=lambda kv: kv[1]["updated_at"])
            for ev in events:
                while baselines and baselines[0][1]["updated_at"] <= ev["timestamp"]:
                    key, baseline = baselines.pop(0)
                    apply_baseline(key, baseline)
                archive.event("journal." + ev["event"], ev)
            for key, baseline in baselines:
                apply_baseline(key, baseline)
            with self.lock:
                candidate = copy.deepcopy(self.data)
                if candidate.get("history_since") != scan_cutoff:
                    self.inventory_scan = "ready"
                    self.publish()
                    return
                if candidate["carrier_id"] in (None, archive.data["carrier_id"]):
                    candidate["carrier_id"] = archive.data["carrier_id"] or candidate["carrier_id"]
                    for section in ("inventory", "orders"):
                        for key, value in archive.data[section].items():
                            previous = candidate[section].get(key, {})
                            newer = value.get("updated_at", "") > previous.get("updated_at", "")
                            same_unknown = value.get("updated_at", "") == previous.get("updated_at", "") and previous.get("stock") is None
                            if newer or same_unknown:
                                candidate[section][key] = value
                    candidate["seen"] = list(dict.fromkeys(archive.data["seen"] + candidate["seen"]))[-10000:]
                    self.inventory_scan = "ready"
                    self.commit(candidate)
                else:
                    self.inventory_scan = "carrier changed"
                    self.publish()
        except Exception:
            self.core.log.exception("Could not rebuild carrier inventory history")
            with self.lock:
                self.inventory_scan = "unavailable"
                self.publish()

    def calculate(self):
        p = self.data["plan"]
        if not p:
            return None
        key = p["commodity"]
        item = self.data["inventory"].get(key, {})
        stock = item.get("stock")
        cargo = self.core.store.get("journal", "cargo") or {}
        own = sum(i.get("count", 0) for i in cargo.get("items", []) if i.get("key") == key)
        cap = p["ship_capacity"] or self.core.store.get("journal", "cargo_capacity")
        remaining = None if stock is None else max(0, p["target"] - stock) if p["mode"] == "load" else max(0, stock - p["target"])
        committed = min(own, remaining) if remaining is not None and p["use_ship_cargo"] and p["mode"] == "load" else 0
        hauling = max(0, remaining - committed) if remaining is not None else None
        order = self.data["orders"].get(key, {})
        ordered = order.get("quantity", 0) if order.get("side") == ("buy" if p["mode"] == "load" else "sell") else 0
        market_sell = p["destination_price"] - (p.get("bonus_per_ton", 0) if p.get("price_includes_bonus") else 0)
        hauler_margin = p["carrier_price"] - p["source_price"] if p["mode"] == "load" else market_sell - p["carrier_price"]
        carrier_margin = market_sell - p["carrier_price"] if p["mode"] == "load" else p["carrier_price"] - p["source_price"]
        basis = p.get("price_basis", "known")
        if not p.get("carrier_price_known", True):
            hauler_margin = carrier_margin = None
        if basis == "unknown acquisition":
            if p["mode"] == "unload":
                carrier_margin = None
            else:
                hauler_margin = None
        elif basis == "unknown resale":
            if p["mode"] == "load":
                carrier_margin = None
            else:
                hauler_margin = None
        # Personal power rewards are not revenue earned by the carrier market.
        base = market_sell - p["source_price"] if basis == "known" else None
        power = self.core.store.get("powerplay")
        valid_bonus = p.get("bonus_context") == {k: power.get(k) for k in ("power", "rank")}
        bonus = p.get("bonus_per_ton", 0) if p.get("bonus_confirmed") and valid_bonus else 0
        split = None
        if p.get("crew_enabled") and basis == "known":
            split = split_profit(p["source_price"], market_sell, p.get("planned_quantity") or hauling,
                                 p["crew_load_percent"], p["crew_unload_percent"])
            carrier_margin = split["owner_per_ton"]
        return {"profit_split": split, "stock": stock, "own_cargo": own, "own_committed": committed, "remaining": remaining,
                "to_haul": hauling, "ordered": ordered, "uncovered": max(0, hauling - ordered) if hauling is not None else None,
                "runs": math.ceil(hauling / cap) if hauling is not None and cap else None,
                "capacity": cap, "next_load": min(hauling, max(0, cap - (cargo.get("count") or 0))) if hauling is not None and cap else None,
                "hauler_margin": hauler_margin, "carrier_margin": carrier_margin,
                "self_margin": base,
                "personal_bonus": bonus, "personal_margin": base + bonus if base is not None else None,
                "bonus_context_valid": valid_bonus,
                "personal_per_run": (base + bonus) * cap if cap and base is not None else None,
                "estimated_carrier_profit": split["owner_profit"] if split else hauling * carrier_margin if hauling is not None and carrier_margin is not None else None}

    def plan(self, q):
        if self.core.store.get("party", "mode") == "member":
            raise ValueError("Leave the party to create a separate carrier plan.")
        p = {k: text(q.get(k, ""), k, k == "commodity") for k in ("commodity", "source", "destination")}
        p["commodity"] = norm(p["commodity"])
        for field in ("source_market_id", "destination_market_id", "carrier_market_id"):
            p[field] = number(q.get(field, 0) or (self.data["carrier_id"] if field == "carrier_market_id" else 0) or 0, field)
        p["mode"] = q.get("mode", "load")
        if p["mode"] not in ("load", "unload"):
            raise ValueError("Choose load or unload.")
        for k in ("target", "ship_capacity", "source_price", "carrier_price", "destination_price", "bonus_per_ton"):
            p[k] = number(q.get(k, 0), k)
        if not isinstance(q.get("use_ship_cargo", False), bool):
            raise ValueError("use_ship_cargo must be true or false.")
        p["use_ship_cargo"] = q.get("use_ship_cargo", False)
        p["price_basis"] = q.get("price_basis", "known")
        if p["price_basis"] not in ("known", "unknown acquisition", "unknown resale"):
            raise ValueError("Invalid price basis.")
        if not isinstance(q.get("carrier_price_known", True), bool):
            raise ValueError("carrier_price_known must be true or false.")
        p["carrier_price_known"] = q.get("carrier_price_known", True)
        for k in ("bonus_confirmed", "price_includes_bonus"):
            if not isinstance(q.get(k, False), bool):
                raise ValueError(k + " must be true or false.")
            p[k] = q.get(k, False)
        if p["price_includes_bonus"] and p["bonus_per_ton"] > p["destination_price"]:
            raise ValueError("An included bonus cannot exceed the entered sell price.")
        power = self.core.store.get("powerplay")
        p["bonus_context"] = {k: power.get(k) for k in ("power", "rank")}
        if not isinstance(q.get("crew_enabled", False), bool):
            raise ValueError("crew_enabled must be true or false.")
        p["crew_enabled"] = q.get("crew_enabled", False)
        p["planned_quantity"] = number(q.get("planned_quantity", 0), "Planned quantity", 1000000)
        p["crew_load_percent"] = number(q.get("crew_load_percent", 25), "Loading share", 100)
        p["crew_unload_percent"] = number(q.get("crew_unload_percent", 25), "Unloading share", 100)
        if p["crew_enabled"]:
            if p["price_basis"] != "known":
                raise ValueError("Both station prices must be known to calculate crew order prices.")
            sell = p["destination_price"] - (p["bonus_per_ton"] if p["price_includes_bonus"] else 0)
            p["crew_split"] = split_profit(p["source_price"], sell, p["planned_quantity"] or None,
                                          p["crew_load_percent"], p["crew_unload_percent"])
            p["carrier_price"] = p["crew_split"]["carrier_buy_price" if p["mode"] == "load" else "carrier_sell_price"]
            p["carrier_price_known"] = True
        with self.lock:
            d = copy.deepcopy(self.data)
            if (d.get("operation") or {}).get("stage") in ACTIVE:
                raise ValueError("Finish or cancel the active trade before changing its route or prices.")
            if d.get("operation"):
                d["previous_operation"] = {"operation": d["operation"], "plan": d.get("plan"), "workload": d.get("workload")}
                d["operation"] = None
            d["plan"] = p
            d["workload"] = None
            self.commit(d)
            return self.core.store.get(NS)

    def reset_inventory(self, q):
        keep = q.get("keep_tritium", False)
        if not isinstance(keep, bool):
            raise ValueError("keep_tritium must be true or false.")
        with self.lock:
            self.core.write_data({k: copy.deepcopy(self.data.get(k)) for k in ("inventory", "orders", "baselines", "history_since")}, "trade-ledger-before-reset.json")
            data = copy.deepcopy(self.data)
            cutoff = now()
            data.update(inventory={}, orders={}, baselines={}, history_since=cutoff)
            if keep:
                row = {"name": "Tritium", "stock": None, "source": "quantity not checked after reset", "updated_at": cutoff}
                data["inventory"]["tritium"] = row
                data["baselines"]["tritium"] = copy.deepcopy(row)
            self.commit(data)
            return self.core.store.get(NS)

    def reconcile(self, q):
        key = norm(text(q.get("commodity", ""), "Commodity", True))
        stock = number(q.get("stock"), "Stock", 1000000)
        with self.lock:
            d = copy.deepcopy(self.data)
            d["inventory"][key] = {"name": text(q.get("name", key), "Name"), "stock": stock, "source": "manual count", "updated_at": now()}
            d["baselines"][key] = copy.deepcopy(d["inventory"][key])
            order = d["orders"].get(key)
            if order and order["side"] == "sell" and order.get("active", bool(order["quantity"])):
                order.update(quantity=stock, updated_at=now())
            self.commit(d)
            return self.core.store.get(NS)

    def event(self, name, ev):
        if not isinstance(ev, dict):
            return
        e = ev.get("event")
        with self.lock:
            if e in ("Docked", "Location", "CarrierJump"):
                self.docked_id = ev.get("MarketID") if e == "Docked" or ev.get("Docked") else None
            elif e in ("Undocked", "FSDJump", "LoadGame"):
                self.docked_id = None
            if e not in ("CarrierStats", "CarrierTradeOrder", "CargoTransfer", "MarketBuy", "MarketSell") and name != "journal.file.Market":
                return
            stamp = ev.get("timestamp", "")
            if not stamp:
                return
            if e in ("CarrierTradeOrder", "CargoTransfer", "MarketBuy", "MarketSell") and self.data.get("history_since") and timestamp_seconds(stamp) <= timestamp_seconds(self.data["history_since"]):
                return
            digest = hashlib.sha256(json.dumps({k: v for k, v in ev.items() if not k.startswith("_")}, sort_keys=True).encode()).hexdigest()
            if digest in self.data["seen"]:
                return
            d = copy.deepcopy(self.data)
            if e == "CarrierStats":
                cid = ev.get("CarrierID")
                if not cid:
                    return
                if d["carrier_id"] and cid != d["carrier_id"]:
                    return  # Never mix another carrier into a saved ledger.
                d["carrier_id"] = cid
            elif name == "journal.file.Market":
                mid = str(ev.get("MarketID") or "")
                old = d["markets"].get(mid, {})
                if not mid or stamp <= old.get("timestamp", ""):
                    return
                d["markets"][mid] = {"market_id": ev["MarketID"], "station": ev.get("StationName"), "system": ev.get("StarSystem"),
                    "timestamp": stamp, "items": [{"key": norm(i.get("Name")), "name": i.get("Name_Localised") or norm(i.get("Name")),
                    "buy": i.get("BuyPrice", 0), "sell": i.get("SellPrice", 0), "stock": i.get("Stock", 0), "demand": i.get("Demand", 0)} for i in ev.get("Items", [])]}
                d["markets"] = dict(sorted(d["markets"].items(), key=lambda kv: kv[1]["timestamp"])[-100:])
            elif e == "CarrierTradeOrder":
                if ev.get("BlackMarket") or (d["carrier_id"] and ev.get("CarrierID") != d["carrier_id"]):
                    return
                d["carrier_id"] = ev.get("CarrierID") or d["carrier_id"]
                key = norm(ev.get("Commodity"))
                old = d["orders"].get(key, {})
                if stamp < old.get("updated_at", ""):
                    return
                side = "buy" if "PurchaseOrder" in ev else "sell"
                qty = ev.get("PurchaseOrder", ev.get("SaleOrder", 0))
                d["orders"][key] = {"name": ev.get("Commodity_Localised") or key, "side": side, "quantity": 0 if ev.get("CancelTrade") else qty,
                    "price": ev.get("Price", 0), "updated_at": stamp, "source": "journal order", "active": not ev.get("CancelTrade", False)}
                if "SaleOrder" in ev and stamp >= d["inventory"].get(key, {}).get("updated_at", ""):
                    d["inventory"][key] = {"name": ev.get("Commodity_Localised") or key, "stock": qty, "source": "sale order stock", "updated_at": stamp}
            else:
                mid = ev.get("MarketID", self.docked_id)
                if not d["carrier_id"] or mid != d["carrier_id"]:
                    return
                changes = ev.get("Transfers", []) if e == "CargoTransfer" else [{"Type": ev.get("Type"), "Count": ev.get("Count", 0), "Direction": "tocarrier" if e == "MarketSell" else "toship"}]
                for change in changes:
                    direction = change.get("Direction")
                    if direction not in ("tocarrier", "toship"):
                        continue
                    key = norm(change.get("Type"))
                    row = d["inventory"].setdefault(key, {"name": key, "stock": None})
                    if stamp < row.get("updated_at", ""):
                        continue
                    delta = change.get("Count", 0) * (1 if direction == "tocarrier" else -1)
                    if row["stock"] is not None:
                        result = row["stock"] + delta
                        row["stock"] = result if result >= 0 else None
                    row.update(source="observed local transfers", updated_at=stamp)
                    order = d["orders"].get(key)
                    if order and stamp >= order["updated_at"] and order.get("active", bool(order["quantity"])):
                        if order["side"] == "sell":
                            # SaleOrder is current stock, not a separate reserved allocation.
                            order.update(quantity=max(0, order["quantity"] + delta), updated_at=stamp)
                        elif e == "MarketSell":
                            order.update(quantity=max(0, order["quantity"] - abs(delta)), updated_at=stamp)
            d["seen"] = (d["seen"] + [digest])[-10000:]
            self.commit(d)

    def spots(self, q):
        key = norm(text(q.get("commodity", ""), "Commodity", True))
        max_distance = number(q.get("max_route_distance", 500), "Maximum route distance", 100000)
        if q.get("source", "observed") == "community":
            return self.routes(self.community_spots(key, q), max_distance)
        with self.lock:
            rows = [{**{k: v for k, v in m.items() if k != "items"}, **i} for m in self.data["markets"].values()
                    if m["market_id"] != self.data["carrier_id"] for i in m["items"] if i["key"] == key]
        return self.routes({"buy": sorted([r for r in rows if r["buy"] > 0 and r["stock"] > 0], key=lambda r: r["buy"])[:15],
                "sell": sorted([r for r in rows if r["sell"] > 0 and r["demand"] > 0], key=lambda r: -r["sell"])[:15],
                "source": "Markets opened by this commander; prices, stock and demand are last observed, not live."}, max_distance)

    @staticmethod
    def routes(result, max_distance=500):
        candidates = []
        for buy in result["buy"]:
            for sell in result["sell"]:
                if buy["market_id"] == sell["market_id"] or sell["sell"] <= buy["buy"]:
                    continue
                distance = math.dist(buy["star_pos"], sell["star_pos"]) if buy.get("star_pos") and sell.get("star_pos") else None
                if max_distance and distance is not None and distance > max_distance:
                    continue
                spread = sell["sell"] - buy["buy"]
                volume = min(buy["stock"], sell["demand"])
                candidates.append({"commodity": buy["key"], "buy": buy, "sell": sell, "profit_per_ton": spread,
                    "margin_percent": round(100 * spread / buy["buy"], 1), "volume": volume, "gross_profit": spread * volume,
                    "distance": round(distance, 1) if distance is not None else None})
        result["routes"] = sorted(candidates, key=lambda r: (-r["profit_per_ton"], -r["volume"]))[:8]
        return result

    def community_spots(self, key, q):
        volume = max(1, number(q.get("min_volume", 1), "Minimum volume", 1000000))
        days = max(1, number(q.get("max_days", 3), "Maximum age in days", 30))
        pad = q.get("pad", "L")
        if pad not in ("L", "M", "S"):
            raise ValueError("Choose L, M or S for landing pad size.")
        if self.core.config.OFFLINE:
            raise ValueError("Community search is unavailable in offline mode. Choose Remembered markets.")
        pos = self.core.store.get("journal", "star_pos")
        qs = urlencode({"minVolume": volume, "maxDaysAgo": days, "fleetCarriers": 0})
        base = "https://api.ardent-insight.com/v2/commodity/name/" + quote(key, safe="")

        def fetch(side):
            raw = self.core.services.fetch_json(base + ("/exports?" if side == "buy" else "/imports?") + qs, ttl=300)
            if not isinstance(raw, list):
                raise ValueError("Unexpected market response.")
            rows = []
            for r in raw[:100]:
                if (r.get("maxLandingPadSize") or 0) < {"L": 3, "M": 2, "S": 1}[pad] or r.get("stationType") == "FleetCarrier":
                    continue
                price = r.get("buyPrice" if side == "buy" else "sellPrice") or 0
                quantity = r.get("stock" if side == "buy" else "demand") or 0
                if price <= 0 or quantity < volume:
                    continue
                try:
                    updated = datetime.fromisoformat(r["updatedAt"].replace("Z", "+00:00"))
                    if (datetime.now(timezone.utc) - updated).total_seconds() > days * 86400:
                        continue
                except (KeyError, ValueError, TypeError):
                    continue
                xyz = [r.get("system" + axis) for axis in "XYZ"]
                distance = round(math.dist(pos, xyz), 1) if pos and all(isinstance(n, (int, float)) for n in xyz) else None
                rows.append({"key": key, "market_id": r.get("marketId"), "station": r.get("stationName"), "system": r.get("systemName"),
                    "buy": r.get("buyPrice", 0), "sell": r.get("sellPrice", 0), "stock": r.get("stock", 0), "demand": r.get("demand", 0),
                    "timestamp": r.get("updatedAt"), "distance": distance, "arrival_ls": r.get("distanceToArrival"),
                    "pad": {1: "S", 2: "M", 3: "L"}.get(r.get("maxLandingPadSize")), "type": r.get("stationType"),
                    "star_pos": xyz if all(isinstance(n, (int, float)) for n in xyz) else None})
            return sorted(rows, key=lambda r: r[side] if side == "buy" else -r[side])[:15]

        result = {"buy": [], "sell": [], "warnings": []}
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = {side: pool.submit(fetch, side) for side in ("buy", "sell")}
            for side, future in pending.items():
                try:
                    result[side] = future.result()
                except Exception:
                    result["warnings"].append(f"Could not retrieve {side} quotes. Try again or use remembered markets.")
        result["source"] = f"Ardent / EDDN community reports, cached 5 minutes. Best reported markets (up to 100 per side before pad filtering), within {days} days. Confirm prices and volume on arrival."
        return result


def setup(core, module):
    desk = Trade(core)
    profiles = MarketProfiles(core, desk)
    operations = Operations(core, desk)
    module.operations = operations
    diagnostics = Diagnostics(core, desk)
    core.http.route("/api/trade/correct", operations.correct, method="POST", tool="correct_hauling_delivery", module=module.name,
        description="Owner corrects a commander's credited loading/unloading total with a reason. Preserves raw cumulative reports, survives retries/reconnects, and records a visible audit entry. Requires current credited and reported totals; stale edits are rejected. Does not change in-game cargo.",
        params={"id":{"type":"string","required":True}, "member":{"type":"string","required":True},
                "phase":{"type":"string","required":True}, "tonnes":{"type":"integer","required":True},
                "expected":{"type":"integer","required":True}, "expected_reported":{"type":"integer","required":True},
                "reason":{"type":"string","required":True}, "request_id":{"type":"string","required":True}})
    core.http.route("/api/trade/diagnostics", diagnostics.export, tool="export_hauling_diagnostics", module=module.name,
        description="Export local hauling diagnostics for the current or most recent job. Includes credited/raw totals, corrections, quotas and retained history; anonymizes commanders and omits credentials, addresses, notes, reasons, full journals, credits and file paths. Members export only their latest shared history. Nothing is uploaded.")
    workloads = Workloads(core, desk)
    core.http.route("/api/trade/workload", workloads.configure, method="POST", tool="configure_trade_workload", module=module.name,
        description="Owner previews or applies equal-tonnage/custom-weight quotas per commander. Owner participation excludes direct transfers from carrier market orders. Rebalancing distributes remaining work without deleting deliveries. Apply requires the basis returned by preview. No in-game orders are placed.",
        params={"action": {"type": "string", "default": "preview"}, "mode": {"type": "string", "default": "equal"},
                "owner_hauls": {"type": "boolean", "default": True}, "shares": {"type": "object"}, "basis": {"type": "string"}})
    core.http.route("/api/trade/profit", preview, method="POST", tool="preview_trade_profit", module=module.name,
        description="Preview crew splits and carrier prices for up to 100 route price rows using the same rules as saved operations. No state changes. Quantity null means unknown.",
        params={"rows": {"type": "array", "required": True}, "loading": {"type": "integer", "default": 25}, "unloading": {"type": "integer", "default": 25}})
    core.http.route("/api/trade/operation", operations.control, method="POST", tool="manage_carrier_operation", module=module.name,
        description="Owner controls the saved team trade: start, pause, resume, depart, unload, complete, cancel, notes. Depart/unload/complete are explicit owner stage confirmations; reported counts remain evidence, never invented inventory. Existing operation actions require its id. Only the local carrier owner can control stages.",
        params={"action": {"type": "string", "required": True}, "id": {"type": "string"}, "notes": {"type": "string"}})
    module.trade = desk
    module.profiles = profiles
    core.http.route("/api/trade/profiles", lambda q: {"profiles": PROFILES, "context": profiles.context()}, tool="get_trade_profiles", module=module.name,
        description="Trade profiles and their live carrier context: observed inventory, buy orders, free space, ship capacity and reference system. Inventory is partial journal evidence.")
    core.http.route("/api/trade/opportunities", profiles.query, tool="find_carrier_opportunities", module=module.name,
        description="Find paired buy/sell routes from Ardent/EDDN reports. For each high-paying buyer, choose the cheapest supplier within route_distance Ly, then rank by spread per ton. Radius limits BOTH stops from the carrier reference system. Unknown route distances are excluded. Broad search screens up to breadth catalog candidates; commodity selects one. Reports are capped at 100 quotes per side, not an exhaustive galaxy search. Unreserved plus buy-order-reserved capacity sizes replacement loads; cancel old orders in game. Unknown/full capacity still permits browsing. Cached five minutes.",
        params={"commodity": {"type": "string"}, "hours": {"type": "integer", "default": 6},
                "radius": {"type": "integer", "default": 100}, "route_distance": {"type": "integer", "default": 100},
                "min_volume": {"type": "integer", "default": 0, "description": "0 automatically requires supply and demand for all reported carrier free space; a positive value overrides the minimum tons."}, "sell_percent": {"type": "integer", "default": 80},
                "breadth": {"type": "integer", "default": 24}, "arrival": {"type": "integer", "default": 10000},
                "pad": {"type": "string", "default": "L"}})
    core.http.route("/api/trade/select", profiles.select, method="POST", tool="select_carrier_opportunity", module=module.name,
        description="Save a trade operation from a fresh opportunity ID using observed quantities and prices. Rechecks inventory context and rejects unknown stock or expired results. Does not place in-game orders.",
        params={"id": {"type": "string", "required": True}, "stock": {"type": "integer", "description": "Explicit current physical count when existing stock is unknown or conflicting."}, "crew_enabled": {"type": "boolean", "default": False},
                "crew_load_percent": {"type": "integer", "default": 25}, "crew_unload_percent": {"type": "integer", "default": 25}})
    core.http.route("/api/trade", lambda q: core.store.get(NS), tool="get_carrier_trade", module=module.name,
        description="Carrier stock evidence, outstanding market orders, persisted operation plan and run calculations. Unknown stock stays null; orders are not inventory.")
    core.http.route("/api/trade/plan", desk.plan, method="POST", tool="plan_carrier_trade", module=module.name,
        description="Save a load/unload plan. Target is desired stock remaining aboard the carrier. Prices are Cr/t estimates, excluding expenses; capacity 0 uses your ship. Does not place in-game orders.",
        params={**{k: {"type": "string", "description": k, "required": k == "commodity"} for k in ("commodity", "source", "destination", "mode")},
                **{k: {"type": "integer", "description": k, "default": 0} for k in ("target", "ship_capacity", "source_price", "carrier_price", "destination_price", "bonus_per_ton")},
                **{k: {"type": "integer", "default": 0, "description": "Verified market ID for automatic crew delivery matching; 0 is unknown."} for k in ("source_market_id", "destination_market_id", "carrier_market_id")},
                "crew_enabled": {"type": "boolean", "default": False, "description": "Derive both carrier order prices from station prices and the crew shares. Excludes personal bonuses."},
                "crew_load_percent": {"type": "integer", "default": 25, "description": "Percent of route spread paid to loading haulers."},
                "crew_unload_percent": {"type": "integer", "default": 25, "description": "Percent paid to unloading haulers; both shares together must not exceed 100."},
                "planned_quantity": {"type": "integer", "default": 0, "description": "Full operation tonnage for profit totals; 0 uses remaining hauling quantity."},
                "price_basis": {"type": "string", "enum": ["known", "unknown acquisition", "unknown resale"], "default": "known"},
                "carrier_price_known": {"type": "boolean", "default": True},
                "bonus_confirmed": {"type": "boolean", "default": False, "description": "Only enable after verifying your personal bonus for the power, rank, commodity and destination."},
                "price_includes_bonus": {"type": "boolean", "default": False, "description": "True if the sell price already includes the personal bonus; prevents adding it twice."},
                "use_ship_cargo": {"type": "boolean", "default": False, "description": "Deduct your matching cargo from new loading work; does not deduct it from outstanding orders."}})
    core.http.route("/api/trade/reset-inventory", desk.reset_inventory, method="POST", tool="reset_carrier_inventory", module=module.name,
        description="Forget carrier commodity counts and market orders, retaining a backup and a cutoff so older journal history cannot recreate them. Does not change the game, saved plans or operations. Optionally retain tritium with an unknown quantity.",
        params={"keep_tritium": {"type": "boolean", "default": False}})
    core.http.route("/api/trade/reconcile", desk.reconcile, method="POST", tool="reconcile_carrier_stock", module=module.name,
        description="Set the current physical stock of ONE commodity after checking the carrier in game. Never enter outstanding buy orders as stock. Replaces older stock evidence.",
        params={"commodity": {"type": "string", "required": True}, "stock": {"type": "integer", "required": True}, "name": {"type": "string"}})
    core.http.route("/api/trade/spots", desk.spots, tool="find_trade_spots", module=module.name,
        description="Find buy/sell stops using remembered local markets (default source=observed) or Ardent/EDDN community reports (source=community). Community mode filters by pad, age and volume, excludes fleet carriers, and returns up to 15 per side from the best 100 quotes. Prices are observations, not live guarantees.",
        params={"commodity": {"type": "string", "required": True}, "source": {"type": "string", "enum": ["observed", "community"], "default": "observed"},
                "pad": {"type": "string", "enum": ["L", "M", "S"], "default": "L"}, "min_volume": {"type": "integer", "default": 1}, "max_days": {"type": "integer", "default": 3},
                "max_route_distance": {"type": "integer", "default": 500, "description": "Maximum distance between paired buy/sell systems in Ly. 0 is unlimited; unknown distances remain explicitly unknown."}})
