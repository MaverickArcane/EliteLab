"""Exercise the tray control against a real isolated local server."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from elitelab.tray_control import TrayControl


class TrayIntegrationTests(unittest.TestCase):
    def test_tray_only_stops_its_own_authenticated_server(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='elitelab-tray-test-') as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            instance = str(Path(tmp) / 'instance')
            env = {**os.environ, 'ELITELAB_INSTANCE_DIR':instance, 'ELITELAB_DATA_DIR':str(Path(tmp)/'data'),
                   'ELITELAB_SETTINGS':str(Path(tmp)/'settings.json'), 'ELITELAB_AUTH_TOKEN':'tray-fixture-token',
                   'ELITELAB_OFFLINE':'1', 'ELITELAB_JOURNAL_DIR':str(root/'tests'/'fixtures'/'journals')}
            flags = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            with open(Path(tmp)/'server.log', 'w+', encoding='utf-8') as log:
                child = subprocess.Popen([sys.executable, '-m', 'elitelab', 'serve', '--no-browser', '--port', str(port)],
                                         cwd=root, env=env, stdout=log, stderr=log, **flags)
                try:
                    control = TrayControl(SimpleNamespace(AUTH_TOKEN='tray-fixture-token'))
                    control.set_child(child)
                    with patch.dict(os.environ, {'ELITELAB_INSTANCE_DIR':instance}):
                        deadline = time.monotonic() + 20
                        while time.monotonic() < deadline and not control.verified_url():
                            if child.poll() is not None:
                                log.seek(0); self.fail(log.read())
                            time.sleep(.1)
                        self.assertEqual(control.verified_url(), f'http://127.0.0.1:{port}/')
                        other = TrayControl(SimpleNamespace(AUTH_TOKEN='tray-fixture-token'))
                        other.set_child(SimpleNamespace(pid=child.pid + 1, poll=lambda:None))
                        self.assertFalse(other.shutdown())
                        self.assertIsNone(child.poll())
                        self.assertTrue(control.shutdown())
                    self.assertEqual(child.wait(timeout=10), 0)
                finally:
                    if child.poll() is None:
                        child.terminate(); child.wait(timeout=10)
