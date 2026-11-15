"""Surface mining notebook and journal evidence, independent of ring mining.

Cargo/MiningRefined/CargoTransfer: Frontier Player Journal manual v34.
LaunchSRV SRVType=mev_rhino and SRV cargo: observed 2026-11-15.
Neither rig placement nor deposit footprints/stock are journal telemetry.
"""
import copy
import datetime as dt
import math
import threading
import time
import uuid

from elitelab.core.gamedata import norm

NS = "rhino"
CAPACITY = 72
MAX_SITES = 100
REFERENCE = {
    "id": "shinrarta-tritium", "name": "Shinrarta tritium cluster",
    "system": "Shinrarta Dezhra", "body": "Shinrarta Dezhra AB 2 j",
    "latitude": 35.9491, "longitude": -31.2339, "radius_m": 5963896,
    "commodity": "Tritium", "rigs": 3, "reported_at": "2026-11-15",
    "notes": "Three working rigs reported near the video's 2:11 position. Current reserves and rig fit must be checked on arrival.",
    "source": "https://www.youtube.com/watch?v=pmkU1LqwPjA&t=131s", "reference": True,
}


def stamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return None


def text(value, limit=160):
    return value.strip()[:limit] if isinstance(value, str) else ""


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and low <= value <= high else None
    except OverflowError:
        return None


def integer(value, high=1000000):
    value = number(value, 0, high)
    return int(value) if value is not None and value == int(value) else None


def required_number(q, key, low, high, whole=False):
    value = number(q.get(key), low, high)
    if value is None or (whole and int(value) != value):
        raise ValueError(f"{key} must be {'an integer' if whole else 'a number'} between {low} and {high}")
    return int(value) if whole else value


def navigation(position, site, now=None):
    result = {"distance_m": None, "bearing": None, "reason": "Choose a site"}
    if not site:
        return result
    when = stamp(position.get("timestamp"))
    now = time.time() if now is None else now
    if when is None or now - when > 120 or when - now > 5:
        result["reason"] = "Waiting for a recent surface position"
    elif (position.get("system", "").casefold() != site["system"].casefold() or
          position.get("body", "").casefold() != site["body"].casefold()):
        result["reason"] = "Approach the saved body"
    elif position.get("latitude") is None or position.get("longitude") is None:
        result["reason"] = "Surface coordinates unavailable"
    else:
        radius = number(position.get("radius_m"), 1, 1e10) or number(site.get("radius_m"), 1, 1e10)
        if radius is None:
            result["reason"] = "Waiting for the body's radius"
            return result
        a, b = math.radians(position["latitude"]), math.radians(site["latitude"])
        lon = math.radians(site["longitude"] - position["longitude"])
        h = min(1, max(0, math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(lon/2)**2))
        distance = radius * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))
        y, x = math.sin(lon)*math.cos(b), math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(lon)
        result.update(distance_m=round(distance, 1), bearing=None if distance < 1 else round(math.degrees(math.atan2(y, x)) % 360, 1) % 360,
                      reason="At saved coordinates" if distance < 25 else "Surface distance and initial heading")
    return result


class Rhino:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        saved = core.read_data("rhino-sites.json", default={})
        self.accounts = saved if isinstance(saved, dict) else {}
        self.commander = self.identity = ""
        self.reset()
        core.bus.on("journal.*", self.event)
        self.publish()

    def reset(self):
        self.system = self.body = ""
        self.position = {}
        self.cargo = {"ship": {}, "srv": {}}
        self.ship_capacity = None
        self.session = None
        self.rigs = None
        self.rigs_at = None
        self.game_start = None
        self.running = True

    def account(self):
        value = self.accounts.get(self.identity, {})
        return value if isinstance(value, dict) else {}

    def sites(self):
        rows = self.account().get("sites", [])
        result = [copy.deepcopy(REFERENCE)]
        for row in rows[:MAX_SITES] if isinstance(rows, list) else []:
            if (isinstance(row, dict) and text(row.get("id")) and text(row.get("name")) and
                    text(row.get("system")) and text(row.get("body")) and
                    number(row.get("latitude"), -90, 90) is not None and number(row.get("longitude"), -180, 180) is not None):
                if row["id"] == REFERENCE["id"]:
                    continue
                clean = {key: text(row.get(key), 1200 if key == "notes" else 160)
                         for key in ("id", "name", "system", "body", "commodity", "notes", "reported_at")}
                clean.update(latitude=row["latitude"], longitude=row["longitude"],
                             radius_m=number(row.get("radius_m"), 1, 1e10), rigs=integer(row.get("rigs"), 6), reference=False)
                result.append(clean)
        return result

    def selected(self):
        return next((s for s in self.sites() if s["id"] == self.account().get("selected")), None)

    def change_account(self, account):
        if not self.identity:
            raise ValueError("Wait for the commander's journal before saving sites")
        updated = {**self.accounts, self.identity: account}
        self.core.write_data(updated, "rhino-sites.json")
        self.accounts = updated
        self.publish()

    def save_site(self, q):
        with self.lock:
            site = {k: text(q.get(k), 1200 if k == "notes" else 160) for k in ("name", "system", "body", "commodity", "notes")}
            if any(not site[k] for k in ("name", "system", "body", "commodity")):
                raise ValueError("name, system, body and commodity are required")
            site.update(latitude=required_number(q, "latitude", -90, 90), longitude=required_number(q, "longitude", -180, 180),
                        rigs=required_number(q, "rigs", 0, 6, True), reported_at=dt.datetime.now(dt.timezone.utc).isoformat(), reference=False)
            site["radius_m"] = number(q.get("radius_m"), 1, 1e10)
            if q.get("radius_m") is not None and site["radius_m"] is None:
                raise ValueError("radius_m must be a positive radius in metres")
            rows = [s for s in self.sites() if not s.get("reference")]
            site_id = text(q.get("id"))
            if site_id and not any(s["id"] == site_id for s in rows):
                raise ValueError("Unknown editable site")
            if not site_id and len(rows) >= MAX_SITES:
                raise ValueError("The notebook is full (100 sites)")
            site["id"] = site_id or uuid.uuid4().hex
            rows = [s for s in rows if s["id"] != site["id"]] + [site]
            self.change_account({"sites": rows, "selected": site["id"]})
            return copy.deepcopy(site)

    def select_site(self, q):
        with self.lock:
            if not isinstance(q.get("id"), str):
                raise ValueError("id must be a string; use an empty string to clear the target")
            site_id = text(q.get("id"))
            if site_id and not any(s["id"] == site_id for s in self.sites()):
                raise ValueError("Unknown site")
            self.change_account({**self.account(), "selected": site_id})
            return self.view({})

    def remove_site(self, q):
        with self.lock:
            site_id = text(q.get("id"))
            rows = [s for s in self.sites() if not s.get("reference")]
            if not any(s["id"] == site_id for s in rows):
                raise ValueError("Unknown editable site")
            account = {**self.account(), "sites": [s for s in rows if s["id"] != site_id]}
            if account.get("selected") == site_id:
                account["selected"] = ""
            self.change_account(account)
            return {"removed": site_id}

    def report_rigs(self, q):
        with self.lock:
            count = required_number(q, "count", 0, 6, True)
            if not self.session or not self.session["active"]:
                raise ValueError("Deploy the Rhino before reporting working rigs")
            self.rigs, self.rigs_at = count, dt.datetime.now(dt.timezone.utc).isoformat()
            self.publish()
            return {"count": count, "source": "commander report", "reported_at": self.rigs_at}

    def start(self, ev):
        self.session = {"active": True, "started_at": text(ev.get("timestamp")), "as_of": text(ev.get("timestamp")),
                        "ended_reason": None, "system": self.system, "body": self.body,
                        "commodities": {}, "refined_tons": 0, "transferred_tons": 0, "unloads": 0,
                        "transfers": [], "timing_incomplete": stamp(ev.get("timestamp")) is None}
        self.rigs = self.rigs_at = None
        self.cargo["srv"] = {}

    def end(self, reason):
        if self.session and self.session["active"]:
            self.session.update(active=False, ended_reason=reason)
        self.rigs = self.rigs_at = None

    def observe_cargo(self, ev):
        vessel = text(ev.get("Vessel")).lower()
        count = integer(ev.get("Count"))
        when = stamp(ev.get("timestamp"))
        if vessel not in self.cargo or count is None or when is None:
            return
        if self.game_start is not None and when < self.game_start:
            return
        previous = stamp(self.cargo[vessel].get("timestamp"))
        if previous is None or when >= previous:
            self.cargo[vessel] = {"count": count, "timestamp": ev["timestamp"], "source": "Cargo observation"}

    def transfer(self, ev):
        rows = ev.get("Transfers")
        if not isinstance(rows, list) or len(rows) > 256:
            return
        # An active Rhino deployment gives direction=toship its SRV context.
        # Reject a carrier transfer rather than interpreting its toship leg as an unload.
        if any(isinstance(r, dict) and r.get("Direction") not in ("toship", "tosrv") for r in rows):
            return
        out = sum(integer(r.get("Count")) or 0 for r in rows if isinstance(r, dict) and r.get("Direction") == "toship")
        back = sum(integer(r.get("Count")) or 0 for r in rows if isinstance(r, dict) and r.get("Direction") == "tosrv")
        if out:
            self.session["transferred_tons"] += out
            self.session["unloads"] += 1
            self.session["transfers"] = (self.session["transfers"] + [{"timestamp": text(ev.get("timestamp")), "tons": out}])[-12:]
        when = stamp(ev.get("timestamp"))
        for vessel, delta in (("ship", out-back), ("srv", back-out)):
            old = self.cargo[vessel]
            before = stamp(old.get("timestamp"))
            if when is not None and before is not None and when > before and old.get("count") is not None:
                total = old["count"] + delta
                self.cargo[vessel] = {"count": total if total >= 0 else None, "timestamp": ev["timestamp"], "source": "Cargo plus recorded transfers"}

    def event(self, name, ev):
        with self.lock:
            if name == "journal.replay.done":
                self.publish()
                return
            if not isinstance(ev, dict):
                return
            e = ev.get("event")
            if self.session and self.session["active"]:
                when, previous = stamp(ev.get("timestamp")), stamp(self.session.get("as_of"))
                if when is not None and (previous is None or when > previous):
                    self.session["as_of"] = ev["timestamp"]
            if e in ("LoadGame", "Commander"):
                commander = text(ev.get("Commander") if e == "LoadGame" else ev.get("Name"))
                identity = ("fid:" + text(ev["FID"]) if text(ev.get("FID")) else
                            self.identity if commander and commander == self.commander else "name:" + commander if commander else "")
                if e == "LoadGame" or (identity and identity != self.identity):
                    self.reset()
                    self.game_start = stamp(ev.get("timestamp"))
                if e == "LoadGame":
                    self.commander, self.identity = commander, identity
                else:
                    self.commander, self.identity = commander or self.commander, identity or self.identity
                if e == "LoadGame" and text(ev.get("Ship")).lower() == "mev_rhino":
                    self.start(ev)
            elif e == "Status" or name == "journal.file.Status":
                when = stamp(ev.get("timestamp"))
                previous_position = stamp(self.position.get("timestamp"))
                if (self.running and when is not None and (self.game_start is None or when >= self.game_start)
                        and (previous_position is None or when >= previous_position)):
                    flags = integer(ev.get("Flags"), 2**40) or 0
                    valid = bool(flags & (1 << 21))
                    self.position = {"system": self.system, "body": text(ev.get("BodyName")), "timestamp": ev.get("timestamp"),
                                     "latitude": number(ev.get("Latitude"), -90, 90) if valid else None,
                                     "longitude": number(ev.get("Longitude"), -180, 180) if valid else None,
                                     "radius_m": number(ev.get("PlanetRadius"), 1, 1e10), "heading": number(ev.get("Heading"), 0, 360)}
            elif e in ("Location", "FSDJump", "CarrierJump", "ApproachBody", "SupercruiseExit"):
                self.system = text(ev.get("StarSystem")) or self.system
                self.body = text(ev.get("Body")) if ev.get("BodyType") != "Star" else ""
                self.position = {}
                if self.session and self.session["active"] and self.body:
                    self.session.update(system=self.system, body=self.body)
            elif e in ("LeaveBody", "SupercruiseEntry", "StartJump"):
                self.body = ""
                self.position = {}
                self.end("Left the surface")
            elif e == "Loadout":
                if text(ev.get("Ship")).lower() != "mev_rhino":
                    self.ship_capacity = integer(ev.get("CargoCapacity"))
            elif e in ("ShipyardSwap", "ShipyardNew", "ShipyardBuy"):
                self.ship_capacity = None
                self.cargo["ship"] = {}
                self.end("Changed ship")
            elif e == "Cargo" or name == "journal.file.Cargo":
                self.observe_cargo(ev)
            elif e == "LaunchSRV":
                if text(ev.get("SRVType")).lower() == "mev_rhino" and ev.get("PlayerControlled") is True:
                    self.start(ev)
                else:
                    self.end("Another SRV deployed")

            active = self.session and self.session["active"]
            if active:
                when = stamp(ev.get("timestamp"))
                if e == "MiningRefined":
                    key = norm(text(ev.get("Type"))) or "unknown"
                    if key not in self.session["commodities"] and len(self.session["commodities"]) >= 128:
                        key = "unknown"
                    row = self.session["commodities"].setdefault(key, {"key": key, "name": text(ev.get("Type_Localised")) or key.title(), "tons": 0})
                    row["tons"] += 1
                    self.session["refined_tons"] += 1
                    if when is None:
                        self.session["timing_incomplete"] = True
                elif e == "CargoTransfer":
                    self.transfer(ev)
                elif e in ("DockSRV", "SRVDestroyed", "Shutdown", "Died"):
                    self.end({"DockSRV": "Boarded ship", "SRVDestroyed": "SRV destroyed", "Shutdown": "Game session ended", "Died": "Commander died"}[e])
            if e == "Shutdown":
                self.running = False
                self.position = {}
            if not ev.get("_replay"):
                self.publish()

    def view(self, q):
        with self.lock:
            session = copy.deepcopy(self.session)
            if session:
                start, end = stamp(session["started_at"]), stamp(session["as_of"])
                elapsed = max(0, end-start) if start is not None and end is not None else None
                session["elapsed_seconds"] = elapsed
                rate_ok = elapsed is not None and elapsed >= 60 and not session["timing_incomplete"]
                session["tons_per_hour"] = round(session["refined_tons"] * 3600 / elapsed, 1) if rate_ok else None
                session["commodities"] = sorted(session["commodities"].values(), key=lambda r: (-r["tons"], r["key"]))
                for row in session["commodities"]:
                    row["tons_per_hour"] = round(row["tons"] * 3600 / elapsed, 1) if rate_ok else None
            cargo = copy.deepcopy(self.cargo)
            for vessel, capacity in (("ship", self.ship_capacity), ("srv", CAPACITY)):
                count = cargo[vessel].get("count")
                cargo[vessel].update(capacity=capacity, free=capacity-count if count is not None and capacity is not None and count <= capacity else None)
            site = self.selected()
            return {"commander": self.commander, "sites": self.sites(), "selected_site": site,
                    "position": copy.deepcopy(self.position), "navigation": navigation(self.position, site),
                    "cargo": cargo, "session": session, "rigs": {"count": self.rigs, "reported_at": self.rigs_at, "source": "commander report"},
                    "rate_note": "Collected tonnes per recorded hour since this Rhino deployment, including setup, driving and unloading. Updates with journal activity; stops at boarding or logout.",
                    "telemetry_note": "Rig positions, hopper contents, efficiency, remaining rig inventory and deposit reserves are not reported by the journal."}

    def publish(self):
        self.core.store.set(NS, "summary", self.view({}))


def setup(core, module):
    rhino = Rhino(core)
    def route(path, fn, tool, description, params=None, method="GET"):
        core.http.route("/api/rhino" + path, fn, tool=tool, module=module.name, description=description, params=params, method=method)
    route("", rhino.view, "get_rhino_status", "Rhino surface mining: commander-scoped saved sites, recent Status coordinates, same-body bearing/distance, separate SRV/ship cargo and current/last deployment yield. Only identified player-controlled Rhino deployments count MiningRefined (one tonne each). Rates include setup/driving/unloading and stop on boarding/logout. Cargo transfer totals are receipts, not extra production or sales. Rig counts are manual reports; no automatic deposit, rig or efficiency telemetry. Reference sites are dated reports, not current reserve guarantees.")
    fields = {k: {"type": "string", "required": True} for k in ("name", "system", "body", "commodity")}
    fields.update({"latitude": {"type": "number", "required": True}, "longitude": {"type": "number", "required": True},
                   "rigs": {"type": "integer", "required": True, "description": "Reported rig fit, 0-6; not live telemetry"},
                   "radius_m": {"type": "number"}, "notes": {"type": "string"}, "id": {"type": "string", "description": "Existing personal site ID to update; omit to create"}})
    route("/sites/save", rhino.save_site, "save_rhino_site", "Save or update one local surface mining site for this commander. Latitude then longitude in degrees; radius in metres if known. User reports only, no game actions or public upload. Up to 100 personal sites.", fields, "POST")
    route("/sites/select", rhino.select_site, "select_rhino_site", "Select a saved/reference site for navigation. Does not set an in-game waypoint. Empty ID clears selection.", {"id": {"type": "string", "required": True}}, "POST")
    route("/sites/remove", rhino.remove_site, "remove_rhino_site", "Remove a personal site from this commander's local notebook. Built-in reference cannot be removed.", {"id": {"type": "string", "required": True}}, "POST")
    route("/rigs", rhino.report_rigs, "report_rhino_rigs", "Record the commander's manually confirmed working rig count (0-6) for this deployment. Clears on boarding, logout or next deployment. Does not deploy or recover rigs.", {"count": {"type": "integer", "required": True}}, "POST")
