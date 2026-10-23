"""combat module: where combat pays Powerplay merits, and a log of the conflict zones you have actually seen.

Powerplay 2.0 rules this encodes (community-documented, see docs/DECISIONS.md):
- Acquisition systems (Unoccupied, your power contesting): bounty hunting pays merits on the kill, +5% since the April 2025 patch.
- Contested acquisition systems: Powerplay combat zones spawn when two or more powers are past the conflict threshold
  (~35,000 of 120,000 control points, ~29%). Observed: once a power is past 100% the acquisition is decided and the
  zones are gone (Porrima, Crucis Sector CL-Y c33 were busts; LP 673-42 with every side between 47% and 68% had seven).
- Undermining (systems controlled by a rival): killing ships aligned to the controlling power pays merits.
- Reinforcement (systems your power controls): bounty hunting pays merits with a 35% penalty.

Zone log: the game writes FSSSignalDiscovered for every Powerplay conflict zone when you arrive in a system (or get
near the nav beacon), with the intensity in the name. That is the only live, exact source of "is there a zone, and how
hot", so we record it per system and keep it in data/zones.json across restarts.
"""
import datetime as dt
import math
import re
import threading

NS = "combat"
KINDS = ["contested", "acquisition", "undermining", "reinforcement"]
CONFLICT_THRESHOLD = 0.29
DECIDED = 1.0
HINTS = {
    "contested": "Powerplay combat zones spawn only where your power AND a rival are both past ~29% and nobody is past 100%. "
                 "Merits per kill. Find the zones in the nav panel (Points of Interest filter) or near the nav beacon.",
    "acquisition": "Bounty hunting here pays merits on each kill (+5%). Pick a system with a ringed planet (Res sites) or sit at the nav beacon.",
    "undermining": "Kill ships pledged to the controlling power (they show the power's name in the target panel). Pirates here do not count.",
    "reinforcement": "Your own systems: bounty hunting pays merits but with a 35% penalty. Only worth it if it is where you already are.",
}
INTENSITY = {"Low": 1, "Med": 2, "Medium": 2, "High": 3, "VeryHigh": 4}


def _age_hours(iso):
    try:
        t = dt.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
        return round((dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600, 1)
    except Exception:
        return None


class ZoneLog:
    """Powerplay conflict zones seen in the journal, keyed by system name."""

    def __init__(self, core):
        self.core = core
        self.lock = threading.Lock()
        self.seen = core.read_data("zones.json", default={}) or {}
        self.addr_to_name = {}
        self.current = None                     # current system name
        self.current_sigs = {}                  # intensity -> set of signal names, for the current system
        for e in ("Location", "FSDJump", "CarrierJump"):
            core.bus.on("journal." + e, self.on_jump)
        core.bus.on("journal.FSSSignalDiscovered", self.on_signal)
        core.bus.on("journal.SupercruiseDestinationDrop", self.on_drop)
        core.bus.on("journal.replay.done", lambda n, v: self.publish())

    def on_jump(self, name, ev):
        self.current = ev.get("StarSystem")
        if ev.get("SystemAddress"):
            self.addr_to_name[ev["SystemAddress"]] = self.current
        self.current_sigs = {}
        if not ev.get("_replay"):
            self.publish()

    @staticmethod
    def parse(signal_name, localised):
        """'$Warzone_Powerplay_Med:#index=4;' -> ('Medium', '$Warzone_Powerplay_Med:#index=4;')"""
        if not signal_name or "Warzone_Powerplay" not in signal_name:
            return None
        m = re.search(r"Warzone_Powerplay_([A-Za-z]+)", signal_name)
        raw = m.group(1) if m else "?"
        level = {"Low": "Low", "Med": "Medium", "Medium": "Medium", "High": "High", "VeryHigh": "Very High"}.get(raw, raw)
        return level

    def on_signal(self, name, ev):
        level = self.parse(ev.get("SignalName"), ev.get("SignalName_Localised"))
        if not level:
            return
        system = self.addr_to_name.get(ev.get("SystemAddress")) or self.current
        if not system:
            return
        with self.lock:
            self.current_sigs.setdefault(level, set()).add(ev.get("SignalName"))
            rec = self.seen.setdefault(system, {"system": system, "zones": {}, "first_seen": ev.get("timestamp"), "last_seen": None, "pos": None})
            rec["last_seen"] = ev.get("timestamp")
            rec["zones"] = {lvl: len(sigs) for lvl, sigs in self.current_sigs.items()}
            pos = self.core.store.get("journal", "star_pos")
            if pos and self.core.store.get("journal", "system") == system:
                rec["pos"] = pos
        if not ev.get("_replay"):
            self.save(); self.publish()

    def on_drop(self, name, ev):
        level = self.parse(ev.get("Type"), ev.get("Type_Localised"))
        if level and self.current and not ev.get("_replay"):
            with self.lock:
                rec = self.seen.setdefault(self.current, {"system": self.current, "zones": {}, "first_seen": ev.get("timestamp"), "last_seen": None, "pos": None})
                rec["last_seen"] = ev.get("timestamp"); rec["last_dropped"] = level
            self.save(); self.publish()

    def save(self):
        with self.lock:
            self.core.write_data(self.seen, "zones.json")

    def here(self):
        with self.lock:
            return {lvl: len(s) for lvl, s in self.current_sigs.items()}

    def rows(self):
        with self.lock:
            out = []
            for rec in self.seen.values():
                z = rec.get("zones") or {}
                hottest = max((INTENSITY.get(k, 0) for k in z), default=0)
                out.append({**rec, "hottest": {1: "Low", 2: "Medium", 3: "High", 4: "Very High"}.get(hottest),
                            "age_h": _age_hours(rec.get("last_seen") or "")})
            out.sort(key=lambda r: (r["age_h"] if r["age_h"] is not None else 1e9))
            return out

    def publish(self):
        self.core.store.update(NS, {"zones_here": self.here(), "zones_seen": self.rows(), "zone_system": self.current})


def setup(core, module):
    svc = core.services
    core.store.set(NS, "last", None)
    zl = ZoneLog(core)

    def find(q):
        power = q.get("power") or core.store.get("powerplay", "power") or "Edmund Mahon"
        ref = q.get("ref") or core.store.get("journal", "system") or "Leesti"
        kind = (q.get("kind") or "contested").lower()
        if kind not in KINDS + ["all"]:
            raise ValueError(f"kind must be one of {KINDS + ['all']}")
        radius = float(q.get("max") or 60)
        limit = min(int(q.get("limit") or 25), 100)
        jr = core.store.get("journal", "jump_range")
        kinds = KINDS if kind == "all" else [kind]
        rows = []
        for k in kinds:
            filters = {"distance": {"min": "0", "max": str(radius)}}
            if k in ("contested", "acquisition"):
                filters["power_state"] = {"value": ["Unoccupied"]}
                filters["power"] = {"value": [power]}
            elif k == "undermining":
                filters["power_state"] = {"value": ["Exploited", "Fortified", "Stronghold"]}
            else:
                filters["controlling_power"] = {"value": [power]}
            results = []
            for page in range(40 if k == "contested" else 1):
                body = {"filters": filters, "sort": [{"distance": {"direction": "asc"}}], "size": 100, "page": page, "reference_system": ref}
                data = svc.fetch_json("https://spansh.co.uk/api/systems/search", body, ttl=1800)
                chunk = data.get("results", [])
                results.extend(chunk)
                if len(chunk) < 100:
                    break
            for s in results:
                conf = s.get("power_conflict_progress") or []
                mine = next((c.get("progress", 0) for c in conf if c.get("power") == power), None)
                rivals_hot = [c for c in conf if c.get("power") != power and (c.get("progress") or 0) >= CONFLICT_THRESHOLD]
                over = [c for c in conf if (c.get("progress") or 0) > DECIDED]
                zone_likely = bool(mine is not None and CONFLICT_THRESHOLD <= mine <= DECIDED and rivals_hot and not over)
                if k == "contested" and not zone_likely:
                    continue
                if k == "undermining" and s.get("controlling_power") in (None, power):
                    continue
                if not s.get("population"):
                    continue
                seen = zl.seen.get(s.get("name"))
                rows.append({
                    "kind": k, "system": s.get("name"), "dist": round(s.get("distance", 0), 1),
                    "jumps": (math.ceil(s.get("distance", 0) / jr) if jr else None),
                    "state": s.get("power_state"), "controlling_power": s.get("controlling_power"),
                    "security": s.get("security"), "population": s.get("population"), "allegiance": s.get("allegiance"),
                    "my_progress": round(mine, 3) if mine is not None else None, "zone_likely": zone_likely,
                    "decided": bool(over), "data_age_h": _age_hours(s.get("updated_at") or ""),
                    "conflict": [{"power": c.get("power"), "progress": round(c.get("progress") or 0, 3)} for c in conf],
                    "seen_zones": (seen or {}).get("zones"), "seen_at": (seen or {}).get("last_seen"),
                    "x": s.get("x"), "y": s.get("y"), "z": s.get("z"),
                })

        def score(r):
            if r["kind"] != "contested":
                return (KINDS.index(r["kind"]), 0, r["dist"])
            # closest two-way race first: the top two sides nearest each other and both high
            top = sorted((c["progress"] for c in r["conflict"]), reverse=True)[:2]
            closeness = (top[0] - top[1]) if len(top) == 2 else 1
            return (0, closeness - min(top, default=0), r["dist"])
        rows.sort(key=score)
        out = {"power": power, "ref": ref, "kind": kind, "radius": radius, "jump_range": jr, "results": rows[:limit],
               "hints": {k: HINTS[k] for k in kinds}, "conflict_threshold": CONFLICT_THRESHOLD,
               "note": "zone_likely: your power and a rival are both between 29% and 100% and nobody is past 100%. "
                       "data_age_h is how old Spansh's numbers are; seen_zones is what your own journal recorded there."}
        core.store.set(NS, "last", out)
        return out

    core.http.route("/api/combat", find, tool="find_combat_systems", module=module.name,
                    description="Systems near the reference where combat earns Powerplay merits for the pledged power. kind=contested: "
                                "systems where your power AND a rival are both past the ~29% conflict threshold and nobody is past 100%, "
                                "the only place Powerplay combat zones exist (zone_likely=true), sorted by closest race; acquisition: bounty "
                                "hunting pays +5%; undermining: rival-controlled systems where killing the controlling power's ships pays; "
                                "reinforcement: your own systems (-35%). Includes Spansh data age, security, population, conflict progress "
                                "per power, distance, jumps, and any zones your own journal has recorded there.",
                    params={"kind": {"type": "string", "description": "contested (default), acquisition, undermining, reinforcement or all", "enum": KINDS + ["all"], "default": "contested"},
                            "ref": {"type": "string", "description": "Reference system; default = current system"},
                            "power": {"type": "string", "description": "Power; default = pledged power"},
                            "max": {"type": "number", "description": "Search radius in Ly", "default": 60},
                            "limit": {"type": "integer", "description": "Max results (<=100)", "default": 25}})
    core.http.route("/api/combat/zones", lambda q: {"system": zl.current, "here": zl.here(), "seen": zl.rows()},
                    tool="get_conflict_zones_seen", module=module.name,
                    description="Powerplay conflict zones recorded from your own journal: the zones (by intensity and count) in the current "
                                "system right now, and every system where zones were seen with when and how hot. This is live and exact, "
                                "unlike Spansh-derived guesses; scout a candidate system and this tells you what is there.")
