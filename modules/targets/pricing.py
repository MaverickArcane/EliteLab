"""Rare-goods estimates from bounded observations, never a universal price law.

Distances use each rare's source. Piecewise interpolation is opt-in and never
extrapolates. The optional 667 Cr/merit setting is the owner's October 2026
Mahon observation (CLAUDE.md), not a rate for other powers or activities.
"""
import datetime as dt
import math
import statistics

from elitelab.core.gamedata import RARES


def label(value):
    return value.strip()[:160] if isinstance(value, str) else ""


def token(value):
    return "".join(c for c in label(value).casefold() if c.isalnum())


RARE_KEYS = {token(name): key for key, name in RARES.items()}
RARE_KEYS.update({token(key): key for key in RARES})


def rare_key(value):
    return RARE_KEYS.get(token(value.replace("$", "").removesuffix("_name;"))) if isinstance(value, str) else None


def number(value, maximum=10**12):
    try:
        n = float(value)
        return n if not isinstance(value, bool) and math.isfinite(n) and 0 <= n <= maximum else None
    except (ValueError, TypeError, OverflowError):
        return None


def param(q, key, default, maximum, minimum=0, integer=False):
    n = number(q.get(key, default), maximum)
    if n is None or n < minimum or (integer and n != int(n)):
        raise ValueError(f"{key} must be {'a whole number' if integer else 'a number'} from {minimum} to {maximum}.")
    return int(n) if integer else n


def coords(value):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        return None
    return list(value) if all(type(n) in (int, float) and number(abs(n), 1000000) is not None for n in value) else None


def age(value, now):
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        seconds = now - t.timestamp()
        return seconds / 3600 if t.tzinfo and seconds >= 0 else None
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return None


def interpolate(points, distance):
    if distance is None:
        return None
    for a, b in zip(points, points[1:]):
        if a["distance"] <= distance <= b["distance"] and a["distance"] < b["distance"]:
            fraction = (distance - a["distance"]) / (b["distance"] - a["distance"])
            return a["price"] + fraction * (b["price"] - a["price"])
    return None


def estimate(rows, cargo, rate, allow_curve):
    curves = []
    for item in cargo:
        grouped = {}
        for row in rows:
            quote = row["goods"][item["key"]]
            if quote["source_distance"] is not None and quote["price"] and quote["status"] == "reported":
                grouped.setdefault(quote["source_distance"], []).append(quote["price"])
        points = [{"distance": d, "price": statistics.median(prices), "observations":len(prices)}
                  for d, prices in sorted(grouped.items())]
        curves.append({"key":item["key"], "name":item["name"], "origin":item["origin"], "points":points,
                       "note":"Median reported prices at each source distance, joined linearly for comparison; market conditions also affect price."})
        if allow_curve:
            for row in rows:
                quote = row["goods"][item["key"]]
                # Missing market listings never establish acceptance. Only an
                # explicitly listed, legal good with sufficient demand can use a model.
                if quote["status"] == "price_unknown":
                    price = interpolate(points, quote["source_distance"])
                    if price is not None:
                        quote.update(price=round(price, 2), status="interpolated")
    for row in rows:
        subtotal, priced, blocked = 0, 0, False
        for item in cargo:
            quote = row["goods"][item["key"]]
            if quote["price"] is not None and quote["status"] in ("reported", "interpolated"):
                quote["sale_value"] = round(quote["price"] * item["tons"], 2)
                subtotal += quote["sale_value"]
                priced += 1
            else:
                quote["sale_value"] = None
            quote["eligibility"] = "blocked" if item["carrier_exposed"] or item["stolen"] or (item["origin"] and item["origin"].casefold() == row["system"].casefold()) or quote["status"] == "prohibited" else "unverified"
            blocked |= quote["eligibility"] == "blocked"
        complete = bool(cargo) and priced == len(cargo)
        row.update(priced_goods=priced, goods_count=len(cargo), priced_subtotal=round(subtotal, 2),
                   estimated_sale=round(subtotal, 2) if complete else None,
                   estimated_merits=round(subtotal / rate, 2) if complete and rate and not blocked else None,
                   merit_eligibility="blocked" if blocked else "unverified")
        # A zero-jump destination has no finite merits/jump rate. It is shown,
        # not divided by an invented jump or promoted to infinite efficiency.
        row["merits_per_jump"] = round(row["estimated_merits"] / row["jumps"], 2) if row["estimated_merits"] is not None and row["jumps"] else None
    return curves
