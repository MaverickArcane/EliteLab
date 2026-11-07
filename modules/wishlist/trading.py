"""Bounded, read-only material trader estimates with executable step ordering."""
from elitelab.core import gamedata as gd


# Recomputed on inventory events: cap candidate work, not just successful trades.
CHAIN_SEARCH_BUDGET = 20_000
TRADER_TYPES = ("Raw", "Manufactured", "Encoded")


def plan_trades(rows, inv, reserve=0):
    """Try direct trades, then pool donors through one intermediate per chain.

    This is a deterministic greedy estimate, not an exhaustive optimizer. Only
    commit a chain if it reduces a wishlist shortfall. Protect need + reserve,
    enforce caps at every step, and reject cycles in the exchange graph.
    """
    reserve = max(0, int(reserve or 0))
    rows = sorted(rows, key=lambda r: (r.get("category") or "", -(r.get("grade") or 0), r["key"]))
    materials = {k: m for k, m in gd.MATERIAL_BY_KEY.items()
                 if m.get("family") and m["category"] in TRADER_TYPES}
    need = {r["key"]: r["need"] for r in rows}
    floor = {k: need.get(k, 0) + reserve for k in materials}
    caps = {k: gd.MATERIAL_CAPS[m["grade"]] for k, m in materials.items()}
    caps.update({r["key"]: r["cap"] for r in rows if r.get("cap") is not None})
    balance = dict(inv)
    original_short = {r["key"]: max(0, r["need"] - balance.get(r["key"], 0)) for r in rows}
    trades, edges, ratios = [], {}, {}

    def ratio(a, b):
        if (a, b) not in ratios:
            ratios[a, b] = gd.trade_ratio(a, b)
        return ratios[a, b]

    def spare(stock, key):
        return max(0, stock.get(key, 0) - floor[key])

    def room(stock, key):
        return max(0, caps[key] - stock.get(key, 0))

    def short(key):
        return max(0, need[key] - balance.get(key, 0))

    def descendants(key):
        found, pending = {key}, [key]
        while pending:
            for child in edges.get(pending.pop(), set()) - found:
                found.add(child)
                pending.append(child)
        return found

    def exchange(stock, steps, donor, target, batches):
        give, get = ratio(donor, target)
        a, b = materials[donor], materials[target]
        before_give, before_get = stock.get(donor, 0), stock.get(target, 0)
        stock[donor] = stock.get(donor, 0) - give * batches
        stock[target] = stock.get(target, 0) + get * batches
        steps.append({"category": b["category"], "ratio": f"{give}:{get}", "same_family": a["family"] == b["family"],
                      "give": {"key": donor, "name": a["name"], "grade": a["grade"], "qty": give * batches,
                               "category": a["category"], "family": a["family"], "before": before_give, "after": stock[donor]},
                      "get": {"key": target, "name": b["name"], "grade": b["grade"], "qty": get * batches,
                              "category": b["category"], "family": b["family"], "before": before_get, "after": stock[target]}})

    def record(steps):
        trades.extend(steps)
        for t in steps:
            edges.setdefault(t["give"]["key"], set()).add(t["get"]["key"])

    # Retain the existing global cheapest-direct-exchange priority.
    options = []
    for r in rows:
        target = r["key"]
        if target not in materials or not short(target):
            continue
        for donor in sorted(materials):
            available = spare(balance, donor)
            rate = ratio(donor, target) if available else None
            if rate:
                give, get = rate
                options.append((give / get, -materials[target]["grade"], -available, donor, target))
    for _, _, _, donor, target in sorted(options):
        give, get = ratio(donor, target)
        batches = min((short(target) + get - 1) // get, spare(balance, donor) // give, room(balance, target) // get)
        if batches and donor not in descendants(target):
            steps = []
            exchange(balance, steps, donor, target, batches)
            record(steps)

    budget = CHAIN_SEARCH_BUDGET
    limited = False
    for r in rows:
        target = r["key"]
        if target not in materials:
            continue
        while short(target) and room(balance, target):
            best = None
            for middle in sorted(materials):
                if budget <= 0:
                    limited = True
                    break
                budget -= 1
                rate = ratio(middle, target)
                if not rate or middle in descendants(target):
                    continue
                give, get = rate
                batches = min((short(target) + get - 1) // get, room(balance, target) // get,
                              max(0, caps[middle] - floor[middle]) // give)
                if not batches:
                    continue
                # Adding middle -> target must not make any funding edge cyclic.
                excluded = descendants(middle) | descendants(target)
                donors = []
                for donor in sorted(materials):
                    if budget <= 0:
                        limited = True
                        break
                    budget -= 1
                    available = spare(balance, donor)
                    funding = ratio(donor, middle) if available and donor not in excluded else None
                    if funding:
                        a, b = funding
                        donors.append((a / b, -available, donor))
                donors.sort()

                def fund(count):
                    stock, steps = dict(balance), []
                    wanted = floor[middle] + count * give
                    for _, _, donor in donors:
                        a, b = ratio(donor, middle)
                        missing = max(0, wanted - stock.get(middle, 0))
                        n = min((missing + b - 1) // b, spare(stock, donor) // a, room(stock, middle) // b)
                        if n:
                            exchange(stock, steps, donor, middle, n)
                    return stock, steps

                stock, steps = fund(batches)
                actual = min(batches, spare(stock, middle) // give)
                if not actual:
                    continue  # No speculative donations that fail to fund a final exchange.
                if actual < batches:
                    stock, steps = fund(actual)  # Do not fund unused partial batches.
                exchange(stock, steps, middle, target, actual)
                covered = min(short(target), actual * get)
                rank = (-covered, len(steps), middle)
                if best is None or rank < best[0]:
                    best = rank, stock, steps
            if best:
                _, balance, steps = best
                record(steps)
            if not best or limited:
                break
        if limited:
            break

    unresolved = [{"key": r["key"], "name": r["name"], "grade": r["grade"], "category": r["category"], "family": r.get("family"),
                   "short": short(r["key"]), **({"note": "not tradeable"} if r["key"] not in materials else {})}
                  for r in rows if short(r["key"])]
    by = {}
    for t in trades:
        b = by.setdefault(t["category"], {"trades": 0, "give": 0, "get": 0})
        b["trades"] += 1
        b["give"] += t["give"]["qty"]
        b["get"] += t["get"]["qty"]
    return {"trades": trades, "by_trader": by, "unresolved": unresolved, "reserve": reserve,
            "covered": sum(original_short.values()) - sum(r["short"] for r in unresolved), "search_limited": limited,
            "note": "Follow exchanges in the listed order. Checks direct exchanges and routes through one intermediate material, "
                    "preserving wishlist needs, reserves and storage limits. This estimate may miss other routes. "
                    + ("Search limit reached; additional trades may be possible. " if limited else "")
                    + "The in-game trader screen is authoritative."}
