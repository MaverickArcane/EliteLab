"""Mined-load handoff uses real buyer evidence and preserves independent crew work."""
import copy
from unittest.mock import patch
import unittest

import test_ptn
from modules.ptn.module import PTN


class MinedUnloadingTests(unittest.TestCase):
    def setUp(self):
        self.f=test_ptn.PTNTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.core,self.desk=self.f.core,self.f.desk
        self.core.modules['trade'].trade.data['carrier_id']=123
        self.f.call('plan_mining_loading',commodity='platinum',source='Ring A / Source',
                    destination='Sell Port / Buyer',quantity=101,starting_stock=20,
                    miner_price=200000,destination_price=280000,destination_market_id=202)
        self.job=self.f.call('manage_carrier_operation',action='start')['operation']
        self.f.call('manage_carrier_operation',action='depart',id=self.job['id'])
        self.job=self.core.store.get('trade','job')['operation']
        self.visit()

    def visit(self, *, consumer=True, demand=1000, price=280000, market_id=202, station_type='Orbis'):
        self.desk.dock_event('journal.Docked',{'timestamp':self.f.time()})
        self.core.store.update('journal',dict(docked=True,system='Buyer',station='Sell Port',station_type=station_type))
        self.core.bus.emit('journal.file.Market',dict(timestamp=self.f.time(),MarketID=market_id,
            StationName='Sell Port',StarSystem='Buyer',Items=[dict(Name='$platinum_name;',Name_Localised='Platinum',
            BuyPrice=0,SellPrice=price,Stock=0,Demand=demand,MeanPrice=57000,Consumer=consumer)]))

    def import_load(self, **changes):
        query=dict(revision=self.desk.data['revision'],operation_id=self.job['id'],
                   operation_updated_at=self.job['updated_at'],buyer_market_id=202,
                   quantity=100,checked_stock=120,unloading_floor=20000)
        query.update(changes)
        return self.f.call('handoff_mining_to_ptn',**query)

    def scout(self):
        return self.f.call('capture_ptn_market',revision=self.desk.data['revision'],side='sell')

    def ready(self):
        self.import_load();self.scout();self.f.mutate('stage',stage='unloading')
        self.f.carrier(system='Buyer',stats_time=self.f.time())
        return self.confirm()

    def confirm(self, **changes):
        q=dict(price=250000,remaining=100,checked_stock=120,
               checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        q.update(changes)
        return self.f.mutate('confirm',**q)

    def test_complete_mined_load_workflow_no_purchase_or_zero_cost_assumption(self):
        source=copy.deepcopy(self.core.store.get('trade','job'))
        result=self.ready();plan,op=result['plan'],result['operation']
        self.assertEqual(plan['kind'],'mining_unload');self.assertIsNone(plan['route']['buy'])
        self.assertEqual(list(plan['scouts']),['sell']);self.assertTrue(op['ready'],op['blockers'])
        self.assertIsNone(op['pricing']['acquisition_cost']);self.assertIsNone(op['pricing']['owner_after_reserve'])
        self.assertEqual(op['pricing']['carrier_proceeds'],25000000)
        self.assertEqual(op['pricing']['unloading_per_ton'],30000)
        advert=self.f.call('prepare_ptn_advert',revision=result['revision'])
        self.assertEqual(advert['profit_per_ton'],30000)
        self.assertIn('is unloading **Platinum** to **Sell Port**',advert['copy_text'])
        self.assertEqual(advert['remaining'],100)
        self.assertEqual(self.core.store.get('trade','job'),source)
        self.assertEqual(PTN(self.core).view()['plan'],plan)
        self.f.mutate('posted',link='')
        self.f.mutate('remaining',remaining=0)
        self.f.mutate('stage',stage='complete')
        self.assertEqual(self.desk.data['plan']['stage'],'complete')
        self.assertEqual(self.core.store.get('trade','job'),source)

    def test_stale_source_owner_stock_buyer_and_active_plan_guards(self):
        for changes in ({'revision':-1},{'operation_id':'old'},{'operation_updated_at':'old'},
                        {'checked_stock':119},{'quantity':102},{'quantity':25001},{'buyer_market_id':999}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.import_load(**changes)
        self.core.store.set('party','mode','member')
        with self.assertRaises(ValueError):self.import_load()
        self.core.store.set('party','mode','solo')
        self.visit(station_type='Outpost')
        with self.assertRaises(ValueError):self.import_load()
        self.visit(market_id=303)
        with self.assertRaises(ValueError):self.import_load(buyer_market_id=303)
        self.visit();self.import_load()
        with self.assertRaises(ValueError):self.import_load()
        with self.assertRaises(ValueError):self.f.call('capture_ptn_market',revision=self.desk.data['revision'],side='buy')
        with self.assertRaises(ValueError):self.f.mutate('stage',stage='loading')
        with self.assertRaises(ValueError):self.f.mutate('resize',quantity=101)
        with self.assertRaises(ValueError):self.f.call('handoff_ptn_to_carrier',revision=self.desk.data['revision'],starting_stock=0)

    def test_expired_stock_can_be_rechecked_and_newer_short_inventory_blocks_advert(self):
        self.import_load();self.scout()
        self.desk.data['plan']['source']['checked_at']=self.f.time(-2)
        with self.assertRaises(ValueError):self.f.mutate('stage',stage='unloading')
        self.f.mutate('stock',checked_stock=120)
        self.f.mutate('stage',stage='unloading');self.f.carrier(system='Buyer')
        with self.assertRaises(ValueError):self.f.mutate('confirm',price=250000,remaining=100,
            checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        self.assertTrue(self.confirm()['operation']['ready'])
        self.core.store.set('trade','inventory',{'platinum':{'stock':110,'updated_at':self.f.time()}})
        self.assertFalse(self.desk.view()['operation']['ready'])
        with self.assertRaises(ValueError):self.f.call('prepare_ptn_advert',revision=self.desk.data['revision'])
        # Owner explicitly rechecks reduced physical stock and outstanding order.
        result=self.confirm(remaining=90,checked_stock=110)
        self.assertTrue(result['operation']['ready'],result['operation']['blockers'])
        self.assertEqual(self.f.call('prepare_ptn_advert',revision=result['revision'])['remaining'],90)

    def test_new_contradictory_buyer_revokes_checks_and_recapture_recovers(self):
        self.ready();self.visit(consumer=False)
        result=self.desk.view()
        self.assertNotIn('sell',result['plan']['scouts'])
        self.assertNotIn('unloading',result['plan']['orders'])
        self.assertFalse(result['operation']['ready'])
        with self.assertRaises(ValueError):self.scout()
        self.visit();self.scout();self.assertTrue(self.confirm()['operation']['ready'])
        self.visit(demand=50);self.scout()
        self.assertFalse(self.confirm()['operation']['ready'])
        self.visit(demand=0);self.scout()
        self.assertTrue(self.confirm()['operation']['ready'])

    def test_failed_import_write_keeps_ptn_and_source_job_unchanged(self):
        before=copy.deepcopy(self.desk.data);job=copy.deepcopy(self.core.store.get('trade','job'))
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.import_load()
        self.assertEqual(self.desk.data,before);self.assertEqual(self.core.store.get('trade','job'),job)

    def test_source_and_order_changes_do_not_silently_rewrite_checked_plan(self):
        self.f.call('manage_carrier_operation',action='unload',id=self.job['id'])
        with self.assertRaises(ValueError):self.import_load()
        self.job=self.core.store.get('trade','job')['operation'];self.ready()
        self.core.store.set('trade','orders',{'platinum':{'side':'sell','price':279000,'quantity':100,'updated_at':self.f.time()}})
        result=self.desk.view();self.assertFalse(result['operation']['ready'])
        self.assertEqual(result['plan']['orders']['unloading']['price'],250000)
        self.f.carrier(callsign='NEW-001')
        with self.assertRaises(ValueError):self.f.call('prepare_ptn_advert',revision=self.desk.data['revision'])
