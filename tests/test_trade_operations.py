"""Operation lifecycle and crew evidence are separate from carrier inventory."""
import copy
from datetime import datetime, timedelta, timezone
import unittest
import test_trade_party as trade_tests
from test_elitelab import Core, loader


class OperationTests(unittest.TestCase):
    call = trade_tests.TradeTests.call

    def setUp(self):
        trade_tests.TradeTests.setUp(self)
        self.call("plan_carrier_trade", commodity="gold", source="Buy Port / Sol", destination="Sell Port / Lave",
                  source_price=100, destination_price=200, target=1440, planned_quantity=1000, crew_enabled=True, carrier_mean_price=100)

    def control(self, action, **q):
        op = self.core.store.get("trade", "operation")
        return self.call("manage_carrier_operation", action=action, id=op["id"] if op else None, **q)

    def report(self, op, loading=0, unloading=0):
        self.core.bus.emit("party.work", {"id": "a"*32, "report": {"cmdr": "Hauler", "work": {"operation_id": op["id"], "loading": loading, "unloading": unloading}}})

    def test_start_requires_carrier_percentage_reference(self):
        self.desk.data['plan']['carrier_mean_price']=0
        with self.assertRaisesRegex(ValueError, '100% price reference'):
            self.call('manage_carrier_operation', action='start')

    def test_start_rejects_stale_online_percentage_reference(self):
        self.desk.data['plan'].update(carrier_mean_source='Ardent / EDDN',carrier_mean_at='2020-01-01T00:00:00Z')
        with self.assertRaisesRegex(ValueError, 'reference is stale'):
            self.control('start')

    def test_start_accepts_online_reference_seconds_ahead_of_the_clock(self):
        ahead = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
        self.desk.data['plan'].update(carrier_mean_source='Ardent / EDDN', carrier_mean_at=ahead)
        self.assertEqual(self.control('start')['operation']['stage'], 'loading')
        self.control('cancel')
        far_ahead = (datetime.now(timezone.utc) + timedelta(seconds=600)).isoformat()
        self.desk.data['plan'].update(carrier_mean_source='Ardent / EDDN', carrier_mean_at=far_ahead)
        with self.assertRaisesRegex(ValueError, 'reference is stale'):
            self.control('start')

    def test_owner_stages_preserve_baseline_and_order_prices(self):
        state = self.control("start")
        self.assertEqual(state["operation"]["stage"], "loading")
        self.assertEqual(state["plan"]["carrier_price"], 125)
        self.control("pause")
        with self.assertRaises(ValueError): self.control("depart")
        self.control("resume")
        self.control("depart")
        state = self.control("unload")
        self.assertEqual((state["plan"]["mode"], state["plan"]["target"], state["plan"]["carrier_price"]), ("unload", 440, 175))
        state = self.control("complete")
        self.assertEqual(state["operation"]["stage"], "complete")
        self.assertEqual(state["operation"]["loaded"], 0)  # Owner stage confirmation never invents crew reports.

    def test_reports_are_idempotent_and_never_change_physical_stock(self):
        before = copy.deepcopy(self.desk.data["inventory"])
        op = self.control("start")["operation"]
        for _ in range(3): self.report(op, 200, 100)
        state = self.core.store.get("trade")
        self.assertEqual((state["operation"]["loaded"], state["operation"]["unloaded"]), (200, 0))
        self.assertEqual(state["inventory"], before)
        self.report(op, 100)
        self.assertEqual(self.core.store.get("trade", "operation")["loaded"], 200)
        self.report(op, 1001)
        self.assertEqual(self.core.store.get("trade", "operation")["loaded"], 200)
        self.control("depart"); self.control("unload")
        self.report(op, 200, 100)
        self.assertEqual(self.core.store.get("trade", "operation")["unloaded"], 100)

    def test_automatic_size_counts_cargo_as_delivery_not_carrier_stock(self):
        self.call("reconcile_carrier_stock", commodity="gold", stock=0)
        self.core.store.set("journal", "cargo", {"count":200,"items":[{"key":"gold","count":200}]})
        self.call("plan_carrier_trade", commodity="gold", source="Buy / Sol", destination="Sell / Lave",
                  target=1000, planned_quantity=0, source_price=100, destination_price=300, use_ship_cargo=True)
        preview = self.call("configure_trade_workload", mode="equal")
        self.assertEqual(preview["quantity"],1000)
        self.call("configure_trade_workload", action="apply", mode="equal", basis=preview["basis"])
        state = self.control("start")
        self.assertEqual((state["operation"]["quantity"],state["operation"]["baseline_stock"]),(1000,0))
        self.assertEqual(state["workload"]["quantity"],1000)
        self.assertEqual(state["calculation"]["to_haul"],800)

    def test_active_plan_is_frozen_and_old_operation_ids_rejected(self):
        self.control("start")
        with self.assertRaises(ValueError): self.call("plan_carrier_trade", commodity="silver", target=500)
        with self.assertRaises(ValueError): self.call("manage_carrier_operation", action="depart", id="old")
        with self.assertRaises(ValueError): self.control("unload")
        self.control("cancel")
        self.call("plan_carrier_trade", commodity="silver", target=500)
        self.assertEqual(self.core.store.get("trade", "plan")["commodity"], "silver")

    def test_notes_reports_and_stage_survive_restart(self):
        op = self.control("start")["operation"]
        self.control("notes", notes="Wait until the carrier reaches the selling system.")
        self.report(op, 100)
        self.control("depart")
        restarted = Core(); loader.load_all(restarted)
        saved = restarted.store.get("trade", "operation")
        self.assertEqual((saved["id"], saved["loaded"], saved["stage"]), (op["id"], 100, "transit"))
        self.assertIn("Wait", saved["notes"])

    def test_replacing_cancelled_or_completed_trade_returns_to_ready(self):
        for ending in ("cancel", "complete"):
            with self.subTest(ending=ending):
                old = self.control("start")["operation"]
                self.report(old, 100)
                if ending == "complete":
                    self.control("depart"); self.control("unload")
                self.control(ending)
                before = copy.deepcopy(self.desk.data["inventory"])
                state = self.call("plan_carrier_trade", commodity="silver", source="Buy / Sol", destination="Sell / Lave",
                                  target=500, planned_quantity=500, source_price=100, destination_price=200)
                self.assertIsNone(state["operation"])
                self.assertEqual(state["previous_operation"]["operation"]["id"], old["id"])
                self.assertEqual(state["previous_operation"]["operation"]["reports"]["a"*32]["loading"], 100)
                self.assertEqual(state["inventory"], before)
                restarted = Core(); loader.load_all(restarted)
                self.assertIsNone(restarted.store.get("trade", "operation"))
                self.report(old, 200)
                self.assertIsNone(self.core.store.get("trade", "operation"))
                new = self.control("start")["operation"]
                self.assertNotEqual(new["id"], old["id"])
                self.assertEqual(new["loaded"], 0)
                self.control("cancel")

    def test_member_cannot_control_the_leader_or_replace_plan(self):
        self.core.store.set("party", "mode", "member")
        with self.assertRaises(ValueError): self.control("start")
        with self.assertRaises(ValueError): self.call("plan_carrier_trade", commodity="gold", target=1000)
