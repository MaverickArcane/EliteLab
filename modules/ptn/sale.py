"""Direct carrier sale drafts, independent of the scouted hauling operation."""
import re
import math
from urllib.parse import quote, urlencode

from elitelab.core.gamedata import norm
from modules.ptn.planning import DEFAULTS, integer, key, line, markdown, now

MARKETS = 'https://api.ardent-insight.com/v2'


def suggestions(desk, query):
    """Bounded buyer reports for cargo already aboard, with an explicit hauler margin."""
    name = line(query.get('commodity'), 'Commodity', 80)
    quantity = integer(query.get('quantity'), 'Sale tonnes', 1, 25000)
    payout = integer(query.get('payout', 20000), 'Desired hauler profit in Cr/t', 1, 1000000)
    radius = integer(query.get('radius', 500), 'Search radius in Ly', 1, 1500)
    system = line(query.get('system') or desk.context().get('system'), 'Search system')
    origin = desk.origin({'system': system})
    # Resolve against actual catalog identifiers; display names are not API keys.
    catalog = desk.core.services.fetch_json(MARKETS+'/commodities', ttl=600)
    if not isinstance(catalog, list):
        raise ValueError('Commodity catalog unavailable. Enter your own sale price or retry.')
    commodity = next((r['commodityName'] for r in catalog[:2000] if isinstance(r, dict)
                      and isinstance(r.get('commodityName'), str) and r['commodityName'].isascii()
                      and r['commodityName'].isalnum() and key(r['commodityName']) == key(norm(name))
                      and not r.get('rare')), None)
    if not commodity:
        raise ValueError('No matching commodity identifier in market reports. Enter your own sale price.')
    warnings, current = [], []
    try:
        params = urlencode(dict(minVolume=quantity, maxDaysAgo=2, fleetCarriers=0))
        raw = desk.core.services.fetch_json(MARKETS+'/system/name/'+quote(system, safe='')+
                                           '/commodities/imports?'+params, ttl=300)
        if not isinstance(raw, list):
            raise ValueError('Invalid market report')
        current = raw[:10000]
        if len(raw) >= 10000:
            warnings.append('Current-system market coverage is capped at 10,000 reports.')
    except Exception:
        warnings.append('Current-system markets unavailable; nearby coverage may still be useful.')
    prefs = {**DEFAULTS, 'quantity':quantity, 'allow_partial':False, 'radius':radius, 'max_hop':0, 'hours':24}
    report = desk.quotes(commodity, 'sell', prefs, origin, system, current)
    if report['failures']:
        warnings.append('Some market reports failed. Suggestions cover only the available reports.')
    if report['capped']:
        warnings.append('Market report limits were reached. Other buyers may be missing.')
    rows = []
    for buyer in report['rows']:
        ceiling = buyer['price'] - payout
        if ceiling <= 0:
            continue
        mean = buyer['mean_price']
        percent, suggested = None, ceiling
        if mean:
            percent, suggested = next(((p, (mean*p+50)//100) for p in range(1000, 4, -1)
                                       if 0 < (mean*p+50)//100 <= ceiling), (None, None))
        if suggested is None:
            continue
        rows.append({**buyer, 'suggested_price':suggested, 'percent':percent,
                     'hauler_profit':buyer['price']-suggested,
                     'carrier_proceeds':quantity*suggested,
                     'jumps':math.ceil(math.dist(origin,buyer['pos'])/500)})
    rows.sort(key=lambda row:(-row['suggested_price'],row['distance']))
    return dict(commodity=commodity, quantity=quantity, payout=payout, system=system, radius=radius,
                checked_at=now(), rows=rows[:10], warnings=warnings,
                basis='Reported large-pad orbital buyers within 24 hours with demand covering the load. Suggested carrier price leaves the requested hauler profit; whole-percent carrier settings are used when meanPrice is known. Move the carrier near the buyer for unloading. These are estimates, not scouted or guaranteed prices.')


def cargo(context):
    """Physical stock evidence only. Buy orders never become available cargo."""
    rows = []
    for commodity, record in context['inventory'].items():
        stock = record.get('stock')
        if type(stock) is not int or stock < 0:
            stock = None
        order = context['orders'].get(commodity) or {}
        price = order.get('price')
        sell_price = (price if order.get('side') == 'sell' and order.get('active') is True
                      and type(price) is int and price > 0 else None)
        name = record.get('name') or commodity
        rows.append(dict(commodity=commodity, name=name.capitalize() if name == name.lower() else name,
                         stock=stock, observed_at=record.get('updated_at'), source=record.get('source'),
                         sell_price=sell_price, order_observed_at=order.get('updated_at') if sell_price else None))
    return sorted(rows, key=lambda row: row['name'].casefold())


def prepare(context, query):
    """Render user-entered sale terms without changing orders, inventory or PTN plans."""
    if not context.get('commander') or not context.get('carrier'):
        raise ValueError('Identify your commander and owned carrier first.')
    if query.get('commander') != context['commander'] or query.get('callsign') != context['callsign']:
        raise ValueError('The commander or carrier changed. Review the sale for the current carrier.')
    callsign = context['callsign']
    if not re.fullmatch(r'[A-Z0-9]{3}-[A-Z0-9]{3}', callsign or ''):
        raise ValueError('A valid carrier callsign is needed before making an advert.')
    system = line(query.get('system'), 'Pickup system')
    commodity = line(query.get('commodity'), 'Commodity', 80)
    row = next((row for row in cargo(context)
                if key(norm(commodity)) in (key(row['commodity']), key(row['name']))), None)
    name = row['name'] if row else commodity
    quantity = integer(query.get('quantity'), 'Sale tonnes', 1, 25000)
    price = integer(query.get('price'), 'Selling price in Cr/t', 1)
    text = (f'**{markdown(context["carrier"])} ({callsign})** is selling **{markdown(name)}** '
            f'in **{markdown(system)}**.\n'
            f'**{quantity:,} t** available at **{price:,} Cr/t**.')
    kind = query.get('kind', 'direct_sale')
    if kind not in ('direct_sale', 'unloading'):
        raise ValueError('Choose direct_sale or unloading.')
    buyer = None
    if kind == 'unloading':
        station = line(query.get('station'), 'Buyer station')
        buyer_price = integer(query.get('buyer_price'), 'Buyer price in Cr/t', 1)
        if buyer_price <= price:
            raise ValueError('The buyer price must exceed your carrier price to offer hauler profit.')
        buyer = dict(station=station, system=system, price=buyer_price, profit=buyer_price-price)
        text = (f'**{markdown(context["carrier"])} ({callsign})** is unloading **{markdown(name)}** '
                f'to **{markdown(station)}** in **{markdown(system)}**.\n'
                f'**{quantity:,} t** available at **{price:,} Cr/t** on the carrier.\n'
                f'Buyer quote: **{buyer_price:,} Cr/t**; estimated hauler profit: **{buyer_price-price:,} Cr/t**.')
    notes = []
    if not row or row['stock'] is None:
        notes.append('Carrier stock is unknown; the quantity is entered by you.')
    elif quantity > row['stock']:
        notes.append('Sale quantity exceeds the last recorded stock. Check the current hold before posting.')
    if system.casefold() != (context.get('system') or '').casefold():
        notes.append('Pickup system differs from the last reported carrier location.')
    return dict(kind=kind, buyer=buyer, copy_text=text, commodity=row['commodity'] if row else norm(commodity),
                name=name, quantity=quantity, price=price, total_proceeds=quantity*price,
                carrier=context['carrier'], callsign=callsign, system=system, stock_evidence=row,
                notes=notes, instructions='Sale draft using your entered tonnes and prices. Check stock, carrier location, sell order, docking access and any buyer quote before posting. Route advert provides the separately checked affiliate workflow. This does not place an order or post a message.')
