"""Tray actions must never target another server or forward secrets remotely."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from elitelab.tray_control import TrayControl


class TrayControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.guard = SimpleNamespace(directory=Path(self.temp.name))
        self.config = SimpleNamespace(AUTH_TOKEN='private-token', ROOT='synthetic-root')
        self.control = TrayControl(self.config)
        self.control.set_child(SimpleNamespace(pid=42, poll=lambda: None))
        self.patch = patch('elitelab.tray_control.InstanceGuard', return_value=self.guard)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def record(self, url='http://127.0.0.1:8766/', pid=42):
        (self.guard.directory/'instance.lock').write_bytes(b' ' + json.dumps({'url':url,'pid':pid}).encode())

    def test_only_own_healthy_server_is_allowed(self):
        self.record()
        with patch('elitelab.tray_control.health', return_value={'ready':True,'pid':42}) as probe:
            self.assertEqual(self.control.verified_url(), 'http://127.0.0.1:8766/')
        probe.assert_called_once_with('http://127.0.0.1:8766/', 'private-token')
        for url,pid in [('http://example.com:8766/',42),('http://127.0.0.1:8766/',43),
                        ('http://user@127.0.0.1:8766/',42),('http://127.0.0.1:8766/x',42)]:
            self.record(url,pid)
            with patch('elitelab.tray_control.health') as probe:
                self.assertIsNone(self.control.verified_url()); probe.assert_not_called()

    def test_localhost_is_normalized_and_dead_child_rejected(self):
        self.record('http://localhost:8766/')
        with patch('elitelab.tray_control.health', return_value={'ready':True, 'pid':42}) as probe:
            self.assertEqual(self.control.verified_url(), 'http://127.0.0.1:8766/')
        probe.assert_called_once_with('http://127.0.0.1:8766/', 'private-token')
        self.control.set_child(SimpleNamespace(pid=42, poll=lambda: 0))
        with patch('elitelab.tray_control.health') as probe:
            self.assertIsNone(self.control.verified_url())
            probe.assert_not_called()

    def test_open_refreshes_changed_browser_settings(self):
        changed = SimpleNamespace(AUTH_TOKEN='private-token', DATA_DIR='new-profile')
        self.control.refresh = lambda: changed
        with patch.object(self.control, 'verified_url', return_value='http://127.0.0.1:8766/'), patch('elitelab.tray_control.open_dashboard', return_value=True) as browser:
            self.assertTrue(self.control.open())
        browser.assert_called_once_with('http://127.0.0.1:8766/', changed)

    def test_open_and_shutdown_refuse_unverified_server(self):
        with patch.object(self.control, 'verified_url', return_value=None), patch('elitelab.tray_control.open_dashboard') as browser, patch('elitelab.tray_control.urllib.request.build_opener') as opener:
            self.assertFalse(self.control.open(True)); self.assertFalse(self.control.shutdown())
            browser.assert_not_called(); opener.assert_not_called()

    def test_setup_opens_verified_server(self):
        with patch.object(self.control, 'verified_url', return_value='http://127.0.0.1:8766/'), patch('elitelab.tray_control.open_dashboard', return_value=True) as browser:
            self.assertTrue(self.control.open(True))
        browser.assert_called_once_with('http://127.0.0.1:8766/setup/', self.config)

    def test_sign_in_toggle_is_explicit_and_rejects_conflicts(self):
        setting = Mock(); setting.status.return_value='disabled'; setting.set_enabled.return_value=True
        with patch('elitelab.tray_control.Autostart', return_value=setting):
            self.assertTrue(self.control.toggle_autostart())
            setting.set_enabled.assert_called_once_with(True)
            setting.reset_mock(); setting.status.return_value='enabled'; setting.set_enabled.return_value=False
            self.assertFalse(self.control.toggle_autostart())
            setting.set_enabled.assert_called_once_with(False)
            setting.reset_mock(); setting.status.return_value='conflict'
            with self.assertRaises(ValueError): self.control.toggle_autostart()
            setting.set_enabled.assert_not_called()

    def test_shutdown_sends_token_to_verified_server_without_redirects(self):
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False); response.read.return_value=b'{"stopping":true}'
        opener = Mock(); opener.open.return_value=response
        with patch.object(self.control, 'verified_url', return_value='http://127.0.0.1:8766/'), patch('elitelab.tray_control.urllib.request.build_opener', return_value=opener) as factory:
            self.assertTrue(self.control.shutdown())
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://127.0.0.1:8766/api/shutdown')
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-token')
        self.assertEqual(request.get_method(), 'POST')
        self.assertIsInstance(factory.call_args.args[1], __import__('elitelab.tray_control',fromlist=['NoRedirect']).NoRedirect)
