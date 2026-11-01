"""Journal evidence for unlock planning. Absence of evidence is never a denial."""
import copy
import glob
import json
import math
import os
import threading
from datetime import datetime, timezone

from elitelab.core.gamedata import norm
from elitelab.core import unlock_research


def key(value):
    return " ".join(str(value or "").casefold().split())


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


EVENTS = ("Fileheader", "Commander", "LoadGame", "Location", "FSDJump", "CarrierJump", "Docked",
          "MissionAccepted", "MissionCompleted", "MissionFailed", "MissionAbandoned", "Missions",
          "EngineerContribution", "Cargo", "CargoDepot", "MissionRedirected", "Undocked", "Rank", "Promotion", "Statistics")


class Progression:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.accounts = core.read_data("progression.json", default={})
        self.active = self.stream = None
        self.active_at = None
        self.session_at = None
        self.awaiting_loadgame = False
        self.stream_location = {}
        self.files = 0
        for path in sorted(glob.glob(os.path.join(core.config.JOURNAL_DIR, "Journal*.log"))):
            # Identity may not carry across a missing or truncated session header.
            self.stream = None
            self.stream_location = {}
            try:
                with open(path, encoding="utf-8") as handle:
                    for line in handle:
                        if not any('"' + event + '"' in line for event in EVENTS):
                            continue
                        try:
                            self.fold(json.loads(line))
                        except (ValueError, TypeError, AttributeError):
                            continue
                self.files += 1
            except OSError:
                continue
        for event in EVENTS:
            core.bus.on("journal." + event, self.on_event)
        core.bus.on("journal.file.Cargo", self.on_cargo)
        core.bus.on("journal.replay.done", self.on_replay)
        self.publish()

    def account(self):
        return self.accounts.get((self.active or {}).get("key"), {})

    @staticmethod
    def put(table, name, row):
        if row["observed_at"] >= table.get(name, {}).get("observed_at", ""):
            table[name] = row

    def fold(self, e):
        kind, at = e.get("event"), stamp(e.get("timestamp"))
        if kind == "Fileheader":
            self.stream = None
            self.stream_location = {}
            return
        if kind in ("Commander", "LoadGame"):
            name = e.get("Name") if kind == "Commander" else e.get("Commander")
            fid = e.get("FID")
            if not name and not fid:
                return
            if not fid and self.stream and key(name) == key(self.stream["name"]):
                fid = self.stream["fid"]
            identity = {"key": "fid:" + str(fid) if fid else "name:" + key(name), "fid": fid, "name": name}
            if self.stream != identity:
                self.stream_location = {}
            self.stream = identity
            if not self.active or (at and at >= (self.active_at or "")):
                newer = not self.active_at or (at and at > self.active_at)
                if self.active != identity or kind == "Commander" or (newer and not self.awaiting_loadgame):
                    self.session_at = at
                if newer or self.active != identity:
                    self.awaiting_loadgame = kind == "Commander"
                self.active, self.active_at = identity, at
            self.accounts.setdefault(identity["key"], {"permits": {}, "visits": {}, "factions": {},
                                                     "missions": {}, "contributions": {}})
            return
        if not self.stream or not at:
            return
        a = self.accounts[self.stream["key"]]
        evidence = {"observed_at": at, "source": "journal." + kind}
        if kind in ("Cargo", "CargoDepot", "MissionCompleted"):
            a["cargo_changed_at"] = max(at, a.get("cargo_changed_at", ""))
        if kind == "Undocked":
            self.stream_location.pop("station", None)
        if kind in ("Rank", "Promotion"):
            for field in ("Combat", "Trade", "Explore", "Empire", "Federation"):
                if number(e.get(field)):
                    self.put(a.setdefault("ranks", {}), field, {**evidence, "value": e[field]})
        if kind == "Statistics" and at >= a.get("statistics", {}).get("observed_at", ""):
            a["statistics"] = {**evidence, "values": {k: e[k] for k in ("Exploration", "Trading", "Smuggling", "Mining", "Combat") if isinstance(e.get(k), dict)}}
        if kind in ("Location", "FSDJump", "CarrierJump", "Docked") and e.get("StarSystem"):
            system = e["StarSystem"]
            self.put(a["visits"], key(system), {**evidence, "system": system})
            if kind == "FSDJump":
                self.put(a.setdefault("ship_jumps", {}), key(system), {**evidence, "system": system})
            loc = {**evidence, "system": system, "station": e.get("StationName"),
                   "station_faction": (e.get("StationFaction") or {}).get("Name")}
            self.stream_location = dict(loc)
            if kind == "Docked" and key(system) == key(a.get("location", {}).get("system")):
                loc = {**a["location"], **loc}
            if isinstance(e.get("Factions"), list):
                loc["factions"] = [r["Name"] for r in e["Factions"] if r.get("Name")]
                loc["factions_observed_at"] = at
                for row in e["Factions"]:
                    rep = row.get("MyReputation")
                    if row.get("Name") and number(rep):
                        self.put(a["factions"], key(row["Name"]), {**evidence, "name": row["Name"],
                                 "reputation": rep, "system": system})
            if at >= a.get("location", {}).get("observed_at", ""):
                a["location"] = loc
        if kind == "MissionCompleted":
            for permit in e.get("PermitsAwarded", []):
                if isinstance(permit, str) and permit.strip():
                    self.put(a["permits"], key(permit), {**evidence, "permit": permit, "mission_id": e.get("MissionID")})
        if kind == "MissionAccepted" and "MissionID" in e:
            # Backfill original requirements even when a newer cached outcome exists.
            row = a["missions"].setdefault(str(e["MissionID"]), {})
            for source, dest in (("Commodity", "commodity"), ("Commodity_Localised", "commodity_name"),
                                 ("Count", "count"), ("Wing", "wing"), ("Name", "name"),
                                 ("LocalisedName", "title"), ("Faction", "faction"), ("Expiry", "expiry"),
                                 ("DestinationSystem", "destination_system"), ("DestinationStation", "destination_station")):
                if source in e:
                    row.setdefault(dest, e[source])
            row.setdefault("accepted_at", at)
            row.setdefault("origin_system", self.stream_location.get("system"))
            row.setdefault("origin_station", self.stream_location.get("station"))
        if kind == "CargoDepot" and "MissionID" in e:
            row = a["missions"].setdefault(str(e["MissionID"]), {"mission_id": e["MissionID"], "status": "unknown", "observed_at": at})
            if at >= row.get("depot", {}).get("observed_at", ""):
                row["depot"] = {**evidence, **{k: e[k] for k in ("ItemsCollected", "ItemsDelivered", "TotalItemsToDeliver", "StartMarketID", "EndMarketID") if k in e}}
        if kind.startswith("Mission") and "MissionID" in e:
            mid = str(e["MissionID"])
            old = a["missions"].get(mid, {})
            if at >= old.get("observed_at", ""):
                status = old.get("status", "accepted") if kind == "MissionRedirected" else kind.removeprefix("Mission").lower()
                row = {**old, **evidence, "mission_id": e["MissionID"], "status": status}
                for source, dest in (("Faction", "faction"), ("LocalisedName", "title"), ("Name", "name"),
                                     ("DestinationSystem", "destination_system"), ("DestinationStation", "destination_station"),
                                     ("Expiry", "expiry"), ("CommodityReward", "commodity_rewards")):
                    if source in e:
                        row[dest] = e[source]
                self.put(a["missions"], mid, row)
        if kind == "Missions" and at >= a.get("missions_snapshot_at", ""):
            a["missions_snapshot_at"] = at
            active_ids = {str(r["MissionID"]) for r in e.get("Active", []) if "MissionID" in r}
            for mid, row in a["missions"].items():
                if row["status"] == "accepted" and mid not in active_ids and row["observed_at"] <= at:
                    row.update({**evidence, "status": "no_longer_active"})
            for group, status in (("Active", "accepted"), ("Failed", "failed"), ("Complete", "ready_to_turn_in")):
                for row in e.get(group, []):
                    if "MissionID" in row:
                        mid = str(row["MissionID"])
                        self.put(a["missions"], mid, {**a["missions"].get(mid, {}), **evidence,
                                                     "mission_id": row["MissionID"], "status": status})
        if kind == "EngineerContribution" and e.get("Engineer") and number(e.get("TotalQuantity")):
            item = e.get("Commodity") or e.get("Material") or e.get("Type") or ""
            ckey = key(e["Engineer"]) + ":" + norm(item)
            self.put(a["contributions"], ckey, {**evidence, "total": e["TotalQuantity"], "commodity": e.get("Commodity"), "kind": e.get("Type")})
        if kind == "Cargo" and e.get("Vessel", "Ship") == "Ship" and isinstance(e.get("Inventory"), list):
            if at >= a.get("cargo", {}).get("observed_at", ""):
                a["cargo"] = {**evidence, "items": e["Inventory"]}

    def publish(self):
        a = self.account()
        cargo = a.get("cargo")
        if cargo and cargo["observed_at"] < (self.active_at or ""):
            cargo = None
        self.core.store.update("progression", {"commander": self.active, "location": self.account().get("location"),
                                              "session_started_at": self.session_at,
                                              "active_missions": [r for r in a.get("missions", {}).values() if r.get("status") in ("accepted", "ready_to_turn_in")],
                                              "cargo": cargo,
                                              "cargo_changed_at": a.get("cargo_changed_at"),
                                              "exploration": {"observed_at": a.get("statistics", {}).get("observed_at"),
                                                  "values": a.get("statistics", {}).get("values", {}).get("Exploration", {})},
                                              "history_files_checked": self.files})

    def on_event(self, name, event):
        with self.lock:
            self.fold(event)
            if not event.get("_replay"):
                self.core.write_data(self.accounts, "progression.json")
            self.publish()

    def on_cargo(self, name, event):
        # Snapshot files lack FID: bind only when newer than the active session.
        if not isinstance(event, dict):
            return
        with self.lock:
            at = stamp(event.get("timestamp"))
            if self.active and self.active_at and at and at >= self.active_at:
                stream = self.stream
                self.stream = self.active
                self.fold({**event, "event": "Cargo"})
                self.stream = stream
                self.publish()

    def on_replay(self, name, event):
        with self.lock:
            self.core.write_data(self.accounts, "progression.json")

    def permits(self, q):
        with self.lock:
            a = self.account()
            system = q.get("system")
            rows = [v for k, v in a.get("permits", {}).items() if not system or k == key(system)]
            return copy.deepcopy({"commander": self.active, "system": system,
                "status": "grant_observed" if rows else "unknown", "grants": rows,
                "last_visit": a.get("visits", {}).get(key(system)) if system else None,
                "last_ship_jump": a.get("ship_jumps", {}).get(key(system)) if system else None,
                "complete_permit_list": False, "history_files_checked": self.files,
                "note": "Only MissionCompleted.PermitsAwarded confirms a recorded grant. Missing means unknown, not locked. "
                        "Visits and plotted routes do not establish current personal permit ownership."})

    def factions(self, q):
        with self.lock:
            a, wanted = self.account(), key(q.get("faction"))
            loc = a.get("location", {})
            names = {key(n): n for n in loc.get("factions", [])}
            names.update({k: r["name"] for k, r in a.get("factions", {}).items()})
            if wanted and wanted not in names:
                names[wanted] = q["faction"]
            rows = []
            for name, display in sorted(names.items()):
                if wanted and wanted not in name:
                    continue
                row = dict(a.get("factions", {}).get(name, {"name": display, "reputation": None, "observed_at": None}))
                row["present_in_current_system"] = (name in {key(n) for n in loc["factions"]}) if "factions" in loc else None
                rows.append(row)
            return copy.deepcopy({"commander": self.active, "location": loc, "factions": rows,
                "note": "Reputation is last observed Factions.MyReputation, not mission reward + indicators. "
                        "System faction presence is last observed; journals do not expose available mission boards."})

    def missions(self, q):
        with self.lock:
            limit = int(q.get("limit", 20))
            if not 1 <= limit <= 100:
                raise ValueError("limit must be 1-100")
            rows = [r for r in self.account().get("missions", {}).values()
                    if not q.get("faction") or key(q["faction"]) in key(r.get("faction"))]
            rows.sort(key=lambda r: r["observed_at"], reverse=True)
            return copy.deepcopy({"commander": self.active, "missions": rows[:limit], "total": len(rows),
                                  "mission_board_available": False, "note": "Accepted missions and journal outcomes only; status is last observed."})

    def unlock(self, q):
        record = unlock_research.resolve(q.get("engineer", "Marco Qwent"))
        with self.lock:
            eng = self.core.store.get("engineering")
            same = (eng.get("commander") or {}).get("key") == (self.active or {}).get("key")
            result = unlock_research.evaluate(record, self.account(), eng.get("engineers", []) if same else [])
            result["commander"] = copy.deepcopy(self.active)
            if record["name"] == "Marco Qwent":
                # Keep existing Qwent fields and travel-aware advice compatible.
                result.update(self.qwent_unlock(q))
            if record.get("faction"):
                result["faction_evidence"] = self.factions({"faction": record["faction"]})
            if record.get("permit"):
                result["permit_evidence"] = self.permits({"system": record["permit"]})
            return result

    def catalog(self, q):
        rows = []
        for record in unlock_research.DATA["engineers"]:
            if q.get("engineer") and key(q["engineer"]) not in key(record["name"]):
                continue
            result = self.unlock({"engineer": record["name"]})
            rows.append({k: result[k] for k in ("engineer", "location", "access", "referral_chain", "next_action", "sources")})
        return {"engineers": rows, "coverage": unlock_research.DATA["coverage"], "reviewed_on": unlock_research.DATA["reviewed_on"]}

    def qwent_unlock(self, q):
        with self.lock:
            eng = self.core.store.get("engineering")
            same = (eng.get("commander") or {}).get("key") == (self.active or {}).get("key")
            row = next((r for r in eng.get("engineers", []) if key(r["name"]) == "marco qwent"), {}) if same else {}
            state = row.get("progress", "unknown")
            a = self.account()
            donated = a.get("contributions", {}).get("marco qwent:modularterminals")
            cargo = a.get("cargo", {})
            aboard = sum(max(0, r.get("Count", 0) - r.get("Stolen", 0)) for r in cargo.get("items", [])
                         if norm(r.get("Name") or "") == "modularterminals") if cargo else None
            remaining = max(0, 25 - donated["total"]) if donated else None
            permit = self.permits({"system": "Sirius"})
            if state == "Unlocked":
                action = "Qwent is unlocked. Choose the required upgrade grade; no more unlock donations are needed."
            elif state == "Invited":
                action = "Visit Qwent Research Base in Sirius and check the remaining Modular Terminals donation (25 total)."
            elif state == "Known":
                if permit["last_ship_jump"]:
                    action = "Referral recorded and a ship jump into Sirius was observed at " + permit["last_ship_jump"]["observed_at"] + ". "
                    action += "If Sirius is still accessible, check the Sirius Corporation board for Qwent's invitation. "
                    action += "Missing grant history alone does not justify a permit grind."
                else:
                    action = "Referral recorded. Check Sirius access, then the Sirius Corporation board for Qwent's invitation. "
                    action += "Permit evidence is incomplete: check the in-game permit list before doing reputation work." if permit["status"] == "unknown" else "A Sirius permit grant is recorded."
            else:
                action = "Check Elvira Martuuk referral progress and the in-game Engineers panel; Qwent's referral is not recorded."
            return copy.deepcopy({"commander": self.active, "engineer": "Marco Qwent", "access": row or {"progress": "unknown"},
                "referral_observed": True if state in ("Known", "Invited", "Unlocked") else None,
                "invitation_observed": state in ("Invited", "Unlocked") if state != "unknown" else None,
                "unlocked": state == "Unlocked" if state != "unknown" else None,
                "sirius_permit": permit, "sirius_corporation": self.factions({"faction": "Sirius Corporation"}),
                "terminals": {"required_total": 25, "donation_evidence": donated, "remaining_to_donate": remaining,
                              "aboard_unstolen": aboard, "cargo_observed_at": cargo.get("observed_at")},
                "next_action": action, "sources": ["https://inara.cz/elite/engineer/7/"], "reviewed_on": "2026-10-31",
                "note": "Cargo is not a donation. Unknown contribution history is not zero. Mission availability is not observable."})


def setup(core, module):
    p = Progression(core)
    for path, fn, tool, description, params in (
        ("permits", p.permits, "get_permit_status", "Recorded permit grants and separate travel evidence. Missing permits remain unknown; never infer a complete permit list.",
         {"system": {"type": "string", "description": "Exact permit/system name; omit to list recorded grants"}}),
        ("factions", p.factions, "get_faction_reputation", "Last observed minor-faction reputation and presence in the current system, scoped to this commander.",
         {"faction": {"type": "string", "description": "Optional faction name filter"}}),
        ("missions", p.missions, "get_mission_progress", "Observed accepted missions and outcomes, including commodity rewards. Does not read mission boards.",
         {"faction": {"type": "string"}, "limit": {"type": "integer", "default": 20}}),
        ("catalog", p.catalog, "list_engineer_unlocks", "Reviewed unlock chains with your observed access, locations and next actions. Ten engineers; explicit source coverage.",
         {"engineer": {"type": "string", "description": "Optional name filter"}}),
        ("unlock", p.unlock, "get_engineer_unlock_progress", "Reviewed engineer referral chain, rank/statistic requirements, contributions and next step. Covers Farseer, Martuuk, Qwent, Palin, Dweller, Ryder, Tani, Tarquin, Nemo and Cheung.",
         {"engineer": {"type": "string", "default": "Marco Qwent"}}),
    ):
        core.http.route("/api/progression/" + path, fn, tool=tool, description=description, params=params, module=module.name)
