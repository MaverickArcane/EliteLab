"""Browser startup follows successful server binding, including custom ports."""
import threading
import unittest
from unittest.mock import Mock, patch

from test_elitelab import Core
from elitelab.core.http import HttpServer, ExclusiveHTTPServer
from http.server import BaseHTTPRequestHandler


class BrowserStartupTests(unittest.TestCase):
    def test_browser_uses_bound_port_and_loopback_for_wildcard(self):
        opened = threading.Event()
        server = Mock(server_address=("0.0.0.0", 43210))
        server.serve_forever.side_effect = lambda: self.assertTrue(opened.wait(2))
        with patch("elitelab.core.http.make_handler"), patch(
                "elitelab.core.http.ExclusiveHTTPServer", return_value=server), patch(
                "elitelab.core.http.webbrowser.open", side_effect=lambda url: opened.set()) as browser:
            HttpServer(Mock()).serve("0.0.0.0", 0, open_browser=True)
            browser.assert_called_once_with("http://127.0.0.1:43210/")
        server.server_close.assert_called_once()

    def test_bind_failure_does_not_open_browser(self):
        with patch("elitelab.core.http.make_handler"), patch(
                "elitelab.core.http.ExclusiveHTTPServer", side_effect=OSError("port in use")), patch(
                "elitelab.core.http.webbrowser.open") as browser:
            with self.assertRaises(OSError):
                HttpServer(Mock()).serve("127.0.0.1", 8766, open_browser=True)
            browser.assert_not_called()

    def test_default_server_does_not_open_browser(self):
        with patch("elitelab.core.http.make_handler"), patch(
                "elitelab.core.http.ExclusiveHTTPServer"), patch(
                "elitelab.core.http.webbrowser.open") as browser:
            HttpServer(Mock()).serve("127.0.0.1", 8766)
            browser.assert_not_called()


class PortOwnershipTests(unittest.TestCase):
    def test_second_server_cannot_bind_same_address(self):
        first=ExclusiveHTTPServer(('127.0.0.1',0), BaseHTTPRequestHandler)
        self.addCleanup(first.server_close)
        with self.assertRaises(OSError):
            ExclusiveHTTPServer(first.server_address, BaseHTTPRequestHandler)


class CoreStartupTests(unittest.TestCase):
    def test_port_failure_happens_before_module_load_and_watcher(self):
        from elitelab.core import Core
        core=Core()
        with patch.object(core._server,'bind',side_effect=OSError('busy')), patch(
                'elitelab.core.load_all') as load, patch.object(core.watcher,'start') as watch:
            with self.assertRaises(OSError):core.start('127.0.0.1',19000)
            load.assert_not_called();watch.assert_not_called()

    def test_shutdown_runs_party_cleanup(self):
        from elitelab.core import Core
        core=Core();callback=Mock();core.shutdown_callbacks.append(callback)
        core._server=Mock();core._server.serve.side_effect=KeyboardInterrupt
        with patch('elitelab.core.load_all'), patch.object(core.watcher,'start'), patch.object(core.watcher,'stop') as stop:
            core.start('127.0.0.1',19000)
        stop.assert_called_once();callback.assert_called_once();self.assertFalse(core.ready)
