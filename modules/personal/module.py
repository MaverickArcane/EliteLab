"""Ship trades and exact station-to-station loops from Spansh market snapshots."""
from datetime import datetime, timezone
import math

from elitelab.core.gamedata import is_rare

STATIONS = 'https://www.spansh.co.uk/api/stations/search'
ORBITAL = ['Coriolis Starport', 'Orbis Starport', 'Ocellus Starport', 'Dodec Starport', 'Asteroid base', 'Outpost']
SURFACE = ['Planetary Port', 'Planetary Outpost', 'Settlement', 'Surface Settlement', 'Dockable Planet Station']


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def numeric(q, key, default, maximum, integer=False):
    try:
        value = q.get(key, default)
        n = float(value)
        if isinstance(value, bool) or not math.isfinite(n) or not 0 < n <= maximum or (integer and n != int(n)):
            raise ValueError()
        return int(n) if integer else n
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f'{key} must be a positive number up to {maximum}.') from None


def system_name(value):
    if not isinstance(value, str) or len(value) > 160:
        raise ValueError('System and station names must be text up to 160 characters.')
    return value.strip()


def commodity_key(name):
    # UI keys only, never journal identifiers.
    return ''.join(c for c in name.casefold() if c.isalnum())


class Personal:
    def __init__(self, core):
        self.core = core

    def stations(self, settings, reference, radius, limit, now):
        # Bucket freshness bounds so repeat searches share the five-minute cache.
        lower = datetime.fromtimestamp(math.floor(now / 300) * 300 - settings['hours'] * 3600, timezone.utc).isoformat()
        upper = datetime.fromtimestamp(math.floor(now / 300) * 300 + 300, timezone.utc).isoformat()
        # Spansh treats max=0 as unbounded. A tiny radius plus exact local name
        # matching restricts origin/destination searches to their actual system.
        filters = {'distance': {'min': 0, 'max': radius or 0.001}, 'has_market': {'value': True},
                   'type': {'value': ORBITAL + (SURFACE if settings['surface'] else [])},
                   'market_updated_at': {'comparison': '<=>', 'value': [lower, upper]}}
        if settings['pad'] == 'L':
            filters['has_large_pad'] = {'value': True}
        if settings['arrival']:
            filters['distance_to_arrival'] = {'min': 0, 'max': settings['arrival']}
        records, total, warnings = [], 0, []
        for page in range(math.ceil(limit / 100)):
            body = {'filters': filters, 'sort': [{'distance': {'direction': 'asc'}}],
                    'size': min(100, limit), 'page': page, 'reference_system': reference}
            try:
                result = self.core.services.fetch_json(STATIONS, body, ttl=300)
                if not isinstance(result, dict) or result.get('error') or not isinstance(result.get('results'), list):
                    raise ValueError('Unexpected Spansh station response.')
            except Exception as exc:
                if not records:
                    raise ValueError('Spansh markets unavailable. Check the system name and retry.') from exc
                warnings.append('Spansh could not finish the station search; showing partial results.')
                break
            batch = result['results']
            count = result.get('count')
            total = max(total, count if type(count) is int else len(records) + len(batch))
            records.extend(batch)
            if len(batch) < body['size'] or len(records) >= total:
                break
        records = records[:limit]
        if total > len(records):
            warnings.append(f'Checked {len(records)} of {total} reported stations near {reference}. Increase search breadth or specify a destination to check more.')
        return records, total, warnings

    def market(self, r, s, now):
        if not isinstance(r, dict) or r.get('type') not in ORBITAL + (SURFACE if s['surface'] else []):
            return None
        if not r.get('has_market') or r.get('carrier_name') or 'stronghold carrier' in str(r.get('name', '')).casefold():
            return None
        if (type(r.get('market_id')) is not int or r['market_id'] <= 0
                or not isinstance(r.get('name'), str) or not r['name']
                or not isinstance(r.get('system_name'), str) or not r['system_name']):
            return None
        if not s['surface'] and r.get('is_planetary'):
            return None
        pad = 'L' if r.get('has_large_pad') is True else 'M' if positive(r.get('medium_pads')) else 'S' if positive(r.get('small_pads')) else None
        if pad is None or {'S': 1, 'M': 2, 'L': 3}[pad] < {'S': 1, 'M': 2, 'L': 3}[s['pad']]:
            return None
        arrival = r.get('distance_to_arrival')
        if s['arrival'] and (type(arrival) not in (int, float) or not math.isfinite(arrival) or not 0 <= arrival <= s['arrival']):
            return None
        if type(arrival) not in (int, float) or not math.isfinite(arrival) or arrival < 0:
            arrival = None
        try:
            observed = datetime.fromisoformat(r['market_updated_at'].replace('Z', '+00:00'))
            if observed.tzinfo is None or not 0 <= now - observed.timestamp() <= s['hours'] * 3600:
                return None
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
        pos = [r.get('system_' + a) for a in 'xyz']
        if not all(type(n) in (int, float) and math.isfinite(n) for n in pos) or not isinstance(r.get('market'), list):
            return None
        buys, sells = {}, {}
        for item in r['market']:
            if not isinstance(item, dict):
                continue
            name = item.get('commodity')
            if not isinstance(name, str) or not name or item.get('is_rare') or is_rare(name) or item.get('is_prohibited'):
                continue
            for target, price, volume in ((buys, item.get('buy_price'), item.get('supply')), (sells, item.get('sell_price'), item.get('demand'))):
                if positive(price) and positive(volume) and volume >= s['quantity']:
                    target[name] = {'price': price, 'volume': volume}
        return {'market_id': r['market_id'], 'station': r['name'], 'system': r['system_name'], 'pad': pad,
                'arrival_ls': arrival, 'observed_at': observed.isoformat(), 'pos': pos, 'buys': buys, 'sells': sells}

    @staticmethod
    def legs(source, target, quantity, selected=''):
        legs = []
        for name, buy in source['buys'].items():
            if selected and commodity_key(name) != selected:
                continue
            sell = target['sells'].get(name)
            if not sell or sell['price'] <= buy['price']:
                continue
            def stop(market, quote):
                return {k: v for k, v in {**market, **quote}.items() if k not in ('pos', 'buys', 'sells')}
            spread = sell['price'] - buy['price']
            legs.append({'commodity': name, 'buy': stop(source, buy), 'sell': stop(target, sell),
                         'quantity': quantity, 'per_ton': spread, 'profit': spread * quantity, 'cost': buy['price'] * quantity})
        return sorted(legs, key=lambda r: (-r['profit'], r['cost'], r['commodity']))

    def search(self, q):
        if self.core.config.OFFLINE:
            raise ValueError('Spansh route search is unavailable in offline mode.')
        j = self.core.store.get('journal')
        origin = system_name(q.get('origin') or j.get('system') or '')
        if not origin:
            raise ValueError('Enter a starting system or wait for your journal location.')
        destination, station = system_name(q.get('destination', '')), system_name(q.get('station', ''))
        if q.get('quantity') in (None, '') and not positive(j.get('cargo_capacity')):
            raise ValueError('Ship cargo capacity is unknown. Enter a load size.')
        quantity = numeric(q, 'quantity', j.get('cargo_capacity'), 1000000, True)
        hours, breadth = numeric(q, 'hours', 24, 72, True), numeric(q, 'breadth', 100, 300, True)
        pad, route_type = q.get('pad', 'L'), q.get('route_type', 'round_trip')
        if pad not in ('S', 'M', 'L') or route_type not in ('one_way', 'round_trip'):
            raise ValueError('Choose a supported landing pad and route type.')
        surface = str(q.get('surface', '0'))
        if surface not in ('0', '1'):
            raise ValueError('Choose whether to include surface stations.')
        arrival = q.get('arrival', 10000)
        arrival = 0 if arrival in (0, '0') and not isinstance(arrival, bool) else numeric(q, 'arrival', 10000, 1000000, True)
        laden = j.get('jump_range_laden')
        laden = laden if positive(laden) else None
        mode = q.get('distance_mode', 'ly')
        if mode == 'jumps':
            jumps = numeric(q, 'jumps', 2, 20, True)
            if laden is None:
                raise ValueError('Fully laden ship range is unknown. Use a light-year distance until ship data is available.')
            distance = jumps * laden
        elif mode == 'ly':
            distance = numeric(q, 'distance', 80, 500)
        else:
            raise ValueError('Choose light-years or estimated jumps.')
        if distance > 500:
            raise ValueError('Search supports up to 500 Ly. Reduce the number of jumps.')
        selected = q.get('commodity', '')
        if not isinstance(selected, str) or len(selected) > 100 or (selected and not selected.isalnum()):
            raise ValueError('Choose a commodity from the market list.')
        settings = dict(origin=origin, destination=destination, station=station, quantity=quantity, distance=distance,
                        hours=hours, pad=pad, surface=surface == '1', arrival=arrival, route_type=route_type, breadth=breadth)
        now = datetime.now(timezone.utc).timestamp()
        local, _, warnings = self.stations(settings, origin, 0, 100, now)
        origins = [m for r in local if (m := self.market(r, settings, now))
                   and m['system'].casefold() == origin.casefold() and (not station or m['station'].casefold() == station.casefold())]
        catalog = {commodity_key(name): name for m in origins for name in m['buys']}
        rows, checked, available, too_far = [], 0, 0, []
        if origins and selected and selected.casefold() not in catalog:
            warnings.append(f'{selected} is not sold at the starting market for this load. Choose a commodity from the list or search all goods.')
        if origins:
            nearby, available, notes = self.stations(settings, destination or origin, 0 if destination else distance, breadth, now)
            warnings.extend(notes)
            markets = {m['market_id']: m for r in nearby if (m := self.market(r, settings, now))
                       and (not destination or m['system'].casefold() == destination.casefold())}
            checked = len(nearby)
            for start in origins:
                for end in markets.values():
                    separation = math.dist(start['pos'], end['pos'])
                    if start['market_id'] == end['market_id']:
                        continue
                    if separation > distance:
                        too_far.append(separation)
                        continue
                    outbound = self.legs(start, end, quantity, selected.casefold())
                    returning = self.legs(end, start, quantity) if route_type == 'round_trip' else []
                    if route_type == 'round_trip' and not returning:
                        continue
                    for leg in outbound:
                        legs = [leg] + returning[:1]
                        profit, cost = sum(l['profit'] for l in legs), sum(l['cost'] for l in legs)
                        required = max(leg['cost'], returning[0]['cost'] - leg['profit']) if returning else leg['cost']
                        rows.append({**leg, 'legs': legs, 'route_type': route_type, 'profit': profit, 'cost': cost,
                                     'per_ton': profit / quantity, 'required_credits': required, 'return_on_cost': 100 * profit / cost,
                                     'distance': round(separation, 2), 'total_distance': round(separation * len(legs), 2),
                                     'estimated_jumps': (max(1, math.ceil(separation / laden)) if separation else 0) if laden else None})
            if destination and not rows and too_far:
                warnings.append(f'{destination} is {min(too_far):.0f} Ly away, beyond the {distance:g} Ly per-leg limit. Increase the distance or switch to estimated jumps.')
        else:
            warnings.append('No fresh eligible starting market found. Check the station name, pad, report age and surface-station filters.')
        rows.sort(key=lambda r: (-r['profit'], r['distance'], r['required_credits']))
        return {'rows': rows[:30], 'commodities': [{'key': key, 'name': name} for key, name in sorted(catalog.items())],
                'screened': checked, 'available': available, 'settings': settings, 'laden_range': laden,
                'ship_capacity': j.get('cargo_capacity'), 'credits': j.get('credits'), 'source': 'Spansh / community markets',
                'warnings': warnings, 'queried_at': datetime.now(timezone.utc).isoformat(),
                'note': 'Nearest eligible stations, cached five minutes; not exhaustive. Fleet carriers excluded. Each leg requires reported supply and demand for the full load. Profit excludes fuel, fees and bonuses.'}


def setup(core, module):
    search = Personal(core)
    core.http.route('/api/personal/routes', search.search, tool='find_personal_trade_routes', module=module.name,
        description='Find ship-sized Spansh trades ranked by profit. Round trips return to the exact starting station with an independent return commodity. Origin defaults to current system; station optionally restricts the starting station. Destination is an optional system. Distance is per leg, at most 500 Ly; jumps use fully laden range as a straight-line estimate. Checks up to breadth nearest eligible stations (default 100, max 300), plus up to 100 origin markets; not exhaustive. Requires full-load positive supply and demand; excludes carriers. Five-minute cache. No game actions.',
        params={'origin': {'type': 'string'}, 'station': {'type': 'string', 'default': ''},
                'destination': {'type': 'string', 'default': ''},
                'route_type': {'type': 'string', 'enum': ['one_way', 'round_trip'], 'default': 'round_trip'},
                'quantity': {'type': 'integer', 'description': 'Tonnes each leg; defaults to ship capacity.'},
                'distance_mode': {'type': 'string', 'enum': ['ly', 'jumps'], 'default': 'ly'},
                'distance': {'type': 'number', 'default': 80}, 'jumps': {'type': 'integer', 'default': 2},
                'pad': {'type': 'string', 'enum': ['S', 'M', 'L'], 'default': 'L'},
                'hours': {'type': 'integer', 'default': 24}, 'breadth': {'type': 'integer', 'default': 100},
                'arrival': {'type': 'integer', 'default': 10000, 'description': 'Maximum approach in Ls; 0 means any.'},
                'surface': {'type': 'string', 'enum': ['0', '1'], 'default': '0'},
                'commodity': {'type': 'string', 'default': '', 'description': 'Outbound key from results; return goods are independent.'}})
