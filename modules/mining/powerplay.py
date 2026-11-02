"""Observed merit gains with conservative, explicitly temporal sale association.

PowerplayMerits supplies MeritsGained/TotalMerits but no sale identifier. Never
derive merits from credits or turn this association into confirmed causation.
The planner may disclose a conditional projection from matching recent evidence.
"""
from elitelab.core.gamedata import POWERS
from .ledger import count, key, number

# Other known earning events invalidate the pending sale, as do travel/death.
INTERRUPTS = {"Bounty", "FactionKillBond", "PVPKill", "PowerplayDeliver", "PowerplayCollect",
              "MultiSellExplorationData", "SellExplorationData", "SellOrganicData", "MissionCompleted",
              "SearchAndRescue", "DatalinkScan", "DataScanned", "SellMicroResources",
              "SupercruiseEntry", "SupercruiseDestinationDrop", "FSDJump", "CarrierJump", "Location", "Docked", "Undocked",
              "Died", "Resurrect", "CargoTransfer", "EjectCargo"}


class MiningPowerplay:
    def __init__(self):
        self.system = self.station = self.power_state = ""
        self.reset()

    def reset(self):
        self.power = None
        self.total = None
        self.session = self.associated = 0
        self.pending = None
        self.recent = []
        self.origins = {}

    def event(self, ev, ts, sold_delta, ledger):
        event = ev.get("event")
        if event in ("PowerplayJoin", "PowerplayDefect", "PowerplayLeave"):
            self.reset()
            power = ev.get("ToPower") if event == "PowerplayDefect" else ev.get("Power")
            self.power = power if isinstance(power, str) and power in POWERS and event != "PowerplayLeave" else None
            return
        if event == "Powerplay":
            power = ev.get("Power")
            power = power if isinstance(power, str) and power in POWERS else None
            if power != self.power:
                self.reset()
            self.power = power
            self.total = self.integer(ev.get("Merits"))
        if event in ("Location", "FSDJump", "CarrierJump", "Docked"):
            if self.system != self.label(ev.get("StarSystem")):
                self.power_state = ""
            self.system = self.label(ev.get("StarSystem"))
            self.station = self.label(ev.get("StationName"))
            if event != "Docked" or "PowerplayState" in ev:
                self.power_state = self.label(ev.get("PowerplayState"))
        if event == "MiningRefined":
            commodity = key(ev.get("Type"))
            origin = (self.system, self.power_state)
            if commodity in self.origins:
                if self.origins[commodity] != origin:
                    self.origins[commodity] = None
            elif len(self.origins) < 64:
                self.origins[commodity] = origin
        if event in ("CargoTransfer", "Died", "Resurrect"):
            # Never promote transferred/unknown cargo into a reusable forecast.
            self.origins = {k: None for k in self.origins}
        if event in INTERRUPTS:
            self.pending = None
        if event == "MarketSell":
            self.pending = None
            quantity = count(ev.get("Count"))
            # Mixed/unknown provenance is not enough evidence for mining attribution.
            if ts is not None and quantity and sold_delta == quantity and not ledger.estimated:
                origin = self.origins.get(key(ev.get("Type"))) or (None, None)
                proceeds = number(ev.get("TotalSale"))
                self.pending = {"time": ts, "commodity": key(ev.get("Type")), "tons": quantity,
                                "system": self.system, "station": self.station, "power_state": self.power_state,
                                "origin": origin[0], "origin_state": origin[1],
                                "price": proceeds / quantity if proceeds is not None else None}
        if event != "PowerplayMerits":
            return
        gained = self.integer(ev.get("MeritsGained"))
        event_power = ev.get("Power")
        if gained is not None and self.power is None and isinstance(event_power, str) and event_power in POWERS:
            self.power = event_power
        if gained is None or (event_power is not None and event_power != self.power):
            self.pending = None
            return
        sale, self.pending = self.pending, None
        associated = bool(gained and sale and ts is not None and 0 <= ts - sale["time"] <= 12)
        self.session += gained
        total = self.integer(ev.get("TotalMerits"))
        if total is not None:
            self.total = total
        if associated:
            self.associated += gained
        self.recent.insert(0, {"timestamp": self.label(ev.get("timestamp")), "gained": gained,
                               "sale_associated": associated,
                               "sale": {k:v for k,v in sale.items() if k != "time"} if associated else None})
        del self.recent[12:]

    @staticmethod
    def integer(value):
        n = number(value, 10**12)
        return int(n) if n is not None and n == int(n) else None

    @staticmethod
    def label(value):
        return value.strip()[:160] if isinstance(value, str) else ""

    def summary(self):
        return {"power": self.power, "total_merits": self.total, "session_merits": self.session,
                "sale_associated_merits": self.associated, "unassociated_merits": self.session - self.associated,
                "association_estimated": True, "recent": list(self.recent),
                "note": "Session merits are recorded PowerplayMerits gains, not a forecast. Mining-sale association is estimated: "
                        "the first gain within 0-12 seconds of an entirely tracked mined sale, with known unmixed cargo and no intervening "
                        "known earning/travel event. The journal has no sale identifier; bonuses can be included. Other gains stay unassociated. "
                        "Counters reset on LoadGame, commander or pledge change; credits and merits remain separate."}
