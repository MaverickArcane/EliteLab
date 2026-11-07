"""PTN economic guarantees, market evidence and independent operation persistence."""
import copy
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timedelta, timezone
import random
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_elitelab import Core, config, loader
from modules.ptn.planning import DEFAULTS as CURRENT_DEFAULTS, advert, pricing, settings, paid_leg

# Preserve the original explicit preferences in the existing workflow regressions.
# New-default and mixed-hauling coverage below uses CURRENT_DEFAULTS directly.
DEFAULTS = {**CURRENT_DEFAULTS,'loading_floor':20000,'unloading_floor':20000,'owner_floor':2500,
            'hours':6,'arrival':2000,'skip_common':True,'avoid_active':True,'allow_partial':False,
            'radius':450,'max_hop':450,'breadth':32,'share_surplus':True}


class PricingTests(unittest.TestCase):
    def test_whole_percent_prices_preserve_floors_and_conserve_every_credit(self):
        rng = random.Random(5)
        for _ in range(120):
            mean = rng.randint(100,100000)
            buy = rng.randint(10,20000)
            sell = buy+rng.randint(45000,150000)
            r = pricing(buy,sell,18000,mean,DEFAULTS)
            if r['settings_valid']:
                self.assertGreaterEqual(r['loading_per_ton'],DEFAULTS['loading_floor'])
                self.assertGreaterEqual(r['unloading_per_ton'],DEFAULTS['unloading_floor'])
                self.assertGreaterEqual(r['owner_per_ton'],DEFAULTS['owner_floor'])
                self.assertEqual(r['hauler_total']+r['owner_total'],r['gross_total'])
                self.assertEqual(r['carrier_buy'],(mean*r['buy_percent']+50)//100)
                self.assertEqual(r['carrier_sell'],(mean*r['sell_percent']+50)//100)

    def test_absent_reference_and_impossible_price_range_are_not_valid_settings(self):
        self.assertFalse(pricing(100,100000,18000,None,DEFAULTS)['settings_valid'])
        self.assertFalse(pricing(100,100000,18000,1,DEFAULTS)['settings_valid'])
        self.assertFalse(pricing(100,20000,18000,10000,DEFAULTS)['settings_valid'])

    def test_surplus_mode_maximizes_weaker_hauler_payout_and_can_be_disabled(self):
        shared=pricing(4000,75000,18000,10000,DEFAULTS)
        retained=pricing(4000,75000,18000,10000,{**DEFAULTS,'share_surplus':False})
        self.assertEqual((shared['loading_per_ton'],shared['unloading_per_ton']),(34200,34300))
        self.assertEqual(shared['owner_per_ton'],2500)
        self.assertEqual((retained['loading_per_ton'],retained['unloading_per_ton']),(20000,20000))
        self.assertEqual(retained['owner_after_reserve'],553000000)
        asymmetric=pricing(4000,75000,18000,10000,{**DEFAULTS,'unloading_floor':40000})
        self.assertGreaterEqual(asymmetric['unloading_per_ton'],40000)
        self.assertGreaterEqual(asymmetric['loading_per_ton'],20000)
        self.assertGreaterEqual(asymmetric['owner_per_ton'],2500)

    def test_exact_affiliate_markdown_no_rounding_up_and_no_mentions(self):
        text = advert('N.A.C. TEST','K9T-GVT','Liquor','Port','System','loading',20047,18001)
        self.assertEqual(text,'**N.A.C. TEST (K9T-GVT)** is loading **Liquor** from **Port** (L pads) in **System**. 20.047k/unit profit, 18.001k units')
        self.assertIn('is unloading **Liquor** to **Port**',advert('Test','K9T-GVT','Liquor','Port','System','unloading',20000,18000))
        with self.assertRaises(ValueError):
            advert('@everyone','K9T-GVT','Liquor','Port','System','loading',20000,18000)
        with self.assertRaises(ValueError):
            advert('Test\nAnother line','K9T-GVT','Liquor','Port','System','loading',20000,18000)

    def test_settings_reject_invalid_and_unbounded_inputs(self):
        for query in ({'quantity':True},{'radius':float('nan')},{'max_hop':2501},{'hours':25},
                      {'loading_floor':0},{'breadth':501},{'breadth':-1},{'cost_reserve':-1},{'avoid_active':'maybe'},
                      {'allow_surface_loading':'maybe'}):
            with self.subTest(query=query),self.assertRaises(ValueError):
                settings(query)


class PTNTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='elitelab-ptn-test-')
        self.addCleanup(temp.cleanup)
        self.data_dir = temp.name
        for name,value in [('DATA_DIR',temp.name),('OFFLINE',False)]:
            p = patch.object(config,name,value);p.start();self.addCleanup(p.stop)
        self.core = Core();self.addCleanup(self.core.close)
        self.buy = dict(commodityName='liquor',marketId=101,stationName='Buy Port',systemName='Source',stationType='Orbis',
                       systemX=20,systemY=0,systemZ=0,maxLandingPadSize=3,distanceToArrival=100,
                       buyPrice=4000,sellPrice=3900,stock=500000,demand=10,meanPrice=10000,
                       bodyName='Source A 2',bodyId=2,updatedAt=self.time())
        self.sell = {**self.buy,'marketId':202,'stationName':'Sell Port','systemName':'Buyer','systemX':200,
                     'sellPrice':75000,'buyPrice':0,'demand':200000,'bodyName':'Buyer A 3'}
        self.board = dict(last_updated=self.time(),missions=[dict(mission_type='load',commodity='Gold',
            system='Elsewhere',station='Station',carrier_name='P.T.N. Test',carrier_identifier='ABC-123',profit=30,demand='18.0')])
        self.fetch_patch = patch.object(self.core.services,'fetch_json',side_effect=self.fetch)
        self.fetch_patch.start();self.addCleanup(self.fetch_patch.stop)
        loader.load_all(self.core)
        self.desk = self.core.modules['ptn'].ptn
        self.core.store.update('journal',{'cmdr':'Fixture Pilot','system':'Sol','star_pos':[0,0,0],
            'carrier':{'name':'N.A.C. Test','callsign':'TST-001','system':'Sol','free_space':25000,'reserved_space':0,
                       'balance':2000000000,'stats_time':self.time()},'docked':False})

    @staticmethod
    def time(hours=0):
        return (datetime.now(timezone.utc)+timedelta(hours=hours)).isoformat().replace('+00:00','Z')

    def fetch(self,url,*args,**kwargs):
        if url.endswith('/missions'):return copy.deepcopy(self.board)
        if url.endswith('/commodities'):
            return [dict(commodityName=name,totalStock=500000,minBuyPrice=4000,maxSellPrice=75000)
                    for name in ('liquor','gold','silver','agronomictreatment')]
        if '/exports?' in url or '/imports?' in url:
            if '/commodity/name/liquor/' not in url:return []
            return [copy.deepcopy(self.buy if '/exports?' in url else self.sell)]
        raise RuntimeError('PTN fixture blocks unrelated provider requests')

    def call(self,name,**q):
        return self.core.http.tools[name].fn(q)

    def scan(self,**q):
        return self.call('find_ptn_routes',**{**DEFAULTS,**q})

    def choose(self):
        r = self.scan()['rows'][0]
        return self.call('select_ptn_route',revision=self.desk.data['revision'],id=r['id'])

    def mutate(self,action,**q):
        return self.call('update_ptn_plan',revision=self.desk.data['revision'],action=action,**q)

    def capture(self,side):
        target = self.buy if side=='buy' else self.sell
        ts = self.time()
        self.desk.dock_event('journal.Docked',{'timestamp':ts})
        self.core.store.update('journal',dict(docked=True,system=target['systemName'],station=target['stationName'],station_type=target['stationType']))
        self.core.bus.emit('journal.file.Market',dict(timestamp=self.time(),MarketID=target['marketId'],
            StationName=target['stationName'],StarSystem=target['systemName'],Items=[dict(Name='$liquor_name;',Name_Localised='Liquor',
                BuyPrice=target['buyPrice'],SellPrice=target['sellPrice'],Stock=target['stock'],Demand=target['demand'],MeanPrice=10000)]))
        return self.call('capture_ptn_market',revision=self.desk.data['revision'],side=side)

    def scout(self):
        self.choose();self.capture('buy');return self.capture('sell')

    def carrier(self,**values):
        c = self.core.store.get('journal','carrier');self.core.store.set('journal','carrier',{**c,**values})

    def confirmed(self):
        self.scout();self.mutate('stage',stage='loading');self.carrier(system='Source')
        return self.mutate('confirm',price=24000,remaining=18000,
                           checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})

    def test_explicit_niche_preferences_orbital_filters_and_both_end_radius(self):
        r = self.scan()
        self.assertEqual([row['commodity'] for row in r['rows']],['liquor'])
        self.assertTrue(r['rows'][0]['viable'])
        self.assertEqual(r['rows'][0]['pricing']['owner_after_reserve'],40000000)
        self.assertGreaterEqual(r['rows'][0]['pricing']['loading_per_ton'],34000)
        self.assertGreaterEqual(r['rows'][0]['pricing']['unloading_per_ton'],34000)
        self.assertEqual(self.core.store.get('ptn')['result']['scanned'],1)
        for changes in ({'stationType':'CraterOutpost'},{'maxLandingPadSize':2},{'stationType':'Unknown'},
                        {'isPlanetary':True},{'systemX':501},{'updatedAt':self.time(-7)},
                        {'distanceToArrival':None},{'distanceToArrival':3000},{'demand':0}):
            old = self.sell;self.sell = {**old,**changes}
            self.assertEqual(self.scan()['rows'],[],changes)
            self.sell = old
        self.sell['updatedAt']=self.time(1)
        self.assertEqual(self.scan()['rows'],[])

    def test_no_floor_relaxation_near_misses_and_missing_reference(self):
        self.sell['sellPrice']=30000
        r = self.scan()['rows'][0]
        self.assertFalse(r['viable']);self.assertGreater(r['pricing']['spread_short'],0)
        self.sell['sellPrice']=75000
        self.buy['meanPrice']=self.sell['meanPrice']=None
        self.assertFalse(self.scan()['rows'][0]['viable'])

    def test_surface_loading_is_opt_in_and_hidden_sources_are_profitable(self):
        self.buy.update(stationType='CraterOutpost',isPlanetary=True)
        result = self.scan()
        self.assertEqual(result['rows'],[])
        self.assertEqual(result['surface_excluded'],dict(count=1,examples=[dict(
            commodity='Liquor',station='Buy Port',system='Source')]))
        row = self.scan(allow_surface_loading=True)['rows'][0]
        self.assertTrue(row['buy']['surface'])
        self.assertFalse(row['sell']['surface'])
        self.assertTrue(row['viable'])
        self.sell['sellPrice']=30000
        self.assertEqual(self.scan()['surface_excluded']['count'],0)
        self.sell['sellPrice']=75000
        self.buy['meanPrice']=self.sell['meanPrice']=None
        self.assertEqual(self.scan()['surface_excluded']['count'],0)

    def test_surface_filter_preserves_pad_age_volume_and_station_safety_checks(self):
        self.buy.update(stationType='CraterPort',isPlanetary=True)
        original = copy.deepcopy(self.buy)
        for changes in ({'maxLandingPadSize':2},{'stationType':'Unknown'},{'stationType':'FleetCarrier'},
                        {'stationType':['CraterPort']},{'isProhibited':True},{'isRare':True},
                        {'stock':100},{'updatedAt':self.time(-7)},{'systemX':501},{'distanceToArrival':None}):
            with self.subTest(changes=changes):
                self.buy = {**original,**changes}
                result = self.scan(allow_surface_loading=True)
                self.assertEqual(result['rows'],[])
                self.assertEqual(result['surface_excluded']['count'],0)
        self.buy = original
        self.sell['stationType']='CraterPort'
        self.assertEqual(self.scan(allow_surface_loading=True)['rows'],[])

    def test_surface_scout_and_advert_and_asymmetric_public_payouts(self):
        self.buy['stationType']='OnFootSettlement'
        row = self.scan(allow_surface_loading=True,loading_floor=30000,unloading_floor=20000,share_surplus=False)['rows'][0]
        self.assertEqual(row['pricing']['loading_per_ton'],30000)
        self.assertEqual(row['pricing']['unloading_per_ton'],20000)
        self.assertEqual(row['pricing']['owner_after_reserve'],373000000)
        self.call('select_ptn_route',revision=self.desk.data['revision'],id=row['id'])
        state = self.capture('buy')
        self.assertTrue(state['plan']['scouts']['buy']['surface'])
        self.core.store.set('journal','station_type','Orbis')
        with self.assertRaisesRegex(ValueError,'Dock'):
            self.call('capture_ptn_market',revision=self.desk.data['revision'],side='buy')
        self.capture('sell');self.mutate('stage',stage='loading');self.carrier(system='Source')
        self.mutate('confirm',price=34000,remaining=18000,
                    checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        result = self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.assertIn('30k/unit profit, 18k units',result['advert'])
        self.assertEqual(result['notes'],'Odyssey surface port. SCO FSD recommended.')
        self.assertEqual(result['copy_text'].count('\n'),1)

    def test_legacy_orbital_plan_cannot_capture_a_surface_market(self):
        self.choose()
        self.desk.data['plan']['route']['settings'].pop('allow_surface_loading',None)
        self.buy['stationType']='CraterPort'
        with self.assertRaisesRegex(ValueError,'Dock'):
            self.capture('buy')

    def test_hidden_sources_are_deduplicated_and_do_not_displace_orbital_choices(self):
        fetch = self.fetch
        def many_sources(url,*args,**kwargs):
            reports = fetch(url,*args,**kwargs)
            if reports and '/exports?' in url:
                return [{**self.buy,'marketId':500+i,'buyPrice':3000,'stationType':'CraterPort'} for i in range(20)]+reports
            if reports and '/imports?' in url:
                return reports+[{**self.sell,'marketId':203,'sellPrice':74000}]
            return reports
        with patch.object(self.core.services,'fetch_json',side_effect=many_sources):
            result = self.scan()
        self.assertEqual(len(result['rows']),2)
        self.assertTrue(all(not r['buy']['surface'] for r in result['rows']))
        self.assertEqual(result['surface_excluded']['count'],20)
        self.assertEqual(len(result['surface_excluded']['examples']),3)

    def test_board_exclusion_benchmark_unknown_and_stale(self):
        self.board['missions'][0]['commodity']='Liquor'
        self.assertEqual(self.scan()['rows'],[])
        self.assertEqual(self.scan(avoid_active=False)['rows'][0]['official_competitors'],0)
        self.assertEqual(self.desk.board['benchmarks']['loading'],30000)
        self.board['last_updated']=self.time(-1)
        row = self.scan()['rows'][0]
        self.assertIsNone(row['official_competitors'])
        self.assertFalse(self.desk.board['available'])

    def test_station_competition_and_supply_buffer(self):
        self.board['missions'][0].update(commodity='Liquor',station='Buy Port',system='Source')
        self.buy['stock']=30000
        row = self.scan(avoid_active=False)['rows'][0]
        self.assertEqual(row['official_competitors'],1)
        self.assertFalse(row['viable'])

    def test_select_and_cancel_do_not_mutate_existing_trade(self):
        self.core.store.update('trade',{'plan':{'commodity':'silver'},'operation':{'stage':'cancelled'}})
        before = self.core.store.get('trade')
        self.choose();self.mutate('stage',stage='cancelled')
        self.assertEqual(before,self.core.store.get('trade'))

    def test_scout_capture_requires_current_station_and_snapshot_and_does_not_invent_prices(self):
        self.choose()
        with self.assertRaisesRegex(ValueError,'Dock'):
            self.call('capture_ptn_market',revision=self.desk.data['revision'],side='buy')
        state = self.capture('buy')
        self.assertEqual(state['plan']['scouts']['buy']['source'],'Local market journal')
        self.assertEqual(state['plan']['name'],'Liquor')
        self.desk.docked_at=datetime.now(timezone.utc).timestamp()+1
        with self.assertRaisesRegex(ValueError,'Dock'):
            self.call('capture_ptn_market',revision=self.desk.data['revision'],side='buy')

    def test_scouts_and_price_checks_gate_advert_on_server(self):
        self.choose()
        with self.assertRaisesRegex(ValueError,'Scout'):
            self.mutate('stage',stage='loading')
        state = self.confirmed()
        self.assertTrue(state['operation']['ready'])
        result = self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.assertIn('**N.A.C. Test (TST-001)** is loading **Liquor**',result['advert'])
        self.assertTrue(result['copy_text'].endswith('\nSCO FSD recommended.'))
        self.assertEqual(result['profit_per_ton'],20000)
        self.assertEqual(result['remaining'],18000)
        self.mutate('confirm',price=23999,remaining=18000,checks=state['operation']['checks'])
        with self.assertRaisesRegex(ValueError,'underpays'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])

    def test_other_carrier_orders_do_not_count_as_free_space_but_this_confirmed_order_does(self):
        self.confirmed();self.carrier(free_space=0,reserved_space=18000)
        self.assertFalse(self.desk.view()['operation']['ready'])
        self.core.store.set('trade','orders',{'liquor':dict(side='buy',price=24000,quantity=18000,updated_at=self.time())})
        self.assertTrue(self.desk.view()['operation']['ready'])
        self.core.store.set('trade','orders',{'silver':dict(side='buy',price=24000,quantity=18000,updated_at=self.time())})
        self.assertFalse(self.desk.view()['operation']['ready'])

    def test_unloading_retains_real_loading_cost_and_does_not_require_loading_station_revisit(self):
        state = self.confirmed()
        self.mutate('confirm',price=25000,remaining=0,checks=state['operation']['checks'])
        self.mutate('stage',stage='transit');self.mutate('stage',stage='unloading');self.carrier(system='Buyer')
        self.desk.data['plan']['scouts']['buy']['observed_at']=self.time(-12)
        self.desk.data['plan']['scouts']['buy']['volume']=0
        state = self.mutate('confirm',price=55000,remaining=5000,checks=state['operation']['checks'])
        self.assertTrue(state['operation']['ready'])
        costs=state['operation']['pricing']
        self.assertEqual(costs['owner_per_ton'],30000)
        self.assertEqual(costs['hauler_total']+costs['owner_total'],costs['gross_total'])
        result = self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.assertIn('is unloading **Liquor** to **Sell Port**',result['advert'])
        self.assertIn('5k units',result['advert'])
        with self.assertRaisesRegex(ValueError,'zero'):
            self.mutate('stage',stage='complete')
        self.mutate('remaining',remaining=0)
        self.assertEqual(self.mutate('stage',stage='complete')['plan']['stage'],'complete')

    def test_remaining_volume_is_used_for_partial_order(self):
        state = self.confirmed()
        self.mutate('confirm',price=24000,remaining=5000,checks=state['operation']['checks'])
        self.desk.data['plan']['scouts']['buy']['volume']=6000
        self.assertTrue(self.desk.view()['operation']['ready'])

    def test_scout_and_order_expiry_are_rechecked_at_advert_time(self):
        self.confirmed()
        self.desk.data['plan']['orders']['loading']['checked_at']=self.time(-2)
        with self.assertRaisesRegex(ValueError,'hour old'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.desk.data['plan']['scouts']['sell']['observed_at']=self.time(-7)
        with self.assertRaisesRegex(ValueError,'expired'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])

    def test_stale_carrier_stats_block_capacity_claim_until_management_is_refreshed(self):
        self.confirmed();self.carrier(stats_time=self.time(-2))
        with self.assertRaisesRegex(ValueError,'Carrier Management'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.carrier(stats_time=self.time())
        self.assertTrue(self.desk.view()['operation']['ready'])

    def test_atomic_save_stale_revision_owner_scope_and_persistence(self):
        self.choose();before=copy.deepcopy(self.desk.data)
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.mutate('stage',stage='cancelled')
        self.assertEqual(self.desk.data,before)
        with self.assertRaisesRegex(ValueError,'changed'):
            self.call('update_ptn_plan',revision=0,action='stage',stage='cancelled')
        self.core.store.set('party','mode','member')
        with self.assertRaisesRegex(ValueError,'owner'):
            self.mutate('stage',stage='cancelled')
        self.core.store.set('party','mode','solo')
        self.core.store.set('journal','cmdr','Other pilot')
        with self.assertRaisesRegex(ValueError,'commander'):
            self.mutate('stage',stage='cancelled')
        reloaded=type(self.desk)(self.core)
        self.assertEqual(reloaded.data['plan'],before['plan'])

    def test_manual_post_confirmation_and_expiry_do_not_send_anything(self):
        self.confirmed()
        with patch.object(self.core.services,'fetch_json',side_effect=AssertionError('no posting')):
            state=self.mutate('posted',link='https://discord.com/channels/1/2/3')
        self.assertIsNotNone(state['operation']['posted'])
        self.desk.data['plan']['posted']['loading']['at']=self.time(-49)
        self.assertTrue(self.desk.view()['operation']['advert_expired'])

    def test_newer_journal_order_updates_advert_quantity_and_changed_price_blocks_copy(self):
        self.confirmed()
        self.core.store.set('trade','orders',{'liquor':dict(side='buy',price=24000,quantity=12000,updated_at=self.time(0.001))})
        result=self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.assertEqual(result['remaining'],12000)
        self.assertIn('12k units',result['advert'])
        self.core.store.set('trade','orders',{'liquor':dict(side='buy',price=23000,quantity=12000,updated_at=self.time(0.001))})
        with self.assertRaisesRegex(ValueError,'newer journal order'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])

    def test_no_network_at_startup_or_view_and_offline_search_has_actionable_error(self):
        with patch.object(self.core.services,'fetch_json',side_effect=AssertionError('no network')):
            self.desk.view();self.desk.publish()
        with patch.object(config,'OFFLINE',True),self.assertRaisesRegex(ValueError,'offline'):
            self.scan()

    def test_normal_defaults_keep_surplus_without_requiring_preferred_target(self):
        self.sell['sellPrice']=50000
        r=self.call('find_ptn_routes',payout_target=30000)['rows'][0]
        self.assertTrue(r['viable'])
        self.assertFalse(r['pricing']['meets_target'])
        self.assertGreaterEqual(r['pricing']['loading_per_ton'],20000)
        self.assertEqual(r['pricing']['owner_after_reserve'],103000000)
        self.assertFalse(r['settings']['share_surplus'])
        self.assertFalse(r['settings']['skip_common'])
        self.assertFalse(r['settings']['avoid_active'])

    def test_nearby_search_does_not_lose_stations_after_first_100_reports(self):
        original=self.fetch
        def fetch(url,*a,**kw):
            if '/nearby/exports?' in url:
                return [{**self.buy,'marketId':500+i,'stationType':'CraterPort'} for i in range(100)]+[self.buy]
            return original(url,*a,**kw)
        with patch.object(self.core.services,'fetch_json',side_effect=fetch) as fetcher:
            self.assertTrue(self.call('find_ptn_routes')['rows'][0]['viable'])
        urls=[c.args[0] for c in fetcher.call_args_list if '/exports?' in c.args[0] and '/commodity/name/' in c.args[0]]
        nearby=[url for url in urls if '/nearby/' in url]
        self.assertTrue(nearby)
        self.assertTrue(all('/system/name/Sol/commodity/name/' in url for url in nearby))
        self.assertTrue(all('maxDistance=500' in url and 'minVolume=2000' in url for url in nearby))
        self.assertTrue(all('maxDaysAgo=2' in url for url in urls))
        self.assertTrue(any('/nearby/' not in url for url in urls))

    def test_all_commodities_includes_stale_catalog_stock_and_low_ranked_spread(self):
        original = self.fetch
        def catalog(url,*args,**kwargs):
            if url.endswith('/commodities'):
                return [dict(commodityName='fixture'+str(i),totalStock=500000,minBuyPrice=1,maxSellPrice=999999)
                        for i in range(65)]+[dict(commodityName='liquor',totalStock=0,minBuyPrice=None,maxSellPrice=None)]
            return original(url,*args,**kwargs)
        with patch.object(self.core.services,'fetch_json',side_effect=catalog):
            result = self.call('find_ptn_routes')
            self.assertEqual(result['scanned'],66)
            self.assertTrue(result['coverage']['all_commodities'])
            self.assertEqual(result['rows'][0]['commodity'],'liquor')
            limited = self.call('find_ptn_routes',breadth=3)
            self.assertEqual(limited['scanned'],3)
            self.assertEqual(limited['available'],66)
            self.assertFalse(limited['coverage']['all_commodities'])

    def test_multijump_sources_and_buyers_are_measured_on_separate_legs(self):
        self.buy['systemX']=1200
        self.sell['systemX']=2600
        original = self.fetch
        def nearby_limits(url,*args,**kwargs):
            rows = original(url,*args,**kwargs)
            if '/nearby/' in url:
                return [r for r in rows if r['systemX']<=500]
            return rows
        with patch.object(self.core.services,'fetch_json',side_effect=nearby_limits) as fetcher:
            result = self.call('find_ptn_routes')
            row = result['rows'][0]
            self.assertEqual((row['approach_jumps'],row['trade_jumps']),(3,3))
            self.assertEqual((row['approach_distance'],row['route_distance']),(1200,1400))
            self.assertTrue(row['viable'])
            self.assertEqual(self.call('find_ptn_routes',radius=1000)['rows'],[])
            self.assertEqual(self.call('find_ptn_routes',max_hop=1000)['rows'],[])
        nearby = [c.args[0] for c in fetcher.call_args_list if '/nearby/' in c.args[0]]
        self.assertTrue(all('maxDistance=500' in url for url in nearby))

    def test_start_to_source_and_source_to_buyer_boundaries_are_inclusive(self):
        self.buy['systemX']=500
        self.sell['systemX']=1000
        row = self.call('find_ptn_routes',radius=500,max_hop=500)['rows'][0]
        self.assertEqual((row['approach_jumps'],row['trade_jumps']),(1,1))
        self.sell['systemX']=1000.01
        self.assertEqual(self.call('find_ptn_routes',radius=500,max_hop=500)['rows'],[])
        self.buy['systemX']=500.01
        self.sell['systemX']=900
        self.assertEqual(self.call('find_ptn_routes',radius=500,max_hop=500)['rows'],[])

    def test_deep_system_stations_are_allowed_by_default_and_approach_filter_is_explicit(self):
        self.buy['distanceToArrival']=33879
        self.sell['distanceToArrival']=145885
        self.assertTrue(self.call('find_ptn_routes')['rows'][0]['viable'])
        self.assertEqual(self.call('find_ptn_routes',arrival=10000)['rows'],[])
        for arrival in (None,-1,True,float('inf')):
            self.buy['distanceToArrival']=arrival
            self.assertEqual(self.call('find_ptn_routes')['rows'],[])

    def test_alternative_loading_sources_are_not_displaced_by_one_sources_many_buyers(self):
        original = self.fetch
        def alternatives(url,*args,**kwargs):
            rows = original(url,*args,**kwargs)
            if '/commodity/name/liquor/' in url and '/exports?' in url:
                return rows+[{**self.buy,'marketId':303,'stationName':'Other Source','buyPrice':4500}]
            if '/commodity/name/liquor/' in url and '/imports?' in url:
                return [{**self.sell,'marketId':1000+i,'sellPrice':75000-i} for i in range(10)]
            return rows
        with patch.object(self.core.services,'fetch_json',side_effect=alternatives):
            rows = self.call('find_ptn_routes')['rows']
        self.assertEqual(len(rows),6)
        self.assertEqual({row['buy']['market_id'] for row in rows},{101,303})
        self.assertEqual(rows[0]['buy']['market_id'],101)

    def test_current_system_sources_are_included_when_nearby_omits_them(self):
        self.buy.update(systemName='Sol',systemX=0)
        original = self.fetch
        def local_only(url,*args,**kwargs):
            if '/system/name/Sol/commodities/exports?' in url:
                return [copy.deepcopy(self.buy)]
            if '/commodity/name/liquor/' in url and '/exports?' in url:
                return []
            return original(url,*args,**kwargs)
        with patch.object(self.core.services,'fetch_json',side_effect=local_only):
            result = self.call('find_ptn_routes',radius=500,max_hop=500)
        row = result['rows'][0]
        self.assertTrue(row['viable'])
        self.assertEqual(row['approach_jumps'],0)
        self.assertEqual(row['buy']['system'],'Sol')
        self.assertTrue(result['coverage']['current_system_complete'])

    def test_current_system_failure_is_explicit_and_other_sources_remain(self):
        original = self.fetch
        def missing_local(url,*args,**kwargs):
            if '/commodities/' in url:
                raise RuntimeError('provider secret')
            return original(url,*args,**kwargs)
        with patch.object(self.core.services,'fetch_json',side_effect=missing_local):
            result = self.call('find_ptn_routes')
        self.assertTrue(result['rows'][0]['viable'])
        self.assertFalse(result['coverage']['current_system_complete'])
        self.assertFalse(result['coverage']['all_commodities'])
        self.assertIn('Current-system',' '.join(result['warnings']))
        self.assertNotIn('provider secret',' '.join(result['warnings']))

    def test_carrier_return_ranks_above_excess_supply_buffer(self):
        original = self.fetch
        self.buy['stock']=20000
        def extra_source(url,*args,**kwargs):
            rows = original(url,*args,**kwargs)
            if '/commodity/name/liquor/' in url and '/exports?' in url:
                rows.append({**self.buy,'marketId':303,'buyPrice':14000,'stock':500000})
            return rows
        with patch.object(self.core.services,'fetch_json',side_effect=extra_source):
            result = self.call('find_ptn_routes')
        self.assertEqual(result['rows'][0]['buy']['market_id'],101)
        self.assertGreater(result['rows'][0]['pricing']['owner_after_reserve'],result['rows'][1]['pricing']['owner_after_reserve'])

    def test_failed_global_feed_keeps_local_results_and_reports_incomplete_coverage(self):
        original = self.fetch
        def fail_global(url,*args,**kwargs):
            if '/commodity/name/' in url and '/nearby/' not in url:
                raise RuntimeError('provider secret')
            return original(url,*args,**kwargs)
        with patch.object(self.core.services,'fetch_json',side_effect=fail_global):
            result = self.call('find_ptn_routes')
        self.assertTrue(result['rows'][0]['viable'])
        self.assertEqual(result['scanned'],4)
        self.assertEqual(result['coverage']['completed'],0)
        self.assertFalse(result['coverage']['all_commodities'])
        self.assertNotIn('provider secret',' '.join(result['warnings']))

    def test_newest_global_quote_cannot_revive_exhausted_local_stock(self):
        original = self.fetch
        def depleted(url,*args,**kwargs):
            rows = original(url,*args,**kwargs)
            if '/commodity/name/liquor/' in url and '/nearby/' not in url and '/exports?' in url:
                return [{**self.buy,'stock':0,'updatedAt':self.time(0.01)}]
            return rows
        with patch.object(self.core.services,'fetch_json',side_effect=depleted):
            self.assertEqual(self.call('find_ptn_routes')['rows'],[])

    def test_partial_orders_use_actual_quantity_in_all_money_and_advert_fields(self):
        self.sell['demand']=5000
        row=self.call('find_ptn_routes')['rows'][0]
        self.assertEqual(row['quantity'],5000)
        self.assertTrue(row['viable'])
        c=row['pricing']
        self.assertEqual(c['owner_after_reserve'],c['owner_per_ton']*5000-CURRENT_DEFAULTS['cost_reserve'])
        self.call('select_ptn_route',id=row['id'],revision=0)
        self.capture('buy');self.capture('sell');self.carrier(system='Source')
        self.mutate('stage',stage='loading')
        state=self.mutate('confirm',price=c['carrier_buy'],remaining=5000,
                          checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        self.assertTrue(state['operation']['ready'])
        text=self.call('prepare_ptn_advert',revision=self.desk.data['revision'])['advert']
        self.assertIn('5k units',text)
        self.core.store.set('journal','system','Source')
        self.assertEqual(self.call('find_ptn_routes',allow_partial=False)['rows'],[])
        self.sell['demand']=1999
        self.assertEqual(self.call('find_ptn_routes')['rows'],[])

    def test_self_loading_records_actual_cost_and_only_advertises_unloading(self):
        row=self.call('find_ptn_routes',haul_mode='self_load',share_surplus=True)['rows'][0]
        self.assertEqual(row['pricing']['loading_per_ton'],0)
        self.assertGreater(row['pricing']['unloading_per_ton'],60000)
        self.call('select_ptn_route',id=row['id'],revision=0)
        self.capture('buy');self.capture('sell');self.mutate('stage',stage='loading')
        self.mutate('confirm',price=4100,remaining=0)
        with self.assertRaisesRegex(ValueError,'yourself'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.mutate('stage',stage='transit');self.mutate('stage',stage='unloading');self.carrier(system='Buyer')
        state=self.mutate('confirm',price=5200,remaining=18000,
                          checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        self.assertTrue(state['operation']['ready'])
        self.assertEqual(state['operation']['pricing']['owner_per_ton'],1100)
        costs=state['operation']['pricing']
        self.assertEqual(costs['hauler_total']+costs['owner_total'],costs['gross_total'])
        self.assertEqual(self.call('prepare_ptn_advert',revision=self.desk.data['revision'])['profit_per_ton'],69800)

    def test_self_unloading_only_advertises_loading_and_records_sale_proceeds(self):
        row=self.call('find_ptn_routes',haul_mode='self_unload',share_surplus=True)['rows'][0]
        self.assertGreater(row['pricing']['loading_per_ton'],60000)
        self.assertEqual(row['pricing']['unloading_per_ton'],0)
        self.call('select_ptn_route',id=row['id'],revision=0)
        self.capture('buy');self.capture('sell');self.mutate('stage',stage='loading');self.carrier(system='Source')
        self.mutate('confirm',price=74000,remaining=18000,
                    checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        self.assertEqual(self.call('prepare_ptn_advert',revision=self.desk.data['revision'])['profit_per_ton'],70000)
        self.mutate('remaining',remaining=0);self.mutate('stage',stage='transit');self.mutate('stage',stage='unloading')
        state=self.mutate('confirm',price=75500,remaining=0)
        self.assertEqual(state['operation']['pricing']['owner_per_ton'],1500)
        with self.assertRaisesRegex(ValueError,'yourself'):
            self.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        self.assertEqual(self.mutate('stage',stage='complete')['plan']['stage'],'complete')

    def test_provider_fields_and_commodity_identity_are_validated(self):
        for change in ({'commodityName':'gold'},{'stationName':{'html':'x'}},{'stationName':'x\u2028oops'},
                       {'marketId':True},{'demand':10**20},{'systemX':float('inf')},{'bodyName':'x\u202eabc'}):
            old=self.sell;self.sell={**old,**change}
            self.assertEqual(self.call('find_ptn_routes')['rows'],[],change)
            self.sell=old
        self.buy['meanPrice']=self.sell['meanPrice']=10**100
        self.assertFalse(self.call('find_ptn_routes')['rows'][0]['viable'])

    def test_scan_cannot_be_selected_after_owner_or_carrier_location_change(self):
        row=self.scan()['rows'][0]
        self.carrier(system='Other system')
        with self.assertRaisesRegex(ValueError,'location or owner'):
            self.call('select_ptn_route',id=row['id'],revision=0)

    def test_stale_raw_market_cannot_supply_a_fresh_mean_price(self):
        self.choose();self.capture('buy')
        self.desk.latest_market['timestamp']=self.time(-1)
        state=self.call('capture_ptn_market',revision=self.desk.data['revision'],side='buy')
        self.assertIsNone(state['plan']['scouts']['buy']['mean_price'])

    def test_advert_rejects_unicode_controls_and_invalid_phases(self):
        for name in ('x\u2028pwn','x\u202epwn','x\x7fpwn','x\u200bpwn'):
            with self.assertRaises(ValueError):advert(name,'TST-001','Liquor','Port','System','loading',20000,18000)
        with self.assertRaises(ValueError):advert('Test','TST-001','Liquor','Port','System','scouting',20000,18000)

    def test_discord_link_must_be_a_message_url_without_suffix_or_controls(self):
        self.confirmed()
        for link in ('https://discord.com/channels/1/2/3\n@everyone','https://discord.com/channels/1/2/3?x=1',
                     'https://discord.com/channels/../@everyone','https://discord.com/channels/1/2'):
            with self.assertRaisesRegex(ValueError,'Discord message link'):self.mutate('posted',link=link)

    def test_search_timeout_reports_partial_coverage_and_releases_scan_lock(self):
        # The loader imports a fresh module object, so patch its own globals.
        # Inject the executor timeout without relying on wall-clock scheduling.
        with patch.object(self.desk,'quotes',return_value=[]),patch.dict(
                self.desk.scan.__globals__,{'as_completed':Mock(side_effect=FuturesTimeout)}):
            result=self.call('find_ptn_routes')
        self.assertIn('time limit',' '.join(result['warnings']))
        self.assertEqual(result['coverage']['completed'],0)
        self.assertFalse(result['coverage']['all_commodities'])
        self.assertFalse(self.desk.searching)
        self.assertEqual(result['rows'],[])

    def test_concurrent_scan_is_rejected_and_old_board_is_not_a_current_benchmark(self):
        self.desk.searching=True
        with patch.object(self.core.services,'fetch_json',side_effect=AssertionError('no parallel scan')):
            with self.assertRaisesRegex(ValueError,'already running'):self.scan()
        self.desk.searching=False
        self.desk.refresh_board()
        self.desk.board['updated_at']=self.time(-1)
        board=self.desk.view()['board']
        self.assertFalse(board['available'])
        self.assertEqual(board['benchmarks'],{})


class FlexiblePricingTests(unittest.TestCase):
    def test_modes_conserve_money_and_never_spend_the_carrier_return(self):
        rng=random.Random(127)
        for mode in ('both','self_load','self_unload'):
            for _ in range(180):
                quantity=rng.randint(2000,25000)
                prefs={**CURRENT_DEFAULTS,'haul_mode':mode,'cost_reserve':rng.randint(0,20000000),
                       'owner_floor':rng.randint(0,3000),'share_surplus':rng.choice((True,False))}
                buy=rng.randint(1,30000);sell=buy+rng.randint(5000,200000)
                c=pricing(buy,sell,quantity,rng.randint(100,40000),prefs)
                if not c['settings_valid']:continue
                self.assertGreater(c['owner_after_reserve'],0)
                self.assertEqual(c['hauler_total']+c['owner_total'],c['gross_total'])
                for phase in ('loading','unloading'):
                    if paid_leg(prefs,phase):self.assertGreaterEqual(c[phase+'_per_ton'],prefs[phase+'_floor'])
                    else:self.assertEqual(c[phase+'_per_ton'],0)

    def test_zero_owner_floor_still_requires_positive_profit_after_reserve(self):
        p={**CURRENT_DEFAULTS,'owner_floor':0,'cost_reserve':5000000}
        c=pricing(4000,50000,5000,10000,p)
        self.assertTrue(c['settings_valid']);self.assertGreater(c['owner_after_reserve'],0)
        self.assertFalse(pricing(4000,25000,5000,10000,p)['settings_valid'])

    def test_optional_preferences_are_bounded_and_target_does_not_change_floors(self):
        p=settings({'payout_target':999999})
        c=pricing(4000,50000,18000,10000,p)
        self.assertTrue(c['settings_valid']);self.assertFalse(c['meets_target'])
        for q in ({'haul_mode':'admin'},{'min_quantity':20000},{'allow_partial':'maybe'},{'payout_target':-1}):
            with self.assertRaises(ValueError):settings(q)
