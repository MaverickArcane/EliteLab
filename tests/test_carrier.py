"""Pinned carrier tool contract, with fixture journals and mocked community reports."""
import os
import tempfile
import unittest
from unittest.mock import patch

from test_elitelab import Core, FIXTURES, config, loader, make_core


class CarrierTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-carrier-test-")
        self.addCleanup(data.cleanup)
        for key, value in (("DATA_DIR", data.name), ("JOURNAL_DIR", os.path.join(FIXTURES, "carriers"))):
            p = patch.object(config, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.core = make_core()
        self.addCleanup(self.core.close)

    def call(self, name, **params):
        return self.core.http.tools[name].fn(params)

    def pin(self, market_id=3700000001):
        return self.call("pin_fleet_carrier", market_id=market_id)

    def report(self, **values):
        return {"record": {
            "market_id": 3700000001, "system_name": "Lave", "updated_at": "2026-10-22T11:00:00Z",
            "system_x": 1, "system_y": 2, "system_z": 3,
            "carrier_docking_access": "All", "services": [{"name": "Refuel"}], **values,
        }}

    def refresh(self, response):
        with patch.object(config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", return_value=response):
            return self.call("refresh_followed_carrier")

    def test_discovers_visits_and_replayed_carrier_jump(self):
        state = self.call("get_followed_carrier")
        self.assertIsNone(state["pinned"])
        self.assertEqual({r["market_id"] for r in state["visited"]}, {3700000001, 3700000002})
        carrier = self.pin()["pinned"]
        self.assertEqual(carrier["callsign"], "TST-001")
        self.assertEqual(carrier["system"], "Zaonce")
        self.assertEqual(carrier["services"], ["refuel", "repair"])
        self.assertEqual(carrier["source"], "journal")
        self.assertEqual(carrier["distance"], 0)
        self.assertNotIn("balance", carrier)
        self.assertNotIn("fuel", carrier)

    def test_pin_survives_restart_without_replay_and_unpin_preserves_owner(self):
        owned = self.call("get_commander_state")["carrier"]
        self.pin()
        restarted = Core()
        loader.load_all(restarted)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.http.tools["get_followed_carrier"].fn({})["pinned"]["market_id"], 3700000001)
        state = self.call("unpin_fleet_carrier")
        self.assertIsNone(state["pinned"])
        self.assertEqual(len(state["visited"]), 2)
        self.assertEqual(self.call("get_commander_state")["carrier"], owned)
        restarted = Core()
        loader.load_all(restarted)
        self.addCleanup(restarted.close)
        self.assertIsNone(restarted.http.tools["get_followed_carrier"].fn({})["pinned"])

    def test_archive_discovers_visits_without_recent_replay(self):
        # Use another empty data directory, then trigger archive discovery without replaying any events.
        with tempfile.TemporaryDirectory() as data, patch.object(config, "DATA_DIR", data):
            core = Core()
            loader.load_all(core)
            self.addCleanup(core.close)
            core.bus.emit("journal.replay.done", 0)
            state = core.http.tools["get_followed_carrier"].fn({})
            self.assertEqual({r["market_id"] for r in state["visited"]}, {3700000001, 3700000002})

    def test_unknown_pin_is_rejected(self):
        with self.assertRaises(ValueError):
            self.pin(999)

    def test_unrelated_carrier_does_not_move_pin(self):
        before = self.pin()["pinned"]
        for event in ("Docked", "CarrierJump"):
            with self.subTest(event=event):
                self.core.bus.emit("journal." + event, {
                    "timestamp": "2026-10-22T12:00:00Z", "event": event, "Docked": True,
                    "StationName": "TST-002", "StationType": "FleetCarrier", "MarketID": 3700000002,
                    "StarSystem": "Sol", "StarPos": [0, 0, 0],
                })
                after = self.call("get_followed_carrier")["pinned"]
                self.assertEqual(after["system"], before["system"])
                self.assertEqual(after["market_id"], before["market_id"])
        self.assertGreater(after["distance"], 0)

    def test_matching_live_jump_and_location_update_pin(self):
        self.pin()
        for event in ("CarrierJump", "Location"):
            with self.subTest(event=event):
                self.core.bus.emit("journal." + event, {
                    "timestamp": "2026-10-22T12:00:00Z", "event": event, "Docked": True,
                    "StationName": "TST-001", "StationType": "FleetCarrier", "MarketID": 3700000001,
                    "StarSystem": "Sol", "StarPos": [0, 0, 0], "StationServices": ["refuel"],
                })
                state = self.call("get_followed_carrier")["pinned"]
                self.assertEqual(state["system"], "Sol")
                self.assertEqual(state["source"], "journal")

    def test_new_remote_report_updates_pin_and_is_persisted(self):
        self.pin()
        state = self.refresh(self.report())
        self.assertEqual(state["pinned"]["system"], "Lave")
        self.assertEqual(state["pinned"]["docking"], "All")
        self.assertEqual(state["pinned"]["source"], "Spansh")
        self.assertIsNotNone(state["checked_at"])
        restarted = make_core()
        self.assertEqual(restarted.http.tools["get_followed_carrier"].fn({})["pinned"]["system"], "Lave")

    def test_older_and_equal_remote_reports_cannot_replace_journal(self):
        before = self.pin()["pinned"]
        for updated in ("2026-10-22T09:00:00Z", before["observed_at"]):
            with self.subTest(updated=updated):
                state = self.refresh(self.report(updated_at=updated))
                self.assertEqual(state["pinned"], before)

    def test_new_journal_observation_supersedes_remote(self):
        self.pin()
        self.refresh(self.report())
        self.core.bus.emit("journal.Docked", {
            "timestamp": "2026-10-22T12:00:00Z", "event": "Docked", "StationName": "TST-001",
            "StationType": "FleetCarrier", "MarketID": 3700000001, "StarSystem": "Sol",
        })
        state = self.call("get_followed_carrier")["pinned"]
        self.assertEqual(state["system"], "Sol")
        self.assertEqual(state["source"], "journal")
        # A different system without coordinates must not retain the previous system's marker.
        self.assertIsNone(state["star_pos"])

    def test_failed_or_mismatched_report_keeps_cached_data(self):
        before = self.pin()["pinned"]
        for response in ({}, self.report(market_id=999), self.report(updated_at=None)):
            with self.subTest(response=response):
                state = self.refresh(response)
                self.assertEqual(state["pinned"], before)
                self.assertTrue(state["error"])
                self.assertFalse(state["refreshing"])
        with patch.object(config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=OSError("unavailable")):
            state = self.call("refresh_followed_carrier")
            self.assertEqual(state["pinned"], before)
            self.assertTrue(state["error"])

    def test_offline_refresh_does_not_request_network(self):
        before = self.pin()["pinned"]
        with patch.object(self.core.services, "fetch_json") as fetch:
            state = self.call("refresh_followed_carrier")
        fetch.assert_not_called()
        self.assertEqual(state["pinned"], before)

    def test_remote_optional_fields_may_be_missing(self):
        self.pin()
        state = self.refresh(self.report(services=None, system_x=None))
        self.assertIsNone(state["error"])
        self.assertIsNone(state["pinned"]["star_pos"])
        self.assertEqual(state["pinned"]["services"], [])

    def test_inflight_report_cannot_restore_removed_pin(self):
        self.pin()

        def fetch(*args, **kwargs):
            self.call("unpin_fleet_carrier")
            return self.report()

        with patch.object(config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=fetch):
            state = self.call("refresh_followed_carrier")
        self.assertIsNone(state["pinned"])
        self.assertFalse(state["refreshing"])

    def test_inflight_report_cannot_overwrite_new_pin(self):
        self.pin()

        def fetch(*args, **kwargs):
            self.pin(3700000002)
            return self.report()

        with patch.object(config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", side_effect=fetch):
            state = self.call("refresh_followed_carrier")
        self.assertEqual(state["pinned"]["market_id"], 3700000002)
        self.assertEqual(state["pinned"]["system"], "Zaonce")

    def test_only_carrier_card_manifest_moves(self):
        cards = [(m.name, c["id"]) for m in self.core.modules.values() for c in m.cards if c["id"] == "carrier"]
        self.assertEqual(cards, [("carrier", "carrier")])
        schema = self.call("list_tools")["tools"]
        tools = [t for t in schema if t["module"] == "carrier"]
        self.assertEqual(len(tools), 4)
        self.assertTrue(all(t["description"] for t in tools))


if __name__ == "__main__":
    unittest.main()
