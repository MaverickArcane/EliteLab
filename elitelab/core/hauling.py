"""Saved commander quotas. Equal means equal tonnes, independent of ship size."""
import hashlib
import json
from math import ceil
from elitelab.core.gamedata import norm


def matching_cargo(member, commodity):
    count = member.get("cargo_count")
    if type(count) is not int or count < 0:
        return 0
    return min(count, sum(i.get("count") or 0 for i in member.get("cargo", [])
                          if norm(i.get("key") or "") == norm(commodity)))


def divide(total, weights, minimums=None):
    """Conserve whole tonnes; use stable identity to break remainder ties."""
    if minimums:
        if sum(minimums.values()) > total:
            raise ValueError("Cargo already in flight exceeds the remaining job. Check deliveries before rebalancing.")
        fixed, pending = {}, dict(weights)
        while pending:
            left = total - sum(fixed.values())
            if not sum(pending.values()):
                if left:
                    raise ValueError("Choose at least one commander to haul.")
                return {**fixed, **dict.fromkeys(pending, 0)}
            portions = divide(left, pending)
            constrained = [mid for mid in pending if portions[mid] < minimums.get(mid, 0)]
            if not constrained:
                return {**fixed, **portions}
            for mid in constrained:
                fixed[mid] = minimums[mid]
                del pending[mid]
        return fixed
    denominator = sum(weights.values())
    if denominator <= 0:
        raise ValueError("Choose at least one commander to haul.")
    result = {mid: total * weight // denominator for mid, weight in weights.items()}
    ranked = sorted(weights, key=lambda mid: (-(total * weights[mid] % denominator), mid))
    for mid in ranked[:total - sum(result.values())]:
        result[mid] += 1
    return result


def build(plan, operation, members, settings, previous=None, fallback_quantity=None, *, joining=False):
    if not plan:
        raise ValueError("Choose a route before splitting the workload.")
    total = (operation or {}).get("quantity") or plan.get("planned_quantity") or fallback_quantity
    if type(total) is not int or not 0 < total <= 1000000:
        raise ValueError("Set a positive operation size before splitting the workload.")
    mode, owner_hauls = settings.get("mode", "equal"), settings.get("owner_hauls", True)
    if mode not in ("equal", "custom") or type(owner_hauls) is not bool:
        raise ValueError("Choose equal tonnes or custom shares, and whether the owner hauls.")
    shares = settings.get("shares", {})
    if not isinstance(shares, dict) or len(shares) > 128 or any(type(v) is not int or not 0 <= v <= 10000 for v in shares.values()):
        raise ValueError("Custom share weights must be whole numbers from 0 to 10000.")
    roster = {m["id"]: m for m in members}
    # Keep earned deliveries and named offline assignees when redistributing.
    known = {r["id"]: {**r, "leader": r["owner"], "stale": True} for r in (previous or {}).get("members", [])}
    known.update(roster)
    reports = (operation or {}).get("reports", {})
    for mid, r in reports.items():
        known.setdefault(mid, {"id": mid, "cmdr": r.get("cmdr"), "leader": r.get("owner", False), "stale": True})
    if any(mid not in known for mid in shares):
        raise ValueError("The crew changed. Refresh the split before applying it.")
    weights = {}
    for mid, m in known.items():
        eligible = (owner_hauls or not m.get("leader")) and not m.get("stale") and m.get("activity") != "away"
        weights[mid] = (shares.get(mid, 0) if mode == "custom" else 1) if eligible else 0
    targets = {}
    old_targets = {r["id"]: r for r in (previous or {}).get("members", [])}
    cargo = {mid: matching_cargo(m, plan["commodity"]) for mid, m in known.items()}
    for phase in ("loading", "unloading"):
        delivered = {mid: reports.get(mid, {}).get(phase, 0) for mid in known}
        remaining = total - sum(delivered.values())
        if remaining < 0:
            raise ValueError("Reported deliveries exceed the job size. Resolve that before rebalancing.")
        if joining and phase == "loading" and (operation or {}).get("stage") != "loading":
            # A late arrival after departure only joins the unloading work.
            targets[phase] = {mid: old_targets.get(mid, {}).get(phase + "_target", 0) for mid in known}
            continue
        # Changing future participation must not strand an assigned load already
        # aboard. Keep weighted shares where possible, with those loads as floors.
        committed = {mid: min(cargo[mid], max(0, old_targets.get(mid, {}).get(phase + "_target", 0) - delivered[mid]))
                     if (operation or {}).get("stage") == phase else 0 for mid in known}
        if joining:
            for mid, m in known.items():
                if m.get("stale") or m.get("activity") == "away":
                    # Joining is not permission to release absent crew's quotas.
                    committed[mid] = max(0, old_targets.get(mid, {}).get(phase + "_target", 0) - delivered[mid])
        portions = divide(remaining, weights, committed)
        targets[phase] = {mid: delivered[mid] + portions[mid] for mid in known}
    if joining:
        for mid, m in known.items():
            if mid in old_targets and (m.get("stale") or m.get("activity") == "away"):
                # Preserve participation too, so returning crew can pick up
                # their reserved remainder without a manual rebalance.
                weights[mid] = old_targets[mid]["weight"]
    rows = [{"id": mid, "cmdr": m.get("cmdr") or "Unknown commander", "owner": bool(m.get("leader")),
             "capacity": m.get("capacity"), "weight": weights[mid],
             "loading_target": targets["loading"][mid], "unloading_target": targets["unloading"][mid]}
            for mid, m in known.items()]
    basis = {"plan": plan, "operation_id": (operation or {}).get("id"), "stage": (operation or {}).get("stage"),
             "reports": reports, "rows": rows, "cargo": cargo, "mode": mode, "owner_hauls": owner_hauls}
    token = hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()
    return {"mode": mode, "owner_hauls": owner_hauls, "shares": shares, "quantity": total, "members": rows, "basis": token}


def view(saved, operation, members, plan):
    if not saved:
        return None
    live = {m["id"]: m for m in members}
    reports = (operation or {}).get("reports", {})
    rows = []
    for assignment in saved["members"]:
        mid = assignment["id"]
        member = live.get(mid)
        capacity = member.get("capacity") if member else assignment.get("capacity")
        cargo = member.get("cargo_count") if member else None
        matching = sum(i.get("count") or 0 for i in (member or {}).get("cargo", []) if norm(i.get("key") or "") == norm(plan["commodity"]))
        usable = max(0, capacity - max(0, cargo - matching)) if type(capacity) is int and type(cargo) is int else capacity
        if not isinstance(usable, int) or usable <= 0:
            usable = None
        row = {**assignment, "capacity": capacity, "usable": usable,
               "connected": bool(member) and not member.get("stale", False), "cargo_count": cargo}
        for phase in ("loading", "unloading"):
            delivered = reports.get(mid, {}).get(phase, 0)
            remaining = max(0, assignment[phase + "_target"] - delivered)
            row[phase + "_done"], row[phase + "_remaining"] = delivered, remaining
            row[phase + "_runs"] = ceil(assignment[phase + "_target"] / usable) if usable else None
            row[phase + "_runs_left"] = ceil(remaining / usable) if usable else (0 if not remaining else None)
            row[phase + "_full_loads"] = remaining // usable if usable else None
            row[phase + "_partial_load"] = remaining % usable if usable else None
        rows.append(row)
    totals = {}
    for phase in ("loading", "unloading"):
        remaining = max(0, saved["quantity"] - sum(r.get(phase, 0) for r in reports.values()))
        own_remaining = min(remaining, sum(r[phase + "_remaining"] for r in rows if r["owner"]))
        totals[phase] = {"remaining": remaining, "owner_remaining": own_remaining,
                         "order_remaining": max(0, remaining - own_remaining),
                         "owner_target": sum(r[phase + "_target"] for r in rows if r["owner"])}
    split = plan.get("crew_split") if plan.get("crew_enabled") else None
    buy_price = split["carrier_buy_price"] if split else plan.get("carrier_price") if plan.get("carrier_price_known") and plan.get("mode") == "load" else None
    sell_price = split["carrier_sell_price"] if split else plan.get("carrier_price") if plan.get("carrier_price_known") and plan.get("mode") == "unload" else None
    economics = None
    if split:
        loading_pay = (saved["quantity"] - totals["loading"]["owner_target"]) * split["loading_per_ton"]
        unloading_pay = (saved["quantity"] - totals["unloading"]["owner_target"]) * split["unloading_per_ton"]
        gross = saved["quantity"] * (split["loading_per_ton"] + split["unloading_per_ton"] + split["owner_per_ton"])
        economics = {"gross_profit": gross, "loading_profit": loading_pay, "unloading_profit": unloading_pay,
                     "crew_profit": loading_pay + unloading_pay, "owner_profit": gross - loading_pay - unloading_pay}
    return {**saved, "members": rows, "loading": totals["loading"], "unloading": totals["unloading"],
            "buy_price": buy_price, "sell_price": sell_price,
            "buy_percent":split.get("carrier_buy_percent") if split else None,
            "sell_percent":split.get("carrier_sell_percent") if split else None,
            "prices_valid":split.get("carrier_prices_valid",False) if split else True,
            "buy_budget": totals["loading"]["order_remaining"] * buy_price if buy_price is not None else None,
            "economics": economics}
