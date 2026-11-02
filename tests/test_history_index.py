"""Persistent history, input bounds, identity isolation and real MCP transport."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_elitelab import Core, config, loader
from elitelab.core.http import make_handler
from modules.history.index import JournalIndex


class HistoryIndexTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="elitelab-history-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.journals = self.root / "journals"; self.journals.mkdir()
        for key, value in (("JOURNAL_DIR",str(self.journals)),("DATA_DIR",str(self.root/"data"))):
            p=patch.object(config,key,value);p.start();self.addCleanup(p.stop)
        self.core=Core();self.addCleanup(self.core.close);loader.load_all(self.core)
        self.path=self.journals/'Journal.2026-10-01T100000.01.log'

    def write(self, events, path=None, mode="w"):
        with (path or self.path).open(mode,encoding="utf-8") as f:
            for e in events:f.write(json.dumps({"timestamp":"2026-10-22T10:00:00Z",**e})+'\n')

    def start(self, fid="F1", name="Miner", credits=1000):
        return {"event":"LoadGame","Commander":name,"FID":fid,"Credits":credits}

    def call(self, tool="get_journal_history", **q):
        return self.core.http.tools[tool].fn(q)

    def history(self, **q):
        return self.call(days=0,**q)

    def test_fixture_analytics_and_existing_travel_contract(self):
        shutil.copyfile(Path(__file__).parent/'fixtures/history'/self.path.name,self.path)
        h=self.history()
        self.assertEqual(len(h['credits']),5)
        self.assertEqual(h['credits'][-1]['credits'],28700000)
        self.assertEqual(h['totals']['merits']['amount'],7500)
        self.assertEqual(h['totals']['material']['amount'],21)
        self.assertEqual(h['materials'][0]['system'],'Leesti')
        self.assertEqual(h['materials'][0]['body'],'Leesti 1')
        travel=self.call('get_travel_history',days=0)
        self.assertEqual([r['name'] for r in travel['route']],['Leesti','Zaonce'])
        self.assertEqual(travel['systems'][-1]['star_class'],'K')
        self.assertEqual(travel['jumps'],1)

    def test_persistence_unchanged_files_and_same_second_append(self):
        self.write([self.start(),{'event':'PowerplayMerits','MeritsGained':10}])
        first=self.history();self.assertEqual(first['index']['files_read'],1)
        self.assertEqual(self.history()['index']['files_read'],0)
        self.write([{'event':'PowerplayMerits','MeritsGained':10}]*2,mode='a')
        self.assertEqual(self.history()['totals']['merits']['amount'],30)
        other=JournalIndex(self.core)
        self.assertEqual(other.refresh()['files_read'],0)
        self.assertEqual(other.refresh()['records'],4)

    def test_rewrite_middle_and_append_invalidates_old_records(self):
        self.write([self.start()]+[{'event':'PowerplayMerits','MeritsGained':10}]*100)
        self.assertEqual(self.history()['totals']['merits']['amount'],1000)
        data=self.path.read_text();at=data.index('"MeritsGained": 10',5000)
        data=data[:at]+data[at:].replace('"MeritsGained": 10','"MeritsGained": 20',1)
        self.path.write_text(data)
        self.write([{'event':'PowerplayMerits','MeritsGained':5}],mode='a')
        self.assertEqual(self.history()['totals']['merits']['amount'],1015)

    def test_truncate_remove_and_event_time_not_mtime(self):
        self.write([self.start(),{'event':'PowerplayMerits','MeritsGained':100}])
        self.history()
        self.write([self.start(credits=500)])
        self.assertNotIn('merits',self.history()['totals'])
        self.assertEqual(self.history()['credits'][0]['credits'],500)
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        self.write([{**self.start(credits=800),'timestamp':now}])
        os.utime(self.path,(1,1))
        self.assertEqual(self.call(days=1)['credits'][0]['credits'],800)
        self.path.unlink()
        self.assertEqual(self.history()['index']['records'],0)

    def test_partial_line_waits_and_bounded_batches_resume(self):
        self.write([self.start()])
        self.history()
        tail=json.dumps({'timestamp':'2026-10-22T10:00:01Z','event':'PowerplayMerits','MeritsGained':12})
        with self.path.open('a') as f:f.write(tail[:30])
        h=self.history();self.assertEqual(h['index']['waiting_files'],1)
        self.assertNotIn('merits',h['totals'])
        with self.path.open('a') as f:f.write(tail[30:]+'\n')
        self.assertEqual(self.history()['totals']['merits']['amount'],12)
        self.write([self.start()]+[{'event':'PowerplayMerits','MeritsGained':1}]*20)
        with patch('modules.history.index.BATCH_BYTES',250):
            result=self.history();self.assertGreater(result['index']['pending_files'],0)
            for _ in range(40):
                result=self.history()
                if not result['index']['pending_files']:break
            self.assertEqual(result['totals']['merits']['amount'],20)
            self.assertEqual(result['index']['pending_files'],0)

    def test_identity_isolation_and_unknown_continuations(self):
        self.write([self.start(),{'event':'PowerplayMerits','MeritsGained':10}])
        other=self.journals/'Journal.2026-10-22T120000.01.log'
        self.write([self.start('F2'),{'event':'PowerplayMerits','MeritsGained':20}],other)
        self.write([{'event':'MaterialCollected','Name':'iron','Count':3}],self.journals/'Journal.2026-10-22T120000.02.log')
        self.core.store.set('journal','cmdr','Miner')
        h=self.history();self.assertTrue(h['selection_required']);self.assertEqual(h['credits'],[])
        self.assertEqual(self.history(commander='fid:F1')['totals']['merits']['amount'],10)
        self.assertEqual(self.history(commander='fid:F2')['totals']['merits']['amount'],20)
        u=self.history(commander='unknown');self.assertEqual(u['materials'][0]['system'],'')

    def test_cycle_boundary_powers_and_daily_last_snapshot(self):
        self.write([self.start(),{'event':'Powerplay','Power':'Edmund Mahon'},
                    {'timestamp':'2026-10-22T06:59:59Z','event':'PowerplayMerits','MeritsGained':7},
                    {'timestamp':'2026-10-22T07:00:00Z','event':'PowerplayMerits','MeritsGained':8},
                    {'timestamp':'2026-10-22T09:00:00+02:00','event':'PowerplayMerits','MeritsGained':2,'Power':'Aisling Duval'},
                    {**self.start(credits=2000),'timestamp':'2026-10-22T20:00:00Z'}])
        h=self.history();self.assertEqual(h['credits'][0]['credits'],2000)
        self.assertEqual({(r['cycle_start'],r['power']):r['merits'] for r in h['merit_cycles']},
                         {('2026-10-15T07:00:00Z','Edmund Mahon'):7,('2026-10-22T07:00:00Z','Edmund Mahon'):8,('2026-10-22T07:00:00Z','Aisling Duval'):2})

    def test_malformed_long_and_nonfinite_records_are_not_trusted(self):
        self.write([self.start(),{'event':'Location','StarSystem':'A','StarPos':[0,0,0]}])
        with self.path.open('a') as f:f.write('{broken}\n'+'x'*2000+'\n')
        self.write([{'event':'MaterialCollected','Name':'iron','Count':3},self.start(),
                    {'event':'PowerplayMerits','MeritsGained':float('nan')},
                    {'event':'MaterialCollected','Name':'gold','Count':True},
                    {'event':'FSDJump','StarSystem':'Bad','StarPos':[10**400,0,0]}],mode='a')
        with patch('modules.history.index.MAX_LINE',1024):h=self.history(commander='unknown')
        self.assertEqual(h['index']['skipped_lines'],2)
        self.assertEqual(h['materials'][0]['system'],'')
        self.assertNotIn('merits',self.history(commander='fid:F1')['totals'])
        json.dumps(h,allow_nan=False)

    def test_literal_sql_filters_and_input_validation(self):
        self.write([self.start(),{'event':'MaterialCollected','Name':'iron','Count':3}])
        self.assertEqual(self.history(material="' OR 1=1 --")['materials'],[])
        self.assertEqual(self.history(material='%')['materials'],[])
        for q in [{'days':-1},{'days':True},{'days':'nan'},{'days':36501},{'material':[]},{'commander':[]}]:
            with self.subTest(q=q),self.assertRaises(ValueError):self.call(**q)
        with self.assertRaises(ValueError):self.call('rebuild_journal_index',path='outside')

    def test_rebuild_corruption_source_change_and_concurrency(self):
        self.write([self.start(),{'event':'PowerplayMerits','MeritsGained':10}]);self.history()
        with ThreadPoolExecutor(max_workers=4) as pool:
            values=list(pool.map(lambda _:self.history()['totals']['merits']['amount'],range(8)))
        self.assertEqual(values,[10]*8)
        db=Path(config.DATA_DIR)/'history.sqlite3';db.write_bytes(b'not sqlite')
        with self.assertRaisesRegex(ValueError,'index unavailable'):self.history()
        self.call('rebuild_journal_index')
        self.assertEqual(self.history()['totals']['merits']['amount'],10)
        self.assertEqual(len(list(db.parent.glob('history.sqlite3.backup-*'))),1)
        empty=self.root/'other';empty.mkdir()
        with patch.object(config,'JOURNAL_DIR',str(empty)):
            self.assertEqual(JournalIndex(self.core).refresh()['records'],0)
        self.assertTrue(self.path.exists())

    def test_symlinked_journals_outside_configured_folder_are_excluded(self):
        external=self.root/'outside.log';external.write_text('{}\n')
        try:self.path.symlink_to(external)
        except OSError:self.skipTest('Symlinks require Windows privileges')
        self.assertEqual(self.history()['index']['files'],0)

    def test_authenticated_mcp_history_and_http_boundaries(self):
        self.write([self.start(),{'event':'PowerplayMerits','MeritsGained':12}])
        with patch.object(config,'AUTH_TOKEN','history-test-token'):
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.core));server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                calls=[('tools/list',{}),('tools/call',{'name':'get_journal_history','arguments':{'days':0}}),
                       ('tools/call',{'name':'get_journal_index'}),('tools/call',{'name':'rebuild_journal_index'}),
                       ('resources/read',{'uri':'elitelab://state/history'}),('tools/call',{'name':'get_journal_history','arguments':{'days':-1}}),
                       ('prompts/get',{'name':'journal_history'})]
                messages=''.join(json.dumps({'jsonrpc':'2.0','id':i,'method':m,'params':q})+'\n' for i,(m,q) in enumerate(calls))
                env=dict(os.environ,ELITELAB_URL=f'http://127.0.0.1:{server.server_port}',ELITELAB_AUTH_TOKEN='history-test-token')
                run=subprocess.run([sys.executable,'-m','elitelab','mcp'],cwd=config.ROOT,env=env,input=messages,capture_output=True,text=True,timeout=20,check=True)
                replies=[json.loads(line)['result'] for line in run.stdout.splitlines()]
                self.assertTrue({'get_journal_history','get_journal_index','rebuild_journal_index'} <= {t['name'] for t in replies[0]['tools']})
                self.assertEqual(json.loads(replies[1]['content'][0]['text'])['totals']['merits']['amount'],12)
                for i in (1,2,3):self.assertFalse(replies[i]['isError'])
                self.assertIn('index',json.loads(replies[4]['contents'][0]['text']))
                self.assertTrue(replies[5]['isError'])
                self.assertIn('get_journal_history',replies[6]['messages'][0]['content']['text'])
                import http.client
                for method,path in [('GET','/api/history/analytics'),('GET','/api/history/index'),('POST','/api/history/rebuild')]:
                    for headers,expected in [({},401),({'Host':'attacker.invalid'},403)]:
                        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                        conn.request(method,path,body='{}' if method=='POST' else None,headers=headers)
                        response=conn.getresponse();self.assertEqual(response.status,expected);response.read();conn.close()
            finally:server.shutdown();server.server_close();thread.join(5)
