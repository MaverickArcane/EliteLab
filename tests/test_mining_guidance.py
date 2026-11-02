"""Regression: cross-system credit sale with no merits and a partially tracked haul."""
import copy
import json
import unittest
from unittest.mock import patch

import test_mining_desk as desk


class MiningGuidanceTests(unittest.TestCase):
    setUp = desk.MiningDeskTests.setUp
    emit = desk.MiningDeskTests.emit
    state = desk.MiningDeskTests.state
    call = desk.MiningDeskTests.call

    def search(self, args=None, data=None, source=None):
        data = copy.deepcopy(data or desk.DATA["stations"])
        def fetch(url, *a, **kw):
            return {"min_max":{"Platinum":{}}} if "field_values" in url else data
        with patch.object(self.core.config,"OFFLINE",False), patch("modules.mining.discovery.time.time",return_value=desk.NOW), \
                patch.object(self.core.services,"fetch_json",side_effect=fetch), \
                patch.object(self.core.services,"spansh_system",return_value=source or {}) as source_call:
            out=self.call("find_mining_buyers",commodity="Platinum",power="Edmund Mahon",**(args or {}))
        return out, source_call

    def test_full_sale_receipt_survives_partial_current_session_attribution(self):
        self.emit("LoadGame",Commander="Fixture Miner")
        for _ in range(114): self.emit("MiningRefined",Type="Platinum")
        self.emit("LoadGame",Commander="Fixture Miner")
        self.emit("Cargo",Inventory=[{"Name":"Platinum","Count":114}])
        for _ in range(54): self.emit("MiningRefined",Type="Platinum")
        self.emit("MarketSell",Type="Platinum",Count=168,TotalSale=44328984)
        self.emit("RepairAll",Cost=1000)
        p=self.state()["profit"]
        self.assertEqual(p["market_sale_proceeds"],44328984)
        self.assertEqual(p["market_sold_tons"],168)
        self.assertEqual(p["sale_proceeds"],14248602)
        self.assertEqual(p["net_profit"],14247602)
        sale=p["transactions"][1]
        self.assertEqual((sale["credits"],sale["tons"],sale["tracked_tons"]),(44328984,168,54))
        self.assertEqual(self.state()["powerplay"]["session_merits"],0)

    def test_untracked_receipts_and_invalid_amounts_do_not_invent_profit(self):
        self.emit("MarketSell",Type="Gold",Count=3,SellPrice=100)
        self.emit("MarketSell",Type="Gold",Count=2,TotalSale=float("nan"))
        self.emit("MarketSell",Type="Gold",Count=True,TotalSale=999)
        p=self.state()["profit"]
        self.assertEqual(p["market_sale_proceeds"],300)
        self.assertEqual(p["sale_proceeds"],0)
        self.assertEqual(p["unknown_market_sale_tons"],2)
        json.dumps(p,allow_nan=False)
        self.emit("LoadGame",Commander="Other")
        self.assertEqual(self.state()["profit"]["market_sale_proceeds"],0)

    def test_power_presence_cannot_replace_controlling_ownership(self):
        data=copy.deepcopy(desk.DATA["stations"])
        row=data["results"][0]
        row.update(system_power=["Edmund Mahon","Felicia Winters"],system_controlling_power="Felicia Winters")
        credit,_=self.search(data=data)
        self.assertIn(row["name"],[r["station"] for r in credit["results"]])
        self.assertEqual(credit["purpose"],"credit_quotes")
        self.assertTrue(all(r["merit_route"]["status"]=="not_checked" for r in credit["results"]))
        out,_=self.search({"powerplay_mode":"reinforcement"},data)
        self.assertNotIn(row["name"],[r["station"] for r in out["results"]])
        row["system_controlling_power"]=None
        self.assertNotIn(row["name"],[r["station"] for r in self.search({"powerplay_mode":"reinforcement"},data)[0]["results"]])

    def test_reinforcement_uses_mining_origin_not_current_travel_origin(self):
        out,fetch=self.search({"powerplay_mode":"reinforcement","ref":"Sol","mined_in":"Delkar"})
        self.assertEqual(len(out["results"]),1)
        self.assertEqual(out["results"][0]["merit_route"]["status"],"candidate")
        fetch.assert_not_called()
        out,_=self.search({"powerplay_mode":"reinforcement","ref":"Delkar","mined_in":"Other source"})
        self.assertEqual(out["results"],[])
        self.assertEqual(out["excluded_routes"],1)
        out,_=self.search({"powerplay_mode":"reinforcement"})
        self.assertEqual(out["results"][0]["merit_route"]["status"],"unknown")

    def test_acquisition_source_owner_state_and_distance(self):
        data=copy.deepcopy(desk.DATA["stations"])
        target=data["results"][1]
        target.update(system_x=20,system_y=0,system_z=0)
        source={"name":"Source","controlling_power":"Edmund Mahon","power_state":"Fortified","x":0,"y":0,"z":0}
        q={"powerplay_mode":"acquisition","mined_in":"Source"}
        self.assertEqual(self.search(q,data,source)[0]["results"][0]["merit_route"]["status"],"candidate")
        for change in ({"controlling_power":"Jerome Archer"},{"power_state":"Exploited"},{"x":-0.01}):
            self.assertEqual(self.search(q,data,{**source,**change})[0]["results"],[])
        for change in ({"controlling_power":None},{"x":float("nan")},{"name":"Wrong source"}):
            self.assertEqual(self.search(q,data,{**source,**change})[0]["results"][0]["merit_route"]["status"],"unknown")
        target["system_x"]=30
        self.assertEqual(self.search(q,data,{**source,"power_state":"Stronghold"})[0]["results"][0]["merit_route"]["status"],"candidate")

    def test_bad_source_is_rejected_before_network(self):
        for origin in ({},True,"x"*161):
            with patch.object(self.core.services,"fetch_json") as fetch,self.assertRaises(ValueError):
                self.call("find_mining_buyers",commodity="Platinum",mined_in=origin)
            fetch.assert_not_called()

    def test_spot_power_presence_is_not_source_ownership(self):
        data=copy.deepcopy(desk.DATA["bodies"])
        for row in data["results"]: row["system_controlling_power"]="Jerome Archer"
        with patch.object(self.core.config,"OFFLINE",False),patch.object(self.core.services,"fetch_json",return_value=data):
            out=self.call("find_mining_spots",power="Edmund Mahon")
        self.assertEqual(out["results"],[])
