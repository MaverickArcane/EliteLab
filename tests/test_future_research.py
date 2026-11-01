"""Behavioral regressions for routes, actual modules, unlock chains and budgets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from test_progression_sourcing import FixtureMixin
from elitelab.core import gamedata as gd
from elitelab.core import config
from elitelab.core.http import make_handler


class FutureResearchTests(FixtureMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).parent / "fixtures/journals/flight/Journal.20261002.000000.01.log"
        shutil.copy(fixture, self.logs / fixture.name)
        self.core = self.make_core()

    def snapshot(self, name, **fields):
        self.core.bus.emit("journal.file." + name, {"timestamp": "2026-10-31T10:01:00Z", **fields})

    def route(self):
        return [{"StarSystem": "Origin", "StarPos": [0, 0, 0]},
                {"StarSystem": "Middle", "StarPos": [3, 4, 0], "StarClass": "K"},
                {"StarSystem": "Destination", "StarPos": [3, 4, 12], "StarClass": "M"}]

    def test_navigation_remaining_route_advances_and_clears(self):
        self.snapshot("NavRoute", Route=self.route())
        result = self.call("get_navigation_context", limit=1)
        self.assertEqual(result["remaining_jumps"], 2)
        self.assertEqual(result["remaining_distance_ly"], 17)
        self.assertTrue(result["truncated"])
        self.emit("FSDJump", StarSystem="Middle", StarPos=[3, 4, 0])
        self.assertEqual(self.call("get_navigation_context")["remaining_jumps"], 1)
        self.emit("NavRouteClear", timestamp="2026-10-31T10:02:00Z")
        self.snapshot("NavRoute", Route=self.route())
        self.assertEqual(self.call("get_navigation_context")["status"], "cleared")

    def test_off_route_and_repeated_system_do_not_invent_next_jump(self):
        self.snapshot("NavRoute", Route=self.route())
        self.emit("FSDJump", StarSystem="Elsewhere")
        self.assertIsNone(self.call("get_navigation_context")["next_system"])
        self.assertEqual(self.call("get_navigation_context")["status"], "off_route")
        self.emit("FSDJump", StarSystem="Origin")
        self.snapshot("NavRoute", Route=self.route() + [self.route()[0]])
        self.assertEqual(self.call("get_navigation_context")["status"], "ambiguous_position")

    def test_snapshots_cannot_leak_across_commanders(self):
        self.snapshot("NavRoute", Route=self.route())
        self.emit("Commander", timestamp="2026-10-31T11:00:00Z", FID="OTHER", Name="Other")
        self.snapshot("NavRoute", Route=self.route())
        self.assertIsNone(self.call("get_navigation_context")["destination"])
        self.assertEqual(self.call("get_ship_modules")["modules"], [])

    def test_old_module_power_and_other_ship_reports_rejected(self):
        row = {"Slot": "SmallHardpoint1", "Item": "hpt_beamlaser_gimbal_small", "Power": 0.3}
        self.snapshot("ModulesInfo", timestamp="2026-10-01T10:00:00Z", Modules=[row])
        self.assertFalse(self.call("get_ship_modules")["power_report_matches_loadout"])
        self.snapshot("ModulesInfo", Modules=[{**row, "Item": "other_module"}])
        self.assertFalse(self.call("get_ship_modules")["power_report_matches_loadout"])
        self.snapshot("ModulesInfo", Modules=[row])
        result = self.call("get_ship_modules", slot="SmallHardpoint")
        self.assertEqual(result["modules"][0]["reported_power_mw"], 0.3)
        self.assertEqual(result["modules"][0]["engineering"]["ExperimentalEffect"], "special_thermal_vent")
        self.emit("EngineerCraft", timestamp="2026-10-31T10:02:00Z", Slot="SmallHardpoint1", Ingredients=[])
        self.assertTrue(self.call("get_ship_modules")["loadout_changed_since_observation"])
        self.assertFalse(self.call("get_ship_modules")["power_report_matches_loadout"])

    def test_freshness_missing_and_old_are_distinct(self):
        result = {r["data"]: r for r in self.call("get_data_freshness")["observations"]}
        self.assertEqual(result["status"]["status"], "missing")
        self.assertEqual(result["loadout"]["status"], "older_than_threshold")

    def test_palin_uses_furthest_distance_not_total_travel(self):
        result = self.call("get_engineer_unlock_progress", engineer="Palin")
        self.assertEqual(result["referral_chain"], ["Elvira Martuuk", "Marco Qwent"])
        self.assertEqual(result["meeting_requirement"]["observed_value"], 3781)
        self.assertFalse(result["meeting_requirement"]["met_when_observed"])
        self.assertEqual(result["donation"]["key"], "unknownenergysource")
        self.emit("Statistics", Exploration={"Greatest_Distance_From_Start":5001})
        self.assertTrue(self.call("get_engineer_unlock_progress", engineer="Palin")["meeting_requirement"]["met_when_observed"])
        self.assertIsNone(self.call("get_engineer_unlock_progress", engineer="Palin")["unlocked"])

    def test_rank_boundaries_and_older_promotions(self):
        for name in ("Farseer", "Hera", "Broo"):
            self.assertTrue(self.call("get_engineer_unlock_progress", engineer=name)["meeting_requirement"]["met_when_observed"])
        self.emit("Promotion", Empire=2)
        self.emit("Rank", timestamp="2026-10-01T10:00:00Z", Empire=0)
        self.assertEqual(self.call("get_engineer_unlock_progress", engineer="Hera")["meeting_requirement"]["observed_value"], 2)
        self.assertFalse(self.call("get_engineer_unlock_progress", engineer="Lei")["meeting_requirement"]["met_when_observed"])

    def test_material_and_credit_donations_are_cumulative_and_scoped(self):
        self.emit("EngineerContribution", Engineer="Professor Palin", Type="Materials", Material="unknownenergysource", Quantity=10, TotalQuantity=10)
        self.emit("EngineerContribution", Engineer="Professor Palin", Type="Materials", Material="unknownenergysource", Quantity=10, TotalQuantity=10)
        self.assertEqual(self.call("get_engineer_unlock_progress", engineer="Palin")["donation"]["remaining"], 15)
        self.emit("EngineerContribution", Engineer="The Dweller", Type="Credits", Quantity=500000, TotalQuantity=500000)
        self.assertEqual(self.call("get_engineer_unlock_progress", engineer="Dweller")["donation"]["remaining"], 0)
        self.emit("Commander", FID="OTHER", Name="Other")
        self.assertIsNone(self.call("get_engineer_unlock_progress", engineer="Palin")["meeting_requirement"]["observed_value"])

    def budget(self, **q):
        return self.call("plan_engineering_upgrade", blueprint="Lightweight", module="Beam laser", **q)

    def inventory(self, count=30):
        self.emit("Materials", Raw=[{"Name":"phosphorus","Count":count},{"Name":"manganese","Count":count}],
                  Manufactured=[{"Name":k,"Count":count} for k in ("salvagedalloys", "conductiveceramics", "uncutfocuscrystals", "conductivepolymers", "precipitatedalloys")], Encoded=[])

    def test_single_roll_budget_and_effect_shortfalls_without_writes(self):
        self.inventory(2)
        before = self.core.store.get("wishlist")
        result = self.budget(grade=3, from_grade=2, mode="single_roll", experimental="Thermal Vent")
        amounts = {r["key"]:r for r in result["materials"]}
        self.assertEqual(amounts["conductiveceramics"]["need"], 1)
        self.assertEqual(amounts["conductivepolymers"]["need"], 3)
        self.assertEqual(amounts["uncutfocuscrystals"]["short"], 3)
        self.assertFalse(result["affordable"])
        self.assertEqual(self.core.store.get("wishlist"), before)
        self.assertEqual(self.call("get_material_inventory")["inventory"]["conductiveceramics"], 2)

    def test_estimate_custom_rolls_quantity_and_experimental_only(self):
        self.inventory()
        result = self.budget(grade=3, from_grade=1, quantity=2, rolls="1,1,2,4,5")
        amounts = {r["key"]:r["need"] for r in result["materials"]}
        self.assertEqual(amounts["manganese"], 6)
        self.assertNotIn("phosphorus", amounts)
        self.assertTrue(result["affordable"])
        effect = self.budget(grade=3, from_grade=3, experimental="Thermal Vent")
        self.assertEqual(effect["steps"], [])
        self.assertEqual(len(effect["materials"]), 3)

    def test_unknown_inventory_and_new_commander_cannot_be_affordable(self):
        self.assertIsNone(self.budget()["affordable"])
        self.inventory()
        self.assertTrue(self.budget()["affordable"])
        self.emit("Commander", FID="OTHER", Name="Other")
        self.assertIsNone(self.budget()["affordable"])

    def test_missing_grade_costs_and_incompatible_effect_rejected(self):
        with patch.dict(gd.BLUEPRINT_BY_KEY["Weapon_LightWeight"]["grades"], {"3": {}}, clear=False):
            with self.assertRaisesRegex(ValueError, "Missing catalog"):
                self.budget(grade=3)
        with self.assertRaisesRegex(ValueError, "incompatible"):
            self.budget(experimental="Mass Manager")
        for values in ({"quantity":0}, {"grade":6}, {"rolls":"1,2"}, {"mode":"single_roll","rolls":"1,2,3,4,5"}):
            with self.assertRaises(ValueError):
                self.budget(**values)

    def test_catalog_reports_coverage_and_no_grind_after_unlock(self):
        self.assertEqual(len(self.call("list_engineer_unlocks")["engineers"]), 10)
        self.emit("EngineerProgress", Engineer="Professor Palin", Progress="Unlocked", Rank=1)
        result = self.call("get_engineer_unlock_progress", engineer="Palin")
        self.assertEqual(result["donation"]["remaining"], 0)
        self.assertIn("no further unlock donation", result["next_action"])

    def test_generic_weapon_cannot_borrow_reviewed_beam_engineer_caps(self):
        result = self.call("plan_engineering_upgrade", blueprint="Weapon_LightWeight", module="Cannon", grade=3)
        self.assertEqual(result["engineers"], [])
        self.assertEqual(result["provenance"]["status"], "not_reviewed")
        self.assertEqual(self.budget(grade=3)["provenance"]["status"], "reviewed")

    def test_new_tools_round_trip_through_http_and_mcp(self):
        calls = {"get_neutron_route": {}, "get_fsd_injection_status": {},
                 "list_synthesis_recipes": {"query":"FSD"}, "plan_synthesis": {"items":[{"key":"fsd_injection_basic","quantity":2}]},
                 "get_navigation_context": {}, "get_ship_modules": {"slot":"SmallHardpoint"},
                 "get_mission_plan": {}, "find_mission_sources": {},
                 "get_data_freshness": {}, "list_engineer_unlocks": {"engineer":"Palin"},
                 "get_engineer_unlock_progress": {"engineer":"Palin"},
                 "plan_engineering_upgrade": {"blueprint":"Lightweight","module":"Beam laser","grade":3,"mode":"single_roll"}}
        with patch.object(config, "AUTH_TOKEN", ""):
            server = ThreadingHTTPServer(("127.0.0.1",0), make_handler(self.core))
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                requests = [{"jsonrpc":"2.0","id":0,"method":"tools/list"}]
                requests += [{"jsonrpc":"2.0","id":i,"method":"tools/call","params":{"name":name,"arguments":q}}
                             for i,(name,q) in enumerate(calls.items(),1)]
                requests.append({"jsonrpc":"2.0","id":99,"method":"tools/call","params":{"name":"plan_engineering_upgrade",
                                 "arguments":{"blueprint":"Lightweight","module":"Beam laser","grade":9}}})
                env = dict(os.environ, ELITELAB_URL=f"http://127.0.0.1:{server.server_address[1]}", ELITELAB_AUTH_TOKEN="")
                result = subprocess.run([sys.executable,"-m","elitelab","mcp"], cwd=config.ROOT, env=env,
                    input="".join(json.dumps(r)+"\n" for r in requests), capture_output=True, text=True, timeout=20, check=True)
                replies = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertTrue(set(calls) <= {t["name"] for t in replies[0]["result"]["tools"]})
                for reply in replies[1:-1]:
                    self.assertFalse(reply["result"]["isError"], reply)
                self.assertTrue(replies[-1]["result"]["isError"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)


if __name__ == "__main__":
    unittest.main()
