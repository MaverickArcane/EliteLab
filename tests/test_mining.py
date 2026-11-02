"""Mining tool contract: replay, live events, timing and bounded journal input."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core, config, loader

FIXTURE = Path(__file__).parent / "fixtures" / "mining"


class MiningTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-mining-")
        self.addCleanup(data.cleanup)
        for key, value in (("DATA_DIR", data.name), ("JOURNAL_DIR", str(FIXTURE))):
            p = patch.object(config, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.core = Core()
        self.addCleanup(self.core.close)
        loader.load_all(self.core)

    def state(self):
        return self.core.http.tools["get_mining_status"].fn({})

    def emit(self, event, timestamp="2026-10-22T12:00:00Z", **fields):
        self.core.bus.emit("journal." + event, {"event": event, "timestamp": timestamp, **fields})

    def test_replay_counts_only_latest_session_and_keeps_same_second_units(self):
        self.core.watcher.replay()
        m = self.state()
        self.assertEqual(m["commander"], "Test Miner")
        self.assertEqual(m["refined_tons"], 3)
        self.assertEqual([(r["key"], r["tons"]) for r in m["commodities"]], [("platinum", 2), ("palladium", 1)])
        self.assertEqual(m["prospector_reports"], 2)
        self.assertEqual(m["tons_per_hour"], 6)
        self.assertEqual(m["elapsed_seconds"], 1800)
        self.assertFalse(m["partial"])
        self.assertTrue(m["ended"])
        self.assertEqual(m["last_prospect"]["remaining"], 0)
        self.assertEqual(m["last_prospect"]["motherlode"], "Alexandrite")
        self.assertEqual(m["last_prospect"]["materials"][0]["name"], "Low Temperature Diamonds")
        self.core.watcher.replay()
        self.assertEqual(self.state(), m)

    def test_live_and_replay_agree(self):
        for line in next(FIXTURE.glob("Journal.*.log")).read_text().splitlines():
            ev = json.loads(line)
            self.core.bus.emit("journal." + ev["event"], ev)
        live = self.state()
        self.core.watcher.replay()
        self.assertEqual(self.state(), live)

    def test_rate_waits_one_minute_includes_idle_and_freezes_after_shutdown(self):
        self.emit("LoadGame", Commander="Miner")
        self.emit("MiningRefined", Type="Gold", Count=999)
        self.assertIsNone(self.state()["tons_per_hour"])
        self.emit("Music", "2026-10-22T12:00:59Z")
        self.assertIsNone(self.state()["tons_per_hour"])
        self.emit("Music", "2026-10-22T12:01:00Z")
        self.assertEqual(self.state()["tons_per_hour"], 60)
        self.emit("Shutdown", "2026-10-22T13:00:00Z")
        self.assertEqual(self.state()["tons_per_hour"], 1)
        frozen = self.state()
        self.emit("Music", "2026-10-23T12:00:00Z")
        self.assertEqual(self.state(), frozen)

    def test_loadgame_and_changed_commander_reset_but_file_continuation_does_not(self):
        self.emit("LoadGame", Commander="A", FID="F1")
        self.emit("MiningRefined", Type="Gold")
        self.emit("FileHeader", part=2)
        self.emit("Commander", Name="A", FID="F1")
        self.assertEqual(self.state()["refined_tons"], 1)
        self.emit("Commander", Name="B", FID="F2")
        self.assertEqual(self.state()["refined_tons"], 0)
        self.assertTrue(self.state()["partial"])
        self.emit("MiningRefined", Type="Gold")
        self.emit("LoadGame", Commander="B", FID="F2")
        self.assertEqual(self.state()["refined_tons"], 0)
        self.assertFalse(self.state()["partial"])

    def test_partial_replay_and_missing_timestamps_are_explicit(self):
        self.emit("MiningRefined", None, Type="Gold")
        self.emit("MiningRefined", Type="Gold")
        self.emit("Music", "2026-10-22T13:00:00Z")
        self.assertTrue(self.state()["partial"])
        self.assertTrue(self.state()["timing_incomplete"])
        self.assertIsNone(self.state()["tons_per_hour"])
        self.assertEqual(self.state()["refined_tons"], 2)

    def test_out_of_order_timestamps_do_not_shrink_elapsed_time(self):
        self.emit("ProspectedAsteroid")
        self.emit("MiningRefined", "2026-10-22T13:00:00Z", Type="Gold")
        self.emit("Music", "2026-10-22T12:01:00Z")
        self.assertEqual(self.state()["elapsed_seconds"], 3600)
        self.emit("MiningRefined", "2026-10-22T11:00:00Z", Type="Gold")
        self.assertEqual(self.state()["elapsed_seconds"], 7200)
        self.assertEqual(self.state()["tons_per_hour"], 1)

    def test_cargo_sales_and_ejection_do_not_change_production(self):
        self.emit("MiningRefined", Type="Gold")
        for event in ("MarketBuy", "MarketSell", "EjectCargo", "Cargo", "MaterialCollected"):
            self.emit(event, Type="Gold", Count=200)
        self.assertEqual(self.state()["refined_tons"], 1)

    def test_malformed_prospect_values_remain_json_safe_and_bounded(self):
        for bad in (float("nan"), float("inf"), -1, 101, True, {}, [], "80", 10**400):
            self.emit("ProspectedAsteroid", Materials=[None, {"Name": "Gold", "Proportion": bad}],
                      Remaining=bad, Content=[], MotherlodeMaterial={})
            m = self.state()
            self.assertIsNone(m["last_prospect"]["remaining"])
            self.assertIsNone(m["last_prospect"]["materials"][0]["proportion"])
            json.dumps(m, allow_nan=False)
        self.emit("ProspectedAsteroid", Materials=[{"Name": "x"*2000, "Proportion": 20}]*1000)
        m = self.state()
        self.assertEqual(len(m["last_prospect"]["materials"]), 32)
        self.assertEqual(len(m["last_prospect"]["materials"][0]["name"]), 160)

    def test_unknown_commodity_and_cardinality_preserve_total(self):
        for i in range(260):
            self.emit("MiningRefined", Type=f"synthetic{i}")
        self.emit("MiningRefined", Type=[])
        m = self.state()
        self.assertEqual(len(m["commodities"]), 256)
        self.assertEqual(m["other_tons"], 5)
        self.assertEqual(sum(r["tons"] for r in m["commodities"]) + m["other_tons"], 261)

    def test_read_only_tool_and_store_snapshots_are_independent(self):
        self.emit("MiningRefined", Type="Gold")
        m = self.state()
        m["commodities"][0]["tons"] = 100
        self.assertEqual(self.state()["commodities"][0]["tons"], 1)
        self.assertEqual(self.core.http.tools["get_mining_status"].method, "GET")
        self.assertFalse(os.path.exists(os.path.join(config.DATA_DIR, "mining.json")))
