"""PTN arithmetic and validation. Targets are estimates, never guaranteed income."""
import math
import re
from bisect import bisect_left
from datetime import datetime, timezone

COMMON = ['agronomictreatment', 'gold', 'silver', 'bertrandite', 'indite', 'gallite', 'palladium', 'tritium']
ORBITAL = {'Coriolis', 'Orbis', 'Ocellus', 'AsteroidBase', 'Outpost', 'Dodec',
           'Coriolis Starport', 'Orbis Starport', 'Ocellus Starport', 'Asteroid base', 'Dodec Starport'}
DEFAULTS = dict(quantity=18000, loading_floor=20000, unloading_floor=20000, owner_floor=2500,
                radius=450, max_hop=450, hours=6, arrival=2000, breadth=24, skip_common=True,
                avoid_active=True, excluded='', hauler_capacity=784, cycle_minutes=5, haulers=3,
                cost_reserve=5000000, share_surplus=True)


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else 0
    except (ValueError, TypeError, AttributeError, OverflowError):
        return 0


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value, label, low=0, high=10**9):
    try:
        number = float(value)
        if isinstance(value, bool) or not math.isfinite(number) or number != int(number) or not low <= number <= high:
            raise ValueError()
        return int(number)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f'{label} must be a whole number from {low} to {high}.') from None


def line(value, label, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f'{label} must be one line of text, up to {limit} characters.')
    return value.strip()


def key(value):
    # Matching only; API commodity identifiers are retained separately.
    return ''.join(c for c in str(value).casefold() if c.isalnum())


def settings(query):
    out = {}
    bounds = dict(quantity=(1, 25000), loading_floor=(1, 1000000), unloading_floor=(1, 1000000),
                  owner_floor=(0, 1000000), radius=(1, 500), max_hop=(1, 500), hours=(1, 24),
                  arrival=(1, 50000), breadth=(1, 48), hauler_capacity=(1, 1000), cycle_minutes=(1, 60),
                  haulers=(1, 50), cost_reserve=(0, 10**10))
    for name, default in DEFAULTS.items():
        value = query.get(name, default)
        if name in bounds:
            out[name] = integer(value, name.replace('_', ' '), *bounds[name])
        elif name in ('skip_common', 'avoid_active', 'share_surplus'):
            if value not in (True, False, 'true', 'false', '1', '0'):
                raise ValueError('Choose whether to exclude common and active commodities.')
            out[name] = value in (True, 'true', '1')
        else:
            if not isinstance(value, str) or len(value) > 1000:
                raise ValueError('Excluded commodities must be comma-separated text up to 1000 characters.')
            out[name] = value
    return out


def pricing(buy, sell, quantity, mean, prefs):
    target_buy, target_sell = buy + prefs['loading_floor'], sell - prefs['unloading_floor']
    bp = sp = None
    cb, cs = target_buy, target_sell
    if type(mean) is int and mean > 0:
        # Unlike nearest-price rounding, these choices never underpay either floor.
        prices = [(p, (mean * p + 50) // 100) for p in range(5, 1001)]
        b = next(((p, v) for p, v in prices if v >= target_buy), None)
        s = next(((p, v) for p, v in reversed(prices) if v <= target_sell), None)
        if b:
            bp, cb = b
        if s:
            sp, cs = s
        if prefs.get('share_surplus',True):
            # Maximize the weaker hauler payout, then their combined payout,
            # while retaining the owner's minimum and the operation reserve.
            owner_min = max(prefs['owner_floor'],math.ceil(prefs['cost_reserve']/quantity))
            values = [v for _,v in prices]
            best = None
            for percent,value in prices:
                if value < target_buy:
                    continue
                at = bisect_left(values,value+owner_min)
                if at>=len(prices):
                    continue
                sell_percent,sell_value = prices[at]
                if sell_value>target_sell:
                    continue
                loading,unloading = value-buy,sell-sell_value
                score = (min(loading,unloading),loading+unloading,-abs(loading-unloading),-value)
                if best is None or score>best[0]:
                    best = (score,percent,value,sell_percent,sell_value)
            if best:
                _,bp,cb,sp,cs = best
    owner = cs - cb
    load, unload = cb - buy, sell - cs
    valid = bp is not None and sp is not None and owner >= prefs['owner_floor']
    return dict(station_buy=buy, station_sell=sell, mean_price=mean, carrier_buy=cb, carrier_sell=cs,
                buy_percent=bp, sell_percent=sp, loading_per_ton=load, unloading_per_ton=unload,
                owner_per_ton=owner, gross_per_ton=sell-buy, gross_total=(sell-buy)*quantity,
                hauler_total=(load+unload)*quantity, owner_total=owner*quantity,
                cost_reserve=prefs['cost_reserve'], owner_after_reserve=owner*quantity-prefs['cost_reserve'],
                funding=cb*quantity, settings_valid=valid,
                spread_short=max(0, prefs['loading_floor']+prefs['unloading_floor']+prefs['owner_floor']-(sell-buy)))


def markdown(value):
    value = line(value, 'Advert text')
    if '@' in value or '`' in value:
        raise ValueError('Advert fields cannot contain mentions or backticks.')
    return re.sub(r'([\\*_~|\[\]])', r'\\\1', value)


def compact(number):
    # Three decimal places preserve exact whole-credit/t quantities; never round up.
    return (str(number//1000) if number % 1000 == 0 else f'{number/1000:.3f}'.rstrip('0')) + 'k'


def advert(carrier, callsign, commodity, station, system, phase, profit, quantity):
    if not re.fullmatch(r'[A-Z0-9]{3}-[A-Z0-9]{3}', callsign or ''):
        raise ValueError('A valid carrier callsign is needed before making an advert.')
    if profit <= 0 or quantity <= 0:
        raise ValueError('An advert needs a positive hauler profit and remaining order.')
    verb, direction = ('loading', 'from') if phase == 'loading' else ('unloading', 'to')
    return (f'**{markdown(carrier)} ({callsign})** is {verb} **{markdown(commodity)}** {direction} '
            f'**{markdown(station)}** (L pads) in **{markdown(system)}**. '
            f'{compact(profit)}/unit profit, {compact(quantity)} units')
