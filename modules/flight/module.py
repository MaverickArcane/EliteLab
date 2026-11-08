"""Ephemeral session observations. Snapshot files do not identify their commander."""
import copy
import math
import threading
from datetime import datetime, timezone

from elitelab.core.gamedata import norm


def timestamp(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def age(at):
    return max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds()) if at else None


def coords(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(type(x) in (int, float) and math.isfinite(x) for x in value)


DIRTY = {"ModuleBuy", "ModuleSell", "ModuleStore", "ModuleRetrieve", "ModuleSwap", "ShipyardSwap", "EngineerCraft", "EngineerLegacyConvert"}
OBSERVED = {"Loadout", "Location", "FSDJump", "CarrierJump", "Docked", "NavRouteClear", "Materials", "Shutdown"} | DIRTY


class Flight:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.state = {}
        core.bus.on("journal.*", self.on_event)

    def on_event(self, name, e):
        if not isinstance(e, dict):
            return
        at = timestamp(e.get("timestamp"))
        if not at:
            return
        with self.lock:
            identity = self.core.store.get("progression")
            since = identity.get("session_started_at")
            commander = identity.get("commander")
            if not commander or not since or at < since:
                return
            if self.state.get("commander") != commander or self.state.get("session_started_at") != since:
                self.state = {"commander": commander, "session_started_at": since, "observations": {}}
            kind = e.get("event")
            snapshot = name.removeprefix("journal.file.") if name.startswith("journal.file.") else None
            if snapshot:
                if snapshot not in ("NavRoute", "ModulesInfo", "Status", "Cargo"):
                    return
                label = "route" if snapshot == "NavRoute" else snapshot.lower()
                if at < self.state.get(label, {}).get("observed_at", ""):
                    return
                if snapshot == "NavRoute" and at <= self.state.get("route_cleared_at", ""):
                    return
                self.state[label] = {"observed_at": at, "source": name, "data": copy.deepcopy(e)}
            elif kind in OBSERVED:
                previous = self.state["observations"].get(kind, "")
                if at < previous:
                    return
                self.state["observations"][kind] = at
                if kind == "Loadout" and at >= self.state.get("loadout", {}).get("observed_at", ""):
                    self.state["loadout"] = {"observed_at": at, "source": name, "data": copy.deepcopy(e)}
                    if at >= self.state.get("loadout_dirty_at", ""):
                        self.state.pop("loadout_dirty_at", None)
                elif kind in DIRTY:
                    self.state["loadout_dirty_at"] = max(at, self.state.get("loadout_dirty_at", ""))
                elif kind in ("Location", "FSDJump", "CarrierJump", "Docked") and at >= self.state.get("location", {}).get("observed_at", ""):
                    previous = self.state.get("location", {})
                    pos = e.get("StarPos")
                    if kind == "Docked" and e.get("StarSystem") == previous.get("system"):
                        pos = previous.get("coordinates")
                    self.state["location"] = {"system": e.get("StarSystem"), "coordinates": pos, "observed_at": at}
                elif kind == "NavRouteClear":
                    self.state["route_cleared_at"] = at
                    if at >= self.state.get("route", {}).get("observed_at", ""):
                        self.state["route"] = {"observed_at": at, "source": name, "data": {"Route": []}}
            else:
                return
            self.core.store.update("flight", {"commander": commander, "session_started_at": since,
                                             "observations": self.state["observations"],
                "context": {k: self.state.get(k) for k in ("commander", "session_started_at", "loadout", "loadout_dirty_at", "location")}})

    def navigation(self, q):
        limit = int(q.get("limit", 20))
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1-100")
        with self.lock:
            route = self.state.get("route", {})
            nodes = route.get("data", {}).get("Route", [])
            loc = self.state.get("location", {})
            indices = [i for i, r in enumerate(nodes) if r.get("StarSystem") == loc.get("system")]
            index = indices[0] if len(indices) == 1 else None
            status = "unknown" if not route else "cleared" if not nodes else "ambiguous_position" if len(indices) > 1 else "off_route" if index is None else "arrived" if index == len(nodes) - 1 else "plotted"
            remaining = nodes[index + 1:] if index is not None else []
            rows, distance = [], 0.0
            previous = nodes[index] if index is not None else None
            for node in remaining:
                segment = math.dist(previous["StarPos"], node["StarPos"]) if coords(previous.get("StarPos")) and coords(node.get("StarPos")) else None
                distance = distance + segment if distance is not None and segment is not None else None
                rows.append({"system": node.get("StarSystem"), "star_class": node.get("StarClass"),
                             "distance_from_previous_ly": round(segment, 3) if segment is not None else None})
                previous = node
            return copy.deepcopy({"commander": self.state.get("commander"), "current_location": loc, "status": status,
                "route_observed_at": route.get("observed_at"), "route_age_seconds": age(route.get("observed_at")),
                "destination": nodes[-1].get("StarSystem") if nodes else None,
                "remaining_jumps": len(remaining) if index is not None else None,
                "remaining_distance_ly": round(distance, 3) if index is not None and distance is not None else None,
                "next_system": remaining[0].get("StarSystem") if remaining else None, "remaining_route": rows[:limit],
                "truncated": len(rows) > limit, "note": "Last plotted ship route, not a carrier jump plan or permit confirmation. "
                "Off-route observations have no inferred next jump. Fuel availability, jump feasibility and safety are not simulated."})

    def modules(self, q):
        with self.lock:
            loadout = self.state.get("loadout", {})
            data = loadout.get("data", {})
            modules = data.get("Modules", [])
            power = self.state.get("modulesinfo", {})
            by_slot = {r.get("Slot"): r for r in modules}
            power_rows = power.get("data", {}).get("Modules", [])
            matches = bool(loadout and power_rows) and power.get("observed_at", "") >= loadout.get("observed_at", "")
            matches = matches and all(norm(r.get("Item")) == norm(by_slot.get(r.get("Slot"), {}).get("Item")) for r in power_rows)
            matches = matches and not self.state.get("loadout_dirty_at")
            reported = {r.get("Slot"): r for r in power_rows} if matches else {}
            result = []
            for row in modules:
                if q.get("slot") and str(q["slot"]).casefold() not in str(row.get("Slot", "")).casefold():
                    continue
                if q.get("item") and str(q["item"]).casefold() not in str(row.get("Item", "")).casefold():
                    continue
                result.append({"slot": row.get("Slot"), "item": row.get("Item"), "on": row.get("On"),
                               "priority": row.get("Priority"), "health": row.get("Health"),
                               "engineering": copy.deepcopy(row.get("Engineering")),
                               "reported_power_mw": reported.get(row.get("Slot"), {}).get("Power")})
            return {"commander": copy.deepcopy(self.state.get("commander")), "ship_id": data.get("ShipID"), "ship": data.get("Ship"),
                    "ship_name": data.get("ShipName"), "loadout_observed_at": loadout.get("observed_at"),
                    "loadout_changed_since_observation": bool(self.state.get("loadout_dirty_at")),
                    "power_report_matches_loadout": bool(matches), "power_observed_at": power.get("observed_at"),
                    "modules": result, "total_modules": len(modules),
                    "note": "Actual Loadout fields, separate from the pinned target. Power report is joined only when its date and every slot/item match. "
                            "Reported module power is not instantaneous draw. No inferred heat or sustained-fire simulation."}

    def freshness(self, q):
        threshold = int(q.get("max_age_seconds", 300))
        if not 1 <= threshold <= 86400:
            raise ValueError("max_age_seconds must be 1-86400")
        with self.lock:
            result = []
            for label in ("loadout", "route", "status", "cargo", "modulesinfo", "location"):
                at = self.state.get(label, {}).get("observed_at")
                elapsed = age(at)
                result.append({"data": label, "observed_at": at, "age_seconds": round(elapsed, 1) if elapsed is not None else None,
                               "status": "missing" if at is None else "older_than_threshold" if elapsed > threshold else "recent"})
            return {"commander": copy.deepcopy(self.state.get("commander")), "session_started_at": self.state.get("session_started_at"),
                    "observations": result, "max_age_seconds": threshold,
                    "shutdown_observed_at": self.state.get("observations", {}).get("Shutdown"),
                    "limitations": ["Old event-driven loadouts can still be correct; age alone does not prove a change.",
                                    "Snapshot files have no commander ID; observations older than the active session are excluded.",
                                    "Permit inventory and available mission boards are not exposed by journals."]}


def setup(core, module):
    f = Flight(core)
    for path, fn, tool, description, params in (
        ("navigation", f.navigation, "get_navigation_context", "Last plotted ship route, destination, next system and remaining jumps/distance, with clear/off-route/stale evidence. Does not prove permits.",
         {"limit": {"type": "integer", "default": 20, "description": "Maximum remaining route nodes, 1-100"}}),
        ("modules", f.modules, "get_ship_modules", "Inspect actual fitted modules and engineering modifiers, separate from the target build; joins dated matching ModulesInfo power reports only.",
         {"slot": {"type": "string", "description": "Optional slot substring"}, "item": {"type": "string", "description": "Optional internal module name substring"}}),
        ("freshness", f.freshness, "get_data_freshness", "Observation ages and missing telemetry for this session. Distinguishes age from invalidity and explains journal blind spots.",
         {"max_age_seconds": {"type": "integer", "default": 300, "description": "Age threshold 1-86400 seconds; does not declare old state incorrect"}})
    ):
        core.http.route("/api/flight/" + path, fn, tool=tool, description=description, params=params, module=module.name)
