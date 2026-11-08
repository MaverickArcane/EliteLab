"""Real-order resizing and acknowledgement of already-posted affiliate adverts."""
import copy
import unittest
from unittest.mock import patch

import test_ptn
from modules.ptn.planning import advert, advertised_profit


class OrderFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.f = test_ptn.PTNTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.desk, self.core = self.f.desk, self.f.core

    def confirm(self, remaining, price=24000):
        return self.f.mutate('confirm', price=price, remaining=remaining,
            checks={k: True for k in ('near_station', 'docking_open', 'funds_checked', 'competition_checked')})

    def test_19898_reserved_order_can_resize_without_replacing_route_or_scouts(self):
        self.f.confirmed()
        original = copy.deepcopy(self.desk.data['plan'])
        self.f.carrier(free_space=0, reserved_space=19898)
        self.core.store.set('trade', 'orders', {'liquor': dict(side='buy', price=24000,
            quantity=19898, updated_at=self.f.time())})
        self.assertFalse(self.desk.view()['operation']['ready'])
        result = self.f.mutate('resize', quantity=19898)
        self.assertEqual(result['plan']['id'], original['id'])
        self.assertEqual(result['plan']['scouts'], original['scouts'])
        self.assertEqual(result['plan']['orders'], original['orders'])
        self.assertEqual(result['plan']['route']['quantity'], 19898)
        self.assertEqual(result['plan']['route']['settings']['quantity'], 19898)
        self.assertEqual(result['operation']['remaining'], 19898)
        self.assertFalse(result['operation']['ready'])
        result = self.confirm(19898)
        self.assertTrue(result['operation']['ready'], result['operation']['blockers'])
        output = self.f.call('prepare_ptn_advert', revision=result['revision'])
        self.assertIn('**20k**/unit profit, 19.898k units', output['advert'])
        self.assertEqual(type(self.desk)(self.core).data['plan']['route']['quantity'], 19898)

    def test_resize_preserves_loaded_tonnes_posting_and_historical_prices(self):
        self.f.confirmed()
        self.f.mutate('posted', link='https://discord.com/channels/1/2/3')
        posted = copy.deepcopy(self.desk.data['plan']['posted'])
        self.core.store.set('trade', 'orders', {'liquor': dict(side='buy', price=24000,
            quantity=17000, updated_at=self.f.time())})
        result = self.f.mutate('resize', quantity=19898)
        self.assertEqual(result['operation']['remaining'], 18898)
        self.assertEqual(result['plan']['posted'], posted)
        self.assertEqual(result['plan']['orders']['loading']['price'], 24000)
        with self.assertRaises(ValueError):
            self.f.mutate('resize', quantity=999)
        self.confirm(18898)
        self.f.mutate('remaining', remaining=0)
        self.f.mutate('stage', stage='transit')
        with self.assertRaises(ValueError):
            self.f.mutate('resize', quantity=20000)

    def test_resize_owner_revision_validation_and_atomic_failure(self):
        self.f.scout()
        before = copy.deepcopy(self.desk.data)
        for quantity in (0, 25001, True, 19898.5, 'bad'):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                self.f.mutate('resize', quantity=quantity)
        with self.assertRaises(ValueError):
            self.f.call('update_ptn_plan', revision=-1, action='resize', quantity=19898)
        self.core.store.set('party', 'mode', 'member')
        with self.assertRaises(ValueError):
            self.f.mutate('resize', quantity=19898)
        self.core.store.set('party', 'mode', 'solo')
        with patch.object(self.core, 'write_data', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.f.mutate('resize', quantity=19898)
        self.assertEqual(self.desk.data, before)
        self.assertEqual(self.f.mutate('resize', quantity=25000)['plan']['route']['quantity'], 25000)

    def test_past_posting_can_be_recorded_despite_changed_live_order_and_stale_market(self):
        self.f.confirmed()
        self.desk.data['plan']['scouts']['buy']['observed_at'] = self.f.time(-2)
        self.core.store.set('trade', 'orders', {'liquor': dict(side='buy', price=24000,
            quantity=19898, updated_at=self.f.time())})
        self.assertFalse(self.desk.view()['operation']['ready'])
        with patch.object(self.core.services, 'fetch_json', side_effect=AssertionError('No Discord action')):
            result = self.f.mutate('posted', link='https://discord.com/channels/1/2/3')
        self.assertEqual(result['plan']['stage'], 'loading')
        self.assertFalse(result['operation']['ready'])
        self.assertEqual(result['operation']['posted']['link'], 'https://discord.com/channels/1/2/3')
        self.assertEqual(type(self.desk)(self.core).data['plan']['posted'], result['plan']['posted'])
        with self.assertRaises(ValueError):
            self.f.call('prepare_ptn_advert', revision=result['revision'])
        with self.assertRaises(ValueError):
            self.f.mutate('posted', link='https://attacker.invalid')

    def test_posting_still_requires_owner_public_phase_and_actual_order(self):
        self.f.scout()
        with self.assertRaises(ValueError): self.f.mutate('posted', link='')
        self.f.mutate('stage', stage='loading')
        with self.assertRaises(ValueError): self.f.mutate('posted', link='')
        self.f.carrier(system='Source'); self.confirm(18000)
        self.core.store.set('party', 'mode', 'member')
        with self.assertRaises(ValueError): self.f.mutate('posted', link='')
        self.core.store.set('party', 'mode', 'solo')
        self.desk.data['plan']['route']['settings']['haul_mode'] = 'self_load'
        with self.assertRaises(ValueError): self.f.mutate('posted', link='')

    def test_profit_rounds_down_bold_keeps_exact_quantity_and_economics(self):
        for exact, shown in ((20308, 20000), (20999, 20000), (20000, 20000), (19999, 19000), (999, 999), (1, 1)):
            with self.subTest(exact=exact):
                self.assertEqual(advertised_profit(exact), shown)
                self.assertLessEqual(shown, exact)
        text = advert('Test', 'TST-001', 'Silver', 'Port', 'System', 'loading', 20308, 19898)
        self.assertIn('**20k**/unit profit, 19.898k units', text)
        self.f.confirmed()
        self.confirm(18000, price=24308)
        output = self.f.call('prepare_ptn_advert', revision=self.desk.data['revision'])
        self.assertEqual(output['profit_per_ton'], 20308)
        self.assertEqual(output['advertised_profit_per_ton'], 20000)
