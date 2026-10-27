"""Paired route search: price, distance, freshness and carrier accounting."""
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import test_trade_party as trade_tests
from test_elitelab import Core, loader, config


class RouteTests(unittest.TestCase):
    call = trade_tests.TradeTests.call

    def setUp(self):
        trade_tests.TradeTests.setUp(self)
        self.profiles = self.core.modules["trade"].profiles
        self.core.store.update("journal", {"system": "Sol", "star_pos": [0, 0, 0], "cargo_capacity": 100,
            "carrier": {"name": "Test carrier", "callsign": "TST-001", "system": "Sol", "free_space": 1000}})
        self.report = {"marketId": 12, "stationName": "Port", "systemName": "Destination", "maxLandingPadSize": 3,
            "stationType": "Orbis", "systemX": 10, "systemY": 0, "systemZ": 0, "distanceToArrival": 100,
            "buyPrice": 100, "sellPrice": 200, "stock": 10000, "demand": 3000, "updatedAt": datetime.now(timezone.utc).isoformat()}
        self.buys = [{**self.report, "marketId": 1}]
        self.sells = [{**self.report, "marketId": 2, "systemX": 50}]
        p = patch.object(config, "OFFLINE", False)
        p.start(); self.addCleanup(p.stop)

    def fetch(self, url, **kwargs):
        if url.endswith('/commodities'):
            return [{"commodityName": "gold", "totalStock": 10000, "maxSellPrice": 200, "minBuyPrice": 100}]
        return self.buys if '/exports?' in url else self.sells

    def query(self, **q):
        with patch.object(self.core.services, "fetch_json", side_effect=self.fetch):
            return self.call("find_carrier_opportunities", **q)

    def test_auto_volume_tracks_free_space_and_filters_both_stops(self):
        from urllib.parse import parse_qs, urlsplit
        carrier = self.core.store.get("journal", "carrier")
        carrier["free_space"] = 2500
        self.core.store.set("journal", "carrier", carrier)
        with patch.object(self.core.services, "fetch_json", side_effect=self.fetch) as fetch:
            result = self.call("find_carrier_opportunities", commodity="gold")
        self.assertEqual(result["settings"]["min_volume"], 2500)
        self.assertEqual(result["rows"][0]["quantity"], 2500)
        quote_urls = [c.args[0] for c in fetch.call_args_list if '/commodity/name/' in c.args[0]]
        self.assertTrue(all(parse_qs(urlsplit(url).query)["minVolume"] == ['2500'] for url in quote_urls))
        carrier["free_space"] = 4000  # Demand is only 3000: this cannot fill and sell a full load.
        self.core.store.set("journal", "carrier", carrier)
        self.assertEqual(self.query(commodity="gold")["rows"], [])
        self.sells[0]["demand"] = 8000
        self.buys[0]["stock"] = 3000
        self.profiles.results.clear()
        self.assertEqual(self.query(commodity="gold")["rows"], [])
        manual = self.query(commodity="gold", min_volume=2000)
        self.assertEqual(manual["settings"]["volume_mode"], "manual")
        self.assertEqual(manual["rows"][0]["quantity"], 3000)

    def test_selected_route_persists_two_crew_prices_and_full_operation_totals(self):
        row = self.query(commodity="gold")["rows"][0]
        state = self.call("select_carrier_opportunity", id=row["id"], crew_enabled=True, crew_load_percent=25, crew_unload_percent=25)
        self.assertEqual(state["plan"]["carrier_price"], 125)
        p = state["calculation"]["profit_split"]
        self.assertEqual((p["gross_profit"], p["owner_profit"], p["crew_profit"]), (100000, 50000, 50000))
        self.assertEqual(state["calculation"]["estimated_carrier_profit"], 50000)
        self.assertEqual(state["calculation"]["carrier_margin"], 50)
        # The same saved route supplies the unloading order without re-entering prices.
        state = self.call("plan_carrier_trade", **{**state["plan"], "mode": "unload", "target": 0})
        self.assertEqual(state["plan"]["carrier_price"], 175)
        self.assertEqual(state["calculation"]["hauler_margin"], 25)
        self.assertEqual(state["calculation"]["profit_split"]["quantity"], 1000)
        second = Core(); loader.load_all(second)
        self.assertEqual(second.store.get("trade", "plan")["crew_split"]["carrier_sell_price"], 175)

    def test_crew_split_excludes_personal_bonus_and_rejects_unknown_cost(self):
        args = dict(commodity="gold", source_price=100, destination_price=220, target=1000,
                    crew_enabled=True, bonus_per_ton=20, price_includes_bonus=True, bonus_confirmed=True)
        state = self.call("plan_carrier_trade", **args)
        self.assertEqual(state["plan"]["crew_split"]["carrier_sell_price"], 175)
        self.assertEqual(state["calculation"]["profit_split"]["owner_per_ton"], 50)
        before = self.core.store.get("trade", "plan")
        for bad in ({"crew_load_percent": 80, "crew_unload_percent": 30}, {"price_basis": "unknown acquisition"}):
            with self.assertRaises(ValueError):
                self.call("plan_carrier_trade", **{**args, **bad})
            self.assertEqual(self.core.store.get("trade", "plan"), before)

    def test_prepare_route_accepts_explicit_physical_count(self):
        row = self.query(commodity="tritium")["rows"][0]
        self.assertIsNone(row["stock"])
        state = self.call("select_carrier_opportunity", id=row["id"], stock=0, crew_enabled=True)
        self.assertEqual(state["inventory"]["tritium"]["stock"], 0)
        self.assertEqual(state["plan"]["target"], row["quantity"])
        self.call("manage_carrier_operation", action="start")
        refreshed = self.query(commodity="gold")["rows"][0]
        with self.assertRaisesRegex(ValueError, "current trade"):
            self.call("select_carrier_opportunity", id=refreshed["id"])

    def test_complete_route_and_capacity_sizing(self):
        row = self.query()["rows"][0]
        self.assertEqual((row["buy"]["price"], row["sell"]["price"], row["route_distance"]), (100, 200, 40))
        self.assertEqual((row["quantity"], row["runs"], row["per_ton"], row["value"]), (1000, 10, 100, 100000))
        self.assertEqual(row["purchase_cost"], 100000)
        state = self.call("select_carrier_opportunity", id=row["id"])
        self.assertEqual((state["plan"]["mode"], state["plan"]["target"]), ("load", 1440))
        self.assertEqual(state["calculation"]["self_margin"], 100)
        self.assertIsNone(state["calculation"]["carrier_margin"])

    def test_cheapest_supplier_within_buyer_radius_not_global_extremes(self):
        self.buys = [{**self.report, "marketId": 1, "buyPrice": 1, "systemX": -100},
                     {**self.report, "marketId": 3, "buyPrice": 90, "systemX": 60},
                     {**self.report, "marketId": 4, "buyPrice": 100, "systemX": 50}]
        row = self.query(route_distance=25)["rows"][0]
        self.assertEqual(row["buy"]["market_id"], 3)
        self.assertEqual(row["route_distance"], 10)

    def test_buy_radius_does_not_filter_sell_stop(self):
        self.buys[0]["systemX"] = 490
        self.sells[0]["systemX"] = 550
        row = self.query(radius=500, route_distance=100)["rows"][0]
        self.assertEqual(row["route_distance"], 60)
        self.assertEqual(row["sell"]["distance"], 550)

    def test_all_returned_quotes_are_paired_before_truncation(self):
        self.buys = [{**self.report, "marketId": i+1, "buyPrice": i+1, "systemX": -200} for i in range(15)]
        self.buys.append({**self.report, "marketId": 99, "buyPrice": 90, "systemX": 50})
        self.assertEqual(self.query(route_distance=25)["rows"][0]["buy"]["market_id"], 99)

    def test_high_sell_price_floor_and_ranking_by_spread_not_volume(self):
        self.sells = [{**self.report, "marketId": 2, "sellPrice": 200, "demand": 1000},
                      {**self.report, "marketId": 3, "sellPrice": 180, "demand": 9000},
                      {**self.report, "marketId": 4, "sellPrice": 150, "demand": 9000}]
        rows = self.query(commodity="gold")["rows"]
        self.assertEqual([r["sell"]["price"] for r in rows], [200, 180])
        self.assertEqual(len(self.query(commodity="gold", sell_percent=95)["rows"]), 1)

    def test_unknown_distance_same_market_and_unprofitable_pairs_excluded(self):
        for changes in ({"systemX": None}, {"marketId": 1}, {"sellPrice": 90}):
            self.sells = [{**self.report, "marketId": 2, **changes}]
            self.assertEqual(self.query()["rows"], [])
            self.profiles.results.clear()

    def test_freshness_pad_volume_and_approach_filters(self):
        bad = [{**self.report, **change, "marketId": i+20} for i, change in enumerate([
            {"updatedAt": "2020-01-01T00:00:00Z"}, {"maxLandingPadSize": 2}, {"stock": 999},
            {"stationType": "FleetCarrier"}, {"distanceToArrival": 10001}])]
        self.buys += bad
        self.assertEqual(len(self.query(commodity="gold")["rows"]), 1)
        self.buys = bad
        self.profiles.results.clear()
        self.assertEqual(self.query()["rows"], [])

    def test_stale_context_selection_and_cache(self):
        result = self.query()
        with patch.object(self.core.services, "fetch_json", side_effect=AssertionError("should use cache")):
            self.assertEqual(self.call("find_carrier_opportunities")["rows"], result["rows"])
        self.call("reconcile_carrier_stock", commodity="gold", stock=12)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.call("select_carrier_opportunity", id=result["rows"][0]["id"])
        row = self.query()["rows"][0]
        state = self.call("select_carrier_opportunity", id=row["id"])
        self.assertEqual(state["plan"]["target"], 1012)

    def test_unknown_stock_does_not_hide_routes_or_count_buy_orders_as_stock(self):
        row = self.query(commodity="tritium")["rows"][0]
        self.assertIsNone(row["stock"])
        self.assertEqual(row["quantity"], 1000)
        self.assertEqual(row["order"]["quantity"], 980)
        with self.assertRaisesRegex(ValueError, "Reconcile"):
            self.call("select_carrier_opportunity", id=row["id"])

    def test_full_or_unknown_capacity_does_not_hide_routes(self):
        for capacity in (None, 0):
            carrier = self.core.store.get("journal", "carrier")
            carrier["free_space"] = capacity
            self.core.store.set("journal", "carrier", carrier)
            with self.assertRaisesRegex(ValueError, "capacity|free space"):
                self.query()
            row = self.query(min_volume=1000)["rows"][0]
            self.assertEqual(row["quantity"], capacity)
            with self.assertRaisesRegex(ValueError, "capacity"):
                self.call("select_carrier_opportunity", id=row["id"])

    def test_reconciliation_conflict_blocks_plan_not_search(self):
        carrier = self.core.store.get("journal", "carrier")
        carrier.update(cargo=10, stats_time=datetime.now(timezone.utc).isoformat())
        self.core.store.set("journal", "carrier", carrier)
        row = self.query()["rows"][0]
        self.assertTrue(row["stock_needs_check"])
        with self.assertRaisesRegex(ValueError, "Reconcile"):
            self.call("select_carrier_opportunity", id=row["id"])
        self.call("reconcile_carrier_stock", commodity="gold", stock=10)
        self.assertFalse(self.query()["rows"][0]["stock_needs_check"])

    def test_filters_and_offline_errors(self):
        for q in ({"profile": "stock"}, {"route_distance": 0}, {"min_volume": -1}, {"sell_percent": 101}):
            with self.assertRaises(ValueError):
                self.call("find_carrier_opportunities", **q)
        with patch.object(config, "OFFLINE", True), self.assertRaisesRegex(ValueError, "offline"):
            self.call("find_carrier_opportunities")

    def test_archive_rebuild_applies_manual_baseline_before_later_transfers(self):
        module = self.core.modules["trade"].instance
        with patch.object(module, "now", return_value="2026-10-22T10:04:30Z"):
            self.call("reconcile_carrier_stock", commodity="gold", stock=50)
        second = Core(); loader.load_all(second); second.watcher.replay()
        self.assertEqual(second.store.get("trade", "inventory")["gold"]["stock"], 40)


if __name__ == "__main__":
    unittest.main()
