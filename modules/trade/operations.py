"""Owner-controlled trade stages and idempotent crew-reported deliveries."""
import copy
import secrets
from datetime import datetime, timezone
from modules.trade.profit import split_profit
from modules.trade.market import CLOCK_SKEW_SECONDS
from elitelab.core.hauling import build as build_workload
from modules.trade.audit import record

ACTIVE = {"loading", "transit", "unloading"}


def timestamp():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def operation_view(operation):
    if not operation:
        return None
    out = {k: copy.deepcopy(v) for k, v in operation.items() if k not in ("audit", "correction_requests", "audit_sequence")}
    out["history"] = copy.deepcopy(operation.get("audit", [])[-20:])
    out["history_count"] = operation.get("audit_sequence", 0)
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
                if plan.get("crew_enabled") and not plan.get("carrier_mean_price"):
                    raise ValueError("Refresh the carrier 100% price reference before starting. Crew prices must use in-game percentage settings.")
                if plan.get("crew_enabled") and plan.get("carrier_mean_source") in ("Ardent / EDDN", "Local market journal"):
                    try:
                        reference_time = datetime.fromisoformat(plan.get("carrier_mean_at", "").replace("Z", "+00:00"))
                        age = (datetime.now(timezone.utc) - reference_time).total_seconds()
                    except (ValueError, TypeError):
                        age = float("inf")
                    if not -CLOCK_SKEW_SECONDS <= age <= 86400:
                        raise ValueError("The carrier 100% price reference is stale. Refresh carrier pricing before starting.")
                qty = plan.get("planned_quantity") or (self.desk.calculate() or {}).get("remaining")
                if not qty or qty < 1 or qty > plan["target"]:
                    raise ValueError("Set a positive operation size and a valid carrier target first.")
                if op:
                    data["previous_operation"] = {"operation": copy.deepcopy(op), "plan": copy.deepcopy(plan), "workload": copy.deepcopy(data.get("workload"))}
                plan["planned_quantity"] = qty
                # Save the selected mode when loading starts. Fixed shares keep
                # their quotas; live mode refreshes estimates from crew reports.
                if not data.get("workload") or op or data["workload"]["quantity"] != qty:
                    data["workload"] = build_workload(plan, None, self.core.store.get("party", "members", []), data.get("workload") or {})
                if plan.get("crew_enabled"):
                    plan["crew_split"] = split_profit(plan["source_price"],
                        plan["destination_price"] - (plan["bonus_per_ton"] if plan.get("price_includes_bonus") else 0),
                        qty, plan["crew_load_percent"], plan["crew_unload_percent"], plan.get("carrier_mean_price"))
                op = {"id": secrets.token_hex(16), "stage": "loading", "paused": False,
                      "quantity": qty, "baseline_stock": plan["target"] - qty, "notes": "",
                      "reports": {}, "started_at": timestamp(), "updated_at": timestamp()}
                op["phase_started_at"] = {"loading": op["started_at"]}
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
                    if after == "complete":
                        op["ended_at"] = timestamp()
                    if after == "unloading":
                        op.setdefault("phase_started_at", {})["unloading"] = timestamp()
                        plan["mode"], plan["target"] = "unload", op["baseline_stock"]
                        if plan.get("crew_enabled"):
                            plan["carrier_price"] = plan["crew_split"]["carrier_sell_price"]
                        else:
                            plan["carrier_price_known"] = False
                elif action in ("pause", "resume"):
                    op["paused"] = action == "pause"
                elif action == "cancel":
                    op["stage"], op["paused"] = "cancelled", False
                    op["ended_at"] = timestamp()
                elif action == "notes":
                    notes = q.get("notes", "")
                    if not isinstance(notes, str) or len(notes) > 500:
                        raise ValueError("Crew instructions must be text up to 500 characters.")
                    op["notes"] = notes.strip()
                else:
                    raise ValueError("Unknown operation action.")
                op["updated_at"] = timestamp()
            record(op, "stage", action=action, stage=op["stage"], paused=op["paused"])
            self.desk.commit(data)
            return self.core.store.get("trade")

    def correct(self, q):
        if self.core.store.get("party", "mode") == "member":
            raise ValueError("Only the carrier owner can correct credited deliveries.")
        phase, mid, reason, request = q.get("phase"), q.get("member"), q.get("reason"), q.get("request_id")
        if phase not in ("loading", "unloading") or not isinstance(mid, str):
            raise ValueError("Choose a commander and loading or unloading.")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
            raise ValueError("Explain the correction in 1 to 300 characters.")
        if not isinstance(request, str) or not 16 <= len(request) <= 80:
            raise ValueError("A unique correction request ID is required.")
        if any(type(q.get(k)) is not int or q[k] < 0 for k in ("tonnes", "expected", "expected_reported")):
            raise ValueError("Delivery totals must be non-negative whole tonnes.")
        command = {k: q[k] for k in ("member", "phase", "tonnes", "expected", "expected_reported", "reason")}
        with self.desk.lock:
            current = self.desk.data.get("operation")
            if not current or current["id"] != q.get("id"):
                raise ValueError("The job changed. Refresh before correcting a delivery.")
            receipt = current.get("correction_requests", {}).get(request)
            if receipt:
                if receipt != command:
                    raise ValueError("This correction request was already used for another change.")
                return operation_view(current)
            if phase == "unloading" and current["stage"] not in ("unloading", "complete") and not (
                    current["stage"] == "cancelled" and self.desk.data["plan"]["mode"] == "unload"):
                raise ValueError("Unloading has not opened for this job.")
            if q["tonnes"] > current["quantity"]:
                raise ValueError("A commander's credited total cannot exceed the job size.")
            roster = {m["id"]: m for m in self.core.store.get("party", "members", [])}
            roster.update({r["id"]: {"cmdr": r["cmdr"], "leader": r["owner"]}
                           for r in (self.desk.data.get("workload") or {}).get("members", []) if r["id"] not in roster})
            if mid not in current["reports"] and mid not in roster:
                raise ValueError("Choose a commander from this job.")
            if mid not in current["reports"] and len(current["reports"]) >= 128:
                raise ValueError("This job's commander history is full.")
            previous = current["reports"].get(mid, {})
            credited, raw = previous.get(phase, 0), previous.get("reported", previous).get(phase, 0)
            accepted_raw = raw
            incoming = roster.get(mid, {}).get("work") or {}
            if incoming.get("operation_id") == current["id"]:
                raw = max(raw, incoming.get(phase) or 0)
            if (credited, raw) != (q["expected"], q["expected_reported"]):
                raise ValueError("A newer delivery or correction arrived. Refresh totals before saving.")
            if len(current.get("correction_requests", {})) >= 1000:
                raise ValueError("This job's correction history is full.")
            data = copy.deepcopy(self.desk.data)
            op = data["operation"]
            row = {**previous, "cmdr": previous.get("cmdr") or roster.get(mid, {}).get("cmdr") or "Unknown commander",
                   "owner": previous.get("owner", roster.get(mid, {}).get("leader", False)),
                   "reported": {k: previous.get("reported", previous).get(k, 0) for k in ("loading", "unloading")},
                   "adjustments": dict(previous.get("adjustments", {})), "updated_at": timestamp()}
            row[phase] = q["tonnes"]
            row["reported"][phase] = raw
            row["adjustments"][phase] = q["tonnes"] - raw
            row["correction_at"] = {**previous.get("correction_at", {}), phase:timestamp()}
            op["reports"][mid] = row
            op.setdefault("correction_requests", {})[request] = command
            record(op, "correction", member_id=mid, cmdr=row["cmdr"], phase=phase,
                   before=credited, after=q["tonnes"], reported_before=accepted_raw, reported_after=raw,
                   adjustment=row["adjustments"][phase], reason=reason.strip())
            self.desk.commit(data)
            return operation_view(op)

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
            accepted = {k: previous.get("reported", previous).get(k, 0) for k in ("loading", "unloading")}
            adjustments = previous.get("adjustments", {})
            for phase in accepted:
                if phase == "unloading" and current["stage"] not in ("unloading", "complete"):
                    continue
                value = work.get(phase, 0)
                if type(value) is int and accepted[phase] <= value <= 1000000000 and 0 <= value + adjustments.get(phase, 0) <= current["quantity"]:
                    accepted[phase] = value
            if all(accepted[k] == previous.get("reported", previous).get(k, 0) for k in accepted):
                return
            data = copy.deepcopy(self.desk.data)
            credited = {k: accepted[k] + adjustments.get(k, 0) for k in accepted}
            data["operation"]["reports"][mid] = {**previous, **credited, "reported": accepted,
                "cmdr": report.get("cmdr") or previous.get("cmdr") or "Unknown commander",
                "owner": mid == self.core.store.get("party", "local_id"), "updated_at": timestamp()}
            evidence_by_phase = dict(previous.get("delivery_evidence", {}))
            for phase in accepted:
                before = previous.get("reported", previous).get(phase, 0)
                if accepted[phase] != before:
                    evidence = work.get("last_entry") or {}
                    phase_evidence = work.get("delivery_evidence", {}).get(phase) or (evidence if evidence.get("phase") == phase else None)
                    if phase_evidence:
                        evidence_by_phase[phase] = {k:phase_evidence.get(k) for k in ("kind", "at", "tonnes")}
                    record(data["operation"], "delivery", member_id=mid,
                           cmdr=data["operation"]["reports"][mid]["cmdr"], phase=phase,
                           before=previous.get(phase, 0), after=credited[phase],
                           reported_before=before, reported_after=accepted[phase], adjustment=adjustments.get(phase, 0),
                           last_entry=copy.deepcopy(evidence) if evidence.get("phase") == phase else None)
            data["operation"]["reports"][mid]["delivery_evidence"] = evidence_by_phase
            self.desk.commit(data)
