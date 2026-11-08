"""Bounded cargo allocations: quoted proceeds, never invented acquisition profit."""
import copy
import math
from datetime import datetime, timezone
from elitelab.core.gamedata import norm

ORBITAL = {'Coriolis Starport','Orbis Starport','Ocellus Starport','Dodec Starport','Asteroid base','Outpost'}
SURFACE = {'Planetary Port','Planetary Outpost','Settlement','Surface Settlement','Dockable Planet Station'}


def key(value):
    return ''.join(c for c in norm(value) if c.isalnum()) if isinstance(value,str) else ''


def number(value, minimum=0, maximum=10**12):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def timestamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z','+00:00'))
        return d.timestamp() if d.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def cargo(journal):
    snapshot = journal.get('cargo') or {}
    items, total = snapshot.get('items'), snapshot.get('count')
    if (type(total) is not int or not 0<=total<=1000000 or not isinstance(items,list) or len(items)>256
            or any(not isinstance(i,dict) or type(i.get('count')) is not int or i['count']<0 for i in items)
            or sum(i['count'] for i in items)!=total):
        return None, []
    grouped, excluded = {}, []
    for item in items:
        ident = key(item.get('key') or item.get('name'))
        if not ident or not item['count']:
            continue
        stolen = item.get('stolen',0)
        if type(stolen) is not int or not 0<=stolen<=item['count'] or item.get('mission_id'):
            excluded.append(dict(key=ident,name=item.get('name') or ident,quantity=item['count'],reason='Mission cargo or unknown ownership'))
            continue
        if stolen:
            excluded.append(dict(key=ident,name=item.get('name') or ident,quantity=stolen,reason='Stolen cargo requires a black market'))
        quantity = item['count']-stolen
        if quantity:
            row = grouped.setdefault(ident,dict(key=ident,name=item.get('name') or ident,quantity=0))
            row['quantity'] += quantity
    return list(grouped.values()), excluded


def market(record, prefs, origin, clock, goods):
    if not isinstance(record,dict):
        return None
    allowed = ORBITAL | (SURFACE if prefs['surface'] else set())
    if (record.get('type') not in allowed or not record.get('has_market') or record.get('carrier_name')
            or (record.get('is_planetary') and not prefs['surface']) or 'stronghold carrier' in str(record.get('name','')).lower()):
        return None
    if type(record.get('market_id')) is not int or record['market_id']<=0:
        return None
    if any(not isinstance(record.get(f),str) or not 0<len(record[f])<=200 for f in ('name','system_name')):
        return None
    observed = timestamp(record.get('market_updated_at'))
    pos = [record.get('system_'+a) for a in 'xyz']
    if observed is None or not 0<=clock-observed<=prefs['hours']*3600 or not all(number(n,-100000,100000) for n in pos):
        return None
    distance = math.dist(origin,pos)
    if distance>prefs['radius']:
        return None
    pad = 'L' if record.get('has_large_pad') is True else 'M' if number(record.get('medium_pads'),1) else 'S' if number(record.get('small_pads'),1) else None
    if not pad or 'SML'.index(pad)<'SML'.index(prefs['pad']):
        return None
    arrival = record.get('distance_to_arrival')
    arrival = arrival if number(arrival) else None
    if prefs['arrival'] and (arrival is None or arrival>prefs['arrival']):
        return None
    offers = {}
    if not isinstance(record.get('market'),list):
        return None
    for item in record['market'][:1024]:
        if not isinstance(item,dict) or item.get('is_prohibited'):
            continue
        ident = key(item.get('commodity'))
        price, demand = item.get('sell_price'),item.get('demand')
        # A zero without explicit consumer evidence is not guaranteed unlimited demand.
        unlimited = demand==0 and type(demand) is int and item.get('consumer') is True
        if ident not in goods or not number(price,1,10**9) or type(demand) is not int or demand<0 or (demand==0 and not unlimited):
            continue
        quote = dict(price=price,demand=demand,unlimited=unlimited,
                     mean_price=item.get('mean_price') if number(item.get('mean_price'),1,10**9) else None)
        # Duplicate/conflicting commodity records are excluded, not added together.
        if ident in offers and offers[ident] != quote:
            offers[ident] = None
        elif ident not in offers:
            offers[ident] = quote
    offers = {k:v for k,v in offers.items() if v}
    if not offers:
        return None
    return dict(market_id=record['market_id'],station=record['name'],system=record['system_name'],pad=pad,
                pos=pos,distance=round(distance,2),arrival_ls=arrival,observed_at=record['market_updated_at'],offers=offers,
                source='Spansh / EDDN',source_url='https://spansh.co.uk/station/'+str(record['market_id']))


def allocate(goods, markets, origin, strategy):
    remaining = {r['key']:r['quantity'] for r in goods}
    names = {r['key']:r['name'] for r in goods}
    stops = {}

    def take(m, ident):
        quote = m['offers'][ident]
        quantity = min(remaining[ident], remaining[ident] if quote['unlimited'] else quote['demand'])
        if quantity<=0:
            return
        stop = stops.setdefault(m['market_id'],{k:copy.deepcopy(v) for k,v in m.items() if k!='offers'})
        stop.setdefault('sales',[]).append(dict(key=ident,name=names[ident],quantity=quantity,price=quote['price'],
            proceeds=quantity*quote['price'],demand=quote['demand'],demand_unlimited=quote['unlimited']))
        remaining[ident] -= quantity

    if strategy=='highest':
        for g in goods:
            for m in sorted((m for m in markets if g['key'] in m['offers']),key=lambda m:(-m['offers'][g['key']]['price'],m['distance'],m['market_id'])):
                if len(stops)>=20 and m['market_id'] not in stops:
                    continue
                take(m,g['key'])
                if not remaining[g['key']]:
                    break
    else:
        candidates = list(markets)
        position = origin
        while candidates and any(remaining.values()) and len(stops)<(1 if strategy=='one_stop' else 20):
            def value(m):
                quantities = [(min(remaining[k],remaining[k] if q['unlimited'] else q['demand']),q['price']) for k,q in m['offers'].items()]
                units = sum(q for q,_ in quantities)
                proceeds = sum(q*p for q,p in quantities)
                return (units,proceeds,-m['distance']) if strategy=='one_stop' else (proceeds/(10+math.dist(position,m['pos'])),units,-m['market_id'])
            chosen = max(candidates,key=value)
            candidates.remove(chosen)
            for ident in chosen['offers']:
                take(chosen,ident)
            position = chosen['pos']
    # Price allocation and travel order are separate: nearest next stop is a
    # practical ordering, not a claim of a shortest travelling-salesman route.
    ordered, position, distance = [],origin,0
    pending = list(stops.values())
    while pending:
        chosen = min(pending,key=lambda m:(math.dist(position,m['pos']),m['market_id']))
        leg = math.dist(position,chosen['pos']);distance+=leg
        chosen['leg_distance']=round(leg,2)
        ordered.append(chosen);pending.remove(chosen);position=chosen['pos']
    return dict(strategy=strategy,stops=ordered,distance=round(distance,2),
                estimated_proceeds=sum(s['proceeds'] for m in ordered for s in m['sales']),net_profit=None,
                sold_quantity=sum(g['quantity']-remaining[g['key']] for g in goods),
                unsold=[dict(key=k,name=names[k],quantity=v) for k,v in remaining.items() if v],
                note='Reported proceeds before travel costs. Acquisition cost is unknown. Up to 20 stops; nearest-next-stop ordering is a heuristic. Verify quotes and demand in game.')
