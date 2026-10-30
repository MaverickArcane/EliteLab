"""A party code admits a commander. It must not let one commander act as another."""
import http.client
import http.server
import json
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from test_elitelab import Core, config, loader

ATTACKER_SECRET = "f" * 32


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_core(saved_local=None):
    core = Core()
    real_read = core.read_data
    local = {} if saved_local is None else saved_local
    with patch.object(core, "read_data", side_effect=lambda *args, _read=real_read, **kwargs: local if args == ("party-local.json",) else _read(*args, **kwargs)):
        loader.load_all(core)
    return core


class PartyIdentityTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-party-identity-")
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
        self.member.join({"url": self.url, "code": self.state["code"]})

    def post(self, body):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("POST", "/report", json.dumps(body),
                               {"Content-Type": "application/json", "Authorization": "Bearer " + self.state["code"]})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    @staticmethod
    def report(**fields):
        return {"cmdr": "Impostor", "capacity": 999, "cargo_count": 0, "cargo": [], **fields}

    def test_member_has_a_private_secret_that_is_never_shared(self):
        self.assertRegex(self.member.secret, "^[0-9a-f]{32}$")
        self.assertNotEqual(self.member.secret, self.member.member_id)
        for m in self.leader.shared()["members"] + self.leader_core.store.get("party", "members"):
            self.assertNotIn("secret", m)

    def test_report_as_another_member_with_a_different_secret_is_rejected(self):
        status, body = self.post({"id": self.member.member_id, "secret": ATTACKER_SECRET, "report": self.report()})
        self.assertEqual(status, 400)
        self.assertIn("identity", body["error"].lower())
        self.assertEqual(self.leader.members[self.member.member_id]["cmdr"], "Hauler")

    def test_report_without_a_secret_is_rejected(self):
        status, _ = self.post({"id": self.member.member_id, "report": self.report()})
        self.assertEqual(status, 400)
        self.assertEqual(self.leader.members[self.member.member_id]["cmdr"], "Hauler")

    def test_leave_with_the_wrong_secret_keeps_the_member(self):
        status, _ = self.post({"id": self.member.member_id, "secret": ATTACKER_SECRET, "leave": True, "report": self.report()})
        self.assertEqual(status, 400)
        self.assertIn(self.member.member_id, self.leader.members)

    def test_a_new_id_is_bound_to_the_first_secret_seen(self):
        newcomer = "c" * 32
        status, _ = self.post({"id": newcomer, "secret": "d" * 32, "report": self.report(cmdr="Newcomer")})
        self.assertEqual(status, 200)
        status, _ = self.post({"id": newcomer, "secret": "e" * 32, "report": self.report(cmdr="Hijacker")})
        self.assertEqual(status, 400)
        status, _ = self.post({"id": newcomer, "secret": "d" * 32, "report": self.report(cmdr="Newcomer")})
        self.assertEqual(status, 200)
        self.assertEqual(self.leader.members[newcomer]["cmdr"], "Newcomer")

    def test_secret_is_restored_with_the_identity_on_restart(self):
        core = load_core({"id": self.member.member_id, "secret": self.member.secret})
        self.addCleanup(core.modules["party"].party.leave)
        party = core.modules["party"].party
        self.assertEqual((party.member_id, party.secret), (self.member.member_id, self.member.secret))

    def test_member_sends_its_secret_with_every_exchange(self):
        bodies, real = [], self.api.exchange

        def spy(url, token, body):
            bodies.append(body)
            return real(url, token, body)

        with patch.object(self.api, "exchange", side_effect=spy):
            self.member.synchronize(self.member.generation, "offline")
            self.member.leave()
        self.assertEqual(len(bodies), 2)
        self.assertTrue(all(b["secret"] == self.member.secret for b in bodies))
        self.assertTrue(bodies[-1]["leave"])
        self.assertNotIn(self.member.member_id, self.leader.members)


class LeaderResponseTests(unittest.TestCase):
    """Members render what the leader sends; numeric job fields must be numbers."""

    @classmethod
    def setUpClass(cls):
        cls.core = load_core()
        cls.api = cls.core.modules["party"].instance

    def serve(self, payload):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    def exchange(self, url):
        return self.api.exchange(url, "x" * 32, {"id": "b" * 32, "secret": "c" * 32, "report": {}})

    def test_non_numeric_job_quantities_are_rejected(self):
        bad = '1"><img src=x onerror=alert(1)>'
        operation = {"id": "a" * 32, "stage": "loading", "quantity": 100, "loaded": 0, "unloaded": 0}
        for field, container in (("quantity", "operation"), ("loaded", "operation"), ("unloaded", "operation"), ("planned_quantity", "plan")):
            payload = {"members": [], "plan": {"commodity": "gold", "planned_quantity": 100}, "operation": dict(operation)}
            payload[container][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.exchange(self.serve(payload))

    def test_numeric_and_missing_job_quantities_are_accepted(self):
        payload = {"members": [], "plan": {"commodity": "gold", "planned_quantity": None},
                   "operation": {"id": "a" * 32, "stage": "loading", "quantity": 100, "loaded": 5, "unloaded": None}}
        self.assertEqual(self.exchange(self.serve(payload))["operation"]["quantity"], 100)
        self.assertEqual(self.exchange(self.serve({"members": [], "plan": None, "operation": None}))["operation"], None)


if __name__ == "__main__":
    unittest.main()
