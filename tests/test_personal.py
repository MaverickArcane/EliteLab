"""Personal routes use local supply and nearby demand, never carrier capacity."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from urllib.parse import urlparse, parse_qs

from modules.personal.module import Personal


class PersonalTests(unittest.TestCase):
    def setUp(self):
        self.journal = {"system": "Sol", "star_pos": [0, 0, 0], "cargo_capacity": 100,
                        "jump_range_laden": 20, "jump_range_now": 40, "credits": 100000,
                        "carrier": {"system": "Lave", "free_space": 20000}}
        self.now = datetime.now(timezone.utc).isoformat()
        self.exports = [self.quote(1, "Sol", 0, buyPrice=100), self.quote(2, "Sol", 0, buyPrice=110)]
        self.imports = [self.quote(3, "Alpha", 39, sellPrice=300), self.quote(4, "Beta", 41, sellPrice=400)]
        self.calls = []
        self.core = SimpleNamespace(config=SimpleNamespace(OFFLINE=False),
            store=SimpleNamespace(get=lambda ns: self.journal),
            services=SimpleNamespace(fetch_json=self.fetch, edsm_coords=lambda names: {names[0]: {"x": 10, "y": 0, "z": 0}}))
        self.desk = Personal(self.core)

    def quote(self, mid, system, x, **extra):
        return {"commodityName": "gold", "marketId": mid, "stationName": "Port " + str(mid),
                "stationType": "Coriolis", "systemName": system, "systemX": x, "systemY": 0, "systemZ": 0,
                "buyPrice": 0, "sellPrice": 0, "stock": 1000, "demand": 1000, "maxLandingPadSize": 3,
                "updatedAt": self.now, **extra}

    def fetch(self, url, ttl):
        self.calls.append(url)
        if url.endswith('/v2/commodities'):
            return [{"commodityName": "gold", "minBuyPrice": 10, "maxSellPrice": 500}]
        if '/commodities/exports?' in url:
            return self.exports
        if '/nearby/imports?' in url:
            return self.imports
        raise AssertionError(url)

    def test_local_supply_nearby_buyers_profit_and_ship_defaults(self):
        self.exports.append(self.quote(10, "Elsewhere", 1, buyPrice=1))
        result = self.desk.search({})
        self.assertEqual(result['settings']['origin'], 'Sol')
        self.assertEqual(result['settings']['quantity'], 100)
        self.assertEqual([r['profit'] for r in result['rows']], [30000, 20000])
        self.assertEqual(result['rows'][0]['buy']['market_id'], 1)
        self.assertEqual(result['rows'][0]['cost'], 10000)
        self.assertTrue(any('/system/name/Sol/commodity/name/gold/nearby/imports?' in u for u in self.calls))

    def test_jump_limit_uses_laden_range_and_optional_destination(self):
        result = self.desk.search({'distance_mode': 'jumps', 'jumps': 2})
        self.assertEqual(result['settings']['distance'], 40)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['estimated_jumps'], 2)
        self.assertEqual(self.desk.search({'destination': 'bEtA'})['rows'][0]['sell']['system'], 'Beta')
        self.assertFalse(self.desk.search({'destination': 'Missing'})['rows'])

    def test_exact_fractional_radius_rechecks_rounded_api_limit(self):
        self.imports[0]['systemX'] = 40.21
        result = self.desk.search({'distance': 40.2})
        self.assertFalse(result['rows'])
        params = parse_qs(urlparse(self.calls[-1]).query)
        self.assertEqual(params['maxDistance'], ['41'])

    def test_filters_age_volume_pad_carriers_coordinates_and_bad_prices(self):
        base = self.imports[0]
        bad = [{"demand": 99}, {"maxLandingPadSize": 2}, {"stationType": "FleetCarrier"},
               {"stationType": "StrongholdCarrier"}, {"systemX": None}, {"sellPrice": float('nan')},
               {"sellPrice": True}, {"marketId": None}, {"updatedAt": "bad"},
               {"updatedAt": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()},
               {"updatedAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}]
        self.imports = [{**base, **patch} for patch in bad] + [base]
        self.assertEqual(len(self.desk.search({})['rows']), 1)

    def test_same_market_and_losses_are_excluded(self):
        self.imports = [self.quote(1, 'Sol', 0, sellPrice=105), self.quote(5, 'Sol', 0, sellPrice=99)]
        self.assertFalse(self.desk.search({})['rows'])

    def test_custom_origin_and_unknown_coordinates(self):
        self.exports[0].update(systemName='Custom', systemX=10)
        result = self.desk.search({'origin': 'Custom', 'quantity': 50})
        self.assertEqual(result['rows'][0]['quantity'], 50)
        self.assertEqual(result['rows'][0]['distance'], 31)
        self.core.services.edsm_coords = lambda names: {}
        with self.assertRaisesRegex(ValueError, 'Coordinates unavailable'):
            self.desk.search({'origin': 'Unknown'})

    def test_unknown_laden_range_never_substitutes_unladen(self):
        self.journal['jump_range_laden'] = None
        with self.assertRaisesRegex(ValueError, 'range is unknown'):
            self.desk.search({'distance_mode': 'jumps'})
        self.assertIsNone(self.desk.search({})['rows'][0]['estimated_jumps'])

    def test_invalid_inputs_rejected_before_network(self):
        for params in ({'quantity': True}, {'quantity': 1.5}, {'distance': 'nan'}, {'distance': 501},
                       {'distance_mode': 'invalid'}, {'hours': 0}, {'breadth': 49}, {'origin': 123},
                       {'commodity': '../gold'}, {'pad': 'X'}, {'jumps': 1.5, 'distance_mode': 'jumps'}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.desk.search(params)
        self.assertEqual(self.calls, [])
        self.journal['jump_range_laden'] = 100
        with self.assertRaisesRegex(ValueError, '500 Ly'):
            self.desk.search({'distance_mode': 'jumps', 'jumps': 6})

    def test_no_local_supply_does_not_search_unavailable_commodities(self):
        self.exports = []
        result = self.desk.search({})
        self.assertFalse(result['rows'])
        self.assertEqual(result['screened'], 0)
        self.assertFalse(any('/nearby/' in url for url in self.calls))

    def test_network_failure_is_visible_and_offline_does_no_io(self):
        def failing(url, ttl):
            if '/nearby/' in url:
                raise OSError('network down')
            return self.fetch(url, ttl)
        self.core.services.fetch_json = failing
        result = self.desk.search({})
        self.assertFalse(result['rows'])
        self.assertEqual(len(result['warnings']), 1)
        self.calls.clear()
        self.core.config.OFFLINE = True
        with self.assertRaisesRegex(ValueError, 'offline'):
            self.desk.search({})
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main()
