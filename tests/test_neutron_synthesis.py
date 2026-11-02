"""Offline journal fixtures and Spansh contract tests; no game input or network."""
import copy
import json
from pathlib import Path
import shutil
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from test_progression_sourcing import FixtureMixin
from elitelab.core import neutron

FIXTURE = Path(__file__).parent / "fixtures/journals/neutron"
RESULT = json.loads((FIXTURE / "spansh-result.json").read_text())
JOB = RESULT["job"]


class TripFixture(FixtureMixin):
    def setUp(self):
        super().setUp()
        shutil.copy(FIXTURE / "Journal.20261003.000000.01.log", self.logs)
        self.core = self.make_core()
        self.core.store.update("journal", {"ship_info": {"id": 56}, "jump_range_laden": 73.179})

    def synth(self):
        return self.call("get_fsd_injection_status")

    def plan(self, **q):
        with patch.object(self.core.services, "post_form", return_value={"status": "queued", "job": JOB}) as send:
            result = self.call("plan_neutron_route", destination="Destination", **q)
            self.request = send.call_args.args[1]
        return result

    def ready(self, **q):
        self.plan(**q)
        with patch.object(self.core.services, "fetch_json", return_value=RESULT):
            return self.call("refresh_neutron_route")


class NeutronTests(TripFixture, unittest.TestCase):
    def test_ship_defaults_job_progress_and_export(self):
        d = self.ready()
        self.assertEqual(self.request["supercharge_multiplier"], 6)
        self.assertEqual(self.request["range"], 73.17)
        self.assertEqual(d["next_waypoint"]["system"], "Neutron")
        self.assertEqual(d["route"]["estimated_total_jumps"], 26)
        self.assertNotIn("fit_signature", d["route"])
        self.assertIsNone(d["palin"]["destination_meets_distance_requirement"])
        self.assertIn("Distance To Arrival", self.call("export_neutron_route")["csv"])
        self.emit("FSDJump", timestamp="2099-01-01T00:00:00Z", StarSystem="Neutron")
        self.assertEqual(self.call("get_neutron_route")["next_waypoint"]["system"], "Destination")
        self.emit("FSDJump", timestamp="2099-01-01T00:01:00Z", StarSystem="Intermediate")
        self.assertEqual(self.call("get_neutron_route")["navigation_status"], "between_waypoints_or_off_route")
        self.emit("FSDJump", timestamp="2099-01-01T00:02:00Z", StarSystem="Destination")
        self.assertEqual(self.call("get_neutron_route")["navigation_status"], "arrived")

    def test_plan_validation_and_pending_protection(self):
        for value in [0, -1, 201, float("nan"), True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plan(range_ly=value)
        d = self.plan()
        with self.assertRaises(ValueError):
            self.plan()
        with self.assertRaises(ValueError):
            self.call("clear_neutron_route", id="wrong")
        self.assertIsNone(self.call("clear_neutron_route", id=d["route"]["id"])["route"])

    def test_poll_error_retry_and_throttle(self):
        self.plan()
        with patch.object(self.core.services, "fetch_json", side_effect=TimeoutError("retry")) as fetch:
            d = self.call("refresh_neutron_route")
            self.assertEqual(d["route"]["status"], "queued")
            self.assertEqual(d["route"]["last_poll_error"], "retry")
            self.call("refresh_neutron_route")
            self.assertEqual(fetch.call_count, 1)

    def test_bad_result_never_becomes_navigation(self):
        for change in ["endpoint", "empty", "boolean_jumps", "infinite_distance", "job"]:
            self.core = self.make_core()
            self.plan(range_ly=70)
            bad = copy.deepcopy(RESULT)
            if change == "endpoint": bad["result"]["destination_system"] = "Elsewhere"
            if change == "empty": bad["result"]["system_jumps"] = []
            if change == "boolean_jumps": bad["result"]["system_jumps"][1]["jumps"] = True
            if change == "infinite_distance": bad["result"]["system_jumps"][1]["distance_left"] = float("inf")
            if change == "job": bad["job"] = "wrong"
            with patch.object(self.core.services, "fetch_json", return_value=bad):
                d = self.call("refresh_neutron_route")
            self.assertEqual(d["waypoint_count"], 0)
            self.assertIsNotNone(d["route"]["last_poll_error"])
            self.call("clear_neutron_route", id=d["route"]["id"])

    def test_fit_changes_unknown_ship_and_commander_isolation(self):
        self.ready()
        self.emit("EngineerCraft", Slot="FrameShiftDrive")
        d = self.call("get_neutron_route")
        self.assertEqual(d["navigation_status"], "ship_or_fit_changed")
        self.assertEqual(d["ship"]["suggested_supercharge_multiplier"], 4)
        self.assertIsNone(d["ship"]["suggested_range_ly"])
        self.emit("Commander", FID="OTHER", Name="Other")
        self.assertIsNone(self.call("get_neutron_route")["route"])
        self.assertIsNone(self.call("get_neutron_route")["ship"]["ship_id"])

    def test_restart_keeps_progress_and_handlers_do_not_call_network(self):
        self.ready()
        with patch.object(self.core.services, "fetch_json", side_effect=AssertionError("network forbidden")) as fetch:
            self.emit("FSDJump", timestamp="2099-01-01T00:00:00Z", StarSystem="Neutron")
            fetch.assert_not_called()
        self.core = self.make_core()
        d = self.call("get_neutron_route")
        self.assertEqual(d["route"]["progress_index"], 1)
        self.assertEqual(d["next_waypoint"]["system"], "Destination")

    def test_explicit_start_palin_and_ship_change_during_submit(self):
        with patch.object(self.core.services, "edsm_coords", return_value={"Real start": {"x":0,"y":0,"z":0}}):
            d = self.ready(career_start="Real start")
        self.assertTrue(d["palin"]["destination_has_100ly_margin"])
        def changed(*args):
            self.emit("ModuleSwap", FromSlot="Slot01", ToSlot="Slot02")
            return {"status":"queued", "job":JOB}
        with patch.object(self.core.services, "post_form", side_effect=changed), self.assertRaises(ValueError):
            self.call("plan_neutron_route", destination="Other", range_ly=73)

    def test_special_drive_only_and_palin_not_total_travel(self):
        for value in [None, "int_hyperdrive_overcharge_size5_class5"]:
            flight = {"commander":{"key":"A"},"loadout":{"data":{"Modules":[{"Slot":"FrameShiftDrive","Item":value or ""}]}}}
            self.assertEqual(neutron.ship_context(flight, {"key":"A"})["suggested_supercharge_multiplier"], 4)
        d = neutron.palin_check({"exploration":{"values":{"Greatest_Distance_From_Start":3781,"Total_Hyperspace_Distance":60000}}}, {})
        self.assertFalse(d["distance_requirement_met_when_observed"])

    def test_failed_save_does_not_publish_unsaved_plan_or_clear(self):
        with patch.object(self.core, "write_data", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.plan()
        self.assertIsNone(self.call("get_neutron_route")["route"])
        d = self.ready()
        with patch.object(self.core, "write_data", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.call("clear_neutron_route", id=d["route"]["id"])
        self.assertEqual(self.call("get_neutron_route")["route"]["id"], d["route"]["id"])

    def test_concurrent_plan_is_rejected_without_blocking_readers(self):
        entered, release = threading.Event(), threading.Event()
        def submit(*args):
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test worker was not released")
            return {"status":"queued", "job":JOB}
        with patch.object(self.core.services, "post_form", side_effect=submit), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.call, "plan_neutron_route", destination="Destination")
            try:
                self.assertTrue(entered.wait(3))
                self.assertIsNone(self.call("get_neutron_route")["route"])
                with self.assertRaisesRegex(ValueError, "already running"):
                    self.call("plan_neutron_route", destination="Another")
            finally:
                release.set()
            self.assertEqual(future.result(3)["route"]["status"], "queued")

    def test_commander_change_while_spansh_runs_cannot_save_to_either_account(self):
        def submit(*args):
            self.emit("Commander", FID="OTHER", Name="Other")
            return {"status":"queued", "job":JOB}
        with patch.object(self.core.services, "post_form", side_effect=submit), self.assertRaisesRegex(ValueError, "Commander changed"):
            self.call("plan_neutron_route", destination="Destination")
        self.assertIsNone(self.call("get_neutron_route")["route"])
        self.emit("Commander", timestamp="2099-01-01T00:00:00Z", FID="FPROGRESS-A", Name="Unlock Pilot")
        self.assertIsNone(self.call("get_neutron_route")["route"])


class SynthesisTests(TripFixture, unittest.TestCase):
    def test_fixture_recipe_costs_inventory_and_history(self):
        d = self.synth()
        self.assertEqual(d["boost"]["status"], "injection_observed")
        self.assertEqual(d["boost"]["multiplier"], 1.25)
        self.assertEqual([r["craftable"] for r in d["injections"]], [2, 2, 1])
        self.assertEqual(d["recorded_crafts"], {"fsd_injection_basic":1})
        self.assertEqual(d["history"][0]["materials_spent"], {"carbon":1,"vanadium":1,"germanium":1})
        self.assertEqual(self.call("list_synthesis_recipes", query="AFM", grade="basic")["recipes"][0]["materials"]["vanadium"], 3)

    def test_shared_materials_are_not_double_budgeted(self):
        result = self.call("plan_synthesis", items=[{"key":"fsd_injection_basic","quantity":2},{"key":"fsd_injection_standard","quantity":2}])
        self.assertFalse(result["affordable"])
        germanium = next(r for r in result["materials"] if r["key"] == "germanium")
        self.assertEqual((germanium["required"],germanium["have"],germanium["short"]), (4,2,2))
        self.assertEqual(self.synth()["injections"][0]["craftable"], 2)

    def test_jet_cone_replaces_injection_and_ship_jump_clears(self):
        self.emit("JetConeBoost", BoostValue=6)
        self.assertEqual(self.synth()["boost"]["multiplier"], 6)
        self.emit("CarrierJump", StarSystem="Origin")
        self.assertEqual(self.synth()["boost"]["status"], "jet_cone_observed")
        self.emit("FSDJump", StarSystem="Next", BoostUsed=1)
        d = self.synth()
        self.assertEqual(d["boost"]["status"], "jump_completed")
        self.assertEqual(d["last_jump"]["preceding_boost"]["source"], "JetConeBoost")
        self.assertEqual(d["last_jump"]["boost_used"], 1)

    def test_replay_restart_and_unrecognised_recipe(self):
        self.core.watcher.replay()
        self.assertEqual(self.synth()["recorded_crafts"]["fsd_injection_basic"], 1)
        self.emit("MaterialCollected", Name="iron", Count=1, Category="Raw")
        self.assertEqual(self.synth()["injections"][0]["craftable"], 2)
        self.core = self.make_core()
        self.assertEqual(self.synth()["recorded_crafts"]["fsd_injection_basic"], 1)
        self.emit("Synthesis", Name="FSD Premium", Materials=[{"Name":"iron","Count":1}])
        self.assertEqual(self.synth()["boost"]["status"], "unknown_injection")
        self.assertIsNone(self.synth()["history"][0]["recipe_key"])

    def test_new_commander_missing_snapshot_is_unknown(self):
        self.emit("Commander", FID="OTHER", Name="Other")
        d = self.synth()
        self.assertIsNone(d["injections"][0]["craftable"])
        self.assertEqual(d["history"], [])
        self.emit("Materials", timestamp="2026-10-01T01:00:00Z", Raw=[{"Name":"carbon","Count":100}])
        self.assertIsNone(self.synth()["injections"][0]["craftable"])
        self.emit("Materials", Raw=[], Manufactured=[], Encoded=[])
        self.assertEqual(self.synth()["injections"][0]["craftable"], 0)

    def test_ship_switch_unknown_and_invalid_quantity(self):
        self.emit("Loadout", ShipID=60, Ship="anaconda", Modules=[])
        self.assertEqual(self.synth()["boost"]["status"], "unknown")
        for value in [0, -1, 1.5, True, float("inf")]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.call("plan_synthesis", items=[{"key":"fsd_injection_basic","quantity":value}])

    def test_older_material_events_cannot_poison_later_live_stock(self):
        self.emit("Commander", FID="OTHER", Name="Other")
        self.emit("Materials", Raw=[{"Name":"carbon","Count":1},{"Name":"vanadium","Count":1},{"Name":"germanium","Count":1}])
        self.emit("Materials", timestamp="2026-10-01T01:00:00Z", Raw=[{"Name":"germanium","Count":100}])
        self.emit("MaterialCollected", Name="carbon", Count=1, Category="Raw")
        self.assertEqual(self.synth()["injections"][0]["craftable"], 1)
        self.assertEqual(self.call("get_material_inventory")["inventory"]["germanium"], 1)

    def test_recipe_aliases_and_invalid_keys(self):
        for alias, total in [("jumponium",3),("AFMU",3),("oxygen",1),("heatsink",3)]:
            self.assertEqual(self.call("list_synthesis_recipes", query=alias)["total"], total)
        with self.assertRaises(ValueError):
            self.call("plan_synthesis", items=[{"key":[],"quantity":1}])

    def test_startup_materials_before_loadgame_remain_available(self):
        self.emit("Commander", timestamp="2099-01-01T00:00:00Z", FID="STARTUP", Name="Startup")
        self.emit("Materials", timestamp="2099-01-01T00:00:01Z", Raw=[{"Name":k,"Count":2} for k in ["carbon","vanadium","germanium"]])
        self.emit("LoadGame", timestamp="2099-01-01T00:00:02Z", FID="STARTUP", Commander="Startup")
        self.assertEqual(self.synth()["injections"][0]["craftable"], 2)
        self.assertEqual(self.call("get_material_inventory")["inventory"]["carbon"], 2)
        self.assertEqual(self.synth()["session_started_at"], "2099-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
