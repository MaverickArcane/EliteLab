"""Party persistence stays off the journal thread; member heartbeats survive bad leaders."""
from datetime import datetime, timezone
import http.server
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_elitelab import Core, config, loader
from test_party_identity import free_port, load_core


def sale(count=25):
    return {"event": "MarketSell", "timestamp": datetime.now(timezone.utc).isoformat(), "MarketID": 123, "Type": "gold", "Count": count}


class FakeLeader:
    """Answers every report with one fixed status and body."""

    def __init__(self, test, status, body):
        payload = json.dumps(body).encode()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        test.addCleanup(self.server.server_close)
        test.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"


class OwnerPersistenceTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-party-writer-")
        self.addCleanup(data.cleanup)
        p = patch.object(config, "DATA_DIR", data.name)
        p.start()
        self.addCleanup(p.stop)
        self.core = load_core()
        self.addCleanup(self.core.modules["party"].party.leave)
        self.party = self.core.modules["party"].party
        tools = self.core.http.tools
        tools["plan_carrier_trade"].fn({"commodity": "gold", "source": "Buy / Sol", "destination": "Sell / Lave", "target": 1000,
                                        "planned_quantity": 1000, "carrier_market_id": 123, "destination_market_id": 456})
        self.op = tools["manage_carrier_operation"].fn({"action": "start"})["operation"]

    def loaded(self):
        return (self.core.store.get("trade", "operation") or {}).get("loaded")

    def test_journal_delivery_defers_the_disk_write_and_credits_the_ledger_after_it(self):
        real, gate, writes = self.core.write_data, threading.Event(), []

        def slow(value, *parts):
            if parts == ("party-local.json",):
                writes.append(threading.current_thread().name)
                if not gate.wait(5):
                    raise AssertionError("Test never released the party-local.json write")
            return real(value, *parts)

        with patch.object(self.core, "write_data", side_effect=slow):
            handler = threading.Thread(target=self.core.bus.emit, args=("journal.MarketSell", sale()))
            handler.start()
            handler.join(2)
            # The watcher thread moves on while the receipt is still being written...
            self.assertFalse(handler.is_alive(), "journal handler blocked on the party-local.json write")
            self.assertEqual(self.party.work["loading"], 25)
            # ...and the owner's ledger only learns about the delivery once that receipt is durable.
            self.assertEqual(self.loaded(), 0)
            gate.set()
            self.assertTrue(self.party.flush(5))
        self.assertEqual(self.loaded(), 25)
        self.assertEqual(self.core.store.get("party", "desk")["progress"]["loading"], 25)
        self.assertEqual(self.core.read_data("party-local.json")["work"]["loading"], 25)
        self.assertEqual(writes, ["party-writer"])

    def test_leave_flushes_pending_receipts(self):
        self.core.bus.emit("journal.MarketSell", sale(40))
        self.party.leave()
        self.assertEqual(self.core.read_data("party-local.json")["work"]["loading"], 40)
        self.assertEqual(self.loaded(), 40)

    def test_manual_report_still_supersedes_queued_receipts_in_order(self):
        self.core.bus.emit("journal.MarketSell", sale(10))
        self.party.report_work({"id": self.op["id"], "tonnes": 5, "request_id": "manual-report-0001"})
        saved = self.core.read_data("party-local.json")
        self.assertEqual(saved["work"]["loading"], 15)
        self.assertEqual(len(saved["auto_seen"]), 1)
        self.assertIn("manual-report-0001", saved["receipts"])
        self.assertTrue(self.party.flush(5))
        self.assertEqual(self.loaded(), 15)
        self.assertEqual(self.core.read_data("party-local.json")["work"]["loading"], 15)


class MemberHeartbeatTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-party-heartbeat-")
        self.addCleanup(data.cleanup)
        p = patch.object(config, "DATA_DIR", data.name)
        p.start()
        self.addCleanup(p.stop)
        self.leader_core, self.member_core = load_core(), load_core()
        for c in (self.leader_core, self.member_core):
            self.addCleanup(c.modules["party"].party.leave)
        self.leader = self.leader_core.modules["party"].party
        self.member = self.member_core.modules["party"].party
        self.api = self.member_core.modules["party"].instance
        self.port = free_port()
        self.state = self.leader.host({"bind": "127.0.0.1", "port": self.port})
        self.url = f"http://127.0.0.1:{self.port}"
        self.member_core.store.update("journal", {"cmdr": "Hauler", "cargo_capacity": 100})

    def member_error(self):
        return self.member_core.store.get("party", "error")

    def test_unreadable_leader_response_is_reported_and_the_heartbeat_continues(self):
        self.member.join({"url": self.url, "code": self.state["code"]})
        good = self.member.remote
        plan = {"commodity": "gold", "planned_quantity": 10}
        operation = {"id": "a" * 32, "stage": "loading", "quantity": 10, "loaded": 0, "unloaded": 0}
        for bad in ({"members": [{"cmdr": "No id"}], "plan": plan, "operation": None},
                    {"members": ["not a member"], "plan": plan, "operation": operation},
                    {"members": [], "plan": {"planned_quantity": 10}, "operation": operation}):
            with self.subTest(bad=bad), patch.object(self.api, "exchange", return_value=bad):
                self.member.synchronize(self.member.generation, "offline")  # must not raise
            self.assertEqual(self.member.mode, "member")
            self.assertEqual(self.member.remote, good)
            self.assertIn("unreadable", self.member.error)
            self.assertIn("EliteLab versions", self.member.error)
            self.assertEqual(self.member_error(), self.member.error)
        # A healthy heartbeat clears the message again.
        self.member.synchronize(self.member.generation, "offline")
        self.assertIsNone(self.member.error)
        self.assertIsNone(self.member_error())
        self.assertEqual(len(self.leader.shared()["members"]), 2)

    def test_join_rejects_an_unreadable_leader_response_without_becoming_a_member(self):
        fake = FakeLeader(self, 200, {"members": [{"cmdr": "No id"}], "plan": {"commodity": "gold", "planned_quantity": 10}, "operation": None})
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.member.join({"url": fake.url, "code": "x" * 32})
        self.assertEqual(self.member.mode, "idle")

    def test_leader_400_text_reaches_the_member(self):
        fake = FakeLeader(self, 400, {"error": "Party is full."})
        with self.assertRaisesRegex(ValueError, "Party is full[.]") as raised:
            self.member.join({"url": fake.url, "code": "x" * 32})
        self.assertNotIn("HTTP 400", str(raised.exception))
        tainted = FakeLeader(self, 400, {"error": "x" * 500 + "\x07<b>bad</b>"})
        with self.assertRaises(ValueError) as raised:
            self.api.exchange(tainted.url, "x" * 32, {"id": "b" * 32, "secret": "c" * 32, "report": {}})
        self.assertLess(len(str(raised.exception)), 320)
        self.assertNotIn("\x07", str(raised.exception))
        empty = FakeLeader(self, 400, {})
        with self.assertRaisesRegex(ValueError, "HTTP 400"):
            self.api.exchange(empty.url, "x" * 32, {"id": "b" * 32, "secret": "c" * 32, "report": {}})

    def test_repeated_rejections_end_the_membership_instead_of_retrying_forever(self):
        self.member.join({"url": self.url, "code": self.state["code"]})
        fake = FakeLeader(self, 400, {"error": "Member identity rejected: another commander already reports with this id."})
        with self.member.lock:
            self.member.url = fake.url
        for attempt in range(1, 4):
            self.member.synchronize(self.member.generation, "Leader unavailable. Retrying; last reports may be stale.")
            self.assertIn("identity rejected", self.member.error, attempt)
            self.assertNotIn("Leader unavailable", self.member.error, attempt)
            self.assertEqual(self.member.mode, "member" if attempt < 3 else "idle", attempt)
        self.assertIn("identity rejected", self.member_error())
        self.assertEqual(self.member_core.store.get("party", "mode"), "idle")

    def test_a_single_rejection_does_not_end_the_membership(self):
        self.member.join({"url": self.url, "code": self.state["code"]})
        real = self.api.exchange
        with patch.object(self.api, "exchange", side_effect=self.api.LeaderRejected("Party is full.")):
            self.member.synchronize(self.member.generation, "offline")
        self.assertEqual((self.member.mode, self.member.error), ("member", "Party is full."))
        with patch.object(self.api, "exchange", side_effect=real):
            self.member.synchronize(self.member.generation, "offline")
        self.assertEqual((self.member.mode, self.member.error), ("member", None))
        self.assertTrue(time.time() - self.member.last_success < 5)


if __name__ == "__main__":
    unittest.main()
