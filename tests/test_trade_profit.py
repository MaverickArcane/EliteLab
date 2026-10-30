"""Crew payouts conserve the route spread across loading and unloading."""
import unittest
from modules.trade.profit import split_profit


class ProfitTests(unittest.TestCase):
    def test_two_order_prices_pay_each_leg_and_leave_carrier_share(self):
        p = split_profit(40000, 60000, 20000)
        self.assertEqual((p["carrier_buy_price"], p["carrier_sell_price"]), (45000, 55000))
        self.assertEqual((p["gross_profit"], p["owner_profit"], p["crew_profit"]), (400000000, 200000000, 200000000))
        self.assertEqual(p["owner_profit"] + p["loading_profit"] + p["unloading_profit"], p["gross_profit"])

    def test_rounding_and_single_leg_work_conserve_every_credit(self):
        for loading, unloading in ((25, 25), (0, 100), (100, 0), (0, 0), (33, 67)):
            p = split_profit(100, 107, 3, loading, unloading)
            self.assertLessEqual(p["carrier_buy_price"], p["carrier_sell_price"])
            self.assertEqual(p["owner_profit"] + p["crew_profit"], 21)
            self.assertEqual((p["carrier_buy_price"] - 100) * 3, p["loading_profit"])
            self.assertEqual((107 - p["carrier_sell_price"]) * 3, p["unloading_profit"])

    def test_unknown_quantity_keeps_totals_unknown_but_prices_useful(self):
        p = split_profit(100, 200, None)
        self.assertIsNone(p["gross_profit"])
        self.assertIsNone(p["owner_profit"])
        self.assertEqual(p["carrier_buy_price"], 125)
        self.assertEqual(split_profit(100, 200, 0)["gross_profit"], 0)

    def test_invalid_split_and_loss_cannot_generate_misleading_orders(self):
        for args in ((100, 200, 10, 70, 40), (100, 90, 10), (100, 200, -1), (100, 200, 10, -1, 0), (100, 200, 10, 25.5, 25)):
            with self.assertRaises(ValueError):
                split_profit(*args)


    def test_percentage_prices_use_actual_rounded_margins(self):
        p=split_profit(4568,64440,19876,25,25,47214)
        self.assertEqual((p['carrier_buy_percent'],p['carrier_sell_percent']),(41,105))
        self.assertEqual((p['carrier_buy_price'],p['carrier_sell_price']),(19358,49575))
        self.assertEqual(p['loading_per_ton'],19358-4568)
        self.assertEqual(p['unloading_per_ton'],64440-49575)
        self.assertEqual(p['owner_profit']+p['crew_profit'],p['gross_profit'])

    def test_percentage_bounds_and_unavailable_route(self):
        p=split_profit(0,1000000,100,0,0,100)
        self.assertEqual((p['carrier_buy_percent'],p['carrier_sell_percent']),(5,1000))
        self.assertGreaterEqual(p['owner_per_ton'],0)
        with self.assertRaises(ValueError):split_profit(1,4,100,25,25,100)
        for mean in (True,-1,1.5):
            with self.assertRaises(ValueError):split_profit(100,200,100,25,25,mean)
        self.assertFalse(split_profit(100,200,100)['carrier_prices_valid'])

    def test_bad_percentage_route_does_not_hide_other_quotes(self):
        from modules.trade.profit import preview
        rows=[{'buy':1,'sell':4,'quantity':10,'mean_price':100},
              {'buy':100,'sell':200,'quantity':10,'mean_price':100}]
        splits=preview({'rows':rows})['splits']
        self.assertIn('error',splits[0]);self.assertEqual(splits[1]['carrier_buy_percent'],125)
