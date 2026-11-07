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
from modules.ptn.planning import (COMMON, DEFAULTS, ORBITAL, advert, finite, integer, key, line,
                                  now, paid_leg, owner_minimum, pricing, settings, stamp)

BOARD = 'https://pilotstradenetwork.com/wp-json/ptn/v1/missions'
MARKETS = 'https://api.ardent-insight.com/v2'
FILE = 'ptn.json'
PHASES = ('scouting', 'loading', 'transit', 'unloading', 'complete', 'cancelled')
CHECKS = ('near_station', 'docking_open', 'funds_checked', 'competition_checked')
SCAN_SECONDS = 90


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
                        progress=copy.deepcopy(self.progress))
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

    def quotes(self, commodity, side, prefs, origin, system):
        minimum = min(prefs['min_quantity'],prefs['quantity']) if prefs['allow_partial'] else prefs['quantity']
        query = urlencode(dict(minVolume=minimum, maxDaysAgo=math.ceil(prefs['hours']/24),
                               maxDistance=prefs['radius'], fleetCarriers=0))
        # Global best-100 lists were discarding nearby stations before our filters
        # ran. The documented nearby endpoints return up to 1000 in this area.
        raw = self.core.services.fetch_json(MARKETS+'/system/name/'+quote(system,safe='')+
                                            '/commodity/name/'+quote(commodity, safe='')+'/nearby'+
                                            ('/exports?' if side=='buy' else '/imports?')+query, ttl=180)
        if not isinstance(raw, list):
            raise ValueError('Unexpected commodity report response.')
        clock, out = datetime.now(timezone.utc).timestamp(), []
        for r in raw[:1000]:
            if not isinstance(r, dict) or r.get('stationType') not in ORBITAL or r.get('maxLandingPadSize')!=3:
                continue
            if r.get('isPlanetary') or r.get('isProhibited') or r.get('isRare'):
                continue
            if key(r.get('commodityName')) != key(commodity):
                continue
            age = clock-stamp(r.get('updatedAt'))
            price = r.get('buyPrice' if side=='buy' else 'sellPrice')
            volume = r.get('stock' if side=='buy' else 'demand')
            arrival, pos = r.get('distanceToArrival'), [r.get('system'+a) for a in 'XYZ']
            if not (type(price) is int and 0 < price <= 10**9 and type(volume) is int and minimum<=volume<=10**12
                    and finite(arrival) and 0<=arrival<=prefs['arrival'] and all(finite(n) for n in pos)
                    and -300<=age<=prefs['hours']*3600 and math.dist(origin,pos)<=prefs['radius']):
                continue
            if type(r.get('marketId')) is not int or not 0<r['marketId']<=2**63:
                continue
            try:
                station_name, system_name = line(r.get('stationName'),'Station'), line(r.get('systemName'),'System')
                body = line(r['bodyName'],'Body') if r.get('bodyName') else None
            except ValueError:
                continue
            out.append(dict(market_id=r['marketId'], station=station_name, system=system_name,
                station_type=r['stationType'], price=price, volume=volume, arrival_ls=arrival, pos=pos,
                distance=round(math.dist(origin,pos),1), body=body,
                body_id=r.get('bodyId') if type(r.get('bodyId')) is int else None,
                mean_price=r.get('meanPrice') if type(r.get('meanPrice')) is int and 0<r['meanPrice']<=10**9 else None,
                observed_at=r['updatedAt'], source='Ardent / EDDN'))
        return sorted(out,key=lambda r:r['price'] if side=='buy' else -r['price'])[:15]

    def search(self, q):
        prefs = settings(q)
        if self.core.config.OFFLINE:
            raise ValueError('Live route discovery is unavailable in offline mode. Saved plans remain available.')
        with self.lock:
            if self.searching:
                raise ValueError('A PTN scan is already running. Wait for it to finish.')
            self.searching = True
            self.progress = dict(done=0,total=0,message='Reading commodity catalog and public board')
            self.publish()
        try:
            return self.scan(prefs)
        finally:
            with self.lock:
                self.searching = False
                self.publish()

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
            stock, buy, sell = r.get('totalStock'), r.get('minBuyPrice'), r.get('maxSellPrice')
            minimum = min(prefs['min_quantity'],prefs['quantity']) if prefs['allow_partial'] else prefs['quantity']
            if not all(finite(n) for n in (stock,buy,sell)) or stock<minimum or not 0<buy<sell<=10**9:
                continue
            seen.add(key(name))
            catalog.append((sell-buy,name))
        catalog.sort(reverse=True)
        candidates = [name for _,name in catalog[:prefs['breadth']]]
        reports = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(self.quotes,name,side,prefs,origin,context['system']):(name,side)
                    for name in candidates for side in ('buy','sell')}
            try:
                for done, job in enumerate(as_completed(jobs,timeout=SCAN_SECONDS),1):
                    name,side = jobs[job]
                    try:
                        reports[name,side] = job.result()
                    except Exception:
                        reports[name,side] = []
                        warnings.append(f'{name}: {side} reports unavailable.')
                    if done%4==0 or done==len(jobs):
                        with self.lock:
                            self.progress = dict(done=done,total=len(jobs),message=f'{done} of {len(jobs)} market reports checked')
                            self.publish()
            except FuturesTimeout:
                warnings.insert(0,'Market search reached its time limit. Results include completed reports only; retry for more coverage.')
            finally:
                for job, report_key in jobs.items():
                    if report_key not in reports:
                        job.cancel()
                        reports[report_key] = []
        rows = []
        for commodity in candidates:
            pairs = []
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
                        quantity = min(quantity,buy['volume']//(1+loading_at_source),sell['volume'])
                        if quantity<prefs['min_quantity']:
                            continue
                    payout = pricing(buy['price'],sell['price'],quantity,ref.get('mean_price'),prefs)
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
                               pricing=payout,viable=viable,reasons=reasons,supply_buffer=round(buffer,2),
                               official_competitors=loading_at_source if board['available'] else None,
                               common=commodity in COMMON,official_active=len(active) if board['available'] else None,
                               score=score,hauler_hour_scenario=round(scenario_hr),settings=prefs)
                    pairs.append(row)
            pairs.sort(key=lambda r:(not r['viable'],not r['pricing']['meets_target'],-r['score'],-r['quantity']))
            rows.extend(pairs[:2])
        rows.sort(key=lambda r:(not r['viable'],not r['pricing']['meets_target'],-r['score'],-r['pricing']['owner_after_reserve']))
        result = dict(rows=rows[:48],scanned=len(candidates),available=len(catalog),excluded=sorted(excluded),
                      viable=sum(r['viable'] for r in rows),checked_at=now(),origin=context['system'],settings=prefs,
                      warnings=warnings[:15],scope='Nearby Ardent/EDDN reports; up to 1000 reports and 15 eligible stations per side per commodity. Verify in game.',
                      context=dict(callsign=context['callsign'],commander=context['commander'],system=context['system']))
        with self.lock:
            current = self.context()
            if any(current[k]!=context[k] for k in ('callsign','commander','system')):
                raise ValueError('Carrier location or owner changed during the search. Search again from the current carrier.')
            self.results = result
            self.publish()
        return result

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
            historical = side=='buy' and plan['stage'] in ('transit','unloading','complete')
            needed = remaining if (side=='buy' and phase=='loading') or (side=='sell' and phase=='unloading') else r['quantity']
            if not scout:
                blockers.append(('Loading' if side=='buy' else 'Unloading')+' station has not been scouted.')
            elif not historical and not -300<=clock-stamp(scout['observed_at'])<=min(p['hours']*3600,3600):
                blockers.append(('Loading' if side=='buy' else 'Unloading')+' scout price has expired. Recheck the market.')
            elif not historical and scout['volume']<needed:
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
            if (not j.get('docked') or j.get('station_type') not in ORBITAL or j.get('system')!=target['system']
                    or j.get('station')!=target['station'] or market.get('market_id')!=target['market_id']
                    or not -300<=clock-stamp(market.get('timestamp'))<=900
                    or stamp(market.get('timestamp'))<self.docked_at):
                raise ValueError('Dock at this orbital station and open its commodity market now, then capture again.')
            item = next((r for r in market.get('commodities',[]) if key(r.get('key'))==key(plan['commodity'])),None)
            if not item:
                raise ValueError('The selected commodity is missing from the current market snapshot.')
            price,volume = item.get(side),item.get('stock' if side=='buy' else 'demand')
            price,volume = integer(price,'Station price',1),integer(volume,'Station supply/demand',0,10**12)
            snapshot_matches = (self.latest_market.get('MarketID')==target['market_id']
                                and self.latest_market.get('timestamp')==market.get('timestamp'))
            raw = next((r for r in self.latest_market.get('Items',[]) if isinstance(r,dict)
                        and key(norm(r.get('Name'))) == key(plan['commodity'])),{}) if snapshot_matches else {}
            if (raw.get('Producer') is False and side=='buy') or (raw.get('Consumer') is False and side=='sell'):
                raise ValueError('This market does not offer this side of the trade. Recheck the commodity.')
            mean = raw.get('MeanPrice')
            if type(mean) is not int or not 0<mean<=10**9:
                mean = None
            data = copy.deepcopy(self.data)
            data['plan']['scouts'][side] = {**target,'price':price,'volume':volume,'mean_price':mean,
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
            notes = 'SCO FSD recommended.' if p.get('sco') else ''
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
    core.http.route('/api/ptn',lambda q:desk.view(),tool='get_ptn_desk',module=module.name,
                    description='PTN carrier plan, independent of Carrier job. Includes scouted prices, payout floors, readiness blockers, order confirmations and public official-board comparisons. No game or Discord actions.')
    core.http.route('/api/ptn/board',desk.refresh_board,tool='get_ptn_public_board',module=module.name,
                    description='Refresh public official PTN missions and median loading/unloading payouts. Affiliate adverts and unadvertised carriers are not covered. Failure is unknown competition, not zero.')
    core.http.route('/api/ptn/search',desk.search,tool='find_ptn_routes',params=search_params,module=module.name,
                    description='Find profitable large-pad orbital carrier routes using nearby Ardent/EDDN reports. Default: 20k preferred payout, 10k minimum per public leg, up to 18k tonnes with smaller orders allowed, common cargo included. Supports owner hauling one leg. Positive carrier return after the reserve is mandatory. No game or Discord actions; scout prices before posting.')
    core.http.route('/api/ptn/select',desk.select,tool='select_ptn_route',method='POST',module=module.name,
                    params={**revision,'id':dict(type='string',required=True,description='Route id from the latest PTN scan.')},
                    description='Save an independent PTN scouting plan from a recent candidate. Replaces only the local PTN draft; never changes Carrier job, game orders or Discord messages.')
    core.http.route('/api/ptn/capture',desk.capture,tool='capture_ptn_market',method='POST',module=module.name,
                    params={**revision,'side':dict(type='string',enum=['buy','sell'],required=True,description='buy = loading station; sell = unloading station.')},
                    description='Capture the current journal commodity price and volume at the selected orbital station. Requires docking and a market snapshot from the current visit within 15 minutes. Invalidates order checks; never fabricates a scout visit.')
    core.http.route('/api/ptn/update',desk.update,tool='update_ptn_plan',method='POST',module=module.name,
                    params={**revision,'action':dict(type='string',required=True,enum=['stage','confirm','remaining','posted']),
                        'stage':dict(type='string',enum=list(PHASES)),'checks':dict(type='object',description='Explicit booleans: near_station, docking_open, funds_checked, competition_checked.'),
                        'price':dict(type='integer',description='Actual carrier order price on public legs; actual average station purchase cost or sale proceeds per tonne on a self-hauled leg.'),
                        'remaining':dict(type='integer',description='Owner-checked outstanding order tonnes.'),'sco':dict(type='boolean'),
                        'link':dict(type='string',description='Optional Discord message link; recording is not posting.')},
                    description='Owner updates PTN stages, four posting checks, actual order price, remaining tonnes or manually posted link. Stages require explicit zero remaining before departure/completion. This never executes in-game or Discord actions.')
    core.http.route('/api/ptn/advert',desk.make_advert,tool='prepare_ptn_advert',params=revision,module=module.name,
                    description='Generate exact affiliate Markdown only after fresh scouts, actual carrier price and owner checks pass. Includes optional SCO note; preserves exact profit and quantity without rounding up. User must use /aco trade, post and confirm Roomba themselves.')
