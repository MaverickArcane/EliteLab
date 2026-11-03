"""Console-free supervisor for the Windows portable bundle.

The dashboard owns the Quit action. Each supervisor only waits for its own
child and restarts it when setup requests a restart; it never kills another
instance or changes a running server's settings.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time


def notify(message):
    ctypes.windll.user32.MessageBoxW(None, message, 'EliteLab', 0x10)


def run(data_dir, settings_path, executable=None, popen=subprocess.Popen):
    """Run a child server, preserving the open window across setup restarts."""
    executable = executable or sys.executable
    logs = Path(data_dir) / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / ('desktop-' + str(os.getpid()) + '.log')
    first = ['--open-browser']
    if not Path(settings_path).is_file():
        first.append('--setup')
    recent_restarts = []
    with log_path.open('a', encoding='utf-8') as log:
        while True:
            cmd = [executable, '-m', 'elitelab', 'serve', *first]
            child = popen(cmd, stdin=subprocess.DEVNULL, stdout=log,
                          stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            status = child.wait()
            if status != 75:
                return status, log_path
            now = time.monotonic()
            recent_restarts = [t for t in recent_restarts if now - t < 30]
            recent_restarts.append(now)
            if len(recent_restarts) >= 5:
                log.write('Too many restart requests in 30 seconds; stopping.\n')
                return status, log_path
            first = ['--no-browser']


def main():
    try:
        from .core import config
        status, log_path = run(config.DATA_DIR, config.SETTINGS_PATH)
        if status:
            notify('EliteLab could not start or stopped unexpectedly. See the log for details:\n' + str(log_path))
        return status
    except Exception as error:
        notify('EliteLab could not start: ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
