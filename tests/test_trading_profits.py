"""Profit API: receipts, missing evidence, session scope, separate plan estimates."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core, config, loader
from modules.profits.module import estimate

FIXTURE = Path(__file__).parent / 'fixtures' / 'journals' / 'profits'


class ProfitTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix='elitelab-profits-')
        self.addCleanup(data.cleanup)
        for key, value in (('DATA_DIR', data.name), ('JOURNAL_DIR', str(FIXTURE))):
            p = patch.object(config, key, value)
            p.start(); self.addCleanup(p.stop)
        self.core = Core()
        self.addCleanup(self.core.close)
        loader.load_all(self.core)

    def state(self):
        return self.core.http.tools['get_trading_profits'].fn({})

    def emit(self, event, **values):
        self.core.bus.emit('journal.' + event, {'event': event, 'timestamp': '2026-11-17T12:00:00Z', **values})

    def test_fixture_live_and_replay_and_repeated_replay_agree(self):
        for line in next(FIXTURE.glob('Journal.*.log')).read_text().splitlines():
            ev = json.loads(line)
            self.core.bus.emit('journal.' + ev['event'], ev)
        live = self.state()
        self.assertEqual(live['session']['profit'], 3700)
        self.assertEqual(live['session']['proceeds'], 4700)
        self.assertEqual(live['session']['sold_tons'], 10)
        self.assertEqual(live['session']['sales'], 2)
        self.assertTrue(live['session']['ended'])
        self.assertIsNone(live['estimate'])
        for _ in range(2):
            self.core.watcher.replay()
            self.assertEqual(self.state(), live)

    def test_unsold_purchases_transfers_and_rewards_are_not_profit(self):
        self.emit('LoadGame', Commander='Trader')
        for event in ('MarketBuy', 'CargoTransfer', 'MissionCompleted', 'ReceiveText', 'CarrierTradeOrder'):
            self.emit(event, TotalCost=5000, TotalSale=10000, Reward=1000, Count=100)
        self.assertEqual(self.state()['session']['profit'], 0)
        self.assertEqual(self.state()['session']['sales'], 0)

    def test_zero_purchase_cost_losses_and_same_second_sales(self):
        self.emit('LoadGame', Commander='Trader')
        self.emit('MarketSell', Count=2, TotalSale=50, AvgPricePaid=100)
        self.emit('MarketSell', Count=2, TotalSale=50, AvgPricePaid=100)
        self.assertEqual(self.state()['session']['profit'], -300)
        self.emit('MarketSell', Count=1, TotalSale=200, AvgPricePaid=0)
        self.assertEqual(self.state()['session']['profit'], -100)
        self.assertEqual(self.state()['session']['sales'], 3)

    def test_unknown_cost_never_becomes_zero_or_a_complete_total(self):
        self.emit('MarketSell', Count=1, TotalSale=100, AvgPricePaid=50)
        self.emit('MarketSell', Count=2, TotalSale=1000)
        s = self.state()['session']
        self.assertIsNone(s['profit'])
        self.assertEqual(s['known_profit'], 50)
        self.assertEqual(s['unknown_sales'], 1)
        self.assertIsNone(s['recent'][0]['profit'])
        self.assertTrue(s['partial'])

    def test_malformed_receipts_do_not_invent_margins(self):
        for bad in (None, True, -1, float('nan'), float('inf'), 10**1000, '100'):
            self.emit('LoadGame', Commander='Trader')
            self.emit('MarketSell', Count=1, TotalSale=bad, AvgPricePaid=100)
            self.assertIsNone(self.state()['session']['profit'])
        for bad in (None, True, -1, .5, 0, 10**1000):
            self.emit('LoadGame', Commander='Trader')
            self.emit('MarketSell', Count=bad, TotalSale=100, AvgPricePaid=0)
            self.assertIsNone(self.state()['session']['profit'])
            self.assertIsNone(self.state()['session']['sold_tons'])

    def test_session_reset_commander_identity_continuation_and_shutdown(self):
        self.emit('LoadGame', Commander='Trader', FID='F1')
        self.emit('MarketSell', Count=1, TotalSale=100, AvgPricePaid=20)
        self.emit('FileHeader', part=2)
        self.emit('Commander', Name='Trader', FID='F1')
        self.assertEqual(self.state()['session']['profit'], 80)
        self.emit('Shutdown')
        self.emit('MarketSell', Count=1, TotalSale=999, AvgPricePaid=0)
        self.assertEqual(self.state()['session']['profit'], 80)
        self.emit('Commander', Name='Trader', FID='F2')
        self.assertEqual(self.state()['session']['profit'], 0)
        self.assertTrue(self.state()['session']['partial'])
        self.emit('MarketSell', Count=1, TotalSale=100, AvgPricePaid=20)
        self.emit('LoadGame', Commander='Trader', FID='F2')
        self.assertEqual(self.state()['session']['profit'], 0)
        self.assertFalse(self.state()['session']['partial'])

    def test_recent_receipts_are_bounded_but_totals_are_not(self):
        for _ in range(20):
            self.emit('MarketSell', Count=1, TotalSale=100, AvgPricePaid=20)
        self.assertEqual(len(self.state()['session']['recent']), 10)
        self.assertEqual(self.state()['session']['sales'], 20)
        self.assertEqual(self.state()['session']['profit'], 1600)

    def test_estimates_publish_without_creating_earnings(self):
        self.emit('LoadGame', Commander='Trader')
        self.core.store.update('personal', self.route())
        self.assertEqual(self.state()['estimate']['profit'], 15000)
        self.assertEqual(self.state()['session']['profit'], 0)
        self.core.store.update('personal', {'plan': None, 'progress': None})
        self.assertIsNone(self.state()['estimate'])

    @staticmethod
    def route():
        return {'plan': {'cmdr': 'Trader', 'legs': [{'quantity': 100, 'commodity': 'Gold', 'buy': {'price': 100}, 'sell': {'price': 400}}]},
                'progress': {'leg': 0, 'quantity': 50, 'stage': 'travel_sell'}}

    def test_route_estimate_uses_current_load_and_rejects_changed_commander(self):
        p = self.route()
        self.assertEqual(estimate(p, {}, 'Trader')['profit'], 15000)
        p['progress']['quantity'] = None
        self.assertIsNone(estimate(p, {}, 'Trader')['profit'])
        p['progress']['stage'] = 'buy'
        self.assertEqual(estimate(p, {}, 'Trader')['profit'], 30000)
        self.assertIsNone(estimate(p, {}, 'Other'))
        p['progress']['leg'] = None
        self.assertIsNone(estimate(p, {}, 'Trader'))

    def test_crew_estimate_is_not_acknowledged_earnings_or_owner_transfers(self):
        party = {'desk': {'operation_id': 'job', 'phase': 'loading', 'action': 'deliver', 'load_earnings': 5000, 'earnings': 999999}}
        self.assertEqual(estimate(self.route(), party, 'Trader')['profit'], 5000)
        party['stale'] = True
        self.assertIsNone(estimate(self.route(), party, 'Trader')['profit'])
        party['stale'] = False; party['desk']['owner'] = True
        self.assertIsNone(estimate(self.route(), party, 'Trader')['profit'])


if __name__ == '__main__':
    unittest.main()
