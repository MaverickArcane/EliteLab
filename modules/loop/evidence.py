"""Bounded cargo and local-market evidence for the rare buying workflow."""
import datetime as dt
import math
import time


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


def workflow(j, arrived, cargo_since=None):
    cargo = j.get("cargo") or {}
    items = cargo.get("items")
    count, cap = qty(cargo.get("count")), qty(j.get("cargo_capacity"))
    known = count is not None and isinstance(items, list) and len(items) <= 256 and all(isinstance(i, dict) and qty(i.get("count")) is not None for i in items)
    if known:
        known = count == int(count) and all(i["count"] == int(i["count"]) for i in items) and sum(i["count"] for i in items) == count
    if cargo_since is not None:
        observed = timestamp(cargo.get("timestamp"))
        known = known and observed is not None and observed >= cargo_since
    market = j.get("market") or {}
    stamp = timestamp(market.get("timestamp"))
    same = bool(j.get("docked") and label(j.get("system")).casefold() == label(market.get("system")).casefold()
                and label(j.get("station")) and label(j.get("station")).casefold() == label(market.get("station")).casefold())
    if not market.get("station"):
        state, message = "not_recorded", "Open the commodities market in game to record local rare stock."
    elif not same:
        state, message = "previous_station", "Snapshot from a previous station. Open the market at your current station to refresh."
    elif stamp is None or stamp > time.time():
        state, message = "undated", "Market time is missing, invalid or in the future. Stock freshness is unknown."
    elif arrived is None or stamp < arrived:
        state, message = "previous_visit", "Snapshot predates this visit, or arrival time is unknown. Open the market again before buying."
    else:
        state, message = "current_snapshot", "Snapshot recorded at this station during this visit. Stock and prices can change; confirm in game."
    rows = market.get("rares_in_stock")
    rows = [{"name":label(r.get("name")), "buy":qty(r.get("buy")), "stock":qty(r.get("stock"))}
            for r in (rows[:256] if isinstance(rows, list) else []) if isinstance(r, dict)]
    return {"cargo_known":known, "free_capacity":max(0,cap-count) if known and cap is not None else None,
            "market":{"status":state, "message":message, "station":label(market.get("station")),
                      "system":label(market.get("system")), "timestamp":label(market.get("timestamp")), "rares":rows}}
