"""Owner-controlled trade stages and idempotent crew-reported deliveries."""
import copy
import secrets
from datetime import datetime, timezone
from modules.trade.profit import split_profit
from elitelab.core.hauling import build as build_workload

ACTIVE = {"loading", "transit", "unloading"}


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def operation_view(operation):
    if not operation:
        return None
    out = copy.deepcopy(operation)
    reports = out.get("reports", {})
    out["loaded"] = sum(r.get("loading", 0) for r in reports.values())
    out["unloaded"] = sum(r.get("unloading", 0) for r in reports.values())
    out["remaining_load"] = max(0, out["quantity"] - out["loaded"])
    out["remaining_unload"] = max(0, out["quantity"] - out["unloaded"])
    return out


class Operations:
    def __init__(self, core, desk):
        self.core, self.desk = core, desk
        core.bus.on("party.work", self.report)

    def control(self, q):
        if self.core.store.get("party", "mode") == "member":
            raise ValueError("Only the carrier owner controls the shared trade.")
        action = q.get("action")
        with self.desk.lock:
            data = copy.deepcopy(self.desk.data)
            op, plan = data.get("operation"), data.get("plan")
            if action == "start":
                if op and op["stage"] in ACTIVE:
                    raise ValueError("Finish or cancel the current trade first.")
                if not plan or plan["mode"] != "load" or not plan.get("source") or not plan.get("destination"):
                    raise ValueError("Choose a complete buy/sell route and loading plan first.")
                qty = plan.get("planned_quantity") or (self.desk.calculate() or {}).get("remaining")
                if not qty or qty < 1 or qty > plan["target"]:
                    raise ValueError("Set a positive operation size and a valid carrier target first.")
                plan["planned_quantity"] = qty
                # Freeze per-commander tonnes when loading starts. Ship changes
                # and disconnects change estimates, never these commitments.
                if not data.get("workload") or op or data["workload"]["quantity"] != qty:
                    data["workload"] = build_workload(plan, None, self.core.store.get("party", "members", []), data.get("workload") or {})
                if plan.get("crew_enabled"):
                    plan["crew_split"] = split_profit(plan["source_price"],
                        plan["destination_price"] - (plan["bonus_per_ton"] if plan.get("price_includes_bonus") else 0),
                        qty, plan["crew_load_percent"], plan["crew_unload_percent"])
                op = {"id": secrets.token_hex(16), "stage": "loading", "paused": False,
                      "quantity": qty, "baseline_stock": plan["target"] - qty, "notes": "",
                      "reports": {}, "started_at": timestamp(), "updated_at": timestamp()}
                data["operation"] = op
            else:
                if not op or q.get("id") != op["id"]:
                    raise ValueError("The operation changed. Refresh before applying this action.")
                if op["stage"] not in ACTIVE:
                    raise ValueError("This operation has ended.")
                transitions = {"depart": ("loading", "transit"), "unload": ("transit", "unloading"), "complete": ("unloading", "complete")}
                if action in transitions:
                    before, after = transitions[action]
                    if op["stage"] != before or op["paused"]:
                        raise ValueError("Resume the operation and follow its stages in order.")
                    op["stage"] = after
                    if after == "unloading":
                        plan["mode"], plan["target"] = "unload", op["baseline_stock"]
                        if plan.get("crew_enabled"):
                            plan["carrier_price"] = plan["crew_split"]["carrier_sell_price"]
                        else:
                            plan["carrier_price_known"] = False
                elif action in ("pause", "resume"):
                    op["paused"] = action == "pause"
                elif action == "cancel":
                    op["stage"], op["paused"] = "cancelled", False
                elif action == "notes":
                    notes = q.get("notes", "")
                    if not isinstance(notes, str) or len(notes) > 500:
                        raise ValueError("Crew instructions must be text up to 500 characters.")
                    op["notes"] = notes.strip()
                else:
                    raise ValueError("Unknown operation action.")
                op["updated_at"] = timestamp()
            self.desk.commit(data)
            return self.core.store.get("trade")

    def report(self, name, payload):
        mid, report = payload["id"], payload["report"]
        work = report.get("work") or {}
        with self.desk.lock:
            current = self.desk.data.get("operation")
            if not current or current["id"] != work.get("operation_id") or current["stage"] == "cancelled":
                return
            previous = current["reports"].get(mid, {})
            if mid not in current["reports"] and len(current["reports"]) >= 128:
                return
            # Cumulative counts: repeated heartbeats/reconnects never double count.
            # Late loading reports remain valid after departure; future unloading does not.
            accepted = {k: previous.get(k, 0) for k in ("loading", "unloading")}
            for phase in accepted:
                if phase == "unloading" and current["stage"] not in ("unloading", "complete"):
                    continue
                value = work.get(phase, 0)
                if type(value) is int and accepted[phase] <= value <= current["quantity"]:
                    accepted[phase] = value
            if all(accepted[k] == previous.get(k, 0) for k in accepted):
                return
            data = copy.deepcopy(self.desk.data)
            data["operation"]["reports"][mid] = {**accepted, "cmdr": report.get("cmdr") or "Unknown commander",
                "owner": mid == self.core.store.get("party", "local_id"), "updated_at": timestamp()}
            self.desk.commit(data)
