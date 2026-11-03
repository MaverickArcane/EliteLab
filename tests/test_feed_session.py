import unittest
import test_mining

class FeedSessionTests(unittest.TestCase):
    setUp = test_mining.MiningTests.setUp
    emit = test_mining.MiningTests.emit

    def test_session_boundary_does_not_clear_api_feed(self):
        self.emit('MarketBuy', '2026-11-01T12:00:00Z', Type='gold', Count=1, BuyPrice=10)
        self.emit('LoadGame', '2026-11-02T12:00:00Z', Commander='A', FID='F1')
        self.emit('MarketSell', '2026-11-02T12:00:01Z', Type='gold', Count=1, SellPrice=20)
        state = self.core.http.tools['get_commander_state'].fn({})
        self.assertEqual(state['feed_session_start'], '2026-11-02T12:00:00Z')
        self.assertEqual([x['event'] for x in state['feed'][:2]], ['MarketSell', 'MarketBuy'])
