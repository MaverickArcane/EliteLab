"""history module: visited systems + route from every journal file.

State: ``history.version`` bumps whenever a jump happens, so the UI knows to
refetch. The data itself is served on demand (it can be thousands of rows).
"""
import json
import os
import time

NS = "history"


class History:
    def __init__(self, core):
        self.core = core
        self._cache = {}
        self.version = 0
        core.store.set(NS, "version", 0)
        core.bus.on("journal.FSDJump", self.bump)
        core.bus.on("journal.CarrierJump", self.bump)
        core.bus.on("journal.Location", self.bump)
        core.bus.on("journal.StartJump", self.bump)
        core.bus.on("journal.replay.done", self.bump)

    def bump(self, name, ev):
        if isinstance(ev, dict) and ev.get("_replay"):
            return
        self.version += 1
        self.core.store.set(NS, "version", self.version)

    def compute(self, days=30):
        from elitelab.core.watcher import journal_files
        cutoff = time.time() - days * 86400 if days else 0
        files = [f for f in journal_files() if os.path.getmtime(f) >= cutoff]
        key = (days, tuple((f, os.path.getmtime(f)) for f in files))
        if self._cache.get("key") == key:
            return self._cache["data"]
        systems, route, classes = {}, [], {}
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"StarPos"' not in line and '"StartJump"' not in line:
                            continue
                        try:
                            ev = json.loads(line)
                        except Exception:
                            continue
                        e = ev.get("event")
                        if e == "StartJump":
                            if ev.get("StarClass") and ev.get("StarSystem"):
                                classes[ev["StarSystem"]] = ev["StarClass"]
                            continue
                        if e not in ("FSDJump", "CarrierJump", "Location"):
                            continue
                        name, pos = ev.get("StarSystem"), ev.get("StarPos")
                        if not name or not pos:
                            continue
                        rec = systems.get(name)
                        if not rec:
                            rec = systems[name] = {"name": name, "pos": pos, "visits": 0, "first": ev.get("timestamp"),
                                                   "last": None, "star_class": None, "carrier": False}
                        rec["last"] = ev.get("timestamp")
                        if e != "Location":
                            rec["visits"] += 1
                        if e == "CarrierJump":
                            rec["carrier"] = True
                        if not route or route[-1]["name"] != name:
                            route.append({"name": name, "ts": ev.get("timestamp"), "event": e, "dist": round(ev.get("JumpDist", 0) or 0, 1)})
            except Exception:
                continue
        for name, rec in systems.items():
            if name in classes:
                rec["star_class"] = classes[name]
        data = {"days": days, "systems": list(systems.values()), "route": route,
                "total_ly": round(sum(r["dist"] for r in route), 1), "jumps": sum(1 for r in route if r["event"] == "FSDJump")}
        self._cache = {"key": key, "data": data}
        return data


def setup(core, module):
    h = History(core)

    def route(q):
        try:
            days = int(q.get("days", 30) or 0)
        except (TypeError, ValueError):
            days = 30
        return h.compute(max(0, days))

    core.http.route("/api/history", route, tool="get_travel_history", module=module.name,
                    description="Systems visited and the chronological route, with star class, visit counts, coordinates, total jumps and light-years.",
                    params={"days": {"type": "integer", "description": "Look back this many days; 0 = all time", "default": 30}})
