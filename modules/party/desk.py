"""Read-only hauling views. All clients use the same quantities and price rules.

Ship cargo, accepted deliveries and pending local reports are separate evidence.
Pickup suggestions are advisory, never reservations or confirmed inventory.
"""
from elitelab.core.gamedata import norm


def stop(value, market_id=None):
    station, sep, system = (value or "").rpartition(" / ")
    return {"station": station if sep else value or "Unknown stop",
            "system": system if sep else None, "market_id": market_id or None}


def rates(plan):
    split = plan.get("crew_split") if plan.get("crew_enabled") else None
    if split:
        return {"loading": split["loading_per_ton"], "unloading": split["unloading_per_ton"]}
    # A manually entered carrier price only describes the selected leg.
    result = {"loading": None, "unloading": None}
    if plan.get("carrier_price_known"):
        if plan.get("mode") == "load" and plan.get("price_basis", "known") != "unknown acquisition":
            result["loading"] = plan["carrier_price"] - plan["source_price"]
        if plan.get("mode") == "unload" and plan.get("price_basis", "known") != "unknown resale":
            result["unloading"] = plan["destination_price"] - (plan.get("bonus_per_ton", 0) if plan.get("price_includes_bonus") else 0) - plan["carrier_price"]
    return result


def earnings(report, prices):
    if any(report.get(phase, 0) and prices[phase] is None for phase in prices):
        return None
    return sum(report.get(phase, 0) * (price or 0) for phase, price in prices.items())


def project(shared, local_id, local, work=None, stale=False):
    """Project a coherent job snapshot into a personal task and durable roster."""
    plan, op = shared.get("plan"), shared.get("operation")
    if not plan:
        return None
    op = op or {}
    phase = op.get("stage", "ready")
    members = {m["id"]: m for m in shared.get("members", [])}
    owner = members.get(local_id, {}).get("leader", False)
    member = {**members.get(local_id, {}), **local}
    prices = rates(plan)
    reports = op.get("reports", {})
    accepted = reports.get(local_id, {})
    own = work if work and work.get("operation_id") == op.get("id") else {}
    progress = {key: accepted.get(key, 0) for key in ("loading", "unloading")}
    pending = {key: max(0, own.get(key, 0) - accepted.get("reported", accepted).get(key, 0)) for key in progress}
    total = op.get("quantity") or plan.get("planned_quantity") or None
    carrier = shared.get("carrier") or {}
    carrier_stop = {"station": " / ".join(filter(None, [carrier.get("name"), carrier.get("callsign")])) or "Carrier",
                    "copy_name": carrier.get("callsign") or carrier.get("name"),
                    "system": carrier.get("system"), "market_id": plan.get("carrier_market_id") or None}
    source = stop(plan.get("source"), plan.get("source_market_id"))
    destination = stop(plan.get("destination"), plan.get("destination_market_id"))
    loading = phase == "loading"
    pickup, delivery = (source, carrier_stop) if loading or phase == "ready" else (carrier_stop, destination)
    suggestion = shared.get("load_suggestion") or {}
    allocation = next((r for r in suggestion.get("members", []) if r["id"] == local_id), None)
    excluded = next((r["reason"] for r in suggestion.get("excluded", []) if r["id"] == local_id), None)
    cargo = member.get("cargo_count")
    aboard = min(cargo, sum(i.get("count") or 0 for i in member.get("cargo", [])
                            if norm(i.get("key") or "") == norm(plan["commodity"]))) if type(cargo) is int else None
    remaining = op.get("remaining_load" if loading else "remaining_unload")
    workload = shared.get("workload")
    assignments = {r["id"]: r for r in (workload or {}).get("members", [])}
    assigned = assignments.get(local_id)
    if workload and phase in ("loading", "unloading"):
        quota_remaining = (assigned or {}).get(phase + "_remaining", 0)
        remaining = min(remaining, quota_remaining) if remaining is not None else quota_remaining
    # Local journal snapshots can be newer than the leader's last heartbeat.
    # Consume the previous pickup allowance as matching cargo arrives locally.
    capacity = member.get("capacity")
    free = max(0, capacity - cargo) if type(capacity) is int and type(cargo) is int else 0
    pickup_quantity = min(free, max(0, allocation["next_buy"] - max(0, (aboard or 0) - allocation.get("aboard", 0)))) if allocation else 0
    if remaining is not None:
        pickup_quantity = min(pickup_quantity, max(0, remaining - (aboard or 0)))
    per_ton = prices.get(phase) if not owner else None
    quantity, action, reason = None, "wait", "Waiting for the owner to start loading."
    if phase == "cancelled":
        reason = "Trade cancelled. No further runs requested."
    elif phase == "complete":
        reason = "Trade complete. Your recorded contributions are below."
    elif stale:
        reason = "Leader connection is stale. Wait for fresh instructions before another run."
    elif shared.get("recovering"):
        reason = "Checking journals for missed deliveries. Wait for updated pickup amounts."
    elif op.get("paused"):
        reason = "Paused. Do not start another run; completed deliveries still count."
    elif phase == "transit":
        reason = "Carrier in transit. Wait for unloading to open."
    elif phase in ("loading", "unloading"):
        if excluded:
            reason = "No pickup suggested: " + excluded + "."
        elif member.get("activity") == "away":
            reason = "You are away. Set your status to ready when you return."
        elif pending[phase]:
            reason = "Delivery saved locally. Waiting for leader acknowledgement; do not report it again."
        elif remaining == 0:
            reason = ("The remaining load is assigned to another ship. Wait for the next live update." if workload and workload.get("mode") == "live"
                      else "No workload assigned to you. The owner can rebalance the crew split." if workload and not assigned
                      else "Your share of this leg is done. Wait for the crew or ask the owner to rebalance." if workload
                      else "This leg's target is met. Wait for the owner to advance the trade.")
        elif aboard is None:
            reason = "Waiting for your ship's cargo report."
        elif pickup_quantity > 0:
            action = "transfer_out" if owner and not loading else "buy"
            quantity = pickup_quantity
            reason = "Transfer cargo from your carrier into your ship." if owner and not loading else "Buy the suggested load, then deliver it."
            if aboard and quantity:
                reason = f"You have {aboard:,} t aboard. Pick up {quantity:,} t more, then deliver {aboard + quantity:,} t."
        elif aboard > 0:
            action = "transfer_in" if owner and loading else "deliver"
            quantity = min(aboard, remaining) if remaining is not None else aboard
            reason = "Transfer cargo directly into your carrier." if owner and loading else "Deliver the cargo already aboard your ship."
        else:
            reason = "No pickup needed from you right now. Check crew progress below."
    split = (plan.get("crew_split") if plan.get("crew_enabled") else None) or {}
    buy_price = plan.get("source_price") if loading or phase == "ready" else split.get("carrier_sell_price", plan.get("carrier_price") if plan.get("carrier_price_known") else None)
    sell_price = split.get("carrier_buy_price", plan.get("carrier_price") if plan.get("carrier_price_known") else None) if loading or phase == "ready" else plan.get("destination_price")
    if sell_price is not None and not (loading or phase == "ready") and plan.get("price_includes_bonus"):
        sell_price -= plan.get("bonus_per_ton", 0)
    if plan.get("price_basis") == "unknown acquisition" and (loading or phase == "ready"):
        buy_price = None
    if plan.get("price_basis") == "unknown resale" and phase == "unloading":
        sell_price = None
    roster = []
    for mid in dict.fromkeys([*members, *reports, *assignments]):
        m, r = members.get(mid, {}), reports.get(mid, {})
        is_owner = m.get("leader", False) or r.get("owner", False)
        a = assignments.get(mid, {})
        t = m.get("telemetry") or {}
        roster.append({"id": mid, "cmdr": m.get("cmdr") or r.get("cmdr") or a.get("cmdr") or "Unknown commander",
                       "you": mid == local_id, "owner": is_owner,
                       "connected": bool(m) and not m.get("stale", False) and not stale,
                       "activity": m.get("activity", "offline"), "system": m.get("system"),
                       "ship": m.get("ship"), "station": m.get("station"), "cargo_count": m.get("cargo_count"), "capacity": m.get("capacity"),
                       "telemetry": t, "docked": m.get("docked"), "assignment": a or None,
                       "loading": r.get("loading", 0), "unloading": r.get("unloading", 0),
                       "earnings": None if is_owner else earnings(r, prices)})
    return {"operation_id": op.get("id"), "commodity": plan["commodity"], "phase": phase,
            "paused": op.get("paused", False), "stale": stale, "owner": owner,
            "action": action, "reason": reason, "quantity": quantity, "aboard": aboard,
            "capacity": member.get("capacity"), "cargo_count": cargo,
            "pickup": pickup, "delivery": delivery, "buy_price": buy_price, "sell_price": sell_price,
            "per_ton": per_ton, "load_earnings": (quantity + (aboard or 0) if action in ("buy", "transfer_out") else quantity) * per_ton if quantity is not None and per_ton is not None else None,
            "earnings": None if owner else earnings(progress, prices),
            "progress": progress, "pending": pending, "adjustments": accepted.get("adjustments", {}), "target": total,
            "assignment": assigned,
            "allocation_mode": (workload or {}).get("mode"),
            "loaded": op.get("loaded", 0), "unloaded": op.get("unloaded", 0),
            "notes": op.get("notes", ""), "crew": roster,
            "over_target": bool(total and (op.get("loaded", 0) > total or op.get("unloaded", 0) > total))}
