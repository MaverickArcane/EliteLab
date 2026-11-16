"""Observed Rhino collections, hold snapshots and transfers; no rig production estimates."""
import copy

from elitelab.core.gamedata import norm


def count(value):
    return value if type(value) is int and 0 <= value <= 1000000 else None


class Tracking:
    def __init__(self):
        self.run = None
        self.floor = None
        self.as_of = None
        self.ship_id = None
        self.capacity = None
        self.equipment = {"dss": None, "large_hangar": None}
        self.holds = {"Ship": {}, "SRV": {}}
        self.rhino_hold = False

    def start(self, timestamp, when, partial=False):
        self.floor = self.as_of = when
        self.rhino_hold = True
        self.holds["SRV"] = {}
        self.run = {"active": True, "started_at": timestamp, "started": when, "partial": partial,
                    "ended_at": None, "end_reason": None, "total_t": 0, "commodities": {},
                    "unloaded_t": 0, "unloads": 0, "points": [], "last_collection": None}

    def event(self, event, ev, when, snapshot=False):
        if when is None or (self.floor is not None and when < self.floor):
            return False
        if self.run and self.run["active"]:
            self.as_of = max(when, self.as_of or when)
        if event == "LoadGame":
            self.floor = when
            if ev.get("Ship") == "mev_rhino":
                self.start(ev.get("timestamp"), when, partial=True)
        if event == "Loadout":
            ship_id = (ev.get("Ship"), ev.get("ShipID"))
            if self.ship_id is not None and ship_id != self.ship_id:
                self.holds["Ship"] = {}
            self.ship_id = ship_id
            self.capacity = count(ev.get("CargoCapacity"))
            modules = ev.get("Modules")
            items = [str(m.get("Item", "")).lower() for m in modules if isinstance(m, dict)] if isinstance(modules, list) else None
            self.equipment = {"dss": any("detailedsurfacescanner" in i for i in items) if items is not None else None,
                              "large_hangar": any("largebuggybay" in i for i in items) if items is not None else None}
        elif event.startswith("Module") and event not in ("ModuleInfo", "ModulesInfo"):
            self.equipment = {"dss": None, "large_hangar": None}
            self.capacity = None
        elif event == "LaunchSRV" and ev.get("PlayerControlled") is not False:
            if ev.get("SRVType") == "mev_rhino":
                self.start(ev.get("timestamp"), when)
            else:
                self.end(ev, "Another SRV launched")
                self.rhino_hold = False
                self.holds["SRV"] = {}
        elif event in ("DockSRV", "Shutdown", "Died", "SupercruiseEntry", "StartJump", "FSDJump", "CarrierJump", "ShipyardSwap", "ShipyardBuy"):
            if event != "DockSRV" or ev.get("PlayerControlled") is not False:
                self.end(ev, event)
            if event in ("ShipyardSwap", "ShipyardBuy"):
                self.holds["Ship"] = {}
                self.capacity = None
                self.equipment = {"dss": None, "large_hangar": None}
        elif event == "Cargo":
            vessel = ev.get("Vessel")
            amount = count(ev.get("Count"))
            if vessel in self.holds and amount is not None and when >= self.holds[vessel].get("when", 0):
                # Cargo.json can still contain the pre-transfer report from this
                # second. Ordered journal Cargo rows remain authoritative.
                if not snapshot or when > self.holds[vessel].get("when", 0):
                    self.holds[vessel] = {"count": amount, "when": when, "observed_at": ev.get("timestamp"), "snapshot": snapshot}
        elif event == "CargoTransfer" and isinstance(ev.get("Transfers"), list):
            deltas = {"Ship": 0, "SRV": 0}
            carrier = bool(ev.get("CarrierID") or ev.get("MarketID"))
            vehicle = not carrier and self.run and self.run["active"]
            for row in ev["Transfers"]:
                if not isinstance(row, dict) or count(row.get("Count")) is None:
                    continue
                amount, direction = row["Count"], row.get("Direction")
                if direction == "toship":
                    deltas["Ship"] += amount
                    if vehicle:
                        deltas["SRV"] -= amount
                elif direction == "tosrv":
                    deltas["Ship"] -= amount
                    if vehicle:
                        deltas["SRV"] += amount
                elif direction == "tocarrier":
                    deltas["Ship"] -= amount
            for vessel, delta in deltas.items():
                hold = self.holds[vessel]
                if delta and hold.get("count") is not None and when >= hold["when"]:
                    # A file snapshot read ahead of the tail has no ordering
                    # within its second. Wait for another report if ambiguous.
                    amount = None if hold.get("snapshot") and when == hold["when"] else count(hold["count"] + delta)
                    self.holds[vessel] = {"count": amount, "when": when, "observed_at": ev.get("timestamp")}
        if self.run and self.run["active"] and when >= self.run["started"]:
            self.as_of = max(when, self.as_of or when)
            if event == "MiningRefined":
                key = norm(ev.get("Type", "")) if isinstance(ev.get("Type"), str) else ""
                if not key or (key not in self.run["commodities"] and len(self.run["commodities"]) >= 128):
                    return False
                rows = self.run["commodities"]
                label = ev.get("Type_Localised")
                row = rows.setdefault(key, {"id": key, "name": label[:160] if isinstance(label, str) and label else key.title(), "tonnes": 0})
                # Each MiningRefined is one tonne. Same-second rows are distinct receipts.
                row["tonnes"] += 1
                self.run["total_t"] += 1
                self.run["last_collection"] = {"name": row["name"], "timestamp": ev.get("timestamp")}
                points = self.run["points"]
                point = {"seconds": max(0, when - self.run["started"]), "tonnes": self.run["total_t"]}
                if points and points[-1]["seconds"] == point["seconds"]:
                    points[-1] = point
                else:
                    points.append(point)
                if len(points) > 240:
                    self.run["points"] = points[::2] + [points[-1]]
            elif event == "CargoTransfer" and isinstance(ev.get("Transfers"), list):
                # Carrier transfers have market IDs. Only vehicle-to-ship unloading counts.
                if ev.get("CarrierID") or ev.get("MarketID"):
                    return True
                amount = sum(count(r.get("Count")) or 0 for r in ev["Transfers"]
                             if isinstance(r, dict) and r.get("Direction") == "toship")
                if amount:
                    self.run["unloaded_t"] += amount
                    self.run["unloads"] += 1
        return True

    def end(self, ev, reason):
        if self.run and self.run["active"]:
            self.run.update(active=False, ended_at=ev.get("timestamp"), end_reason=reason)

    def view(self):
        run = copy.deepcopy(self.run)
        if run:
            run["elapsed_seconds"] = max(0, (self.as_of or run["started"]) - run.pop("started"))
            run["commodities"] = sorted(run["commodities"].values(), key=lambda row: (-row["tonnes"], row["id"]))
            run["average_tph"] = round(run["total_t"] * 3600 / run["elapsed_seconds"], 1) if run["elapsed_seconds"] >= 60 else None
        holds = {}
        for vessel, label, capacity in (("Ship", "ship", self.capacity), ("SRV", "rhino", 72)):
            known = self.holds[vessel] if vessel == "Ship" or self.rhino_hold else {}
            amount = known.get("count")
            holds[label] = {"count": amount, "capacity": capacity, "observed_at": known.get("observed_at"),
                            "free": max(0, capacity - amount) if capacity is not None and amount is not None else None}
        return {"session": run, "cargo": holds, "equipment": dict(self.equipment)}
