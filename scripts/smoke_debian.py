"""Exercise an extracted Debian package without installing it on the host."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def smoke(package):
    with tempfile.TemporaryDirectory(prefix='elitelab-deb-smoke-') as tmp:
        root = Path(tmp)
        subprocess.run(['dpkg-deb', '-x', str(Path(package).resolve()), str(root / 'extract')], check=True)
        app = root / 'extract/usr/lib/elitelab'
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('ELITELAB_', 'PYTHON'))}
        env.update(HOME=str(root), XDG_DATA_HOME=str(root / 'data'), XDG_CONFIG_HOME=str(root / 'config'),
                   ELITELAB_INSTANCE_DIR=str(root / 'instance'), ELITELAB_HOST='127.0.0.1',
                   ELITELAB_OFFLINE='1', ELITELAB_JOURNAL_DIR=str(ROOT / 'tests/fixtures/journals'))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type': 'application/json'})
            with opener.open(req, timeout=2) as response:
                return json.load(response)

        def start():
            log = (root / 'server.log').open('a', encoding='utf-8')
            process = subprocess.Popen([sys.executable, '-m', 'elitelab', 'serve', '--no-browser', '--port', str(port)],
                                       cwd=app, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
            log.close()
            return process

        process = None
        try:
            for cycle in range(2):
                process = start()
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError((root / 'server.log').read_text(errors='replace'))
                    try:
                        health = request('/api/health')
                        journal = request('/api/journal')
                        if health.get('ready') and journal.get('cmdr') == 'Testpilot':
                            break
                    except (OSError, ValueError):
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError('Extracted server did not replay the fixture journal')
                assert health['pid'] == process.pid
                assert (root / 'data/elitelab').is_dir(), 'Package must use its XDG data directory'
                if cycle == 0:
                    request('/api/trade/plan', {'commodity': 'gold', 'source': 'Buy / Sol',
                        'destination': 'Sell / Lave', 'source_price': 100, 'destination_price': 300,
                        'target': 1000, 'planned_quantity': 1000})
                    saved = {p.relative_to(root / 'data'): p.read_bytes() for p in (root / 'data').rglob('*') if p.is_file()}
                    assert saved, 'Application did not persist data'
                    assert request('/api/restart', {})['restarting']
                    assert process.wait(timeout=10) == 75
                else:
                    assert all((root / 'data' / p).is_file() for p in saved), 'Restart lost persisted files'
                    assert request('/api/shutdown', {})['stopping']
                    assert process.wait(timeout=10) == 0
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    print('Extracted Debian package replay, persistence and restart passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    smoke(parser.parse_args().package)
