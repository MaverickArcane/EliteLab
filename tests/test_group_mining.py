"""Ring-to-carrier coordination on the real authenticated two-client transport."""
from datetime import datetime, timezone
import time
import threading
import unittest
from unittest.mock import patch

import test_trade_party
import test_ptn


class GroupMiningTests(unittest.TestCase):
    def setUp(self):
        self.f=test_trade_party.PartyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_equal_tonnes_delivery_replay_reconnect_and_unloading(self):
        f=self.f;tools=f.leader_core.http.tools
        f.leader_core.store.update('journal',{'cmdr':'Owner','cargo_capacity':100})
        f.member_core.store.update('journal',{'cmdr':'Miner','cargo_capacity':50})
        f.leader_core.modules['trade'].trade.data['carrier_id']=123
        f.member.join({'url':f.url,'code':f.state['code']})
        before=f.leader_core.store.get('trade','inventory')
        plan=tools['plan_mining_loading'].fn(dict(commodity='platinum',source='Ring A / Sol',destination='Buyer / Lave',
            quantity=101,starting_stock=20,miner_price=200000,destination_price=280000,destination_market_id=456))
        self.assertEqual(plan['plan']['activity'],'mining')
        self.assertEqual(plan['plan']['target'],121)
        self.assertIsNone(plan['calculation']['hauler_margin'])
        self.assertEqual(f.leader_core.store.get('trade','inventory'),before)
        op=tools['manage_carrier_operation'].fn({'action':'start'})['operation']
        members=f.leader_core.store.get('trade','workload')['members']
        targets=[r['loading_target'] for r in members]
        self.assertEqual(sorted(targets),[50,51])
        f.member.report_work({'activity':'ready'})
        bus=f.member_core.bus
        event=dict(event='MiningRefined',timestamp=datetime.now(timezone.utc).isoformat(),Type='platinum')
        bus.emit('journal.MiningRefined',event)
        self.assertEqual(f.leader.shared()['operation']['loaded'],0)
        sale=dict(event='MarketSell',timestamp=datetime.now(timezone.utc).isoformat(),Type='platinum',MarketID=123,Count=20,TotalSale=4000000)
        bus.emit('journal.MarketSell',sale);bus.emit('journal.MarketSell',sale)
        f.member.report_work({'activity':'ready'})
        self.assertEqual(f.leader.shared()['operation']['loaded'],20)
        f.member.leave();f.member.join({'url':f.url,'code':f.state['code']})
        bus.emit('journal.MarketSell',{**sale,'_replay':True})
        f.member.report_work({'activity':'ready'})
        self.assertEqual(f.leader.shared()['operation']['loaded'],20)
        for action in ('depart','unload'):
            tools['manage_carrier_operation'].fn({'action':action,'id':op['id']})
        self.assertFalse(f.leader_core.store.get('trade','plan')['carrier_price_known'])
        # The same two-client mining job can prepare a checked public unload.
        clock=datetime.now(timezone.utc).isoformat()
        f.leader_core.store.set('journal','carrier',dict(name='Group Carrier',callsign='TST-001',
            system='Lave',stats_time=clock,free_space=24000,reserved_space=0))
        f.leader_core.bus.emit('journal.Docked',dict(event='Docked',timestamp=clock,
            StationName='Buyer',StarSystem='Lave',StationType='Orbis',MarketID=456))
        f.leader_core.bus.emit('journal.file.Market',dict(timestamp=datetime.now(timezone.utc).isoformat(),
            MarketID=456,StationName='Buyer',StarSystem='Lave',Items=[dict(Name='$platinum_name;',
            Name_Localised='Platinum',SellPrice=280000,BuyPrice=0,Demand=1000,Stock=0,MeanPrice=57000,Consumer=True)]))
        source_job=f.leader_core.store.get('trade','job')
        ptn=tools['get_ptn_desk'].fn({})
        ptn=tools['handoff_mining_to_ptn'].fn(dict(revision=ptn['revision'],operation_id=op['id'],
            operation_updated_at=source_job['operation']['updated_at'],buyer_market_id=456,
            checked_stock=40,quantity=20,unloading_floor=20000))
        ptn=tools['capture_ptn_market'].fn(dict(revision=ptn['revision'],side='sell'))
        ptn=tools['update_ptn_plan'].fn(dict(revision=ptn['revision'],action='stage',stage='unloading'))
        ptn=tools['update_ptn_plan'].fn(dict(revision=ptn['revision'],action='confirm',price=250000,
            remaining=20,checked_stock=40,checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')}))
        advert=tools['prepare_ptn_advert'].fn(dict(revision=ptn['revision']))
        self.assertEqual(advert['remaining'],20);self.assertEqual(advert['profit_per_ton'],30000)
        self.assertEqual(f.leader_core.store.get('trade','job'),source_job)
        f.member.report_work({'activity':'ready'})
        sold={**sale,'MarketID':456,'timestamp':datetime.now(timezone.utc).isoformat()}
        bus.emit('journal.MarketSell',sold);f.member.report_work({'activity':'ready'})
        self.assertEqual(f.leader.shared()['operation']['unloaded'],20)
        with self.assertRaises(ValueError):
            tools['plan_mining_loading'].fn(dict(commodity='platinum',source='Ring',destination='Buyer',quantity=10,starting_stock=0,miner_price=1,destination_price=2))


class PTNHandoffTests(unittest.TestCase):
    def setUp(self):
        self.f=test_ptn.PTNTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_handoff_requires_scouts_revision_and_preserves_independent_stages(self):
        f=self.f;f.confirmed();revision=f.desk.data['revision'];stage=f.desk.data['plan']['stage']
        with self.assertRaises(ValueError):
            f.call('handoff_ptn_to_carrier',revision=revision-1,starting_stock=0)
        plan=f.call('handoff_ptn_to_carrier',revision=revision,starting_stock=20)['plan']
        self.assertEqual(plan['source_market_id'],101)
        self.assertEqual(plan['destination_market_id'],202)
        self.assertEqual(plan['target'],plan['planned_quantity']+20)
        self.assertEqual(plan['carrier_price'],f.desk.data['plan']['orders']['loading']['price'])
        self.assertTrue(plan['carrier_price_known'])
        self.assertEqual(f.desk.data['plan']['stage'],stage)
        self.assertEqual(f.desk.data['revision'],revision)
        f.call('manage_carrier_operation',action='start')
        with self.assertRaises(ValueError):
            f.call('handoff_ptn_to_carrier',revision=revision,starting_stock=20)

    def test_handoff_preserves_actual_price_and_releases_lock_before_trade_publication(self):
        f=self.f;f.confirmed()
        f.mutate('confirm',price=25000,remaining=18000,
                 checks={k:True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        entered=threading.Event();worker=None
        def copy_plan(q):
            nonlocal worker
            def observer():
                with f.desk.lock:entered.set()
            worker=threading.Thread(target=observer);worker.start()
            self.assertTrue(entered.wait(1),'PTN lock held across a cross-module publication')
            return q
        with patch.object(f.core.http.tools['plan_carrier_trade'],'fn',side_effect=copy_plan):
            result=f.call('handoff_ptn_to_carrier',revision=f.desk.data['revision'],starting_stock=0)
        worker.join(timeout=2)
        self.assertEqual(result['carrier_price'],25000)
        self.assertTrue(result['carrier_price_known'])
