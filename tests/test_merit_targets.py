"""Rare cargo pricing, distance curves and adversarial target ranking."""
import copy
import json
import os
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import unittest
from unittest.mock import patch

import test_mining
from elitelab.core import config
from elitelab.core.http import make_handler

DATA = json.loads((Path(__file__).parent / "fixtures/targets/stations.json").read_text())
NOW = 1793588400  # 2026-11-02 03:00 UTC


class MeritTargetTests(unittest.TestCase):
    setUp = test_mining.MiningTests.setUp
    emit = test_mining.MiningTests.emit

    def prepare(self):
        self.emit("LoadGame", Commander="Target Tester")
        self.emit("Powerplay", Power="Edmund Mahon")
        self.emit("Location", StarSystem="Zaonce", StarPos=[0,0,0], Docked=True, StationType="Orbis", StationName="Ridley Scott")
        self.emit("MarketBuy", Type="alieneggs", Count=10, BuyPrice=500)
        self.core.store.update("journal", {"jump_range_laden":20, "jump_range_now":25,
                              "cargo":{"items":[{"key":"alieneggs", "name":"Leathery Eggs", "count":10, "rare":True}]}})

    def run_search(self, q=None, data=None, fetch=None):
        args = {"min":0, "max":200, "rate_mode":"mahon_observed", **(q or {})}
        with patch.object(self.core.config, "OFFLINE", False), patch("modules.targets.planner.time.time", return_value=NOW), \
                patch.object(self.core.services, "fetch_json", side_effect=fetch, return_value=copy.deepcopy(data or DATA)) as mocked:
            result = self.core.http.tools["find_sell_targets"].fn(args)
        return result, mocked

    def test_ranks_merits_per_laden_jump_not_price_or_unladen_range(self):
        self.prepare()
        out, _ = self.run_search()
        near, far, unknown = out["results"]
        self.assertEqual([r["system"] for r in out["results"]], ["Test Near","Test Far","Test Middle"])
        self.assertEqual(near["jumps"], 4)
        self.assertEqual(near["estimated_sale"], 200000)
        self.assertGreater(near["merits_per_jump"], far["merits_per_jump"])
        self.assertIsNone(unknown["estimated_merits"])
        self.assertEqual(self.run_search({"sort":"merits"})[0]["results"][0]["system"], "Test Far")

    def test_curve_is_opt_in_interpolation_only_and_preserves_reported_quotes(self):
        self.prepare()
        out, _ = self.run_search({"interpolate":True})
        middle = next(r for r in out["results"] if r["system"] == "Test Middle")
        self.assertEqual(middle["goods"]["alieneggs"]["price"], 25000)
        self.assertEqual(middle["goods"]["alieneggs"]["status"], "interpolated")
        self.assertEqual(len(out["curves"][0]["points"]), 2)
        data = copy.deepcopy(DATA)
        data["results"][1]["system_x"] = 200
        self.assertIsNone(next(r for r in self.run_search({"interpolate":True},data)[0]["results"] if r["system"]=="Test Middle")["estimated_sale"])
        data["results"][1]["system_x"] = 120
        data["results"][1]["market"] = []
        row = next(r for r in self.run_search({"interpolate":True},data)[0]["results"] if r["system"]=="Test Middle")
        self.assertIsNone(row["estimated_sale"])
        self.assertEqual(row["refuses"], [])
        self.assertIsNone(row["accepts_all"])

    def test_each_rares_source_differs_from_manual_travel_origin(self):
        self.prepare()
        out, _ = self.run_search({"ref":"Sol"})
        self.assertTrue(out["manual_origin"])
        self.assertEqual(out["cargo"][0]["origin"], "Zaonce")
        self.assertEqual(out["results"][0]["goods"]["alieneggs"]["source_distance"], 80)
        self.emit("Location", StarSystem="Lave", StarPos=[60,0,0], Docked=True, StationType="Orbis")
        self.emit("MarketBuy", Type="lavianbrandy", Count=3)
        self.core.store.set("journal", "cargo", {"items":[{"key":"alieneggs","count":10},{"key":"lavianbrandy","count":3}]})
        data = copy.deepcopy(DATA)
        for r in data["results"]:
            r["market"].append({"commodity":"Lavian Brandy", "sell_price":10000, "demand":100})
        out, _ = self.run_search(data=data)
        near = next(r for r in out["results"] if r["system"]=="Test Near")
        self.assertEqual(near["goods"]["lavianbrandy"]["source_distance"], 20)
        self.assertEqual(near["estimated_sale"], 230000)

    def test_unknown_rates_ranges_and_partial_loads_are_not_zero(self):
        self.prepare()
        self.assertIsNone(self.run_search({"rate_mode":"unknown"})[0]["results"][0]["estimated_merits"])
        self.core.store.set("journal", "jump_range_laden", None)
        out, _ = self.run_search()
        self.assertTrue(all(r["merits_per_jump"] is None for r in out["results"]))
        self.core.store.set("journal", "cargo", {"items":[{"key":"alieneggs","count":10},{"key":"lavianbrandy","count":3}]})
        row = self.run_search()[0]["results"][0]
        self.assertIsNone(row["estimated_sale"])
        self.assertIsNone(row["estimated_merits"])
        self.assertGreater(row["priced_subtotal"], 0)

    def test_known_cargo_restrictions_block_merits_not_credit_quotes(self):
        for event in ("transfer", "same_origin", "stolen"):
            self.prepare()
            data = copy.deepcopy(DATA)
            if event == "transfer": self.emit("CargoTransfer", Transfers=[{"Type":"alieneggs","Direction":"toship","Count":10}])
            if event == "same_origin": data["results"][0]["system_name"] = "Zaonce"
            if event == "stolen": self.core.store.set("journal", "cargo", {"items":[{"key":"alieneggs","count":10,"stolen":1}]})
            out, _ = self.run_search(data=data)
            row = next(r for r in out["results"] if r["station"]=="Test Near Exchange")
            self.assertEqual(row["merit_eligibility"], "blocked")
            self.assertIsNone(row["estimated_merits"])
            self.assertEqual(row["estimated_sale"], 200000)

    def test_provider_filters_rechecked_and_bad_quotes_cannot_seed_curves(self):
        self.prepare()
        for changes in ({"system_power":["Aisling Duval"]},{"system_power_state":"Stronghold"},{"has_large_pad":False},
                        {"type":"Fleet Carrier"},{"is_planetary":True},{"distance":201},{"distance":float("nan")}):
            data={"results":[{**DATA["results"][0],**changes}]}
            with self.subTest(changes=changes):self.assertEqual(self.run_search(data=data)[0]["results"], [])
        for changes in ({"sell_price":float("nan")},{"is_prohibited":True},{"demand":1},{"demand":None}):
            data=copy.deepcopy(DATA);data["results"][0]["market"][0].update(changes)
            out,_=self.run_search({"interpolate":True},data)
            self.assertEqual(len(out["curves"][0]["points"]),1)
        data=copy.deepcopy(DATA);data["results"][0]["market_updated_at"]="2099-01-01T00:00:00Z"
        self.assertEqual(len(self.run_search(data=data)[0]["curves"][0]["points"]),1)

    def test_validation_precedes_network_and_never_guesses_pledge(self):
        self.prepare()
        for q in ({"rate_mode":"mahon_observed","power":"Aisling Duval"},{"min":200,"max":100},{"max":"nan"},
                  {"limit":-1},{"limit":True},{"hours":float("inf")},{"sort":{}},{"pad":[]},
                  {"rate_mode":"custom","credits_per_merit":0},{"interpolate":"yes"},{"interpolate":1},{"ref":{}},{"power":[]}):
            with self.subTest(q=q),patch.object(config,"OFFLINE",False),patch.object(self.core.services,"fetch_json") as fetch,self.assertRaises(ValueError):
                self.core.http.tools["find_sell_targets"].fn(q)
            fetch.assert_not_called()
        self.emit("LoadGame",Commander="Other commander")
        self.assertEqual(self.core.store.get("powerplay","power"),"Edmund Mahon")
        with self.assertRaisesRegex(ValueError,"Pledged power unknown"):self.run_search()

    def test_live_changes_clear_cached_results_and_reject_inflight_responses(self):
        self.prepare();self.run_search()
        self.assertIsNotNone(self.core.store.get("targets","last"))
        self.core.store.set("journal","jump_range_laden",15)
        self.assertIsNone(self.core.store.get("targets","last"))
        def change(*args,**kwargs):
            self.core.store.set("journal","cargo",{"items":[]})
            return DATA
        with self.assertRaisesRegex(ValueError,"changed"):self.run_search(fetch=change)

    def test_pagination_bounded_error_redacted_and_partial_disclosed(self):
        self.prepare()
        first={"results":[{**DATA["results"][0],"name":f"Station {i}"} for i in range(25)],"count":10000}
        out,fetch=self.run_search(fetch=lambda *a,**k:first)
        self.assertEqual(fetch.call_count,4)
        self.assertEqual(out["stations_checked"],100)
        def partial(*a,**k):
            if a[1]["page"]:raise RuntimeError("private secret")
            return first
        self.assertTrue(self.run_search(fetch=partial)[0]["partial"])
        with self.assertRaisesRegex(ValueError,"Spansh target search unavailable") as caught:
            self.run_search(fetch=lambda *a,**k:(_ for _ in ()).throw(RuntimeError("private secret")))
        self.assertNotIn("secret",str(caught.exception))

    def test_commander_and_replay_boundaries_clear_previous_evidence(self):
        self.prepare()
        self.emit("LoadGame", Commander="Target Tester", FID="F1")
        self.emit("Powerplay", Power="Edmund Mahon")
        self.emit("MarketBuy", Type="alieneggs", Count=10)
        self.emit("Commander", Name="Target Tester", FID="F1")
        self.assertEqual(self.run_search()[0]["cargo"][0]["origin"], "Zaonce")
        self.core.bus.emit("journal.replay", 5)
        self.emit("Commander", Name="Target Tester", FID="F2")
        self.assertEqual(self.core.store.get("targets", "origins"), {})
        self.assertIsNone(self.core.store.get("targets", "pledge"))
        with self.assertRaisesRegex(ValueError,"Pledged power unknown"):self.run_search()

    def test_carrier_purchase_duplicate_quotes_and_zero_jump(self):
        self.prepare()
        self.core.store.set("journal","station_type","FleetCarrier")
        self.emit("MarketBuy",Type="alieneggs",Count=10)
        self.assertTrue(all(r["estimated_merits"] is None for r in self.run_search()[0]["results"]))
        self.prepare()
        data=copy.deepcopy(DATA)
        data["results"][0]["distance"]=0
        row=next(r for r in self.run_search(data=data)[0]["results"] if r["system"]=="Test Near")
        self.assertEqual(row["jumps"],0)
        self.assertIsNone(row["merits_per_jump"])
        data["results"][0]["market"]*=2
        row=next(r for r in self.run_search(data=data)[0]["results"] if r["system"]=="Test Near")
        self.assertIsNone(row["estimated_sale"])

    def test_authenticated_mcp_uses_same_planner_resource_prompt_and_validation(self):
        self.prepare()
        before=self.core.store.get("powerplay")
        with patch.object(config,"AUTH_TOKEN","targets-test-token"),patch.object(config,"OFFLINE",False),patch("modules.targets.planner.time.time",return_value=NOW),patch.object(self.core.services,"fetch_json",return_value=copy.deepcopy(DATA)):
            server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.core))
            server.daemon_threads=True
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                calls=[("tools/list",{}),("tools/call",{"name":"find_sell_targets","arguments":{"min":0,"rate_mode":"mahon_observed","interpolate":True}}),
                       ("resources/read",{"uri":"elitelab://state/targets"}),("prompts/get",{"name":"plan_rares_run"}),
                       ("tools/call",{"name":"find_sell_targets","arguments":{"power":"Aisling Duval","rate_mode":"mahon_observed"}})]
                messages="".join(json.dumps({"jsonrpc":"2.0","id":i,"method":m,"params":q})+"\n" for i,(m,q) in enumerate(calls))
                env=dict(os.environ,ELITELAB_URL=f"http://127.0.0.1:{server.server_port}",ELITELAB_AUTH_TOKEN="targets-test-token")
                run=subprocess.run([sys.executable,"-m","elitelab","mcp"],cwd=config.ROOT,env=env,input=messages,capture_output=True,text=True,timeout=25,check=True)
                replies=[json.loads(line)["result"] for line in run.stdout.splitlines()]
                schema=next(t["inputSchema"] for t in replies[0]["tools"] if t["name"]=="find_sell_targets")
                self.assertEqual(schema["properties"]["interpolate"]["type"],"boolean")
                self.assertFalse(replies[1]["isError"],replies[1])
                result=json.loads(replies[1]["content"][0]["text"])
                self.assertEqual(result["results"][0]["system"],"Test Near")
                self.assertEqual(result,json.loads(replies[2]["contents"][0]["text"])["last"])
                self.assertIn("Leave rate_mode=unknown",replies[3]["messages"][0]["content"]["text"])
                self.assertTrue(replies[4]["isError"])
                self.assertEqual(before,self.core.store.get("powerplay"))
                env["ELITELAB_AUTH_TOKEN"]="wrong-token"
                denied=subprocess.run([sys.executable,"-m","elitelab","mcp"],cwd=config.ROOT,env=env,input=messages,capture_output=True,text=True,timeout=25,check=True)
                self.assertTrue(json.loads(denied.stdout.splitlines()[1])["result"]["isError"])
                self.assertNotIn("targets-test-token",denied.stdout)
            finally:
                server.shutdown();server.server_close();thread.join(5)

    def test_newer_search_wins_and_catalogue_changes_invalidate(self):
        self.prepare()
        newer=[]
        def fetch(*args,**kwargs):
            if not newer:
                newer.append(None)
                newer[0]=self.core.http.tools["find_sell_targets"].fn({"min":0,"ref":"Sol"})
            return copy.deepcopy(DATA)
        with self.assertRaisesRegex(ValueError,"newer search"):
            self.run_search(fetch=fetch)
        self.assertEqual(self.core.store.get("targets","last"),newer[0])
        self.emit("LoadGame",Commander="Target Tester")
        self.emit("Powerplay",Power="Edmund Mahon")
        self.core.store.set("loop","stations",[{"system":"Zaonce","coords":{"x":0,"y":0,"z":0},"rares":[{"key":"alieneggs"}]}])
        out,_=self.run_search()
        self.assertEqual(out["cargo"][0]["origin_basis"],"rare loop catalogue")
        revision=self.core.store.get("targets","evidence_revision")
        self.emit("CargoTransfer",Transfers=[{"Type":"alieneggs"}])
        self.assertGreater(self.core.store.get("targets","evidence_revision"),revision)
        self.assertIsNone(self.core.store.get("targets","last"))
        self.run_search()
        self.core.store.set("loop","stations",[])
        self.assertIsNone(self.core.store.get("targets","last"))

    def test_unmapped_rare_and_invalid_quantity_cannot_be_dropped_from_load(self):
        self.prepare()
        for extra in ({"key":"future_rare","name":"New rare","count":2,"rare":True},
                      {"key":"alieneggs","count":float("nan")}, {"key":"alieneggs","count":True}):
            self.core.store.set("journal","cargo",{"items":[{"key":"alieneggs","count":10},extra]})
            out,_=self.run_search({"interpolate":True})
            self.assertTrue(all(r["estimated_sale"] is None for r in out["results"]))
            self.assertTrue(all(r["estimated_merits"] is None for r in out["results"]))
