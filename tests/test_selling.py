"""Cargo sale allocations and actual journal sale progress, without network."""
import copy
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from test_elitelab import Core,config,loader
from modules.selling import planning as p
from modules.selling.module import Selling


class SellingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.core=Core();self.addCleanup(self.core.close)
        self.core.data_path=lambda *parts:str(Path(temp.name).joinpath(*parts))
        self.core.store.update('journal',dict(cmdr='Trader',system='Sol',star_pos=[0,0,0],
            cargo=dict(count=30,items=[dict(key='gold',name='Gold',count=10,stolen=0),dict(key='silver',name='Silver',count=20,stolen=0)])))
        self.desk=Selling(self.core)
        self.clock=datetime.now(timezone.utc)
        self.markets=[self.market(1,10,100,50,5,10),self.market(2,30,90,80,10,20)]

    def market(self,ident,x,gold,silver,gold_demand=100,silver_demand=100):
        return dict(market_id=ident,name=f'Port {ident}',system_name=f'System {ident}',type='Orbis Starport',
                    has_market=True,has_large_pad=True,distance_to_arrival=100,system_x=x,system_y=0,system_z=0,
                    market_updated_at=self.clock.isoformat(),market=[dict(commodity='Gold',sell_price=gold,demand=gold_demand),
                    dict(commodity='Silver',sell_price=silver,demand=silver_demand)])

    def search(self,**params):
        with patch.object(config,'OFFLINE',False),patch.object(self.core.services,'fetch_json',return_value=dict(results=self.markets,count=len(self.markets))):
            self.desk.search(params)
            self.assertTrue(self.desk.done.wait(3))
        result=self.desk.view()
        self.assertEqual(result['job']['status'],'complete',result['job'])
        return result['result']

    def test_mixed_cargo_price_allocation_and_one_stop_are_demand_limited(self):
        result=self.search()
        best=next(r for r in result['plans'] if r['strategy']=='highest')
        one=next(r for r in result['plans'] if r['strategy']=='one_stop')
        self.assertEqual(best['estimated_proceeds'],5*100+5*90+20*80)
        self.assertEqual(best['sold_quantity'],30);self.assertEqual(len(best['stops']),2)
        self.assertEqual(best['distance'],30);self.assertEqual(best['unsold'],[])
        self.assertIsNone(best['net_profit'])
        self.assertEqual(one['estimated_proceeds'],10*90+20*80)
        self.assertEqual(len(one['stops']),1)
        for plan in result['plans']:
            for item in result['context']['goods']:
                allocated=sum(s['quantity'] for stop in plan['stops'] for s in stop['sales'] if s['key']==item['key'])
                missing=sum(s['quantity'] for s in plan['unsold'] if s['key']==item['key'])
                self.assertEqual(allocated+missing,item['quantity'])

    def test_unknown_zero_stale_far_and_inaccessible_quotes_are_excluded(self):
        for change in (dict(has_large_pad=False),dict(type='Fleet Carrier'),dict(system_x=90),
                       dict(market_updated_at=(self.clock-timedelta(days=2)).isoformat()),
                       dict(market_updated_at=(self.clock+timedelta(days=1)).isoformat()),dict(market='invalid')):
            with self.subTest(change=change):
                self.markets=[{**self.market(1,10,100,50),**change}]
                self.assertEqual(self.search()['plans'][0]['stops'],[])
        self.markets=[self.market(1,10,100,50,0,0)]
        self.assertEqual(self.search()['plans'][0]['stops'],[])
        self.markets[0]['market'][0]['consumer']=True
        self.assertEqual(self.search()['plans'][0]['sold_quantity'],10)

    def test_cargo_rejects_partial_snapshot_and_excludes_mission_and_stolen(self):
        j=self.core.store.get('journal')
        j['cargo']['items'][0]['stolen']=3
        j['cargo']['items'][1]['mission_id']=123
        goods,excluded=p.cargo(j)
        self.assertEqual(goods,[dict(key='gold',name='Gold',quantity=7)])
        self.assertEqual(sum(r['quantity'] for r in excluded),23)
        j['cargo']['count']=99
        self.assertIsNone(p.cargo(j)[0])

    def test_journal_fixture_preserves_mission_identity_for_exclusion(self):
        loader.load_all(self.core)
        event=json.loads((Path(__file__).parent/'fixtures'/'selling'/'Cargo.json').read_text())
        self.core.bus.emit('journal.file.Cargo',event)
        goods,excluded=p.cargo(self.core.store.get('journal'))
        self.assertEqual(goods,[dict(key='gold',name='gold',quantity=7)])
        self.assertEqual(sum(r['quantity'] for r in excluded),23)

    def test_receipt_write_is_off_bus_and_limit_keeps_old_deduplication(self):
        result=self.search();self.desk.select({'id':result['plans'][0]['id']})
        threads=[];entered=threading.Event();release=threading.Event();original=self.core.write_data
        def delayed(*args):
            threads.append(threading.current_thread());entered.set()
            if not release.wait(3):raise OSError('fixture not released')
            return original(*args)
        event=dict(event='MarketSell',timestamp=datetime.now(timezone.utc).isoformat(),MarketID=1,Type='gold',Count=1)
        try:
            with patch.object(self.core,'write_data',side_effect=delayed):
                self.desk.sale('',event)
                self.assertTrue(entered.wait(1))
                self.assertNotIn(threading.current_thread(),threads)
                release.set();self.desk.flush()
        finally:
            release.set()
        with self.desk.lock:
            plan=self.desk.saved[self.desk.identity()]
            plan['receipts']+=['fixture-'+str(n) for n in range(1999)]
            self.desk.sale('',{**event,'Count':2})
            self.desk.sale('',event)
            self.assertEqual(plan['sold']['1:gold'],1)
            self.assertEqual(len(plan['receipts']),2000)

    def test_save_rejects_changed_cargo_and_persists_sales_without_double_counting(self):
        result=self.search();ident=result['plans'][0]['id']
        original=self.core.store.get('journal','cargo')
        self.core.store.set('journal','cargo',dict(count=0,items=[]))
        with self.assertRaisesRegex(ValueError,'changed'):
            self.desk.select({'id':ident})
        self.core.store.set('journal','cargo',original)
        self.desk.select({'id':ident})
        event=dict(event='MarketSell',timestamp=datetime.now(timezone.utc).isoformat(),MarketID=1,Type='gold',Count=3,TotalSale=300)
        self.desk.sale('',event);self.desk.sale('',{**event,'_replay':True})
        plan=self.desk.view()['plan']
        self.assertEqual(plan['sold']['1:gold'],3)
        self.assertEqual(plan['stops'][0]['sales'][0]['remaining'],2)
        self.desk.flush()
        reloaded=Selling(self.core)
        self.assertEqual(reloaded.view()['plan']['sold'],plan['sold'])
        self.core.store.set('journal','cmdr','Someone else')
        self.assertIsNone(reloaded.view()['plan'])

    def test_partial_provider_failure_and_duplicate_stations_never_double_demand(self):
        original=self.market(1,10,100,50,2,3)
        self.markets=[original,copy.deepcopy(original)]
        self.assertEqual(self.search()['plans'][0]['sold_quantity'],5)
        first=dict(results=[{**original,'market_id':n+1} for n in range(25)],count=200)
        with patch.object(config,'OFFLINE',False),patch.object(self.core.services,'fetch_json',side_effect=[first,OSError('offline')]):
            self.desk.search({'breadth':200});self.assertTrue(self.desk.done.wait(3))
        result=self.desk.view()['result']
        self.assertIn('partial',' '.join(result['warnings']))
        self.assertEqual(result['checked'],25)

    def test_small_pages_preserve_offsets_and_total_breadth(self):
        calls=[]
        def fetch(url,body,**kwargs):
            calls.append((body['page'],body['size']))
            offset=body['page']*body['size']
            return dict(count=80,results=[self.market(n+1,10,100,50) for n in range(offset,offset+body['size'])])
        with patch.object(config,'OFFLINE',False),patch.object(self.core.services,'fetch_json',side_effect=fetch):
            self.desk.search({'breadth':30});self.assertTrue(self.desk.done.wait(3))
        self.assertEqual(calls,[(0,25),(1,25)])
        self.assertEqual(self.desk.view()['result']['checked'],30)

    def test_invalid_search_and_failed_persistence_leave_plan_intact(self):
        result=self.search();self.desk.select({'id':result['plans'][0]['id']})
        saved=copy.deepcopy(self.desk.saved)
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.desk.clear({})
        self.assertEqual(self.desk.saved,saved)
        with patch.object(config,'OFFLINE',False):
            for q in ({'radius':float('nan')},{'radius':True},{'breadth':301},{'surface':'yes'},{'pad':'XL'}):
                with self.subTest(q=q),self.assertRaises(ValueError):self.desk.search(q)
