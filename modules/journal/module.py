"""journal module: folds game events into the ``journal`` namespace.

Keys: cmdr, credits, ship, ship_name, ship_ident, cargo_capacity, jump_range,
system, star_pos, station, station_type, docked, system_power,
system_power_state, system_powers, materials (totals), materials_detail,
carrier, cargo, market, status, feed, last_event_time, game_version.
"""
import json
import os

NS = "journal"

SHIP_NAMES = {
    "type8": "Type-8 Transporter", "type9": "Type-9 Heavy", "type7": "Type-7 Transporter", "type6": "Type-6 Transporter",
    "panthermkii": "Panther Clipper Mk II", "cutter": "Imperial Cutter", "anaconda": "Anaconda", "python": "Python",
    "python_nx": "Python Mk II", "krait_mkii": "Krait Mk II", "krait_light": "Krait Phantom", "mandalay": "Mandalay",
    "cobramkiii": "Cobra Mk III", "cobramkiv": "Cobra Mk IV", "cobramkv": "Cobra Mk V", "corsair": "Corsair",
    "federation_corvette": "Federal Corvette", "belugaliner": "Beluga Liner", "asp": "Asp Explorer",
    "diamondbackxl": "Diamondback Explorer", "diamondback": "Diamondback Scout", "dolphin": "Dolphin", "orca": "Orca",
    "typex": "Alliance Chieftain", "typex_2": "Alliance Crusader", "typex_3": "Alliance Challenger",
    "ferdelance": "Fer-de-Lance", "mamba": "Mamba", "vulture": "Vulture", "sidewinder": "Sidewinder", "eagle": "Eagle",
    "hauler": "Hauler", "adder": "Adder", "viper": "Viper Mk III", "viper_mkiv": "Viper Mk IV",
    "empire_trader": "Imperial Clipper", "empire_courier": "Imperial Courier", "empire_eagle": "Imperial Eagle",
    "federation_dropship": "Federal Dropship", "federation_dropship_mkii": "Federal Assault Ship",
    "federation_gunship": "Federal Gunship", "independant_trader": "Keelback", "asp_scout": "Asp Scout",
}

KNOWN_RARES = {
    "leestianeviljuice", "bluemilk", "lavianbrandy", "disomacorn", "orrerianviciousbrew", "uszaiantreegrub",
    "leatheryeggs", "zeesszeantgrubglue", "momusbogspaniel", "alyabodysoap", "fujintea", "witchhaulkobebeef",
    "taurichimes", "chateaudeaegaeon", "cetirabbits", "eraninpearlwhisky", "altairianskin", "centaurimegagin",
    "lucanonionhead", "wuthieloku", "onionheadbetastrain", "indibourbon", "harmasilversearum", "kamitracigars",
}

FEED = {
    "FSDJump": lambda e: f"Jumped to {e.get('StarSystem')} ({e.get('JumpDist', 0):.1f} Ly)",
    "Docked": lambda e: f"Docked at {e.get('StationName')}, {e.get('StarSystem')}",
    "Undocked": lambda e: f"Undocked from {e.get('StationName')}",
    "MarketBuy": lambda e: f"Bought {e.get('Count')} t {e.get('Type_Localised') or e.get('Type')} @ {e.get('BuyPrice'):,} Cr",
    "MarketSell": lambda e: f"Sold {e.get('Count')} t {e.get('Type_Localised') or e.get('Type')} @ {e.get('SellPrice'):,} Cr",
    "PowerplayMerits": lambda e: f"+{e.get('MeritsGained'):,} merits (total {e.get('TotalMerits'):,})",
    "PowerplayRank": lambda e: f"Powerplay rank {e.get('Rank')} with {e.get('Power')}",
    "PowerplayJoin": lambda e: f"Pledged to {e.get('Power')}",
    "PowerplayLeave": lambda e: f"Left {e.get('Power')}",
    "PowerplayDefect": lambda e: f"Defected from {e.get('FromPower')} to {e.get('ToPower')}",
    "CarrierJump": lambda e: f"Carrier arrived in {e.get('StarSystem')}",
    "CarrierJumpRequest": lambda e: f"Carrier jump scheduled to {e.get('SystemName')}",
    "Bounty": lambda e: f"Bounty {e.get('TotalReward', 0):,} Cr",
    "MissionCompleted": lambda e: f"Mission complete: {e.get('LocalisedName') or e.get('Name')}",
    "Interdicted": lambda e: f"Interdicted by {e.get('Interdictor_Localised') or e.get('Interdictor')}",
    "Died": lambda e: "Ship destroyed",
    "FuelScoop": lambda e: f"Scooped {e.get('Scooped', 0):.1f} t fuel",
    "MaterialCollected": lambda e: f"+{e.get('Count')} {e.get('Name_Localised') or e.get('Name')}",
    "EngineerCraft": lambda e: f"Engineered {e.get('Slot')}: {e.get('BlueprintName')} G{e.get('Level')}",
}


def norm(name):
    """'$leestianeviljuice_name;' and 'leestianeviljuice' both -> 'leestianeviljuice'."""
    n = (name or "").lower().strip()
    if n.startswith("$"):
        n = n[1:]
    if n.endswith("_name;"):
        n = n[:-6]
    return n


class Journal:
    def __init__(self, core):
        self.core = core
        self.st = {
            "cmdr": None, "credits": None, "ship": None, "ship_name": None, "ship_ident": None,
            "cargo_capacity": None, "jump_range": None, "system": None, "star_pos": None,
            "station": None, "station_type": None, "docked": False,
            "system_power": None, "system_power_state": None, "system_powers": [],
            "materials": {"Raw": 0, "Manufactured": 0, "Encoded": 0}, "materials_detail": {},
            "carrier": None, "last_event_time": None, "game_version": None, "ship_info": None,
            "cargo": {"count": None, "items": []}, "market": {"station": None, "system": None, "rares_in_stock": []},
            "status": {},
        }
        self.feed = []
        self._market_rares = set()
        self._cargo_raw = None
        self.core.store.update(NS, self.st)
        core.bus.on("journal.*", self.on_event)
        core.bus.on("journal.replay.done", self.on_replay_done)

    # -- publishing ----------------------------------------------------------
    def push(self, keys=None):
        data = self.st if keys is None else {k: self.st[k] for k in keys}
        self.core.store.update(NS, data)

    # -- events -------------------------------------------------------------
    def on_event(self, name, ev):
        if name.startswith("journal.file."):
            return self.on_file(name.rsplit(".", 1)[1], ev)
        if name == "journal.replay.done":
            return
        e = ev.get("event")
        st = self.st
        st["last_event_time"] = ev.get("timestamp")
        changed = {"last_event_time"}
        if e in FEED:
            try:
                self.feed.append({"ts": ev.get("timestamp"), "event": e, "text": FEED[e](ev)})
                self.feed = self.feed[-40:]
                st["feed"] = list(reversed(self.feed)); changed.add("feed")
            except Exception:
                pass
        if e == "Fileheader":
            st["game_version"] = ev.get("gameversion"); changed.add("game_version")
        elif e == "Commander":
            st["cmdr"] = ev.get("Name"); changed.add("cmdr")
        elif e == "LoadGame":
            st["cmdr"] = ev.get("Commander"); st["credits"] = ev.get("Credits")
            st["ship"] = ev.get("Ship_Localised") or SHIP_NAMES.get((ev.get("Ship") or "").lower()) or ev.get("Ship")
            st["ship_name"] = ev.get("ShipName"); st["ship_ident"] = ev.get("ShipIdent")
            changed |= {"cmdr", "credits", "ship", "ship_name", "ship_ident"}
        elif e == "Loadout":
            st["ship"] = ev.get("Ship_Localised") or SHIP_NAMES.get((ev.get("Ship") or "").lower()) or st["ship"] or ev.get("Ship")
            st["ship_name"] = ev.get("ShipName"); st["ship_ident"] = ev.get("ShipIdent")
            st["cargo_capacity"] = ev.get("CargoCapacity"); st["jump_range"] = ev.get("MaxJumpRange")
            fuel = ev.get("FuelCapacity") or {}
            mods = ev.get("Modules") or []
            st["ship_info"] = {
                "type": st["ship"], "internal": ev.get("Ship"), "id": ev.get("ShipID"), "name": ev.get("ShipName"), "ident": ev.get("ShipIdent"),
                "hull_value": ev.get("HullValue"), "modules_value": ev.get("ModulesValue"), "rebuy": ev.get("Rebuy"),
                "hull_health": ev.get("HullHealth"), "unladen_mass": ev.get("UnladenMass"), "cargo_capacity": ev.get("CargoCapacity"),
                "max_jump_range": ev.get("MaxJumpRange"), "fuel_main": fuel.get("Main"), "fuel_reserve": fuel.get("Reserve"),
                "hot": ev.get("Hot"), "module_count": len(mods),
                "core": [{"slot": m.get("Slot"), "item": m.get("Item"), "engineering": (m.get("Engineering") or {}).get("BlueprintName"),
                          "level": (m.get("Engineering") or {}).get("Level")} for m in mods
                         if m.get("Slot") in ("PowerPlant", "MainEngines", "FrameShiftDrive", "LifeSupport", "PowerDistributor", "Radar", "FuelTank", "Armour")],
                "hardpoints": [{"slot": m.get("Slot"), "item": m.get("Item")} for m in mods if (m.get("Slot") or "").startswith(("Small", "Medium", "Large", "Huge", "Tiny"))],
            }
            changed |= {"ship", "ship_name", "ship_ident", "cargo_capacity", "jump_range", "ship_info"}
        elif e in ("Location", "FSDJump", "CarrierJump"):
            st["system"] = ev.get("StarSystem"); st["star_pos"] = ev.get("StarPos")
            st["system_power"] = ev.get("ControllingPower"); st["system_power_state"] = ev.get("PowerplayState")
            st["system_powers"] = ev.get("Powers") or []
            changed |= {"system", "star_pos", "system_power", "system_power_state", "system_powers"}
            if ev.get("Docked"):
                st["docked"] = True; st["station"] = ev.get("StationName"); st["station_type"] = ev.get("StationType")
            elif e != "Location":
                st["docked"] = False; st["station"] = None; st["station_type"] = None
            changed |= {"docked", "station", "station_type"}
            if e == "CarrierJump":
                c = st.get("carrier") or {}; c["system"] = ev.get("StarSystem"); st["carrier"] = c; changed.add("carrier")
        elif e == "Docked":
            st["docked"] = True; st["station"] = ev.get("StationName"); st["station_type"] = ev.get("StationType")
            st["system"] = ev.get("StarSystem") or st["system"]; changed |= {"docked", "station", "station_type", "system"}
        elif e == "Undocked":
            st["docked"] = False; st["station"] = None; st["station_type"] = None; changed |= {"docked", "station", "station_type"}
        elif e == "Materials":
            det = {}
            for cat in ("Raw", "Manufactured", "Encoded"):
                items = ev.get(cat) or []
                st["materials"][cat] = sum(i.get("Count", 0) for i in items)
                det[cat] = sorted([[i.get("Name_Localised") or i.get("Name"), i.get("Count", 0)] for i in items], key=lambda x: -x[1])
            st["materials_detail"] = det; changed |= {"materials", "materials_detail"}
        elif e == "MaterialCollected":
            cat = ev.get("Category")
            if cat in st["materials"]:
                st["materials"][cat] += ev.get("Count", 0); changed.add("materials")
        elif e == "CarrierStats":
            st["carrier"] = self._carrier(ev, st.get("carrier")); changed.add("carrier")
        elif e == "CarrierLocation":
            c = st.get("carrier") or {}; c["system"] = ev.get("StarSystem"); st["carrier"] = c; changed.add("carrier")
        self.push(changed)

    def _carrier(self, ev, prev):
        su = ev.get("SpaceUsage") or {}; fin = ev.get("Finance") or {}
        return {"name": ev.get("Name"), "callsign": ev.get("Callsign"), "fuel": ev.get("FuelLevel"),
                "balance": fin.get("CarrierBalance"), "free_space": su.get("FreeSpace"), "cargo": su.get("Cargo"),
                "docking": ev.get("DockingAccess"), "system": (prev or {}).get("system"), "stats_time": ev.get("timestamp"),
                "services": [c.get("CrewRole") for c in (ev.get("Crew") or []) if c.get("Activated")]}

    def on_replay_done(self, name, n):
        if not (self.st.get("carrier") or {}).get("name"):
            self._backfill_carrier()
        self.push()

    def _backfill_carrier(self):
        """CarrierStats only appears when the carrier screen is opened; look back through older journals."""
        from elitelab.core.watcher import journal_files
        from elitelab.core import config
        for fp in journal_files(newest_first=True)[config.RECENT_JOURNALS:60]:
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines = [ln for ln in f if '"event":"CarrierStats"' in ln]
                if lines:
                    self.st["carrier"] = self._carrier(json.loads(lines[-1]), self.st.get("carrier")); return
            except Exception:
                continue

    # -- snapshot files ------------------------------------------------------------
    def on_file(self, name, data):
        st = self.st
        if name == "Status":
            flags = data.get("Flags", 0)
            st["status"] = {"docked_flag": bool(flags & 1), "landed": bool(flags & 2), "supercruise": bool(flags & 16),
                            "fsd_charging": bool(flags & (1 << 17)), "fuel": (data.get("Fuel") or {}).get("FuelMain"),
                            "cargo_tons": data.get("Cargo"), "legal": data.get("LegalState"), "timestamp": data.get("timestamp")}
            if "Balance" in data:
                st["credits"] = data["Balance"]
            self.push({"status", "credits"})
        elif name == "Market":
            self._market_rares = {norm(i.get("Name")) for i in (data.get("Items") or []) if i.get("Rare")}
            st["market"] = {"station": data.get("StationName"), "system": data.get("StarSystem"), "timestamp": data.get("timestamp"),
                            "rares_in_stock": [{"name": i.get("Name_Localised") or i.get("Name"), "buy": i.get("BuyPrice"), "stock": i.get("Stock")}
                                               for i in (data.get("Items") or []) if i.get("Rare") and (i.get("Stock") or 0) > 0]}
            self.push({"market"})
            if self._cargo_raw:
                self.on_file("Cargo", self._cargo_raw)
        elif name == "Cargo":
            self._cargo_raw = data
            rare_keys = self._market_rares | KNOWN_RARES
            items = []
            for i in data.get("Inventory") or []:
                key = norm(i.get("Name"))
                items.append({"name": i.get("Name_Localised") or i.get("Name"), "key": key, "count": i.get("Count"),
                              "stolen": i.get("Stolen", 0), "rare": key in rare_keys})
            st["cargo"] = {"count": data.get("Count"), "items": items, "timestamp": data.get("timestamp")}
            self.push({"cargo"})


def setup(core, module):
    j = Journal(core)
    core.http.route("/api/journal", lambda q: core.store.get(NS),
                    tool="get_commander_state", module=module.name,
                    description="Live commander state from the journal: name, credits, ship, cargo capacity and jump range, "
                                "current system/station, docked flag, Powerplay control of the current system, cargo with rare "
                                "goods tagged, rares in stock at the last market opened, fleet carrier summary, materials totals, "
                                "and the recent event feed.")
