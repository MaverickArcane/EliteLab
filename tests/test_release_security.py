"""Real HTTP regression checks for credential redirects and session expiry."""
import hashlib
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import logging
import os
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from elitelab import mcp
from elitelab.core import config
from elitelab.core.bus import EventBus
from elitelab.core.http import Router, make_handler
from elitelab.core.store import Store


class ReleaseSecurityTests(unittest.TestCase):
    def server(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_mcp_rejects_all_redirects_before_sending_credentials(self):
        received = []

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
            do_POST = do_GET
            def log_message(self, *args):
                pass

        target = self.server(Target)
        redirect = {'code': 302, 'url': f'http://127.0.0.1:{target.server_port}/untrusted'}

        class Redirect(Target):
            def do_GET(self):
                if self.path == '/untrusted':
                    return super().do_GET()
                self.send_response(redirect['code'])
                self.send_header('Location', redirect['url'])
                self.send_header('Content-Length', '0')
                self.end_headers()
            do_POST = do_GET

        source = self.server(Redirect)
        base = f'http://127.0.0.1:{source.server_port}'
        with patch.object(mcp, 'BASE', base), patch.dict(os.environ, ELITELAB_AUTH_TOKEN='fixture-token'):
            for destination in (redirect['url'], base + '/untrusted'):
                redirect['url'] = destination
                for code in (301, 302, 303, 307, 308):
                    redirect['code'] = code
                    for method, path in (('GET', '/api/schema'), ('POST', '/api/tool'), ('GET', '/api/state')):
                        with self.subTest(code=code, method=method, destination=destination):
                            with self.assertRaisesRegex(RuntimeError, f'HTTP {code}'):
                                mcp._http(method, path, body={} if method == 'POST' else None)
            self.assertEqual(received, [])
            with patch.object(mcp, 'BASE', f'http://127.0.0.1:{target.server_port}'):
                self.assertEqual(mcp._http('GET', '/api/schema'), {})
            self.assertEqual(received, ['Bearer fixture-token'])

    def stream(self, token, cookie=None, bearer=None):
        store = Store(EventBus())
        core = SimpleNamespace(store=store, http=Router(), log=logging.getLogger('release-test'))
        server = self.server(make_handler(core))
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=4)
        self.addCleanup(conn.close)
        headers = {}
        if cookie:
            headers['Cookie'] = cookie
        if bearer:
            headers['Authorization'] = 'Bearer ' + bearer
        conn.request('GET', '/events', headers=headers)
        response = conn.getresponse()
        self.addCleanup(response.close)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.fp.readline(), b'event: snapshot\n')
        response.fp.readline(); response.fp.readline()
        return store, response, server

    def test_cookie_stream_closes_at_expiry_even_when_idle(self):
        for publish in (False, True):
            with self.subTest(publish=publish), patch.object(config, 'AUTH_TOKEN', 'fixture-token'):
                expiry = int(time.time()) + 2
                value = f'{expiry}.fixture'
                signature = hmac.new(b'fixture-token', value.encode(), hashlib.sha256).hexdigest()
                cookie = f'elitelab_session={value}.{signature}'
                store, response, server = self.stream('fixture-token', cookie=cookie)
                time.sleep(max(0, expiry - time.time()) + .05)
                if publish:
                    store.set('private', 'value', 'after expiry')
                self.assertEqual(response.read(), b'')
                self.assertEqual(len(store._subs), 0)
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                try:
                    conn.request('GET', '/api/state', headers={'Cookie': cookie})
                    self.assertEqual(conn.getresponse().status, 401)
                finally:
                    conn.close()

    def test_bearer_and_local_streams_continue(self):
        for token in ('fixture-token', ''):
            with self.subTest(token=bool(token)), patch.object(config, 'AUTH_TOKEN', token):
                store, response, _ = self.stream(token, bearer=token or None)
                store.set('fixture', 'value', 'still authorized')
                self.assertEqual(response.fp.readline(), b'event: state\n')
                self.assertIn(b'still authorized', response.fp.readline())
                response.close()


if __name__ == '__main__':
    unittest.main()
