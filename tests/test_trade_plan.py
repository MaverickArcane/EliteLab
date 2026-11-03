"""Selected trade route: ids, persistence, and progress from docking, cargo and recorded sales."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

import test_mining
from test_elitelab import config
from modules.personal import plan as planning


def iso(offset_seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat().replace('+00:00', 'Z')


class TradePlanTests(unittest.TestCase):
    emit = test_mining.MiningTests.emit

    def setUp(self):
        test_mining.MiningTests.setUp(self)
        self.core.watcher.replay()      # Testpilot, known cargo, old market events that must not count

    def station(self, mid, system, x, market, age_hours=0):
        when = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
        return dict(market_id=mid, name='Port ' + str(mid), system_name=system, type='Coriolis Starport', has_market=True,
                    has_large_pad=True, distance_to_arrival=100, market_updated_at=when, system_x=x, system_y=0, system_z=0, market=market)

    def markets(self, age_hours=0):
        item = lambda name, buy, sell: dict(commodity=name, buy_price=buy, sell_price=sell, supply=1000, demand=1000)
        origin = self.station(1, 'Sol', 0, [item('Gold', 100, 0), item('Silver', 0, 300)], age_hours)
        other = self.station(2, 'Alpha', 39, [item('Gold', 0, 400), item('Silver', 200, 0)], age_hours)
        return origin, other

    def search(self, age_hours=0, **extra):
        origin, other = self.markets(age_hours)

        def fetch(url, body=None, ttl=None):
            local = body['filters']['distance']['max'] == 0.001 and body['reference_system'] == 'Sol'
            return {'count': 1, 'results': [origin] if local else [other]}

        with patch.object(config, 'OFFLINE', False), patch.object(self.core.services, 'fetch_json', fetch):
            return self.core.http.tools['find_personal_trade_routes'].fn({'origin': 'Sol', 'quantity': 100, 'hours': 72, **extra})

    def select(self, **extra):
        result = self.search(**extra)
        return self.core.http.tools['select_trade_route'].fn({'id': result['rows'][0]['id']})

    def state(self):
        return self.core.http.tools['get_trade_plan'].fn({})

    def dock(self, system, station, stamp=None):
        self.emit('Docked', stamp or iso(), StarSystem=system, StationName=station)

    def cargo(self, **goods):
        inventory = [{'Name': k, 'Name_Localised': k.title(), 'Count': v} for k, v in goods.items()]
        self.core.bus.emit('journal.file.Cargo', {'Count': sum(goods.values()), 'timestamp': iso(), 'Inventory': inventory})

    def test_local_market_commodity_evidence_is_bounded_and_scoped(self):
        selected = self.select()
        buy = selected['plan']['legs'][0]['buy']
        self.dock(buy['system'], buy['station'])
        self.core.bus.emit('journal.file.Market', {'event':'Market','timestamp':iso(), 'MarketID':buy['market_id'],
            'StarSystem':buy['system'],'StationName':buy['station'],'Items':[
                {'Name':'$gold_name;','Name_Localised':'Gold','BuyPrice':125,'SellPrice':0,'Stock':0,'Demand':None},
                {'Name':'$silver_name;','Name_Localised':'<script>','BuyPrice':float('nan'),'SellPrice':250,'Stock':None,'Demand':7}]})
        market = self.core.http.tools['get_commander_state'].fn({})['market']
        self.assertEqual(market['market_id'], buy['market_id'])
        self.assertEqual(market['commodities'][0], {'key':'gold','name':'Gold','buy':125,'sell':0,'stock':0,'demand':None})
        self.assertEqual(market['commodities'][1]['buy'], None)
        self.assertEqual(market['commodities'][1]['name'], '<script>')
        self.assertEqual(self.core.http.tools['get_rares_loop'].fn({})['workflow']['market']['status'],'current_snapshot')
        json.dumps(market, allow_nan=False)
        self.core.bus.emit('journal.file.Market', {'timestamp':iso(),'MarketID':999,'StarSystem':buy['system'],
            'StationName':buy['station'],'Items':[{'Name':'gold','BuyPrice':200,'Stock':40}]})
        self.assertNotEqual(self.core.store.get('journal','market')['market_id'],buy['market_id'])
        self.core.bus.emit('journal.file.Market', {'timestamp':iso(),'MarketID':buy['market_id'],'StarSystem':buy['system'],
            'StationName':buy['station'],'Items':[{'Name':f'item{i}','BuyPrice':i} for i in range(513)]})
        market = self.core.store.get('journal','market')
        self.assertEqual(len(market['commodities']),512)
        self.assertTrue(market['commodities_truncated'])

    def test_rows_carry_stable_ids_and_stop_positions(self):
        first, second = self.search(), self.search()
        row = first['rows'][0]
        self.assertRegex(row['id'], r'^[0-9a-f]{16}$')
        self.assertEqual(row['id'], second['rows'][0]['id'])
        self.assertEqual([l['buy']['pos'] for l in row['legs']], [[0, 0, 0], [39, 0, 0]])
        self.assertNotEqual(row['id'], planning.route_id({**row, 'quantity': 50}))

    def test_selection_persists_across_restart_and_clears(self):
        self.assertEqual({k:self.state()[k] for k in ('plan','progress')}, {'plan': None, 'progress': None})
        selected = self.select()
        self.assertEqual([l['commodity'] for l in selected['plan']['legs']], ['Gold', 'Silver'])
        self.assertEqual(selected['plan']['cmdr'], 'Test Miner')
        self.assertEqual(selected['progress']['stage'], 'travel_buy')
        saved = json.loads(open(self.core.data_path('personal.json'), encoding='utf-8').read())
        self.assertEqual(saved['plan']['id'], selected['plan']['id'])
        from elitelab.core import Core, loader
        again = Core()
        self.addCleanup(again.close)
        loader.load_all(again)
        self.assertEqual(again.http.tools['get_trade_plan'].fn({})['plan']['id'], selected['plan']['id'])
        self.assertEqual(again.http.tools['get_trade_plan'].fn({})['progress']['stage'], 'travel_buy')
        cleared = self.core.http.tools['clear_trade_route'].fn({})
        self.assertEqual({k:cleared[k] for k in ('plan','progress')}, {'plan': None, 'progress': None})
        self.assertIsNone(json.loads(open(self.core.data_path('personal.json'), encoding='utf-8').read())['plan'])

    def test_invalid_selection_and_failed_save_preserve_the_previous_plan(self):
        select = self.core.http.tools['select_trade_route'].fn
        for value in (None, [], {}, '', 'unknown', '../../escape'):
            with self.assertRaises(ValueError):
                select({'id': value})
        chosen = self.select()['plan']['id']
        result = self.search(quantity=50)
        with patch.object(self.core, 'write_data', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                select({'id': result['rows'][0]['id']})
        self.assertEqual(self.state()['plan']['id'], chosen)
        with self.assertRaises(ValueError):
            select({'id': chosen})      # no longer in the latest search

    def test_progress_follows_docking_cargo_and_recorded_sales(self):
        self.select()
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['next']['station'], p['next']['role'], p['leg']), ('travel_buy', 'Port 1', 'buy', 0))
        self.assertFalse(p['cargo_known'])
        self.cargo()
        self.assertTrue(self.state()['progress']['cargo_known'])
        self.dock('Sol', 'Port 1')
        self.cargo(gold=40)
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['quantity'], p['next']['docked_here']), ('buy', 60, True))
        self.assertIn('40 t already aboard', p['reason'])
        self.cargo(gold=100)
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['next']['station'], p['next']['system'], p['quantity']), ('travel_sell', 'Port 2', 'Alpha', 100))
        self.assertIn('Then buy Silver', p['reason'])
        self.dock('Alpha', 'Port 2')
        self.assertEqual(self.state()['progress']['stage'], 'sell')
        self.emit('MarketSell', iso(), MarketID=2, Type='gold', Type_Localised='Gold', Count=100, SellPrice=400, TotalSale=40000)
        p = self.state()['progress']
        self.assertEqual((p['leg'], p['stage'], p['legs'][0]['done'], p['legs'][0]['sold'], p['legs'][0]['sale_total']), (1, 'buy', True, 100, 40000))
        self.assertEqual(p['action'], 'Buy 100 t Silver')
        self.cargo(silver=100)
        self.dock('Sol', 'Port 1')
        self.emit('MarketSell', iso(), MarketID=1, Type='silver', Type_Localised='Silver', Count=100, SellPrice=300, TotalSale=30000)
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['leg'], p['next']), ('complete', None, None))
        self.assertIn('70,000 Cr', p['reason'])
        json.dumps(self.state(), allow_nan=False)

    def test_partial_sale_with_an_empty_hold_completes_the_leg(self):
        self.select(route_type='one_way')
        self.cargo(gold=100)
        self.dock('Alpha', 'Port 2')
        self.emit('MarketSell', iso(), MarketID=2, Type='gold', Type_Localised='Gold', Count=60, SellPrice=400, TotalSale=24000)
        p = self.state()['progress']
        self.assertEqual(p['stage'], 'sell')
        self.assertIn('60 t sold here so far', p['reason'])
        self.cargo()
        self.assertEqual(self.state()['progress']['stage'], 'complete')

    def test_events_before_selection_or_at_other_markets_are_ignored(self):
        self.emit('MarketSell', iso(-5), MarketID=2, Type='gold', Type_Localised='Gold', Count=100, SellPrice=400, TotalSale=40000)
        self.select()
        self.emit('MarketSell', iso(-3600), MarketID=2, Type='gold', Type_Localised='Gold', Count=100, SellPrice=400, TotalSale=40000)
        self.emit('MarketSell', iso(), MarketID=9, Type='gold', Type_Localised='Gold', Count=100, SellPrice=400, TotalSale=40000)
        self.emit('MarketBuy', iso(), MarketID=1, Type='silver', Type_Localised='Silver', Count=100, BuyPrice=1, TotalCost=100)
        legs = self.state()['progress']['legs']
        self.assertEqual([(l['bought'], l['sold']) for l in legs], [(0, 0), (0, 0)])
        self.assertFalse(legs[0]['done'])

    def test_unknown_cargo_falls_back_to_docking_and_recorded_purchases(self):
        self.select()
        self.core.bus.emit('journal.file.Cargo', {'Count': 5, 'timestamp': iso(), 'Inventory': [{'Name': 'gold', 'Count': 2}]})
        p = self.state()['progress']
        self.assertFalse(p['cargo_known'])
        self.assertEqual((p['stage'], p['legs'][0]['aboard']), ('travel_buy', None))
        self.dock('Sol', 'Port 1')
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['quantity']), ('buy', 100))
        self.assertIn('Cargo has not been observed', p['reason'])
        self.emit('MarketBuy', iso(), MarketID=1, Type='gold', Type_Localised='Gold', Count=100, BuyPrice=100, TotalCost=10000)
        self.emit('Undocked', iso())
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['legs'][0]['bought'], p['legs'][0]['spent']), ('travel_sell', 100, 10000))

    def test_quote_age_credits_and_commander_change_are_reported(self):
        self.select(age_hours=30)
        p = self.state()['progress']
        self.assertEqual(p['quotes']['status'], 'aging')
        self.assertAlmostEqual(p['quotes']['age_hours'], 30, delta=0.2)
        self.core.store.set('journal', 'credits', 5000)
        self.dock('Sol', 'Port 1')
        self.cargo()
        p = self.state()['progress']
        self.assertEqual((p['stage'], p['credits'], p['credits_short']), ('buy', 5000, True))
        self.core.store.set('journal', 'credits', 20000)
        self.assertFalse(self.state()['progress']['credits_short'])
        self.assertFalse(p['commander_changed'])
        self.emit('LoadGame', iso(), Commander='Someone Else', FID='F9')
        self.assertTrue(self.state()['progress']['commander_changed'])

    def test_stale_and_unknown_quote_ages(self):
        self.select(age_hours=60)
        self.assertEqual(self.state()['progress']['quotes']['status'], 'stale')
        plan = self.state()['plan']
        plan['legs'][0]['buy']['observed_at'] = None
        self.assertEqual(planning.quotes(plan, datetime.now(timezone.utc).timestamp())['status'], 'unknown')

    def test_saved_plan_is_validated_before_use(self):
        self.core.write_data({'plan': {'id': 'x', 'legs': [{'commodity': 'Gold'}], 'quantity': 1}}, 'personal.json')
        bad = self.select()['plan']
        bad['legs'][0]['buy']['volume'] = 'lots'
        self.assertFalse(planning.valid_plan(bad))
        self.core.write_data({'plan': bad}, 'personal.json')
        from elitelab.core import Core, loader
        again = Core()
        self.addCleanup(again.close)
        loader.load_all(again)
        self.assertEqual({k:again.http.tools['get_trade_plan'].fn({})[k] for k in ('plan','progress')}, {'plan': None, 'progress': None})

    def test_journal_handlers_do_not_write_files_or_fetch(self):
        self.select()
        with patch.object(self.core, 'write_data') as write, patch.object(self.core.services, 'fetch_json') as fetch:
            self.dock('Sol', 'Port 1')
            self.cargo(gold=100)
            self.emit('MarketSell', iso(), MarketID=2, Type='gold', Type_Localised='Gold', Count=100, SellPrice=400, TotalSale=40000)
            self.assertFalse([c for c in write.call_args_list if c.args[-1] == 'personal.json'])
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
