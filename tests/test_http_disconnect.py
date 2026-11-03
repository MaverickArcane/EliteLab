"""An abandoned keep-alive request is a closed connection, not an app failure."""
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from elitelab.core.http import Router, config, make_handler


class DisconnectTests(unittest.TestCase):
    def handler(self, error):
        handler = object.__new__(make_handler(Mock()))
        handler.rfile = Mock()
        handler.rfile.readline.side_effect = error
        handler.close_connection = False
        return handler

    def test_peer_disconnects_close_the_connection(self):
        for error in (ConnectionAbortedError(), ConnectionResetError(), BrokenPipeError()):
            with self.subTest(error=type(error).__name__):
                handler = self.handler(error)
                handler.handle_one_request()
                self.assertTrue(handler.close_connection)

    def test_unrelated_errors_are_not_hidden(self):
        with self.assertRaisesRegex(ValueError,"application error"):
            self.handler(ValueError("application error")).handle_one_request()

    def health_request(self, writes=None, route_error=None):
        core = Mock()
        core.http = Router()
        route = Mock(return_value={"ok": True}, side_effect=route_error)
        core.http.route('/api/health', route)
        handler = object.__new__(make_handler(core))
        handler.server = Mock(server_address=('127.0.0.1', 8766))
        handler.rfile = BytesIO(b'GET /api/health HTTP/1.1\r\nHost: localhost\r\n\r\n')
        handler.wfile = Mock()
        handler.wfile.write.side_effect = writes + [None, None] if writes is not None else None
        with patch.object(config, 'AUTH_TOKEN', ''):
            handler.handle_one_request()
        return core, handler

    def test_response_disconnects_do_not_log_or_attempt_a_second_response(self):
        for error_type in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            for phase in ('headers', 'body'):
                with self.subTest(error=error_type.__name__, phase=phase):
                    writes = [error_type()] if phase == 'headers' else [None, error_type()]
                    core, handler = self.health_request(writes=writes)
                    self.assertTrue(handler.close_connection)
                    core.log.exception.assert_not_called()
                    self.assertEqual(handler.wfile.write.call_count, len(writes))

    def test_health_response_still_succeeds(self):
        core, handler = self.health_request()
        core.log.exception.assert_not_called()
        self.assertFalse(handler.close_connection)
        self.assertIn(b'200 OK', handler.wfile.write.call_args_list[0].args[0])
        self.assertEqual(handler.wfile.write.call_args_list[1].args[0], b'{"ok": true}')

    def test_route_failures_are_still_logged_and_return_500(self):
        for error in (RuntimeError('route failed'), ConnectionResetError('upstream failed')):
            with self.subTest(error=type(error).__name__):
                core, handler = self.health_request(route_error=error)
                core.log.exception.assert_called_once_with('request failed: %s %s', 'GET', '/api/health')
                self.assertIn(b'500 Internal Server Error', handler.wfile.write.call_args_list[0].args[0])
