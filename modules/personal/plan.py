"""Selected commodity route: the next action from journal evidence, never from assumptions.

A plan is one row from a Trading search (one or two legs). Progress is derived from
what the journal shows: exact docking, observed cargo, recorded MarketBuy/MarketSell
events at the planned market IDs. Cargo aboard is not a purchase receipt, a quote is
not a guarantee, and distance is a straight line, not a plotted route.
"""
import datetime as dt
import hashlib
import math

FRESH_HOURS, AGING_HOURS = 12, 48
STAGES = {
    "travel_buy": "Travel to the buy station",
    "buy": "Buy the load",
    "travel_sell": "Travel to the sell station",
    "sell": "Sell the load",
    "complete": "Route complete",
}


def label(value):
    return value.strip()[:160] if isinstance(value, str) else ""


def qty(value):
    return value if type(value) in (int, float) and 0 <= value <= 10**9 and math.isfinite(value) else None


def xyz(value):
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(type(v) in (int, float) and abs(v) <= 10**6 and math.isfinite(v) for v in value)


def timestamp(value):
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.timestamp() if d.tzinfo else None
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return None


def commodity_key(name):
    return "".join(c for c in str(name or "").casefold() if c.isalnum())


def same_goods(a, b):
    ka, kb = commodity_key(a), commodity_key(b)
    return bool(ka) and ka == kb


def route_id(row):
    parts = [str(row.get("route_type")), str(row.get("quantity"))]
    parts += [f"{l['buy']['market_id']}-{l['sell']['market_id']}-{commodity_key(l['commodity'])}" for l in row.get("legs", [])]
    return hashlib.sha1(":".join(parts).encode("utf-8")).hexdigest()[:16]


def valid_stop(stop):
    return (isinstance(stop, dict) and type(stop.get("market_id")) is int and stop["market_id"] > 0
            and label(stop.get("station")) and label(stop.get("system"))
            and qty(stop.get("price")) is not None and (stop.get("volume") is None or qty(stop.get("volume")) is not None)
            and (stop.get("pos") is None or xyz(stop.get("pos"))))


def valid_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("legs"), list) or not 1 <= len(plan["legs"]) <= 2:
        return False
    if type(plan.get("quantity")) is not int or plan["quantity"] <= 0 or not isinstance(plan.get("id"), str):
        return False
    for leg in plan["legs"]:
        if not isinstance(leg, dict) or not label(leg.get("commodity")) or type(leg.get("quantity")) is not int or leg["quantity"] <= 0:
            return False
        if not valid_stop(leg.get("buy")) or not valid_stop(leg.get("sell")):
            return False
    return True


def plan_from_row(row, now, cmdr, source):
    """Keep only what the workflow needs from a search row."""
    keep = ("market_id", "station", "system", "pad", "arrival_ls", "observed_at", "price", "volume", "pos")
    legs = [{"commodity": leg["commodity"], "quantity": int(leg["quantity"]),
             "buy": {k: leg["buy"].get(k) for k in keep}, "sell": {k: leg["sell"].get(k) for k in keep},
             "per_ton": leg["per_ton"], "profit": leg["profit"], "cost": leg["cost"]} for leg in row["legs"]]
    plan = {"id": row["id"], "route_type": row["route_type"], "quantity": int(row["quantity"]), "legs": legs,
            "profit": row["profit"], "cost": row["cost"], "required_credits": row["required_credits"],
            "distance": row["distance"], "total_distance": row["total_distance"], "estimated_jumps": row["estimated_jumps"],
            "selected_at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(), "cmdr": label(cmdr) or None,
            "source": source}
    if not valid_plan(plan):
        raise ValueError("That route is missing station or price details and cannot be selected.")
    return plan


def cargo_evidence(j):
    cargo = j.get("cargo") or {}
    items = cargo.get("items")
    count = qty(cargo.get("count"))
    known = (count is not None and isinstance(items, list) and len(items) <= 256
             and all(isinstance(i, dict) and qty(i.get("count")) is not None for i in items))
    if known:
        known = count == int(count) and all(i["count"] == int(i["count"]) for i in items) and sum(i["count"] for i in items) == count
    return known, (items if known else [])


def aboard(items, commodity):
    return sum(int(i["count"]) for i in items if same_goods(i.get("name"), commodity) or same_goods(i.get("key"), commodity))


def docked_at(j, stop):
    return bool(j.get("docked") and label(j.get("system")).casefold() == label(stop.get("system")).casefold()
                and label(j.get("station")) and label(j.get("station")).casefold() == label(stop.get("station")).casefold())


def quotes(plan, now):
    stamps = [timestamp(s.get("observed_at")) for leg in plan["legs"] for s in (leg["buy"], leg["sell"])]
    stamps = [s for s in stamps if s is not None and s <= now]
    if len(stamps) < 2 * len(plan["legs"]):
        return {"age_hours": None, "status": "unknown", "message": "Report times are missing; treat prices as unverified."}
    age = (now - min(stamps)) / 3600
    status = "fresh" if age < FRESH_HOURS else "aging" if age < AGING_HOURS else "stale"
    message = {"fresh": "Prices reported within the last 12 hours. Confirm in game before buying.",
               "aging": "Oldest report is over 12 hours old. Supply, demand and prices may have moved.",
               "stale": "Oldest report is over 48 hours old. Search again before committing to this route."}[status]
    return {"age_hours": round(age, 1), "status": status, "message": message}


def counts(events, plan):
    """Recorded MarketBuy/MarketSell tonnes per leg at the planned market IDs since selection."""
    since = timestamp(plan.get("selected_at"))
    out = [{"bought": 0, "spent": 0, "sold": 0, "sale_total": 0} for _ in plan["legs"]]
    for ev in events:
        if not isinstance(ev, dict):
            continue
        stamp = timestamp(ev.get("timestamp"))
        if since is not None and (stamp is None or stamp < since):
            continue
        goods, market, count = ev.get("Type_Localised") or ev.get("Type"), ev.get("MarketID"), qty(ev.get("Count"))
        if count is None or type(market) is not int:
            continue
        for i, leg in enumerate(plan["legs"]):
            if not (same_goods(goods, leg["commodity"]) or same_goods(ev.get("Type"), leg["commodity"])):
                continue
            if ev.get("event") == "MarketBuy" and market == leg["buy"]["market_id"]:
                out[i]["bought"] += int(count)
                out[i]["spent"] += int(qty(ev.get("TotalCost")) or 0)
            elif ev.get("event") == "MarketSell" and market == leg["sell"]["market_id"]:
                out[i]["sold"] += int(count)
                out[i]["sale_total"] += int(qty(ev.get("TotalSale")) or 0)
    return out


def progress(plan, j, events, now):
    known, items = cargo_evidence(j)
    recorded = counts(events, plan)
    legs = []
    for leg, rec in zip(plan["legs"], recorded):
        have = aboard(items, leg["commodity"]) if known else None
        done = rec["sold"] >= leg["quantity"] or (rec["sold"] > 0 and known and have == 0)
        legs.append({**rec, "commodity": leg["commodity"], "quantity": leg["quantity"], "aboard": have, "done": done})
    index = next((i for i, l in enumerate(legs) if not l["done"]), None)
    ship = j.get("star_pos") if xyz(j.get("star_pos")) else None
    out = {"leg": index, "leg_count": len(legs), "legs": legs, "cargo_known": known, "quotes": quotes(plan, now),
           "commander_changed": bool(plan.get("cmdr") and label(j.get("cmdr")) and label(j.get("cmdr")) != plan["cmdr"]),
           "credits": qty(j.get("credits")), "credits_short": None, "next": None}
    if index is None:
        sales = sum(l["sale_total"] for l in legs)
        out.update(stage="complete", title=STAGES["complete"], action="Route complete", quantity=None,
                   reason=f"Recorded sales total {sales:,} Cr before fuel and fees. Profit depends on what you paid; see the journal history.")
        return out
    leg, current = plan["legs"][index], legs[index]
    have, at_buy, at_sell = current["aboard"], docked_at(j, leg["buy"]), docked_at(j, leg["sell"])
    if known:
        topping_up = at_buy and 0 < have < leg["quantity"] and current["sold"] == 0
        if have > 0 and not topping_up:
            stage = "sell" if at_sell else "travel_sell"
        else:
            stage = "buy" if at_buy else "travel_buy"
    else:
        stage = "buy" if at_buy else "sell" if at_sell else "travel_sell" if current["bought"] > 0 else "travel_buy"
    buying = stage in ("buy", "travel_buy")
    stop = leg["buy"] if buying else leg["sell"]
    dist = round(math.dist(ship, stop["pos"]), 1) if ship and stop.get("pos") else None
    supply = f"{int(qty(leg['buy']['volume']) or 0):,} t supply"
    demand = f"{int(qty(leg['sell']['volume']) or 0):,} t demand"
    tons = f"{have:,} t" if known and have else f"{leg['quantity']:,} t"
    unseen = "" if known else " Cargo has not been observed; confirm the hold in game."
    if stage == "buy":
        quantity = max(0, leg["quantity"] - have) if known else leg["quantity"]
        action = f"Buy {quantity:,} t {leg['commodity']}"
        reason = (f"Docked at {leg['buy']['station']}. " + (f"{have:,} t already aboard. " if known and have else "")
                  + f"Reported {leg['buy']['price']:,} Cr/t with {supply}." + unseen)
        out["credits_short"] = (out["credits"] < leg["buy"]["price"] * quantity) if out["credits"] is not None else None
    elif stage == "travel_buy":
        quantity = leg["quantity"]
        action = f"Travel to {leg['buy']['station']}, {leg['buy']['system']}"
        reason = f"Buy {leg['quantity']:,} t {leg['commodity']} there at a reported {leg['buy']['price']:,} Cr/t with {supply}."
    elif stage == "travel_sell":
        quantity = have if known else None
        action = f"Travel to {leg['sell']['station']}, {leg['sell']['system']}"
        reason = f"Sell {tons} {leg['commodity']} there at a reported {leg['sell']['price']:,} Cr/t with {demand}." + unseen
    else:
        quantity = have if known else None
        action = f"Sell {tons} {leg['commodity']}"
        reason = (f"Docked at {leg['sell']['station']}. Reported {leg['sell']['price']:,} Cr/t with {demand}."
                  + (f" {current['sold']:,} t sold here so far." if current["sold"] else "") + unseen)
    if index + 1 < len(legs) and not buying:
        reason += f" Then buy {plan['legs'][index + 1]['commodity']} for the return leg."
    out.update(stage=stage, title=STAGES[stage], action=action, reason=reason, quantity=quantity,
               next={"role": "buy" if buying else "sell", "station": stop["station"], "system": stop["system"],
                     "market_id": stop["market_id"], "pos": stop.get("pos"), "dist": dist, "docked_here": at_buy if buying else at_sell})
    return out
