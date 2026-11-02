"""Run source setup from an extracted tree, with real HTTP and isolated data."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest.mock import patch

from test_elitelab import Core, config

ROOT = Path(__file__).resolve().parents[1]


class BrowserReadinessTests(unittest.TestCase):
    def test_setup_opens_only_after_own_ready_health_response(self):
        core = Core(); core.ready = True
        opened = threading.Event()
        states = [None, {'ready': True, 'pid': -1}, {'ready': False, 'pid': os.getpid()},
                  {'ready': True, 'pid': os.getpid()}]
        with patch('elitelab.instance.health', side_effect=states) as health, patch(
                'webbrowser.open', side_effect=lambda url: opened.set()) as browser:
            timer = core._open_browser('0.0.0.0', 19000, '/setup/')
            try:
                self.assertTrue(opened.wait(3))
                browser.assert_called_once_with('http://127.0.0.1:19000/setup/')
                self.assertEqual(health.call_count, 4)
                self.assertEqual(health.call_args.args, ('http://127.0.0.1:19000/', config.AUTH_TOKEN))
            finally:
                core.ready = False; timer.cancel(); timer.join(2); core.close()

    def test_stopping_during_health_probe_does_not_open_browser(self):
        core = Core(); core.ready = True
        def health(*args):
            core.ready = False
            return {'ready': True, 'pid': os.getpid()}
        with patch('elitelab.instance.health', side_effect=health), patch('webbrowser.open') as browser:
            timer = core._open_browser('127.0.0.1', 19000, '/setup/')
            timer.join(2)
            self.assertFalse(timer.is_alive())
            browser.assert_not_called()
        core.close()


class SourceSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='EliteLab setup ')
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.app = self.folder / 'source & space'
        self.app.mkdir()
        for name in ('elitelab', 'modules', 'web'):
            shutil.copytree(ROOT / name, self.app / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('Setup EliteLab.cmd', 'Start EliteLab.cmd', 'setup.sh', 'start.sh'):
            shutil.copyfile(ROOT / name, self.app / name)
        (self.app / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/serve-loop.cmd', self.app / 'scripts/serve-loop.cmd')
        self.journals = self.folder / 'Saved Games journals'
        shutil.copytree(ROOT / 'tests/fixtures/journals', self.journals)
        self.data = self.folder / 'persistent data'
        self.data.mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); self.port = sock.getsockname()[1]
        self.base = f'http://127.0.0.1:{self.port}/'
        self.settings = self.folder / 'settings with spaces.json'
        self.original = {'port': self.port, 'host': '127.0.0.1', 'journal_dir': str(self.folder / 'missing journals'),
                         'data_dir': str(self.data), 'connections': {'future': {'keep': True}}, 'future_key': 'keep'}
        self.settings.write_text(json.dumps(self.original), encoding='utf-8')
        self.browser_log = self.folder / 'browser.jsonl'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('ELITELAB_')}
        self.env.update(ELITELAB_OFFLINE='1', ELITELAB_INSTANCE_DIR=str(self.folder / 'instance'),
                        PYTHONPATH=str(self.folder / 'capture'), LAB_SETUP_BROWSER_LOG=str(self.browser_log),
                        PATH=os.path.dirname(sys.executable) + os.pathsep + os.environ.get('PATH', ''))
        capture = self.folder / 'capture'; capture.mkdir()
        (capture / 'sitecustomize.py').write_text(
            'import json,os,webbrowser\n'
            'class Capture:\n'
            ' def open(self,url,*args,**kwargs):\n'
            '  with open(os.environ["LAB_SETUP_BROWSER_LOG"],"a") as f: f.write(json.dumps(url)+"\\n")\n'
            '  return True\n'
            'webbrowser.register("setup-test",None,Capture(),preferred=True)\n', encoding='ascii')
        self.flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.log = (self.folder / 'launch.log').open('w')
        self.addCleanup(self.log.close)
        self.process = None
        self.addCleanup(self.stop)

    def command(self, *args):
        if os.name == 'nt':
            return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', 'call', 'Setup EliteLab.cmd', *args]
        return ['/bin/sh', str(self.app / 'setup.sh'), *args]

    def request(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=2) as response:
            return json.load(response)

    def wait_for(self, fn):
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                value = fn()
                if value:
                    return value
            except (OSError, ValueError):
                pass
            if self.process and self.process.poll() is not None:
                break
            time.sleep(.05)
        self.log.flush()
        self.fail('Setup did not reach expected state:\n' + (self.folder / 'launch.log').read_text(errors='replace'))

    def browser_calls(self):
        return [json.loads(line) for line in self.browser_log.read_text().splitlines()] if self.browser_log.exists() else []

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.request('api/shutdown', {})
                self.process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True)
                else:
                    import signal
                    os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=8)

    def test_extracted_setup_saves_restarts_and_reuses_without_losing_data(self):
        self.process = subprocess.Popen(self.command('--settings', str(self.settings)), cwd=self.app, env=self.env,
                                        stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log, **self.flags)
        first = self.wait_for(lambda: (h if (h := self.request('api/health')).get('ready') else None))
        self.wait_for(self.browser_calls)
        self.assertEqual(self.browser_calls(), [self.base + 'setup/'])
        self.assertFalse(self.request('api/setup')['journal_found'])
        self.request('api/wishlist/add', {'item': 'iron', 'kind': 'material', 'qty': 7})
        wishlist = (self.data / 'engineering_wishlist.json').read_bytes()
        result = self.request('api/setup', {'journal_dir': str(self.journals)})
        self.assertTrue(result['restart_required'])
        saved = json.loads(self.settings.read_text())
        self.assertEqual(saved, {**self.original, 'journal_dir': str(self.journals)})
        self.request('api/restart', {})
        self.wait_for(lambda: (h if (h := self.request('api/health')).get('ready') and h['pid'] != first['pid'] else None))
        self.assertTrue(self.request('api/setup')['journal_found'])
        self.assertEqual(self.browser_calls(), [self.base + 'setup/'], 'Restart opened a duplicate tab')
        self.assertEqual((self.data / 'engineering_wishlist.json').read_bytes(), wishlist)
        second = subprocess.run(self.command('--settings', str(self.settings)), cwd=self.app, env=self.env,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, **self.flags)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn('Reusing it', second.stdout)
        self.assertEqual(self.browser_calls(), [self.base + 'setup/'] * 2)
        self.assertEqual(json.loads(self.settings.read_text()), saved)
        self.assertEqual((self.data / 'engineering_wishlist.json').read_bytes(), wishlist)
        self.request('api/shutdown', {})
        self.assertEqual(self.process.wait(timeout=10), 0)

    def test_busy_port_reports_error_without_opening_browser_or_changing_settings(self):
        with socket.socket() as busy:
            busy.bind(('127.0.0.1', self.port)); busy.listen()
            result = subprocess.run(self.command('--settings', str(self.settings)), cwd=self.app, env=self.env,
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15, **self.flags)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('could not listen', result.stdout + result.stderr)
        self.assertIn(str(self.settings), result.stdout + result.stderr)
        self.assertEqual(self.browser_calls(), [])
        self.assertEqual(json.loads(self.settings.read_text()), self.original)

    def test_missing_python_produces_installation_guidance(self):
        empty = self.folder / 'empty path'; empty.mkdir()
        env = dict(self.env, PATH=str(empty))
        if os.name != 'nt':
            (empty / 'dirname').symlink_to(shutil.which('dirname'))
        result = subprocess.run(self.command(), cwd=self.app, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10, **self.flags)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python 3.10 or newer was not found', result.stdout + result.stderr)
        self.assertIn('python.org', result.stdout + result.stderr)
        self.assertEqual(self.browser_calls(), [])

    @unittest.skipUnless(os.name == 'posix', 'POSIX interpreter selection')
    def test_old_python3_falls_back_to_supported_python(self):
        bins = self.folder / 'python candidates'; bins.mkdir()
        (bins / 'python3').write_text('#!/bin/sh\nexit 1\n', encoding='ascii')
        (bins / 'python3').chmod(0o755)
        (bins / 'python').symlink_to(sys.executable)
        env = dict(self.env, PATH=str(bins) + os.pathsep + self.env['PATH'])
        result = subprocess.run(self.command('--help'), cwd=self.app, env=env, capture_output=True, text=True,
                                timeout=10, **self.flags)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('--setup', result.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX interpreter selection')
    def test_only_old_interpreters_produce_guidance(self):
        bins = self.folder / 'old python'; bins.mkdir()
        (bins / 'dirname').symlink_to(shutil.which('dirname'))
        for name in ('python3', 'python'):
            p = bins / name; p.write_text('#!/bin/sh\nexit 1\n', encoding='ascii'); p.chmod(0o755)
        env = dict(self.env, PATH=str(bins))
        result = subprocess.run(self.command(), cwd=self.app, env=env, capture_output=True, text=True, timeout=10, **self.flags)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python 3.10 or newer', result.stderr)
