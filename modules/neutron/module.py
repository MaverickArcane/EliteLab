"""Commander-scoped external route plans. No game input or network in event handlers."""
import copy
import csv
import io
import math
import threading
import time
import uuid
from datetime import datetime, timezone

from elitelab.core import neutron as n


def now():
    return datetime.now(timezone.utc).isoformat()


class Neutron:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.accounts = core.read_data("neutron.json", default={})
        self.inflight = set()
        self.polled = {}
        for topic in ("state.flight.context", "state.progression.commander", "state.progression.exploration", "state.synthesis.summary"):
            core.bus.on(topic, self.on_state)
        self.on_state()

    def identity(self):
        return self.core.store.get("progression", "commander") or {}

    def account(self):
        return self.accounts.get(self.identity().get("key"), {})

    def persist(self):
        self.core.write_data(self.accounts, "neutron.json")

    def replace_route(self, key, route):
        accounts = {**self.accounts, key: {**self.accounts.get(key, {}), "route": route}}
        self.core.write_data(accounts, "neutron.json")
        self.accounts = accounts

    def context(self):
        p = self.core.store.get("progression")
        f = self.core.store.get("flight", "context") or {}
        commander = p.get("commander")
        ship = n.ship_context(f, commander)
        loc = f.get("location") or {} if f.get("commander") == commander else {}
        j = self.core.store.get("journal")
        laden = j.get("jump_range_laden")
        same_ship = ship["ship_id"] is not None and ship["ship_id"] == (j.get("ship_info") or {}).get("id")
        ship["suggested_range_ly"] = math.floor(laden * 100) / 100 if same_ship and not ship["loadout_changed"] and n.numeric(laden) and laden > 0 else None
        synthesis = self.core.store.get("synthesis", "summary") or {}
        return {"commander": commander, "location": loc, "ship": ship,
                "boost_observation": synthesis.get("boost") if synthesis.get("commander") == commander else None,
                "palin": n.palin_check(p, self.account().get("route") or {})}

    def on_state(self, *args):
        with self.lock:
            route = copy.deepcopy(self.account().get("route") or {})
            context = self.context()
            loc = context["location"]
            if route.get("status") == "ready" and loc.get("observed_at", "") >= route.get("created_at", ""):
                points = route.get("waypoints", [])
                indices = [i for i, row in enumerate(points) if row["system"].casefold() == str(loc.get("system", "")).casefold()]
                if len(indices) == 1 and indices[0] > route.get("progress_index", -1):
                    route["progress_index"] = indices[0]
                    self.replace_route(self.identity()["key"], route)
            self.core.store.set("neutron", "summary", self.view({"limit": 5}))

    def view(self, q):
        limit = int(n.number(q.get("limit", 10), "limit", 1, 100))
        if float(q.get("limit", 10)) != limit:
            raise ValueError("limit must be an integer")
        with self.lock:
            context = self.context()
            route = copy.deepcopy(self.account().get("route") or {})
        points = route.pop("waypoints", [])
        index = route.get("progress_index", -1)
        current = str(context["location"].get("system") or "").casefold()
        matches = [i for i, r in enumerate(points) if r["system"].casefold() == current]
        at = matches[0] if len(matches) == 1 else None
        ship = context["ship"]
        changed_ship = route.get("ship_id") is not None and route.get("ship_id") != ship["ship_id"]
        changed_fit = bool(route and (ship["loadout_changed"] or route.get("fit_signature") != self.fit_signature()))
        route.pop("fit_signature", None)
        if context["location"].get("observed_at", "") < route.get("created_at", "") and at != 0:
            at = None
        navigation = "no_route"
        if points:
            navigation = "arrived" if at == len(points) - 1 else "at_waypoint" if at is not None and at >= index else "between_waypoints_or_off_route"
            if changed_ship or changed_fit:
                navigation = "ship_or_fit_changed"
        start = index + 1
        if at is not None and at >= index:
            start = at + 1
        next_point = points[start] if start < len(points) else None
        return {**context, "route": route or None, "navigation_status": navigation,
                "ship_changed": changed_ship, "fit_changed": changed_fit,
                "next_waypoint": next_point, "waypoint_count": len(points),
                "remaining_waypoints": max(0, len(points) - start),
                "waypoints": [{"index": i, **r} for i, r in enumerate(points[start:start + limit], start)],
                "truncated": len(points) - start > limit,
                "notes": ["Spansh neutron routes are waypoints; a leg may need multiple ordinary jumps. Plot each next waypoint in the game.",
                          "Refuelling stops are not planned. Leave the highway for scoopable stars as needed; K/G/B/F/O/A/M stars provide fuel.",
                          "Keep fuel in reserve, monitor FSD health and repair it with an AFMU or at a station. Scooping a neutron cone does not refill fuel.",
                          "No automatic clipboard changes, galaxy-map plotting or ship controls. Copy buttons act only when clicked.",
                          "A changed ship or fit needs a new range check and route. Being between waypoints does not confirm a wrong course."]}

    def fit_signature(self):
        f = self.core.store.get("flight", "context") or {}
        if f.get("commander") != self.identity():
            return None
        data = (f.get("loadout") or {}).get("data", {})
        # Stable across health/fuel updates; changes when relevant fitted hardware changes.
        return [{"slot": m.get("Slot"), "item": m.get("Item"), "engineering": m.get("Engineering")}
                for m in sorted(data.get("Modules", []), key=lambda m: m.get("Slot", "")) if not str(m.get("Slot", "")).startswith(("Paint", "ShipName", "ShipID", "WeaponColour", "EngineColour"))]

    def plan(self, q):
        destination = n.system_name(q.get("destination"), "Destination")
        context = self.context()
        key = (context["commander"] or {}).get("key")
        if not key:
            raise ValueError("Wait for commander identity before saving a route")
        source = n.system_name(q.get("source") or context["location"].get("system"), "Source")
        if source.casefold() == destination.casefold():
            raise ValueError("Source and destination must differ")
        jump_range = n.number(q.get("range_ly", context["ship"]["suggested_range_ly"]), "Normal unboosted range", 1, 200)
        signature = self.fit_signature()
        efficiency = n.number(q.get("efficiency", 60), "Efficiency", 1, 100)
        mode = q.get("supercharge", "auto")
        if mode not in ("auto", "4", "6"):
            raise ValueError("supercharge must be auto, 4 or 6")
        multiplier = context["ship"]["suggested_supercharge_multiplier"] if mode == "auto" else int(mode)
        career_name = n.system_name(q["career_start"], "Career start") if q.get("career_start") else None
        request = {"from": source, "to": destination, "range": jump_range, "efficiency": efficiency,
                   "supercharge_multiplier": multiplier}
        token = uuid.uuid4().hex
        with self.lock:
            if key in self.inflight:
                raise ValueError("A route request is already running")
            existing = self.accounts.get(key, {}).get("route") or {}
            if existing.get("status") in ("queued", "running"):
                raise ValueError("A route is still calculating; refresh it or clear it before submitting another")
            self.inflight.add(key)
        try:
            career = None
            if career_name:
                coords = self.core.services.edsm_coords([career_name])
                row = next((v for k, v in coords.items() if k.casefold() == career_name.casefold()), {})
                if n.position(row) is None:
                    raise ValueError("Could not resolve the supplied career starting system")
                career = {"system": career_name, "coordinates": n.position(row), "source": "user-supplied starting system; EDSM coordinates"}
            response = self.core.services.post_form(n.API + "/route", request)
            if not isinstance(response, dict) or response.get("status") != "queued":
                raise ValueError("Spansh could not queue route: " + str(response.get("error", response) if isinstance(response, dict) else response)[:300])
            job = n.job_id(response.get("job"))
            with self.lock:
                if self.identity().get("key") != key:
                    raise ValueError("Commander changed while submitting route; response was not saved")
                if signature != self.fit_signature() or self.context()["ship"]["loadout_changed"]:
                    raise ValueError("Ship fit changed while submitting route; check range and submit again")
                route = {"id": token, "job": job, "status": "queued", "created_at": now(), "request": request,
                         "ship_id": context["ship"]["ship_id"], "ship_name": context["ship"]["ship_name"],
                         "fit_signature": signature, "career_start": career,
                         "spansh_url": "https://spansh.co.uk/plotter/results/" + job,
                         "progress_index": -1, "waypoints": [], "poll_after_seconds": 5}
                self.replace_route(key, route)
                self.on_state()
            return self.view({})
        finally:
            with self.lock:
                self.inflight.discard(key)

    def refresh(self, q):
        with self.lock:
            key = self.identity().get("key")
            route = copy.deepcopy(self.account().get("route") or {})
            if not route or route.get("status") not in ("queued", "running"):
                return self.view(q)
            if q.get("id") and q["id"] != route["id"]:
                raise ValueError("Route changed; refresh the current route")
            last = self.polled.get(route["id"], 0)
            if time.monotonic() - last < 3 or key in self.inflight:
                return self.view(q)
            self.polled[route["id"]] = time.monotonic()
            self.inflight.add(key)
        try:
            response = self.core.services.fetch_json(n.API + "/results/" + n.job_id(route["job"]), ttl=2)
            if not isinstance(response, dict):
                raise ValueError("Invalid Spansh job response")
            if response.get("job") and str(response["job"]).lower() != route["job"].lower():
                raise ValueError("Spansh returned a different job")
            status = response.get("status")
            if status == "ok":
                route["waypoints"] = n.parse_result(response, route["request"])
                route["status"] = "ready"
                route["estimated_total_jumps"] = sum(r["estimated_jumps_from_previous"] for r in route["waypoints"])
                route["progress_index"] = 0 if str(self.context()["location"].get("system", "")).casefold() == route["request"]["from"].casefold() else -1
            elif status in ("queued", "running"):
                route["status"] = status
            else:
                route["status"] = "error"
                route["error"] = str(response.get("error") or "Unexpected Spansh job status: " + str(status))[:400]
            route.pop("last_poll_error", None)
        except Exception as ex:
            # Temporary network/provider errors remain retryable. Existing waypoints are preserved.
            route["last_poll_error"] = str(ex)[:400]
        finally:
            with self.lock:
                self.inflight.discard(key)
        with self.lock:
            if self.identity().get("key") == key and (self.account().get("route") or {}).get("id") == route.get("id"):
                self.replace_route(key, route)
                self.on_state()
        return self.view(q)

    def clear(self, q):
        with self.lock:
            key = self.identity().get("key")
            route = self.account().get("route") or {}
            if key in self.inflight:
                raise ValueError("Wait for the current request to finish before clearing")
            if not q.get("id") or q["id"] != route.get("id"):
                raise ValueError("Pass the current route id to clear it")
            self.replace_route(key, None)
            self.on_state()
        return self.view({})

    def export(self, q):
        with self.lock:
            route = copy.deepcopy(self.account().get("route") or {})
        if route.get("status") != "ready":
            raise ValueError("No completed route to export")
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(["System Name", "Distance To Arrival", "Distance Remaining", "Neutron Star", "Jumps"])
        for row in route["waypoints"]:
            name = row["system"]
            # Prevent formula execution when opened in a spreadsheet.
            if name.startswith(("=", "+", "-", "@")):
                name = "'" + name
            writer.writerow([name, row["distance_from_previous_ly"], row["distance_remaining_ly"],
                             "Yes" if row["neutron_star"] else "No", row["estimated_jumps_from_previous"]])
        return {"filename": "neutron-" + route["job"] + ".csv", "csv": out.getvalue(),
                "note": "Spansh-compatible waypoint CSV. Distance To Arrival is the historical Spansh column name for leg distance in Ly, not station arrival distance."}


def setup(core, module):
    obj = Neutron(core)
    core.http.route("/api/neutron/route", obj.view, tool="get_neutron_route", module=module.name,
        description="Current commander's saved Spansh route, next waypoint, ship preparation and Palin 5000 Ly evidence. No network. Waypoints can require several jumps; refuelling is not planned.",
        params={"limit": {"type": "integer", "default": 10, "description": "Next waypoints to return, 1-100"}})
    core.http.route("/api/neutron/plan", obj.plan, tool="plan_neutron_route", method="POST", module=module.name,
        description="Submit and save a Spansh neutron-highway route job. Source defaults to current ship location; range defaults to available full-fuel/full-cargo estimate, otherwise required. Uses normal UNBOOSTED range. Auto selects 6x only for a verified fitted Caspian special FSD, otherwise 4x. Poll with refresh_neutron_route. Does not plot in game.",
        params={"destination": {"type": "string", "required": True}, "source": {"type": "string"},
                "range_ly": {"type": "number", "description": "Verified normal unboosted jump range, 1-200 Ly. Never enter boosted range."},
                "efficiency": {"type": "number", "default": 60, "description": "Spansh route efficiency 1-100; higher favours a more direct path"},
                "supercharge": {"type": "string", "enum": ["auto", "4", "6"], "default": "auto"},
                "career_start": {"type": "string", "description": "Optional user-confirmed career starting system for Palin endpoint check; never assume Sol"}})
    core.http.route("/api/neutron/refresh", obj.refresh, tool="refresh_neutron_route", method="POST", module=module.name,
        description="Check the saved Spansh job once, at most every three seconds. Retains pending jobs for retry on network errors; stores completed waypoints. No blocking poll loop.",
        params={"id": {"type": "string", "description": "Optional expected current route ID"}})
    core.http.route("/api/neutron/clear", obj.clear, tool="clear_neutron_route", method="POST", module=module.name,
        description="Clear this commander's saved neutron plan. Does not cancel a Spansh job or change the in-game route.",
        params={"id": {"type": "string", "required": True}})
    core.http.route("/api/neutron/export", obj.export, tool="export_neutron_route", module=module.name,
        description="Export the completed neutron waypoint route as Spansh-compatible CSV text and a filename.")
