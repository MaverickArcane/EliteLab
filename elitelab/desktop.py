"""Console-free supervisor for the Windows portable bundle.

The dashboard owns the Quit action. Each supervisor only waits for its own
child and restarts it when setup requests a restart; it never kills another
instance or changes a running server's settings.
"""
import ctypes
import importlib
import os
from pathlib import Path
import subprocess
import sys
import time
import threading


def notify(message):
    ctypes.windll.user32.MessageBoxW(None, message, 'EliteLab', 0x10)


def run(data_dir, settings_path, executable=None, popen=subprocess.Popen, on_child=None):
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
            if on_child:
                on_child(child)
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


def tray_enabled():
    return os.name == 'nt'


def tray_main(config):
    from .tray_control import TrayControl
    from .windows_tray import WindowsTray
    control = TrayControl(config, refresh=lambda: importlib.reload(config))
    try:
        tray = WindowsTray(control, notify)
    except OSError as error:
        notify('The tray icon could not start. Use Quit in the dashboard to stop EliteLab. ' + str(error))
        return run(config.DATA_DIR, config.SETTINGS_PATH)
    result = {}
    finished = threading.Event()
    def supervise():
        try:
            result['value'] = run(config.DATA_DIR, config.SETTINGS_PATH, on_child=control.set_child)
        except Exception as error:
            result['error'] = error
        finally:
            finished.set()
            tray.close()
    worker = threading.Thread(target=supervise, name='desktop-supervisor')
    worker.start()
    failed = False
    try:
        tray.loop()
    except Exception as error:
        failed = True
        notify('The tray stopped. Use Quit in the dashboard to stop EliteLab. ' + str(error))
    if not finished.is_set() and not failed:
        notify('The tray closed. Use Quit in the dashboard to stop EliteLab.')
    if worker.is_alive():
        worker.join()
    if 'error' in result:
        raise result['error']
    return result['value']


def main():
    try:
        from .core import config
        status, log_path = tray_main(config) if tray_enabled() else run(config.DATA_DIR, config.SETTINGS_PATH)
        if status:
            notify('EliteLab could not start or stopped unexpectedly. See the log for details:\n' + str(log_path))
        return status
    except Exception as error:
        notify('EliteLab could not start: ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
