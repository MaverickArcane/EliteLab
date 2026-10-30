"""Regression tests for audit findings and the transport boundary."""
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_elitelab import ROOT, make_core
from elitelab.core import Core, config
from elitelab.core.bus import EventBus
from elitelab.core.http import make_handler
from elitelab.core.watcher import JournalWatcher


class WatcherTests(unittest.TestCase):
    def test_replay_boundary_consumes_only_complete_read_lines(self):
        for during_replay in (False, True):
            with self.subTest(during_replay=during_replay), tempfile.TemporaryDirectory() as tmp:
                with patch.object(config, 'JOURNAL_DIR', tmp):
                    path = Path(tmp, 'Journal.1.log')
                    path.write_bytes(b'{"event":"First"}\n' + (b'' if during_replay else b'{"event":"Sec'))
                    bus = EventBus()
                    seen = []
                    bus.on('journal.*', lambda n, e: seen.append(n))
                    def append(n, ev):
                        with path.open('ab') as f:
                            f.write(b'{"event":"Second"}\n')
                    if during_replay:
                        bus.on('journal.First', append)
                    watcher = JournalWatcher(bus)
                    watcher.replay()
                    if not during_replay:
                        with path.open('ab') as f:
                            f.write(b'ond"}\n')
                    watcher._tick()
                    watcher._tick()
                    self.assertEqual(seen, ['journal.First', 'journal.replay.done', 'journal.Second'])


class IsolatedCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = patch.object(config, 'DATA_DIR', self.tmp.name)
        self.data.start()
        self.addCleanup(self.data.stop)
        self.core = make_core()
        self.addCleanup(self.core.close)

    def call(self, name, **args):
        return self.core.http.tools[name].fn(args)

    def emit(self, event, **data):
        self.core.bus.emit('journal.' + event, {'event': event, **data})

    def test_wishlist_rejection_preserves_memory_store_and_disk(self):
        self.call('set_wishlist', items={'arsenic': 10})
        before = self.call('get_wishlist')
        state = self.core.store.get('materials')
        disk = Path(self.tmp.name, 'wishlist.json').read_bytes()
        for args in ({'items': {'iron': 3, 'arsenic': 'oops'}}, {'items': []},
                     {'items': False}, {'items': {'arsenic': None}}, {'items': {}, 'mode': 'typo'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.call('set_wishlist', **args)
            self.assertEqual(self.call('get_wishlist'), before)
            self.assertEqual(self.core.store.get('materials'), state)
            self.assertEqual(Path(self.tmp.name, 'wishlist.json').read_bytes(), disk)
        with patch.object(self.core, 'write_data', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.call('set_wishlist', items={'iron': 1})
        self.assertEqual(self.call('get_wishlist'), before)

    def test_concurrent_wishlist_additions_are_not_lost(self):
        self.call('set_wishlist', items={}, mode='clear')
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: self.call('set_wishlist', items={'iron': 1}, mode='add'), range(40)))
        self.assertEqual(self.call('get_wishlist')['wishlist'][0]['need'], 40)
        self.assertEqual(self.core.read_data('wishlist.json')['iron']['need'], 40)
        self.assertEqual(self.core.store.get('materials', 'wishlist')['iron']['need'], 40)

    def test_location_snapshot_supersedes_docking_state(self):
        self.emit('Docked', StarSystem='Old', StationName='Old station', StationType='Orbis')
        self.emit('Location', StarSystem='New', Docked=False, StarPos=[0, 0, 0])
        state = self.call('get_commander_state')
        self.assertFalse(state['docked'])
        self.assertIsNone(state['station'])
        self.assertIsNone(state['station_type'])
        self.emit('Location', StarSystem='New', Docked=True, StationName='New station', StationType='Outpost')
        self.assertTrue(self.call('get_commander_state')['docked'])
        self.assertEqual(self.call('get_commander_state')['station'], 'New station')

    def test_long_session_merits_and_hour_window(self):
        now = 1800000000
        timestamp = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        with patch('time.time', return_value=now):
            self.emit('LoadGame', timestamp=timestamp(now - 7200))
            self.emit('PowerplayMerits', timestamp=timestamp(now - 4000), MeritsGained=11)
            total = 11
            for i in range(501):
                n = i % 7 + 1
                total += n
                self.emit('PowerplayMerits', timestamp=timestamp(now - 1), MeritsGained=n, TotalMerits=total)
            summary = self.call('get_merits_summary')
            self.assertEqual(summary['session_merits'], total)
            self.assertEqual(summary['unattributed'], total)
            self.assertEqual(summary['last_hour'], total - 11)
            self.assertEqual(summary['by_activity']['unattributed']['events'], 502)
            self.assertEqual(len(summary['recent']), 15)
            self.emit('LoadGame', timestamp=timestamp(now))
            self.assertEqual(self.call('get_merits_summary')['session_merits'], 0)
            self.assertEqual(self.call('get_merits_summary')['last_hour'], 0)

    def test_loop_recomputes_once_for_location_snapshot(self):
        seen = []
        self.core.bus.on('state.journal.location', lambda n, v: seen.append(n))
        self.emit('Location', StarSystem='Leesti', Docked=True, StarPos=[1, 2, 3])
        self.assertEqual(len(seen), 1)
        loop = self.call('get_rares_loop')
        self.assertTrue(next(s for s in loop['stations'] if s['system'] == 'Leesti')['docked_here'])


class TransportTests(IsolatedCoreTests):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.core))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port

    def request(self, method, path, body=None, headers=None, conn=None):
        own = conn is None
        conn = conn or http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.read()
        if own:
            conn.close()
        return result

    def test_cross_origin_writes_blocked_and_same_origin_allowed(self):
        self.call('set_wishlist', items={'arsenic': 10})
        body = json.dumps({'items': {}, 'mode': 'clear'})
        for headers, status in [
            ({'Content-Type': 'text/plain', 'Origin': 'https://unrelated.example'}, 403),
            ({'Content-Type': 'application/json', 'Origin': 'null'}, 403),
            ({'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:1'}, 403),
            ({'Content-Type': 'application/x-www-form-urlencoded'}, 415),
            ({'Content-Type': 'application/json', 'Sec-Fetch-Site': 'cross-site'}, 403),
        ]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('POST', '/api/materials/wishlist', body, headers)[0], status)
                self.assertEqual(self.call('get_wishlist')['wishlist'][0]['need'], 10)
        for origin in (None, f'http://127.0.0.1:{self.port}'):
            headers = {'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = origin
            self.assertEqual(self.request('POST', '/api/materials/wishlist', body, headers)[0], 200)

    def test_keepalive_invalid_wishlist_and_static_guard(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        self.addCleanup(conn.close)
        self.call('set_wishlist', items={'arsenic': 10})
        status, _ = self.request('POST', '/api/materials/wishlist', '{"items":{"iron":3,"arsenic":"oops"}}',
                                 {'Content-Type': 'application/json'}, conn)
        self.assertEqual(status, 400)
        status, body = self.request('GET', '/api/materials/wishlist', conn=conn)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['wishlist'][0]['key'], 'arsenic')
        self.assertEqual(self.request('GET', '/%2e%2e/elitelab/core/config.py')[0], 404)

    def test_sse_snapshot_framing(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request('GET', '/events')
        response = conn.getresponse()
        self.addCleanup(response.close)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.fp.readline(), b'event: snapshot\n')
        state = json.loads(response.fp.readline().decode()[6:])
        self.assertEqual(state['journal']['cmdr'], 'Testpilot')
        self.assertEqual(response.fp.readline(), b'\n')

    def test_mcp_stdio_handshake_tools_and_call(self):
        from elitelab.mcp import SUPPORTED_PROTOCOLS, PROTOCOL
        env = {**os.environ, 'ELITELAB_URL': f'http://127.0.0.1:{self.port}'}
        messages = [{'jsonrpc': '2.0', 'id': i, 'method': 'initialize', 'params': {'protocolVersion': version}}
                    for i, version in enumerate((*SUPPORTED_PROTOCOLS, 'unknown'))]
        messages.extend([{'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                         {'jsonrpc': '2.0', 'id': 90, 'method': 'tools/list'},
                         {'jsonrpc': '2.0', 'id': 91, 'method': 'tools/call', 'params': {'name': 'health'}}])
        run = subprocess.run([sys.executable, '-m', 'elitelab', 'mcp'], input='\n'.join(map(json.dumps, messages)) + '\n',
                             capture_output=True, text=True, env=env, cwd=ROOT, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        replies = {m['id']: m for m in map(json.loads, run.stdout.splitlines())}
        for i, version in enumerate((*SUPPORTED_PROTOCOLS, PROTOCOL)):
            self.assertEqual(replies[i]['result']['protocolVersion'], version)
        self.assertTrue(any(t['name'] == 'health' for t in replies[90]['result']['tools']))
        self.assertTrue(json.loads(replies[91]['result']['content'][0]['text'])['ok'])


if __name__ == '__main__':
    unittest.main()
