"""Job-scoped catch-up uses real journal files and durable idempotency receipts."""
import copy
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core, config, loader, FIXTURES
from modules.party.recovery import phase_at


class DeliveryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for key,value in (('DATA_DIR',self.temp.name),('JOURNAL_DIR',str(Path(FIXTURES,'recovery')))):
            p=patch.object(config,key,value);p.start();self.addCleanup(p.stop)
        self.core=self.client()
        self.core.store.update('journal',{'cargo_capacity':200,'cargo':{'count':0,'items':[]}})
        self.call('plan_carrier_trade',commodity='gold',source='Buy / Sol',destination='Sell / Lave',
                  source_price=100,destination_price=300,target=1000,planned_quantity=1000,
                  carrier_market_id=123,destination_market_id=789)
        self.call('manage_carrier_operation',action='start')
        self.desk=self.core.modules['trade'].trade
        self.party=self.core.modules['party'].party
        self.set_stage('loading')
        self.party.save_work(self.party.work,tracking={'operation_id':self.op['id'],'since':'2026-10-20T10:00:00Z',
                                                     'owner':True,'manual_through':{}})

    def client(self):
        core=Core();loader.load_all(core)
        self.addCleanup(core.close)
        return core

    def call(self,tool,**q):
        return self.core.http.tools[tool].fn(q)

    def set_stage(self,stage):
        data=copy.deepcopy(self.desk.data)
        data['operation'].update(stage=stage,started_at='2026-10-20T10:00:00Z',
            phase_started_at={'loading':'2026-10-20T10:00:00Z'})
        if stage in ('unloading','complete'):
            data['operation']['phase_started_at']['unloading']='2026-10-20T11:00:00Z'
            data['plan']['mode']='unload'
        if stage=='complete':data['operation']['ended_at']='2026-10-20T12:00:00Z'
        self.desk.commit(data);self.op=data['operation']

    def wait(self,party):
        deadline=time.monotonic()+3
        while party.recovery['running'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(party.recovery['running'])

    def recover(self,party=None):
        party=party or self.party
        party.schedule_recovery();self.wait(party)
        return party.work

    def test_owner_restart_recovers_missed_sales_and_transfers_once(self):
        restarted=self.client();party=restarted.modules['party'].party
        party.docked_market=999  # Archive docking context must not overwrite live location.
        work=self.recover(party)
        self.assertEqual(work['loading'],150)
        self.assertEqual(party.docked_market,999)
        self.assertEqual(restarted.store.get('trade','operation')['loaded'],150)
        again=self.client();party2=again.modules['party'].party
        self.assertEqual(self.recover(party2)['loading'],150)
        self.assertEqual(party2.recovery['recovered'],0)

    def test_member_waits_for_matching_job_and_recovers_both_legs(self):
        self.set_stage('complete')
        shared=self.party.shared()
        self.party.save_work(None,tracking={**self.party.tracking,'owner':False})
        restarted=self.client();member=restarted.modules['party'].party
        # A member does not trust an unrelated local owner plan after restart.
        member.mode='member';member.remote={'members':[]}
        self.assertIsNone(self.recover(member))
        member.remote=shared;member.last_success=time.time()
        work=self.recover(member)
        self.assertEqual((work['loading'],work['unloading']),(150,80))
        self.assertEqual(set(work['delivery_evidence']),{'loading','unloading'})
        self.assertEqual(restarted.store.get('trade','operation')['unloaded'],0)

    def test_manual_reports_and_corrections_exclude_older_evidence(self):
        self.party.save_work({'operation_id':self.op['id'],'loading':100,'unloading':0},
            tracking={**self.party.tracking,'manual_through':{'loading':'2026-10-20T10:01:00Z'}})
        self.assertEqual(self.recover()['loading'],150)
        # An owner correction covers the old transfer too; no second raw increment.
        self.set_stage('unloading')
        data=copy.deepcopy(self.desk.data)
        data['operation']['reports'][self.party.member_id]['correction_at']={'loading':'2026-10-20T10:03:00Z'}
        self.desk.commit(data)
        self.party.auto_seen=[]
        work=self.recover()
        self.assertEqual((work['loading'],work['unloading']),(150,105))

    def test_disconnected_member_waits_for_fresh_leader_state(self):
        shared=self.party.shared()
        self.party.mode='member';self.party.remote=shared
        self.party.last_success=time.time()-3600
        self.assertIsNone(self.recover())
        self.party.last_success=time.time()
        self.assertEqual(self.recover()['loading'],150)

    def test_failed_write_keeps_delivery_retryable(self):
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            self.recover()
        self.assertIsNone(self.party.work)
        self.assertIn('disk full',self.party.recovery['error'])
        self.party.recovery_retry=0
        self.assertEqual(self.recover()['loading'],150)

    def test_cancelled_and_ambiguous_older_jobs_are_not_backfilled(self):
        self.set_stage('cancelled')
        self.assertIsNone(self.recover())
        self.set_stage('unloading')
        data=copy.deepcopy(self.desk.data);data['operation'].pop('phase_started_at')
        self.desk.commit(data)
        self.assertIsNone(self.recover())
        self.assertIn('older job',self.party.recovery['error'])

    def test_live_delivery_seen_before_scan_is_not_credited_twice(self):
        self.party.journal_delivery('journal.MarketSell',{'timestamp':'2026-10-20T10:01:00Z',
            'event':'MarketSell','Type':'gold','MarketID':123,'Count':100})
        self.assertEqual(self.recover()['loading'],150)

    def test_new_join_boundary_and_job_identity_are_enforced(self):
        event={'timestamp':'2026-10-20T10:01:00Z'}
        self.assertIsNone(phase_at(self.op,event,{**self.party.tracking,'since':'2026-10-20T10:02:00Z'},self.party.member_id))
        self.assertIsNone(phase_at(self.op,event,{**self.party.tracking,'operation_id':'different'},self.party.member_id))

    def test_leave_during_catchup_discards_old_work_and_manual_input_waits(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set();release.wait(2)
            yield {'timestamp':'2026-10-20T10:01:00Z','event':'MarketSell','Type':'gold','MarketID':123,'Count':100},None
        api=self.core.modules['party'].instance
        with patch.object(api,'deliveries',slow):
            self.party.schedule_recovery()
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.core.store.get('party','desk')['action'],'wait')
                with self.assertRaisesRegex(ValueError,'catch-up'):
                    self.party.report_work({'id':self.op['id'],'phase':'loading','tonnes':100,'request_id':'a'*32})
                self.party.leave()
            finally:
                release.set();self.wait(self.party)
        self.assertIsNone(self.party.work)
        self.assertEqual(self.party.recovery['recovered'],0)

    def test_partial_final_line_waits_for_watcher_instead_of_being_recovered(self):
        directory=Path(self.temp.name,'journals');directory.mkdir()
        event='{"timestamp":"2026-10-20T10:01:00Z","event":"MarketSell","Type":"gold","MarketID":123,"Count":100}'
        Path(directory,'Journal.partial.log').write_text(event,encoding='utf-8')
        with patch.object(config,'JOURNAL_DIR',str(directory)):
            self.assertIsNone(self.recover())
