"""Rare buying evidence, journal transitions and authenticated HTTP/MCP parity."""
import json
import unittest
from unittest.mock import patch

import test_mining
from test_elitelab import config
from modules.loop.evidence import workflow, timestamp, qty, xyz


class RaresWorkflowTests(unittest.TestCase):
    setUp = test_mining.MiningTests.setUp
    emit = test_mining.MiningTests.emit

    def state(self):
        return self.core.http.tools['get_rares_loop'].fn({})

    def cargo(self, count=4, stamp='2026-10-22T12:00:02Z'):
        self.core.bus.emit('journal.file.Cargo', {'Count':count, 'timestamp':stamp,
            'Inventory':[{'Name':'alieneggs','Count':count}] if count else []})

    def market(self, station='Ridley Scott', stamp='2026-10-22T12:00:03Z'):
        self.core.bus.emit('journal.file.Market', {'StarSystem':'Zaonce','StationName':station,'timestamp':stamp,
            'Items':[{'Name':'alieneggs','Name_Localised':'Leathery Eggs','Rare':True,'Stock':12,'BuyPrice':24500}]})

    def dock(self, station='Ridley Scott', stamp='2026-10-22T12:00:01Z'):
        self.emit('Docked',stamp,StarSystem='Zaonce',StationName=station)

    def test_unknown_empty_and_present_cargo_are_distinct(self):
        self.assertIsNone(self.state()['tons_total'])
        self.assertFalse(self.state()['workflow']['cargo_known'])
        self.cargo(0)
        self.assertEqual(self.state()['tons_total'],0)
        self.assertTrue(self.state()['workflow']['cargo_known'])
        self.cargo()
        self.assertEqual(self.state()['tons_total'],4)
        self.assertTrue(next(s for s in self.state()['stations'] if s['system']=='Zaonce')['in_hold'])
        self.emit('Loadout',CargoCapacity=64)
        self.assertEqual(self.state()['workflow']['free_capacity'],60)

    def test_arrival_requires_exact_station_and_survives_name_case(self):
        self.dock('Another Station')
        self.assertFalse(any(s['docked_here'] for s in self.state()['stations']))
        self.dock(' ridley scott ')
        self.assertEqual([s['system'] for s in self.state()['stations'] if s['docked_here']],['Zaonce'])
        self.emit('Undocked')
        self.assertFalse(any(s['docked_here'] for s in self.state()['stations']))

    def test_market_current_visit_previous_visit_and_previous_station(self):
        self.assertEqual(self.state()['workflow']['market']['status'],'not_recorded')
        self.dock();self.market()
        self.assertEqual(self.state()['workflow']['market']['status'],'current_snapshot')
        self.emit('Undocked','2026-10-22T12:01:00Z')
        self.assertEqual(self.state()['workflow']['market']['status'],'previous_station')
        self.dock(stamp='2026-10-22T12:02:00Z')
        self.assertEqual(self.state()['workflow']['market']['status'],'previous_visit')
        self.market(stamp='2026-10-22T12:02:01Z')
        self.assertEqual(self.state()['workflow']['market']['status'],'current_snapshot')
        self.market('Another Station')
        self.assertEqual(self.state()['workflow']['market']['status'],'previous_station')

    def test_session_reset_rejects_old_cargo_but_continuation_preserves_it(self):
        self.emit('LoadGame',Commander='Rare Tester',FID='F1')
        self.cargo();self.dock();self.market()
        self.emit('Commander','2026-10-22T12:00:04Z',Name='Rare Tester',FID='F1')
        self.assertTrue(self.state()['workflow']['cargo_known'])
        self.assertEqual(self.state()['workflow']['market']['status'],'current_snapshot')
        self.emit('LoadGame','2026-10-22T12:10:00Z',Commander='Rare Tester',FID='F1')
        self.assertFalse(self.state()['workflow']['cargo_known'])
        self.assertIsNone(self.state()['tons_total'])
        self.assertEqual(self.state()['workflow']['market']['status'],'previous_visit')
        self.cargo(stamp='2026-10-22T12:10:02Z')
        self.assertTrue(self.state()['workflow']['cargo_known'])
        self.emit('Commander','2026-10-22T12:20:00Z',Name='Other',FID='F2')
        self.assertFalse(self.state()['workflow']['cargo_known'])

    def test_offline_unknown_distances_and_selection_failure_preserve_state(self):
        self.assertTrue(all(s['dist'] is None for s in self.state()['stations']))
        select=self.core.http.tools['select_rares_loop'].fn
        for value in (None, [], {}, '../../escape', 'unknown'):
            with self.assertRaises(ValueError):select({'id':value})
        with patch.object(self.core,'write_data',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):select({'id':'lave'})
        self.assertEqual(self.state()['id'],'lave')
        self.assertEqual(select({'id':'lave'})['id'],'lave')

    def test_journal_evidence_handlers_do_not_write_files_or_fetch(self):
        from modules.loop.module import Loop
        loop=Loop(self.core)
        with patch.object(self.core,'write_data') as write, patch.object(self.core.services,'edsm_coords') as fetch:
            loop.event('journal.Docked',{'event':'Docked','timestamp':'2026-10-22T12:00:00Z'})
            loop.recompute()
            write.assert_not_called();fetch.assert_not_called()

    def test_coordinate_validation_keeps_json_finite_and_nearest_stop_first(self):
        from modules.loop.module import Loop
        loop=Loop(self.core)
        self.core.store.set('journal','star_pos',[0,0,0])
        loop.coords.coords={'Leesti':{'x':30,'y':40,'z':0},'Diso':{'x':3,'y':4,'z':0},
                            'Lave':{'x':float('nan'),'y':0,'z':0}}
        loop.recompute()
        self.assertEqual(self.state()['next'],{'system':'Diso','station':'Shifnalport','dist':5.0})
        self.assertIsNone(next(s for s in self.state()['stations'] if s['system']=='Lave')['coords'])
        json.dumps(self.state(),allow_nan=False)

    def test_authenticated_http_and_mcp_return_same_evidence(self):
        import os,subprocess,sys,threading,http.client
        from http.server import ThreadingHTTPServer
        from elitelab.core.http import make_handler
        self.dock();self.cargo();self.market()
        with patch.object(config,'AUTH_TOKEN','rares-test-token'):
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.core));server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                calls=[('tools/list',{}),('tools/call',{'name':'get_rares_loop','arguments':{}}),
                       ('tools/call',{'name':'select_rares_loop','arguments':{'id':'../escape'}})]
                messages=''.join(json.dumps({'jsonrpc':'2.0','id':i,'method':m,'params':q})+'\n' for i,(m,q) in enumerate(calls))
                env=dict(os.environ,ELITELAB_URL=f'http://127.0.0.1:{server.server_port}',ELITELAB_AUTH_TOKEN='rares-test-token')
                run=subprocess.run([sys.executable,'-m','elitelab','mcp'],env=env,cwd=config.ROOT,input=messages,text=True,capture_output=True,check=True,timeout=20)
                results=[json.loads(line)['result'] for line in run.stdout.splitlines()]
                tool=next(t for t in results[0]['tools'] if t['name']=='get_rares_loop')
                self.assertIn('null tons',tool['description'])
                self.assertEqual(json.loads(results[1]['content'][0]['text']),self.state())
                self.assertTrue(results[2]['isError'])
                for endpoint,method,body in (('/api/loop','GET',None),('/api/loop/select','POST','{"id":"lave"}')):
                    for headers,status in (({},401),({'Host':'untrusted.invalid'},403),
                                           ({'Origin':'https://untrusted.invalid','Authorization':'Bearer rares-test-token'},403 if method=='POST' else 200),
                                           ({'Authorization':'Bearer rares-test-token'},200)):
                        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                        conn.request(method,endpoint,body=body,headers={'Content-Type':'application/json',**headers})
                        r=conn.getresponse();payload=r.read();conn.close();self.assertEqual(r.status,status)
                        if status==200:self.assertEqual(json.loads(payload),self.state())
            finally:
                server.shutdown();server.server_close();thread.join(2)


class EvidenceTests(unittest.TestCase):
    def test_untrusted_numeric_and_time_values_remain_unknown(self):
        for value in (True,-1,float('nan'),float('inf'),10**1000,'4'):
            self.assertIsNone(qty(value))
            if value != -1:self.assertFalse(xyz([value,0,0]))
        for value in (None,{},'bad','2026-10-22T12:00:00'):
            self.assertIsNone(timestamp(value))
        for cargo in ({}, {'count':0}, {'count':3,'items':[]}, {'count':True,'items':[]},
                      {'count':1,'items':[{'count':1.5}]}, {'count':1,'items':[None]}):
            self.assertFalse(workflow({'cargo':cargo},None)['cargo_known'])

    def test_invalid_future_or_missing_market_time_never_becomes_current(self):
        for stamp in (None,'bad','2999-01-01T00:00:00Z'):
            j={'docked':True,'system':'Zaonce','station':'Ridley Scott',
               'market':{'system':'Zaonce','station':'Ridley Scott','timestamp':stamp,
                         'rares_in_stock':[{'name':'Eggs','buy':-1,'stock':True}]}}
            market=workflow(j,0)['market']
            self.assertEqual(market['status'],'undated')
            self.assertIsNone(market['rares'][0]['buy']);self.assertIsNone(market['rares'][0]['stock'])
