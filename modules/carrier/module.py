"""Pinned visitor carriers, identified by MarketID, with timestamped observations.

Journal data is local evidence; Spansh is a last-reported location, not live tracking.
Owner-only finance, fuel and capacity stay in journal.carrier.
"""
import copy
from datetime import datetime, timezone
import json
import math
import threading

from elitelab.core.watcher import journal_files

NS = "carrier"
REFRESH_SECONDS = 300
MAX_VISITED = 50


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        return 0


class Carriers:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.fetch_lock = threading.Lock()
        self.wake = threading.Event()
        saved = core.read_data("carrier.json", default={}) or {}
        self.records = saved.get("records", {})
        self.positions = {}
        self.selected = saved.get("selected")
        if self.selected not in self.records:
            self.selected = None
        self.generation = 0
        self.checked_at = None
        self.error = None
        self.refreshing = False
        self.worker = None
        for event in ("Docked", "Location", "CarrierJump", "FSDJump"):
            core.bus.on("journal." + event, self.on_event)
        core.bus.on("journal.replay.done", self.on_replay_done)
        core.bus.on("state.journal.star_pos", lambda n, v: self.publish())
        self.publish()

    def publish(self):
        with self.lock:
            pinned = copy.deepcopy(self.records.get(self.selected))
            if pinned:
                ship = self.core.store.get("journal", "star_pos")
                pos = pinned.get("star_pos")
                pinned["distance"] = round(math.dist(ship, pos), 1) if ship and pos else None
            visited = sorted(self.records.values(), key=lambda r: timestamp(r.get("last_seen")), reverse=True)
            self.core.store.update(NS, {
                "pinned": pinned,
                "visited": [{k: r.get(k) for k in ("market_id", "callsign", "system", "last_seen")} for r in visited],
                "checked_at": self.checked_at, "error": self.error, "refreshing": self.refreshing,
                "offline": self.core.config.OFFLINE,
            })

    def save(self):
        self.core.write_data({"selected": self.selected, "records": self.records}, "carrier.json")

    def on_event(self, name, ev):
        self.observe(ev, persist=not ev.get("_replay"))

    def observe(self, ev, persist=False):
        if ev.get("StarSystem") and ev.get("StarPos"):
            with self.lock:
                self.positions[ev["StarSystem"]] = ev["StarPos"]
        if ev.get("event") not in ("Docked", "Location", "CarrierJump") or ev.get("StationType") != "FleetCarrier":
            return
        if ev.get("event") != "Docked" and not ev.get("Docked"):
            return
        market_id = ev.get("MarketID")
        if not isinstance(market_id, int) or market_id <= 0 or not ev.get("StationName") or not ev.get("StarSystem"):
            return
        observed = ev.get("timestamp")
        if not timestamp(observed):
            return
        key = str(market_id)
        with self.lock:
            prev = self.records.get(key, {})
            if timestamp(observed) < timestamp(prev.get("last_seen")):
                return
            record = {**prev, "market_id": market_id, "callsign": ev["StationName"], "last_seen": observed}
            if timestamp(observed) >= timestamp(prev.get("observed_at")):
                pos = ev.get("StarPos") or self.positions.get(ev["StarSystem"])
                if pos is None and ev["StarSystem"] == prev.get("system"):
                    pos = prev.get("star_pos")
                record.update(system=ev["StarSystem"], star_pos=pos,
                              services=ev.get("StationServices", []), docking=None, source="journal", observed_at=observed)
            self.records[key] = record
            oldest = sorted(self.records, key=lambda k: timestamp(self.records[k].get("last_seen")))
            for old in oldest:
                if len(self.records) <= MAX_VISITED:
                    break
                if old != self.selected:
                    del self.records[old]
            if persist:
                self.save()
            self.publish()

    def scan_archive(self):
        # Runs off the watcher thread in the server; only observations, never emits replay events.
        for path in journal_files():
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if 'FleetCarrier' not in line and 'StarPos' not in line:
                            continue
                        try:
                            self.observe(json.loads(line))
                        except (ValueError, TypeError):
                            continue
            except OSError:
                continue
        with self.lock:
            self.save()

    def on_replay_done(self, name, payload):
        if self.core.watcher.is_alive():
            if self.worker is None:
                self.worker = threading.Thread(target=self.run, name="carrier-follow", daemon=True)
                self.worker.start()
        else:
            self.scan_archive()

    def run(self):
        self.scan_archive()
        while self.core.watcher.is_alive():
            self.wake.clear()
            self.refresh()
            self.wake.wait(REFRESH_SECONDS)

    def pin(self, market_id):
        key = str(market_id)
        with self.lock:
            if key not in self.records:
                raise ValueError("Choose a fleet carrier from the visited list.")
            self.selected = key
            self.generation += 1
            self.checked_at = self.error = None
            self.refreshing = False
            self.save()
            self.publish()
        self.wake.set()
        return self.core.store.get(NS)

    def unpin(self):
        with self.lock:
            self.selected = None
            self.generation += 1
            self.checked_at = self.error = None
            self.refreshing = False
            self.save()
            self.publish()
        return self.core.store.get(NS)

    def refresh(self):
        if not self.fetch_lock.acquire(blocking=False):
            return self.core.store.get(NS)
        try:
            with self.lock:
                key, generation = self.selected, self.generation
                if key is None or self.core.config.OFFLINE:
                    return self.core.store.get(NS)
                self.refreshing = True
                self.publish()
            error = None
            record = None
            try:
                data = self.core.services.fetch_json("https://spansh.co.uk/api/station/" + key, ttl=REFRESH_SECONDS)
                record = data.get("record") or {}
                if str(record.get("market_id")) != key or not record.get("system_name") or not timestamp(record.get("updated_at")):
                    raise ValueError("Carrier report is missing its identity, system or timestamp.")
                pos = [record.get("system_" + axis) for axis in ("x", "y", "z")]
                update = {
                    "system": record["system_name"],
                    "star_pos": pos if all(isinstance(v, (int, float)) and math.isfinite(v) for v in pos) else None,
                    "services": [s["name"] for s in (record.get("services") or []) if isinstance(s, dict) and s.get("name")],
                    "docking": record.get("carrier_docking_access"),
                    "source": "Spansh", "observed_at": record["updated_at"],
                }
            except Exception:
                error = "Could not retrieve a carrier report. Keeping the last known information."
            with self.lock:
                # A request may finish after the user changes or removes the pin.
                if key != self.selected or generation != self.generation:
                    return self.core.store.get(NS)
                self.checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                self.error = error
                self.refreshing = False
                if not error:
                    prev = self.records[key]
                    if timestamp(record["updated_at"]) > timestamp(prev.get("observed_at")):
                        prev.update(update)
                        self.save()
                self.publish()
                return self.core.store.get(NS)
        finally:
            self.fetch_lock.release()


def setup(core, module):
    carriers = Carriers(core)
    core.http.route("/api/carrier", lambda q: core.store.get(NS), tool="get_followed_carrier", module=module.name,
                    description="Pinned fleet carrier's last reported system, services, source and observation time; also up to 50 visited carriers available to pin. Remote reports may be stale. Owner-only fuel and finance remain in get_commander_state.")
    core.http.route("/api/carrier/pin", lambda q: carriers.pin(q.get("market_id")), method="POST",
                    tool="pin_fleet_carrier", module=module.name,
                    description="Persistently follow one visited fleet carrier. Choose its market_id from get_followed_carrier.visited. Replaces the previous pin; does not imply ownership.",
                    params={"market_id": {"type": "integer", "required": True, "description": "Market ID of a visited fleet carrier."}})
    core.http.route("/api/carrier/unpin", lambda q: carriers.unpin(), method="POST", tool="unpin_fleet_carrier", module=module.name,
                    description="Remove the pinned fleet carrier. Keeps visited carriers and restores the owned-carrier card if available.")
    core.http.route("/api/carrier/refresh", lambda q: carriers.refresh(), method="POST", tool="refresh_followed_carrier", module=module.name,
                    description="Check Spansh for the pinned carrier's last reported location and services. Cached for five minutes; older reports never replace newer journal observations. Offline mode keeps cached data.")
