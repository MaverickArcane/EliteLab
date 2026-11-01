"""Regression coverage for commander evidence and strictly nearby market reports."""
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

os.environ["ELITELAB_OFFLINE"] = "1"
from elitelab.core import Core, config, loader


class FixtureMixin:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.logs = Path(self.temp.name) / "journals"
        self.logs.mkdir()
        fixture = Path(__file__).parent / "fixtures/journals/progression/Journal.20261001.000000.01.log"
        shutil.copy(fixture, self.logs / fixture.name)
        p = patch.multiple(config, DATA_DIR=str(Path(self.temp.name) / "data"), JOURNAL_DIR=str(self.logs), OFFLINE=True)
        p.start()
        self.addCleanup(p.stop)
        self.core = self.make_core()

    def make_core(self):
        core = Core()
        loader.load_all(core)
        core.watcher.replay()
        return core

    def call(self, name, **q):
        return self.core.http.tools[name].fn(q)

    def emit(self, event, **fields):
        self.core.bus.emit("journal." + event, {"event": event, "timestamp": "2026-10-31T10:00:00Z", **fields})


class ProgressionTests(FixtureMixin, unittest.TestCase):
    def test_grant_separate_from_route_carrier_and_missing_evidence(self):
        self.assertEqual(self.call("get_permit_status", system="Sirius")["status"], "grant_observed")
        self.emit("CarrierJump", StarSystem="Sol", Factions=[])
        self.emit("NavRoute", Route=[{"StarSystem": "Sol"}])
        status = self.call("get_permit_status", system="Sol")
        self.assertEqual(status["status"], "unknown")
        self.assertEqual(status["last_visit"]["source"], "journal.CarrierJump")
        self.assertFalse(status["complete_permit_list"])

    def test_reputation_zero_local_presence_and_reward_indicators(self):
        self.assertEqual(self.call("get_faction_reputation", faction="Neutral Faction")["factions"][0]["reputation"], 0)
        self.assertEqual(self.call("get_faction_reputation", faction="Sirius Corporation")["factions"][0]["reputation"], 29.0625)
        self.emit("FSDJump", StarSystem="Elsewhere", Factions=[{"Name": "Local faction", "MyReputation": 12}])
        self.emit("Docked", StarSystem="Elsewhere", StationName="Port", StationFaction={"Name": "Local faction"})
        row = self.call("get_faction_reputation", faction="Sirius Corporation")["factions"][0]
        self.assertFalse(row["present_in_current_system"])
        self.assertEqual(row["system"], "Procyon")
        self.assertIsNone(self.call("get_faction_reputation", faction="Unseen")["factions"][0]["reputation"])

    def test_older_replay_and_commander_isolation(self):
        self.emit("Commander", FID="FPROGRESS-B", Name="Second Pilot")
        self.emit("Commander", timestamp="2026-10-01T10:00:00Z", FID="FPROGRESS-A", Name="Unlock Pilot")
        self.emit("MissionCompleted", timestamp="2026-10-01T10:01:00Z", MissionID=102, PermitsAwarded=["Alioth"])
        self.assertEqual(self.call("get_permit_status", system="Sirius")["status"], "unknown")
        self.assertEqual(self.call("get_faction_reputation")["factions"], [])
        self.emit("Commander", FID="FPROGRESS-A", Name="Unlock Pilot")
        self.emit("LoadGame", Commander="Unlock Pilot")
        self.assertEqual(self.call("get_permit_status", system="Alioth")["status"], "grant_observed")

    def test_history_beyond_replay_and_persistence(self):
        for day in range(27, 31):
            (self.logs / f"Journal.202610{day}.000000.01.log").write_text(json.dumps(
                {"timestamp": f"2026-10-{day}T00:00:00Z", "event": "Commander", "FID": "FPROGRESS-A", "Name": "Unlock Pilot"}) + "\n")
        self.core = self.make_core()
        self.assertEqual(self.call("get_permit_status", system="Sirius")["status"], "grant_observed")
        (self.logs / "Journal.20261001.000000.01.log").unlink()
        self.core = self.make_core()
        self.assertEqual(self.call("get_permit_status", system="Sirius")["status"], "grant_observed")

    def test_qwent_stages_contributions_not_double_counted(self):
        result = self.call("get_engineer_unlock_progress")
        self.assertTrue(result["referral_observed"])
        self.assertFalse(result["invitation_observed"])
        self.assertEqual(result["terminals"]["remaining_to_donate"], 20)
        self.assertEqual(result["terminals"]["aboard_unstolen"], 20)
        self.core.watcher.replay()
        self.assertEqual(self.call("get_engineer_unlock_progress")["terminals"]["remaining_to_donate"], 20)
        self.emit("EngineerProgress", Engineer="Marco Qwent", Progress="Invited")
        self.assertTrue(self.call("get_engineer_unlock_progress")["invitation_observed"])
        self.emit("EngineerProgress", Engineer="Marco Qwent", Progress="Unlocked", Rank=1)
        self.assertIn("no more unlock donations", self.call("get_engineer_unlock_progress")["next_action"])
        with self.assertRaises(ValueError):
            self.call("get_engineer_unlock_progress", engineer="Etienne Dorn")

    def test_stale_cargo_snapshot_does_not_leak_to_new_commander(self):
        self.emit("Commander", FID="FPROGRESS-B", Name="Second Pilot")
        self.core.bus.emit("journal.file.Cargo", {"timestamp": "2026-10-01T10:00:06Z", "Vessel": "Ship", "Inventory": [
            {"Name": "modularterminals", "Count": 25}]})
        self.assertIsNone(self.call("get_engineer_unlock_progress")["terminals"]["aboard_unstolen"])
        self.assertIsNone(self.call("get_engineer_unlock_progress")["terminals"]["remaining_to_donate"])

    def test_ship_jump_evidence_survives_docking_without_claiming_permit(self):
        self.emit("Commander", FID="FPROGRESS-B", Name="Second Pilot")
        self.emit("EngineerProgress", Engineer="Marco Qwent", Progress="Known")
        self.emit("FSDJump", StarSystem="Sirius")
        self.emit("Docked", StarSystem="Sirius", StationName="Patterson Enterprise")
        permit = self.call("get_permit_status", system="Sirius")
        self.assertEqual(permit["status"], "unknown")
        self.assertEqual(permit["last_ship_jump"]["source"], "journal.FSDJump")
        self.assertIn("does not justify a permit grind", self.call("get_engineer_unlock_progress")["next_action"])

    def test_mission_outcomes_and_active_snapshot(self):
        rows = self.call("get_mission_progress", faction="Sirius")["missions"]
        self.assertEqual(rows[0]["status"], "completed")
        self.assertEqual(rows[0]["commodity_rewards"][0]["Count"], 25)
        self.emit("MissionAccepted", MissionID=201, Faction="Sirius Corporation")
        self.emit("Missions", Active=[], Complete=[{"MissionID": 201}], Failed=[])
        rows = self.call("get_mission_progress")["missions"]
        self.assertEqual(rows[0]["status"], "ready_to_turn_in")
        self.assertFalse(self.call("get_mission_progress")["mission_board_available"])


class SourcingTests(FixtureMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.core.store.update("journal", {"system": "Sirius", "star_pos": [0, 0, 0]})
        self.rows = []
        self.urls = []
        self.catalog = [{"commodityName": "modularterminals", "totalStock": 0}]
        self.fetch = patch.object(self.core.services, "fetch_json", side_effect=self.response)
        self.fetch.start()
        self.addCleanup(self.fetch.stop)

    def response(self, url, **kwargs):
        self.urls.append(url)
        return self.catalog if url.endswith("/commodities") else self.rows

    def row(self, name="Carrier", x=5, age=1, **kwargs):
        return {"commodityName": "modularterminals", "marketId": name, "stationName": name,
                "systemName": "Nearby", "stationType": "FleetCarrier", "systemX": x, "systemY": 0, "systemZ": 0,
                "maxLandingPadSize": 3, "buyPrice": 3044, "stock": 25,
                "updatedAt": (datetime.now(timezone.utc) - timedelta(hours=age)).isoformat(), **kwargs}

    def find(self, **q):
        return self.call("find_commodity_sources", commodity="Modular Terminals", **q)

    def test_nearest_first_including_carriers_with_unknown_access(self):
        self.rows = [self.row("Far", x=20, buyPrice=100), self.row("Near", x=3)]
        result = self.find()
        self.assertEqual([r["station"] for r in result["sources"]], ["Near", "Far"])
        self.assertEqual(result["sources"][0]["cost_for_quantity"], 76100)
        self.assertEqual(result["sources"][0]["docking_access"], "unknown")
        self.assertIn("maxDistance=25", self.urls[-1])
        self.assertNotIn("fleetCarriers=", self.urls[-1])

    def test_radius_age_stock_pad_and_missing_coordinates_enforced(self):
        self.rows = [self.row("Remote", x=25.01), self.row("Old", age=49), self.row("Future", age=-1),
                     self.row("Empty", stock=24), self.row("Small", maxLandingPadSize=1), self.row("Unknown", systemX=None)]
        result = self.find()
        self.assertEqual(result["status"], "no_matching_reports_within_radius")
        self.assertEqual(sum(result["rejected"].values()), 6)
        self.assertEqual(len(self.urls), 2)

    def test_carrier_filter_and_explicit_origin(self):
        self.rows = [self.row("Carrier", x=100), self.row("Station", x=110, stationType="Coriolis Starport")]
        with patch.object(self.core.services, "edsm_coords", return_value={"Sol": {"x": 100, "y": 0, "z": 0}}):
            result = self.find(reference="Sol", carriers="exclude")
        self.assertEqual(result["sources"][0]["distance_ly"], 10)
        self.assertEqual(len(result["sources"]), 1)
        self.assertIn("fleetCarriers=0", self.urls[-1])

    def test_aliases_query_both_and_newer_report_wins(self):
        self.catalog.append({"commodityName": "modular terminals", "totalStock": 0})
        self.rows = [self.row("Duplicate", age=2), self.row("Duplicate", age=1, stock=0), self.row("Valid")]
        result = self.find()
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(len(result["source_urls"]), 2)
        self.assertTrue(any("modular%20terminals" in url for url in self.urls))

    def test_invalid_origin_and_provider_error_not_empty_success(self):
        self.core.store.set("journal", "star_pos", None)
        with patch.object(self.core.services, "edsm_coords", return_value={}):
            with self.assertRaisesRegex(ValueError, "coordinates"):
                self.find()
        self.core.store.set("journal", "star_pos", [0, 0, 0])
        self.rows = {"error": "unavailable"}
        with self.assertRaisesRegex(ValueError, "invalid nearby"):
            self.find()

    def test_invalid_radius_rejected_before_network(self):
        for value in (0, 501, True, 25.5):
            with self.assertRaises(ValueError):
                self.find(max_distance_ly=value)
        self.assertEqual(self.urls, [])


if __name__ == "__main__":
    unittest.main()
