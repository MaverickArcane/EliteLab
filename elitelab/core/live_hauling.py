"""Live next-load allocation: preserve cargo, share work by available holds."""
import hashlib
import json
from .gamedata import norm


def distribute(total, spaces):
    """Full crew rounds, then the fewest ships needed for the final pickup."""
    result = dict.fromkeys(spaces, 0)
    available = {mid: size for mid, size in spaces.items() if size > 0}
    capacity = sum(available.values())
    if not capacity:
        return result, total
    rounds, tail = divmod(total, capacity)
    for mid, size in available.items():
        result[mid] = rounds * size
    fits = [mid for mid, size in available.items() if size >= tail]
    if tail and fits:
        result[min(fits, key=lambda mid: (available[mid], mid))] += tail
    elif tail:
        for mid in sorted(available, key=lambda mid: (-available[mid], mid)):
            take = min(tail, available[mid])
            result[mid] += take
            tail -= take
            if not tail:
                break
    return result, 0


def build_live(plan, operation, members, settings, previous, quantity):
    op, previous = operation or {}, previous or {}
    reports, owner_hauls = op.get("reports", {}), settings.get("owner_hauls", True)
    old = {r["id"]: r for r in previous.get("members", [])}
    live = {m["id"]: m for m in members}
    known = {mid: {**r, "leader":r["owner"], "stale":True} for mid, r in old.items()}
    known.update(live)
    for mid, report in reports.items():
        known.setdefault(mid, {"id":mid, "cmdr":report.get("cmdr"), "leader":report.get("owner",False), "stale":True})
    stage = op.get("stage", "ready")
    current = "unloading" if stage in ("transit", "unloading", "complete") else "loading"
    snapshots, cargo, spaces, usable, eligible = {}, {}, {}, {}, {}
    for mid, member in known.items():
        snapshot = old.get(mid, {}).get("cargo_snapshot", {})
        count = member.get("cargo_count")
        if mid in live and (not member.get("stale") or member.get("departed") or not snapshot) and type(count) is int and count >= 0:
            observed = {"count":count, "matching":min(count, sum(i.get("count") or 0 for i in member.get("cargo", [])
                        if norm(i.get("key") or "") == norm(plan["commodity"]))), "at":member.get("cargo_at")}
            # A delivery can arrive before Cargo.json changes. Repeated copies
            # of that old hold must not re-reserve the cargo just delivered.
            if any(snapshot.get(k) != value for k,value in observed.items()):
                snapshot = {**observed,"delivered":{p:reports.get(mid, {}).get(p,0) for p in ("loading","unloading")}}
        snapshots[mid] = snapshot
        # Retain absent ships' physical cargo, but consume any later credited delivery.
        delta = sum(max(0, reports.get(mid, {}).get(p,0)-snapshot.get("delivered",{}).get(p,0)) for p in ("loading","unloading"))
        cargo[mid] = max(0, snapshot.get("matching",0)-delta)
        capacity = member.get("capacity")
        telemetry = member.get("telemetry") or {}
        valid = type(capacity) is int and capacity > 0 and type(count) is int and 0 <= count <= capacity
        eligible[mid] = bool(valid and not member.get("stale") and member.get("activity") != "away"
                             and telemetry.get("game_running") is not False and telemetry.get("vehicle") in (None,"ship")
                             and (owner_hauls or not member.get("leader")))
        usable[mid] = max(0, capacity-max(0,count-snapshot.get("matching",0))) if valid else 0
        spaces[mid] = max(0,capacity-count) if eligible[mid] else 0
    targets, unassigned, reserved = {}, {}, {}
    for phase in ("loading", "unloading"):
        delivered = {mid:reports.get(mid,{}).get(phase,0) for mid in known}
        remaining = max(0, quantity-sum(delivered.values()))
        if phase == "loading" and current == "unloading":
            targets[phase], unassigned[phase], reserved[phase] = delivered, 0, 0
            continue
        committed, left = dict.fromkeys(known,0), remaining
        if phase == current:
            for mid in sorted(known):
                committed[mid] = min(left,cargo[mid])
                left -= committed[mid]
        future_space = {mid:usable[mid] if eligible[mid] else 0 for mid in known}
        if phase == current:
            # Decide this pickup using free space, then estimate later rounds
            # using usable holds. A full ship still has work after delivering.
            pickups, _ = distribute(min(left,sum(spaces.values())), spaces)
            future, unassigned[phase] = distribute(left-sum(pickups.values()), future_space)
            portions = {mid:pickups[mid]+future[mid] for mid in known}
        else:
            portions, unassigned[phase] = distribute(left, future_space)
        targets[phase] = {mid:delivered[mid]+committed[mid]+portions[mid] for mid in known}
        reserved[phase] = sum(committed[mid] for mid in known if not eligible[mid])
    rows = [{"id":mid,"cmdr":m.get("cmdr") or "Unknown commander","owner":bool(m.get("leader")),
             "capacity":m.get("capacity"),"weight":int(eligible[mid]),"cargo_snapshot":snapshots[mid],
             "loading_target":targets["loading"][mid],"unloading_target":targets["unloading"][mid]} for mid,m in known.items()]
    basis = {"plan":plan,"operation_id":op.get("id"),"stage":stage,"reports":reports,"rows":rows,
             "owner_hauls":owner_hauls,"mode":"live","unassigned":unassigned}
    return {"mode":"live","owner_hauls":owner_hauls,"shares":{},"quantity":quantity,"members":rows,
            "unassigned":unassigned,"reserved":reserved,
            "basis":hashlib.sha256(json.dumps(basis,sort_keys=True).encode()).hexdigest()}
