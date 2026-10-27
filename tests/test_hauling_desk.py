"""Player instructions must agree with cargo, acknowledged work and job stages."""
import copy
import unittest

from modules.party.desk import project
from modules.party.loads import recommend
from modules.trade.operations import operation_view
from modules.trade.profit import split_profit


class HaulingDeskTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"commodity": "gold", "source": "Buy Port / Sol", "destination": "Sell Port / Lave",
                     "source_price": 100, "destination_price": 300, "crew_enabled": True,
                     "crew_split": split_profit(100, 300, 1000), "planned_quantity": 1000,
                     "carrier_market_id": 123, "source_market_id": 456, "destination_market_id": 789}
        self.op = {"id": "job", "stage": "loading", "quantity": 1000, "reports": {}}
        self.members = [{"id": "owner", "cmdr": "Owner", "leader": True, "capacity": 400, "cargo_count": 0, "cargo": []},
                        {"id": "crew", "cmdr": "Crew", "capacity": 200, "cargo_count": 0, "cargo": []}]

    def view(self, who="crew", work=None, stale=False):
        op = operation_view(self.op)
        shared = {"plan": self.plan, "operation": op, "members": self.members,
                  "carrier": {"name": "The Carrier", "callsign": "ABC-123", "system": "Sol"},
                  "load_suggestion": recommend(self.plan, op, self.members)}
        local = next((m for m in self.members if m["id"] == who), {})
        before = copy.deepcopy(shared)
        result = project(shared, who, local, work, stale)
        self.assertEqual(shared, before)
        return result

    def test_next_run_prices_destinations_and_copy_quantities(self):
        d = self.view()
        self.assertEqual((d["action"], d["quantity"], d["per_ton"], d["load_earnings"]), ("buy", 200, 50, 10000))
        self.assertEqual((d["pickup"]["system"], d["pickup"]["station"]), ("Sol", "Buy Port"))
        self.assertEqual((d["buy_price"], d["sell_price"]), (100, 150))
        self.op["stage"] = "unloading"
        d = self.view()
        self.assertEqual((d["pickup"]["market_id"], d["delivery"]["system"], d["buy_price"], d["sell_price"]), (123, "Lave", 250, 300))

    def test_ship_cargo_changes_action_without_inventing_progress(self):
        self.members[1].update(cargo_count=80, cargo=[{"key": "gold", "count": 60}, {"key": "silver", "count": 20}])
        d = self.view()
        self.assertEqual((d["action"], d["quantity"], d["progress"]["loading"], d["earnings"]), ("buy", 120, 0, 0))
        self.assertIn("deliver 180 t", d["reason"])

    def test_owner_transfers_are_not_crew_earnings(self):
        self.members[0].update(cargo_count=400, cargo=[{"key": "gold", "count": 400}])
        self.assertEqual(self.view("owner")["action"], "transfer_in")
        self.assertIsNone(self.view("owner")["per_ton"])
        self.members[0].update(cargo_count=0, cargo=[])
        self.op["stage"] = "unloading"
        self.assertEqual(self.view("owner")["action"], "transfer_out")

    def test_pending_reports_are_distinct_from_accepted_progress(self):
        self.op["reports"]["crew"] = {"loading": 100, "unloading": 0}
        d = self.view(work={"operation_id": "job", "loading": 125, "unloading": 0})
        self.assertEqual((d["progress"]["loading"], d["pending"]["loading"], d["earnings"]), (100, 25, 5000))
        self.assertEqual(d["action"], "wait")
        self.assertEqual(self.view(work={"operation_id": "old", "loading": 500})["pending"]["loading"], 0)

    def test_pause_disconnect_and_ended_jobs_never_request_pickups(self):
        self.assertEqual(self.view(stale=True)["action"], "wait")
        self.op["paused"] = True
        self.assertEqual(self.view()["action"], "wait")
        self.op["paused"] = False
        for phase in ("ready", "transit", "complete", "cancelled"):
            self.op["stage"] = phase
            d = self.view()
            self.assertEqual(d["action"], "wait")
            self.assertIsNone(d["quantity"])

    def test_disconnected_contributions_survive_and_totals_can_flag_conflicts(self):
        self.op["reports"] = {"crew": {"cmdr": "Crew", "loading": 800, "unloading": 200},
                              "departed": {"cmdr": "Old friend", "loading": 300, "unloading": 0}}
        d = self.view()
        departed = next(m for m in d["crew"] if m["id"] == "departed")
        self.assertFalse(departed["connected"])
        self.assertEqual(departed["earnings"], 15000)
        self.assertEqual(d["earnings"], 50000)
        self.assertTrue(d["over_target"])

    def test_unknown_prices_and_capacity_stay_unknown(self):
        self.plan.update(crew_enabled=False, carrier_price_known=False)
        self.members[1]["capacity"] = None
        d = self.view()
        self.assertIsNone(d["per_ton"])
        self.assertIsNone(d["quantity"])
        self.assertEqual(d["action"], "wait")
        self.op["reports"]["crew"] = {"loading": 100}
        self.assertIsNone(self.view()["earnings"])

    def test_personal_bonus_is_not_promised_to_every_crew_member(self):
        self.op["stage"] = "unloading"
        self.op["reports"]["crew"] = {"unloading":100}
        self.plan.update(mode="unload", crew_enabled=False, carrier_price_known=True,
                         carrier_price=150, destination_price=300, price_includes_bonus=True, bonus_per_ton=50)
        d = self.view()
        self.assertEqual((d["sell_price"],d["per_ton"],d["earnings"]),(250,100,10000))
