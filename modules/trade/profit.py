"""Whole-credit carrier order prices and conserved two-leg crew payouts."""


def preview(q):
    rows = q.get("rows")
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Provide at most 100 route prices.")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Each route must contain buy, sell and quantity values.")
    return {"splits": [split_profit(row.get("buy"), row.get("sell"), row.get("quantity"),
                                   q.get("loading", 25), q.get("unloading", 25)) for row in rows]}


def split_profit(buy, sell, quantity, loading=25, unloading=25):
    for name, value in (("Buy price", buy), ("Sell price", sell), ("Loading share", loading), ("Unloading share", unloading)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(name + " must be a non-negative whole number.")
    if loading + unloading > 100:
        raise ValueError("Loading and unloading shares cannot exceed 100% together.")
    if sell < buy:
        raise ValueError("Sell price must cover the buy price before sharing profit.")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0):
        raise ValueError("Quantity must be a non-negative whole number or unknown.")
    spread = sell - buy
    load = spread * loading // 100
    unload = spread * unloading // 100
    owner = spread - load - unload
    total = lambda n: n * quantity if quantity is not None else None
    return {"quantity": quantity, "loading_percent": loading, "unloading_percent": unloading,
            "owner_percent": 100 - loading - unloading, "carrier_buy_price": buy + load,
            "carrier_sell_price": sell - unload, "loading_per_ton": load, "unloading_per_ton": unload,
            "owner_per_ton": owner, "gross_profit": total(spread), "owner_profit": total(owner),
            "loading_profit": total(load), "unloading_profit": total(unload), "crew_profit": total(load + unload)}
