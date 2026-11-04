"""Mac login ownership, browser selection, private protocol and child cleanup."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import queue
import subprocess
import sys
import tarfile
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.error
from unittest.mock import Mock, patch

from elitelab.macos_autostart import MacAutostart
from elitelab.macos_desktop import check_journal, read_commands, run, stop_child
from elitelab import window
from test_elitelab import config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_debian', ROOT / 'scripts/build_debian.py')
debian = importlib.util.module_from_spec(spec)
spec.loader.exec_module(debian)
spec = importlib.util.spec_from_file_location('build_macos', ROOT / 'scripts/build_macos.py')
package = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'build_debian': debian}):
    spec.loader.exec_module(package)


class MacDesktopTests(unittest.TestCase):
    def fixture(self, home):
        app = home / 'Applications/EliteLab.app'
        root = app / 'Contents/Resources/app'
        root.mkdir(parents=True)
        (root / '.macos-bundle').touch()
        (app / 'Contents/MacOS').mkdir()
        (app / 'Contents/MacOS/EliteLab').touch()
        return root

    def test_login_opt_in_upgrade_and_foreign_entry_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = self.fixture(home)
            setting = MacAutostart(root, home)
            self.assertEqual(setting.status(), 'disabled')
            setting.set_enabled(True)
            entry = plistlib.loads(setting.path.read_bytes())
            self.assertEqual(entry['ProgramArguments'], ['/usr/bin/open', '-a', str(root.parent.parent.parent.resolve())])
            self.assertIs(entry['RunAtLoad'], True)
            self.assertNotIn('KeepAlive', entry)
            self.assertEqual(MacAutostart(root, home).status(), 'enabled')
            setting.set_enabled(False)
            self.assertFalse(setting.path.exists())
            setting.path.write_bytes(b'foreign')
            for enabled in (True, False):
                with self.assertRaises(ValueError): setting.set_enabled(enabled)
            self.assertEqual(setting.path.read_bytes(), b'foreign')

    def test_source_cannot_register_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting = MacAutostart(tmp, tmp)
            with self.assertRaises(ValueError): setting.set_enabled(True)
            self.assertFalse(setting.path.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink ownership')
    def test_symlink_login_is_never_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            setting = MacAutostart(self.fixture(home), home)
            target = home / 'foreign'
            target.write_bytes(setting.entry)
            setting.path.parent.mkdir(parents=True)
            setting.path.symlink_to(target)
            for enabled in (True, False):
                with self.assertRaises(ValueError): setting.set_enabled(enabled)
            self.assertTrue(setting.path.is_symlink())
            self.assertEqual(target.read_bytes(), setting.entry)

    def test_mac_data_stays_outside_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = self.fixture(home)
            (root / 'data').mkdir()
            with patch('elitelab.core.config.os.path.expanduser', return_value=str(home)):
                self.assertEqual(config._default_data_dir(str(root), 'posix'),
                                 str(home / 'Library/Application Support/EliteLab'))

    def test_mac_browser_discovery_and_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = self.fixture(home)
            chrome = home / 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
            chrome.parent.mkdir(parents=True)
            chrome.touch()
            self.assertEqual(window.macos_browsers(applications=[home / 'Applications']), [str(chrome)])
            cfg = SimpleNamespace(ROOT=root, DATA_DIR=home / 'data', BROWSER=str(chrome))
            with patch('elitelab.window.sys.platform', 'darwin'), patch('elitelab.window.subprocess.Popen') as launch:
                self.assertTrue(window.open_dashboard('http://127.0.0.1:8000/setup/', cfg))
            self.assertEqual(launch.call_args.args[0][:3], [str(chrome), '--app=http://127.0.0.1:8000/setup/',
                                                          '--user-data-dir=' + str(home / 'data/browser')])
            with patch('elitelab.window.sys.platform', 'darwin'), patch('elitelab.window.macos_browsers', return_value=[]), patch('elitelab.window.webbrowser.open', return_value=True) as fallback:
                self.assertTrue(window.open_dashboard('http://127.0.0.1:8000/', cfg))
            fallback.assert_called_once()

    def test_protocol_only_fixed_actions_and_eof_quits(self):
        for source, expected in [('open\nsetup\nlogin\nstatus\n', ['open', 'setup', 'login', 'status', 'quit']),
                                 ('open; rm anything\n', ['quit']), ('x' * 300 + '\n', ['quit']),
                                 ('open', ['quit'])]:
            commands = queue.Queue()
            read_commands(io.StringIO(source), commands)
            self.assertEqual(list(commands.queue), expected)

    def test_shutdown_fallback_reaps_only_owned_child(self):
        child = Mock(poll=Mock(return_value=None))
        control = Mock(child=child, shutdown=Mock(return_value=False))
        stop_child(control)
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=10)
        child.reset_mock()
        control.shutdown.return_value = True
        child.wait.side_effect = [subprocess.TimeoutExpired('child', 75), 0]
        stop_child(control)
        child.terminate.assert_not_called()
        child.kill.assert_called_once()

    def test_check_cannot_pass_when_server_exits_without_becoming_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            child = Mock(poll=Mock(return_value=0), returncode=0)
            with patch.object(config, 'DATA_DIR', tmp), patch('elitelab.macos_desktop.subprocess.Popen', return_value=child):
                with self.assertRaisesRegex(RuntimeError, 'own ready server'):
                    run(check=True)
            child.terminate.assert_not_called()

    def test_diagnostic_rejects_unverified_urls_and_never_follows_redirects(self):
        control = Mock(verified_url=Mock(return_value=None))
        with patch('elitelab.macos_desktop.urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError): check_journal(control)
            opener.assert_not_called()
        seen = []
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                seen.append((self.path, self.headers.get('Authorization')))
                self.send_response(302)
                self.send_header('Location', '/must-not-follow')
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            control.verified_url.return_value = f'http://127.0.0.1:{server.server_port}/'
            control.config.AUTH_TOKEN = 'private-token'
            with self.assertRaises(urllib.error.HTTPError) as error: check_journal(control)
            self.assertEqual(error.exception.code, 302)
            self.assertEqual(seen, [('/api/journal', 'Bearer private-token')])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_runtime_checksum_and_archive_escape_are_rejected(self):
        if not hasattr(tarfile, 'data_filter'):
            self.skipTest('Runtime builder requires Python 3.13+')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'runtime.tar.gz'
            for name in ('python/../../escaped', '/outside'):
                with tarfile.open(archive, 'w:gz') as tar:
                    info = tarfile.TarInfo(name)
                    info.size = 4
                    tar.addfile(info, io.BytesIO(b'data'))
                digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                with self.assertRaises((ValueError, tarfile.FilterError)):
                    package.extract_runtime(archive, root / 'extract', digest)
                self.assertFalse((root / 'escaped').exists())
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    package.extract_runtime(archive, root / 'extract', '0' * 64)
