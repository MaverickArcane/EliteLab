"""Turn the Elite Dangerous journal and companion JSON files into a single state dict.

The game writes newline-delimited JSON to Journal.*.log plus a handful of
snapshot files (Status.json, Cargo.json, Market.json...). Everything here is
read-only and tolerant of partial lines, since the game may be mid-write.
"""
import glob
import json
import os
import time

from . import config

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

# Rare commodities the game does not flag in Cargo.json. Keys are the internal names.
KNOWN_RARES = {
    "leestianeviljuice", "bluemilk", "lavianbrandy", "disomacorn", "orrerianviciousbrew", "uszaiantreegrub",
    "leatheryeggs", "zeesszeantgrubglue", "momusbogspaniel", "alyabodysoap", "fujintea", "witchhaulkobebeef",
    "taurichimes", "chateaudeaegaeon", "cetirabbits", "eraninpearlwhisky", "altairianskin", "centaurimegagin",
    "lucanonionhead", "wuthieloku", "onionheadbetastrain", "indibourbon", "harmasilversearum", "kamitracigars",
}

# Events worth showing in the live feed, with a short formatter each.
FEED_EVENTS = {
    "FSDJump": lambda e: f"Jumped to {e.get('StarSystem')} ({e.get('JumpDist', 0):.1f} Ly)",
    "Docked": lambda e: f"Docked at {e.get('StationName')}, {e.get('StarSystem')}",
    "Undocked": lambda e: f"Undocked from {e.get('StationName')}",
    "MarketBuy": lambda e: f"Bought {e.get('Count')} t {e.get('Type_Localised') or e.get('Type')} @ {e.get('BuyPrice'):,} Cr",
    "MarketSell": lambda e: f"Sold {e.get('Count')} t {e.get('Type_Localised') or e.get('Type')} @ {e.get('SellPrice'):,} Cr"
                            + (f" (+{e.get('TotalSale', 0) - e.get('AvgPricePaid', 0) * e.get('Count', 0):,} Cr)" if e.get('AvgPricePaid') is not None else ""),
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
}


def _norm(name):
    """Normalise commodity keys: Market.json uses '$leestianeviljuice_name;', Cargo.json uses 'leestianeviljuice'."""
    n = (name or "").lower().strip()
    if n.startswith("$"):
        n = n[1:]
    if n.endswith("_name;"):
        n = n[:-6]
    return n


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def journal_files(newest_first=False):
    files = glob.glob(os.path.join(config.JOURNAL_DIR, "Journal.*.log"))
    files.sort(key=os.path.getmtime, reverse=newest_first)
    return files


def iter_events(files):
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except Exception:
                        continue
        except Exception:
            continue


def _carrier_from_stats(ev, prev):
    su = ev.get("SpaceUsage") or {}
    fin = ev.get("Finance") or {}
    return {
        "name": ev.get("Name"), "callsign": ev.get("Callsign"), "fuel": ev.get("FuelLevel"),
        "balance": fin.get("CarrierBalance"), "free_space": su.get("FreeSpace"), "cargo": su.get("Cargo"),
        "docking": ev.get("DockingAccess"), "system": (prev or {}).get("system"), "stats_time": ev.get("timestamp"),
        "services": [c.get("CrewRole") for c in (ev.get("Crew") or []) if c.get("Activated")],
    }


def _backfill_carrier(st):
    """CarrierStats only appears when the carrier management screen is opened, so look back through older journals."""
    for fp in journal_files(newest_first=True)[config.RECENT_JOURNALS:60]:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                lines = [ln for ln in f if '"event":"CarrierStats"' in ln]
        except Exception:
            continue
        if not lines:
            continue
        try:
            st["carrier"] = _carrier_from_stats(json.loads(lines[-1]), st.get("carrier"))
            return
        except Exception:
            continue


def empty_state():
    return {
        "cmdr": None, "credits": None, "ship": None, "ship_name": None, "ship_ident": None,
        "cargo_capacity": None, "jump_range": None, "system": None, "star_pos": None,
        "station": None, "station_type": None, "docked": False,
        "system_power": None, "system_power_state": None, "system_powers": [],
        "power": None, "merits": None, "rank": None, "time_pledged": None,
        "materials": {"Raw": 0, "Manufactured": 0, "Encoded": 0}, "materials_detail": {},
        "carrier": None, "last_event_time": None, "game_version": None, "feed": [],
    }


def apply_event(st, ev):
    """Fold one journal event into the state dict."""
    e = ev.get("event")
    st["last_event_time"] = ev.get("timestamp")
    if e in FEED_EVENTS:
        try:
            st["feed"].append({"ts": ev.get("timestamp"), "event": e, "text": FEED_EVENTS[e](ev)})
        except Exception:
            pass
    if e == "Fileheader":
        st["game_version"] = ev.get("gameversion")
    elif e == "Commander":
        st["cmdr"] = ev.get("Name")
    elif e == "LoadGame":
        st["cmdr"] = ev.get("Commander"); st["credits"] = ev.get("Credits")
        st["ship"] = ev.get("Ship_Localised") or SHIP_NAMES.get((ev.get("Ship") or "").lower()) or ev.get("Ship")
        st["ship_name"] = ev.get("ShipName"); st["ship_ident"] = ev.get("ShipIdent")
    elif e == "Loadout":
        st["ship"] = ev.get("Ship_Localised") or SHIP_NAMES.get((ev.get("Ship") or "").lower()) or st["ship"] or ev.get("Ship")
        st["ship_name"] = ev.get("ShipName"); st["ship_ident"] = ev.get("ShipIdent")
        st["cargo_capacity"] = ev.get("CargoCapacity"); st["jump_range"] = ev.get("MaxJumpRange")
    elif e in ("Location", "FSDJump", "CarrierJump"):
        st["system"] = ev.get("StarSystem"); st["star_pos"] = ev.get("StarPos")
        st["system_power"] = ev.get("ControllingPower"); st["system_power_state"] = ev.get("PowerplayState")
        st["system_powers"] = ev.get("Powers") or []
        if ev.get("Docked"):
            st["docked"] = True; st["station"] = ev.get("StationName"); st["station_type"] = ev.get("StationType")
        elif e != "Location":
            st["docked"] = False; st["station"] = None; st["station_type"] = None
        if e == "CarrierJump":
            c = st.get("carrier") or {}
            c["system"] = ev.get("StarSystem"); st["carrier"] = c
    elif e == "Docked":
        st["docked"] = True; st["station"] = ev.get("StationName"); st["station_type"] = ev.get("StationType")
        st["system"] = ev.get("StarSystem") or st["system"]
    elif e == "Undocked":
        st["docked"] = False; st["station"] = None; st["station_type"] = None
    elif e == "Powerplay":
        st["power"] = ev.get("Power"); st["merits"] = ev.get("Merits"); st["rank"] = ev.get("Rank")
        st["time_pledged"] = ev.get("TimePledged")
    elif e == "PowerplayJoin":
        st["power"] = ev.get("Power"); st["merits"] = 0; st["rank"] = 0; st["time_pledged"] = 0
    elif e == "PowerplayDefect":
        st["power"] = ev.get("ToPower"); st["merits"] = 0; st["rank"] = 0; st["time_pledged"] = 0
    elif e == "PowerplayLeave":
        st["power"] = None; st["merits"] = None; st["rank"] = None; st["time_pledged"] = None
    elif e == "PowerplayMerits":
        st["merits"] = ev.get("TotalMerits", st["merits"])
    elif e == "PowerplayRank":
        st["rank"] = ev.get("Rank")
    elif e == "Materials":
        det = {}
        for cat in ("Raw", "Manufactured", "Encoded"):
            items = ev.get(cat) or []
            st["materials"][cat] = sum(i.get("Count", 0) for i in items)
            det[cat] = sorted([[i.get("Name_Localised") or i.get("Name"), i.get("Count", 0)] for i in items],
                              key=lambda x: -x[1])
        st["materials_detail"] = det
    elif e == "MaterialCollected":
        cat = ev.get("Category")
        if cat in st["materials"]:
            st["materials"][cat] += ev.get("Count", 0)
    elif e == "CarrierStats":
        st["carrier"] = _carrier_from_stats(ev, st.get("carrier"))
    elif e == "CarrierLocation":
        c = st.get("carrier") or {}
        c["system"] = ev.get("StarSystem"); st["carrier"] = c


def build_state():
    st = empty_state()
    for ev in iter_events(journal_files()[-config.RECENT_JOURNALS:]):
        apply_event(st, ev)
    st["feed"] = st["feed"][-30:][::-1]

    if not (st.get("carrier") or {}).get("name"):
        _backfill_carrier(st)

    status = _read_json(os.path.join(config.JOURNAL_DIR, "Status.json")) or {}
    if "Balance" in status:
        st["credits"] = status["Balance"]
    flags = status.get("Flags", 0)
    st["status"] = {
        "docked_flag": bool(flags & 1), "landed": bool(flags & 2), "supercruise": bool(flags & 16),
        "fsd_charging": bool(flags & (1 << 17)), "fuel": (status.get("Fuel") or {}).get("FuelMain"),
        "cargo_tons": status.get("Cargo"), "legal": status.get("LegalState"), "timestamp": status.get("timestamp"),
    }

    cargo = _read_json(os.path.join(config.JOURNAL_DIR, "Cargo.json")) or {}
    market = _read_json(os.path.join(config.JOURNAL_DIR, "Market.json")) or {}
    rare_keys = {_norm(i.get("Name")) for i in (market.get("Items") or []) if i.get("Rare")} | KNOWN_RARES
    inv = []
    for i in cargo.get("Inventory") or []:
        key = _norm(i.get("Name"))
        inv.append({"name": i.get("Name_Localised") or i.get("Name"), "key": key, "count": i.get("Count"),
                    "stolen": i.get("Stolen", 0), "rare": key in rare_keys})
    st["cargo"] = {"count": cargo.get("Count"), "items": inv}
    rares_here = [{"name": i.get("Name_Localised") or i.get("Name"), "buy": i.get("BuyPrice"), "stock": i.get("Stock")}
                  for i in (market.get("Items") or []) if i.get("Rare") and (i.get("Stock") or 0) > 0]
    st["market"] = {"station": market.get("StationName"), "system": market.get("StarSystem"),
                    "timestamp": market.get("timestamp"), "rares_in_stock": rares_here}
    st["generated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    st["journal_dir"] = config.JOURNAL_DIR
    st["journal_ok"] = bool(journal_files())
    return st
