"""Ship range, source/destination pairing and evidence-qualified merit ranking."""
import copy
import json
import unittest
from unittest.mock import patch

import test_mining_desk as desk
from test_mining_desk import DATA, NOW


class MiningOptionsTests(unittest.TestCase):
    setUp = desk.MiningDeskTests.setUp
    call = desk.MiningDeskTests.call
    emit = desk.MiningDeskTests.emit
    state = desk.MiningDeskTests.state

    def run_search(self, q=None, data=None):
        data = data or copy.deepcopy(DATA)
        def fetch(url, *args, **kwargs):
            if "field_values" in url:
                return {"min_max": {"Platinum": {}}}
            return data["bodies" if "/bodies/" in url else "stations"]
        with patch.object(self.core.config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=fetch) as mocked, \
                patch("modules.mining.discovery.time.time", return_value=NOW):
            result = self.call("find_mining_spots", **(q or {}))
        return result, mocked

    def test_laden_cap_default_override_boundary_and_manual_origin(self):
        self.core.store.update("journal", {"jump_range_laden":10.16, "jump_range_now":30})
        result, mocked = self.run_search({"radius":200, "ref":"Sol"})
        self.assertEqual(result["radius"], 10.16)
        self.assertTrue(result["manual_origin"])
        self.assertEqual(mocked.call_args.args[1]["filters"]["distance"]["max"], 10.16)
        self.assertEqual(len(result["results"]), 2)
        self.core.store.update("journal", {"jump_range_laden":10.159})
        self.assertEqual(len(self.run_search()[0]["results"]), 1)
        self.core.store.update("journal", {"jump_range_now":3.25})
        self.assertEqual(self.run_search()[0]["radius"], 3.25)
        self.assertEqual(self.run_search({"radius":1.5})[0]["radius"], 1.5)

    def test_unknown_range_never_falls_back_to_unladen_or_boost(self):
        for value in (None, 0, True, float("nan"), float("inf"), -1):
            self.core.store.update("journal", {"jump_range_laden":value, "jump_range_now":300, "jump_range":300})
            with patch.object(self.core.services, "fetch_json") as fetch, self.assertRaises(ValueError):
                self.call("find_mining_spots", ref="Sol", radius=200)
            fetch.assert_not_called()

    def test_live_ship_swap_and_loadgame_invalidate_range(self):
        for event in ("ShipyardSwap", "ShipyardNew", "ShipyardBuy", "LoadGame"):
            self.core.store.update("journal", {"jump_range_laden":25, "jump_range_now":30})
            self.emit(event, ShipType="Python")
            self.assertIsNone(self.core.store.get("journal", "jump_range_laden"))

    def test_loadout_status_recomputes_current_range_and_missing_mass_fails_closed(self):
        loadout = dict(Ship="Python", ShipID=1, UnladenMass=500, CargoCapacity=128, FuelCapacity={"Main":32},
                       Modules=[{"Slot":"FrameShiftDrive", "Item":"int_hyperdrive_size5_class5"}])
        self.emit("Loadout", **loadout)
        laden = self.core.store.get("journal", "jump_range_laden")
        self.assertGreater(laden, 0)
        self.core.bus.emit("journal.file.Status", {"Fuel":{"FuelMain":0.1}, "Cargo":128})
        self.assertLess(self.core.store.get("journal", "jump_range_now"), laden)
        self.assertLess(self.run_search()[0]["radius"], laden)
        del loadout["CargoCapacity"]
        self.emit("Loadout", **loadout)
        self.assertIsNone(self.core.store.get("journal", "jump_range_laden"))

    def test_changes_during_provider_io_reject_stale_response(self):
        def fetch(*args, **kwargs):
            self.core.store.update("journal", {"jump_range_laden":4})
            return DATA["bodies"]
        with patch.object(self.core.config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=fetch):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.call("find_mining_spots")

    def merit_query(self, **extra):
        return dict(sort="merits", hotspot="Platinum", power="Edmund Mahon", **extra)

    def test_reinforcement_requires_same_system_and_unknown_is_null(self):
        out, mocked = self.run_search(self.merit_query(quantity=40))
        row = out["results"][0]
        self.assertEqual(row["buyer"]["system"], row["system"])
        self.assertEqual(row["buyer"]["station"], "Test Prospect Exchange")
        self.assertIsNone(row["merit_estimate"])
        self.assertEqual(mocked.call_count, 3)
        self.assertIn("fallback", out["ranking_note"])
        json.dumps(out, allow_nan=False)

    def test_acquisition_checks_source_state_distance_and_missing_coordinates(self):
        data = copy.deepcopy(DATA)
        source = data["bodies"]["results"][0]
        target = data["stations"]["results"][1]
        source.update(system_x=0, system_y=0, system_z=0)
        target.update(system_x=30, system_y=0, system_z=0)
        q = self.merit_query(powerplay_mode="acquisition")
        self.assertEqual(self.run_search(q, data)[0]["results"][0]["buyer"]["from_ring_ly"], 30)
        target["system_x"] = 30.0001
        self.assertIsNone(self.run_search(q, data)[0]["results"][0]["buyer"])
        source["system_power_state"] = "Fortified"
        target["system_x"] = 20
        self.assertIsNotNone(self.run_search(q, data)[0]["results"][0]["buyer"])
        target["system_x"] = 20.0001
        self.assertIsNone(self.run_search(q, data)[0]["results"][0]["buyer"])
        target["system_x"] = None
        self.assertIsNone(self.run_search(q, data)[0]["results"][0]["buyer"])

    def observe_sale(self):
        ts = "2026-11-02T02:00:00Z"
        self.emit("LoadGame", ts, Commander="Miner")
        self.emit("Powerplay", ts, Power="Edmund Mahon", Merits=0)
        self.emit("Location", ts, StarSystem="Delkar", StationName="Test Prospect Exchange", PowerplayState="Stronghold")
        self.emit("Cargo", ts, Inventory=[])
        for _ in range(2): self.emit("MiningRefined", ts, Type="Platinum")
        self.emit("MarketSell", ts, Type="Platinum", Count=2, TotalSale=556000)
        self.emit("PowerplayMerits", "2026-11-02T02:00:01Z", Power="Edmund Mahon", MeritsGained=200, TotalMerits=200)
        self.core.store.update("journal", {"jump_range_laden":25, "jump_range_now":30})

    def test_forecast_uses_matching_sale_evidence_and_leaves_recorded_totals_alone(self):
        self.observe_sale()
        out, _ = self.run_search(self.merit_query(quantity=10))
        estimate = out["results"][0]["merit_estimate"]
        self.assertEqual(estimate["merits"], 1000)
        self.assertEqual(estimate["basis"], "conditional_sale_association")
        self.assertEqual(self.state()["powerplay"]["session_merits"], 200)
        self.assertEqual(self.state()["profit"]["sale_proceeds"], 556000)
        # A new price, another market or changed source state cannot reuse this yield.
        for kind in ("price", "station", "state", "age", "pledge"):
            self.observe_sale()
            data = copy.deepcopy(DATA)
            if kind == "price": data["stations"]["results"][0]["market"][0]["sell_price"] += 1
            if kind == "station": data["stations"]["results"][0]["name"] = "Other station"
            if kind == "state": data["bodies"]["results"][0]["system_power_state"] = "Fortified"
            if kind == "age":
                summary = self.state()
                summary["powerplay"]["recent"][0]["timestamp"] = "2026-10-01T01:00:00Z"
                self.core.store.set("mining", "summary", summary)
            if kind == "pledge": self.emit("PowerplayLeave", Power="Edmund Mahon")
            with self.subTest(kind=kind):
                self.assertIsNone(self.run_search(self.merit_query(), data)[0]["results"][0]["merit_estimate"])

    def test_invalid_planning_parameters_fail_before_network(self):
        for extra in ({"quantity":True}, {"hours":float("inf")}, {"pad":[]}, {"sort":[]}, {"powerplay_mode":{}}, {"hotspot":""}):
            q = {**self.merit_query(), **extra}
            with patch.object(self.core.services, "fetch_json") as fetch, self.assertRaises(ValueError):
                self.call("find_mining_spots", **q)
            fetch.assert_not_called()

    def test_conditional_yield_sorts_before_higher_price_unknown_yield(self):
        self.observe_sale()
        data = copy.deepcopy(DATA)
        ring = data["bodies"]["results"][1]
        ring["rings"][0]["signals"] = [{"name":"Platinum", "count":1}]
        data["stations"]["results"][1]["system_power_state"] = "Fortified"
        out, _ = self.run_search(self.merit_query(), data)
        known, unknown = out["results"]
        self.assertEqual(known["system"], "Delkar")
        self.assertGreater(unknown["buyer"]["price"], known["buyer"]["price"])
        self.assertIsNone(unknown["merit_estimate"])
        self.assertEqual(unknown["merit_eligibility"], "reported_candidate")

    def test_mixed_mining_origins_never_reuse_a_sale_as_a_forecast(self):
        self.observe_sale()
        ts = "2026-11-02T02:05:00Z"
        self.emit("FSDJump", ts, StarSystem="LTT 4487", PowerplayState="Fortified")
        self.emit("MiningRefined", ts, Type="Platinum")
        self.emit("FSDJump", ts, StarSystem="Delkar", PowerplayState="Stronghold")
        self.emit("Docked", ts, StarSystem="Delkar", StationName="Test Prospect Exchange")
        self.emit("MarketSell", ts, Type="Platinum", Count=1, TotalSale=278000)
        self.emit("PowerplayMerits", ts, Power="Edmund Mahon", MeritsGained=100, TotalMerits=300)
        recent = self.state()["powerplay"]["recent"][0]
        self.assertTrue(recent["sale_associated"])
        self.assertIsNone(recent["sale"]["origin"])


if __name__ == "__main__":
    unittest.main()
