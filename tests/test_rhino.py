"""Rhino evidence, replay, local notebook and surface navigation contracts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_elitelab import Core, config, loader

FIXTURE = Path(__file__).parent / "fixtures" / "rhino"


class RhinoTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="elitelab-rhino-test-")
        self.addCleanup(directory.cleanup)
        for key, value in (("DATA_DIR", directory.name), ("JOURNAL_DIR", str(FIXTURE))):
            setting = patch.object(config, key, value)
            setting.start(); self.addCleanup(setting.stop)
        self.core = Core()
        loader.load_all(self.core)
        self.addCleanup(self.core.close)

    def call(self, tool="get_rhino_status", **params):
        return self.core.http.tools[tool].fn(params)

    def emit(self, event, timestamp="2026-11-15T12:00:00Z", **data):
        self.core.bus.emit("journal." + event, {"event": event, "timestamp": timestamp, **data})

    def launch(self):
        self.emit("LoadGame", Commander="Rhino Test", FID="F-RHINO", Ship="panthermkii")
        self.emit("Location", StarSystem="Shinrarta Dezhra", Body="Shinrarta Dezhra AB 2 j", BodyType="Planet")
        self.emit("LaunchSRV", SRVType="mev_rhino", PlayerControlled=True)

    def save(self, **overrides):
        return self.call("save_rhino_site", name="My tritium", system="Shinrarta Dezhra", body="Shinrarta Dezhra AB 2 j",
                         commodity="Tritium", **{"latitude":35.9491, "longitude":-31.2339, "rigs":3, **overrides})

    def position(self, **overrides):
        self.core.bus.emit("journal.file.Status", {"event":"Status", "timestamp":"2026-11-15T12:02:00Z",
            "Flags":(1 << 21) | (1 << 26), "BodyName":"Shinrarta Dezhra AB 2 j", "PlanetRadius":5963896,
            "Latitude":35.950340, "Longitude":-31.233133, **overrides})

    def test_fixture_replay_live_and_repeat_are_equal(self):
        for line in next(FIXTURE.glob("Journal.*")).read_text().splitlines():
            event = json.loads(line)
            self.core.bus.emit("journal." + event["event"], event)
        expected = self.call()
        self.assertEqual(expected["session"]["refined_tons"], 3)
        self.assertEqual(expected["session"]["tons_per_hour"], 90)
        self.assertEqual(expected["session"]["commodities"][0]["tons"], 2)
        self.assertEqual(expected["session"]["unloads"], 1)
        self.assertEqual(expected["cargo"]["srv"]["count"], 0)
        self.assertEqual(expected["cargo"]["ship"]["count"], 103)
        self.assertTrue(expected["session"]["active"])
        for _ in range(2):
            self.core.watcher.replay()
            self.assertEqual(self.call(), expected)

    def test_ring_and_other_srv_output_not_counted(self):
        self.emit("MiningRefined", Type="Gold")
        self.assertIsNone(self.call()["session"])
        self.launch()
        self.emit("LaunchSRV", SRVType="testbuggy", PlayerControlled=True)
        self.emit("MiningRefined", Type="Gold")
        self.assertEqual(self.call()["session"]["refined_tons"], 0)
        self.emit("LaunchSRV", SRVType="mev_rhino", PlayerControlled=False)
        self.assertFalse(self.call()["session"]["active"])

    def test_rate_includes_setup_unloading_and_idle_then_stops_on_boarding(self):
        self.launch()
        self.emit("MiningRefined", "2026-11-15T12:00:30Z", Type="Tritium", Count=900)
        self.assertIsNone(self.call()["session"]["tons_per_hour"])
        self.emit("Music", "2026-11-15T12:02:00Z")
        self.assertEqual(self.call()["session"]["tons_per_hour"], 30)
        self.emit("DockSRV", "2026-11-15T12:03:00Z", SRVType="mev_rhino")
        self.assertEqual(self.call()["session"]["tons_per_hour"], 20)
        self.emit("Music", "2026-11-15T16:00:00Z")
        self.emit("MiningRefined", "2026-11-15T16:00:00Z", Type="Gold")
        self.assertEqual(self.call()["session"]["refined_tons"], 1)
        self.assertEqual(self.call()["session"]["tons_per_hour"], 20)

    def test_shutdown_commander_and_new_deployment_boundaries(self):
        self.launch()
        self.emit("MiningRefined", Type="Tritium")
        self.call("report_rhino_rigs", count=3)
        self.emit("Shutdown", "2026-11-15T12:02:00Z")
        self.position()
        self.assertFalse(self.call()["session"]["active"])
        self.assertEqual(self.call()["position"], {})
        self.assertIsNone(self.call()["rigs"]["count"])
        self.emit("LoadGame", Commander="Other", FID="OTHER")
        self.assertIsNone(self.call()["session"])
        self.launch()
        self.assertEqual(self.call()["session"]["refined_tons"], 0)

    def test_cargo_holds_snapshot_age_and_transfers_stay_separate(self):
        self.core.watcher.replay()
        self.core.bus.emit("journal.file.Cargo", {"event":"Cargo", "Vessel":"SRV", "Count":72, "timestamp":"2026-11-15T12:03:00Z"})
        self.emit("Cargo", "2026-11-15T12:01:00Z", Vessel="SRV", Count=3)
        state = self.call()
        self.assertEqual(state["cargo"]["srv"]["count"], 72)
        self.assertEqual(state["cargo"]["srv"]["free"], 0)
        self.assertEqual(state["cargo"]["ship"]["free"], 1033)
        self.emit("CargoTransfer", "2026-11-15T12:04:00Z", Transfers=[{"Direction":"tocarrier","Count":50},{"Direction":"toship","Count":60}])
        self.assertEqual(self.call()["session"]["unloads"], 1)
        self.assertEqual(self.call()["cargo"]["ship"]["count"], 103)

    def test_transfer_is_not_production_and_unknown_ship_hold_stays_unknown(self):
        self.launch()
        self.emit("CargoTransfer", "2026-11-15T12:01:00Z", Transfers=[{"Direction":"toship","Count":72}])
        self.assertEqual(self.call()["session"]["transferred_tons"], 72)
        self.assertEqual(self.call()["session"]["refined_tons"], 0)
        self.assertIsNone(self.call()["cargo"]["ship"].get("count"))

    def test_missing_timing_and_malformed_numbers_remain_safe(self):
        self.launch()
        self.emit("MiningRefined", None, Type="Tritium")
        self.emit("Music", "2026-11-15T12:02:00Z")
        self.assertIsNone(self.call()["session"]["tons_per_hour"])
        for bad in (True, float("nan"), float("inf"), -1, {}, [], 10**400):
            self.emit("Cargo", Vessel="SRV", Count=bad)
            self.position(Latitude=bad, PlanetRadius=bad)
            json.dumps(self.call(), allow_nan=False)
        self.assertIsNone(self.call()["cargo"]["srv"].get("count"))

    def test_notebook_persists_and_is_commander_scoped(self):
        self.launch()
        site = self.save()
        self.emit("Commander", Name="Other", FID="OTHER")
        self.assertEqual(len(self.call()["sites"]), 1)
        self.assertIsNone(self.call()["selected_site"])
        self.emit("Commander", Name="Rhino Test", FID="F-RHINO")
        self.assertEqual(self.call()["selected_site"]["id"], site["id"])
        restarted = Core(); loader.load_all(restarted); self.addCleanup(restarted.close)
        restarted.watcher.replay()
        self.assertEqual(restarted.http.tools["get_rhino_status"].fn({})["selected_site"]["id"], site["id"])
        self.save(id=site["id"], rigs=6)
        self.assertEqual(self.call()["selected_site"]["rigs"], 6)
        self.call("remove_rhino_site", id=site["id"])
        self.assertIsNone(self.call()["selected_site"])

    def test_reference_and_validation_do_not_overwrite_notebook(self):
        with self.assertRaises(ValueError): self.save()
        self.launch()
        for data in ({"latitude":91}, {"longitude":-181}, {"rigs":7}, {"rigs":1.5}, {"rigs":True}, {"radius_m":-1}, {"latitude":float("nan")}, {"id":"shinrarta-tritium"}):
            with self.assertRaises(ValueError): self.save(**data)
        self.assertEqual(len(self.call()["sites"]), 1)
        with self.assertRaises(ValueError): self.call("remove_rhino_site", id="shinrarta-tritium")

    def test_recent_same_body_navigation_matches_known_location(self):
        self.launch(); self.call("select_rhino_site", id="shinrarta-tritium"); self.position()
        module = self.core.modules["rhino"].instance
        with patch.object(module.time, "time", return_value=module.stamp("2026-11-15T12:02:01Z")):
            state = self.call()
            self.assertAlmostEqual(state["navigation"]["distance_m"], 144.3, delta=1)
            self.assertTrue(180 < state["navigation"]["bearing"] < 220)
            self.position(BodyName="Other body")
            self.assertIsNone(self.call()["navigation"]["distance_m"])
            self.position(Flags=0)
            self.assertIsNone(self.call()["navigation"]["bearing"])

    def test_departure_includes_final_timestamp(self):
        self.launch(); self.emit("MiningRefined", Type="Tritium")
        self.emit("LeaveBody", "2026-11-15T12:05:00Z")
        self.assertEqual(self.call()["session"]["elapsed_seconds"], 300)
        self.assertFalse(self.call()["session"]["active"])

    def test_older_position_cannot_replace_newer_and_missing_identity_clears_scope(self):
        self.launch(); self.save(); self.position()
        self.position(timestamp="2026-11-15T12:01:59Z", Latitude=0)
        self.assertEqual(self.call()["position"]["latitude"], 35.950340)
        self.emit("Commander", Name="Rhino Test")
        self.assertEqual(len(self.call()["sites"]), 2)
        self.emit("LoadGame")
        self.assertEqual(len(self.call()["sites"]), 1)
        self.assertIsNone(self.call()["selected_site"])

    def test_failed_save_keeps_previous_selection_and_invalid_id_does_not_clear(self):
        self.launch(); site = self.save()
        with patch.object(self.core, "write_data", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.save(latitude=0)
        self.assertEqual(self.call()["selected_site"]["id"], site["id"])
        with self.assertRaises(ValueError): self.call("select_rhino_site", id=[])
        self.assertEqual(self.call()["selected_site"]["id"], site["id"])

    def test_navigation_handles_dateline_and_stale_positions(self):
        module = self.core.modules["rhino"].instance
        p = {"system":"A", "body":"B", "latitude":0, "longitude":179.9, "radius_m":1000, "timestamp":"2026-11-15T12:00:00Z"}
        site = {"system":"A", "body":"B", "latitude":0, "longitude":-179.9}
        now = module.stamp(p["timestamp"])
        self.assertAlmostEqual(module.navigation(p, site, now)["distance_m"], 3.5, delta=.1)
        self.assertEqual(module.navigation(p, site, now)["bearing"], 90)
        self.assertIsNone(module.navigation(p, site, now+121)["distance_m"])

    def test_rig_count_manual_only_and_post_contracts(self):
        with self.assertRaises(ValueError): self.call("report_rhino_rigs", count=3)
        self.launch(); self.call("report_rhino_rigs", count=3)
        self.assertEqual(self.call()["rigs"]["count"], 3)
        self.assertIsNone(self.call()["selected_site"])
        self.emit("DockSRV", SRVType="mev_rhino")
        self.assertIsNone(self.call()["rigs"]["count"])
        for name in ("save_rhino_site", "select_rhino_site", "remove_rhino_site", "report_rhino_rigs"):
            self.assertEqual(self.core.http.tools[name].method, "POST")
        self.assertEqual(self.core.http.tools["get_rhino_status"].method, "GET")
