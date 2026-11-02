"""Unified synthesis planning, saved-data compatibility and shared allocation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from test_elitelab import Core, config, loader
from modules.wishlist.module import Wishlist


class MaterialPlanTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='elitelab-plan-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        p=patch.object(config,'DATA_DIR',str(self.root));p.start();self.addCleanup(p.stop)
        self.core=Core();self.addCleanup(self.core.close);loader.load_all(self.core)
        self.emit('Commander',Name='Planner',FID='F-PLAN')
        self.emit('LoadGame',Commander='Planner',FID='F-PLAN')

    def emit(self,event,**fields):
        self.core.bus.emit('journal.'+event,{'event':event,'timestamp':'2026-11-01T10:00:00Z',**fields})

    def stock(self,**counts):
        self.emit('Materials',Raw=[{'Name':k,'Count':v} for k,v in counts.items()],Manufactured=[],Encoded=[])

    def call(self,name,**q):return self.core.http.tools[name].fn(q)
    def add(self,key='fsd_injection_basic',qty=1):return self.call('wishlist_add',item=key,kind='synthesis',qty=qty)['entry']
    def plan(self):return self.call('get_engineering_wishlist')

    def test_shared_stock_allocated_once_across_recipes_and_targets(self):
        self.stock(carbon=5,vanadium=5,germanium=5,cadmium=5,niobium=5)
        a=self.add(qty=4);b=self.add('fsd_injection_standard',3)
        w=self.plan();self.assertTrue(w['entries'][0]['complete']);self.assertFalse(w['entries'][1]['complete'])
        self.assertEqual(w['entries'][1]['craftable'],1)
        self.assertEqual(w['summary']['units_short'],6)
        self.assertEqual(sum(e['short'] for e in w['entries']),6)
        self.call('wishlist_update',id=a['id'],qty=2)
        self.assertTrue(self.plan()['summary']['complete'])
        self.assertEqual(self.plan()['entries'][0]['id'],a['id'])
        self.call('wishlist_add',item='carbon',kind='material',qty=1)
        self.assertEqual(self.plan()['summary']['units_short'],1)

    def test_preview_uses_remaining_stock_without_saving_or_crafting(self):
        self.stock(carbon=3,vanadium=3,germanium=3);self.add(qty=2)
        before=(self.root/'engineering_wishlist.json').read_bytes();inv=self.call('get_material_inventory')
        r=self.call('preview_material_plan',item='fsd_injection_basic',kind='synthesis',qty=2)
        self.assertEqual(r['entry']['craftable'],1);self.assertEqual(r['entry']['short'],3)
        self.assertEqual((self.root/'engineering_wishlist.json').read_bytes(),before)
        self.assertEqual(self.call('get_material_inventory'),inv)
        self.assertEqual(self.call('get_fsd_injection_status')['history'],[])

    def test_legacy_saved_entries_and_material_targets_remain_editable(self):
        self.stock(carbon=8,vanadium=8,germanium=8)
        original=self.call('wishlist_add',item='FSD_LongRange',grade=2,qty=1)['entry']
        self.call('set_wishlist',items={'carbon':3})
        w=self.plan();self.assertTrue(w['entries'][0]['legacy'])
        self.assertEqual(w['entries'][1]['id'],original['id'])
        self.call('wishlist_update',id='legacy:carbon',qty=4)
        self.assertEqual(self.core.store.get('materials','wishlist')['carbon']['need'],4)
        self.assertEqual(Wishlist(self.core).compute()['entries'][1]['id'],original['id'])
        self.call('wishlist_remove',id='legacy:carbon')
        self.assertNotIn('carbon',self.core.store.get('materials','wishlist'))
        self.assertTrue((self.root/'wishlist.json').exists())

    def test_unknown_inventory_and_commander_switch_do_not_claim_ready(self):
        self.add();self.assertIsNone(self.plan()['entries'][0]['complete'])
        self.emit('MaterialCollected',Name='carbon',Count=20)
        self.assertFalse(self.plan()['inventory_known'])
        self.stock(carbon=2,vanadium=2,germanium=2)
        self.assertTrue(self.plan()['summary']['complete'])
        self.emit('Commander',Name='Other',FID='F-OTHER',timestamp='2026-11-01T11:00:00Z')
        self.assertFalse(self.plan()['inventory_known'])
        self.assertIsNone(self.plan()['entries'][0]['craftable'])
        self.assertEqual(self.plan()['entries'][0]['qty'],1)

    def test_craft_updates_inventory_but_not_planned_quantity(self):
        self.stock(carbon=3,vanadium=3,germanium=3);self.add(qty=3)
        self.emit('Synthesis',Name='FSD Basic',Materials=[{'Name':k,'Count':1} for k in ('carbon','vanadium','germanium')],timestamp='2026-11-01T10:01:00Z')
        w=self.plan();self.assertEqual(w['entries'][0]['qty'],3);self.assertEqual(w['entries'][0]['craftable'],2)
        self.assertEqual(w['summary']['units_short'],3)
        d=self.call('get_fsd_injection_status');self.assertEqual(d['boost']['status'],'injection_observed')
        self.emit('FSDJump',StarSystem='Leesti',BoostUsed=1,timestamp='2026-11-01T10:02:00Z')
        self.assertEqual(self.call('get_fsd_injection_status')['boost']['status'],'jump_completed')

    def test_failed_update_is_atomic_and_invalid_quantities_rejected(self):
        a=self.add();before=copy.deepcopy(self.plan())
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.call('wishlist_update',id=a['id'],qty=4)
        self.assertEqual(self.plan(),before)
        for qty in (0,-1,10001,True,1.5,'nan',[],{}):
            for tool in ('wishlist_add','preview_material_plan','wishlist_update'):
                with self.subTest(tool=tool,qty=qty),self.assertRaises(ValueError):
                    self.call(tool,item='fsd_injection_basic',kind='synthesis',id=a['id'],qty=qty)
        with self.assertRaises(ValueError):self.call('wishlist_update',id='missing',qty=1)
        with self.assertRaises(ValueError):self.call('wishlist_add',item='../outside',kind='synthesis')

    def test_concurrent_plan_edits_keep_entries_and_correct_totals(self):
        self.stock(carbon=100,vanadium=100,germanium=100)
        with ThreadPoolExecutor(max_workers=4) as pool:entries=list(pool.map(lambda _:self.add(qty=2),range(10)))
        self.assertEqual(len(self.plan()['entries']),10)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda e:self.call('wishlist_update',id=e['id'],qty=3),entries))
        self.assertEqual({r['need'] for r in self.plan()['needs']},{30})
        self.assertEqual(len(json.loads((self.root/'engineering_wishlist.json').read_text())),10)

    def test_existing_blueprint_effect_unlock_and_build_costs_preserved(self):
        for item in ('FSD_LongRange','special_fsd_heavy','unlock_guardian_fsd_booster','50 tellurium'):
            r=self.call('wishlist_add',item=item)
            self.assertEqual(r['status'],'added');self.assertTrue(r['needs'])
        self.assertEqual(len(self.plan()['entries']),4)
        self.assertEqual(len(self.call('wishlist_options')['synthesis']),35)
        with self.assertRaisesRegex(ValueError,'no build is pinned'):
            self.call('wishlist_add',key='build')

    def test_authenticated_mcp_uses_the_same_saved_plan_and_prompt(self):
        import os,subprocess,sys,threading,http.client
        from http.server import ThreadingHTTPServer
        from elitelab.core.http import make_handler
        self.stock(carbon=3,vanadium=3,germanium=3)
        with patch.object(config,'AUTH_TOKEN','plan-test-token'):
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.core));server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                def invoke(calls):
                    messages=''.join(json.dumps({'jsonrpc':'2.0','id':i,'method':m,'params':q})+'\n' for i,(m,q) in enumerate(calls))
                    env=dict(os.environ,ELITELAB_URL=f'http://127.0.0.1:{server.server_port}',ELITELAB_AUTH_TOKEN='plan-test-token')
                    run=subprocess.run([sys.executable,'-m','elitelab','mcp'],env=env,cwd=config.ROOT,input=messages,text=True,capture_output=True,check=True,timeout=20)
                    return [json.loads(line)['result'] for line in run.stdout.splitlines()]
                replies=invoke([('tools/list',{}),('tools/call',{'name':'wishlist_add','arguments':{'item':'fsd_injection_basic','kind':'synthesis','qty':2}}),('tools/call',{'name':'preview_material_plan','arguments':{'item':'fsd_injection_basic','kind':'synthesis','qty':2}}),('prompts/get',{'name':'materials_recipe_plan'})])
                self.assertTrue({'preview_material_plan','wishlist_update'}<={t['name'] for t in replies[0]['tools']})
                entry=json.loads(replies[1]['content'][0]['text'])['entry']
                self.assertEqual(json.loads(replies[2]['content'][0]['text'])['entry']['craftable'],1)
                self.assertIn('inventory_known',replies[3]['messages'][0]['content']['text'])
                result=invoke([('tools/call',{'name':'wishlist_update','arguments':{'id':entry['id'],'qty':3}})])[0]
                self.assertFalse(result['isError']);self.assertEqual(self.plan()['entries'][0]['qty'],3)
                for endpoint in ('preview','update'):
                    for headers,status in (({},401),({'Host':'untrusted.invalid'},403)):
                        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                        conn.request('POST','/api/wishlist/'+endpoint,body='{}',headers=headers)
                        r=conn.getresponse();self.assertEqual(r.status,status);r.read();conn.close()
            finally:server.shutdown();server.server_close();thread.join(5)
