"""merits module: where do my merits come from, and how fast?

The journal's PowerplayMerits event does not say what earned the merits, but it
lands within a second or two of its cause (MarketSell, Bounty, FactionKillBond,
...). We keep a short window of recent "cause" events and attribute each gain
to the latest one. Gains far above what a sale should pay are tagged as
objective bonuses.

State ``merits``: session_start, session_merits, hours, per_hour, last_hour,
by_activity {name: {merits, events, per_event}}, best, recent [...], unattributed.
"""
import datetime as dt
import time

NS = "merits"
WINDOW_S = 12          # a cause older than this is not blamed for a gain
RARE_RATE = 667.0      # Cr of sale value per merit observed for rares with Mahon's bonus (used only for bonus detection)

KNOWN_RARES = {
    "leestianeviljuice", "bluemilk", "lavianbrandy", "disomacorn", "orrerianviciousbrew", "uszaiantreegrub",
    "alieneggs", "zeesszeantgrubglue", "momusbogspaniel", "alyabodysoap", "fujintea", "witchhaulkobebeef",
    "taurichimes", "chateaudeaegaeon", "cetirabbits", "eraninpearlwhisky", "altairianskin", "centaurimegagin",
    "lucanonionhead", "wuthieloku", "onionheadbetastrain", "indibourbon", "harmasilversearum", "kamitracigars",
}

# event -> (activity, detail-builder)
CAUSES = {
    "MarketSell": lambda e: ("rares" if (e.get("Type") or "").lower() in KNOWN_RARES else "trade",
                             f"{e.get('Count')} t {e.get('Type_Localised') or e.get('Type')} for {e.get('TotalSale', 0):,} Cr"),
    "Bounty": lambda e: ("bounty hunting", f"{e.get('Target_Localised') or e.get('Target')} {e.get('TotalReward', 0):,} Cr"),
    "FactionKillBond": lambda e: ("combat zone", f"bond {e.get('Reward', 0):,} Cr vs {e.get('VictimFaction_Localised') or e.get('VictimFaction')}"),
    "PVPKill": lambda e: ("pvp", f"killed {e.get('Victim')}"),
    "PowerplayDeliver": lambda e: ("hauling", f"delivered {e.get('Count')} {e.get('Type_Localised') or e.get('Type')}"),
    "PowerplayCollect": lambda e: ("hauling", f"collected {e.get('Count')} {e.get('Type_Localised') or e.get('Type')}"),
    "MultiSellExplorationData": lambda e: ("exploration", f"sold data for {e.get('TotalEarnings', 0):,} Cr"),
    "SellExplorationData": lambda e: ("exploration", f"sold data for {e.get('TotalEarnings', 0):,} Cr"),
    "SellOrganicData": lambda e: ("exobiology", "sold organic data"),
    "MissionCompleted": lambda e: ("missions", e.get("LocalisedName") or e.get("Name")),
    "SearchAndRescue": lambda e: ("search and rescue", f"{e.get('Count')} {e.get('Name_Localised') or e.get('Name')}"),
    "DatalinkScan": lambda e: ("scans", "datalink scan"),
    "DataScanned": lambda e: ("scans", e.get("Type_Localised") or e.get("Type")),
    "SellMicroResources": lambda e: ("odyssey trade", "sold micro resources"),
    "ShipTargeted": None,   # ignored
}


def _ts(s):
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except Exception:
        return None


class Merits:
    def __init__(self, core):
        self.core = core
        self.reset(None)
        for e in list(CAUSES) + ["PowerplayMerits", "LoadGame", "PowerplayJoin", "PowerplayDefect", "PowerplayLeave"]:
            core.bus.on("journal." + e, self.on_event)
        core.bus.on("journal.replay.done", lambda n, v: self.publish())

    def reset(self, ts):
        self.session_start = ts
        self.causes = []          # [(ts, activity, detail, cr)]
        self.gains = []           # [{ts, gained, activity, detail}]
        self.unattributed = 0

    def on_event(self, name, ev):
        e, ts = ev.get("event"), _ts(ev.get("timestamp"))
        if e in ("LoadGame", "PowerplayJoin", "PowerplayDefect", "PowerplayLeave"):
            self.reset(ts); self.publish(); return
        if e == "PowerplayMerits":
            gained = ev.get("MeritsGained") or 0
            act, detail = "unattributed", ""
            cause = None
            for c in reversed(self.causes):
                if ts is not None and c[0] is not None and ts - c[0] <= WINDOW_S:
                    cause = c; break
            if cause:
                act, detail, cr = cause[1], cause[2], cause[3]
                if act in ("rares", "trade") and cr and gained > 2.5 * (cr / RARE_RATE) and gained >= 500:
                    act, detail = "objective bonus", f"paid alongside {detail}"
            else:
                self.unattributed += gained
            self.gains.append({"ts": ev.get("timestamp"), "t": ts, "gained": gained, "activity": act, "detail": detail,
                               "total": ev.get("TotalMerits")})
            self.gains = self.gains[-500:]
            self.publish(); return
        fn = CAUSES.get(e)
        if fn:
            act, detail = fn(ev)
            cr = ev.get("TotalSale") or ev.get("TotalReward") or ev.get("Reward") or ev.get("TotalEarnings") or 0
            self.causes.append((ts, act, detail, cr))
            self.causes = self.causes[-50:]

    def summary(self):
        now = time.time()
        total = sum(g["gained"] for g in self.gains)
        first = self.session_start or (self.gains[0]["t"] if self.gains else None)
        hours = max((now - first) / 3600, 1 / 60) if first else None
        last_hour = sum(g["gained"] for g in self.gains if g["t"] and now - g["t"] <= 3600)
        by = {}
        for g in self.gains:
            b = by.setdefault(g["activity"], {"merits": 0, "events": 0})
            b["merits"] += g["gained"]; b["events"] += 1
        for b in by.values():
            b["per_event"] = round(b["merits"] / b["events"]) if b["events"] else 0
            b["share"] = round(100 * b["merits"] / total) if total else 0
        best = max(by.items(), key=lambda kv: kv[1]["merits"])[0] if by else None
        return {"session_start": dt.datetime.fromtimestamp(first, dt.timezone.utc).isoformat() if first else None,
                "session_merits": total, "hours": round(hours, 2) if hours else None,
                "per_hour": round(total / hours) if hours else None, "last_hour": last_hour,
                "by_activity": by, "best": best, "unattributed": self.unattributed,
                "recent": [{k: v for k, v in g.items() if k != "t"} for g in self.gains[-15:]][::-1],
                "note": "Merits attributed to the latest sale/kill/delivery within 12 s. Observed: rares pay ~1 merit per 667 Cr of sale value (Mahon +25%)."}

    def publish(self):
        self.core.store.update(NS, self.summary())


def setup(core, module):
    m = Merits(core)
    core.http.route("/api/merits", lambda q: m.summary(), tool="get_merits_summary", module=module.name,
                    description="Where this session's Powerplay merits came from (rares, trade, bounty hunting, combat zone bonds, hauling, "
                                "exploration, missions, objective bonuses), merits per hour overall and in the last hour, merits per event, "
                                "and a recent log. Use it to compare activities with real numbers.")
