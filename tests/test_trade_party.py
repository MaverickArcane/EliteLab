"""Inventory accounting, replay safety and real two-client LAN party transport."""
import copy
from datetime import datetime, timezone
import http.client
import json
import os
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from test_elitelab import Core, FIXTURES, config, loader


class TradeTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-trade-test-")
        self.addCleanup(data.cleanup)
        for k, v in (("DATA_DIR", data.name), ("JOURNAL_DIR", os.path.join(FIXTURES, "trade"))):
            p = patch.object(config, k, v)
            p.start()
            self.addCleanup(p.stop)
        self.core = Core()
        loader.load_all(self.core)
        self.core.watcher.replay()
        self.desk = self.core.modules["trade"].trade

    def call(self, tool, **q):
        return self.core.http.tools[tool].fn(q)

    def event(self, event, **values):
        self.core.bus.emit("journal." + event, {"event": event, "timestamp": "2026-10-23T12:00:00Z", **values})

    def test_orders_are_not_inventory_and_transfers_need_baseline(self):
        state = self.call("get_carrier_trade")
        self.assertIsNone(state["inventory"]["tritium"]["stock"])
        self.assertEqual(state["orders"]["tritium"]["quantity"], 980)
        self.assertEqual(state["inventory"]["gold"]["stock"], 440)
        # Sell availability follows stock; direct transfers do not fill buy orders.
        self.assertEqual(state["orders"]["gold"]["quantity"], 440)
        self.assertEqual(state["buy_commitment"], 49000000)

    def test_replay_and_restart_do_not_double_count(self):
        state = self.call("get_carrier_trade")
        self.core.watcher.replay()
        self.assertEqual(self.call("get_carrier_trade"), state)
        second = Core()
        loader.load_all(second)
        second.watcher.replay()
        self.assertEqual(second.store.get("trade"), state)

    def test_manual_count_wins_over_old_replay(self):
        self.call("reconcile_carrier_stock", commodity="gold", stock=200)
        self.core.watcher.replay()
        self.assertEqual(self.call("get_carrier_trade")["inventory"]["gold"]["stock"], 200)

    def test_unrelated_carrier_and_srv_transfer_ignored(self):
        before = self.call("get_carrier_trade")["inventory"]
        self.event("Docked", MarketID=999, StationName="Other", StationType="FleetCarrier")
        self.event("CargoTransfer", Transfers=[{"Type": "gold", "Count": 30, "Direction": "toship"}])
        self.event("Docked", MarketID=3700000001, StationName="TST-001", StationType="FleetCarrier")
        self.event("CargoTransfer", Transfers=[{"Type": "gold", "Count": 30, "Direction": "tosrv"}])
        self.assertEqual(self.call("get_carrier_trade")["inventory"], before)

    def test_cancel_does_not_delete_stock(self):
        self.event("CarrierTradeOrder", CarrierID=3700000001, Commodity="gold", CancelTrade=True)
        state = self.call("get_carrier_trade")
        self.assertEqual(state["inventory"]["gold"]["stock"], 440)
        self.assertEqual(state["orders"]["gold"]["quantity"], 0)

    def test_plan_separates_stock_ship_orders_and_runs(self):
        self.call("reconcile_carrier_stock", commodity="tritium", stock=200)
        self.core.store.update("journal", {"cargo_capacity": 100, "cargo": {"count": 70, "items": [{"key": "tritium", "count": 50}, {"key": "gold", "count": 20}]}})
        c = self.call("plan_carrier_trade", commodity="tritium", target=1500, source_price=40000, carrier_price=50000, destination_price=70000, use_ship_cargo=True)["calculation"]
        self.assertEqual((c["stock"], c["remaining"], c["to_haul"], c["uncovered"], c["runs"], c["next_load"]), (200, 1300, 1250, 270, 13, 30))
        self.assertEqual((c["hauler_margin"], c["carrier_margin"], c["self_margin"]), (10000, 20000, 30000))
        c = self.call("plan_carrier_trade", commodity="tritium", mode="unload", target=50, ship_capacity=64, use_ship_cargo=True)["calculation"]
        self.assertEqual((c["remaining"], c["own_committed"], c["runs"]), (150, 0, 3))

    def test_unknown_stock_zero_capacity_and_completed_target(self):
        c = self.call("plan_carrier_trade", commodity="unknown", target=100)["calculation"]
        self.assertIsNone(c["remaining"])
        self.assertIsNone(c["runs"])
        self.call("reconcile_carrier_stock", commodity="unknown", stock=100)
        c = self.call("plan_carrier_trade", commodity="unknown", target=100, ship_capacity=100)["calculation"]
        self.assertEqual(c["runs"], 0)

    def test_bad_input_and_failed_save_are_atomic(self):
        before = copy.deepcopy(self.desk.data)
        for bad in (-1, float("nan"), float("inf"), True, 1.5, "oops"):
            with self.assertRaises(ValueError):
                self.call("reconcile_carrier_stock", commodity="gold", stock=bad)
        with patch.object(self.core, "write_data", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.call("reconcile_carrier_stock", commodity="gold", stock=1)
        self.assertEqual(before, self.desk.data)

    def test_market_normalization_and_price_direction(self):
        self.core.bus.emit("journal.file.Market", {"timestamp": "2026-10-23T10:00:00Z", "MarketID": 123, "StationName": "Port", "StarSystem": "Sol", "Items": [
            {"Name": "$tritium_name;", "BuyPrice": 4, "SellPrice": 3, "Stock": 100, "Demand": 200}]})
        result = self.call("find_trade_spots", commodity="tritium")
        self.assertEqual(result["buy"][0]["buy"], 4)
        self.assertEqual(result["sell"][0]["sell"], 3)

    def test_community_filters_pad_volume_age_and_carriers(self):
        base = {"marketId": 123, "stationName": "Port", "systemName": "Sol", "maxLandingPadSize": 3, "buyPrice": 10, "sellPrice": 20,
                "stock": 100, "demand": 200, "updatedAt": datetime.now(timezone.utc).isoformat(), "stationType": "Orbis"}
        rows = [base, {**base, "maxLandingPadSize": 2}, {**base, "stock": 0, "demand": 0}, {**base, "updatedAt": "2020-01-01T00:00:00Z"}, {**base, "stationType": "FleetCarrier"}]
        with patch.object(config, "OFFLINE", False), patch.object(self.core.services, "fetch_json", return_value=rows) as fetch:
            result = self.call("find_trade_spots", commodity="tritium", source="community", min_volume=100)
        self.assertEqual((len(result["buy"]), len(result["sell"])), (1, 1))
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result["warnings"], [])

    def test_route_pairs_require_different_markets_and_positive_profit(self):
        a = {"key": "gold", "market_id": 1, "buy": 100, "sell": 90, "stock": 1000, "demand": 500}
        b = {**a, "market_id": 2, "sell": 300, "demand": 200}
        result = self.desk.routes({"buy": [a], "sell": [a, b]})
        self.assertEqual(len(result["routes"]), 1)
        r = result["routes"][0]
        self.assertEqual((r["profit_per_ton"], r["margin_percent"], r["volume"], r["gross_profit"]), (200, 200, 200, 40000))

    def test_personal_bonus_requires_confirmation_and_never_inflates_carrier_margin(self):
        values = dict(commodity="gold", target=1000, source_price=100, carrier_price=200, destination_price=300, bonus_per_ton=50, ship_capacity=100)
        c = self.call("plan_carrier_trade", **values)["calculation"]
        self.assertEqual((c["personal_margin"], c["personal_bonus"], c["carrier_margin"]), (200, 0, 100))
        c = self.call("plan_carrier_trade", **values, bonus_confirmed=True)["calculation"]
        self.assertEqual((c["personal_margin"], c["personal_per_run"], c["carrier_margin"]), (250, 25000, 100))
        c = self.call("plan_carrier_trade", **values, bonus_confirmed=True, price_includes_bonus=True)["calculation"]
        self.assertEqual(c["personal_margin"], 200)
        self.assertEqual(c["carrier_margin"], 50)
        self.core.store.set("powerplay", "rank", 99)
        self.assertEqual(self.core.store.get("trade", "calculation")["personal_bonus"], 0)

    def test_reset_removes_old_orders_and_history_cannot_restore_them(self):
        with patch.object(self.core.modules["trade"].instance, "now", return_value="2026-10-24T00:00:00.500Z"):
            cleared = self.call("reset_carrier_inventory", keep_tritium=True)
        self.assertEqual(list(cleared["inventory"]), ["tritium"])
        self.assertIsNone(cleared["inventory"]["tritium"]["stock"])
        self.assertEqual(cleared["orders"], {})
        self.assertTrue(self.core.read_data("trade-ledger-before-reset.json")["orders"])
        second = Core(); loader.load_all(second); second.watcher.replay()
        self.assertEqual(list(second.store.get("trade", "inventory")), ["tritium"])
        self.assertEqual(second.store.get("trade", "orders"), {})
        # Fractional reset times must reject a same-second earlier journal record.
        second.bus.emit("journal.CarrierTradeOrder", {"event":"CarrierTradeOrder","timestamp":"2026-10-24T00:00:00Z", "CarrierID":3700000001,"Commodity":"silver","SaleOrder":500,"Price":100})
        self.assertNotIn("silver", second.store.get("trade", "inventory"))
        second.bus.emit("journal.CarrierTradeOrder", {"event":"CarrierTradeOrder","timestamp":"2026-10-25T00:00:00Z", "CarrierID":3700000001,"Commodity":"tritium","SaleOrder":50,"Price":100})
        self.assertEqual(second.store.get("trade", "inventory")["tritium"]["stock"], 50)

    def test_ptn_workflow_removed(self):
        self.assertNotIn("get_ptn_trade_ideas", self.core.http.tools)



class PartyTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-party-test-")
        self.addCleanup(data.cleanup)
        p = patch.object(config, "DATA_DIR", data.name)
        p.start()
        self.addCleanup(p.stop)
        self.leader_core, self.member_core = Core(), Core()
        for c in (self.leader_core, self.member_core):
            real_read = c.read_data
            with patch.object(c, "read_data", side_effect=lambda *args, _read=real_read, **kwargs: {} if args == ("party-local.json",) else _read(*args, **kwargs)):
                loader.load_all(c)
            self.addCleanup(c.modules["party"].party.leave)
        self.leader = self.leader_core.modules["party"].party
        self.member = self.member_core.modules["party"].party
        self.api = self.member_core.modules["party"].instance
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.state = self.leader.host({"bind": "127.0.0.1", "port": port})
        self.url = f"http://127.0.0.1:{port}"

    def test_two_clients_report_plan_and_leave_without_uploading_secrets(self):
        self.leader_core.http.tools["plan_carrier_trade"].fn({"commodity": "gold", "target": 100})
        self.member_core.store.update("journal", {"cmdr": "Hauler", "credits": 999999, "system": "Sol", "cargo_capacity": 100,
            "cargo": {"count": 20, "items": [{"key": "gold", "name": "Gold", "count": 20}], "timestamp": "2026-10-26T10:00:00Z"}})
        joined = self.member.join({"url": self.url, "code": self.state["code"]})
        self.assertEqual(joined["plan"]["commodity"], "gold")
        remote = self.leader_core.store.get("party", "members")[1]
        self.assertEqual((remote["cmdr"], remote["cargo_count"]), ("Hauler", 20))
        self.assertNotIn("credits", remote)
        self.assertIsNone(joined["code"])
        self.assertEqual(self.leader_core.store.get("trade", "inventory"), {})
        self.member.leave()
        self.assertEqual(len(self.leader.shared()["members"]), 1)

    def test_live_telemetry_changes_arrive_without_manual_reporting(self):
        fixture = os.path.join(FIXTURES, "telemetry")
        with patch.object(config, "JOURNAL_DIR", fixture):
            self.member_core.watcher.replay()
        self.member.join({"url": self.url, "code": self.state["code"]})
        first = self.leader.shared()["members"][1]
        self.assertEqual(first["ship_name"], "Cargo Runner")
        self.assertEqual(first["telemetry"]["fuel"], 7.5)
        self.assertEqual(first["telemetry"]["fuel_capacity"], 64)
        self.assertEqual(first["telemetry"]["hull_health"], .8)
        self.assertTrue(first["telemetry"]["shields_up"])
        self.assertTrue(first["telemetry"]["supercruise"])
        self.assertTrue(first["telemetry"]["low_fuel"])
        self.assertEqual(first["telemetry"]["destination"], "Galileo")
        self.member_core.bus.emit("journal.file.Status", {"event":"Status", "timestamp":"2026-10-26T18:00:01Z", "Flags":(1<<24)|(1<<20)|(1<<23), "Fuel":{"FuelMain":5.25,"FuelReservoir":.3}})
        self.member_core.bus.emit("journal.FSDJump", {"event":"FSDJump", "timestamp":"2026-10-26T18:00:01Z", "StarSystem":"Lave"})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            report = self.leader.shared()["members"][1]
            if report["telemetry"]["fuel"] == 5.25 and report["system"] == "Lave":
                break
            time.sleep(.05)
        self.assertEqual(report["telemetry"]["fuel"], 5.25)
        self.assertEqual(report["system"], "Lave")
        self.assertFalse(report["telemetry"]["shields_up"])
        self.assertTrue(report["telemetry"]["interdicted"])
        self.assertTrue(report["telemetry"]["overheating"])
        self.assertFalse(report["telemetry"]["low_fuel"])
        self.assertNotIn("credits", report)

    def test_telemetry_keeps_fuel_timestamp_and_resets_for_other_vehicles(self):
        bus = self.member_core.bus
        bus.emit("journal.file.Status", {"Flags":1<<24,"timestamp":"2026-10-26T18:00:00Z","Fuel":{"FuelMain":10}})
        bus.emit("journal.file.Status", {"Flags":(1<<24)|1,"timestamp":"2026-10-26T18:00:05Z"})
        t = self.member.local()["telemetry"]
        self.assertEqual(t["fuel"], 10)
        self.assertEqual(t["fuel_at"], "2026-10-26T18:00:00Z")
        self.assertEqual(t["status_at"], "2026-10-26T18:00:05Z")
        bus.emit("journal.file.Status", {"Flags":0,"Flags2":1,"timestamp":"2026-10-26T18:00:06Z"})
        t = self.member.local()["telemetry"]
        self.assertEqual(t["vehicle"], "foot")
        self.assertIsNone(t["fuel"])
        self.assertIsNone(t["fuel_capacity"])
        bus.emit("journal.Shutdown", {"event":"Shutdown","timestamp":"2026-10-26T18:00:07Z"})
        self.assertFalse(self.member.local()["telemetry"]["game_running"])
        bus.emit("journal.LoadGame", {"event":"LoadGame","timestamp":"2026-10-26T18:01:00Z"})
        self.assertTrue(self.member.local()["telemetry"]["game_running"])
        self.assertIsNone(self.member.local()["telemetry"]["shields_up"])

    def test_other_ship_hull_and_target_health_are_not_ours(self):
        bus = self.member_core.bus
        bus.emit("journal.Loadout", {"event":"Loadout","HullHealth":.9,"timestamp":"2026-10-26T18:00:00Z"})
        for event in ({"event":"HullDamage","Health":.2,"PlayerPilot":True,"Fighter":True},
                      {"event":"HullDamage","Health":.2,"PlayerPilot":False,"Fighter":False},
                      {"event":"ShipTargetted","HullHealth":.2,"ShieldHealth":.1}):
            bus.emit("journal."+event["event"], event)
        self.assertEqual(self.member.local()["telemetry"]["hull_health"], .9)

    def test_telemetry_rejects_invalid_values_and_supports_old_clients(self):
        for field, bad in (("fuel",float("nan")),("fuel",-1),("fuel",True),("fuel",float("inf")),("shields_up",1),("hull_health",2),("vehicle","bad")):
            with self.subTest(field=field,bad=bad), self.assertRaises(ValueError):
                self.api.sanitize({"telemetry":{field:bad}})
        self.assertIsNone(self.api.sanitize({})["telemetry"])
        t = self.api.sanitize({"telemetry":{"fuel":0,"shields_up":False,"credits":123}})["telemetry"]
        self.assertEqual(t["fuel"], 0)
        self.assertFalse(t["shields_up"])
        self.assertNotIn("credits", t)

    def test_leader_status_updates_publish_immediately_and_disconnect_stays_stale(self):
        self.leader_core.bus.emit("journal.file.Status", {"Flags":(1<<24)|8,"timestamp":"2026-10-26T18:00:00Z","Fuel":{"FuelMain":12}})
        self.assertEqual(self.leader_core.store.get("party","members")[0]["telemetry"]["fuel"], 12)
        self.leader.receive({"id":self.member.member_id,"report":self.member.local()})
        with self.leader.lock:
            self.leader.members[self.member.member_id]["received"] -= 31
        self.assertTrue(self.leader.shared()["members"][1]["stale"])

    def test_shared_operation_deliveries_status_and_reconnect(self):
        tools = self.leader_core.http.tools
        tools["plan_carrier_trade"].fn({"commodity":"gold", "source":"Buy / Sol", "destination":"Sell / Lave",
            "source_price":100, "destination_price":200, "target":1000, "planned_quantity":1000, "crew_enabled":True})
        op = tools["manage_carrier_operation"].fn({"action":"start"})["operation"]
        joined = self.member.join({"url":self.url,"code":self.state["code"]})
        self.assertEqual(joined["operation"]["id"], op["id"])
        report = self.member.report_work({"id":op["id"], "tonnes":100, "activity":"hauling"})
        self.assertEqual(report["operation"]["loaded"],100)
        self.assertEqual(report["members"][1]["activity"],"hauling")
        for _ in range(3): self.leader.receive({"id":self.member.member_id,"report":self.member.local()})
        self.assertEqual(self.leader.shared()["operation"]["loaded"],100)
        self.member.leave()
        self.member.join({"url":self.url,"code":self.state["code"]})
        self.assertEqual(self.leader.shared()["operation"]["loaded"],100)
        self.assertEqual(self.leader_core.store.get("trade","inventory"),{})
        saved = self.member_core.read_data("party-local.json")
        self.assertEqual((saved["id"],saved["work"]["loading"]),(self.member.member_id,100))
        with self.assertRaises(ValueError): self.member.report_work({"id":"old", "tonnes":1})
        with self.assertRaises(ValueError): self.member_core.http.tools["manage_carrier_operation"].fn({"action":"cancel","id":op["id"]})

    def test_delivery_saved_during_network_failure_retries_without_double_count(self):
        tools = self.leader_core.http.tools
        tools["plan_carrier_trade"].fn({"commodity":"gold", "source":"Buy / Sol", "destination":"Sell / Lave", "target":1000,"planned_quantity":1000})
        op = tools["manage_carrier_operation"].fn({"action":"start"})["operation"]
        self.member.join({"url":self.url,"code":self.state["code"]})
        with patch.object(self.api, "exchange", side_effect=OSError("offline")):
            pending = self.member.report_work({"id":op["id"],"tonnes":100})
        self.assertIn("saved locally", pending["error"])
        self.assertEqual(pending["work"]["loading"],100)
        # Another report (or heartbeat) sends the cumulative count again, not another 100 t.
        self.member.report_work({"activity":"hauling"})
        self.member.report_work({"activity":"ready"})
        self.assertEqual(self.leader.shared()["operation"]["loaded"],100)

    def prepare_auto_operation(self):
        tools = self.leader_core.http.tools
        tools["plan_carrier_trade"].fn({"commodity":"gold", "source":"Buy / Sol", "destination":"Sell / Lave", "target":1000,"planned_quantity":1000,
            "carrier_market_id":123,"source_market_id":789,"destination_market_id":456})
        op = tools["manage_carrier_operation"].fn({"action":"start"})["operation"]
        self.member.join({"url":self.url,"code":self.state["code"]})
        return op

    def test_journal_sales_sync_automatically_and_deduplicate_after_restart(self):
        op = self.prepare_auto_operation()
        event = {"event":"MarketSell","timestamp":datetime.now(timezone.utc).isoformat(),"MarketID":123,"Type":"gold","Count":25,"SellPrice":100}
        for wrong in ({"MarketID":999}, {"Type":"silver"}, {"_replay":True}, {"event":"MarketBuy"}):
            self.member.journal_delivery('journal.'+event['event'], {**event,**wrong})
        self.assertIsNone(self.member.work)
        self.member_core.bus.emit("journal.MarketSell", event)
        self.member_core.bus.emit("journal.MarketSell", event)
        self.assertEqual(self.member.work["loading"],25)
        deadline = time.monotonic()+5
        while time.monotonic()<deadline and self.leader.shared()["operation"]["loaded"]!=25:
            time.sleep(.05)
        self.assertEqual(self.leader.shared()["operation"]["loaded"],25)
        self.member.leave()
        restarted=Core();loader.load_all(restarted)
        party=restarted.modules["party"].party
        self.addCleanup(party.leave)
        self.assertEqual(party.member_id,self.member.member_id)
        party.join({"url":self.url,"code":self.state["code"]})
        party.journal_delivery("journal.MarketSell", event)
        self.assertEqual(party.work["loading"],25)
        self.assertEqual(self.leader.shared()["operation"]["loaded"],25)

    def test_unloading_only_counts_sales_at_the_destination_and_owner_transfers_load(self):
        op = self.prepare_auto_operation()
        timestamp=datetime.now(timezone.utc).isoformat()
        self.leader.journal_delivery("journal.Docked", {"event":"Docked","MarketID":123})
        self.leader.journal_delivery("journal.CargoTransfer", {"event":"CargoTransfer","timestamp":timestamp,"Transfers":[{"Type":"gold","Count":30,"Direction":"tocarrier"},{"Type":"gold","Count":20,"Direction":"toship"}]})
        self.assertEqual(self.leader.shared()["operation"]["loaded"],30)
        # Transfers require the selected carrier, and replay must not duplicate them.
        self.leader.journal_delivery("journal.CargoTransfer", {"event":"CargoTransfer", "_replay":True,"timestamp":timestamp,"Transfers":[{"Type":"gold","Count":30,"Direction":"tocarrier"}]})
        self.leader.journal_delivery("journal.Docked", {"event":"Docked","MarketID":999})
        self.leader.journal_delivery("journal.CargoTransfer", {"event":"CargoTransfer", "timestamp":timestamp,"Transfers":[{"Type":"gold","Count":30,"Direction":"tocarrier"}]})
        self.assertEqual(self.leader.shared()["operation"]["loaded"],30)
        for action in ("depart","unload"):
            self.leader_core.http.tools["manage_carrier_operation"].fn({"action":action,"id":op["id"]})
        self.member.report_work({"activity":"hauling"})
        event={"event":"MarketSell","timestamp":datetime.now(timezone.utc).isoformat(),"Type":"gold","Count":20}
        self.leader.journal_delivery("journal.Docked", {"event":"Docked","MarketID":123})
        self.leader.journal_delivery("journal.CargoTransfer", {"event":"CargoTransfer","timestamp":timestamp,"Transfers":[{"Type":"gold","Count":20,"Direction":"toship"}]})
        self.assertEqual(self.leader.shared()["operation"]["unloaded"],0)
        self.leader.journal_delivery("journal.MarketSell", {**event,"MarketID":456})
        self.assertEqual(self.leader.shared()["operation"]["unloaded"],20)
        self.member.journal_delivery("journal.MarketSell", {**event,"MarketID":123})
        self.assertIsNone(self.member.work)
        self.member.journal_delivery("journal.MarketSell", {**event,"MarketID":456})
        self.assertEqual(self.member.work["unloading"],20)
        self.member.report_work({"activity":"ready"})
        self.assertEqual(self.leader.shared()["operation"]["unloaded"],40)
        self.assertEqual(self.leader_core.store.get("trade","inventory"),{})

    def test_listener_rejects_wrong_code_browser_origin_and_management_routes(self):
        for path, code, origin, expected in (("/report", "wrong", None, 403), ("/report", self.state["code"], "http://evil.test", 403), ("/api/party/host", self.state["code"], None, 404)):
            connection = http.client.HTTPConnection("127.0.0.1", self.state["port"], timeout=2)
            headers = {"Authorization": "Bearer " + code, "Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            connection.request("POST", path, "{}", headers)
            response = connection.getresponse()
            self.assertEqual(response.status, expected)
            response.read()
            connection.close()

    def test_invalid_reports_and_public_addresses_rejected(self):
        for report in ({"capacity": -1}, {"cargo": [{"count": "bad"}]}, {"cmdr": ["bad"]}):
            with self.assertRaises(ValueError):
                self.api.sanitize(report)
        self.assertTrue(self.api.private_address("100.100.1.2"))
        self.assertFalse(self.api.private_address("8.8.8.8"))
        with self.assertRaises(ValueError):
            self.api.exchange("http://8.8.8.8:8767", "test", {})
        with self.assertRaises(ValueError):
            self.member.join({"url": self.url, "code": "x" * 32})
        self.assertEqual(self.member.mode, "idle")

    def test_stale_reports_expire_and_host_recreation_rotates_code(self):
        self.leader.receive({"id": "a" * 32, "report": {"cmdr": "Old"}})
        self.leader.members["a" * 32]["received"] = time.time() - 40
        self.assertTrue(self.leader.shared()["members"][1]["stale"])
        self.leader.members["a" * 32]["received"] = time.time() - 301
        self.assertEqual(len(self.leader.shared()["members"]), 1)
        old = self.state["code"]
        self.leader.leave()
        new = self.leader.host({"bind": "127.0.0.1", "port": self.state["port"]})
        self.assertNotEqual(new["code"], old)

    def test_heartbeat_sends_new_cargo_and_disconnect_preserves_stale_evidence(self):
        self.member.join({"url": self.url, "code": self.state["code"]})
        self.member_core.store.update("journal", {"cargo": {"count": 77, "items": [{"key": "gold", "count": 77}]}})
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if self.leader.shared()["members"][1]["cargo_count"] == 77:
                break
            time.sleep(.05)
        self.assertEqual(self.leader.shared()["members"][1]["cargo_count"], 77)
        self.member.last_success = time.time() - 31
        self.member.publish()
        state = self.member_core.store.get("party")
        self.assertTrue(state["stale"])
        self.assertTrue(all(m["stale"] for m in state["members"]))


if __name__ == "__main__":
    unittest.main()
