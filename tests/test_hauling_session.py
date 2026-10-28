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
            "target": 400, "planned_quantity": 400, "source_price": 100, "destination_price": 300, "crew_enabled": True, "carrier_mean_price":100,
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

    def test_close_party_notifies_connected_members_and_releases_port(self):
        self.report(self.crew, 50, "p")
        leader = self.owner.modules["party"].party
        leader.leave()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and any(c.modules["party"].party.mode != "idle" for c in (self.crew, self.other)):
            time.sleep(.02)
        for client in (self.crew, self.other):
            state = client.store.get("party")
            self.assertEqual(state["mode"], "idle")
            self.assertIsNone(state["operation"])
            self.assertIsNone(state["plan"])
            self.assertIn("closed the party", state["error"])
        self.assertEqual(self.crew.store.get("party", "work")["loading"], 50)
        self.assertIsNone(leader.server)
        new = leader.host({"bind":"127.0.0.1", "port":int(self.invite["url"].rsplit(":",1)[1])})
        self.assertNotEqual(new["code"], self.invite["code"])
        self.crew.modules["party"].party.join({"url":self.invite["url"], "code":new["code"]})
        self.assertEqual(self.crew.store.get("party", "mode"), "member")

    def test_member_that_misses_closure_detaches_when_room_is_recreated(self):
        leader = self.owner.modules["party"].party
        member = self.crew.modules["party"].party
        member.stop.set()
        self.other.modules["party"].party.leave()
        with patch.object(self.owner.modules["party"].instance, "CLOSE_GRACE_SECONDS", .01):
            leader.leave()
        leader.host({"bind":"127.0.0.1", "port":int(self.invite["url"].rsplit(":",1)[1])})
        member.synchronize(member.generation, "temporary failure")
        self.assertEqual(member.mode, "idle")
        self.assertIn("no longer valid", self.crew.store.get("party", "error"))
        self.assertEqual(len(leader.members), 0)

    def test_temporary_network_loss_does_not_end_membership(self):
        party = self.crew.modules["party"].party
        with patch.object(self.crew.modules["party"].instance, "exchange", side_effect=OSError("offline")):
            party.synchronize(party.generation, "temporary failure")
        self.assertEqual(party.mode, "member")
        self.assertEqual(self.crew.store.get("party", "operation")["id"], self.op["id"])
        self.sync(self.crew)
        self.assertIsNone(self.crew.store.get("party", "error"))

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

    def test_new_join_gets_remaining_share_and_reconnect_does_not_rebalance(self):
        self.report(self.crew,50,"j")
        self.owner.store.set("journal","cargo",{"count":120,"items":[{"key":"gold","count":120}]})
        newcomer = self.client("late")
        party = newcomer.modules["party"].party
        state = party.join(self.invite)
        assignment = state["desk"]["assignment"]
        self.assertGreater(assignment["loading_remaining"],0)
        self.assertEqual(assignment["loading_runs_left"],1)
        workload = self.owner.store.get("party","workload")
        owner = next(r for r in workload["members"] if r["owner"])
        self.assertEqual(owner["loading_remaining"],120)
        self.assertEqual(workload["loading"]["order_remaining"],230)
        self.assertEqual(self.owner.store.get("trade","operation")["loaded"],50)
        saved = self.owner.read_data("trade.json")["workload"]
        for _ in range(3):self.sync(newcomer)
        party.leave()
        newcomer = self.client("late")
        newcomer.modules["party"].party.join(self.invite)
        self.assertEqual(self.owner.read_data("trade.json")["workload"],saved)
        joins = [e for e in self.owner.store.get("trade","operation")["history"] if e.get("action")=="join" and e.get("member_id")==party.member_id]
        self.assertEqual(len(joins),1)

    def test_new_join_during_unloading_only_adds_unloading_work(self):
        self.report(self.crew,400,"k")
        self.control("depart");self.control("unload")
        self.sync(self.crew)
        self.report(self.crew,80,"u",phase="unloading")
        before = self.owner.store.get("trade","workload")
        newcomer = self.client("late")
        state = newcomer.modules["party"].party.join(self.invite)
        self.assertEqual(state["desk"]["assignment"]["loading_target"],0)
        self.assertEqual(state["desk"]["assignment"]["unloading_remaining"],80)
        after = self.owner.store.get("trade","workload")
        self.assertEqual([r["loading_target"] for r in after["members"][:-1]], [r["loading_target"] for r in before["members"]])
        self.assertEqual(state["operation"]["unloaded"],80)

    def test_custom_split_keeps_owner_weights_when_new_crew_join(self):
        configure = self.owner.http.tools["configure_trade_workload"].fn
        q = {"mode":"custom","owner_hauls":False,"shares":{self.crew.modules["party"].party.member_id:1}}
        draft = configure(q)
        configure({**q,"action":"apply","basis":draft["basis"]})
        before = self.owner.read_data("trade.json")["workload"]
        newcomer = self.client("late")
        state = newcomer.modules["party"].party.join(self.invite)
        self.assertIsNone(state["desk"]["assignment"])
        self.assertEqual(self.owner.read_data("trade.json")["workload"],before)

    def test_absent_crew_resume_reserved_share_after_someone_else_joins(self):
        party = self.crew.modules["party"].party
        before = self.sync(self.crew)["desk"]["assignment"]
        party.leave()
        self.client("late").modules["party"].party.join(self.invite)
        state = party.join(self.invite)
        self.assertEqual(state["desk"]["assignment"]["loading_target"],before["loading_target"])
        self.assertEqual(state["desk"]["assignment"]["weight"],before["weight"])
        self.assertEqual(state["desk"]["action"],"buy")
        self.assertGreater(state["desk"]["quantity"],0)

    def test_away_newcomer_gets_share_when_ready(self):
        newcomer = self.client("late")
        party = newcomer.modules["party"].party
        party.activity = "away"
        state = party.join(self.invite)
        self.assertIsNone(state["desk"]["assignment"])
        # Another arrival must not accidentally enroll the away member at zero.
        self.client("later").modules["party"].party.join(self.invite)
        state = self.sync(newcomer)
        self.assertGreater(state["desk"]["assignment"]["loading_remaining"],0)

    def test_join_after_cancellation_does_not_change_workload(self):
        self.control("cancel")
        before = self.owner.read_data("trade.json")["workload"]
        self.client("late").modules["party"].party.join(self.invite)
        self.assertEqual(self.owner.read_data("trade.json")["workload"],before)

    def test_failed_automatic_split_keeps_saved_work_and_retries(self):
        before = self.owner.read_data("trade.json")["workload"]
        newcomer = self.client("late")
        with patch.object(self.owner,"write_data",side_effect=OSError("disk unavailable")):
            state = newcomer.modules["party"].party.join(self.invite)
            self.assertIsNone(state["desk"]["assignment"])
            self.assertEqual(self.owner.store.get("trade","workload"),before)
            self.assertIn("disk unavailable",self.owner.store.get("trade","workload_join_error"))
        state = self.sync(newcomer)
        self.assertGreater(state["desk"]["assignment"]["loading_remaining"],0)
        self.assertIsNone(self.owner.store.get("trade","workload_join_error"))

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

    def test_leaving_flushes_a_delivery_saved_during_network_loss(self):
        party = self.crew.modules["party"].party
        api = self.crew.modules["party"].instance
        with patch.object(api,"exchange",side_effect=OSError("offline")):
            self.report(self.crew,50,"l")
        party.leave()
        self.assertEqual(self.owner.store.get("trade","operation")["loaded"],50)
        self.assertEqual(party.mode,"idle")
        roster = self.owner.store.get("party","desk")["crew"]
        member = next(m for m in roster if m["id"]==party.member_id)
        self.assertFalse(member["connected"])
        self.assertEqual(member["loading"],50)
        exported = self.crew.http.tools["export_hauling_diagnostics"].fn({})
        self.assertEqual(exported["client"]["saved_work"]["operation_id"],self.op["id"])
        self.assertEqual(exported["client"]["saved_work"]["reported"]["loading"],50)
        self.assertIsNone(exported["client"]["pending"])

    def test_owner_restart_recovers_work_saved_before_ledger_write_failed(self):
        write = self.owner.write_data

        def fail_ledger(value, *parts):
            if parts == ("trade.json",):
                raise OSError("simulated interrupted ledger write")
            return write(value,*parts)

        with patch.object(self.owner,"write_data",side_effect=fail_ledger):
            state = self.report(self.owner,50,"f")
        self.assertEqual(state["desk"]["pending"]["loading"],50)
        self.owner.modules["party"].party.leave()
        self.owner = self.client("owner")
        self.assertEqual(self.owner.store.get("trade","operation")["loaded"],50)
        self.assertEqual(self.owner.store.get("party","desk")["pending"]["loading"],0)
        self.owner = self.client("owner")
        self.assertEqual(self.owner.store.get("trade","operation")["loaded"],50)

    def test_pending_loading_report_survives_owner_stage_change_and_reconnect(self):
        api = self.crew.modules["party"].instance
        with patch.object(api,"exchange",side_effect=OSError("offline")):
            self.report(self.crew,75,"t")
        self.control("depart")
        self.control("unload")
        state = self.sync(self.crew)
        self.assertEqual((state["operation"]["loaded"],state["operation"]["unloaded"]),(75,0))
        self.assertEqual(state["desk"]["pending"]["loading"],0)
        self.sync(self.crew)
        self.assertEqual(self.owner.store.get("trade","operation")["loaded"],75)

    def test_full_ship_rejoins_with_same_assignment_and_no_duplicate_pickup(self):
        configure = self.owner.http.tools["configure_trade_workload"].fn
        q = {"mode":"equal","owner_hauls":False}
        draft = configure(q)
        configure({**q,"action":"apply","basis":draft["basis"]})
        cargo = {"count":200,"items":[{"key":"gold","count":200}]}
        self.crew.store.set("journal","cargo",cargo)
        before = self.sync(self.crew)
        self.assertEqual((before["desk"]["action"],before["desk"]["quantity"]),("deliver",200))
        self.crew.modules["party"].party.leave()
        self.crew = self.client("crew")
        self.crew.store.set("journal","cargo",cargo)
        self.crew.modules["party"].party.join(self.invite)
        after = self.sync(self.crew)
        self.assertEqual(after["desk"]["assignment"]["loading_target"],200)
        self.assertEqual((after["desk"]["action"],after["desk"]["quantity"]),("deliver",200))

    def test_owner_correction_does_not_create_pending_work_or_block_later_deliveries(self):
        self.report(self.crew,350,"a")
        mid = self.crew.modules["party"].party.member_id
        self.owner.http.tools["correct_hauling_delivery"].fn({"id":self.op["id"],"member":mid,"phase":"loading",
            "tonnes":100,"expected":350,"expected_reported":350,"reason":"Duplicate manual report","request_id":"correction-a"*3})
        state = self.sync(self.crew)
        self.assertEqual(state["desk"]["progress"]["loading"],100)
        self.assertEqual(state["desk"]["pending"]["loading"],0)
        self.assertEqual(state["desk"]["adjustments"]["loading"],-250)
        state = self.report(self.crew,200,"b")
        self.assertEqual(state["operation"]["loaded"],300)
        self.assertEqual(state["work"]["loading"],550)
        count = state["operation"]["history_count"]
        self.crew.modules["party"].party.leave()
        self.crew = self.client("crew")
        self.crew.modules["party"].party.join(self.invite)
        state = self.sync(self.crew)
        self.assertEqual(state["desk"]["progress"]["loading"],300)
        self.assertEqual(state["desk"]["pending"]["loading"],0)
        self.assertEqual(state["operation"]["history_count"],count)
        exported = self.crew.http.tools["export_hauling_diagnostics"].fn({})
        self.assertEqual(exported["history_scope"],"latest shared entries")
        self.assertEqual(exported["client"]["local_totals"]["loading"],550)
        self.assertEqual(exported["client"]["pending"]["loading"],0)
        owner_export = self.owner.http.tools["export_hauling_diagnostics"].fn({})
        self.assertEqual(exported["reports"][0]["member"],owner_export["reports"][0]["member"])

    def test_journal_delivery_is_kept_before_client_receives_owner_correction(self):
        self.report(self.crew,350,"a")
        mid = self.crew.modules["party"].party.member_id
        api = self.crew.modules["party"].instance
        with patch.object(api,"exchange",side_effect=OSError("offline")):
            self.owner.http.tools["correct_hauling_delivery"].fn({"id":self.op["id"],"member":mid,"phase":"loading",
                "tonnes":100,"expected":350,"expected_reported":350,"reason":"Duplicate entry","request_id":"late-correction"*2})
            self.crew.bus.emit("journal.MarketSell",{"event":"MarketSell","timestamp":datetime.now(timezone.utc).isoformat(),
                "MarketID":123,"Type":"gold","Count":100})
        self.assertEqual(self.crew.modules["party"].party.work["loading"],450)
        state = self.sync(self.crew)
        self.assertEqual(state["desk"]["progress"]["loading"],200)
        self.assertEqual(state["desk"]["pending"]["loading"],0)

    def test_owner_can_reconcile_a_report_above_the_target_in_one_correction(self):
        self.report(self.crew,350,"a")
        mid = self.crew.modules["party"].party.member_id
        self.crew.bus.emit("journal.MarketSell",{"event":"MarketSell","timestamp":datetime.now(timezone.utc).isoformat(),
            "MarketID":123,"Type":"gold","Count":100})
        state = self.sync(self.crew)
        self.assertEqual(state["desk"]["pending"]["loading"],100)
        corrected = self.owner.http.tools["correct_hauling_delivery"].fn({"id":self.op["id"],"member":mid,"phase":"loading",
            "tonnes":400,"expected":350,"expected_reported":450,"reason":"50 t belonged to another job","request_id":"over-target-correction"})
        self.assertEqual(corrected["loaded"],400)
        state = self.sync(self.crew)
        self.assertEqual(state["desk"]["pending"]["loading"],0)
        self.assertEqual(state["operation"]["loaded"],400)
