"""Mining merit evidence, provider power boundaries and authenticated MCP transport."""
import copy
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import test_mining
from test_mining_desk import DATA, NOW
from elitelab.core import config
from elitelab.core.http import make_handler


class MiningPowerplayTests(unittest.TestCase):
    setUp = test_mining.MiningTests.setUp
    state = test_mining.MiningTests.state
    emit = test_mining.MiningTests.emit

    def prepare(self):
        self.emit("LoadGame", Commander="Miner")
        self.emit("Docked", StarSystem="Delkar", StationName="Test station")
        self.emit("Powerplay", Power="Edmund Mahon", Merits=1000)
        self.emit("Cargo", Inventory=[])
        self.emit("MiningRefined", Type="Platinum")
        self.emit("MarketSell", Type="Platinum", Count=1, TotalSale=200000)

    def gain(self, timestamp="2026-10-22T12:00:01Z", **kw):
        self.emit("PowerplayMerits", timestamp, **{"Power":"Edmund Mahon", "MeritsGained":100, "TotalMerits":1100, **kw})

    def test_recorded_totals_separate_from_estimated_sale_association(self):
        self.prepare()
        self.gain()
        self.gain("2026-10-22T12:00:02Z", MeritsGained=500, TotalMerits=1600)
        p = self.state()["powerplay"]
        self.assertEqual((p["session_merits"], p["sale_associated_merits"], p["unassociated_merits"], p["total_merits"]), (600,100,500,1600))
        self.assertTrue(p["association_estimated"])
        self.assertEqual(p["recent"][1]["sale"]["station"], "Test station")
        self.assertEqual(self.state()["profit"]["net_profit"], 200000)

    def test_time_window_excludes_future_old_and_missing_timestamps(self):
        for ts in ["2026-10-22T11:59:59Z", "2026-10-22T12:00:13Z", "bad", None]:
            with self.subTest(ts=ts):
                self.prepare(); self.gain(ts)
                self.assertEqual(self.state()["powerplay"]["sale_associated_merits"], 0)
                self.assertEqual(self.state()["powerplay"]["session_merits"], 100)
        for ts in ["2026-10-22T12:00:00Z", "2026-10-22T12:00:12Z"]:
            self.prepare(); self.gain(ts)
            self.assertEqual(self.state()["powerplay"]["sale_associated_merits"], 100)

    def test_competing_activity_travel_and_nonmined_sales_break_association(self):
        for event, fields in [("Bounty", {}), ("MissionCompleted", {}), ("FSDJump", {}), ("Docked", {}),
                              ("CarrierJump", {"StarSystem":"Elsewhere"}), ("PowerplayDeliver", {}), ("MarketSell", {"Type":"Gold", "Count":1, "TotalSale":10})]:
            with self.subTest(event=event):
                self.prepare(); self.emit(event, **fields); self.gain()
                self.assertEqual(self.state()["powerplay"]["sale_associated_merits"], 0)

    def test_mixed_and_missing_cargo_baselines_never_claim_mining_merits(self):
        for baseline in [None, [{"Name":"Platinum","Count":1}]]:
            self.emit("LoadGame", Commander="Miner")
            self.emit("Powerplay", Power="Edmund Mahon", Merits=1000)
            if baseline is not None: self.emit("Cargo", Inventory=baseline)
            self.emit("MiningRefined", Type="Platinum")
            self.emit("MarketSell", Type="Platinum", Count=2 if baseline else 1, TotalSale=200000)
            self.gain()
            self.assertEqual(self.state()["powerplay"]["sale_associated_merits"], 0)
            self.assertEqual(self.state()["powerplay"]["session_merits"], 100)

    def test_resets_wrong_power_and_shutdown(self):
        for event, fields in [("LoadGame", {"Commander":"Miner"}), ("Commander", {"Name":"Other"}),
                              ("PowerplayLeave", {}), ("PowerplayDefect", {"ToPower":"Aisling Duval"}),
                              ("PowerplayJoin", {"Power":"Edmund Mahon"})]:
            self.prepare(); self.gain(); self.emit(event, **fields)
            self.assertEqual(self.state()["powerplay"]["session_merits"], 0)
        self.prepare(); self.gain(Power="Aisling Duval")
        self.assertEqual(self.state()["powerplay"]["session_merits"], 0)
        self.emit("Shutdown"); before = self.state(); self.gain()
        self.assertEqual(self.state(), before)

    def test_malformed_gains_bounded_history_and_replay(self):
        # Exercise the mining handler directly: unrelated legacy listeners do
        # not validate malformed gains and are outside this module's contract.
        from modules.mining.powerplay import MiningPowerplay
        from modules.mining.ledger import Ledger
        p = MiningPowerplay()
        for value in [True, -1, 0.5, float("inf"), float("nan"), "100", 10**400]:
            p.event({"event":"PowerplayMerits", "MeritsGained":value}, 1, 0, Ledger())
        self.assertEqual(p.summary()["session_merits"], 0)
        self.prepare()
        for i in range(20): self.gain(MeritsGained=1)
        self.assertEqual(len(self.state()["powerplay"]["recent"]), 12)
        before = self.state()["powerplay"]
        self.prepare()
        for i in range(20): self.gain(MeritsGained=1, _replay=True)
        self.core.bus.emit("journal.replay.done", {})
        self.assertEqual(self.state()["powerplay"], before)

    def test_partial_history_can_read_power_from_merit_event(self):
        self.gain()
        p = self.state()["powerplay"]
        self.assertEqual(p["power"], "Edmund Mahon")
        self.assertEqual(p["session_merits"], 100)
        self.assertEqual(p["sale_associated_merits"], 0)

    def fetch(self, url, *args, **kwargs):
        return {"min_max":{"Platinum":{}}} if "field_values" in url else copy.deepcopy(DATA["bodies" if "/bodies/" in url else "stations"])

    def test_buyer_power_filter_uses_pledge_and_rechecks_provider_claims(self):
        self.prepare()
        with patch.object(config, "OFFLINE", False), patch("modules.mining.discovery.time.time", return_value=NOW), patch.object(self.core.services, "fetch_json", side_effect=self.fetch) as fetch:
            tool = self.core.http.tools["find_mining_buyers"].fn
            a = tool({"ref":"Delkar", "commodity":"Platinum", "powerplay_mode":"acquisition"})
            self.assertEqual(a["power"], "Edmund Mahon")
            self.assertEqual([r["station"] for r in a["results"]], ["Test Miners Landing"])
            self.assertEqual(fetch.call_args.args[1]["filters"]["system_power"]["value"], ["Edmund Mahon"])
            self.assertIsNone(a["merit_estimate"])
            b = tool({"ref":"Delkar", "commodity":"Platinum", "powerplay_mode":"reinforcement"})
            self.assertEqual([r["station"] for r in b["results"]], ["Test Prospect Exchange"])
            c = tool({"ref":"Delkar", "commodity":"Platinum", "powerplay_mode":"reinforcement", "power":"Aisling Duval"})
            self.assertEqual(c["results"], [])

    def test_invalid_power_inputs_fail_before_network(self):
        self.prepare()
        self.emit("LoadGame", Commander="Miner")
        self.assertEqual(self.core.store.get("powerplay", "power"), "Edmund Mahon")
        with patch.object(self.core.services, "fetch_json") as fetch:
            for q in [{"powerplay_mode":"acquisition"}, {"powerplay_mode":[]}, {"power":[]}, {"power":"unknown"}, {"powerplay_mode":"javascript:"}]:
                with self.subTest(q=q), self.assertRaises(ValueError):
                    self.core.http.tools["find_mining_buyers"].fn({"ref":"Delkar", "commodity":"Platinum", **q})
            fetch.assert_not_called()

    def test_authenticated_mcp_schema_calls_resource_prompt_and_errors(self):
        self.prepare(); self.gain()
        self.core.store.update("journal", {"jump_range_laden":25, "jump_range_now":30})
        with patch.object(config, "AUTH_TOKEN", "mining-test-token"), patch.object(config, "OFFLINE", False), patch("modules.mining.discovery.time.time", return_value=NOW), patch.object(self.core.services, "fetch_json", side_effect=self.fetch):
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.core))
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                requests = [
                    ("initialize", {}), ("tools/list", {}),
                    ("tools/call", {"name":"get_mining_status"}),
                    ("tools/call", {"name":"find_mining_spots", "arguments":{"ref":"Delkar","pristine":True,"radius":200,"sort":"merits","hotspot":"Platinum","power":"Edmund Mahon","powerplay_mode":"reinforcement"}}),
                    ("tools/call", {"name":"find_mining_buyers", "arguments":{"ref":"Delkar","commodity":"Platinum","powerplay_mode":"acquisition"}}),
                    ("resources/read", {"uri":"elitelab://state/mining"}), ("prompts/get", {"name":"mining_run"}),
                    ("tools/call", {"name":"find_mining_buyers", "arguments":{"commodity":"Platinum","powerplay_mode":"bad"}})]
                messages = "".join(json.dumps({"jsonrpc":"2.0","id":i,"method":m,"params":q})+"\n" for i,(m,q) in enumerate(requests))
                env = dict(os.environ, ELITELAB_URL=f"http://127.0.0.1:{server.server_port}", ELITELAB_AUTH_TOKEN="mining-test-token")
                run = subprocess.run([sys.executable,"-m","elitelab","mcp"], cwd=config.ROOT, env=env, input=messages, capture_output=True, text=True, timeout=25, check=True)
                replies = [json.loads(line)["result"] for line in run.stdout.splitlines()]
                schema = next(t["inputSchema"] for t in replies[1]["tools"] if t["name"] == "find_mining_buyers")
                self.assertEqual(schema["properties"]["powerplay_mode"]["enum"], ["none","acquisition","reinforcement"])
                spot_schema = next(t["inputSchema"] for t in replies[1]["tools"] if t["name"] == "find_mining_spots")
                self.assertEqual(spot_schema["properties"]["sort"]["enum"], ["distance", "merits"])
                for i in (2,3,4): self.assertFalse(replies[i]["isError"], replies[i])
                self.assertEqual(json.loads(replies[2]["content"][0]["text"])["powerplay"]["sale_associated_merits"], 100)
                spots = json.loads(replies[3]["content"][0]["text"])
                self.assertEqual(spots["radius"], 25)
                self.assertEqual(spots["results"][0]["buyer"]["system"], "Delkar")
                self.assertIsNone(spots["results"][0]["merit_estimate"])
                self.assertEqual(json.loads(replies[4]["content"][0]["text"])["power"], "Edmund Mahon")
                self.assertEqual(json.loads(replies[5]["contents"][0]["text"])["summary"]["powerplay"]["session_merits"], 100)
                self.assertIn("Do not promise eligibility", replies[6]["messages"][0]["content"]["text"])
                self.assertTrue(replies[7]["isError"])
                env["ELITELAB_AUTH_TOKEN"] = "wrong-token"
                denied = subprocess.run([sys.executable,"-m","elitelab","mcp"], cwd=config.ROOT, env=env, input=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_mining_status"}})+"\n", capture_output=True, text=True, timeout=15, check=True)
                self.assertTrue(json.loads(denied.stdout)["result"]["isError"])
                self.assertNotIn("mining-test-token", denied.stdout)
            finally:
                server.shutdown(); server.server_close(); thread.join(5)
