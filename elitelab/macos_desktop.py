"""Private pipe bridge between the native menu bar and its own server child."""
import argparse
import importlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import urllib.request

from .macos_autostart import MacAutostart
from .tray_control import NoRedirect, TrayControl


def read_commands(stream, commands):
    try:
        while True:
            line = stream.readline(256)
            if not line or not line.endswith('\n'):
                break
            action = line.strip()
            if action not in ('open', 'setup', 'login', 'status', 'quit'):
                break
            commands.put(action)
    finally:
        commands.put('quit')


def emit(**message):
    print(json.dumps(message), flush=True)


def check_journal(control):
    """Read only our live child's loopback endpoint; never follow redirects."""
    url = control.verified_url()
    if not url:
        raise ValueError('The owned server is no longer ready')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    token = control.config.AUTH_TOKEN
    request = urllib.request.Request(url + 'api/journal',
        headers={'Authorization': 'Bearer ' + token} if token else {})
    with opener.open(request, timeout=5) as response:
        journal = json.loads(response.read(1024 * 1024))
    return {key: journal.get(key) for key in ('cmdr', 'system')}


def stop_child(control):
    """Gracefully stop only our child; reap it even if startup failed."""
    child = control.child
    if child is None or child.poll() is not None:
        return
    requested = control.shutdown()
    if not requested:
        child.terminate()
    try:
        child.wait(timeout=75 if requested else 10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=10)


def run(check=False):
    from .core import config
    control = TrayControl(config, refresh=lambda: importlib.reload(config), autostart_factory=MacAutostart)
    commands = queue.Queue(maxsize=16)
    if not check:
        threading.Thread(target=read_commands, args=(sys.stdin, commands), daemon=True).start()
    logs = Path(config.DATA_DIR) / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / ('desktop-' + str(os.getpid()) + '.log')
    # Never pass interpreter injection variables to the child server.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PYTHON')}
    restarts = []
    first = True
    with log_path.open('a', encoding='utf-8') as log:
        try:
            while True:
                args = ['--no-browser'] if check or not first else ['--open-browser']
                if first and not Path(config.SETTINGS_PATH).is_file():
                    args.append('--setup')
                child = subprocess.Popen([sys.executable, '-E', '-s', '-B', '-m', 'elitelab', 'serve', *args],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env)
                control.set_child(child)
                ready = False
                deadline = time.monotonic() + 60
                while child.poll() is None:
                    if not ready:
                        url = control.verified_url()
                        if url:
                            ready = True
                            emit(event='ready', url=url, pid=child.pid, login=control.autostart_status())
                            if check:
                                emit(event='check', journal=check_journal(control))
                                stop_child(control)
                                return child.returncode
                        elif time.monotonic() > deadline:
                            raise RuntimeError('Server did not become ready. See ' + str(log_path))
                    try:
                        action = commands.get(timeout=.1)
                    except queue.Empty:
                        continue
                    if action == 'quit':
                        stop_child(control)
                        return 0
                    try:
                        if action in ('open', 'setup'):
                            if not control.open(setup=action == 'setup'):
                                raise ValueError('The dashboard is not ready yet, or the browser could not open.')
                        elif action == 'login':
                            control.toggle_autostart()
                        emit(event='result', action=action, login=control.autostart_status())
                    except (OSError, ValueError) as error:
                        emit(event='error', message=str(error))
                if check and child.returncode != 75:
                    raise RuntimeError('Check did not start its own ready server. Quit any running EliteLab and retry. See ' + str(log_path))
                if child.returncode != 75:
                    if child.returncode:
                        raise RuntimeError('Server exited with status ' + str(child.returncode) + '. See ' + str(log_path))
                    return 0
                now = time.monotonic()
                restarts = [t for t in restarts if now - t < 30] + [now]
                if len(restarts) >= 5:
                    raise RuntimeError('Too many restart requests. See ' + str(log_path))
                control.config = importlib.reload(config)
                first = False
        finally:
            stop_child(control)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        return run(args.check)
    except Exception as error:
        try:
            emit(event='error', message=str(error))
        except OSError:
            pass
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
