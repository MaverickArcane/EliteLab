"""Exercise staging isolation, diagnostic privacy and a real supervised server."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

from elitelab import staging


class StagingTests(unittest.TestCase):
    def test_inherited_live_configuration_cannot_escape_profile(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'ELITELAB_SETTINGS': 'live.json', 'ELITELAB_DATA_DIR': 'live-data',
            'ELITELAB_AUTH_TOKEN': 'private', 'ELITELAB_MODULES_DIR': 'old-modules',
            'ELITELAB_DISABLE': 'party', 'ELITELAB_HOST': '0.0.0.0'}):
            root = Path(tmp)
            env = staging.environment(root, root / 'journals', True)
            self.assertEqual(env['ELITELAB_SETTINGS'], str(root / 'settings.json'))
            self.assertEqual(env['ELITELAB_DATA_DIR'], str(root / 'data'))
            self.assertEqual(env['ELITELAB_INSTANCE_DIR'], str(root / 'instance'))
            self.assertEqual(env['ELITELAB_HOST'], '127.0.0.1')
            self.assertNotIn('ELITELAB_AUTH_TOKEN', env)
            self.assertNotIn('ELITELAB_MODULES_DIR', env)
            self.assertNotIn('ELITELAB_DISABLE', env)

    def test_bundle_is_bounded_allowlisted_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('settings.json', 'party.json', 'Journal.log', 'instance.lock'):
                (root / name).write_text('DO-NOT-EXPORT')
            secret = 'aB9_' * 8
            (root / 'staging.log').write_text('x' * (staging.LIMIT + 100) + '\nBearer ' + secret
                + '\ncode=' + secret + '\n' + str(Path.home()) + '\nhttps://host/?token=abc\n')
            run = staging.metadata()
            (root / 'run.json').write_text(json.dumps(run))
            first = staging.collect(root, 'Join failed ' + secret)
            second = staging.collect(root)
            self.assertNotEqual(first, second)
            with zipfile.ZipFile(first) as bundle:
                names = set(bundle.namelist())
                self.assertEqual(names, {'collector.json', 'run.json', 'problem.txt', 'READ-ME.txt', 'staging.log'})
                content = '\n'.join(bundle.read(n).decode() for n in names)
                for private in (secret, 'DO-NOT-EXPORT', str(Path.home()), 'https://host/'):
                    self.assertNotIn(private, content)
                self.assertEqual(json.loads(bundle.read('run.json'))['build'], run['build'])
                self.assertLessEqual(len(bundle.read('staging.log')), staging.LIMIT)

    def test_profile_cannot_traverse(self):
        with self.assertRaises(SystemExit):
            staging.main(['--profile', '../live', 'collect'])

    def test_real_server_collect_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journals = root / 'journals'
            journals.mkdir()
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            program = ('from pathlib import Path; from argparse import Namespace; from elitelab.staging import run; '
                       'import sys; sys.exit(run(Path(sys.argv[1]), Namespace(journals=Path(sys.argv[2]), '
                       'offline=True, no_browser=True, port=int(sys.argv[3]))))')
            with (root / 'console.txt').open('w') as console:
                process = subprocess.Popen([sys.executable, '-c', program, str(root), str(journals), str(port)],
                                           cwd=staging.ROOT, stdout=console, stderr=console)
                url = f'http://127.0.0.1:{port}'
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                try:
                    deadline = time.monotonic() + 20
                    while True:
                        try:
                            with opener.open(url + '/api/health', timeout=1) as response:
                                health = json.load(response)
                            break
                        except OSError:
                            if process.poll() is not None or time.monotonic() >= deadline:
                                self.fail((root / 'console.txt').read_text())
                            time.sleep(.1)
                    self.assertEqual(Path(health['journal_dir']), journals)
                    self.assertTrue((root / 'instance' / 'instance.lock').exists())
                    with zipfile.ZipFile(staging.collect(root, 'Live collection')) as bundle:
                        self.assertIn('staging.log', bundle.namelist())
                    request = urllib.request.Request(url + '/api/restart', data=b'{}',
                        headers={'Content-Type': 'application/json', 'Origin': url}, method='POST')
                    with opener.open(request, timeout=5):
                        pass
                    deadline = time.monotonic() + 20
                    while True:
                        log = (root / 'staging.log').read_text(encoding='utf-8')
                        if log.count('listening on') >= 2:
                            break
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail('Supervised restart failed: ' + log)
                        time.sleep(.1)
                    request = urllib.request.Request(url + '/api/shutdown', data=b'{}',
                        headers={'Content-Type': 'application/json', 'Origin': url}, method='POST')
                    with opener.open(request, timeout=5):
                        pass
                    self.assertEqual(process.wait(timeout=15), 0)
                    self.assertTrue(staging.collect(root, 'Stopped collection').is_file())
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
