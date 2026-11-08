"""Bounded source/market pairing; conditional forecasts use local sale evidence.

No universal credits-to-merits conversion. See docs/MINING.md for researched
Powerplay conditions, empirical limitations and the strict observation match.
"""
import math
import time

from .discovery import MAX_RADIUS, POWER_MODES, age, parameter, token
from .ledger import number


def separation(ring, buyer):
    if ring["system"].casefold() == buyer["system"].casefold():
        return 0.0
    a, b = [ring[k] for k in "xyz"], buyer["coordinates"]
    if any(v is None for v in a + b):
        return None
    return math.dist(a, b)


def forecast(core, ring, buyer, commodity, quantity, power, now):
    pp = ((core.store.get("mining", "summary") or {}).get("powerplay") or {})
    if pp.get("power") != power:
        return None
    for event in pp.get("recent", [])[:12]:
        sale = event.get("sale") or {}
        hours = age(event.get("timestamp"), now)
        tons, gained = number(sale.get("tons")), number(event.get("gained"))
        if (not event.get("sale_associated") or hours is None or hours > 24 or not tons or not gained
                or token(sale.get("commodity")) != token(commodity)
                or sale.get("origin") != ring["system"] or sale.get("origin_state") != ring["power_state"]
                or sale.get("system") != buyer["system"] or sale.get("station") != buyer["station"]
                or sale.get("power_state") != buyer["power_state"] or sale.get("price") != buyer["price"]):
            continue
        return {"merits": round(gained / tons * quantity, 1), "per_ton": round(gained / tons, 3),
                "basis": "conditional_sale_association", "timestamp": event["timestamp"],
                "sample_tons": tons, "sample_merits": gained,
                "note": "Assumes the same earning conditions and merits per ton as this temporally associated sale. "
                        "Association is not causation; bonuses, bulk sale size and cycle changes can change the reward."}
    return None


def rank(discovery, rings, q, ref, radius, power, mode, commodity):
    quantity = parameter(q, "quantity", 1, 1000000, True)
    # One shared station search, not a request per ring. At most 4 body pages,
    # one catalogue and 4 station pages; never widen the mining radius.
    markets = discovery.buyers({"ref": ref, "radius": min(MAX_RADIUS, radius + (30 if mode == "acquisition" else 0)),
                                "commodity": commodity, "quantity": quantity, "pad": q.get("pad", "L"),
                                "hours": q.get("hours", 24)}, _limit=100)
    now = time.time()
    for ring in rings:
        candidates = []
        for buyer in markets["results"]:
            if buyer["power_state"] not in POWER_MODES[mode] or (mode == "reinforcement" and buyer["controlling_power"] != power) or (mode == "acquisition" and (power not in buyer["powers"] or buyer["controlling_power"] is not None)):
                continue
            distance = separation(ring, buyer)
            if mode == "reinforcement":
                compatible = ring["system"].casefold() == buyer["system"].casefold()
            else:
                reach = {"Fortified": 20, "Stronghold": 30}.get(ring["power_state"])
                compatible = reach is not None and distance is not None and distance <= reach
            if not compatible:
                continue
            estimate = forecast(discovery.core, ring, buyer, markets["commodity"], quantity, power, now)
            candidates.append({**buyer, "from_ring_ly": round(distance, 3), "merit_estimate": estimate,
                               "merit_eligibility": "reported_candidate"})
        candidates.sort(key=lambda b: (b["merit_estimate"] is None,
            -(b["merit_estimate"]["merits"] if b["merit_estimate"] else 0), -b["price"], b["from_ring_ly"], b["station"]))
        ring.update({"commodity": markets["commodity"], "quantity": quantity, "powerplay_mode": mode,
                     "buyer": candidates[0] if candidates else None,
                     "merit_estimate": candidates[0]["merit_estimate"] if candidates else None,
                     "merit_eligibility": "reported_candidate" if candidates else "unknown",
                     "merit_note": "Confirm the local mining activity, pledge, source and cargo provenance in game. "
                                   "Carrier transfers can remove mining origin. " +
                                   ("No matching recent sale evidence; yield unknown." if not candidates or not candidates[0]["merit_estimate"]
                                    else "Conditional forecast from a recent matching sale; not recorded future gains.")})
    rings.sort(key=lambda r: (r["merit_estimate"] is None,
        -(r["merit_estimate"]["merits"] if r["merit_estimate"] else 0), r["buyer"] is None,
        -(r["buyer"]["price"] if r["buyer"] else 0), r["distance"], r["ring"]))
    return {"powerplay_mode": mode, "commodity": markets["commodity"], "quantity": quantity,
            "pad": q.get("pad", "L"), "hours": parameter(q, "hours", 24, 72),
            "stations_checked": markets["stations_checked"], "market_note": markets["note"],
            "ranking_note": "Conditional merit estimates first. Unknown yields follow, with reported source/market candidates "
                            "ordered by sale price, then distance. Price ordering is a fallback, not a merit forecast. "
                            "No merits/hour estimate: extraction and travel rates are unknown. At most the nearest 30 rings "
                            "and 100 nearby markets are compared; this is not a galaxy-wide optimum."}
