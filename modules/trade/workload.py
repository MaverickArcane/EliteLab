"""Owner-only workload preview and persistence routes."""
import copy
from elitelab.core.hauling import build, view


class Workloads:
    def __init__(self, core, desk):
        self.core, self.desk = core, desk

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
            saved = build(plan, op, members, q, data.get("workload"))
            if action == "apply":
                if q.get("basis") != saved["basis"]:
                    raise ValueError("The job or crew changed. Preview the current split before applying it.")
                candidate = copy.deepcopy(data)
                candidate["workload"] = saved
                self.desk.commit(candidate)
            return view(saved, op, members, plan)
