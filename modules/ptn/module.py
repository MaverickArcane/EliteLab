"""A separate PTN planning desk. Never places game orders or posts to Discord."""
import copy
import math
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from datetime import datetime, timezone
from statistics import median
from urllib.parse import quote, urlencode

from elitelab.core.gamedata import is_rare, norm
from modules.ptn.planning import (COMMON, DEFAULTS, advert, finite, integer, key, line,
                                  now, paid_leg, owner_minimum, pricing, settings, stamp, station_kind, unlimited_demand)

BOARD = 'https://pilotstradenetwork.com/wp-json/ptn/v1/missions'
MARKETS = 'https://api.ardent-insight.com/v2'
FILE = 'ptn.json'
PHASES = ('scouting', 'loading', 'transit', 'unloading', 'complete', 'cancelled')
CHECKS = ('near_station', 'docking_open', 'funds_checked', 'competition_checked')
SCAN_SECONDS = 300
STATIONS_PER_KIND = 50


class PTN:
    def __init__(self, core):
        self.core = core
        self.lock = threading.RLock()
        self.data = core.read_data(FILE, default={}) or {}
        self.data.setdefault('revision', 0)
        self.data.setdefault('plan', None)
        self.data.setdefault('history', [])
        self.results, self.board, self.searching = None, None, False
        self.progress = None
        self.search_job = None
        self.search_done = threading.Event()
        self.search_done.set()
        self.latest_market, self.docked_at = {}, 0
        core.bus.on('journal.file.Market', self.market_event)
        core.bus.on('journal.Docked', self.dock_event)
        for event in ('state.journal.carrier','state.journal.location','state.journal.market','state.trade.orders','state.trade.inventory'):
            core.bus.on(event,lambda n,v:self.publish())
        self.publish()

    def market_event(self, name, event):
        with self.lock:
            if stamp(event.get('timestamp')) >= stamp(self.latest_market.get('timestamp')):
                self.latest_market = event
                self.invalidate_observation(event)

    def invalidate_observation(self, event):
        """A new local contradiction blocks adverts even before Capture is clicked."""
        plan = self.data.get('plan')
        if not plan or plan['stage'] in ('complete', 'cancelled'):
            return
        j = self.core.store.get('journal') or {}
        age = datetime.now(timezone.utc).timestamp() - stamp(event.get('timestamp'))
        if not j.get('docked') or not -300 <= age <= 900 or stamp(event.get('timestamp')) < self.docked_at:
            return
        for side in ('buy', 'sell'):
            target = plan['route'][side]
            if (event.get('MarketID') != target['market_id'] or j.get('system') != target['system']
                    or j.get('station') != target['station']
                    or station_kind(j.get('station_type')) != station_kind(target.get('station_type'))):
                continue
            raw = next((r for r in event.get('Items', []) if isinstance(r, dict)
                        and key(norm(r.get('Name'))) == key(plan['commodity'])), None)
            reason = None
            if raw is None:
                reason = 'The selected commodity is missing from the current market snapshot.'
            elif raw.get('Producer' if side == 'buy' else 'Consumer') is False:
                reason = 'This market does not offer this side of the trade. Recheck the commodity.'
            else:
                try:
                    integer(raw.get('BuyPrice' if side == 'buy' else 'SellPrice'), 'Station price', 1)
                    integer(raw.get('Stock' if side == 'buy' else 'Demand'), 'Station supply/demand', 0, 10**12)
                except ValueError as error:
                    reason = str(error)
            if reason:
                try:
                    self.guard({'revision': self.data['revision']})
                    self.reject_capture(side, dict(market_id=event['MarketID'], timestamp=event['timestamp']), reason)
                except ValueError:
                    pass
                except OSError:
                    self.core.log.exception('PTN market invalidation could not be saved; adverts remain blocked in memory')

    def dock_event(self, name, event):
        with self.lock:
            self.docked_at = stamp(event.get('timestamp'))

    def context(self):
        j = self.core.store.get('journal') or {}
        c = j.get('carrier') or {}
        t = self.core.store.get('trade') or {}
        return dict(carrier=c.get('name'), callsign=c.get('callsign'), carrier_id=t.get('carrier_id'),
                    system=c.get('system'), free_space=c.get('free_space'), reserved_space=c.get('reserved_space'),
                    balance=c.get('balance'), stats_at=c.get('stats_time'), orders=t.get('orders') or {},
                    inventory=t.get('inventory') or {}, commander=j.get('cmdr'))

    def guard(self, q, switching=False):
        if self.core.store.get('party', 'mode') == 'member':
            raise ValueError('Only the local carrier owner can change this PTN plan.')
        if integer(q.get('revision'), 'Revision') != self.data['revision']:
            raise ValueError('This plan changed. Refresh before saving.')
        p, c = self.data.get('plan'), self.context()
        if p and not switching and (p.get('callsign') != c.get('callsign') or p.get('commander') != c.get('commander')):
            raise ValueError('The commander or carrier changed. Start a new plan for the current owner.')

    def commit(self, data):
        data['revision'] = self.data['revision'] + 1
        self.core.write_data(data, FILE)
        self.data = data
        self.publish()
        return self.view()

    def publish(self):
        self.core.store.update('ptn', self.view())

    def view(self):
        with self.lock:
            data = copy.deepcopy(self.data)
            data.update(context=self.context(), result=copy.deepcopy(self.results), board=copy.deepcopy(self.board),
                        defaults=copy.deepcopy(DEFAULTS), common=list(COMMON), searching=self.searching,
                        progress=copy.deepcopy(self.progress), search_job=copy.deepcopy(self.search_job))
            if data['board'] and data['board']['available'] and datetime.now(timezone.utc).timestamp()-stamp(data['board']['updated_at'])>900:
                data['board'].update(available=False,benchmarks={},missions=[],error='Public board snapshot expired. Refresh to compare payouts.')
            if data['plan']:
                data['operation'] = self.operation(data['plan'])
            else:
                data['operation'] = None
            return data

    def refresh_board(self, q=None):
        try:
            raw = self.core.services.fetch_json(BOARD, ttl=120)
            if not isinstance(raw, dict) or not isinstance(raw.get('missions'), list):
                raise ValueError('Unexpected public board response.')
            clock, updated = datetime.now(timezone.utc).timestamp(), stamp(raw.get('last_updated'))
            if not -300 <= clock-updated <= 900:
                raise ValueError('The public board has not updated within 15 minutes.')
            missions = []
            for r in raw['missions'][:500]:
                if not isinstance(r, dict) or r.get('mission_type') not in ('load', 'unload'):
                    continue
                try:
                    profit = float(r.get('profit')) * 1000
                    if not finite(profit) or not 0 < profit <= 10000000:
                        continue
                    missions.append(dict(phase='loading' if r['mission_type']=='load' else 'unloading',
                        commodity=line(r.get('commodity'), 'Commodity'), system=line(r.get('system'), 'System'),
                        station=line(r.get('station'), 'Station'), carrier=line(r.get('carrier_name'), 'Carrier'),
                        callsign=line(r.get('carrier_identifier'), 'Callsign'), profit=int(profit),
                        quantity_text=str(r.get('demand', ''))[:30]))
                except (ValueError, TypeError):
                    continue
            benchmarks = {phase: int(median([r['profit'] for r in missions if r['phase']==phase]))
                          if any(r['phase']==phase for r in missions) else None for phase in ('loading', 'unloading')}
            board = dict(available=True, checked_at=now(), updated_at=raw['last_updated'], missions=missions,
                         benchmarks=benchmarks, source=BOARD,
                         scope='Public official PTN missions only. Affiliate adverts and unadvertised carriers are not included.')
        except Exception:
            board = dict(available=False, checked_at=now(), missions=[], benchmarks={}, source=BOARD,
                         error='Could not read a fresh public board. Retry later.',
                         scope='Competition and payout comparisons are unavailable. Nothing is assumed empty.')
        with self.lock:
            self.board = board
            self.publish()
        return board

    def origin(self, context):
        j = self.core.store.get('journal') or {}
        name = context.get('system')
        if not name:
            raise ValueError('Carrier location is unknown. Open Carrier Management in game first.')
        if j.get('system') == name:
            pos = j.get('star_pos')
        else:
            coords = self.core.services.edsm_coords([name]).get(name) or {}
            pos = [coords.get(a) for a in 'xyz']
        if not isinstance(pos, (list, tuple)) or len(pos)!=3 or not all(finite(n) for n in pos):
            raise ValueError('Carrier coordinates are unknown. Wait for a location report and retry.')
        return pos

    def quotes(self, commodity, side, prefs, origin, system, current=()):
        minimum = min(prefs['min_quantity'],prefs['quantity']) if prefs['allow_partial'] else prefs['quantity']
        # The provider silently clamps nearby requests to 500 Ly. Combine them
        # with global price leaders instead of pretending maxDistance=1500 works.
        # Buyers may be beyond the start radius: the final leg is checked per pair.
        radius = prefs['radius'] if side=='buy' else prefs['radius']+prefs['max_hop']
        # Provider filters use whole UTC dates with a strict > comparison.
        # Fetch the preceding date too, then enforce exact hours below.
        query = dict(minVolume=minimum,maxDaysAgo=math.ceil(prefs['hours']/24)+1,fleetCarriers=0)
        suffix = '/exports?' if side=='buy' else '/imports?'
        urls = [(MARKETS+'/system/name/'+quote(system,safe='')+'/commodity/name/'+quote(commodity,safe='')+
                 '/nearby'+suffix+urlencode({**query,'maxDistance':min(radius,500)}),1000)]
        if radius>500:
            urls.append((MARKETS+'/commodity/name/'+quote(commodity,safe='')+suffix+urlencode(query),100))
        raw, failures, capped, successful = list(current), 0, 0, 0
        for url,limit in urls:
            try:
                report = self.core.services.fetch_json(url,ttl=300)
                if not isinstance(report,list):
                    raise ValueError('Unexpected commodity report response.')
                raw.extend(report[:limit])
                capped += len(report)>=limit
                successful += 1
            except Exception:
                failures += 1
        # Resolve duplicate reports before filtering so a newer exhausted or
        # invalid quote cannot resurrect an older, favorable price.
        latest = {}
        for r in raw:
            if (not isinstance(r,dict) or key(r.get('commodityName'))!=key(commodity)
                    or type(r.get('marketId')) is not int or not 0<r['marketId']<=2**63):
                continue
            previous = latest.get(r['marketId'])
            if not previous or stamp(r.get('updatedAt'))>=stamp(previous.get('updatedAt')):
                latest[r['marketId']] = r
        clock, out = datetime.now(timezone.utc).timestamp(), []
        for r in latest.values():
            if not isinstance(r, dict) or r.get('maxLandingPadSize')!=3:
                continue
            kind = station_kind(r.get('stationType'), r.get('isPlanetary'))
            if not kind or (kind=='surface' and side!='buy') or r.get('isProhibited') or r.get('isRare'):
                continue
            if key(r.get('commodityName')) != key(commodity):
                continue
            age = clock-stamp(r.get('updatedAt'))
            price = r.get('buyPrice' if side=='buy' else 'sellPrice')
            volume = r.get('stock' if side=='buy' else 'demand')
            # Ardent imports explicitly define a reported zero as unlimited demand.
            # Keep the reported value and its meaning separate; never synthesize stock.
            unlimited = side=='sell' and type(volume) is int and volume==0
            arrival, pos = r.get('distanceToArrival'), [r.get('system'+a) for a in 'XYZ']
            if not (type(price) is int and 0 < price <= 10**9 and type(volume) is int
                    and (unlimited or minimum<=volume<=10**12)
                    and finite(arrival) and 0<=arrival<=10**10 and (not prefs['arrival'] or arrival<=prefs['arrival'])
                    and all(finite(n) for n in pos)
                    and -300<=age<=prefs['hours']*3600 and math.dist(origin,pos)<=radius):
                continue
            if type(r.get('marketId')) is not int or not 0<r['marketId']<=2**63:
                continue
            try:
                station_name, system_name = line(r.get('stationName'),'Station'), line(r.get('systemName'),'System')
                body = line(r['bodyName'],'Body') if r.get('bodyName') else None
            except ValueError:
                continue
            out.append(dict(market_id=r['marketId'], station=station_name, system=system_name,
                station_type=r['stationType'], surface=kind=='surface', price=price, volume=volume, arrival_ls=arrival, pos=pos,
                demand_unlimited=unlimited,
                distance=round(math.dist(origin,pos),1), body=body,
                body_id=r.get('bodyId') if type(r.get('bodyId')) is int else None,
                mean_price=r.get('meanPrice') if type(r.get('meanPrice')) is int and 0<r['meanPrice']<=10**9 else None,
                observed_at=r['updatedAt'], source='Ardent / EDDN'))
        # Retain separate buckets so cheap surface sources cannot displace orbital
        # choices. Hidden surface comparisons use the same validated reports.
        out.sort(key=lambda r:r['price'] if side=='buy' else -r['price'])
        return dict(rows=([r for r in out if not r['surface']][:STATIONS_PER_KIND]
                         + [r for r in out if r['surface']][:STATIONS_PER_KIND]),
                    failures=failures,capped=capped,successful=successful,complete=not failures)

    def search(self, q):
        prefs = settings(q)
        if self.core.config.OFFLINE:
            raise ValueError('Live route discovery is unavailable in offline mode. Saved plans remain available.')
        with self.lock:
            if self.searching:
                raise ValueError('A PTN scan is already running. Wait for it to finish.')
            self.searching = True
            self.search_done.clear()
            self.search_job = dict(id=secrets.token_hex(10), status='running', started_at=now(),
                                   finished_at=None, error=None, poll_after_seconds=2)
            self.results = None
            self.progress = dict(done=0,total=0,message='Reading commodity catalog and public board')
            self.publish()
            job = copy.deepcopy(self.search_job)
        def run():
            try:
                self.scan(prefs)
                with self.lock:
                    self.search_job['status'] = 'complete'
            except Exception as error:
                self.core.log.exception('PTN search failed')
                with self.lock:
                    self.search_job.update(status='failed', error=str(error) if isinstance(error,ValueError)
                                           else 'Market search failed. Check the local log and retry.')
            finally:
                with self.lock:
                    self.searching = False
                    self.search_job['finished_at'] = now()
                    self.publish()
                    self.search_done.set()
        try:
            threading.Thread(target=run, name='ptn-search', daemon=True).start()
        except Exception:
            with self.lock:
                self.searching = False
                self.search_done.set()
                self.search_job.update(status='failed',error='Could not start the search.',finished_at=now())
                self.publish()
            raise
        return dict(search_job=job, searching=True, status_tool='get_ptn_desk',
                    message='Search started. Poll get_ptn_desk every 2 seconds; result and errors remain available there.')

    def scan(self, prefs):
        context, warnings = self.context(), []
        origin = self.origin(context)
        board = self.refresh_board()
        excluded = {key(n) for n in prefs['excluded'].split(',') if n.strip()}
        if prefs['skip_common']:
            excluded.update(COMMON)
        if prefs['avoid_active'] and board['available']:
            excluded.update(key(r['commodity']) for r in board['missions'])
        if not board['available']:
            warnings.append('Public PTN board unavailable: active-commodity exclusions and competitor counts are incomplete.')
        raw = self.core.services.fetch_json(MARKETS+'/commodities', ttl=600)
        if not isinstance(raw, list):
            raise ValueError('Commodity catalog unavailable. Retry the scan.')
        catalog = []
        raw = raw[:2000]
        display_names = {key(r['commodityName']):r['commodityName'].title() for r in raw
                         if isinstance(r,dict) and isinstance(r.get('commodityName'),str) and ' ' in r['commodityName']}
        seen = set()
        for r in raw:
            if not isinstance(r, dict):
                continue
            name = r.get('commodityName')
            # Catalog has both translated display names and journal identifiers. Never invent an API key.
            if (not isinstance(name, str) or not name.isascii() or not name.isalnum() or len(name)>100
                    or key(name) in excluded or key(name) in seen or r.get('rare') or is_rare(name)):
                continue
            # Catalog summaries can lag the live order feeds by months. They
            # prioritize work only; stale stock/spread must never exclude cargo.
            buy,sell = r.get('minBuyPrice'),r.get('maxSellPrice')
            spread = sell-buy if all(finite(n) and 0<=n<=10**9 for n in (buy,sell)) else 0
            seen.add(key(name))
            catalog.append((spread,name))
        catalog.sort(reverse=True)
        candidates = [name for _,name in (catalog[:prefs['breadth']] if prefs['breadth'] else catalog)][:500]
        # Nearby deliberately omits the reference system. Fetch its markets in
        # two bulk calls so arriving at a source never removes it from discovery.
        current_reports, current_complete = {}, True
        minimum = min(prefs['min_quantity'],prefs['quantity']) if prefs['allow_partial'] else prefs['quantity']
        local_query = urlencode(dict(minVolume=minimum,maxDaysAgo=math.ceil(prefs['hours']/24)+1,fleetCarriers=0))
        for side in ('buy','sell'):
            try:
                local = self.core.services.fetch_json(MARKETS+'/system/name/'+quote(context['system'],safe='')+
                    '/commodities/'+('exports?' if side=='buy' else 'imports?')+local_query,ttl=300)
                if not isinstance(local,list):
                    raise ValueError('Unexpected current-system reports.')
                if len(local)>10000:
                    warnings.append('Current-system reports reached the 10,000-order limit; coverage is partial.')
                    current_complete = False
                for row in local[:10000]:
                    if isinstance(row,dict) and isinstance(row.get('commodityName'),str) and len(row['commodityName'])<=100:
                        current_reports.setdefault((key(row['commodityName']),side),[]).append(row)
            except Exception:
                current_complete = False
                warnings.append(f'Current-system {side} reports unavailable; local station coverage is incomplete.')
        reports, coverage = {}, {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(self.quotes,name,side,prefs,origin,context['system'],current_reports.get((key(name),side),())):(name,side)
                    for name in candidates for side in ('buy','sell')}
            try:
                for done, job in enumerate(as_completed(jobs,timeout=SCAN_SECONDS),1):
                    name,side = jobs[job]
                    try:
                        report = job.result()
                        reports[name,side] = report['rows']
                        coverage[name,side] = report
                    except Exception:
                        reports[name,side] = []
                        warnings.append(f'{name}: {side} reports unavailable.')
                    if done%4==0 or done==len(jobs):
                        with self.lock:
                            self.progress = dict(done=done,total=len(jobs),message=f'{done} of {len(jobs)} commodity sides checked; searching {len(candidates)} commodities')
                            self.publish()
            except FuturesTimeout:
                warnings.insert(0,'Market search reached its time limit. Results include completed reports only; retry for more coverage.')
            finally:
                for job, report_key in jobs.items():
                    if report_key not in reports:
                        job.cancel()
                        reports[report_key] = []
        rows, hidden_sources = [], {}
        for commodity in candidates:
            pairs, prices = [], {}
            for buy in reports[commodity,'buy']:
                for sell in reports[commodity,'sell']:
                    distance = math.dist(buy['pos'],sell['pos'])
                    if buy['market_id']==sell['market_id'] or distance>prefs['max_hop'] or sell['price']<=buy['price']:
                        continue
                    ref = max((r for r in (buy,sell) if r['mean_price']),key=lambda r:stamp(r['observed_at']),default={})
                    active = [m for m in board['missions'] if key(m['commodity'])==key(commodity)]
                    loading_at_source = sum(m['callsign']!=context['callsign'] and m['phase']=='loading' and key(m['system'])==key(buy['system'])
                                            and key(m['station'])==key(buy['station']) for m in active)
                    quantity = prefs['quantity']
                    if prefs['allow_partial']:
                        quantity = min(quantity,buy['volume']//(1+loading_at_source))
                        if not unlimited_demand(sell,'sell'):
                            quantity = min(quantity,sell['volume'])
                        if quantity<prefs['min_quantity']:
                            continue
                    price_key = (buy['price'],sell['price'],quantity,ref.get('mean_price'))
                    if price_key not in prices:
                        prices[price_key] = pricing(*price_key,prefs)
                    payout = prices[price_key]
                    buffer = buy['volume']/(quantity*(1+loading_at_source))
                    reasons = []
                    if not payout['settings_valid']:
                        reasons.append('Payout floors or whole-percent carrier prices do not fit this spread.')
                    if payout['owner_after_reserve']<=0:
                        reasons.append('Carrier return must stay positive after the cost reserve.')
                    if quantity<prefs['quantity']:
                        reasons.append(f'Order reduced to {quantity:,} t to fit reported supply/demand and known loading competition.')
                    if max(datetime.now(timezone.utc).timestamp()-stamp(s['observed_at']) for s in (buy,sell))>6*3600:
                        reasons.append('A report is over 6 hours old. Verify its price before moving the carrier.')
                    if buffer<1.5:
                        reasons.append('Supply has less than 1.5 loads per known carrier. Scout competing orders.')
                    viable = payout['settings_valid'] and payout['owner_after_reserve']>0 and buffer>=1
                    # Explainable scenario comparison, not a prediction of hauler turnout or completion.
                    scenario_hr = payout['advertised_per_ton']*prefs['hauler_capacity']*60/prefs['cycle_minutes']
                    score = round(scenario_hr/10**6 + min(buffer,5)*2 - loading_at_source*10
                                  - max(buy['arrival_ls'],sell['arrival_ls'])/1000,1)
                    row = dict(id=secrets.token_hex(10), commodity=commodity, name=display_names.get(key(commodity),commodity.title()),
                               buy=buy,sell=sell,quantity=quantity,route_distance=round(distance,1),
                               approach_distance=round(math.dist(origin,buy['pos']),1),
                               approach_jumps=math.ceil(math.dist(origin,buy['pos'])/500),
                               trade_jumps=math.ceil(distance/500),
                               pricing=payout,viable=viable,reasons=reasons,supply_buffer=round(buffer,2),
                               official_competitors=loading_at_source if board['available'] else None,
                               common=commodity in COMMON,official_active=len(active) if board['available'] else None,
                               score=score,hauler_hour_scenario=round(scenario_hr),settings=prefs)
                    if buy['surface'] and not prefs.get('allow_surface_loading',False):
                        if viable:
                            source_key = (commodity,buy['market_id'])
                            previous = hidden_sources.get(source_key)
                            if not previous or score>previous['score']:
                                hidden_sources[source_key] = row
                    else:
                        pairs.append(row)
            pairs.sort(key=self.route_rank)
            # Show alternative loading locations before filling all six places
            # with different buyers for the same source (carrier parking can fill).
            choices, per_source = [], {}
            for row in pairs:
                if row['viable']!=pairs[0]['viable']:
                    break
                source = row['buy']['market_id']
                if per_source.get(source,0)>=2:
                    continue
                per_source[source] = per_source.get(source,0)+1
                choices.append(row)
                if len(choices)==6:
                    break
            chosen = {row['id'] for row in choices}
            for row in pairs:
                if len(choices)==6:
                    break
                if row['id'] not in chosen:
                    choices.append(row)
            rows.extend(choices[:6])
        rows.sort(key=self.route_rank)
        hidden = sorted(hidden_sources.values(),key=lambda r:-r['score'])
        checked = sum(all(coverage.get((name,side),{}).get('successful') for side in ('buy','sell')) for name in candidates)
        completed = sum(all(coverage.get((name,side),{}).get('complete') for side in ('buy','sell')) for name in candidates)
        failures = sum(r['failures'] for r in coverage.values())
        if failures:
            warnings.append(f'{failures} market feeds failed. Completed feeds are included; retry for missing coverage.')
        if completed<len(candidates):
            warnings.insert(0,f'Partial search: {completed} of {len(candidates)} commodities completed all market feeds.')
        result = dict(rows=rows[:200],scanned=checked,attempted=len(candidates),available=len(catalog),excluded=sorted(excluded),
                      coverage=dict(completed=completed,requested=len(candidates),catalog=len(catalog),
                          capped_feeds=sum(r['capped'] for r in coverage.values()),failed_feeds=failures,
                          all_commodities=completed==len(catalog) and current_complete,
                          current_system_complete=current_complete,routes_found=len(rows)),
                      viable=sum(r['viable'] for r in rows),checked_at=now(),origin=context['system'],settings=prefs,
                      surface_excluded=dict(count=len(hidden),examples=[dict(commodity=r['name'],station=r['buy']['station'],
                          system=r['buy']['system']) for r in hidden[:3]]),
                      warnings=warnings[:15],scope='Current-system markets, up to 1000 nearby reports plus 100 global price leaders per side, 50 eligible stops of each type. Market coverage is bounded; not every station is returned. Verify in game.',
                      context=dict(callsign=context['callsign'],commander=context['commander'],system=context['system']))
        with self.lock:
            current = self.context()
            if any(current[k]!=context[k] for k in ('callsign','commander','system')):
                raise ValueError('Carrier location or owner changed during the search. Search again from the current carrier.')
            self.results = result
            self.publish()
        return result

    @staticmethod
    def route_rank(row):
        # Hauler minimums already gate viability. Rank what the owner keeps,
        # rather than allowing supply buffers to outweigh hundreds of millions.
        return (not row['viable'],-row['pricing']['owner_after_reserve'],
                -row['pricing']['advertised_per_ton'],row['approach_jumps']+row['trade_jumps'],-row['score'])

    def select(self, q):
        with self.lock:
            self.guard(q,switching=True)
            row = next((r for r in (self.results or {}).get('rows',[]) if r['id']==q.get('id')),None)
            if not row or datetime.now(timezone.utc).timestamp()-stamp(self.results.get('checked_at'))>1800:
                raise ValueError('Choose a route from a scan less than 30 minutes old.')
            c = self.context()
            if any((self.results.get('context') or {}).get(k)!=c[k] for k in ('callsign','commander','system')):
                raise ValueError('The search belongs to a different carrier location or owner. Search again.')
            if not c['callsign'] or not c['carrier']:
                raise ValueError('Owned carrier identity is unknown. Open Carrier Management first.')
            data = copy.deepcopy(self.data)
            if data['plan']:
                data['history'] = ([dict(id=data['plan']['id'],commodity=data['plan']['name'],stage=data['plan']['stage'],
                                         ended_at=now())]+data['history'])[:10]
            data['plan'] = dict(id=secrets.token_hex(12),carrier=c['carrier'],callsign=c['callsign'],commander=c['commander'],
                               name=row['name'],commodity=row['commodity'],route=copy.deepcopy(row),stage='scouting',
                               created_at=now(),scouts={},checks={},orders={},remaining={},remaining_at={},posted={},sco=True)
            return self.commit(data)

    def operation(self, plan):
        r,p = plan['route'],plan['route']['settings']
        buy,sell = (plan['scouts'].get(side) or r[side] for side in ('buy','sell'))
        refs = [s for s in (buy,sell) if type(s.get('mean_price')) is int and s['mean_price']>0]
        mean = max(refs,key=lambda s:stamp(s['observed_at']),default={}).get('mean_price')
        costs = pricing(buy['price'],sell['price'],r['quantity'],mean,p)
        phase = plan['stage'] if plan['stage'] in ('loading','unloading') else 'loading'
        public_phase = paid_leg(p,phase)
        phase_order = plan['orders'].get(phase)
        actual_buy = plan['orders'].get('loading',{}).get('price',costs['carrier_buy'])
        actual_sell = plan['orders'].get('unloading',{}).get('price',costs['carrier_sell'])
        loading = actual_buy-buy['price'] if paid_leg(p,'loading') else 0
        unloading = sell['price']-actual_sell if paid_leg(p,'unloading') else 0
        # A self-hauled leg uses the actual station purchase cost / sale proceeds,
        # not a carrier transfer price. No profit is attributed to public haulers.
        station_buy = buy['price'] if paid_leg(p,'loading') else actual_buy
        station_sell = sell['price'] if paid_leg(p,'unloading') else actual_sell
        costs.update(loading_per_ton=loading,unloading_per_ton=unloading,
                     carrier_buy=actual_buy,carrier_sell=actual_sell,funding=actual_buy*r['quantity'],
                     gross_per_ton=station_sell-station_buy,gross_total=(station_sell-station_buy)*r['quantity'],
                     owner_per_ton=actual_sell-actual_buy,owner_total=(actual_sell-actual_buy)*r['quantity'],
                     owner_after_reserve=(actual_sell-actual_buy)*r['quantity']-p['cost_reserve'],
                     hauler_total=(loading+unloading)*r['quantity'])
        blockers = []
        clock,c = datetime.now(timezone.utc).timestamp(),self.context()
        remaining = plan['remaining'].get(phase,r['quantity'])
        journal_order = c['orders'].get(plan['commodity'],{})
        fresh_order = (public_phase and phase_order and stamp(journal_order.get('updated_at'))>
                       max(stamp(phase_order['checked_at']),stamp(plan.get('remaining_at',{}).get(phase))))
        remaining_source = 'Owner-checked order'
        if fresh_order:
            expected_side = 'buy' if phase=='loading' else 'sell'
            if journal_order.get('side')!=expected_side or journal_order.get('price')!=phase_order['price']:
                blockers.append('A newer journal order has a different price or side. Recheck and confirm the actual game values.')
            elif type(journal_order.get('quantity')) is int and 0<=journal_order['quantity']<=r['quantity']:
                remaining = journal_order['quantity']
                remaining_source = 'Newer carrier order journal'
            else:
                blockers.append('A newer carrier order exceeds this plan size. Recheck the remaining tonnes.')
        if c['commander']!=plan.get('commander') or c['callsign']!=plan.get('callsign'):
            blockers.append('The active commander or carrier does not match this plan.')
        for side in ('buy','sell'):
            scout = plan['scouts'].get(side)
            invalid = plan.get('invalid_scouts', {}).get(side)
            if invalid:
                blockers.append(invalid['reason'] + ' Capture a valid market and confirm the order again.')
            historical = side=='buy' and plan['stage'] in ('transit','unloading','complete')
            needed = remaining if (side=='buy' and phase=='loading') or (side=='sell' and phase=='unloading') else r['quantity']
            if not scout:
                blockers.append(('Loading' if side=='buy' else 'Unloading')+' station has not been scouted.')
            elif not historical and not -300<=clock-stamp(scout['observed_at'])<=min(p['hours']*3600,3600):
                blockers.append(('Loading' if side=='buy' else 'Unloading')+' scout price has expired. Recheck the market.')
            elif not historical and not unlimited_demand(scout,side) and scout['volume']<needed:
                blockers.append(('Supply' if side=='buy' else 'Demand')+' no longer covers the planned order.')
        if not costs['settings_valid']:
            blockers.append('The scouted spread cannot support the public payout minimums and carrier margin at whole-percent prices.')
        if costs['owner_after_reserve']<=0:
            blockers.append('The carrier return must be positive after the cost reserve.')
        basic = list(blockers)
        if not public_phase:
            blockers.append('You are hauling this leg yourself. There is no public advert for this phase.')
        if plan['stage'] not in ('loading','unloading'):
            blockers.append('Open the loading or unloading phase before preparing its advert.')
        stop = buy if phase=='loading' else sell
        if key(c.get('system'))!=key(stop['system']):
            blockers.append('The carrier is not reported in the advertised station system.')
        if not -300<=clock-stamp(c.get('stats_at'))<=3600:
            blockers.append('Open Carrier Management to refresh carrier capacity and location; its stats are over an hour old or unknown.')
        reserved_here = (journal_order.get('quantity',0) if journal_order.get('side')=='buy'
                         and phase_order and journal_order.get('price')==phase_order['price']
                         and stamp(journal_order.get('updated_at'))>=stamp(plan['created_at']) else 0)
        if public_phase and phase=='loading' and (not finite(c['free_space']) or c['free_space']+reserved_here<remaining):
            blockers.append('Unreserved carrier space does not cover the order. Cancel or resize old buy orders in game, then refresh Carrier Management.')
        checks = plan['checks'].get(phase,{})
        labels = dict(near_station='Confirm the carrier is parked close to the station body.',
                      docking_open='Confirm carrier docking access is open to haulers.',
                      funds_checked='Confirm the order is funded and the market service is open.',
                      competition_checked='Check other carriers and the station supply/demand before posting.')
        blockers.extend(labels[k] for k in CHECKS if public_phase and checks.get(k) is not True)
        if not phase_order:
            blockers.append('Enter and confirm the actual in-game carrier order price.')
        elif clock-stamp(phase_order['checked_at'])>3600:
            blockers.append('Recheck the in-game carrier order; its confirmation is over an hour old.')
        else:
            margin = phase_order['price']-buy['price'] if phase=='loading' else sell['price']-phase_order['price']
            floor = p['loading_floor' if phase=='loading' else 'unloading_floor']
            if public_phase and margin<floor:
                blockers.append('The actual carrier order underpays your advertised payout floor.')
            # Preserve the other leg's promised payout and minimum owner margin.
            owner = (actual_sell-phase_order['price'] if phase=='loading'
                     else phase_order['price']-actual_buy)
            if owner<owner_minimum(p,r['quantity']):
                blockers.append('The actual order leaves insufficient margin for the other leg and carrier reserve.')
        if remaining<=0:
            blockers.append('This order has no remaining tonnes to advertise.')
        posted = plan['posted'].get(phase)
        return dict(revision=self.data['revision'],plan_id=plan['id'],stage=plan['stage'],
                    pricing=costs,phase=phase,public_phase=public_phase,buy=buy,sell=sell,blockers=blockers,scout_blockers=basic,
                    ready=not blockers,remaining=remaining,checks=checks,order=phase_order,
                    remaining_source=remaining_source,
                    posted=posted,advert_expired=bool(posted and clock-stamp(posted['at'])>=48*3600),
                    runs=math.ceil(r['quantity']/p['hauler_capacity']),
                    scenario_minutes=math.ceil(r['quantity']/p['hauler_capacity']/p['haulers'])*p['cycle_minutes'])

    def capture(self, q):
        with self.lock:
            self.guard(q)
            plan = self.data['plan']
            if not plan or plan['stage'] in ('complete','cancelled'):
                raise ValueError('Choose an active route before capturing a station market.')
            side = q.get('side')
            if side not in ('buy','sell'):
                raise ValueError('Choose the loading or unloading station.')
            j = self.core.store.get('journal') or {}
            market = j.get('market') or {}
            target = plan['route'][side]
            clock = datetime.now(timezone.utc).timestamp()
            kind = station_kind(j.get('station_type'))
            expected_kind = station_kind(target.get('station_type'))
            surface_allowed = side=='buy' and plan['route']['settings'].get('allow_surface_loading',False)
            if (not j.get('docked') or not kind or kind!=expected_kind or (kind=='surface' and not surface_allowed)
                    or j.get('system')!=target['system']
                    or j.get('station')!=target['station'] or market.get('market_id')!=target['market_id']
                    or not -300<=clock-stamp(market.get('timestamp'))<=900
                    or stamp(market.get('timestamp'))<self.docked_at):
                raise ValueError('Dock at the selected station with the allowed station type and open its commodity market now, then capture again.')
            item = next((r for r in market.get('commodities',[]) if key(r.get('key'))==key(plan['commodity'])),None)
            if not item:
                return self.reject_capture(side, market, 'The selected commodity is missing from the current market snapshot.')
            price,volume = item.get(side),item.get('stock' if side=='buy' else 'demand')
            try:
                price,volume = integer(price,'Station price',1),integer(volume,'Station supply/demand',0,10**12)
            except ValueError as error:
                return self.reject_capture(side, market, str(error))
            snapshot_matches = (self.latest_market.get('MarketID')==target['market_id']
                                and self.latest_market.get('timestamp')==market.get('timestamp'))
            raw = next((r for r in self.latest_market.get('Items',[]) if isinstance(r,dict)
                        and key(norm(r.get('Name'))) == key(plan['commodity'])),{}) if snapshot_matches else {}
            if (raw.get('Producer') is False and side=='buy') or (raw.get('Consumer') is False and side=='sell'):
                return self.reject_capture(side, market, 'This market does not offer this side of the trade. Recheck the commodity.')
            unlimited = side=='sell' and volume==0
            if unlimited and not (type(raw.get('Demand')) is int and raw['Demand']==0
                                  and type(raw.get('SellPrice')) is int and raw['SellPrice']==price):
                return self.reject_capture(side, market, 'Unlimited demand needs an explicit zero demand and positive sell price in the current market journal. Open Commodities again and recapture.')
            mean = raw.get('MeanPrice')
            if type(mean) is not int or not 0<mean<=10**9:
                mean = None
            data = copy.deepcopy(self.data)
            data['plan'].setdefault('invalid_scouts', {}).pop(side, None)
            data['plan']['scouts'][side] = {**target,'station_type':j['station_type'],'surface':kind=='surface',
                                          'price':price,'volume':volume,'mean_price':mean,
                                          'demand_unlimited':unlimited,
                                          'observed_at':market['timestamp'],'source':'Local market journal'}
            if item.get('name'):
                data['plan']['name'] = line(item['name'],'Commodity')
            # Purchase costs become historical once loading ends; a fresh buyer
            # report must not erase the price already paid to loading haulers.
            if plan['stage'] in ('transit','unloading'):
                data['plan']['checks'].pop('unloading',None)
                data['plan']['orders'].pop('unloading',None)
            else:
                data['plan']['checks'],data['plan']['orders'] = {},{}
            return self.commit(data)

    def reject_capture(self, side, market, reason):
        """Persist newer contradictory evidence before rejecting an active scout."""
        plan = self.data['plan']
        scout = plan['scouts'].get(side)
        # The station/docking/freshness checks have already passed. Only matching
        # raw local evidence newer than a saved scout may revoke its confirmation.
        trusted = (self.latest_market.get('MarketID') == market.get('market_id')
                   and self.latest_market.get('timestamp') == market.get('timestamp'))
        historical = side == 'buy' and plan['stage'] in ('transit', 'unloading')
        if trusted and scout and not historical and stamp(market.get('timestamp')) > stamp(scout.get('observed_at')):
            data = copy.deepcopy(self.data)
            p = data['plan']
            p.setdefault('invalid_scouts', {})[side] = dict(reason=reason, observed_at=market['timestamp'])
            p['scouts'].pop(side, None)
            phase = 'loading' if side == 'buy' else 'unloading'
            p['checks'].pop(phase, None)
            p['orders'].pop(phase, None)
            try:
                self.commit(data)
            except OSError:
                # Never keep offering an advert after observing a contradiction,
                # even when the disk cannot save the invalidation.
                self.data = data
                self.publish()
                raise
        raise ValueError(reason)

    def update(self, q):
        with self.lock:
            self.guard(q)
            if not self.data['plan']:
                raise ValueError('Choose a route first.')
            data = copy.deepcopy(self.data)
            p,action = data['plan'],q.get('action')
            if action=='stage':
                stage = q.get('stage')
                allowed = {'scouting':('loading','cancelled'),'loading':('transit','cancelled'),
                           'transit':('unloading','cancelled'),'unloading':('complete','cancelled')}
                if stage not in allowed.get(p['stage'],()):
                    raise ValueError('Follow Scout, Load, Move, Unload, Complete in order.')
                if stage=='loading' and self.operation(p)['scout_blockers']:
                    raise ValueError('Scout both markets and resolve the route economics before loading.')
                if stage=='transit' and p['remaining'].get('loading',p['route']['quantity'])!=0:
                    raise ValueError('Confirm zero tonnes remain to load before departure.')
                if stage=='transit' and not p['orders'].get('loading'):
                    raise ValueError('Confirm the actual loading order price before departure; it becomes the purchase cost.')
                if stage=='complete' and p['remaining'].get('unloading',p['route']['quantity'])!=0:
                    raise ValueError('Confirm zero tonnes remain to unload before completing.')
                if stage=='complete' and not p['orders'].get('unloading'):
                    raise ValueError('Confirm the actual unloading order price before completing.')
                p['stage'] = stage
            elif action=='confirm':
                phase = p['stage']
                if phase not in ('loading','unloading'):
                    raise ValueError('Open a loading or unloading phase first.')
                checks = q.get('checks')
                public_phase = paid_leg(p['route']['settings'],phase)
                if public_phase and (not isinstance(checks,dict) or any(type(checks.get(k)) is not bool for k in CHECKS)):
                    raise ValueError('Confirm the four carrier and station checks explicitly.')
                p['checks'][phase] = {k:checks[k] for k in CHECKS} if public_phase else {}
                p['orders'][phase] = dict(price=integer(q.get('price'),'Actual carrier order price',1),checked_at=now())
                p['remaining'][phase] = integer(q.get('remaining'),'Remaining tonnes',0,p['route']['quantity'])
                p.setdefault('remaining_at',{})[phase] = now()
                if type(q.get('sco',True)) is not bool:
                    raise ValueError('SCO recommendation must be true or false.')
                p['sco'] = q.get('sco',True)
            elif action=='remaining':
                if p['stage'] not in ('loading','unloading'):
                    raise ValueError('Open a loading or unloading phase first.')
                p['remaining'][p['stage']] = integer(q.get('remaining'),'Remaining tonnes',0,p['route']['quantity'])
                p.setdefault('remaining_at',{})[p['stage']] = now()
            elif action=='posted':
                if not self.operation(p)['ready']:
                    raise ValueError('Resolve advert checks before recording a posted advert.')
                link = q.get('link','')
                if (not isinstance(link,str) or len(link)>250
                        or (link and not re.fullmatch(r'https://discord\.com/channels/[0-9]{1,25}/[0-9]{1,25}/[0-9]{1,25}',link))):
                    raise ValueError('Enter a Discord message link, or leave it blank.')
                p['posted'][p['stage']] = dict(at=now(),link=link)
            else:
                raise ValueError('Unknown PTN plan action.')
            return self.commit(data)

    def carrier_handoff(self, q):
        with self.lock:
            self.guard(q)
            plan = self.data.get('plan')
            if not plan or plan['stage'] not in ('scouting', 'loading'):
                raise ValueError('Hand off a scouted route before leaving the loading phase.')
            stock = integer(q.get('starting_stock'), 'Checked starting carrier stock', 0, 1000000)
            operation = self.operation(plan)
            if operation['scout_blockers']:
                raise ValueError('Finish current station scouting before handing this route to Carrier ops.')
            buy,sell = operation['buy'],operation['sell']
            route = plan['route']
            tool = self.core.http.tools.get('plan_carrier_trade')
            if not tool:
                raise ValueError('Carrier operations module is unavailable.')
            confirmed = plan['orders'].get('loading') if paid_leg(route['settings'],'loading') else None
            candidate = dict(commodity=plan['commodity'],source=buy['station']+' / '+buy['system'],
                destination=sell['station']+' / '+sell['system'],source_market_id=buy['market_id'],
                destination_market_id=sell['market_id'],mode='load',source_price=buy['price'],
                destination_price=sell['price'],carrier_price=confirmed['price'] if confirmed else operation['pricing']['carrier_buy'],
                carrier_price_known=bool(confirmed),target=stock+route['quantity'],planned_quantity=route['quantity'],crew_enabled=False)
        # The checked revision is an immutable snapshot. Do not hold the PTN
        # lock while publishing trade state: trade listeners also publish PTN.
        return tool.fn(candidate)

    def make_advert(self, q):
        with self.lock:
            self.guard(q)
            p = self.data['plan']
            if not p:
                raise ValueError('Choose and scout a route first.')
            op = self.operation(p)
            if op['blockers']:
                raise ValueError(' '.join(op['blockers']))
            stop = op['buy'] if op['phase']=='loading' else op['sell']
            profit = op['pricing']['loading_per_ton' if op['phase']=='loading' else 'unloading_per_ton']
            text = advert(p['carrier'],p['callsign'],p['name'],stop['station'],stop['system'],op['phase'],profit,op['remaining'])
            notes = []
            if station_kind(stop.get('station_type'))=='surface':
                notes.append('Odyssey surface port.' if stop['station_type'] in ('OnFootSettlement','Odyssey Settlement') else 'Surface port.')
            if p.get('sco'):
                notes.append('SCO FSD recommended.')
            notes = ' '.join(notes)
            return dict(advert=text,notes=notes,copy_text=text+('\n'+notes if notes else ''),profit_per_ton=profit,
                        remaining=op['remaining'],instructions='Use /aco trade and review its generated string, then paste in affiliate-trade-alerts without role pings. Review and confirm Roomba; close it with the appropriate completion reaction. This desk does not post or close Discord adverts.')


def setup(core, module):
    desk = PTN(core)
    module.ptn = desk
    revision = {'revision':dict(type='integer',required=True,description='Current revision from get_ptn_desk; stale changes are rejected.')}
    search_params = {name:dict(type='boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'string',
                              default=value,description=name.replace('_',' ')) for name,value in DEFAULTS.items()}
    search_params['haul_mode'].update(enum=['both','self_load','self_unload'],
        description='both: pay public haulers on both legs; self_load/self_unload: owner hauls that leg and pays haulers on the other.')
    search_params['payout_target']['description']='Preferred public payout in Cr/t. Ranks routes but never silently changes minimum payouts or hides profitable alternatives.'
    search_params['allow_partial']['description']='Allow smaller orders down to min_quantity when reports cannot support quantity. Every result carries its actual size and recalculated reserve.'
    search_params['owner_floor']['description']='Minimum carrier margin per tonne before the cost reserve. A positive total return after the reserve is always required.'
    search_params['allow_surface_loading']['description']='Include known large-pad surface loading stations. Default false. Unloading remains orbital. Excluded surface sources with profitable pairs are summarized separately.'
    search_params['radius']['description']='Maximum Ly from current carrier to loading source; default 1500 (three 500 Ly jumps minimum). Buyers are checked from the source, not the starting carrier.'
    search_params['max_hop']['description']='Maximum Ly from loading source to buyer; default 1500. Multi-jump legs are allowed; displayed jumps are straight-line lower bounds, not plotted paths.'
    search_params['breadth']['description']='Commodity limit: 0 (default) checks every non-rare catalog commodity after explicit exclusions, up to 500. Nonzero limits are optional. Coverage reports incomplete scans.'
    search_params['arrival']['description']='Optional maximum station distance from the main star in Ls; 0 (default) imposes no cutoff. This is a scouting approach, not the hauler trip from a carrier parked near the body.'
    core.http.route('/api/ptn',lambda q:desk.view(),tool='get_ptn_desk',module=module.name,
                    description='PTN carrier plan, independent of Carrier job. Includes scouted prices, payout floors, readiness blockers, order confirmations and public official-board comparisons. No game or Discord actions.')
    core.http.route('/api/ptn/board',desk.refresh_board,tool='get_ptn_public_board',module=module.name,
                    description='Refresh public official PTN missions and median loading/unloading payouts. Affiliate adverts and unadvertised carriers are not covered. Failure is unknown competition, not zero.')
    core.http.route('/api/ptn/search',desk.search,tool='find_ptn_routes',params=search_params,module=module.name,
                    description='Start a background scan and return immediately. Poll get_ptn_desk every 2 seconds for search_job status, errors and result; do not start duplicate scans. Search every non-rare catalog commodity using nearby and global Ardent/EDDN reports, ranked by carrier return after reserve. Default: sources within 1500 Ly of carrier, buyers within 1500 Ly of source, orbital-only, 20k minimum per public leg, retain surplus, up to 18k tonnes with smaller orders allowed. Explicit zero-demand buyers have demand_unlimited=true; zero loading stock is empty. Market coverage is bounded and reported. No game or Discord actions; scout prices before posting.')
    core.http.route('/api/ptn/select',desk.select,tool='select_ptn_route',method='POST',module=module.name,
                    params={**revision,'id':dict(type='string',required=True,description='Route id from the latest PTN scan.')},
                    description='Save an independent PTN scouting plan from a recent candidate. Replaces only the local PTN draft; never changes Carrier job, game orders or Discord messages.')
    core.http.route('/api/ptn/carrier',desk.carrier_handoff,tool='handoff_ptn_to_carrier',method='POST',module=module.name,
                    params={**revision,'starting_stock':dict(type='integer',required=True,description='Owner-checked existing tonnes of this commodity aboard the carrier.')},
                    description='Copy a freshly scouted PTN loading route and agreed prices into a local Carrier ops plan for crew coordination. Rejects an active carrier job. PTN stages remain independent; no order is placed and no game or Discord action occurs.')
    core.http.route('/api/ptn/capture',desk.capture,tool='capture_ptn_market',method='POST',module=module.name,
                    params={**revision,'side':dict(type='string',enum=['buy','sell'],required=True,description='buy = loading station; sell = unloading station.')},
                    description='Capture the current journal commodity price and volume at the selected station, respecting the saved surface-loading preference. Requires docking and a market snapshot from the current visit within 15 minutes. Unlimited demand requires explicit zero-demand buyer evidence in that journal. Invalidates order checks; never fabricates a scout visit.')
    core.http.route('/api/ptn/update',desk.update,tool='update_ptn_plan',method='POST',module=module.name,
                    params={**revision,'action':dict(type='string',required=True,enum=['stage','confirm','remaining','posted']),
                        'stage':dict(type='string',enum=list(PHASES)),'checks':dict(type='object',description='Explicit booleans: near_station, docking_open, funds_checked, competition_checked.'),
                        'price':dict(type='integer',description='Actual carrier order price on public legs; actual average station purchase cost or sale proceeds per tonne on a self-hauled leg.'),
                        'remaining':dict(type='integer',description='Owner-checked outstanding order tonnes.'),'sco':dict(type='boolean'),
                        'link':dict(type='string',description='Optional Discord message link; recording is not posting.')},
                    description='Owner updates PTN stages, four posting checks, actual order price, remaining tonnes or manually posted link. Stages require explicit zero remaining before departure/completion. This never executes in-game or Discord actions.')
    core.http.route('/api/ptn/advert',desk.make_advert,tool='prepare_ptn_advert',params=revision,module=module.name,
                    description='Generate exact affiliate Markdown only after fresh scouts, actual carrier price and owner checks pass. Includes optional SCO note; preserves exact profit and quantity without rounding up. User must use /aco trade, post and confirm Roomba themselves.')
