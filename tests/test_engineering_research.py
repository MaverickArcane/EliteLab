"""Offline regression tests for research evidence, comparisons and per-ship notes."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

os.environ["ELITELAB_OFFLINE"] = "1"
from elitelab.core import Core, config, loader
from elitelab.core import gamedata as gd
from elitelab.core import engineering_research as facts


class EngineeringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.logs = Path(self.temp.name) / "journals"
        self.logs.mkdir()
        fixture = Path(__file__).parent / "fixtures/journals/engineering/Journal.20261001.000000.01.log"
        shutil.copy(fixture, self.logs / fixture.name)
        self.data = str(Path(self.temp.name) / "data")
        self.patches = patch.multiple(config, DATA_DIR=self.data, JOURNAL_DIR=str(self.logs), OFFLINE=True)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.core = self.make_core()

    def make_core(self):
        core = Core()
        loader.load_all(core)
        core.watcher.replay()
        return core

    def call(self, name, **params):
        return self.core.http.tools[name].fn(params)

    def emit(self, event, **fields):
        self.core.bus.emit("journal." + event, {"event": event, "timestamp": "2026-10-31T10:00:00Z", **fields})

    def engineer(self, name):
        return self.call("get_engineer_access", engineer=name)["engineers"][0]

    def test_engineer_access_bootstraps_beyond_replay_window(self):
        for day in range(27, 31):
            (self.logs / f"Journal.202610{day}.000000.01.log").write_text(json.dumps(
                {"timestamp": f"2026-10-{day}T00:00:00Z", "event": "LoadGame", "FID": "FTEST-A", "Commander": "Research Pilot"}) + "\n")
        self.core = self.make_core()
        self.assertEqual(self.engineer("Dweller")["rank"], 5)
        self.assertEqual(self.engineer("Martuuk")["rank_progress"], 34)
        self.assertIsNone(self.engineer("Hera Tani")["unlocked"])

    def test_partial_and_full_events_respect_observation_order(self):
        self.emit("EngineerProgress", Engineer="Hera Tani", Rank=1)
        self.assertIsNone(self.engineer("Hera Tani")["unlocked"])
        self.emit("EngineerProgress", Engineer="Elvira Martuuk", Rank=3, RankProgress=12)
        self.assertEqual(self.engineer("Martuuk")["progress"], "Unlocked")
        self.emit("EngineerProgress", timestamp="2026-10-30T00:00:00Z", Engineers=[
            {"Engineer": "Elvira Martuuk", "Progress": "Unlocked", "Rank": 2}])
        self.assertEqual(self.engineer("Martuuk")["rank"], 3)
        self.assertIsNone(self.engineer("Dweller")["unlocked"])
        self.emit("EngineerProgress", timestamp="2026-10-29T00:00:00Z", Engineer="The Dweller", Progress="Unlocked", Rank=5)
        self.assertIsNone(self.engineer("Dweller")["unlocked"])

    def test_engineer_cache_survives_restart_without_old_logs(self):
        self.emit("EngineerProgress", Engineer="Elvira Martuuk", Rank=4)
        for path in self.logs.glob("*.log"):
            path.unlink()
        (self.logs / "Journal.20261031.000000.01.log").write_text(json.dumps(
            {"event": "Commander", "FID": "FTEST-A", "Name": "Research Pilot"}) + "\n")
        self.core = self.make_core()
        self.assertEqual(self.engineer("Martuuk")["rank"], 4)

    def test_loadgame_without_fid_preserves_matching_commander(self):
        self.emit("LoadGame", Commander="Research Pilot")
        self.assertEqual(self.call("get_build_context")["commander"]["fid"], "FTEST-A")
        self.assertEqual(self.engineer("Dweller")["rank"], 5)

    def test_budget_keeps_startup_materials_but_rejects_previous_sessions(self):
        def known():
            return self.call("plan_engineering_upgrade", blueprint="Lightweight", module="Beam laser", grade=1)["inventory_has_current_session_baseline"]

        self.emit("Commander", timestamp="2026-11-01T12:00:00Z", FID="AUDIT", Name="Audit Pilot")
        self.assertFalse(known())
        self.emit("Materials", timestamp="2026-11-01T12:00:01Z", Raw=[{"Name": "phosphorus", "Count": 50}], Manufactured=[], Encoded=[])
        self.assertTrue(known())
        self.emit("LoadGame", timestamp="2026-11-01T12:00:02Z", Commander="Audit Pilot")
        self.assertTrue(known())
        self.assertEqual(self.call("get_material_inventory")["inventory"]["phosphorus"], 50)
        self.emit("Commander", timestamp="2026-11-02T12:00:00Z", FID="AUDIT", Name="Audit Pilot")
        self.assertFalse(known())
        self.emit("Materials", timestamp="2026-11-01T12:00:01Z", Raw=[{"Name": "phosphorus", "Count": 50}], _replay=True)
        self.assertFalse(known())
        self.emit("Commander", timestamp="2026-11-03T12:00:00Z", FID="OTHER", Name="Other Pilot")
        self.assertFalse(known())

    def test_older_session_replay_does_not_change_active_identity_or_ship(self):
        self.emit("Loadout", Ship="smallcombat01_nx", ShipID=51, ShipName="Latest", Modules=[])
        self.emit("Commander", FID="FTEST-B", Name="Another Pilot")
        self.emit("Loadout", Ship="python", ShipID=70, Modules=[])
        self.emit("Commander", timestamp="2026-10-01T00:00:00Z", FID="FTEST-A", Name="Research Pilot")
        self.emit("Loadout", timestamp="2026-10-01T00:00:01Z", ShipID=50, Ship="smallcombat01_nx", Modules=[])
        self.emit("EngineerProgress", timestamp="2026-10-01T00:00:02Z", Engineer="The Dweller", Progress="Unlocked", Rank=5)
        current = self.call("get_build_context")
        self.assertEqual(current["commander"]["fid"], "FTEST-B")
        self.assertEqual(current["ship_id"], 70)
        self.assertIsNone(self.engineer("Dweller")["unlocked"])
        self.emit("Commander", timestamp="2026-10-31T11:00:00Z", FID="FTEST-A", Name="Research Pilot")
        self.assertEqual(self.call("get_build_context")["ship_id"], 51)

    def test_commander_switch_does_not_leak_evidence_or_context(self):
        self.call("save_build_context", expected_revision=0, playstyle="Keep plasma shocks")
        self.emit("Commander", FID="FTEST-B", Name="Another Pilot")
        self.emit("Loadout", Ship="smallcombat01_nx", ShipID=50, Modules=[])
        self.assertIsNone(self.engineer("Dweller")["unlocked"])
        self.assertEqual(self.call("get_build_context")["context"]["playstyle"], "")
        self.call("save_build_context", expected_revision=0, playstyle="Trade")
        self.emit("Commander", FID="FTEST-A", Name="Renamed Pilot")
        self.assertEqual(self.call("get_build_context", ship_id=50)["context"]["playstyle"], "Keep plasma shocks")

    def test_context_partial_update_clear_and_revision_conflict(self):
        a = self.call("save_build_context", expected_revision=0, preferences="Preserve boost", open_problems="Heat")
        self.assertEqual(a["context"]["revision"], 1)
        self.call("save_build_context", expected_revision=1, open_problems="")
        b = self.call("get_build_context")["context"]
        self.assertEqual(b["preferences"], "Preserve boost")
        self.assertEqual(b["open_problems"], "")
        with self.assertRaises(ValueError):
            self.call("save_build_context", expected_revision=1, notes="Stale")
        self.assertEqual(self.call("get_build_context")["context"]["revision"], 2)
        self.core = self.make_core()
        self.assertEqual(self.call("get_build_context")["context"]["preferences"], "Preserve boost")

    def test_context_is_per_ship_and_does_not_touch_pin(self):
        pin = {"name": "Original reference", "ship_fdname": "smallcombat01_nx"}
        self.core.store.set("build", "pinned", pin)
        self.call("save_build_context", expected_revision=0, accepted_deviations="Different beam")
        self.assertEqual(self.call("get_build_context", ship_id=51)["context"]["revision"], 0)
        self.assertEqual(self.core.store.get("build", "pinned"), pin)
        self.assertEqual(self.call("get_build_context")["observed_loadout"]["ship_id"], 50)

    def test_context_requires_identity_and_rejects_invalid_values(self):
        for q in ({"expected_revision": 0, "notes": ["bad"]}, {"expected_revision": 0, "notes": "x" * 4001},
                  {"expected_revision": 0, "notes": "x", "ship_id": "../bad"}, {"expected_revision": 0, "unknown": "x"}):
            with self.assertRaises(ValueError):
                self.call("save_build_context", **q)
        self.emit("Commander", Name="No FID")
        with self.assertRaises(ValueError):
            self.call("save_build_context", expected_revision=0, ship_id=50, notes="x")

    def test_concurrent_context_writes_have_one_winner(self):
        def save(note):
            try:
                self.call("save_build_context", expected_revision=0, notes=note)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(save, ["one", "two"]))
        self.assertEqual(sum(outcomes), 1)

    def test_failed_context_write_does_not_publish_unsaved_state(self):
        with patch.object(self.core, "write_data", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.call("save_build_context", expected_revision=0, notes="lost")
        self.assertEqual(self.call("get_build_context")["context"]["revision"], 0)

    def test_beam_comparison_and_engineer_cap(self):
        result = self.call("compare_engineering", module="Beam laser", grade=3,
                           blueprints="lightweight,long range,short range", experimental="thermal vent")
        lw, lr, sr = result["options"]
        self.assertEqual(lw["modifiers_percent"]["distributor_draw"], -25)
        self.assertEqual(lw["modifiers_percent"]["power_draw"], -20)
        self.assertEqual(sr["modifiers_percent"]["thermal_load"], 20)
        self.assertEqual(result["experimental"]["ingredients"]["conductivepolymers"], 3)
        self.assertEqual(result["experimental"]["mechanics"][0]["source"]["kind"], "community_test")
        dweller = next(e for e in lw["engineers"] if e["name"] == "The Dweller")
        self.assertTrue(dweller["unlocked"])
        self.assertEqual(dweller["max_grade"], 3)
        g5 = self.call("compare_engineering", module="beam", grade=5, blueprints="lightweight")
        self.assertFalse(next(e for e in g5["options"][0]["engineers"] if e["name"] == "The Dweller")["offers_target_grade"])

    def test_grade_comparison_and_effects_are_separate(self):
        r = self.call("compare_engineering", module="plant", blueprints="Armoured@1,Armoured@5", experimental="Monstered")
        self.assertEqual([o["modifiers_percent"]["power_generation"] for o in r["options"]], [4, 12])
        self.assertEqual(r["experimental"]["modifiers"]["power_generation"], 5)
        pd = self.call("compare_engineering", module="distributor", grade=5, blueprints="charge enhanced,weapon focused")
        self.assertEqual(pd["options"][0]["modifiers_percent"]["weapons_capacity"], -5)
        self.assertEqual(pd["options"][1]["modifiers_percent"]["weapons_capacity"], 60)

    def test_unknown_or_incompatible_comparisons_fail_explicitly(self):
        for q in ({"module": "beam", "blueprints": "Weapon_RapidFire"},
                  {"module": "plasma accelerator"}, {"module": "beam", "grade": 6},
                  {"module": "beam", "experimental": "Monstered"},
                  {"module": "beam", "blueprints": "PowerPlant_Armoured"}):
            with self.assertRaises(ValueError):
                self.call("compare_engineering", **q)

    def test_recipe_module_filter_and_exact_key_respect_scope(self):
        r = self.call("get_recipe", key="long range", module="Beam laser", grade=1)
        self.assertEqual(r["key"], "Weapon_LongRange")
        self.assertEqual(r["provenance"]["status"], "reviewed")
        self.assertIn("error", self.call("get_recipe", key="PowerPlant_Armoured", module="Beam laser"))
        self.assertIn("error", self.call("get_recipe", key="Weapon_LongRange", kind="experimental"))
        unknown = self.call("get_recipe", key="FSD_LongRange")
        self.assertEqual(unknown["provenance"]["status"], "not_reviewed")

    def test_validation_catches_recipe_drift_and_bad_ingredient(self):
        self.assertTrue(self.call("validate_engineering_data")["ok"])
        self.assertEqual(self.call("validate_engineering_data")["source_reviewed"], 11)
        altered = copy.deepcopy(gd._ENG)
        vent = next(e for e in altered["experimentals"] if e["key"] == "special_thermal_vent")
        vent["ingredients"]["invented-material"] = 0
        report = facts.validate_catalog(altered)
        self.assertFalse(report["ok"])
        self.assertTrue(any("differs" in e for e in report["errors"]))
        self.assertTrue(any("invalid ingredient" in e for e in report["errors"]))

    def test_all_new_tools_have_transport_compatible_schema(self):
        for tool in ("compare_engineering", "get_engineer_access", "get_build_context", "save_build_context", "validate_engineering_data"):
            schema = self.core.http.tools[tool].schema()["input_schema"]
            self.assertTrue(all(v["type"] in ("string", "integer") for v in schema["properties"].values()))
        self.assertEqual(self.core.http.tools["save_build_context"].method, "POST")


if __name__ == "__main__":
    unittest.main()
