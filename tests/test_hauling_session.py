"""Independent clients complete a job over real HTTP with retries and restarts."""
import socket
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core, config, loader


class HaulingSessionTests(unittest.TestCase):
    def setUp(self):
        offline = patch.object(config, "OFFLINE", True)
        offline.start()
        self.addCleanup(offline.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner = self.client("owner")
        self.crew = self.client("crew")
        self.other = self.client("other")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        state = self.owner.modules["party"].party.host({"bind": "127.0.0.1", "port": port})
        self.invite = {"url": f"http://127.0.0.1:{port}", "code": state["code"]}
        self.owner.http.tools["plan_carrier_trade"].fn({"commodity": "gold", "source": "Buy / Sol", "destination": "Sell / Lave",
            "target": 400, "planned_quantity": 400, "source_price": 100, "destination_price": 300, "crew_enabled": True,
            "carrier_market_id": 123, "source_market_id": 456, "destination_market_id": 789})
        self.op = self.control("start")
        for c in (self.crew, self.other):
            c.modules["party"].party.join(self.invite)

    def client(self, name):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        core = Core()
        core.data_path = lambda *parts: str(folder.joinpath(*parts))
        loader.load_all(core)
        core.store.update("journal", {"cmdr": name, "system": "Sol", "cargo_capacity": 200,
                          "cargo": {"count": 0, "items": []}})
        self.addCleanup(core.modules["party"].party.leave)
        return core

    def control(self, action):
        op = self.owner.store.get("trade", "operation")
        return self.owner.http.tools["manage_carrier_operation"].fn({"action": action, "id": op["id"] if op else None})["operation"]

    def report(self, core, tonnes, key, phase="loading"):
        return core.modules["party"].party.report_work({"id": self.op["id"], "phase": phase, "tonnes": tonnes, "request_id": key * 32})

    def sync(self, core):
        return core.modules["party"].party.report_work({"activity": "hauling"})

    def test_full_session_repeated_requests_ship_change_disconnect_and_restart(self):
        first = self.report(self.crew, 200, "a")
        self.assertEqual(first["desk"]["earnings"], 10000)
        for _ in range(3): self.report(self.crew, 200, "a")
        self.assertEqual(self.owner.store.get("trade", "operation")["loaded"], 200)
        member_id = self.crew.modules["party"].party.member_id
        self.crew.modules["party"].party.leave()
        roster = self.owner.store.get("party", "desk")["crew"]
        self.assertEqual(next(m["loading"] for m in roster if m["id"] == member_id), 200)
        self.crew = self.client("crew")
        self.crew.modules["party"].party.join(self.invite)
        self.assertEqual(self.crew.modules["party"].party.member_id, member_id)
        self.report(self.crew, 200, "a")
        self.assertEqual(self.owner.store.get("trade", "operation")["loaded"], 200)
        self.other.store.set("journal", "cargo_capacity", 100)
        state = self.sync(self.other)
        self.assertLessEqual(state["desk"]["quantity"] or 0, 100)
        self.report(self.other, 200, "b")
        self.control("depart")
        self.assertEqual(self.sync(self.crew)["desk"]["action"], "wait")
        self.control("unload")
        for core, key in ((self.crew, "c"), (self.other, "d")):
            self.sync(core)
            self.report(core, 200, key, "unloading")
        final = self.control("complete")
        self.assertEqual((final["loaded"], final["unloaded"]), (400, 400))
        self.assertEqual(self.sync(self.crew)["desk"]["earnings"], 20000)
        self.assertEqual(self.owner.store.get("trade", "inventory"), {})

    def test_network_loss_keeps_pending_separate_and_retry_acknowledges_once(self):
        api = self.crew.modules["party"].instance
        with patch.object(api, "exchange", side_effect=OSError("offline")):
            state = self.report(self.crew, 50, "r")
            self.assertEqual(state["desk"]["pending"]["loading"], 50)
            self.assertEqual(state["desk"]["progress"]["loading"], 0)
            self.assertEqual(state["desk"]["earnings"], 0)
        state = self.report(self.crew, 50, "r")
        self.assertEqual(state["operation"]["loaded"], 50)
        self.assertEqual(state["desk"]["pending"]["loading"], 0)
        with self.assertRaises(ValueError): self.report(self.crew, 60, "r")

    def test_old_phase_form_rejected_without_writing_to_new_phase(self):
        self.control("depart"); self.control("unload")
        self.sync(self.crew)
        with self.assertRaises(ValueError): self.report(self.crew, 25, "s", "loading")
        self.assertIsNone(self.crew.modules["party"].party.work)

    def test_automatic_delivery_and_duplicate_event_do_not_double_credit(self):
        event = {"event": "MarketSell", "timestamp": datetime.now(timezone.utc).isoformat(), "MarketID": 123, "Type": "gold", "Count": 80}
        for _ in range(3): self.crew.bus.emit("journal.MarketSell", event)
        state = self.sync(self.crew)
        self.assertEqual(state["desk"]["progress"]["loading"], 80)
        self.assertEqual(state["desk"]["earnings"], 4000)
        self.assertEqual(state["operation"]["loaded"], 80)

    def test_owner_solo_panel_tracks_without_opening_a_party_listener(self):
        party = self.owner.modules["party"].party
        party.leave()
        self.owner.store.set("journal", "cargo_capacity", 40)
        self.owner.store.set("journal", "cargo", {"count": 40, "items": [{"key": "gold", "count": 40}]})
        state = self.owner.store.get("party")
        self.assertEqual(state["mode"], "idle")
        self.assertEqual(state["desk"]["action"], "transfer_in")
        self.assertIsNone(party.server)
        self.owner.bus.emit("journal.Docked", {"event": "Docked", "MarketID": 123})
        self.owner.bus.emit("journal.CargoTransfer", {"event": "CargoTransfer", "timestamp": datetime.now(timezone.utc).isoformat(),
            "Transfers": [{"Type": "gold", "Count": 40, "Direction": "tocarrier"}]})
        state = self.owner.store.get("party")
        self.assertEqual(state["desk"]["progress"]["loading"], 40)
        self.assertIsNone(state["desk"]["earnings"])
        self.assertEqual(state["operation"]["loaded"], 40)

    def test_workload_is_shared_and_survives_reconnect_without_reassigning(self):
        configure=self.owner.http.tools["configure_trade_workload"].fn
        q={"mode":"equal","owner_hauls":False}
        draft=configure(q)
        self.assertEqual(draft["loading"]["order_remaining"],400)
        configure({**q,"action":"apply","basis":draft["basis"]})
        state=self.sync(self.crew)
        self.assertEqual(state["desk"]["assignment"]["loading_target"],200)
        self.report(self.crew,50,"w")
        self.crew.store.set("journal","cargo_capacity",100)
        state=self.sync(self.crew)
        self.assertEqual(state["desk"]["assignment"]["loading_runs_left"],2)
        self.assertEqual(state["workload"]["loading"]["order_remaining"],350)
        self.crew.modules["party"].party.leave()
        self.crew=self.client("crew")
        self.crew.modules["party"].party.join(self.invite)
        state=self.sync(self.crew)
        self.assertEqual(state["desk"]["assignment"]["loading_target"],200)
        self.assertEqual(state["desk"]["assignment"]["loading_remaining"],150)
        self.assertEqual(self.owner.read_data("trade.json")["workload"]["owner_hauls"],False)

    def test_stale_workload_preview_and_member_mutation_are_rejected(self):
        configure=self.owner.http.tools["configure_trade_workload"].fn
        before=self.owner.store.get("trade","workload")
        draft=configure({"mode":"equal"})
        self.report(self.crew,50,"v")
        with self.assertRaises(ValueError): configure({"mode":"equal","action":"apply","basis":draft["basis"]})
        self.assertEqual(self.owner.store.get("trade","workload"),before)
        with self.assertRaises(ValueError): self.crew.http.tools["configure_trade_workload"].fn({"action":"preview"})

    def test_owner_direct_transfers_do_not_reduce_crew_order_twice(self):
        configure=self.owner.http.tools["configure_trade_workload"].fn
        q={"mode":"custom","owner_hauls":True,"shares":{
            self.owner.modules["party"].party.member_id:2,self.crew.modules["party"].party.member_id:1,self.other.modules["party"].party.member_id:1}}
        draft=configure(q)
        configure({**q,"action":"apply","basis":draft["basis"]})
        self.assertEqual(self.owner.store.get("party","workload")["loading"]["order_remaining"],200)
        self.report(self.owner,100,"o")
        w=self.owner.store.get("party","workload")
        self.assertEqual((w["loading"]["owner_remaining"],w["loading"]["order_remaining"]),(100,200))
        self.report(self.crew,50,"p")
        self.assertEqual(self.owner.store.get("party","workload")["loading"]["order_remaining"],150)

    def test_cargo_change_invalidates_rebalance_preview(self):
        configure = self.owner.http.tools["configure_trade_workload"].fn
        draft = configure({"mode":"equal"})
        self.crew.store.set("journal","cargo",{"count":50,"items":[{"key":"gold","count":50}]})
        self.sync(self.crew)
        with self.assertRaises(ValueError):
            configure({"mode":"equal","action":"apply","basis":draft["basis"]})
