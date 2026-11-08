"""PTN arithmetic and validation. Targets are estimates, never guaranteed income."""
import math
import re
import unicodedata
from bisect import bisect_left
from datetime import datetime, timezone

COMMON = ['agronomictreatment', 'gold', 'silver', 'bertrandite', 'indite', 'gallite', 'palladium', 'tritium']
ORBITAL = {'Coriolis', 'Orbis', 'Ocellus', 'AsteroidBase', 'Outpost', 'Dodec',
           'Coriolis Starport', 'Orbis Starport', 'Ocellus Starport', 'Asteroid base', 'Dodec Starport'}
SURFACE = {'CraterOutpost', 'CraterPort', 'OnFootSettlement', 'Planetary Outpost',
           'Planetary Port', 'Odyssey Settlement'}
DEFAULTS = dict(quantity=18000, loading_floor=20000, unloading_floor=20000, owner_floor=1000,
                radius=1500, max_hop=1500, hours=24, arrival=0, breadth=0, skip_common=False,
                avoid_active=False, excluded='', hauler_capacity=784, cycle_minutes=5, haulers=3,
                cost_reserve=5000000, share_surplus=False, haul_mode='both', payout_target=20000,
                allow_partial=True, min_quantity=2000, allow_surface_loading=False)


def station_kind(station_type, planetary=False):
    if not isinstance(station_type, str):
        return None
    if station_type in SURFACE:
        return 'surface'
    if station_type in ORBITAL and not planetary:
        return 'orbital'
    return None


def paid_leg(prefs, phase):
    return prefs.get('haul_mode', 'both') != ('self_load' if phase == 'loading' else 'self_unload')


def unlimited_demand(stop, side):
    # Explicit evidence only: missing demand and exhausted loading stock are not unlimited.
    return (side == 'sell' and stop.get('demand_unlimited') is True
            and type(stop.get('volume')) is int and stop['volume'] == 0
            and type(stop.get('price')) is int and 0 < stop['price'] <= 10**9)


def owner_minimum(prefs, quantity):
    # Cover the reserve AND leave a positive return, even on a smaller order.
    return max(prefs['owner_floor'], prefs['cost_reserve'] // quantity + 1)


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
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(unicodedata.category(c).startswith('C') or c in '\u2028\u2029' for c in value)):
        raise ValueError(f'{label} must be one line of text, up to {limit} characters.')
    return value.strip()


def key(value):
    # Matching only; API commodity identifiers are retained separately.
    return ''.join(c for c in str(value).casefold() if c.isalnum())


def settings(query):
    out = {}
    bounds = dict(quantity=(1, 25000), loading_floor=(1, 1000000), unloading_floor=(1, 1000000),
                  owner_floor=(0, 1000000), radius=(1, 2500), max_hop=(1, 2500), hours=(1, 24),
                  arrival=(0, 10000000), breadth=(0, 500), hauler_capacity=(1, 1000), cycle_minutes=(1, 60),
                  haulers=(1, 50), cost_reserve=(0, 10**10), payout_target=(1, 1000000), min_quantity=(1,25000))
    for name, default in DEFAULTS.items():
        value = query.get(name, default)
        if name in bounds:
            out[name] = integer(value, name.replace('_', ' '), *bounds[name])
        elif name in ('skip_common', 'avoid_active', 'share_surplus', 'allow_partial', 'allow_surface_loading'):
            if value not in (True, False, 'true', 'false', '1', '0'):
                raise ValueError(name.replace('_', ' ') + ' must be true or false.')
            out[name] = value in (True, 'true', '1')
        elif name == 'haul_mode':
            if value not in ('both', 'self_load', 'self_unload'):
                raise ValueError('Choose haulers on both legs, load yourself, or unload yourself.')
            out[name] = value
        else:
            if not isinstance(value, str) or len(value) > 1000:
                raise ValueError('Excluded commodities must be comma-separated text up to 1000 characters.')
            out[name] = value
    if out['allow_partial'] and out['min_quantity'] > out['quantity']:
        raise ValueError('Minimum order size cannot exceed the maximum order size.')
    return out


def pricing(buy, sell, quantity, mean, prefs):
    load_paid, unload_paid = paid_leg(prefs,'loading'), paid_leg(prefs,'unloading')
    load_floor = prefs['loading_floor'] if load_paid else 0
    unload_floor = prefs['unloading_floor'] if unload_paid else 0
    target_buy, target_sell = buy + load_floor, sell - unload_floor
    bp = sp = None
    cb, cs = target_buy, target_sell
    owner_min = owner_minimum(prefs, quantity)
    if type(mean) is int and 0 < mean <= 10**9:
        # Unlike nearest-price rounding, these choices never underpay either floor.
        prices = [(p, (mean * p + 50) // 100) for p in range(5, 1001)]
        buys = prices if load_paid else [(None,buy)]
        sells = prices if unload_paid else [(None,sell)]
        b = next(((p, v) for p, v in buys if v >= target_buy), None)
        s = next(((p, v) for p, v in reversed(sells) if v <= target_sell), None)
        if b:
            bp, cb = b
        if s:
            sp, cs = s
        if prefs.get('share_surplus',True):
            # Maximize the weaker hauler payout, then their combined payout,
            # while retaining the owner's minimum and the operation reserve.
            values = [v for _,v in sells]
            best = None
            for percent,value in buys:
                if value < target_buy:
                    continue
                at = bisect_left(values,value+owner_min)
                if at>=len(sells):
                    continue
                sell_percent,sell_value = sells[at]
                if sell_value>target_sell:
                    continue
                loading,unloading = value-buy,sell-sell_value
                payouts = [n for n, paid in ((loading,load_paid),(unloading,unload_paid)) if paid]
                score = (min(payouts),sum(payouts),-abs(loading-unloading),-value)
                if best is None or score>best[0]:
                    best = (score,percent,value,sell_percent,sell_value)
            if best:
                _,bp,cb,sp,cs = best
    owner = cs - cb
    load, unload = cb - buy, sell - cs
    valid = ((bp is not None or not load_paid) and (sp is not None or not unload_paid)
             and owner >= owner_min and load >= load_floor and unload >= unload_floor)
    paid_payouts = [n for n, paid in ((load,load_paid),(unload,unload_paid)) if paid]
    return dict(station_buy=buy, station_sell=sell, mean_price=mean, carrier_buy=cb, carrier_sell=cs,
                buy_percent=bp, sell_percent=sp, loading_per_ton=load, unloading_per_ton=unload,
                owner_per_ton=owner, gross_per_ton=sell-buy, gross_total=(sell-buy)*quantity,
                hauler_total=(load+unload)*quantity, owner_total=owner*quantity,
                cost_reserve=prefs['cost_reserve'], owner_after_reserve=owner*quantity-prefs['cost_reserve'],
                funding=cb*quantity, settings_valid=valid, loading_paid=load_paid, unloading_paid=unload_paid,
                advertised_per_ton=min(paid_payouts), required_spread=load_floor+unload_floor+owner_min,
                meets_target=valid and min(paid_payouts)>=prefs.get('payout_target',20000),
                spread_short=max(0, load_floor+unload_floor+owner_min-(sell-buy)))


def markdown(value):
    value = line(value, 'Advert text')
    if '@' in value or '`' in value:
        raise ValueError('Advert fields cannot contain mentions or backticks.')
    return re.sub(r'([\\*_~|\[\]])', r'\\\1', value)


def compact(number):
    # Three decimal places preserve exact whole-credit/t quantities; never round up.
    return (str(number//1000) if number % 1000 == 0 else f'{number/1000:.3f}'.rstrip('0')) + 'k'


def advertised_profit(profit):
    """Whole thousands for readable adverts, never above the checked payout."""
    profit = integer(profit, 'Hauler profit', 1)
    return profit // 1000 * 1000 if profit >= 1000 else profit


def advert(carrier, callsign, commodity, station, system, phase, profit, quantity):
    if phase not in ('loading','unloading'):
        raise ValueError('Choose a public loading or unloading phase.')
    profit = integer(profit,'Hauler profit',1)
    quantity = integer(quantity,'Advert tonnes',1,25000)
    if not re.fullmatch(r'[A-Z0-9]{3}-[A-Z0-9]{3}', callsign or ''):
        raise ValueError('A valid carrier callsign is needed before making an advert.')
    if profit <= 0 or quantity <= 0:
        raise ValueError('An advert needs a positive hauler profit and remaining order.')
    verb, direction = ('loading', 'from') if phase == 'loading' else ('unloading', 'to')
    return (f'**{markdown(carrier)} ({callsign})** is {verb} **{markdown(commodity)}** {direction} '
            f'**{markdown(station)}** (L pads) in **{markdown(system)}**. '
            f'**{compact(advertised_profit(profit))}**/unit profit, {compact(quantity)} units')
