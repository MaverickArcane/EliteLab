"""Trader-first cargo liquidation with bounded background discovery."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import secrets
import threading

from modules.selling import planning as p

FILE = 'selling.json'
STATIONS = 'https://www.spansh.co.uk/api/stations/search'
# Station rows can include large outfitting lists. Keep individual responses
# below the shared 8 MiB download limit while retaining the overall search bound.
PAGE_SIZE = 25


def now():
    return datetime.now(timezone.utc).isoformat()


class Selling:
    def __init__(self,core):
        self.core=core
        self.lock=threading.RLock()
        self.saved=core.read_data(FILE,default={}) or {}
        self.io=threading.Lock();self.changed=threading.Condition(self.lock)
        self.version=0;self.written=0;self.writer=None;self.stopping=False;self.save_error=None
        core.shutdown_callbacks.append(self.close)
        self.result=None;self.job=None;self.done=threading.Event();self.done.set()
        self.purchases={}
        for event in ('state.journal.cargo','state.journal.cmdr','state.journal.system'):
            core.bus.on(event,lambda n,v:self.publish())
        core.bus.on('journal.MarketSell',self.sale)
        core.bus.on('journal.MarketBuy',self.purchase)
        core.bus.on('journal.LoadGame',self.reset_purchases)
        self.publish()

    def identity(self):
        j=self.core.store.get('journal') or {}
        return j.get('cmdr')

    def context(self):
        j=self.core.store.get('journal') or {}
        goods,excluded=p.cargo(j)
        return dict(commander=j.get('cmdr'),system=j.get('system'),pos=j.get('star_pos'),goods=goods,excluded=excluded)

    def view(self,q=None):
        with self.lock:
            context=self.context()
            plan=copy.deepcopy(self.saved.get(self.identity()))
            if plan:
                for stop in plan['stops']:
                    for sale in stop['sales']:
                        sale['remaining']=max(0,sale['quantity']-plan.get('sold',{}).get(str(stop['market_id'])+':'+sale['key'],0))
                plan['complete']=all(not s['remaining'] for stop in plan['stops'] for s in stop['sales'])
                plan['next_stop']=next((m for m in plan['stops'] if any(s['remaining'] for s in m['sales'])),None)
                expected={r['key']:r['quantity'] for r in plan['cargo']}
                for stop in plan['stops']:
                    for s in stop['sales']:
                        expected[s['key']]-=s['quantity']-s['remaining']
                actual={r['key']:r['quantity'] for r in context['goods'] or []}
                plan['cargo_changed']=context['goods'] is None or {k:v for k,v in expected.items() if v}!=actual
                plan['quotes_stale']=any(datetime.now(timezone.utc).timestamp()-(p.timestamp(m.get('observed_at')) or 0)>24*3600 for m in plan['stops'])
            result=copy.deepcopy(self.result) if self.result and self.result['context']['commander']==context['commander'] else None
            if result:
                result['cargo_changed']=result['context']['goods']!=context['goods']
            return dict(context=context,result=result,job=copy.deepcopy(self.job),plan=plan,
                        purchases=copy.deepcopy(self.purchases),save_error=self.save_error,
                        source='Spansh / EDDN',source_url='https://spansh.co.uk/stations')

    def commit(self, saved):
        """Route writes are synchronous; a failed write leaves the prior plan intact."""
        with self.io:
            self.core.write_data(saved,FILE)
        self.saved=saved;self.version+=1;self.written=self.version;self.save_error=None
        self.publish()

    def write_loop(self):
        while True:
            with self.lock:
                while self.written>=self.version and not self.stopping:
                    self.changed.wait()
                if self.stopping:
                    return
                version,snapshot=self.version,copy.deepcopy(self.saved)
                self.io.acquire()
            error=None
            try:
                self.core.write_data(snapshot,FILE)
            except OSError:
                error='Sale progress could not be saved. It remains in memory; check the data folder and retry.'
                self.core.log.exception('Could not save cargo sale progress')
            finally:
                self.io.release()
            with self.lock:
                if not error:
                    self.written=max(self.written,version)
                # A newer successful route write supersedes this older failure.
                self.save_error=error if self.written<self.version else None
                self.publish()
                if error and not self.stopping:
                    self.changed.wait(5)

    def flush(self):
        with self.lock:
            if self.written<self.version:
                with self.io:
                    self.core.write_data(self.saved,FILE)
                self.written=self.version;self.save_error=None

    def close(self):
        try:
            self.flush()
        finally:
            with self.lock:
                self.stopping=True;self.changed.notify_all()
            if self.writer:
                self.writer.join(timeout=2)

    def publish(self):
        self.core.store.update('selling',self.view())

    def search(self,q):
        if self.core.config.OFFLINE:
            raise ValueError('Buyer discovery is unavailable offline. Saved sale plans remain available.')
        context=self.context()
        if not context['commander'] or not context['system'] or context['goods'] is None:
            raise ValueError('Wait for a commander, location and complete cargo snapshot.')
        if not context['goods']:
            raise ValueError('No legal, unassigned cargo is aboard to sell.')
        if len(context['goods'])>64:
            raise ValueError('Search supports up to 64 different commodities per hold.')
        if not isinstance(context['pos'],list) or len(context['pos'])!=3 or not all(p.number(n,-100000,100000) for n in context['pos']):
            raise ValueError('Current system coordinates are unknown. Wait for a location report.')
        prefs={}
        for field,default,lo,hi in (('radius',80,1,500),('hours',24,1,72),('breadth',100,1,300),('arrival',10000,0,1000000)):
            try:
                value=float(q.get(field,default))
            except (ValueError,TypeError):
                raise ValueError(f'{field} must be a number from {lo} to {hi}.') from None
            if isinstance(q.get(field),bool) or not p.number(value,lo,hi) or (field=='breadth' and value!=int(value)):
                raise ValueError(f'{field} must be a number from {lo} to {hi}.')
            prefs[field]=int(value) if field=='breadth' else value
        prefs['pad']=q.get('pad','L');prefs['surface']=q.get('surface',False)
        if prefs['pad'] not in ('S','M','L') or type(prefs['surface']) is not bool:
            raise ValueError('Choose a pad size and true/false surface access.')
        with self.lock:
            if self.job and self.job['status']=='running':
                raise ValueError('A cargo buyer search is already running. Read get_cargo_sale_plan for its progress.')
            self.result=None;self.done.clear()
            self.job=dict(id=secrets.token_hex(8),status='running',error=None,checked=0,started_at=now())
            job=copy.deepcopy(self.job)
            self.publish()
        def run():
            try:
                result=self.scan(context,prefs)
                with self.lock:
                    if self.context()!=context:
                        raise ValueError('Commander, location or cargo changed during the search. Search again.')
                    self.result=result;self.job['status']='complete'
            except Exception as error:
                self.core.log.exception('Cargo buyer search failed')
                with self.lock:
                    self.job.update(status='failed',error=str(error) if isinstance(error,ValueError) else 'Market search failed. Check the local log and retry.')
            finally:
                with self.lock:
                    self.publish();self.done.set()
        try:
            threading.Thread(target=run,name='cargo-buyers',daemon=True).start()
        except Exception:
            with self.lock:
                self.job.update(status='failed',error='Could not start buyer search. Retry.');self.done.set();self.publish()
            raise
        return dict(job=job,status_tool='get_cargo_sale_plan',poll_after_seconds=2)

    def scan(self,context,prefs):
        clock=datetime.now(timezone.utc).timestamp()
        goods={r['key']:r for r in context['goods']}
        markets={};warnings=[];checked=0;total=0
        lower=datetime.fromtimestamp(math.floor(clock/300)*300-prefs['hours']*3600,timezone.utc).isoformat()
        upper=datetime.fromtimestamp(math.floor(clock/300)*300+300,timezone.utc).isoformat()
        filters={'distance':{'min':0,'max':prefs['radius']},'has_market':{'value':True},
                 'type':{'value':sorted(p.ORBITAL | (p.SURFACE if prefs['surface'] else set()))},
                 'market_updated_at':{'comparison':'<=>','value':[lower,upper]}}
        if prefs['pad']=='L':
            filters['has_large_pad']={'value':True}
        if prefs['arrival']:
            filters['distance_to_arrival']={'min':0,'max':prefs['arrival']}
        for page in range(math.ceil(prefs['breadth']/PAGE_SIZE)):
            size=min(PAGE_SIZE,prefs['breadth'])
            body=dict(reference_system=context['system'],size=size,page=page,
                filters=filters,sort=[{'distance':{'direction':'asc'}}])
            try:
                raw=self.core.services.fetch_json(STATIONS,body,ttl=300)
                if not isinstance(raw,dict) or not isinstance(raw.get('results'),list):
                    raise ValueError('Unexpected market response.')
            except Exception:
                if not checked:
                    raise ValueError('Spansh markets unavailable. Retry the buyer search.') from None
                warnings.append('Some market pages failed; results are partial.');break
            batch=raw['results'][:min(size,prefs['breadth']-checked)];checked+=len(batch)
            total=max(total,raw.get('count') if type(raw.get('count')) is int else checked)
            for record in batch:
                market=p.market(record,prefs,context['pos'],clock,goods)
                if market and (market['market_id'] not in markets or p.timestamp(market['observed_at'])>p.timestamp(markets[market['market_id']]['observed_at'])):
                    markets[market['market_id']]=market
            with self.lock:
                self.job['checked']=checked;self.publish()
            if len(batch)<size or checked>=total:
                break
        if checked<total:
            warnings.append(f'Checked {checked} of {total} reported stations. Increase breadth or change radius to compare more.')
        rows=list(markets.values())
        plans=[dict(id=secrets.token_hex(8),**p.allocate(context['goods'],rows,context['pos'],strategy)) for strategy in ('highest','nearby','one_stop')]
        buyers=[]
        for g in context['goods']:
            offers=[{k:v for k,v in m.items() if k!='offers'}|m['offers'][g['key']] for m in rows if g['key'] in m['offers']]
            offers.sort(key=lambda r:(-r['price'],r['distance']))
            buyers.append({**g,'buyers':offers[:5],'best_found':offers[0]['price'] if offers else None})
        return dict(context=context,checked_at=now(),settings=prefs,checked=checked,available=total,buyers=buyers,plans=plans,warnings=warnings,
                    scope='Nearby reported markets only; no galaxy-wide optimum. Quotes must pass age, distance, station and pad filters. Prohibited and unknown-demand offers are excluded; permit access remains unverified. Prices can change or incur bulk-sale reductions.')

    def select(self,q):
        with self.lock:
            result=self.result
            if not result or result['context']!=self.context():
                raise ValueError('Cargo or location changed. Search current buyers again before tracking a route.')
            if datetime.now(timezone.utc).timestamp()-p.timestamp(result['checked_at'])>1800:
                raise ValueError('Search is over 30 minutes old. Refresh buyers first.')
            plan=next((r for r in result['plans'] if r['id']==q.get('id')),None)
            if not plan or not plan['stops']:
                raise ValueError('Choose a sale plan with at least one buyer.')
            saved=copy.deepcopy(self.saved)
            saved[self.identity()]={**copy.deepcopy(plan),'selected_at':now(),'cargo':result['context']['goods'],
                                    'sold':{},'receipts':[],'commander':self.identity()}
            self.commit(saved)
            return self.view()

    def clear(self,q):
        with self.lock:
            saved=copy.deepcopy(self.saved);saved.pop(self.identity(),None)
            self.commit(saved)
            return self.view()

    def purchase(self,name,event):
        count,cost=event.get('Count'),event.get('TotalCost')
        if type(count) is int and count>0 and p.number(cost):
            ident=p.key(event.get('Type'))
            self.purchases[ident]=dict(price=cost/count,observed_at=event.get('timestamp'))
            self.publish()

    def reset_purchases(self,name,event):
        self.purchases.clear();self.publish()

    def sale(self,name,event):
        with self.lock:
            plan=self.saved.get(self.identity())
            if not plan or p.timestamp(event.get('timestamp')) is None or p.timestamp(event['timestamp'])<p.timestamp(plan['selected_at']):
                return
            count=event.get('Count');ident=p.key(event.get('Type'));market=event.get('MarketID')
            if type(count) is not int or count<=0:
                return
            receipt=hashlib.sha256(json.dumps({k:v for k,v in event.items() if not k.startswith('_')},sort_keys=True).encode()).hexdigest()
            if receipt in plan['receipts'] or len(plan['receipts'])>=2000:
                return
            planned=next((s for m in plan['stops'] if m['market_id']==market for s in m['sales'] if s['key']==ident),None)
            if not planned:
                return
            saved=copy.deepcopy(self.saved);current=saved[self.identity()];slot=str(market)+':'+ident
            current['sold'][slot]=min(planned['quantity'],current['sold'].get(slot,0)+count)
            # Never evict receipts: an old replay could otherwise count twice.
            current['receipts'].append(receipt)
            current['progress_limited']=len(current['receipts'])>=2000
            self.saved=saved;self.version+=1;self.publish()
            if self.writer is None:
                self.writer=threading.Thread(target=self.write_loop,name='cargo-sale-writer',daemon=True)
                self.writer.start()
            self.changed.notify_all()


def setup(core,module):
    desk=Selling(core);module.selling=desk
    core.http.route('/api/selling',desk.view,tool='get_cargo_sale_plan',module=module.name,
        description='Current cargo, background buyer-search status, best-found nearby quotes and saved multi-stop sale progress. Proceeds are estimates; net profit is unknown without acquisition costs. Mission and stolen cargo are excluded.')
    core.http.route('/api/selling/search',desk.search,tool='find_cargo_buyers',method='POST',module=module.name,
        description='Start a bounded nearby buyer search for legal unassigned cargo actually aboard. Returns immediately; poll get_cargo_sale_plan every 2 seconds for results/errors. Compares highest reported price, nearby stops and one-stop sale plans; no game actions.',
        params={'radius':dict(type='number',description='Ly from current system, default 80, maximum 500.'),
                'hours':dict(type='number',description='Maximum quote age in hours, default 24, maximum 72.'),
                'breadth':dict(type='integer',description='Stations to inspect, default 100, maximum 300.'),
                'arrival':dict(type='number',description='Maximum arrival Ls, default 10000; zero means no limit.'),
                'pad':dict(type='string',enum=['S','M','L'],description='Minimum pad, default L.'),
                'surface':dict(type='boolean',description='Include known surface stations, default false.')})
    core.http.route('/api/selling/select',desk.select,tool='select_cargo_sale_plan',method='POST',module=module.name,
        description='Track a sale plan ID from the latest buyer search. Rejects changed cargo/location and searches older than 30 minutes. Matching journal sales advance progress; never sells or plots in game.',
        params={'id':dict(type='string',required=True,description='Plan ID from get_cargo_sale_plan.result.plans.')})
    core.http.route('/api/selling/clear',desk.clear,tool='clear_cargo_sale_plan',method='POST',module=module.name,
        description='Remove only the current commander\'s saved cargo sale route. Does not change cargo or game orders.')
