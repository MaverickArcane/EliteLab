"""journal module: folds game events into the ``journal`` namespace.

Keys: cmdr, credits, ship, ship_name, ship_ident, cargo_capacity, jump_range,
system, star_pos, station, station_type, docked, system_power,
system_power_state, system_powers, materials (totals), materials_detail,
carrier, cargo, market, status, feed, last_event_time, game_version.
"""
import json
import os
import re
import threading

from elitelab.core.gamedata import is_rare, norm

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
    "CarrierJumpCancelled": lambda e: "Carrier jump cancelled",
    "Bounty": lambda e: f"Bounty {e.get('TotalReward', 0):,} Cr",
    "MissionCompleted": lambda e: f"Mission complete: {e.get('LocalisedName') or e.get('Name')}",
    "Interdicted": lambda e: f"Interdicted by {e.get('Interdictor_Localised') or e.get('Interdictor')}",
    "Died": lambda e: "Ship destroyed",
    "FuelScoop": lambda e: f"Scooped {e.get('Scooped', 0):.1f} t fuel",
    "MaterialCollected": lambda e: f"+{e.get('Count')} {e.get('Name_Localised') or e.get('Name')}",
    "EngineerCraft": lambda e: f"Engineered {e.get('Slot')}: {e.get('BlueprintName')} G{e.get('Level')}",
}


from elitelab.core import edsy
from elitelab.core import gamedata as gd
from elitelab.core.builds import COSMETIC as COSMETIC_SLOTS, group_of      # shared with the build comparison


class Journal:
    @staticmethod
    def _module(m):
        """One Loadout module for ship_info.modules: journal slot, lower-case item, power state and engineering, plus the
        display name, class, rating and mount from the EDSY table and blueprint/effect names from gamedata (for the ship card)."""
        eng = m.get("Engineering") or {}
        item = (m.get("Item") or "").lower()
        info = edsy.MODULE_BY_FDNAME.get(item)
        if not info:                                    # newer than the EDSY table: make the journal id presentable
            info = {"name": re.sub(r"class(\d)", r"C\1", re.sub(r"size(\d)", r"S\1", re.sub(r"^(int_|hpt_)", "", item))).replace("_", " ")}
        bpk = gd.BLUEPRINT_BY_LOWER.get((eng.get("BlueprintName") or "").lower())
        exk = gd.EXPERIMENTAL_BY_LOWER.get((eng.get("ExperimentalEffect") or "").lower())
        return {"slot": m.get("Slot"), "group": group_of(m.get("Slot")), "item": item, "on": m.get("On"), "priority": m.get("Priority"),
                "health": m.get("Health"), "name": info.get("name") or item, "class": info.get("class"), "rating": info.get("rating"),
                "mount": info.get("mount"),
                "engineering": ({"blueprint": eng.get("BlueprintName"), "blueprint_name": gd.BLUEPRINT_BY_KEY[bpk]["name"] if bpk else eng.get("BlueprintName"),
                                 "level": eng.get("Level"), "quality": eng.get("Quality"), "experimental": eng.get("ExperimentalEffect"),
                                 "experimental_name": gd.EXPERIMENTAL_BY_KEY[exk]["name"] if exk else eng.get("ExperimentalEffect"),
                                 "engineer": eng.get("Engineer")} if eng else None)}

    def __init__(self, core):
        self.core = core
        self.st = {
            "cmdr": None, "credits": None, "ship": None, "ship_name": None, "ship_ident": None,
            "cargo_capacity": None, "jump_range": None, "jump_range_now": None, "jump_range_laden": None, "system": None, "star_pos": None,
            "station": None, "station_type": None, "docked": False,
            "system_power": None, "system_power_state": None, "system_powers": [],
            "carrier": None, "last_event_time": None, "game_version": None, "ship_info": None,
            "cargo": {"count": None, "items": []}, "market": {"station": None, "system": None, "rares_in_stock": []},
            "status": {},
            "game_running": None, "hull_health": None, "hull_at": None,
        }
        self.feed = []
        self._market_rares = set()
        self._cargo_raw = None
        self._learned_ships = {}     # internal hull id -> display name, learned from shipyard events
        self._ship_internal = None
        self.core.store.update(NS, self.st)
        core.bus.on("journal.*", self.on_event)
        core.bus.on("journal.replay.done", self.on_replay_done)

    # -- publishing ----------------------------------------------------------
    def push(self, keys=None):
        data = self.st if keys is None else {k: self.st[k] for k in keys}
        self.core.store.update(NS, data)
        if keys is None or set(keys) & {"cargo", "system", "docked", "star_pos"}:
            self.core.bus.emit("state.journal.location", None)

    # -- ship names -----------------------------------------------------------
    def _learn(self, internal, display):
        if internal and display:
            self._learned_ships[internal.lower()] = display

    def ship_name(self, internal):
        k = (internal or "").lower()
        if not k:
            return None
        return self._learned_ships.get(k) or SHIP_NAMES.get(k) or k.replace("_nx", "").replace("_", " ").title()

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
        elif e == "StoredShips":
            for s in (ev.get("ShipsHere") or []) + (ev.get("ShipsRemote") or []):
                self._learn(s.get("ShipType"), s.get("ShipType_Localised"))
        elif e in ("ShipyardSwap", "ShipyardNew", "ShipyardBuy"):
            self._learn(ev.get("ShipType"), ev.get("ShipType_Localised"))
            if e == "ShipyardSwap":
                self._ship_internal = ev.get("ShipType"); st["ship"] = self.ship_name(ev.get("ShipType")); changed.add("ship")
        elif e == "LoadGame":
            st["game_running"] = True; st["status"] = {}; st["hull_health"] = None; st["hull_at"] = None
            changed |= {"game_running", "status", "hull_health", "hull_at"}
            st["cmdr"] = ev.get("Commander"); st["credits"] = ev.get("Credits")
            self._learn(ev.get("Ship"), ev.get("Ship_Localised"))
            self._ship_internal = ev.get("Ship"); st["ship"] = ev.get("Ship_Localised") or self.ship_name(ev.get("Ship"))
            st["ship_name"] = ev.get("ShipName"); st["ship_ident"] = ev.get("ShipIdent")
            changed |= {"cmdr", "credits", "ship", "ship_name", "ship_ident"}
        elif e == "Loadout":
            st["hull_health"] = ev.get("HullHealth"); st["hull_at"] = ev.get("timestamp")
            changed |= {"hull_health", "hull_at"}
            self._learn(ev.get("Ship"), ev.get("Ship_Localised"))
            st["ship_internal"] = (ev.get("Ship") or "").lower()
            self._ship_internal = ev.get("Ship"); st["ship"] = ev.get("Ship_Localised") or self.ship_name(ev.get("Ship"))
            st["ship_name"] = ev.get("ShipName"); st["ship_ident"] = ev.get("ShipIdent")
            st["cargo_capacity"] = ev.get("CargoCapacity"); st["jump_range"] = ev.get("MaxJumpRange"); st["jump_range_now"] = ev.get("MaxJumpRange")
            fuel = ev.get("FuelCapacity") or {}
            mods = ev.get("Modules") or []
            st["ship_info"] = {
                "type": st["ship"], "internal": ev.get("Ship"), "id": ev.get("ShipID"), "name": ev.get("ShipName"), "ident": ev.get("ShipIdent"),
                "hull_value": ev.get("HullValue"), "modules_value": ev.get("ModulesValue"), "rebuy": ev.get("Rebuy"),
                "hull_health": ev.get("HullHealth"), "unladen_mass": ev.get("UnladenMass"), "cargo_capacity": ev.get("CargoCapacity"),
                "max_jump_range": ev.get("MaxJumpRange"), "fuel_main": fuel.get("Main"), "fuel_reserve": fuel.get("Reserve"),
                "hot": ev.get("Hot"), "module_count": len(mods),
                # every functional module with its group and engineering (the ship card and the build module read this);
                # cosmetics and fixed fittings dropped
                "modules": [self._module(m) for m in mods if not (m.get("Slot") or "").startswith(COSMETIC_SLOTS)],
            }
            # laden and current jump range (issue 4): FSD stats from the EDSY table, optimal mass from the engineering modifiers
            fsd = next((m for m in mods if m.get("Slot") == "FrameShiftDrive"), None)
            optmass = next((x.get("Value") for x in ((fsd or {}).get("Engineering") or {}).get("Modifiers") or [] if x.get("Label") == "FSDOptimalMass"), None)
            if fsd and not optmass:
                optmass = (edsy.MODULE_BY_FDNAME.get((fsd.get("Item") or "").lower()) or {}).get("fsdoptmass")
            self._fsd = {"item": (fsd or {}).get("Item"), "optmass": optmass, "unladen": ev.get("UnladenMass"), "fuel_cap": fuel.get("Main") or 0,
                         "cargo_cap": ev.get("CargoCapacity") or 0,
                         "booster": next((m.get("Item") for m in mods if (m.get("Item") or "").lower().startswith("int_guardianfsdbooster")), None)}
            self._ranges()
            changed |= {"ship", "ship_name", "ship_ident", "cargo_capacity", "jump_range", "jump_range_now", "jump_range_laden", "ship_info", "ship_internal"}
        elif e in ("Location", "FSDJump", "CarrierJump"):
            st["system"] = ev.get("StarSystem"); st["star_pos"] = ev.get("StarPos")
            st["system_power"] = ev.get("ControllingPower"); st["system_power_state"] = ev.get("PowerplayState")
            st["system_powers"] = ev.get("Powers") or []
            changed |= {"system", "star_pos", "system_power", "system_power_state", "system_powers"}
            if ev.get("Docked"):
                st["docked"] = True; st["station"] = ev.get("StationName"); st["station_type"] = ev.get("StationType")
            else:
                st["docked"] = False; st["station"] = None; st["station_type"] = None
            changed |= {"docked", "station", "station_type"}
            if e == "CarrierJump":
                c = st.get("carrier") or {}; c["system"] = ev.get("StarSystem"); st["carrier"] = c; changed.add("carrier")
        elif e == "Docked":
            st["docked"] = True; st["station"] = ev.get("StationName"); st["station_type"] = ev.get("StationType")
            st["system"] = ev.get("StarSystem") or st["system"]; changed |= {"docked", "station", "station_type", "system"}
        elif e == "Undocked":
            st["docked"] = False; st["station"] = None; st["station_type"] = None; changed |= {"docked", "station", "station_type"}
        elif e == "HullDamage" and ev.get("PlayerPilot") is True and ev.get("Fighter") is False:
            st["hull_health"] = ev.get("Health"); st["hull_at"] = ev.get("timestamp")
            changed |= {"hull_health", "hull_at"}
        elif e == "Shutdown":
            st["game_running"] = False; changed.add("game_running")
        elif e == "CarrierStats":
            st["carrier"] = self._carrier(ev, st.get("carrier")); changed.add("carrier")
        elif e == "CarrierLocation":
            c = st.get("carrier") or {}; c["system"] = ev.get("StarSystem"); st["carrier"] = c; changed.add("carrier")
        self.push(changed)

    def _carrier(self, ev, prev):
        su = ev.get("SpaceUsage") or {}; fin = ev.get("Finance") or {}
        return {"name": ev.get("Name"), "callsign": ev.get("Callsign"), "fuel": ev.get("FuelLevel"),
                "balance": fin.get("CarrierBalance"), "free_space": su.get("FreeSpace"), "reserved_space": su.get("CargoSpaceReserved", 0), "cargo": su.get("Cargo"),
                "docking": ev.get("DockingAccess"), "system": (prev or {}).get("system"), "stats_time": ev.get("timestamp"),
                "services": [c.get("CrewRole") for c in (ev.get("Crew") or []) if c.get("Activated")]}

    def on_replay_done(self, name, n):
        self.push()
        if not (self.st.get("carrier") or {}).get("name"):
            # Scanning older journals can take a while on big archives; never block the watcher thread for it.
            threading.Thread(target=self._backfill_carrier, name="carrier-backfill", daemon=True).start()

    def _backfill_carrier(self):
        """CarrierStats only appears when the carrier screen is opened; look back through older journals."""
        from elitelab.core.watcher import journal_files
        from elitelab.core import config
        for fp in journal_files(newest_first=True)[config.RECENT_JOURNALS:60]:
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines = [ln for ln in f if '"event":"CarrierStats"' in ln]
                if lines:
                    if not (self.st.get("carrier") or {}).get("name"):      # a live CarrierStats may have arrived meanwhile
                        self.st["carrier"] = self._carrier(json.loads(lines[-1]), self.st.get("carrier"))
                        self.push({"carrier"})
                    return
            except Exception:
                continue

    def _ranges(self):
        """jump_range_laden (full tank, full hold) and jump_range_now (fuel and cargo from Status.json) from the FSD."""
        f = getattr(self, "_fsd", None) or {}
        st = self.st
        laden = now = None
        if f.get("item") and f.get("unladen"):
            stt = st.get("status") or {}
            fuel_now = stt.get("fuel") if stt.get("fuel") is not None else f["fuel_cap"]
            cargo_now = stt.get("cargo_tons") if stt.get("cargo_tons") is not None else 0
            laden = edsy.jump_range(f["item"], f["optmass"], f["unladen"] + f["fuel_cap"] + f["cargo_cap"], f["booster"])
            now = edsy.jump_range(f["item"], f["optmass"], f["unladen"] + fuel_now + cargo_now, f["booster"], fuel=fuel_now)
        st["jump_range_laden"] = laden
        st["jump_range_now"] = now if now is not None else st.get("jump_range")     # the one key consumers read; unladen max as fallback

    # -- snapshot files ------------------------------------------------------------
    def on_file(self, name, data):
        st = self.st
        if name == "Status":
            flags = data.get("Flags", 0)
            flags2 = data.get("Flags2", 0)
            vehicle = "foot" if flags2 & 1 else "taxi" if flags2 & 2 else "crew" if flags2 & 4 else "srv" if flags & (1 << 26) else "fighter" if flags & (1 << 25) else "ship" if flags & (1 << 24) else None
            prev = st.get("status") or {}
            if prev.get("vehicle") != vehicle:
                prev = {}  # Never carry ship fuel into a fighter, SRV or on-foot reading.
            fuel_data = data.get("Fuel") or {}
            fuel = fuel_data.get("FuelMain")
            st["status"] = {"docked_flag": bool(flags & 1), "landed": bool(flags & 2), "supercruise": bool(flags & 16),
                            "fsd_charging": bool(flags & (1 << 17)),
                            "fuel": fuel if fuel is not None else prev.get("fuel"),   # the game omits Fuel in station menus; keep the last reading
                            "fuel_reservoir": fuel_data.get("FuelReservoir", prev.get("fuel_reservoir")),
                            "fuel_at": data.get("timestamp") if fuel is not None else prev.get("fuel_at"),
                            "vehicle": vehicle, "body": data.get("BodyName"),
                            "destination": (data.get("Destination") or {}).get("Name_Localised") or (data.get("Destination") or {}).get("Name"),
                            "shields_up": bool(flags & 8) if "Flags" in data else None,
                            "fsd_jump": bool(flags & (1 << 30)), "scooping": bool(flags & (1 << 11)),
                            "low_fuel": bool(flags & (1 << 19)), "overheating": bool(flags & (1 << 20)),
                            "in_danger": bool(flags & (1 << 22)), "interdicted": bool(flags & (1 << 23)),
                            "silent_running": bool(flags & (1 << 10)), "hardpoints": bool(flags & (1 << 6)),
                            "cargo_tons": data.get("Cargo"), "legal": data.get("LegalState"), "timestamp": data.get("timestamp")}
            if "Balance" in data:
                st["credits"] = data["Balance"]
            self._ranges()
            self.push({"status", "credits", "jump_range_now"})
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
            items = []
            for i in data.get("Inventory") or []:
                key = norm(i.get("Name"))
                display = i.get("Name_Localised") or i.get("Name")
                items.append({"name": display, "key": key, "count": i.get("Count"), "stolen": i.get("Stolen", 0),
                              "rare": key in self._market_rares or is_rare(key) or is_rare(display)})
            st["cargo"] = {"count": data.get("Count"), "items": items, "timestamp": data.get("timestamp")}
            self.push({"cargo"})


def setup(core, module):
    j = Journal(core)
    core.http.route("/api/journal", lambda q: core.store.get(NS),
                    tool="get_commander_state", module=module.name,
                    description="Live commander state from the journal: name, credits, ship (with loadout summary), cargo capacity "
                                "and jump range, current system/station, docked flag, Powerplay control of the current system, cargo "
                                "with rare goods tagged, rares in stock at the last market opened, fleet carrier summary, and the "
                                "recent event feed. Materials live in get_materials.")
