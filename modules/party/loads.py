"""Advisory crew sizing; never changes a plan, reserves cargo or records delivery."""
from elitelab.core.gamedata import norm


def recommend(plan, operation, members, fallback_quantity=None, workload=None):
    if not plan:
        return None
    phase = (operation or {}).get("stage", "ready")
    remaining = ((operation or {}).get("remaining_unload" if phase == "unloading" else "remaining_load")
                 if operation else plan.get("planned_quantity") or fallback_quantity)
    if type(remaining) is not int or remaining < 0:
        return None
    rows, excluded = [], []
    assignments = {r["id"]: r for r in (workload or {}).get("members", [])}
    leg = "unloading" if phase in ("transit", "unloading", "complete") else "loading"
    for member in members:
        t = member.get("telemetry") or {}
        capacity, cargo = member.get("capacity"), member.get("cargo_count")
        reason = ("connection stale" if member.get("stale") else "away" if member.get("activity") == "away"
                  else "game closed" if t.get("game_running") is False
                  else "not in main ship" if t.get("vehicle") not in (None, "ship")
                  else "cargo space unknown" if type(capacity) is not int or capacity <= 0 or type(cargo) is not int or cargo < 0 or cargo > capacity
                  else None)
        if reason:
            excluded.append({"id": member["id"], "cmdr": member.get("cmdr"), "reason": reason})
            continue
        aboard = min(cargo, sum(i.get("count") or 0 for i in member.get("cargo", []) if norm(i.get("key") or "") == norm(plan["commodity"])))
        usable = capacity - (cargo - aboard)
        rows.append({"id": member["id"], "cmdr": member.get("cmdr"), "leader": member.get("leader", False),
                     "capacity": capacity, "round_capacity": usable, "aboard": aboard, "free": capacity - cargo, "next_buy": 0})
    round_capacity = sum(r["round_capacity"] for r in rows)
    aboard = sum(r["aboard"] for r in rows)
    free = sum(r["free"] for r in rows)
    to_buy = max(0, remaining - aboard)
    enabled = phase in ("ready", "loading", "unloading") and not (operation or {}).get("paused")
    next_buy = min(free, to_buy) if enabled else 0
    if workload:
        # Each ship's pickup is capped by its saved quota and onboard cargo.
        # Global bounds still protect the final partial round after overshoots.
        for row in rows:
            assigned = assignments.get(row["id"], {})
            row["remaining"] = assigned.get(leg + "_remaining", 0)
            row["free"] = min(row["free"], max(0, row["remaining"] - row["aboard"]))
        free = sum(r["free"] for r in rows)
        next_buy = min(free, to_buy) if enabled else 0
    # Largest remainders divide the last partial round proportionally to each
    # ship's free hold, in whole tonnes, with stable identity tie-breaking.
    if free:
        for row in rows:
            row["next_buy"] = next_buy * row["free"] // free
        spare = next_buy - sum(r["next_buy"] for r in rows)
        ranked = sorted(rows, key=lambda r: (-(next_buy * r["free"] % free), r["id"]))
        for row in ranked[:spare]:
            row["next_buy"] += 1
    full_rounds, tail = divmod(remaining, round_capacity) if round_capacity else (0, remaining)
    return {"phase": phase, "enabled": enabled, "remaining": remaining, "aboard": aboard,
            "to_buy": to_buy, "next_buy": next_buy, "round_capacity": round_capacity,
            "full_rounds": full_rounds, "tail": tail,
            "suggested_quantity": full_rounds * round_capacity if full_rounds else remaining,
            "members": rows, "excluded": excluded}
