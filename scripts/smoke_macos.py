"""Install, exercise, upgrade and remove a package on disposable macOS CI only."""
import argparse
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
APP = Path('/Applications/EliteLab.app')
IDENTIFIER = 'net.elitelab.desktop'


def smoke(package):
    if sys.platform != 'darwin' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Package installation/removal is restricted to disposable GitHub macOS runners')
    if APP.exists() or APP.is_symlink():
        raise RuntimeError('Refusing to replace a pre-existing EliteLab.app')
    package = Path(package).resolve()
    with tempfile.TemporaryDirectory(prefix='elitelab-macos-smoke-') as tmp:
        home = Path(tmp)
        settings = home / '.config/elitelab/settings.json'
        settings.parent.mkdir(parents=True)
        settings_bytes = b'{"future_setting": "preserve on upgrade"}\n'
        settings.write_bytes(settings_bytes)
        data = home / 'Library/Application Support/EliteLab'
        data.mkdir(parents=True)
        sentinel = data / 'upgrade-sentinel.json'
        sentinel.write_bytes(b'{"saved":true}\n')
        browser_log = home / 'browser.log'
        browser = home / 'browser recorder'
        browser.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$ELITELAB_TEST_BROWSER_LOG"\n', encoding='ascii')
        browser.chmod(0o755)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'LANG': 'en_US.UTF-8',
               'ELITELAB_INSTANCE_DIR': str(home / 'instance'), 'ELITELAB_HOST': '127.0.0.1',
               'ELITELAB_PORT': str(port), 'ELITELAB_OFFLINE': '1',
               'ELITELAB_JOURNAL_DIR': str(ROOT / 'tests/fixtures/journals'),
               'ELITELAB_BROWSER': str(browser), 'ELITELAB_TEST_BROWSER_LOG': str(browser_log)}
        source = APP / 'Contents/Resources/app'
        native = APP / 'Contents/MacOS/EliteLab'
        python = source / 'runtime/bin/python3'
        login = home / ('Library/LaunchAgents/' + IDENTIFIER + '.plist')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, body=None):
            req = urllib.request.Request(f'http://127.0.0.1:{port}' + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json'})
            with opener.open(req, timeout=5) as response:
                return json.load(response)

        def install():
            subprocess.run(['/usr/bin/sudo', '/usr/sbin/installer', '-pkg', str(package), '-target', '/'], check=True)

        process = None
        try:
            for cycle in range(2):
                install()
                subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(APP)], check=True)
                result = subprocess.run([str(native), '--check'], env=env, text=True, capture_output=True, timeout=100)
                assert result.returncode == 0, result.stdout + result.stderr
                messages = [json.loads(line) for line in result.stdout.splitlines()]
                assert any(m.get('event') == 'check' and m['journal'].get('cmdr') == 'Testpilot' for m in messages), messages
                process = subprocess.Popen([str(python), '-E', '-s', '-u', '-m', 'elitelab.macos_desktop'],
                    cwd=source, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                messages = queue.Queue()
                def collect(stream):
                    for line in stream:
                        messages.put(json.loads(line))
                reader = threading.Thread(target=collect, args=(process.stdout,), daemon=True)
                reader.start()
                def ready():
                    deadline = time.monotonic() + 70
                    while time.monotonic() < deadline:
                        message = messages.get(timeout=max(.1, deadline - time.monotonic()))
                        if message.get('event') == 'error':
                            raise AssertionError(message)
                        if message.get('event') == 'ready':
                            return message['pid']
                    raise AssertionError('Native backend never became ready')
                pid = ready()
                if cycle == 0:
                    request('/api/trade/plan', {'commodity': 'gold', 'source': 'Buy / Sol',
                        'destination': 'Sell / Lave', 'source_price': 100, 'destination_price': 300,
                        'target': 1000, 'planned_quantity': 1000})
                    assert request('/api/restart', {})['restarting']
                    assert ready() != pid, 'Supervisor did not replace the restarted child'
                assert request('/api/trade')['plan'].get('commodity') == 'gold'
                process.stdin.write('quit\n')
                process.stdin.flush()
                assert process.wait(timeout=85) == 0
                reader.join(timeout=5)
                process.stdin.close()
                process.stdout.close()
                assert settings.read_bytes() == settings_bytes
                assert sentinel.read_bytes() == b'{"saved":true}\n'
            # Native AppKit menu targets: enable/disable login, dashboard, setup, Quit.
            subprocess.run([str(native), '--ui-check'], env=env, check=True, timeout=100)
            assert not login.exists(), 'Login toggle did not remove its own entry'
            recorded = browser_log.read_text()
            assert f'--app=http://127.0.0.1:{port}/setup/' in recorded
            assert '--user-data-dir=' + str(data / 'browser') in recorded
            assert not (source / 'data').exists(), 'App wrote data inside its installation'
        finally:
            if process is not None and process.poll() is None:
                process.stdin.close()  # Parent EOF must also stop/reap the owned server.
                process.wait(timeout=85)
            # Fixed, preflight-checked path on a disposable runner; never user data.
            subprocess.run(['/usr/bin/sudo', '/bin/rm', '-rf', '/Applications/EliteLab.app'], check=True)
            subprocess.run(['/usr/bin/sudo', '/usr/sbin/pkgutil', '--forget', IDENTIFIER], check=True)
        assert not APP.exists()
        assert settings.read_bytes() == settings_bytes
        assert sentinel.read_bytes() == b'{"saved":true}\n'
        print('macOS native controls, fixture replay, restart, upgrade and removal passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    smoke(parser.parse_args().package)
