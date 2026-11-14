"""Lifecycle and parsing cases found during the pre-merge implementation review."""
import http.client
import json
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from elitelab.core import config
from elitelab.core.bus import EventBus
from elitelab.core.http import ExclusiveHTTPServer, Router, make_handler
from elitelab.core.store import Store
from modules.party.module import Party


class ReviewBoundaryTests(unittest.TestCase):
    def server(self, handler):
        server = ExclusiveHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def dashboard(self):
        auth = patch.object(config, 'AUTH_TOKEN', '')
        auth.start(); self.addCleanup(auth.stop)
        self.mutation = Mock(return_value={'ok': True})
        self.core = SimpleNamespace(store=Store(EventBus()), http=Router(), log=Mock())
        self.core.http.route('/api/test', self.mutation, method='POST')
        return self.server(make_handler(self.core))

    def wire(self, server, length='2', extra='', body=b'{}'):
        with socket.create_connection(server.server_address, timeout=3) as connection:
            connection.sendall(('POST /api/test HTTP/1.1\r\nHost: localhost\r\n'
                'Content-Type: application/json\r\nContent-Length: '+length+'\r\n'+extra+
                'Connection: close\r\n\r\n').encode()+body)
            connection.shutdown(socket.SHUT_WR)
            response = http.client.HTTPResponse(connection)
            response.begin(); response.read()
            return response.status

    def test_dashboard_rejects_non_decimal_lengths_and_empty_transfer_encoding(self):
        server = self.dashboard()
        for length, extra in [('+2', ''), ('0_2', ''), ('2', 'Transfer-Encoding:\r\n')]:
            with self.subTest(length=length, extra=extra):
                self.assertEqual(self.wire(server, length, extra), 400)
        self.mutation.assert_not_called()
        self.assertEqual(self.wire(server), 200)

    def test_dashboard_body_timeout_is_a_client_error_and_closes_connection(self):
        server = self.dashboard()
        original = server.RequestHandlerClass.setup
        def setup(handler):
            original(handler); handler.connection.settimeout(.1)
        with patch.object(server.RequestHandlerClass, 'setup', setup):
            with socket.create_connection(server.server_address, timeout=3) as connection:
                connection.sendall(b'POST /api/test HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{')
                response = http.client.HTTPResponse(connection); response.begin(); response.read()
                self.assertEqual(response.status, 400)
                self.assertEqual(connection.recv(1), b'')
        self.mutation.assert_not_called()
        self.core.log.exception.assert_not_called()

    def test_json_decoder_recursion_errors_are_rejected_without_tracebacks(self):
        # Decoder recursion limits differ between supported Python versions.
        # Force that failure at the parser boundary, then exercise real HTTP.
        decoder = patch('json.loads', side_effect=RecursionError('decoder nesting limit'))
        decoder.start(); self.addCleanup(decoder.stop)
        body = b'{}'
        server = self.dashboard()
        self.assertEqual(self.wire(server, str(len(body)), body=body), 400)
        self.mutation.assert_not_called()
        self.core.log.exception.assert_not_called()
        party = SimpleNamespace(token='code', lock=threading.RLock(), receive=Mock(return_value={}))
        server = self.server(Party.handler(party))
        with socket.create_connection(server.server_address, timeout=3) as connection:
            connection.sendall((f'POST /report HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer code\r\n'
                f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body)
            response = http.client.HTTPResponse(connection); response.begin(); response.read()
            self.assertEqual(response.status, 400)
        party.receive.assert_not_called()

    def test_closing_listener_terminates_idle_connections_and_event_subscriptions(self):
        server = self.dashboard()
        idle = socket.create_connection(server.server_address, timeout=3)
        self.addCleanup(idle.close)
        idle.sendall(b'GET /api/test HTTP/1.1\r\nHost: localhost\r\n')
        stream = http.client.HTTPConnection(*server.server_address, timeout=3)
        self.addCleanup(stream.close)
        stream.request('GET', '/events'); response = stream.getresponse()
        self.addCleanup(response.close)
        self.assertEqual(response.fp.readline(), b'event: snapshot\n')
        response.fp.readline(); response.fp.readline()
        server.shutdown(); server.server_close()
        deadline = time.monotonic()+2
        while server._connections and time.monotonic()<deadline: time.sleep(.01)
        self.assertFalse(server._connections, 'Closed listener retained active workers')
        self.assertFalse(server._streams)
        self.assertFalse(self.core.store._subs)

    def test_party_rechecks_invitation_after_read_before_receiving(self):
        party = SimpleNamespace(token='old-code', lock=threading.RLock(), receive=Mock(return_value={'ok': True}))
        handler = Party.handler(party)
        original = handler.setup
        reading, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def setup(instance):
            original(instance)
            raw = instance.rfile
            def read(size):
                reading.set()
                if not release.wait(3): raise AssertionError('Body gate not released')
                return raw.read(size)
            instance.rfile = SimpleNamespace(read=read, readline=raw.readline, close=raw.close)
        with patch.object(handler, 'setup', setup):
            server = self.server(handler)
            with socket.create_connection(server.server_address, timeout=3) as connection:
                connection.sendall(b'POST /report HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer old-code\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}')
                self.assertTrue(reading.wait(2))
                with party.lock: party.token = 'new-room-code'
                release.set()
                response = http.client.HTTPResponse(connection); response.begin(); response.read()
                self.assertEqual(response.status, 403)
        party.receive.assert_not_called()

    def test_party_rejects_python_integer_syntax_in_content_length(self):
        party = SimpleNamespace(token='code', lock=threading.RLock(), receive=Mock(return_value={'ok': True}))
        server = self.server(Party.handler(party))
        for value in ('+2','0_2'):
            with self.subTest(length=value), socket.create_connection(server.server_address, timeout=3) as connection:
                connection.sendall(('POST /report HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer code\r\nContent-Type: application/json\r\nContent-Length: '+value+'\r\n\r\n{}').encode())
                response = http.client.HTTPResponse(connection); response.begin(); response.read()
                self.assertEqual(response.status, 400)
        party.receive.assert_not_called()

    def test_real_party_rehost_cannot_accept_a_report_from_the_old_room(self):
        from test_party_identity import free_port, load_core
        with tempfile.TemporaryDirectory(prefix='elitelab-review-room-') as tmp, patch.object(config, 'DATA_DIR', tmp):
            core = load_core()
            party = core.modules['party'].party
            reading, release = threading.Event(), threading.Event()
            original = party.handler
            def gated_handler():
                handler = original(); setup = handler.setup
                def wrap(instance):
                    setup(instance); raw = instance.rfile
                    def read(size):
                        reading.set()
                        if not release.wait(8): raise AssertionError('Body gate not released')
                        return raw.read(size)
                    instance.rfile = SimpleNamespace(read=read, readline=raw.readline, close=raw.close)
                handler.setup = wrap
                return handler
            try:
                port = free_port()
                with patch.object(party, 'handler', gated_handler):
                    old = party.host({'bind': '127.0.0.1', 'port': port})
                mid = 'a'*32
                body = json.dumps({'id': mid, 'secret': 'b'*32, 'report': {'cmdr': 'Old room probe'}}).encode()
                with socket.create_connection(('127.0.0.1', port), timeout=4) as connection:
                    connection.sendall((f'POST /report HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {old["code"]}\r\n'
                        f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n').encode()+body)
                    self.assertTrue(reading.wait(3))
                    party.leave()
                    new = party.host({'bind': '127.0.0.1', 'port': free_port()})
                    self.assertNotEqual(new['code'], old['code'])
                    release.set()
                    try:
                        response = http.client.HTTPResponse(connection); response.begin(); response.read()
                        self.assertNotEqual(response.status, 200)
                    except (ConnectionError, http.client.RemoteDisconnected):
                        pass
                    self.assertNotIn(mid, party.members)
            finally:
                release.set(); core.close()
