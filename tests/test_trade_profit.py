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
