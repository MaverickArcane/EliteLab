"""An abandoned keep-alive request is a closed connection, not an app failure."""
import unittest
from unittest.mock import Mock

from elitelab.core.http import make_handler


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
