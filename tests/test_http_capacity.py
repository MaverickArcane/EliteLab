"""Bound connections before worker allocation; reserve room for ordinary APIs."""
import http.client
import logging
import socket
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from elitelab.core import config
from elitelab.core.bus import EventBus
from elitelab.core.http import ExclusiveHTTPServer, Router, make_handler
from elitelab.core.store import Store


class SmallServer(ExclusiveHTTPServer):
    max_connections = 4
    max_connections_per_peer = 2
    max_streams = 2
    max_streams_per_peer = 1


class HttpCapacityTests(unittest.TestCase):
    def setUp(self):
        auth = patch.object(config, 'AUTH_TOKEN', '')
        auth.start(); self.addCleanup(auth.stop)
        self.core = SimpleNamespace(store=Store(EventBus()), http=Router(), log=logging.getLogger('capacity-test'))
        self.core.http.route('/api/ping', lambda q: {'ok': True})
        self.server = SmallServer(('127.0.0.1', 0), make_handler(self.core))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.sockets = []
        self.addCleanup(lambda: [s.close() for s in self.sockets])

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(.01)
        self.fail('Capacity did not recover before the deadline')

    def hold(self, peer):
        connection = socket.create_connection(self.server.server_address, timeout=2, source_address=(peer, 0))
        connection.sendall(b'GET /api/ping HTTP/1.1\r\nHost: localhost\r\n')
        self.sockets.append(connection)
        return connection

    def request(self, peer='127.0.0.1', path='/api/ping', method='GET'):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=2, source_address=(peer, 0))
        try:
            connection.request(method, path)
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            return result
        finally:
            connection.close()

    def test_one_peer_is_capped_before_threads_and_other_peers_still_work(self):
        held = [self.hold('127.0.0.1') for _ in range(2)]
        self.wait_for(lambda: len(self.server._connections) == 2)
        for _ in range(6):
            self.assertEqual(self.request()[0], 503)
            self.assertEqual(len(self.server._connections), 2)
        self.assertEqual(self.request('127.0.0.2')[0], 200)
        for connection in held: connection.close()
        self.wait_for(lambda: not self.server._connections)
        self.assertEqual(self.request()[0], 200)

    def test_global_limit_bounds_multiple_peers_and_recovers(self):
        for peer in ('127.0.0.1', '127.0.0.2'):
            for _ in range(2): self.hold(peer)
        self.wait_for(lambda: len(self.server._connections) == 4)
        self.assertEqual(self.request('127.0.0.3')[0], 503)
        self.assertEqual(len(self.server._connections), 4)
        for connection in self.sockets: connection.close()
        self.wait_for(lambda: not self.server._connections)
        self.assertFalse(self.server._peer_connections)
        self.assertEqual(self.request()[0], 200)

    def test_thread_creation_failure_releases_admission(self):
        request = object()
        with patch('http.server.ThreadingHTTPServer.process_request', side_effect=RuntimeError('thread unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'thread unavailable'):
                self.server.process_request(request, ('127.0.0.1', 1234))
        self.assertFalse(self.server._connections)
        self.assertFalse(self.server._peer_connections)

    def stream(self, peer):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=2, source_address=(peer, 0))
        connection.request('GET', '/events')
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.fp.readline(), b'event: snapshot\n')
        response.fp.readline(); response.fp.readline()
        self.addCleanup(connection.close); self.addCleanup(response.close)
        return connection, response

    def test_stream_quota_leaves_api_room_and_closed_tabs_release_slots(self):
        first, response = self.stream('127.0.0.1')
        self.assertEqual(self.request(path='/events')[0], 503)
        self.assertEqual(self.request()[0], 200)
        second, response2 = self.stream('127.0.0.2')
        self.assertEqual(self.request('127.0.0.3', '/events')[0], 503)
        self.assertEqual(self.request('127.0.0.3')[0], 200)
        response.close(); first.close()
        self.wait_for(lambda: self.server._stream_count == 1)
        self.assertNotIn('127.0.0.1', self.server._streams)
        third, response3 = self.stream('127.0.0.1')
        response2.close(); second.close(); response3.close(); third.close()
        self.wait_for(lambda: self.server._stream_count == 0)

    def test_headers_do_not_disclose_runtime_and_style_policy_is_strict(self):
        for method, path, expected in [('GET', '/api/ping', 200), ('GET', '/api/missing', 404), ('TRACE', '/', 501)]:
            status, headers, _ = self.request(path=path, method=method)
            self.assertEqual(status, expected)
            self.assertEqual(headers['Server'], 'EliteLab')
            if method == 'GET':
                self.assertIn("style-src 'self';", headers['Content-Security-Policy'])
                self.assertIn("style-src-attr 'none'", headers['Content-Security-Policy'])
                self.assertNotIn('unsafe-inline', headers['Content-Security-Policy'])
