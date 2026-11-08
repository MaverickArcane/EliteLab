"""Mining accounting and adversarial community-search contracts."""
import copy
import datetime as dt
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_mining

DATA = json.loads((Path(__file__).parent / "fixtures/mining/spansh.json").read_text())
NOW = dt.datetime(2026, 11, 2, 3, tzinfo=dt.timezone.utc).timestamp()


class MiningDeskTests(unittest.TestCase):
    def setUp(self):
        test_mining.MiningTests.setUp(self)
        self.core.store.update("journal", {"system":"Delkar", "jump_range_laden":80, "jump_range_now":90})
    state = test_mining.MiningTests.state
    emit = test_mining.MiningTests.emit
    def call(self, tool, **q):
        return self.core.http.tools[tool].fn(q)

    def search(self, tool, response, **q):
        def answer(url, *args, **kwargs):
            return {"min_max":{"Platinum":{},"Low Temperature Diamonds":{}}} if url.endswith("field_values/market") else response
        with patch.object(self.core.config, "OFFLINE", False), patch("modules.mining.discovery.time.time", return_value=NOW), patch.object(self.core.services, "fetch_json", side_effect=answer) as fetch:
            out = self.call(tool, ref="Delkar", **q)
            self.assertEqual(fetch.call_count, 2 if tool == "find_mining_buyers" else 1)
            self.assertEqual(fetch.call_args.kwargs["ttl"], 300)
            self.assertEqual(fetch.call_args.args[1]["size"], 25)
            return out, fetch.call_args.args[1]

    def test_spots_use_actual_nested_ring_filter_and_enforce_local_filters(self):
        out, request = self.search("find_mining_spots", DATA["bodies"], ring_type="Metallic", hotspot="Platinum", pristine=True)
        self.assertEqual(request["filters"]["rings"], [{"type": "Metallic"}])
        self.assertEqual([r["ring"] for r in out["results"]], ["Delkar 7 A Ring"])
        self.assertEqual(out["results"][0]["distance"], 0)
        self.assertEqual(out["results"][0]["signals"][0]["count"], 2)
        self.assertIsNone(out["results"][0]["permit_required"])

    def test_power_filter_selects_owned_mining_sources(self):
        out, body = self.search("find_mining_spots", DATA["bodies"], radius=100, power="Edmund Mahon")
        self.assertEqual(body["filters"]["system_power_state"]["value"], ["Exploited", "Fortified", "Stronghold"])
        self.assertEqual([r["system"] for r in out["results"]], ["Delkar", "LTT 4487"])
        self.assertEqual(out["results"][0]["jumps"], 0)

    def test_spots_bound_and_sanitize_provider_input(self):
        raw = copy.deepcopy(DATA["bodies"])
        raw["results"] += [None, {}, {"system_name":"bad","distance":float("nan")}]
        raw["results"][0]["system_x"] = 10**400
        raw["results"][0]["rings"][0]["signals"].append({"name":"<img onerror=x>","count":float("inf")})
        out, _ = self.search("find_mining_spots", raw)
        self.assertEqual(len(out["results"]), 3)
        self.assertIsNone(out["results"][0]["x"])
        json.dumps(out, allow_nan=False)

    def test_buyers_sort_price_but_enforce_pad_demand_freshness_and_radius(self):
        out, query = self.search("find_mining_buyers", DATA["stations"], commodity="platinum", quantity=50, pad="L")
        self.assertEqual(query["filters"]["market"][0]["name"], "Platinum")
        self.assertEqual(query["filters"]["market"][0]["demand"]["value"][0], 50)
        self.assertEqual([r["station"] for r in out["results"]], ["Test Miners Landing", "Test Prospect Exchange"])
        self.assertEqual(out["results"][0]["estimated_sale"], 14575000)
        self.assertEqual(out["results"][0]["age_hours"], 2)
        out, _ = self.search("find_mining_buyers", DATA["stations"], commodity="Platinum", quantity=1, pad="M")
        self.assertEqual(out["results"][0]["station"], "Test Small Depot")

    def test_buyers_honor_wider_radius_and_still_enforce_its_boundary(self):
        raw=copy.deepcopy(DATA["stations"])
        raw["results"][0]["distance"]=500
        raw["results"][1]["distance"]=500.01
        out, query=self.search("find_mining_buyers",raw,commodity="Platinum",quantity=50,pad="L",radius=500)
        self.assertEqual(query["filters"]["distance"]["max"],500)
        self.assertEqual([r["station"] for r in out["results"]],["Test Prospect Exchange"])

    def test_buyers_reject_stale_future_prohibited_carrier_and_bad_quotes(self):
        for updates in [{"market_updated_at":"2026-10-01T00:00:00Z"}, {"market_updated_at":"2099-01-01T00:00:00Z"}, {"has_market":False}, {"carrier_name":"Test"}, {"is_planetary":True}, {"distance":201}, {"market":None}, {"market":[{"commodity":"Platinum","sell_price":float("nan"),"demand":100}]}, {"market":[{"commodity":"Platinum","sell_price":100,"demand":100,"is_prohibited":True}]}]:
            with self.subTest(updates=updates):
                raw = {"results":[{**copy.deepcopy(DATA["stations"]["results"][0]), **updates}]}
                out, _ = self.search("find_mining_buyers", raw, commodity="Platinum")
                self.assertEqual(out["results"], [])

    def test_search_validation_precedes_network(self):
        for tool, q in [("find_mining_spots", {"radius":"nan"}), ("find_mining_spots", {"ring_type":"javascript:"}), ("find_mining_spots", {"hotspot":[]}), ("find_mining_spots", {"power":[]}), ("find_mining_buyers", {"commodity":"Platinum","quantity":True}), ("find_mining_buyers", {"commodity":{},"pad":"L"}), ("find_mining_buyers", {"commodity":"Platinum","hours":100})]:
            with self.subTest(q=q), patch.object(self.core.services, "fetch_json") as fetch, self.assertRaises(ValueError):
                self.call(tool, ref="Delkar", **q)
            fetch.assert_not_called()

    def test_offline_and_provider_errors_have_useful_messages(self):
        with self.assertRaisesRegex(ValueError, "offline"):
            self.call("find_mining_spots", ref="Delkar")
        with patch.object(self.core.config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=RuntimeError("private secret")):
            with self.assertRaisesRegex(ValueError, "Spansh search unavailable") as ex:
                self.call("find_mining_spots", ref="Delkar")
            self.assertNotIn("secret", str(ex.exception))

    def test_profit_real_sales_costs_and_no_mark_to_market_income(self):
        self.emit("LoadGame", Commander="Miner")
        self.emit("Cargo", Inventory=[])
        self.emit("BuyDrones", TotalCost=2000)
        for _ in range(3): self.emit("MiningRefined", Type="Platinum")
        self.emit("MarketSell", Type="Platinum", Count=2, TotalSale=500000)
        self.emit("RefuelAll", Cost=500)
        self.emit("RepairAll", Cost=1000)
        self.emit("BuyAmmo", Cost=500)
        p = self.state()["profit"]
        self.assertEqual(p["sale_proceeds"], 500000)
        self.assertEqual(p["operating_costs"], 4000)
        self.assertEqual(p["net_profit"], 496000)
        self.assertEqual(p["remaining"], {"platinum":1})
        self.assertFalse(p["estimated"])

    def test_mixed_cargo_is_conservative_and_explicitly_estimated(self):
        self.emit("Cargo", Inventory=[])
        self.emit("MiningRefined", Type="Gold")
        self.emit("Cargo", Inventory=[{"Name":"Gold","Count":2}])
        self.assertTrue(self.state()["profit"]["estimated"])
        self.emit("LoadGame", Commander="Miner")
        self.emit("Cargo", Inventory=[{"Name":"Platinum","Count":2}])
        self.emit("MiningRefined", Type="Platinum")
        self.emit("MarketSell", Type="Platinum", Count=2, TotalSale=600000)
        self.assertEqual(self.state()["profit"]["sale_proceeds"], 0)
        self.emit("MarketSell", Type="Platinum", Count=1, TotalSale=300000)
        self.assertEqual(self.state()["profit"]["sale_proceeds"], 300000)
        self.assertTrue(self.state()["profit"]["estimated"])

    def test_transfers_ejection_and_returned_cargo_cannot_be_sold_twice(self):
        for _ in range(3): self.emit("MiningRefined", Type="Gold")
        self.emit("EjectCargo", Type="Gold", Count=1)
        self.emit("CargoTransfer", Transfers=[{"Type":"Gold","Count":1,"Direction":"tocarrier"}])
        self.emit("CargoTransfer", Transfers=[{"Type":"Gold","Count":1,"Direction":"toship"}])
        self.emit("MarketSell", Type="Gold", Count=5, TotalSale=5000)
        p = self.state()["profit"]
        self.assertEqual(p["sale_proceeds"], 1000)
        self.assertEqual(p["sold_tons"], 1)
        self.assertEqual(p["removed_tons"], 2)
        self.assertEqual(p["remaining"], {})

    def test_cargo_reconciliation_ignores_stale_snapshot_and_marks_losses(self):
        self.emit("MiningRefined", Type="Gold")
        self.emit("Cargo", "2026-10-22T11:00:00Z", Inventory=[])
        self.assertEqual(self.state()["profit"]["remaining"], {"gold":1})
        self.emit("Cargo", "2026-10-22T12:01:00Z", Inventory=[])
        self.assertEqual(self.state()["profit"]["remaining"], {})
        self.assertEqual(self.state()["profit"]["removed_tons"], 1)

    def test_missing_sale_price_and_malformed_costs_do_not_invent_profit(self):
        self.emit("MiningRefined", Type="Gold")
        self.emit("MarketSell", Type="Gold", Count=1, TotalSale=float("nan"))
        self.emit("BuyDrones", TotalCost=float("inf"))
        p = self.state()["profit"]
        self.assertEqual(p["unknown_sale_tons"], 1)
        self.assertEqual(p["net_profit"], 0)
        json.dumps(p, allow_nan=False)

    def test_ledger_replay_live_equivalence_with_money(self):
        events = [{"event":"Cargo","Inventory":[]}, {"event":"BuyDrones","TotalCost":200}, {"event":"MiningRefined","Type":"Gold"}, {"event":"MarketSell","Type":"Gold","Count":1,"TotalSale":1000}]
        for e in events: self.emit(e["event"], **{k:v for k,v in e.items() if k != "event"})
        live = self.state()["profit"]
        self.emit("LoadGame")
        for e in events: self.emit(e["event"], _replay=True, **{k:v for k,v in e.items() if k != "event"})
        self.core.bus.emit("journal.replay.done", 4)
        self.assertEqual(self.state()["profit"], live)

    def test_ledger_is_bounded_and_resets_on_commander_change(self):
        for _ in range(20): self.emit("BuyDrones", TotalCost=100)
        self.assertEqual(len(self.state()["profit"]["transactions"]), 12)
        self.emit("LoadGame", Commander="Other")
        self.assertEqual(self.state()["profit"]["net_profit"], 0)

    def test_commodity_alias_and_quotes_never_mutate_session_profit(self):
        self.emit("MiningRefined", Type="LowTemperatureDiamond")
        before = self.state()
        raw = copy.deepcopy(DATA["stations"])
        raw["results"][0]["market"][0]["commodity"] = "Low Temperature Diamonds"
        out, query = self.search("find_mining_buyers", raw, commodity="lowtemperaturediamond")
        self.assertEqual(query["filters"]["market"][0]["name"], "Low Temperature Diamonds")
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(self.state(), before)

    def test_provider_pagination_is_bounded_and_partial_failure_is_disclosed(self):
        rows = {"results":[copy.deepcopy(DATA["bodies"]["results"][0]) for _ in range(25)], "count":1000}
        with patch.object(self.core.config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=[rows, RuntimeError("provider timeout")]) as fetch:
            result = self.call("find_mining_spots", ref="Delkar")
            self.assertEqual(fetch.call_count, 2)
            self.assertIn("partial", result["note"])
            self.assertEqual(len(result["results"]), 1)
        with patch.object(self.core.config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", return_value=rows) as fetch:
            self.call("find_mining_spots", ref="Delkar")
            self.assertEqual(fetch.call_count, 4)
            self.assertEqual([c.args[1]["page"] for c in fetch.call_args_list], [0,1,2,3])
