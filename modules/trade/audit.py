"""Bounded operation history and explicitly allowlisted diagnostic exports."""
import copy
import hashlib
from datetime import datetime, timezone

MAX_HISTORY = 2000


def record(operation, kind, **values):
    at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sequence = operation.get("audit_sequence", 0) + 1
    operation["audit_sequence"] = sequence
    history = operation.setdefault("audit", [])
    history.append({"sequence": sequence, "at": at, "kind": kind, **values})
    operation["audit"] = history[-MAX_HISTORY:]
    operation["updated_at"] = at


class Diagnostics:
    def __init__(self, core, desk):
        self.core, self.desk = core, desk

    def export(self, q):
        # Never export the full store, config, journal, or transport credentials.
        with self.desk.lock:
            data = copy.deepcopy(self.desk.data)
            party = self.core.store.get("party")
        member = party.get("mode") == "member"
        if member:
            job = party
            scope = "latest shared entries"
        else:
            job = data if data.get("operation") else data.get("previous_operation") or data
            scope = "retained owner history"
        op, plan, workload = job.get("operation") or {}, job.get("plan") or {}, job.get("workload") or {}
        reports = op.get("reports", {})
        history = op.get("history", []) if member else op.get("audit", [])
        members = party.get("members", [])
        identities = list(dict.fromkeys([party.get("local_id"), *reports,
            *(m["id"] for m in members), *(r["id"] for r in workload.get("members", [])),
            *(e.get("member_id") for e in history)]))
        # Stable within a job across different clients' exports, without exposing
        # the persistent commander identity or tying separate jobs together.
        aliases = {mid: "commander_" + hashlib.sha256((op.get("id", "") + ":" + mid).encode()).hexdigest()[:12]
                   for mid in identities if mid}
        alias = lambda mid: aliases.get(mid)
        phases = ("loading", "unloading")
        totals = {phase: sum(r.get(phase, 0) for r in reports.values()) for phase in phases}
        local_work = party.get("work") or {}
        local_report = reports.get(party.get("local_id"), {})
        local_matches = bool(op) and local_work.get("operation_id") == op.get("id")
        pending = {phase: max(0, local_work.get(phase, 0) - local_report.get("reported", local_report).get(phase, 0))
                   for phase in phases} if local_matches else None
        checks = []
        for phase in phases:
            if totals[phase] > op.get("quantity", 0):
                checks.append(f"{phase} reports exceed the job target by {totals[phase]-op.get('quantity',0)} t")
            if pending and pending[phase]:
                checks.append(f"{pending[phase]} t {phase} awaits acknowledgement")
        if party.get("stale"):
            checks.append("Leader connection is stale")
        if op and not plan.get("carrier_market_id"):
            checks.append("Loading market ID is unknown; automatic matching is unavailable")
        if op and not plan.get("destination_market_id"):
            checks.append("Unloading market ID is unknown; automatic matching is unavailable")
        safe_history = []
        for event in history:
            safe = {k: copy.deepcopy(event[k]) for k in ("sequence", "at", "kind", "action", "stage", "paused", "phase",
                    "before", "after", "reported_before", "reported_after", "adjustment", "mode", "owner_hauls") if k in event}
            if event.get("member_id"):
                safe["member"] = alias(event["member_id"])
            if event.get("reason"):
                safe["reason_provided"] = True
            evidence = event.get("last_entry") or {}
            safe["last_entry"] = {k: evidence[k] for k in ("kind", "phase", "tonnes", "at") if k in evidence}
            safe_history.append(safe)
        from elitelab import __version__
        return {"format": "elitelab-hauling-diagnostics-v1", "app_version": __version__,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "redactions": ["commander names and identities", "connection credentials and addresses",
                           "free-text notes and correction reasons", "unrelated journals, credits and filesystem paths"],
            "client": {"mode": party.get("mode"), "stale": bool(party.get("stale")), "member": alias(party.get("local_id")),
                       "pending": pending, "local_totals": {phase: local_work.get(phase, 0) for phase in phases} if local_matches else {},
                       "saved_work": {"operation_id":local_work.get("operation_id"),
                                      "reported":{phase:local_work.get(phase,0) for phase in phases}} if local_work else None},
            "operation": {k: op[k] for k in ("id", "stage", "paused", "quantity", "baseline_stock", "started_at", "updated_at") if k in op},
            "route": {k: plan[k] for k in ("commodity", "source", "destination", "source_market_id", "destination_market_id",
                        "carrier_market_id", "source_price", "destination_price", "carrier_price", "carrier_mean_price", "crew_enabled") if k in plan},
            "carrier_prices": {k:plan["crew_split"][k] for k in ("carrier_buy_price", "carrier_sell_price",
                "carrier_buy_percent", "carrier_sell_percent", "carrier_prices_valid") if k in plan.get("crew_split",{})},
            "totals": totals, "checks": checks,
            "reports": [{"member": alias(mid), "owner": bool(r.get("owner")),
                         "credited": {phase: r.get(phase, 0) for phase in phases},
                         "reported": {phase: r.get("reported", r).get(phase, 0) for phase in phases},
                         "adjustments": {phase: r.get("adjustments", {}).get(phase, 0) for phase in phases}}
                        for mid, r in reports.items()],
            "assignments": [{"member": alias(r["id"]), **{k: r[k] for k in ("owner", "weight", "loading_target", "unloading_target") if k in r}}
                            for r in workload.get("members", [])],
            "crew": [{"member": alias(m["id"]), **{k: m[k] for k in ("leader", "stale", "activity", "capacity", "cargo_count") if k in m},
                      "latest_totals": {phase:(m.get("work") or {}).get(phase,0) for phase in phases}
                          if (m.get("work") or {}).get("operation_id")==op.get("id") else {}}
                     for m in members],
            "history_scope": scope, "history_count": op.get("audit_sequence", op.get("history_count", 0)),
            "history_retained": len(safe_history), "history": safe_history}
