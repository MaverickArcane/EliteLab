"""Rhino notebook, surface navigation and shared HTTP/MCP guide contracts."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from elitelab import mcp
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
        self.catalog_size = len(self.call("get_rhino_sites")["sites"])

    def call(self, tool="get_rhino_status", **params):
        return self.core.http.tools[tool].fn(params)

    def emit(self, event, timestamp="2026-11-15T12:00:00Z", **data):
        self.core.bus.emit("journal." + event, {"event": event, "timestamp": timestamp, **data})

    def launch(self):
        self.emit("LoadGame", Commander="Rhino Test", FID="F-RHINO", Ship="panthermkii")
        self.emit("Location", StarSystem="Shinrarta Dezhra", Body="Shinrarta Dezhra AB 2 j", BodyType="Planet")

    def save(self, **overrides):
        return self.call("save_rhino_site", **{"name":"My tritium", "system":"Shinrarta Dezhra", "body":"Shinrarta Dezhra AB 2 j",
                         "commodity":"Tritium", "latitude":35.9491, "longitude":-31.2339, **overrides})

    def position(self, **overrides):
        self.core.bus.emit("journal.file.Status", {"event":"Status", "timestamp":"2026-11-15T12:02:00Z",
            "Flags":(1 << 21) | (1 << 26), "BodyName":"Shinrarta Dezhra AB 2 j", "PlanetRadius":5963896,
            "Latitude":35.950340, "Longitude":-31.233133, **overrides})

    def test_fixture_replay_live_and_repeat_preserve_notebook(self):
        self.launch(); site = self.save()
        for line in next(FIXTURE.glob("Journal.*")).read_text().splitlines():
            event = json.loads(line)
            self.core.bus.emit("journal." + event["event"], event)
        expected = self.call()
        self.assertEqual(expected["selected_site"]["id"], site["id"])
        self.assertNotIn("rigs", expected)
        self.assertEqual(expected["session"]["total_t"], 3)
        self.assertEqual(expected["session"]["unloaded_t"], 3)
        self.assertEqual(expected["session"]["commodities"][0]["id"], "tritium")
        self.assertEqual(expected["session"]["commodities"][0]["tonnes"], 2)
        for _ in range(2):
            self.core.watcher.replay()
            self.assertEqual(self.call(), expected)

    def test_notebook_persists_and_is_commander_scoped(self):
        self.launch(); site = self.save()
        self.emit("Commander", Name="Other", FID="OTHER")
        self.assertEqual(len(self.call()["sites"]), self.catalog_size)
        self.assertIsNone(self.call()["selected_site"])
        self.emit("Commander", Name="Rhino Test", FID="F-RHINO")
        self.assertEqual(self.call()["selected_site"]["id"], site["id"])
        restarted = Core(); loader.load_all(restarted); self.addCleanup(restarted.close)
        restarted.watcher.replay()
        self.assertEqual(restarted.http.tools["get_rhino_status"].fn({})["selected_site"]["id"], site["id"])
        self.save(id=site["id"], notes="Three rigs tested; flat approach")
        self.assertEqual(self.call()["selected_site"]["notes"], "Three rigs tested; flat approach")
        self.call("select_rhino_site", id="")
        self.assertIsNone(self.call()["selected_site"])
        self.assertEqual(len(self.call()["sites"]), self.catalog_size + 1)
        self.call("select_rhino_site", id=site["id"])
        self.call("remove_rhino_site", id=site["id"])
        self.assertIsNone(self.call()["selected_site"])

    def test_collections_survive_unloading_and_stop_at_docking(self):
        self.launch()
        self.emit("MiningRefined", Type="tritium")
        self.assertIsNone(self.call()["session"])
        self.emit("LaunchSRV", SRVType="mev_rhino", PlayerControlled=True)
        for _ in range(2):
            self.emit("MiningRefined", "2026-11-15T12:01:00Z", Type="tritium", Count=99)
        self.emit("MiningRefined", "2026-11-15T12:01:01Z", Type="water")
        self.emit("CargoTransfer", "2026-11-15T12:02:00Z", Transfers=[{"Type":"tritium", "Count":2, "Direction":"toship"}])
        self.emit("CargoTransfer", "2026-11-15T12:02:01Z", Transfers=[{"Type":"tritium", "Count":2, "Direction":"tosrv"}])
        self.emit("CargoTransfer", "2026-11-15T12:02:02Z", CarrierID=123, Transfers=[{"Count":80, "Direction":"toship"}])
        run = self.call()["session"]
        self.assertEqual((run["total_t"], run["unloaded_t"], run["unloads"]), (3, 2, 1))
        self.assertEqual(len(run["points"]), 2)
        self.emit("DockSRV", "2026-11-15T12:03:00Z", ID=66)
        run = self.call()["session"]
        self.assertFalse(run["active"])
        self.assertEqual(run["elapsed_seconds"], 180)
        self.assertEqual(run["average_tph"], 60)
        self.emit("MiningRefined", "2026-11-15T12:05:00Z", Type="tritium")
        self.assertEqual(self.call()["session"], run)
        self.emit("LaunchSRV", "2026-11-15T12:06:00Z", SRVType="mev_rhino", PlayerControlled=True)
        self.assertEqual(self.call()["session"]["total_t"], 0)
        self.assertEqual(self.call()["session"]["elapsed_seconds"], 0)

    def test_partial_login_identity_and_other_srv_do_not_mix_runs(self):
        self.emit("LoadGame", Commander="Rhino Test", FID="F-RHINO", Ship="mev_rhino")
        self.assertTrue(self.call()["session"]["partial"])
        self.emit("MiningRefined", "2026-11-15T12:00:01Z", Type="tritium")
        self.emit("LaunchSRV", "2026-11-15T12:00:02Z", SRVType="mev_scarab", PlayerControlled=False)
        self.assertTrue(self.call()["session"]["active"])
        self.emit("LaunchSRV", "2026-11-15T12:00:03Z", SRVType="mev_scarab", PlayerControlled=True)
        self.assertFalse(self.call()["session"]["active"])
        self.emit("Cargo", "2026-11-15T12:00:04Z", Vessel="SRV", Count=2)
        self.assertIsNone(self.call()["cargo"]["rhino"]["count"])
        self.emit("Commander", "2026-11-15T12:00:05Z", Name="Another", FID="F-OTHER")
        self.assertIsNone(self.call()["session"])
        self.assertIsNone(self.call()["equipment"]["dss"])

    def test_cargo_reports_are_absolute_and_unknown_is_not_empty(self):
        self.launch()
        self.assertIsNone(self.call()["cargo"]["ship"]["count"])
        self.emit("Loadout", CargoCapacity=1136, Modules=[])
        self.emit("Cargo", Vessel="Ship", Count=100)
        self.emit("LaunchSRV", SRVType="mev_rhino")
        self.emit("Cargo", "2026-11-15T12:01:00Z", Vessel="SRV", Count=72)
        self.emit("CargoTransfer", "2026-11-15T12:01:01Z", Transfers=[{"Count":72, "Direction":"toship"}])
        self.emit("Cargo", "2026-11-15T12:01:01Z", Vessel="Ship", Count=172)
        self.emit("Cargo", "2026-11-15T12:01:01Z", Vessel="SRV", Count=0)
        self.emit("Cargo", "2026-11-15T12:00:59Z", Vessel="SRV", Count=55)
        self.assertEqual(self.call()["cargo"]["ship"]["count"], 172)
        self.assertEqual(self.call()["cargo"]["rhino"]["free"], 72)
        self.assertEqual(self.call()["session"]["total_t"], 0)
        self.assertEqual(self.call()["session"]["unloaded_t"], 72)

    def test_equipment_unknown_missing_and_observed_are_distinct(self):
        self.launch()
        self.assertEqual(self.call()["equipment"], {"dss":None, "large_hangar":None})
        self.emit("Loadout", CargoCapacity=400, Modules=[])
        self.assertEqual(self.call()["equipment"], {"dss":False, "large_hangar":False})
        self.emit("Loadout", CargoCapacity=400, Modules=[{"Item":"int_mkiilargebuggybay_size2_class3"}, {"Item":"int_detailedsurfacescanner_tiny"}])
        self.assertEqual(self.call()["equipment"], {"dss":True, "large_hangar":True})
        self.emit("ModuleSell")
        self.assertIsNone(self.call()["equipment"]["large_hangar"])
        self.assertIsNone(self.call()["cargo"]["ship"]["capacity"])

    def test_stale_and_malformed_receipts_cannot_contaminate_new_deployment(self):
        self.launch()
        self.emit("LaunchSRV", "2026-11-15T12:02:00Z", SRVType="mev_rhino")
        for timestamp in ("bad", "2026-11-15T12:01:59Z"):
            self.emit("MiningRefined", timestamp, Type="tritium")
        for value in (None, {}, [], ""):
            self.emit("MiningRefined", "2026-11-15T12:02:01Z", Type=value)
        self.assertEqual(self.call()["session"]["total_t"], 0)
        self.emit("Shutdown", "2026-11-15T12:03:00Z")
        self.emit("MiningRefined", "2026-11-15T12:03:01Z", Type="tritium")
        self.assertEqual(self.call()["session"]["total_t"], 0)
        json.dumps(self.call(), allow_nan=False)

    def test_legacy_rig_fit_survives_as_notes(self):
        self.launch(); site = self.save(notes="Flat ground")
        saved = self.core.read_data("rhino-sites.json")
        saved["fid:F-RHINO"]["sites"][0]["rigs"] = 3
        self.core.write_data(saved, "rhino-sites.json")
        restarted = Core(); loader.load_all(restarted); self.addCleanup(restarted.close)
        restarted.watcher.replay()
        report = restarted.http.tools["get_rhino_status"].fn({})["selected_site"]
        self.assertEqual(report["id"], site["id"])
        self.assertEqual(report["notes"], "Reported rig fit: 3. Flat ground")
        self.assertNotIn("rigs", report)
        restarted.http.tools["save_rhino_site"].fn(report)
        self.assertEqual(restarted.http.tools["get_rhino_status"].fn({})["selected_site"]["notes"], report["notes"])

    def test_reference_and_validation_do_not_overwrite_notebook(self):
        with self.assertRaises(ValueError): self.save()
        self.launch()
        for data in ({"latitude":91}, {"longitude":-181}, {"latitude":True}, {"radius_m":-1}, {"latitude":float("nan")}, {"id":"shinrarta-tritium"}, {"name":""}):
            with self.assertRaises(ValueError): self.save(**data)
        self.assertEqual(len(self.call()["sites"]), self.catalog_size)
        with self.assertRaises(ValueError): self.call("remove_rhino_site", id="shinrarta-tritium")
        for bad in (True, float("nan"), float("inf"), {}, [], 10**400):
            self.position(Latitude=bad, PlanetRadius=bad)
            json.dumps(self.call(), allow_nan=False)

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

    def test_departure_and_shutdown_clear_coordinates_without_losing_sites(self):
        self.launch(); site = self.save()
        for event in ("LeaveBody", "SupercruiseEntry", "StartJump", "FSDJump", "Shutdown"):
            self.position(); self.emit(event, "2026-11-15T12:03:00Z")
            self.assertEqual(self.call()["position"], {})
            self.assertEqual(self.call()["selected_site"]["id"], site["id"])
        self.position(timestamp="2026-11-15T12:03:01Z")
        self.assertEqual(self.call()["position"], {})

    def test_older_position_cannot_replace_newer_and_missing_identity_clears_scope(self):
        self.launch(); self.save(); self.position()
        self.position(timestamp="2026-11-15T12:01:59Z", Latitude=0)
        self.assertEqual(self.call()["position"]["latitude"], 35.950340)
        self.emit("Commander", Name="Rhino Test")
        self.assertEqual(len(self.call()["sites"]), self.catalog_size + 1)
        self.emit("LoadGame")
        self.assertEqual(len(self.call()["sites"]), self.catalog_size)
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
        for clock in (now+121, now-6):
            self.assertIsNone(module.navigation(p, site, clock)["distance_m"])

    def test_catalog_filters_keep_field_confirmation_separate_from_rig_claims_and_reserves(self):
        confirmed = self.call("get_rhino_sites", verification="confirmed")["sites"]
        self.assertEqual({s["id"] for s in confirmed}, {"wregoe-iridium-30", "shinrarta-tritium"})
        wregoe = next(s for s in confirmed if s["id"] == "wregoe-iridium-30")
        self.assertEqual((wregoe["rigs_observed"], wregoe["rigs_reported"]), (6, 6))
        self.assertEqual((wregoe["latitude"], wregoe["longitude"]), (-66.9655, -109.5819))
        self.assertEqual(wregoe["availability"], "unknown")
        tritium = self.call("get_rhino_sites", commodity="tRiTiUm")["sites"]
        self.assertEqual(len(tritium), 2)
        self.assertEqual(next(s for s in tritium if s["verification"] == "confirmed")["availability"], "reported_depleted")
        lead = self.call("get_rhino_sites", verification="unconfirmed", commodity="Tritium")["sites"][0]
        self.assertEqual(lead["id"], "hip63920-tritium")
        self.assertNotIn("rigs_reported", lead)  # Six-rig test is not tied to these coordinates.
        monazite = self.call("get_rhino_sites", commodity="Monazite")["sites"][0]
        self.assertEqual(monazite["rigs_estimated"], 5)
        self.assertEqual(monazite["verification"], "unconfirmed")
        for site in self.call("get_rhino_sites")["sites"]:
            self.assertTrue(site["evidence"] and site["reported_at"] and site["sources"])
            self.assertTrue(all(s["url"].startswith("https://") for s in site["sources"]))
        wregoe["sources"].clear()
        self.assertTrue(self.call("get_rhino_sites")["sites"][0]["sources"])
        with self.assertRaises(ValueError): self.call("get_rhino_sites", verification="stocked")

    def test_location_reports_persist_per_commander_without_rewriting_source_evidence(self):
        self.launch()
        original = next(s for s in self.call()["sites"] if s["id"] == "wregoe-iridium-31")
        report = self.call("report_rhino_site", id=original["id"], verification="confirmed", availability="reported_depleted", evidence="Fixture visit: six deployed, then depleted.")
        self.assertEqual(report["reference_evidence"], original["evidence"])
        self.assertEqual(report["sources"], original["sources"])
        self.assertEqual(report["verification"], "confirmed")
        self.assertEqual(report["availability"], "reported_depleted")
        self.assertIsNone(self.call()["selected_site"])  # Reporting does not move the destination.
        self.save(notes="An unrelated notebook edit")
        self.emit("Commander", Name="Other", FID="OTHER")
        self.assertEqual(next(s for s in self.call()["sites"] if s["id"] == original["id"]), original)
        restarted = Core(); loader.load_all(restarted); self.addCleanup(restarted.close); restarted.watcher.replay()
        after = restarted.http.tools["get_rhino_sites"].fn({})["sites"]
        self.assertEqual(next(s for s in after if s["id"] == original["id"]), report)

    def test_bookmarks_start_unconfirmed_and_moving_one_invalidates_its_report(self):
        self.launch(); site = self.save()
        self.assertEqual(site["verification"], "unconfirmed")
        report = self.call("report_rhino_site", id=site["id"], verification="confirmed", availability="unknown", evidence="Visited, found tritium.")
        edited = self.save(id=site["id"], notes="Approach from the south")
        self.assertEqual(edited["reported_at"], report["reported_at"])
        self.assertEqual(edited["verification"], "confirmed")
        moved = self.save(id=site["id"], latitude=0)
        self.assertEqual(moved["verification"], "unconfirmed")
        self.assertNotIn(site["id"], self.core.read_data("rhino-sites.json")["fid:F-RHINO"]["reports"])
        self.call("report_rhino_site", id=site["id"], verification="unconfirmed", availability="unknown", evidence="Unvisited lead")
        self.call("remove_rhino_site", id=site["id"])
        self.assertNotIn(site["id"], self.core.read_data("rhino-sites.json")["fid:F-RHINO"]["reports"])

    def test_report_validation_and_failed_persistence_leave_catalog_unchanged(self):
        params = {"id":"shinrarta-tritium", "verification":"confirmed", "availability":"unknown", "evidence":"Fixture visit"}
        with self.assertRaises(ValueError): self.call("report_rhino_site", **params)
        self.launch(); before = self.call()
        for overrides in ({"id":"missing"}, {"verification":"sure"}, {"availability":"stocked"}, {"evidence":"  "}):
            with self.assertRaises(ValueError): self.call("report_rhino_site", **{**params, **overrides})
        with patch.object(self.core, "write_data", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.call("report_rhino_site", **params)
        self.assertEqual(self.call(), before)

    def test_guide_available_without_login_bounded_by_topic_and_detached(self):
        overview = self.call("get_rhino_guide")
        self.assertEqual([s["id"] for s in overview["sections"]], ["overview"])
        full = self.call("get_rhino_guide", topic="all")
        self.assertEqual(len(full["topics"]), 10)
        for topic in full["topics"]:
            result = self.call("get_rhino_guide", topic=topic["id"])
            self.assertEqual(len(result["sections"]), 1)
            self.assertEqual(result["sections"][0], next(s for s in full["sections"] if s["id"] == topic["id"]))
            self.assertTrue(all(key in result["sources"] for key in result["sections"][0]["sources"]))
        overview["sections"][0]["steps"].clear()
        self.assertTrue(self.call("get_rhino_guide")["sections"][0]["steps"])
        for bad in ("missing", "../../guide", None, [], 1):
            with self.assertRaises(ValueError): self.call("get_rhino_guide", topic=bad)

    def test_mcp_can_discover_and_read_the_same_guide(self):
        def backend(method, path, params=None, body=None):
            if path == "/api/schema":
                return {"tools": [r.schema() for r in self.core.http.tools.values()]}
            return self.core.http.routes[(method, path)].fn(params or body or {})
        requests = [
            {"id":1, "method":"initialize", "params":{}},
            {"id":2, "method":"tools/list"},
            {"id":3, "method":"tools/call", "params":{"name":"get_rhino_guide", "arguments":{"topic":"unloading"}}},
            {"id":4, "method":"prompts/get", "params":{"name":"rhino_mining"}},
            {"id":5, "method":"tools/call", "params":{"name":"get_rhino_sites", "arguments":{"verification":"unconfirmed", "commodity":"Tritium"}}},
        ]
        output = io.StringIO()
        with patch.object(mcp, "_tool_cache", {}), patch.object(mcp, "_http", side_effect=backend), \
             patch("sys.stdin", io.StringIO("\n".join(json.dumps(r) for r in requests))), patch("sys.stdout", output):
            mcp.serve()
        replies = [json.loads(line)["result"] for line in output.getvalue().splitlines()]
        self.assertIn("get_rhino_guide", replies[0]["instructions"])
        tool = next(t for t in replies[1]["tools"] if t["name"] == "get_rhino_guide")
        self.assertIn("placement", tool["inputSchema"]["properties"]["topic"]["enum"])
        self.assertEqual(json.loads(replies[2]["content"][0]["text"]), self.call("get_rhino_guide", topic="unloading"))
        self.assertIn("get_rhino_guide", replies[3]["messages"][0]["content"]["text"])
        self.assertEqual(json.loads(replies[4]["content"][0]["text"]), self.call("get_rhino_sites", verification="unconfirmed", commodity="Tritium"))
        report_tool = next(t for t in replies[1]["tools"] if t["name"] == "report_rhino_site")
        self.assertIn("evidence", report_tool["inputSchema"]["required"])
        self.assertNotIn("report_rhino_rigs", self.core.http.tools)

    def test_mutations_are_post_and_reading_guide_is_read_only(self):
        for name in ("save_rhino_site", "select_rhino_site", "remove_rhino_site", "report_rhino_site"):
            self.assertEqual(self.core.http.tools[name].method, "POST")
        self.assertEqual(self.core.http.tools["get_rhino_status"].method, "GET")
        self.assertEqual(self.core.http.tools["get_rhino_guide"].method, "GET")
        self.assertEqual(self.core.http.tools["get_rhino_sites"].method, "GET")
        before = self.call()
        self.call("get_rhino_guide", topic="all")
        self.assertEqual(self.call(), before)
