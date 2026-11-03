"""Trade-to-Powerplay handoff is bounded planning context, never reward evidence."""
import json
import unittest
from unittest.mock import patch

import test_trade_plan
from test_elitelab import config


class TradePowerplayTests(unittest.TestCase):
    setUp = test_trade_plan.TradePlanTests.setUp
    emit = test_trade_plan.TradePlanTests.emit
    station = test_trade_plan.TradePlanTests.station
    markets = test_trade_plan.TradePlanTests.markets
    search = test_trade_plan.TradePlanTests.search
    select = test_trade_plan.TradePlanTests.select
    cargo = test_trade_plan.TradePlanTests.cargo

    def context(self, **q):
        return self.core.http.tools['get_trade_powerplay_handoff'].fn(q)

    def pledge(self, name='Edmund Mahon'):
        self.emit('Powerplay',Power=name,Merits=1200,Rank=1)

    def test_missing_completed_unknown_pledge_and_changed_commander(self):
        self.assertEqual(self.context()['status'],'no_plan')
        self.select();self.emit('PowerplayLeave')
        c=self.context();self.assertEqual(c['status'],'pledge_unknown');self.assertIsNone(c['next_tool'])
        self.pledge();self.assertTrue(self.context()['ready'])
        self.emit('Commander',Name='Someone Else',FID='OTHER')
        self.assertEqual(self.context()['status'],'commander_mismatch')
        self.assertIsNone(self.context()['next_tool'])

    def test_buy_and_sell_use_active_leg_exact_stop_without_changing_route(self):
        self.pledge();selected=self.select()
        before=self.core.store.get('personal','plan')
        for role,system,station in [('buy','Sol','Port 1'),('sell','Alpha','Port 2')]:
            c=self.context(role=role)
            self.assertTrue(c['ready']);self.assertEqual(c['commodity'],'Gold');self.assertEqual(c['quantity'],100)
            self.assertEqual(c['stop']['station'],station)
            self.assertEqual(c['next_tool'],{'name':'find_sell_targets','arguments':{'ref':system,'power':'Edmund Mahon'}})
            self.assertEqual(c['eligibility'],'unknown');self.assertIsNone(c['expected_merits'])
        self.assertEqual(self.core.store.get('personal','plan'),before)
        self.assertEqual(self.core.store.get('powerplay','merits'),1200)

    def test_return_leg_and_completion_invalidate_old_tokens(self):
        self.pledge();self.select();old=self.context()['token']
        self.cargo()
        self.emit('MarketSell',test_trade_plan.iso(1),MarketID=2,Type='Gold',Count=100,TotalSale=40000)
        c=self.context();self.assertEqual(c['leg'],1);self.assertEqual(c['commodity'],'Silver');self.assertEqual(c['stop']['system'],'Sol')
        self.assertNotEqual(c['token'],old)
        with self.assertRaisesRegex(ValueError,'changed'):self.context(token=old)
        self.emit('MarketSell',test_trade_plan.iso(2),MarketID=1,Type='Silver',Count=100,TotalSale=30000)
        self.assertEqual(self.context()['status'],'complete');self.assertFalse(self.context()['ready'])

    def test_reselection_clear_and_pledge_changes_reject_stale_context(self):
        self.pledge();self.select();old=self.context()['token']
        self.pledge('Felicia Winters')
        with self.assertRaises(ValueError):self.context(token=old)
        c=self.context();self.assertEqual(c['power'],'Felicia Winters')
        self.select(quantity=50)
        with self.assertRaises(ValueError):self.context(token=c['token'])
        old=self.context()['token'];self.core.http.tools['clear_trade_route'].fn({})
        with self.assertRaises(ValueError):self.context(token=old)
        self.assertEqual(self.context()['status'],'no_plan')

    def test_unknown_cargo_old_quotes_and_distance_never_become_merits(self):
        self.pledge();self.select(age_hours=60)
        self.core.store.set('journal','cargo',{'count':None,'items':[]})
        c=self.context();self.assertEqual(c['quotes']['status'],'stale')
        self.assertIsNone(c['expected_merits']);self.assertEqual(c['eligibility'],'unknown')
        self.assertNotIn('quantity',c['next_tool']['arguments'])
        self.assertNotIn('rate_mode',c['next_tool']['arguments'])

    def test_invalid_inputs_and_unavailable_finder(self):
        for role in ('../escape',{},[],True,None):
            with self.assertRaises(ValueError):self.context(role=role)
        self.pledge();self.select()
        for token in ({},[],True,'x'*10000):
            with self.assertRaises(ValueError):self.context(token=token)
        self.core.http.tools.pop('find_sell_targets')
        c=self.context();self.assertEqual(c['status'],'finder_unavailable');self.assertIsNone(c['next_tool'])

    def test_preview_does_not_persist_or_fetch(self):
        self.pledge();self.select()
        with patch.object(self.core,'write_data') as write, patch.object(self.core.services,'fetch_json') as fetch:
            c=self.context();self.assertTrue(c['ready'])
            write.assert_not_called();fetch.assert_not_called()
        self.assertEqual(c['token'],self.core.store.get('personal','powerplay_handoff')['token'])

    def test_pledge_requires_this_session_and_continuation_preserves_it(self):
        self.pledge();self.select();self.assertTrue(self.context()['ready'])
        self.emit('Commander',Name='Test Miner',FID='F2')
        self.assertTrue(self.context()['ready'])
        self.emit('LoadGame',Commander='Test Miner',FID='F2')
        self.assertEqual(self.core.store.get('powerplay','power'),'Edmund Mahon')
        self.assertEqual(self.context()['status'],'pledge_unknown')
        self.pledge();self.assertTrue(self.context()['ready'])
        self.emit('Commander',Name='Test Miner',FID='ANOTHER_ACCOUNT')
        self.assertEqual(self.context()['status'],'pledge_unknown')

    def test_authenticated_http_and_real_stdio_mcp_contract(self):
        import os,subprocess,sys,threading,http.client
        from http.server import ThreadingHTTPServer
        from elitelab.core.http import make_handler
        self.pledge();self.select();expected=self.context(role='buy')
        with patch.object(config,'AUTH_TOKEN','handoff-test-token'):
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.core));server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                calls=[('tools/list',{}),('tools/call',{'name':'get_trade_powerplay_handoff','arguments':{'role':'buy'}}),
                       ('tools/call',{'name':'get_trade_powerplay_handoff','arguments':{'token':'old'}}),
                       ('prompts/get',{'name':'trade_powerplay_handoff'})]
                messages=''.join(json.dumps({'jsonrpc':'2.0','id':i,'method':m,'params':q})+'\n' for i,(m,q) in enumerate(calls))
                env=dict(os.environ,ELITELAB_URL=f'http://127.0.0.1:{server.server_port}',ELITELAB_AUTH_TOKEN='handoff-test-token')
                run=subprocess.run([sys.executable,'-m','elitelab','mcp'],env=env,cwd=config.ROOT,input=messages,text=True,capture_output=True,check=True,timeout=20)
                result=[json.loads(line)['result'] for line in run.stdout.splitlines()]
                tool=next(t for t in result[0]['tools'] if t['name']=='get_trade_powerplay_handoff')
                self.assertIn('expected_merits null',tool['description'])
                self.assertEqual(json.loads(result[1]['content'][0]['text']),expected)
                self.assertTrue(result[2]['isError'])
                self.assertIn('expected_merits null',result[3]['messages'][0]['content']['text'])
                for headers,status in (({},401),({'Host':'untrusted.invalid'},403),({'Authorization':'Bearer handoff-test-token'},200)):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                    conn.request('GET','/api/personal/powerplay?role=buy',headers=headers)
                    response=conn.getresponse();payload=response.read();conn.close()
                    self.assertEqual(response.status,status)
                    if status==200:self.assertEqual(json.loads(payload),expected)
            finally:
                server.shutdown();server.server_close();thread.join(2)
