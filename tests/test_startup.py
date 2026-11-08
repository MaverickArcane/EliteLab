"""Browser startup follows successful server binding, including custom ports."""
import threading
import unittest
from unittest.mock import Mock, patch

from elitelab.core.http import HttpServer


class BrowserStartupTests(unittest.TestCase):
    def test_browser_uses_bound_port_and_loopback_for_wildcard(self):
        opened = threading.Event()
        server = Mock(server_address=("0.0.0.0", 43210))
        server.serve_forever.side_effect = lambda: self.assertTrue(opened.wait(2))
        with patch("elitelab.core.http.make_handler"), patch(
                "elitelab.core.http.ThreadingHTTPServer", return_value=server), patch(
                "elitelab.core.http.webbrowser.open", side_effect=lambda url: opened.set()) as browser:
            HttpServer(Mock()).serve("0.0.0.0", 0, open_browser=True)
            browser.assert_called_once_with("http://127.0.0.1:43210/")
        server.server_close.assert_called_once()

    def test_bind_failure_does_not_open_browser(self):
        with patch("elitelab.core.http.make_handler"), patch(
                "elitelab.core.http.ThreadingHTTPServer", side_effect=OSError("port in use")), patch(
                "elitelab.core.http.webbrowser.open") as browser:
            with self.assertRaises(OSError):
                HttpServer(Mock()).serve("127.0.0.1", 8766, open_browser=True)
            browser.assert_not_called()

    def test_default_server_does_not_open_browser(self):
        with patch("elitelab.core.http.make_handler"), patch(
                "elitelab.core.http.ThreadingHTTPServer"), patch(
                "elitelab.core.http.webbrowser.open") as browser:
            HttpServer(Mock()).serve("127.0.0.1", 8766)
            browser.assert_not_called()
