"""Conservative attribution of refinery units to later journal sales.

Frontier Journal v34: MarketSell.TotalSale, BuyDrones.TotalCost, station service
Cost, and CargoTransfer.Transfers. Other cargo is consumed before mined units;
without a cargo baseline this is an estimate, never a claim of exact provenance.
"""
import math

from elitelab.core.gamedata import norm


def number(value, maximum=10**15):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= maximum else None
    except OverflowError:
        return None


def count(value):
    n = number(value, 1000000)
    return int(n) if n is not None and n == int(n) else 0


def key(value):
    return norm(value.strip()[:160]) if isinstance(value, str) else ""


class Ledger:
    COSTS = {"BuyDrones": ("Limpets", "TotalCost"), "BuyAmmo": ("Ammunition", "Cost"),
             "RefuelAll": ("Fuel", "Cost"), "RefuelPartial": ("Fuel", "Cost"),
             "Repair": ("Repairs", "Cost"), "RepairAll": ("Repairs", "Cost")}

    def __init__(self):
        self.stock = {}
        self.baseline = False
        self.estimated = False
        self.revenue = self.sold = self.removed = self.unknown_sale_tons = 0
        self.costs = {}
        self.transactions = []
        self.last_inventory_ts = None

    def row(self, name):
        if not name or (name not in self.stock and len(self.stock) >= 256):
            self.estimated = True
            return None
        return self.stock.setdefault(name, {"mined": 0, "other": 0})

    def record(self, ev, label, credits, tons=0):
        self.transactions.insert(0, {"timestamp": str(ev.get("timestamp") or "")[:80],
                                    "label": label[:160], "credits": round(credits, 2), "tons": tons})
        del self.transactions[12:]

    def consume(self, name, quantity):
        row = self.row(name)
        if not row:
            return 0
        other = min(row["other"], quantity)
        row["other"] -= other
        mined = min(row["mined"], quantity - other)
        row["mined"] -= mined
        return mined

    def event(self, ev, ts):
        event = ev.get("event")
        name = key(ev.get("Type"))
        if event == "Cargo" and isinstance(ev.get("Inventory"), list) and ev.get("Vessel", "Ship") == "Ship":
            # Cargo.json is a latest snapshot, not historical replay evidence.
            if ts is None or (self.last_inventory_ts is not None and ts < self.last_inventory_ts):
                return
            totals = {}
            for item in ev["Inventory"][:256]:
                if isinstance(item, dict) and key(item.get("Name")):
                    k = key(item["Name"])
                    totals[k] = totals.get(k, 0) + count(item.get("Count"))
            for k in set(self.stock) | set(totals):
                row = self.row(k)
                if row is None:
                    continue
                available = totals.get(k, 0)
                if row["mined"] + row["other"] > available:
                    # Unexplained loss: remove mined units first, never invent proceeds.
                    loss = min(row["mined"], row["mined"] + row["other"] - available)
                    row["mined"] -= loss
                    self.removed += loss
                    if loss:
                        self.estimated = True
                row["other"] = max(0, available - row["mined"])
                if row["mined"] and row["other"]:
                    self.estimated = True
            self.baseline = True
            self.last_inventory_ts = ts
            return
        if event == "MiningRefined":
            row = self.row(name)
            if row is not None:
                row["mined"] += 1
            if not self.baseline:
                self.estimated = True
        elif event in ("MarketBuy", "CollectCargo"):
            row = self.row(name)
            if row is not None:
                row["other"] += count(ev.get("Count", 1 if event == "CollectCargo" else 0))
        elif event in ("MarketSell", "EjectCargo"):
            quantity = count(ev.get("Count"))
            matched = self.consume(name, quantity)
            if event == "MarketSell" and matched:
                total = number(ev.get("TotalSale"))
                if total is None and number(ev.get("SellPrice")) is not None:
                    total = ev["SellPrice"] * quantity
                self.sold += matched
                if total is None:
                    self.unknown_sale_tons += matched
                else:
                    proceeds = total * matched / quantity
                    self.revenue += proceeds
                    self.record(ev, "Sale: " + name, proceeds, matched)
            elif event == "EjectCargo":
                self.removed += matched
        elif event == "CargoTransfer" and isinstance(ev.get("Transfers"), list):
            for transfer in ev["Transfers"][:256]:
                if not isinstance(transfer, dict):
                    continue
                k, quantity = key(transfer.get("Type")), count(transfer.get("Count"))
                if transfer.get("Direction") == "toship":
                    row = self.row(k)
                    if row is not None:
                        row["other"] += quantity
                elif transfer.get("Direction") in ("tocarrier", "tosrv"):
                    self.removed += self.consume(k, quantity)
        elif event == "CargoDepot":
            k, quantity = key(ev.get("CargoType")), count(ev.get("Count"))
            if ev.get("UpdateType") == "Deliver":
                self.removed += self.consume(k, quantity)
            elif ev.get("UpdateType") == "Collect":
                row = self.row(k)
                if row is not None:
                    row["other"] += quantity
        elif event == "Died":
            self.removed += sum(r["mined"] for r in self.stock.values())
            self.stock.clear()
            self.baseline = True
        elif event in self.COSTS:
            label, field = self.COSTS[event]
            cost = number(ev.get(field))
            if cost is not None:
                self.costs[label] = self.costs.get(label, 0) + cost
                self.record(ev, label, -cost)
        elif event == "SellDrones":
            refund = number(ev.get("TotalSale"))
            if refund is not None:
                self.costs["Limpets"] = self.costs.get("Limpets", 0) - refund
                self.record(ev, "Limpet refund", refund)
        if event in ("MiningRefined", "MarketBuy", "MarketSell", "CollectCargo", "EjectCargo", "CargoTransfer", "CargoDepot", "Died"):
            if ts is not None:
                self.last_inventory_ts = max(ts, self.last_inventory_ts or ts)
        if any(r["mined"] and r["other"] for r in self.stock.values()):
            self.estimated = True

    def summary(self):
        costs = sum(self.costs.values())
        return {"sale_proceeds": round(self.revenue, 2), "sold_tons": self.sold,
                "operating_costs": round(costs, 2), "net_profit": round(self.revenue - costs, 2),
                "cost_breakdown": dict(self.costs), "estimated": self.estimated,
                "unknown_sale_tons": self.unknown_sale_tons, "removed_tons": self.removed,
                "remaining": {k: r["mined"] for k, r in self.stock.items() if r["mined"]},
                "transactions": list(self.transactions),
                "note": "Sales attributed to tracked refinery units; other cargo is sold first. Missing initial cargo makes attribution estimated. "
                        "Net subtracts this game session's recorded limpets, fuel, repairs and ammo, including other activities. "
                        "Transfers/ejection remove tracked units; returning cargo is not reclassified as mined. Unsold value is separate."}
