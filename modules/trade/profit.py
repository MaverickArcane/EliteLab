"""Percentage carrier settings and conserved two-leg crew payouts."""


class CarrierPriceUnavailable(ValueError):
    pass


def preview(q):
    rows = q.get("rows")
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("Provide at most 100 route prices.")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Each route must contain buy, sell and quantity values.")
    splits = []
    for row in rows:
        try:
            splits.append(split_profit(row.get("buy"), row.get("sell"), row.get("quantity"),
                                       q.get("loading",25), q.get("unloading",25), row.get("mean_price")))
        except CarrierPriceUnavailable as error:
            splits.append({"error":str(error)})
    return {"splits":splits}


def split_profit(buy, sell, quantity, loading=25, unloading=25, mean_price=None):
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
    target_buy, target_sell = buy + load, sell - unload
    buy_percent = sell_percent = None
    if mean_price is not None and (type(mean_price) is not int or not 0 <= mean_price <= 1000000000):
        raise ValueError("The 100% carrier price must be a positive whole number, or zero when unknown.")
    if mean_price:
        # Use whole percentage settings and round to displayed whole credits.
        # Choose within the station spread so neither leg nor the owner loses.
        settings = [(percent, (mean_price * percent + 50) // 100) for percent in range(5, 1001)]
        settings = [(percent, price) for percent, price in settings if buy <= price <= sell]
        if not settings:
            raise CarrierPriceUnavailable("No carrier percentage setting between 5% and 1000% fits this route without a loss.")
        buy_percent, carrier_buy = min(settings, key=lambda pair: (abs(pair[1]-target_buy), pair[1]))
        sell_percent, carrier_sell = min(settings, key=lambda pair: (abs(pair[1]-target_sell), pair[1]))
        load, unload = carrier_buy - buy, sell - carrier_sell
    owner = spread - load - unload
    total = lambda n: n * quantity if quantity is not None else None
    return {"quantity": quantity, "loading_percent": loading, "unloading_percent": unloading,
            "mean_price": mean_price or None, "carrier_prices_valid": buy_percent is not None,
            "carrier_buy_percent": buy_percent, "carrier_sell_percent": sell_percent,
            "target_carrier_buy_price": target_buy, "target_carrier_sell_price": target_sell,
            "owner_percent": 100 - loading - unloading, "carrier_buy_price": buy + load,
            "carrier_sell_price": sell - unload, "loading_per_ton": load, "unloading_per_ton": unload,
            "owner_per_ton": owner, "gross_profit": total(spread), "owner_profit": total(owner),
            "loading_profit": total(load), "unloading_profit": total(unload), "crew_profit": total(load + unload)}
