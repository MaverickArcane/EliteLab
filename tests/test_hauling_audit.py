"""Corrections, evidence and exports under duplicate/reordered crew reports."""
import json
import random
import unittest

import test_trade_party as trade_tests
from test_elitelab import Core, loader
from modules.trade.audit import MAX_HISTORY, record
from modules.trade.operations import operation_view


class HaulingAuditTests(unittest.TestCase):
    call = trade_tests.TradeTests.call

    def setUp(self):
        trade_tests.TradeTests.setUp(self)
        self.call("plan_carrier_trade", commodity="gold", source="Buy / Sol", destination="Sell / Lave",
                  source_price=100, destination_price=300, target=10440, planned_quantity=10000, crew_enabled=True)
        self.op = self.call("manage_carrier_operation", action="start")["operation"]
        self.mid = "a"*32

    def report(self, loading, unloading=0, entry=None):
        work = {"operation_id":self.op["id"],"loading":loading,"unloading":unloading}
        if entry:
            work["last_entry"] = entry
        self.core.bus.emit("party.work", {"id":self.mid,"report":{"cmdr":"Private Commander","work":work}})

    def correction(self, tonnes, request="correction-00000001", phase="loading", **extra):
        row = self.core.store.get("trade","operation")["reports"][self.mid]
        return {"id":self.op["id"],"member":self.mid,"phase":phase,"tonnes":tonnes,
                "expected":row.get(phase,0),"expected_reported":row.get("reported",row).get(phase,0),
                "reason":"Duplicate manual entry", "request_id":request, **extra}

    def test_correction_survives_retries_late_reports_and_restart(self):
        self.report(200)
        command = self.correction(100)
        self.call("correct_hauling_delivery",**command)
        self.report(200); self.report(150); self.report(250)
        self.call("correct_hauling_delivery",**command)
        state = self.core.store.get("trade","operation")
        self.assertEqual(state["loaded"],150)
        self.assertEqual(state["reports"][self.mid]["reported"]["loading"],250)
        self.assertEqual(state["reports"][self.mid]["adjustments"]["loading"],-100)
        self.assertNotIn("correction_requests",state)
        self.assertEqual(sum(e["kind"]=="correction" for e in state["history"]),1)
        restarted = Core(); loader.load_all(restarted)
        self.assertEqual(restarted.store.get("trade","operation")["loaded"],150)
        with self.assertRaises(ValueError):
            self.call("correct_hauling_delivery",**{**command,"tonnes":99})

    def test_stale_correction_and_member_writes_are_rejected(self):
        self.report(100)
        command = self.correction(50)
        self.report(125)
        with self.assertRaises(ValueError): self.call("correct_hauling_delivery",**command)
        self.core.store.set("party","mode","member")
        with self.assertRaises(ValueError): self.call("correct_hauling_delivery",**self.correction(50))
        self.assertEqual(self.core.store.get("trade","operation")["loaded"],125)

    def test_bad_phase_total_reason_or_unknown_commander_cannot_change_progress(self):
        self.report(100)
        for extra in ({"tonnes":-1},{"tonnes":10001},{"tonnes":True},{"reason":" "},
                      {"member":"unknown"},{"phase":"unloading"},{"request_id":"short"},{"id":"old"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.call("correct_hauling_delivery",**{**self.correction(50),**extra})
        self.assertEqual(self.core.store.get("trade","operation")["loaded"],100)

    def test_delivery_history_identifies_latest_local_evidence_and_ignores_heartbeats(self):
        entry = {"kind":"MarketSell","phase":"loading","tonnes":100,"at":"2026-10-27T15:00:00Z"}
        self.report(100,entry=entry)
        before = self.core.store.get("trade","operation")["history_count"]
        for _ in range(4): self.report(100,entry=entry)
        op = self.core.store.get("trade","operation")
        self.assertEqual(op["history_count"],before)
        event = op["history"][-1]
        self.assertEqual((event["kind"],event["before"],event["after"]),("delivery",0,100))
        self.assertEqual(event["last_entry"],entry)

    def test_export_is_allowlisted_and_anonymized(self):
        self.report(100)
        self.call("correct_hauling_delivery",**self.correction(75,reason="PRIVATE_REASON"))
        self.core.store.update("party",{"code":"PRIVATE_CODE","url":"http://PRIVATE_ADDRESS", "error":"PRIVATE_PATH"})
        self.core.store.update("journal",{"credits":987654321,"cmdr":"Private Commander"})
        self.desk.data["operation"]["notes"]="PRIVATE_NOTES"
        exported = self.call("export_hauling_diagnostics")
        encoded = json.dumps(exported)
        for secret in ("PRIVATE_CODE","PRIVATE_ADDRESS","PRIVATE_PATH","PRIVATE_NOTES","PRIVATE_REASON","Private Commander",self.mid,"987654321"):
            self.assertNotIn(secret,encoded)
        self.assertEqual(exported["totals"]["loading"],75)
        self.assertEqual(exported["reports"][0]["reported"]["loading"],100)
        self.assertEqual(exported["reports"][0]["adjustments"]["loading"],-25)
        self.assertTrue(exported["history"][-1]["reason_provided"])

    def test_history_is_bounded_and_transport_shares_only_latest_entries(self):
        op = {"quantity":100,"reports":{}}
        for _ in range(MAX_HISTORY+5): record(op,"stage",action="pause",stage="loading",paused=True)
        self.assertEqual(len(op["audit"]),MAX_HISTORY)
        public = operation_view(op)
        self.assertEqual(len(public["history"]),20)
        self.assertEqual(public["history_count"],MAX_HISTORY+5)
        self.assertNotIn("audit",public)

    def test_seeded_two_leg_session_conserves_corrected_totals_under_failures(self):
        rng = random.Random(991)
        sent = {"loading":1,"unloading":0}
        accepted = dict(sent)
        offsets = {"loading":0,"unloading":0}
        self.report(1)
        packets = [dict(sent)]
        for phase in ("loading","unloading"):
            if phase=="unloading":
                for action in ("depart","unload"):
                    self.call("manage_carrier_operation",action=action,id=self.op["id"])
            for step in range(80):
                sent[phase] += rng.randrange(1,20)
                packets.append(dict(sent))
                packet = rng.choice(packets)  # delayed, duplicated and missing reports
                self.report(packet["loading"],packet["unloading"])
                for leg in accepted:
                    if leg=="loading" or phase=="unloading": accepted[leg]=max(accepted[leg],packet[leg])
                if step%9==0:
                    desired = max(0,accepted[phase]+offsets[phase]+rng.randrange(-20,21))
                    command = self.correction(desired,request=f"{phase}-correction-{step:08}",phase=phase)
                    self.call("correct_hauling_delivery",**command)
                    self.call("correct_hauling_delivery",**command)
                    offsets[phase]=desired-accepted[phase]
                if step%23==0:
                    self.core = Core(); loader.load_all(self.core)
                    self.desk = self.core.modules["trade"].trade
                op = self.core.store.get("trade","operation")
                self.assertEqual(op["loaded"],accepted["loading"]+offsets["loading"])
                self.assertEqual(op["unloaded"],accepted["unloading"]+offsets["unloading"])
                for leg, total in (("loading",op["loaded"]),("unloading",op["unloaded"])):
                    self.assertEqual(total,sum(row.get(leg,0) for row in op["reports"].values()))
