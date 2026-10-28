"""Spansh trades: exact loops, full-load eligibility and bounded discovery."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import copy
import unittest
from modules.personal.module import Personal


class PersonalTests(unittest.TestCase):
    def setUp(self):
        self.journal = {'system': 'Sol', 'cargo_capacity': 100, 'jump_range_laden': 20, 'credits': 10000}
        self.now = datetime.now(timezone.utc).isoformat()
        self.origin = self.station(1, 'Sol', 0, [self.item('Gold', 100, 0), self.item('Silver', 0, 300)])
        self.other = self.station(2, 'Alpha', 39, [self.item('Gold', 0, 400), self.item('Silver', 500, 0)])
        self.third = self.station(3, 'Beta', 41, [self.item('Gold', 0, 300), self.item('Silver', 100, 0)])
        self.locals, self.nearby = [self.origin], [self.other, self.third]
        self.calls = []
        self.core = SimpleNamespace(config=SimpleNamespace(OFFLINE=False), store=SimpleNamespace(get=lambda ns: self.journal),
                                    services=SimpleNamespace(fetch_json=self.fetch))
        self.desk = Personal(self.core)

    def item(self, name, buy, sell, **extra):
        return dict(commodity=name, buy_price=buy, sell_price=sell, supply=1000, demand=1000, **extra)

    def station(self, mid, system, x, market):
        return dict(market_id=mid, name='Port '+str(mid), system_name=system, type='Dodec Starport',
                    has_market=True, has_large_pad=True, distance_to_arrival=100, market_updated_at=self.now,
                    system_x=x, system_y=0, system_z=0, market=market)

    def fetch(self, url, body=None, ttl=None):
        self.calls.append((url, body))
        if body['filters']['distance']['max'] == 0.001 and body['reference_system'] == 'Sol':
            return {'count': len(self.locals), 'results': self.locals}
        return {'count': len(self.nearby), 'results': self.nearby}

    def test_exact_loop_not_two_hops_and_independent_return_commodity(self):
        result = self.desk.search({})
        self.assertEqual(len(result['rows']), 1)  # Alpha has no profitable return.
        row = result['rows'][0]
        self.assertEqual([l['commodity'] for l in row['legs']], ['Gold', 'Silver'])
        self.assertEqual([l['buy']['market_id'] for l in row['legs']], [1, 3])
        self.assertEqual([l['sell']['market_id'] for l in row['legs']], [3, 1])
        self.assertEqual(row['profit'], 40000)
        self.assertEqual(row['cost'], 20000)
        self.assertEqual(row['required_credits'], 10000)
        self.assertEqual(row['return_on_cost'], 200)
        self.assertEqual(result['settings']['quantity'], 100)
        self.assertIn('Spansh', result['source'])

    def test_one_way_keeps_destination_and_laden_jump_filter(self):
        result = self.desk.search({'route_type': 'one_way', 'distance_mode': 'jumps', 'jumps': 2})
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['rows'][0]['sell']['system'], 'Alpha')
        self.assertEqual(result['rows'][0]['estimated_jumps'], 2)
        self.assertEqual(len(result['rows'][0]['legs']), 1)
        self.assertEqual(self.desk.search({'destination': 'bEtA'})['rows'][0]['sell']['system'], 'Beta')
        self.assertFalse(self.desk.search({'destination': 'Missing'})['rows'])
        self.assertFalse(self.desk.search({'station': 'Missing'})['rows'])
        self.assertTrue(self.desk.search({'station': 'pOrT 1'})['rows'])

    def test_return_to_exact_station_not_another_station_in_same_system(self):
        self.origin['market'][1]['sell_price'] = 0
        self.locals.append(self.station(4, 'Sol', 0, [self.item('Silver', 0, 900)]))
        self.assertFalse(self.desk.search({})['rows'])

    def test_starting_funds_account_for_outbound_profit(self):
        self.third['market'][1]['buy_price'] = 1000
        self.origin['market'][1]['sell_price'] = 1200
        row = self.desk.search({'destination': 'Beta'})['rows'][0]
        self.assertEqual(row['required_credits'], 80000)  # 100k return purchase minus 20k earned outbound.

    def test_fractional_radius_and_same_market_exclusion(self):
        self.third['system_x'] = 40.21
        self.assertFalse(self.desk.search({'distance': 40.2})['rows'])
        self.third['market_id'] = 1
        self.assertFalse(self.desk.search({})['rows'])

    def test_invalid_station_reports_filtered(self):
        base = copy.deepcopy(self.third)
        bad = [{'type':'Drake-Class Carrier'}, {'carrier_name':'Carrier'}, {'name':'Stronghold Carrier'},
               {'system_x':None}, {'system_x':True}, {'market_id':True}, {'has_large_pad':False},
               {'market_updated_at':'bad'}, {'market_updated_at':'2026-01-01'},
               {'market_updated_at':(datetime.now(timezone.utc)-timedelta(days=4)).isoformat()},
               {'market_updated_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},
               {'distance_to_arrival':10001}, {'is_planetary':True}]
        for patch in bad:
            with self.subTest(patch=patch):
                self.nearby = [{**base, **patch}]
                self.assertFalse(self.desk.search({})['rows'])

    def test_full_load_price_and_rare_filters_on_both_legs(self):
        for side, index, key, value in [('nearby',1,'supply',99), ('nearby',0,'demand',0),
                                      ('local',1,'demand',99), ('local',0,'supply',99),
                                      ('nearby',1,'buy_price',float('nan')), ('nearby',0,'sell_price',True),
                                      ('nearby',1,'is_rare',True)]:
            with self.subTest(key=key,side=side):
                self.setUp()
                target = self.third if side == 'nearby' else self.origin
                target['market'][index][key] = value
                self.assertFalse(self.desk.search({})['rows'])

    def test_surface_and_pad_filters_are_enforced_locally(self):
        self.third.update(type='Planetary Port', is_planetary=True)
        self.assertFalse(self.desk.search({})['rows'])
        self.assertTrue(self.desk.search({'surface':'1'})['rows'])
        self.third.update(type='Outpost', is_planetary=False, has_large_pad=False, medium_pads=1)
        self.assertTrue(self.desk.search({'pad':'M'})['rows'])

    def test_selected_commodity_only_restricts_outbound(self):
        self.origin['market'][0]['commodity'] = 'HN Shock Mount'
        self.third['market'][0]['commodity'] = 'HN Shock Mount'
        r = self.desk.search({'commodity':'hnshockmount'})
        self.assertEqual(r['rows'][0]['legs'][1]['commodity'], 'Silver')
        self.assertEqual(r['commodities'][0], {'key':'hnshockmount','name':'HN Shock Mount'})
        self.assertFalse(self.desk.search({'commodity':'missing'})['rows'])

    def test_unknown_range_and_validation_before_io(self):
        for q in ({'quantity':True},{'quantity':1.5},{'distance':'nan'},{'distance':501},{'breadth':301},
                  {'hours':0},{'pad':'X'},{'origin':123},{'commodity':'../gold'},{'surface':'yes'},
                  {'arrival':-1},{'route_type':'loopish'},{'distance_mode':'bad'}):
            with self.subTest(q=q), self.assertRaises(ValueError):
                self.desk.search(q)
        self.assertFalse(self.calls)
        self.journal['jump_range_laden'] = None
        with self.assertRaisesRegex(ValueError,'range is unknown'):
            self.desk.search({'distance_mode':'jumps'})
        self.assertIsNone(self.desk.search({})['rows'][0]['estimated_jumps'])

    def test_origin_must_match_and_empty_search_stops_early(self):
        self.origin['system_name'] = 'Wrong'
        r = self.desk.search({})
        self.assertFalse(r['rows'])
        self.assertEqual(len(self.calls),1)
        self.assertTrue(r['warnings'])

    def test_offline_and_network_failure(self):
        self.core.config.OFFLINE = True
        with self.assertRaisesRegex(ValueError,'offline'):
            self.desk.search({})
        self.assertFalse(self.calls)
        self.core.config.OFFLINE = False
        def fail(*a,**kw):
            raise OSError('network unavailable')
        self.core.services.fetch_json = fail
        with self.assertRaisesRegex(ValueError,'Spansh markets unavailable'):
            self.desk.search({})

    def test_bounded_pages_and_visible_partial_failure(self):
        original = self.fetch
        def paged(url, body=None, ttl=None):
            if body['filters']['distance']['max'] == 0.001:
                return original(url,body,ttl)
            if body['page'] == 1:
                raise OSError('second page unavailable')
            return {'count':250,'results':[self.third]*100}
        self.core.services.fetch_json = paged
        r = self.desk.search({'breadth':200})
        self.assertEqual(len(r['rows']),1)
        self.assertEqual(r['screened'],100)
        self.assertEqual(r['available'],250)
        self.assertTrue(any('partial' in w for w in r['warnings']))


if __name__ == '__main__':
    unittest.main()
