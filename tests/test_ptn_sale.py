"""Hold-based sale drafts and buyer-backed price suggestions, without a sourcing plan."""
import copy
import unittest
from unittest.mock import patch

import test_ptn


class SaleAdvertTests(unittest.TestCase):
    def setUp(self):
        self.f = test_ptn.PTNTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.core, self.desk = self.f.core, self.f.desk
        self.core.store.update('trade', dict(inventory={
            'liquor':dict(name='Liquor', stock=340, updated_at=self.f.time(-2), source='observed local transfers'),
            'tritium':dict(name='tritium', stock=None, updated_at=self.f.time(), source='observed local transfers')},
            orders={'liquor':dict(side='sell', active=True, price=50000, quantity=340, updated_at=self.f.time()),
                    'tritium':dict(side='buy', active=True, price=40000, quantity=18000)}))

    def draft(self, **values):
        q = dict(commander='Fixture Pilot', callsign='TST-001', commodity='liquor', quantity=340,
                 price=54001, system='Sol')
        return self.f.call('prepare_ptn_sale_advert', **{**q, **values})

    def prices(self, **values):
        return self.f.call('suggest_ptn_sale_price', **{**dict(commodity='Liquor', quantity=340), **values})

    def test_generate_exact_sale_without_route_and_without_mutation(self):
        before = copy.deepcopy(self.desk.data), copy.deepcopy(self.core.store.get('trade'))
        advert = self.draft()
        self.assertEqual(advert['copy_text'], '**N.A.C. Test (TST-001)** is selling **Liquor** in **Sol**.\n'
                         '**340 t** available at **54,001 Cr/t**.')
        self.assertEqual(advert['total_proceeds'], 18360340)
        self.assertIsNone(advert['buyer'])
        self.assertEqual(before, (self.desk.data, self.core.store.get('trade')))
        self.assertIsNone(self.desk.data['plan'])

    def test_unknown_stock_and_buy_orders_never_invent_available_tonnes_or_sale_price(self):
        rows = {r['commodity']:r for r in self.f.call('get_ptn_desk')['sale_cargo']}
        self.assertIsNone(rows['tritium']['stock']); self.assertIsNone(rows['tritium']['sell_price'])
        self.assertEqual(rows['liquor']['sell_price'], 50000)
        advert = self.draft(commodity='tritium', quantity=100)
        self.assertIn('unknown', advert['notes'][0])
        self.assertEqual(advert['quantity'],100)
        with self.assertRaises(ValueError): self.draft(quantity=None)

    def test_owner_quantity_can_override_old_stock_but_does_not_reconcile_it(self):
        advert = self.draft(quantity=400)
        self.assertIn('exceeds',advert['notes'][0])
        self.assertEqual(self.core.store.get('trade','inventory')['liquor']['stock'],340)

    def test_manual_commodity_and_pickup_preserve_explicit_unknowns(self):
        advert = self.draft(commodity='Iridium',system='Buyer')
        self.assertIsNone(advert['stock_evidence'])
        self.assertEqual(len(advert['notes']),2)
        self.assertIn('**Iridium**', advert['copy_text'])

    def test_unloading_draft_has_exact_estimated_margin_and_needs_positive_payout(self):
        advert = self.draft(kind='unloading', station='Sell Port', system='Buyer', buyer_price=75000)
        self.assertEqual(advert['buyer']['profit'],20999)
        self.assertIn('estimated hauler profit: **20,999 Cr/t**',advert['copy_text'])
        self.assertIn('is unloading **Liquor** to **Sell Port**',advert['copy_text'])
        for changes in ({'buyer_price':54001},{'buyer_price':50000},{'station':''},{'buyer_price':None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.draft(**{**dict(kind='unloading',station='Sell Port',buyer_price=75000),**changes})

    def test_identity_switch_validation_and_markdown_injection(self):
        for changes in ({'quantity':0},{'quantity':25001},{'price':0},{'price':1.2},{'price':True},
                        {'price':float('nan')},{'commander':'Other'},{'callsign':'BAD-001'},
                        {'system':'@everyone'},{'commodity':'`evil`'},{'system':'Sol\nFake'},
                        {'kind':'loading'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.draft(**changes)
        self.assertIn('Some\\*thing',self.draft(commodity='Some*thing')['copy_text'])

    def test_suggestions_use_buyer_less_payout_with_carrier_settings_and_full_load_demand(self):
        before = copy.deepcopy(self.desk.data)
        result = self.prices(payout=20001)
        row = result['rows'][0]
        self.assertEqual(row['price'],75000)
        self.assertEqual(row['suggested_price'],54900)
        self.assertEqual(row['percent'],549)
        self.assertEqual(row['hauler_profit'],20100)
        self.assertEqual(row['volume'],200000)
        self.assertEqual(row['distance'],200)
        self.assertEqual(row['jumps'],1)
        self.assertEqual(row['source'],'Ardent / EDDN')
        self.assertEqual(self.desk.data,before)
        self.f.sell['demand'] = 339
        self.assertEqual(self.prices()['rows'],[])
        self.f.sell['demand'] = 0
        self.assertTrue(self.prices()['rows'][0]['demand_unlimited'])

    def test_unknown_mean_keeps_price_target_and_setting_unknown(self):
        self.f.sell.pop('meanPrice')
        row = self.prices(payout=20001)['rows'][0]
        self.assertEqual(row['suggested_price'],54999)
        self.assertIsNone(row['percent'])

    def test_filters_stale_distant_surface_low_prices_and_handles_failed_reports(self):
        original = copy.deepcopy(self.f.sell)
        for changes in ({'updatedAt':self.f.time(-25)},{'systemX':501},{'stationType':'CraterPort'},
                        {'sellPrice':15000},{'maxLandingPadSize':2}):
            self.f.sell = {**original,**changes}
            with self.subTest(changes=changes): self.assertEqual(self.prices()['rows'],[])
        self.f.sell = original
        self.assertEqual(self.prices(radius=100)['rows'],[])
        with patch.object(self.core.services,'fetch_json',side_effect=lambda url,**kw:
                          self.f.fetch(url,**kw) if url.endswith('/commodities') else (_ for _ in ()).throw(OSError('offline'))):
            result = self.prices()
        self.assertEqual(result['rows'],[]); self.assertTrue(result['warnings'])

    def test_includes_current_system_without_silently_using_ship_location(self):
        self.f.carrier(system='Buyer')
        self.core.store.update('journal',dict(system='Elsewhere',star_pos=[1000,0,0]))
        original = self.f.fetch
        def fetch(url,**kw):
            if '/system/name/Buyer/commodities/imports?' in url: return [self.f.sell]
            if '/nearby/imports?' in url: return []
            return original(url,**kw)
        with patch.object(self.core.services,'edsm_coords',return_value={'Buyer':dict(x=200,y=0,z=0)}), \
             patch.object(self.core.services,'fetch_json',side_effect=fetch):
            result = self.prices()
        self.assertEqual(result['system'],'Buyer')
        self.assertEqual(result['rows'][0]['distance'],0)
        self.assertEqual(result['rows'][0]['jumps'],0)


if __name__ == '__main__':
    unittest.main()
