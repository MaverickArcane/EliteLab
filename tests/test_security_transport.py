"""Real-wire party framing and bounded, credential-free rejection evidence."""
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from elitelab.core.security import SecurityEvents
from modules.party.module import Party


class PartyFramingTests(unittest.TestCase):
    def setUp(self):
        self.party = SimpleNamespace(token="fixture-party-code", receive=Mock(return_value={"ok": True}))
        self.logger = Mock()
        replacement = patch("modules.party.module.log", self.logger)
        replacement.start()
        self.addCleanup(replacement.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Party.handler(self.party))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, lengths=(), extra="", body=b"{}", auth="fixture-party-code", half_close=True):
        headers = "".join(f"Content-Length: {length}\r\n" for length in lengths)
        request = (f"POST /report HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {auth}\r\n"
                   f"Content-Type: application/json\r\n{headers}{extra}Connection: close\r\n\r\n").encode() + body
        with socket.create_connection(self.server.server_address, timeout=3) as connection:
            connection.sendall(request)
            if half_close:
                connection.shutdown(socket.SHUT_WR)
            response = b""
            while chunk := connection.recv(4096):
                response += chunk
        return int(response.split(b" ")[1]), json.loads(response.split(b"\r\n\r\n", 1)[1])

    def test_ambiguous_and_incomplete_bodies_never_reach_party_state(self):
        cases = [((2, 2), "", b"{}"), ((2, 99), "", b"{}"),
                 ((2,), "Transfer-Encoding: chunked\r\n", b"{}"),
                 ((), "", b"{}"), ((3,), "", b"{}"),
                 ((64001,), "", b"{}"), ((2,), "", b"{x")]
        for lengths, extra, body in cases:
            with self.subTest(lengths=lengths, extra=extra):
                status, _ = self.post(lengths, extra, body)
                self.assertEqual(status, 400)
        self.party.receive.assert_not_called()
        self.logger.warning.assert_called_once()
        self.assertEqual(self.post((2,))[0], 200)
        self.party.receive.assert_called_once_with({})

    def test_auth_denial_is_recorded_without_credentials(self):
        self.assertEqual(self.post((2,), auth="ATTACKER-CREDENTIAL")[0], 403)
        self.party.receive.assert_not_called()
        call = self.logger.warning.call_args
        rendered = call.args[0] % call.args[1:]
        self.assertIn("source=party", rendered)
        self.assertIn("status=403", rendered)
        self.assertNotIn("ATTACKER", rendered)
        self.assertNotIn("fixture-party-code", rendered)

    def test_stalled_body_times_out_before_touching_party_state(self):
        original = self.server.RequestHandlerClass.setup

        def short_timeout(handler):
            original(handler)
            handler.connection.settimeout(0.1)

        with patch.object(self.server.RequestHandlerClass, "setup", short_timeout):
            status, body = self.post((3,), body=b"{", half_close=False)
        self.assertEqual(status, 400)
        self.assertIn("timed out", body["error"])
        self.party.receive.assert_not_called()
        self.assertEqual(self.post((2,))[0], 200)

    def test_peer_resets_close_without_server_thread_tracebacks(self):
        handler_class = Party.handler(self.party)
        handler = object.__new__(handler_class)
        for error in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            handler.close_connection = False
            with patch.object(BaseHTTPRequestHandler, "handle_one_request", side_effect=error):
                handler.handle_one_request()
            self.assertTrue(handler.close_connection)

    def test_application_errors_are_not_silenced_as_disconnects(self):
        handler = object.__new__(Party.handler(self.party))
        with patch.object(BaseHTTPRequestHandler, "handle_one_request", side_effect=RuntimeError("fixture defect")):
            with self.assertRaisesRegex(RuntimeError, "fixture defect"):
                handler.handle_one_request()


class SecurityEvidenceTests(unittest.TestCase):
    def test_concurrent_rejections_share_one_bounded_counter(self):
        logger = Mock()
        events = SecurityEvents(logger, "party")
        with patch("elitelab.core.security.time.monotonic", return_value=10):
            with ThreadPoolExecutor(max_workers=16) as workers:
                list(workers.map(events.rejected, [403] * 1000))
        logger.warning.assert_called_once()
        with patch("elitelab.core.security.time.monotonic", return_value=70):
            events.rejected(403)
        self.assertEqual(logger.warning.call_args.args[-1], 999)

    def test_repeated_denials_are_counted_without_unbounded_log_growth(self):
        logger = Mock()
        events = SecurityEvents(logger, "dashboard")
        with patch("elitelab.core.security.time.monotonic", return_value=10):
            for _ in range(1000):
                events.rejected(401)
            events.rejected(403)
            events.rejected(200)
            events.rejected(404)
        self.assertEqual(logger.warning.call_count, 2)
        with patch("elitelab.core.security.time.monotonic", return_value=70):
            events.rejected(401)
        self.assertEqual(logger.warning.call_count, 3)
        self.assertEqual(logger.warning.call_args.args[-1], 999)
        self.assertEqual(len(events.recent), 2)


if __name__ == "__main__":
    unittest.main()
