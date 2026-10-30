"""Cooperative restart and launcher exit-status contract, using isolated fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_elitelab import Core, config, ROOT


class RestartTests(unittest.TestCase):
    def run_server(self, restart):
        with tempfile.TemporaryDirectory() as data, patch.object(config, 'DATA_DIR', data):
            core = Core()
            result = []
            thread = threading.Thread(target=lambda: result.append(core.start('127.0.0.1', 0)), daemon=True)
            thread.start()
            try:
                deadline = time.monotonic() + 5
                while not core.ready and thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(core.ready)
                self.assertGreater(core._server.srv.server_port, 0)
                if restart:
                    core.request_restart()
                else:
                    core._server.stop()
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertEqual(result, [75 if restart else 0])
                self.assertFalse(core.ready)
            finally:
                if thread.is_alive():
                    core._server.stop()
                    thread.join(5)

    def test_restart_returns_75(self):
        self.run_server(True)

    def test_normal_stop_returns_zero(self):
        self.run_server(False)

    def test_settings_flag_is_applied_before_core_import(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text(json.dumps({'port': 8799}), encoding='utf-8')
            env = dict(os.environ)
            env.pop('ELITELAB_PORT', None)
            code = ('import sys; from elitelab.__main__ import main; '
                    'main(["--settings", sys.argv[1], "modules"]); '
                    'from elitelab.core import config; print("PORT", config.PORT)')
            run = subprocess.run([sys.executable, '-c', code, str(path)], cwd=ROOT,
                                 env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('PORT 8799', run.stdout)

    @unittest.skipUnless(os.name == 'posix', 'POSIX launcher')
    def test_shell_launcher_restarts_only_on_75(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / 'python3'
            fake.write_text('#!/bin/sh\necho call >> "$LAB_TEST_LOG"\n'
                            '[ "$(wc -l < "$LAB_TEST_LOG")" -eq 1 ] && exit "$LAB_TEST_FIRST"\nexit 0\n')
            fake.chmod(0o755)
            for first, count, status in ((75, 2, 0), (1, 1, 1), (76, 1, 76)):
                log = root / ('calls-' + str(first))
                env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                           LAB_TEST_LOG=str(log), LAB_TEST_FIRST=str(first))
                run = subprocess.run(['sh', str(Path(ROOT) / 'start.sh')], env=env, timeout=10)
                self.assertEqual(run.returncode, status)
                self.assertEqual(len(log.read_text().splitlines()), count)

    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_windows_launcher_restarts_only_on_75(self):
        with tempfile.TemporaryDirectory(prefix='EliteLab restart ') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            launcher = root / 'scripts' / 'serve-loop.cmd'
            launcher.write_bytes((Path(ROOT) / 'scripts' / 'serve-loop.cmd').read_bytes())
            (root / 'elitelab').mkdir()
            (root / 'elitelab' / '__main__.py').write_text(
                'import os, pathlib, sys\n'
                'p = pathlib.Path(os.environ["LAB_TEST_LOG"])\n'
                'first = not p.exists()\n'
                'with p.open("a") as f: f.write(" ".join(sys.argv[1:]) + "\\n")\n'
                'sys.exit(int(os.environ["LAB_TEST_FIRST"]) if first else 0)\n')
            for first, count, status in ((75, 2, 0), (1, 1, 1), (76, 1, 76)):
                log = root / ('calls-' + str(first))
                env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'],
                           LAB_TEST_LOG=str(log), LAB_TEST_FIRST=str(first))
                run = subprocess.run(['cmd', '/c', str(launcher), 'serve', '--port', '8799'],
                                     env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, status, run.stderr)
                self.assertEqual(log.read_text().splitlines(), ['--open-browser serve --port 8799'] * count)
