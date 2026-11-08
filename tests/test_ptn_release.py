"""PTN release regressions: contradictory scouts and recoverable searches."""
import copy
import http.client
from http.server import ThreadingHTTPServer
import json
import threading
import time
import unittest
from unittest.mock import patch

import test_ptn
from elitelab import mcp
from elitelab.core.http import make_handler


class PTNReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_ptn.PTNTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.desk = self.fixture.desk

    def observation(self, side='buy', changes=None, missing=False, market_id=None, timestamp=None):
        f = self.fixture
        target = f.buy if side == 'buy' else f.sell
        ts = timestamp or f.time()
        f.core.store.update('journal', dict(docked=True, system=target['systemName'], station=target['stationName'],
                                           station_type=target['stationType']))
        item = dict(Name='$liquor_name;', BuyPrice=4000, SellPrice=75000, Stock=500000,
                    Demand=200000, MeanPrice=10000, Producer=True, Consumer=True)
        item.update(changes or {})
        f.core.bus.emit('journal.file.Market', dict(timestamp=ts, MarketID=market_id or target['marketId'],
            StationName=target['stationName'], StarSystem=target['systemName'], Items=[] if missing else [item]))

    def test_new_contradictions_revoke_scout_and_advert_and_valid_capture_recovers(self):
        f = self.fixture
        for side, changes, missing in [('buy', {'Producer': False}, False), ('sell', {'Consumer': False}, False),
                                       ('buy', {}, True), ('buy', {'BuyPrice': 0}, False),
                                       ('sell', {'SellPrice': -1}, False), ('sell', {'SellPrice': None}, False)]:
            with self.subTest(side=side, changes=changes, missing=missing):
                f.carrier(system='Sol')
                f.core.store.set('journal', 'system', 'Sol')
                self.assertTrue(f.confirmed()['operation']['ready'])
                self.observation(side, changes, missing)
                self.assertFalse(self.desk.view()['operation']['ready'])
                self.assertIn(side, self.desk.data['plan']['invalid_scouts'])
                self.assertNotIn(side, self.desk.data['plan']['scouts'])
                with self.assertRaises(ValueError):
                    f.call('prepare_ptn_advert', revision=self.desk.data['revision'])
                saved = f.core.read_data('ptn.json')
                self.assertIn(side, saved['plan']['invalid_scouts'])
                f.capture(side)
                self.assertNotIn(side, self.desk.data['plan']['invalid_scouts'])
                f.mutate('confirm', price=24000, remaining=18000,
                         checks={k: True for k in ('near_station','docking_open','funds_checked','competition_checked')})
                self.assertTrue(self.desk.view()['operation']['ready'])

    def test_wrong_market_old_observation_and_stale_revision_preserve_scout(self):
        f = self.fixture; f.confirmed()
        before = copy.deepcopy(self.desk.data)
        self.observation(changes={'Producer': False}, market_id=999)
        self.observation(changes={'Producer': False}, timestamp=f.time(-2))
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            f.call('capture_ptn_market', revision=before['revision']-1, side='buy')
        self.assertEqual(before, self.desk.data)

    def test_failed_save_keeps_advert_blocked_and_historical_buy_is_preserved(self):
        f = self.fixture; f.confirmed()
        with patch.object(f.core, 'write_data', side_effect=OSError('fixture disk full')):
            self.observation(changes={'Producer': False})
        self.assertFalse(self.desk.view()['operation']['ready'])
        f.capture('buy')
        f.mutate('confirm', price=24000, remaining=18000,
                 checks={k: True for k in ('near_station','docking_open','funds_checked','competition_checked')})
        f.mutate('remaining', remaining=0); f.mutate('stage', stage='transit')
        before = copy.deepcopy(self.desk.data)
        self.observation(changes={'Producer': False})
        self.assertEqual(before, self.desk.data)

    def test_mcp_start_and_poll_are_bounded_while_worker_waits(self):
        f = self.fixture
        entered, release = threading.Event(), threading.Event()
        original = self.desk.scan
        def delayed(prefs):
            entered.set()
            if not release.wait(5):
                raise ValueError('fixture worker was not released')
            return original(prefs)
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(f.core))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        old_cache = dict(mcp._tool_cache)
        self.addCleanup(lambda: (mcp._tool_cache.clear(),mcp._tool_cache.update(old_cache)))
        mcp._tool_cache.clear()
        with patch.object(mcp,'BASE',f'http://127.0.0.1:{server.server_port}'), patch.object(self.desk,'scan',side_effect=delayed):
            try:
                started = time.monotonic()
                result = mcp._call('find_ptn_routes', {})
                self.assertLess(time.monotonic()-started,2)
                self.assertTrue(entered.wait(1))
                status = mcp._call('get_ptn_desk', {})
                self.assertEqual(status['search_job']['id'], result['search_job']['id'])
                self.assertEqual(status['search_job']['status'], 'running')
                with self.assertRaisesRegex(RuntimeError,'already running'):
                    mcp._call('find_ptn_routes', {})
            finally:
                release.set()
                self.assertTrue(self.desk.search_done.wait(5))
            status = mcp._call('get_ptn_desk', {})
            self.assertEqual(status['search_job']['status'],'complete')
            self.assertTrue(status['result']['rows'])
        with patch.object(self.desk,'scan',side_effect=ValueError('Fixture catalog unavailable')):
            self.desk.search({});self.assertTrue(self.desk.search_done.wait(2))
        status = self.desk.view()
        self.assertEqual(status['search_job']['status'],'failed')
        self.assertIn('catalog unavailable',status['search_job']['error'])
        self.assertIsNone(status['result'])
