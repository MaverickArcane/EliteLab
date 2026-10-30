"""Owner-only workload preview and persistence routes."""
import copy
from elitelab.core.hauling import build, view
from modules.trade.audit import record


class Workloads:
    def __init__(self, core, desk):
        self.core, self.desk = core, desk
        core.bus.on("party.roster", self.include_newcomers)

    def include_newcomers(self, name, members):
        """Include new eligible crew once; heartbeats and reconnects keep quotas."""
        if self.core.store.get("party", "mode") != "leader":
            return
        with self.desk.lock:
            data = self.desk.data
            op, saved = data.get("operation"), data.get("workload")
            if op and op["stage"] in ("loading", "transit", "unloading") and saved and saved["mode"] == "live":
                # Save material cargo/roster changes, never heartbeat timestamps.
                # Absent crew retain observed cargo but release unpicked work.
                try:
                    updated = build(data["plan"],op,members,saved,saved)
                    if updated != saved:
                        candidate = copy.deepcopy(data)
                        candidate["workload"] = updated
                        self.desk.commit(candidate)
                except (ValueError, OSError) as error:
                    self.core.store.set("trade","workload_join_error","Could not save live cargo allocation: "+str(error))
                    return
                self.core.store.set("trade","workload_join_error",None)
                return
            if not op or op["stage"] not in ("loading", "transit", "unloading") or not saved or saved["mode"] != "equal":
                self.core.store.set("trade", "workload_join_error", None)
                return
            assigned = {r["id"] for r in saved["members"]}
            newcomers = [m for m in members if m["id"] not in assigned and not m.get("stale")
                         and m.get("activity") != "away" and (saved["owner_hauls"] or not m.get("leader"))]
            if not newcomers:
                self.core.store.set("trade", "workload_join_error", None)
                return
            try:
                included = assigned | {m["id"] for m in newcomers}
                updated = build(data["plan"], op, [m for m in members if m["id"] in included], saved, saved, joining=True)
                candidate = copy.deepcopy(data)
                candidate["workload"] = updated
                for member in newcomers:
                    record(candidate["operation"], "workload", action="join", member_id=member["id"],
                           cmdr=member.get("cmdr"), mode="equal", owner_hauls=saved["owner_hauls"])
                self.desk.commit(candidate)
            except (ValueError, OSError) as error:
                # Keep the saved split on failure; the next report retries.
                self.core.store.set("trade", "workload_join_error", "Could not include new crew automatically: " + str(error))
                return
            self.core.store.set("trade", "workload_join_error", None)

    def configure(self, q):
        if self.core.store.get("party", "mode") == "member":
            raise ValueError("Only the carrier owner can change the workload split.")
        action = q.get("action", "preview")
        if action not in ("preview", "apply"):
            raise ValueError("Choose preview or apply.")
        with self.desk.lock:
            data = self.desk.data
            op, plan = data.get("operation"), data.get("plan")
            if op and op["stage"] in ("complete", "cancelled"):
                raise ValueError("Prepare a new job before splitting its workload.")
            members = self.core.store.get("party", "members", [])
            saved = build(plan, op, members, q, data.get("workload"), (self.desk.calculate() or {}).get("remaining"))
            if action == "apply":
                if q.get("basis") != saved["basis"]:
                    raise ValueError("The job or crew changed. Preview the current split before applying it.")
                candidate = copy.deepcopy(data)
                candidate["workload"] = saved
                if candidate.get("operation"):
                    record(candidate["operation"], "workload", mode=saved["mode"], owner_hauls=saved["owner_hauls"])
                self.desk.commit(candidate)
            return view(saved, op, members, plan)
