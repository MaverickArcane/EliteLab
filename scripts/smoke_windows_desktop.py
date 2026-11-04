"""Exercise native Windows tray messages against an isolated packaged server."""
import argparse
import ctypes
from ctypes import wintypes
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def wait_for(probe, message, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(message)


def browser_recorder(root):
    """Compile a tiny GUI-subsystem recorder; no console or real browser opens."""
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise OSError('Cannot find the Windows system directory')
    system = Path(buffer.value)
    source = root / 'browser.cs'
    source.write_text('using System; using System.IO; public class Recorder { [STAThread] public static void Main(string[] args) { '
        'File.AppendAllLines(Environment.GetEnvironmentVariable("ELITELAB_TEST_BROWSER_LOG"), args); } }', encoding='ascii')
    compiler = root / 'compile.ps1'
    compiler.write_text('param([string]$SourceFile, [string]$OutputFile)\n'
        '$ErrorActionPreference = "Stop"\n'
        'Add-Type -TypeDefinition (Get-Content -Raw -LiteralPath $SourceFile) -OutputAssembly $OutputFile -OutputType WindowsApplication\n', encoding='ascii')
    executable = root / 'browser recorder.exe'
    subprocess.run([str(system / 'WindowsPowerShell/v1.0/powershell.exe'), '-NoProfile', '-NonInteractive',
                    '-ExecutionPolicy', 'Bypass', '-File', str(compiler), str(source), str(executable)],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=45)
    return executable, system


def find_tray(app):
    """Find only the native window whose executable is this isolated bundle."""
    from elitelab import windows_tray as native
    enum_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    enumerate_windows = native.signature(native.user32, 'EnumWindows', wintypes.BOOL, enum_type, wintypes.LPARAM)
    class_name = native.signature(native.user32, 'GetClassNameW', ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    process_id = native.signature(native.user32, 'GetWindowThreadProcessId', wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    open_process = native.signature(native.kernel32, 'OpenProcess', wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    image_name = native.signature(native.kernel32, 'QueryFullProcessImageNameW', wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    close_handle = native.signature(native.kernel32, 'CloseHandle', wintypes.BOOL, wintypes.HANDLE)
    found = []
    @enum_type
    def visit(hwnd, unused):
        name = ctypes.create_unicode_buffer(256)
        class_name(hwnd, name, len(name))
        if name.value != 'EliteLabDesktopTray':
            return True
        pid = wintypes.DWORD()
        process_id(hwnd, ctypes.byref(pid))
        handle = open_process(0x00100000 | 0x1000, False, pid.value)
        if not handle:
            return True
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if image_name(handle, 0, path, ctypes.byref(size)) and Path(path.value).resolve() == (app / 'runtime/pythonw.exe').resolve():
            found.append((hwnd, handle, pid.value))
            return False
        close_handle(handle)
        return True
    enumerate_windows(visit, 0)
    return found[0] if found else None


def smoke_shortcut(shortcut, app, env, root):
    """Follow the installed .lnk and exercise its real supervisor's tray."""
    from elitelab import windows_tray as native
    root.mkdir()
    browser, system = browser_recorder(root)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    browser_log = root / 'browser.log'
    env = {**env, 'PATH': str(system), 'ELITELAB_PORT': str(port), 'ELITELAB_BROWSER': str(browser),
           'ELITELAB_TEST_BROWSER_LOG': str(browser_log)}
    check = root / 'shortcut.vbs'
    check.write_text('Option Explicit\nDim shell, link\nSet shell = CreateObject("WScript.Shell")\n'
        'Set link = shell.CreateShortcut(WScript.Arguments(0))\n'
        'If LCase(link.TargetPath) <> LCase(WScript.Arguments(1)) Then WScript.Quit 11\n'
        'If link.Arguments <> Chr(34) & WScript.Arguments(2) & Chr(34) Then WScript.Quit 12\n'
        'If LCase(link.WorkingDirectory) <> LCase(WScript.Arguments(3)) Then WScript.Quit 13\n'
        'shell.Run Chr(34) & WScript.Arguments(0) & Chr(34), 0, False\n', encoding='ascii')
    subprocess.run([str(system / 'cscript.exe'), '//Nologo', str(check), str(shortcut),
                    str(system / 'wscript.exe'), str(app / 'Launch EliteLab.vbs'), str(app)],
                   env=env, check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    close_handle = native.signature(native.kernel32, 'CloseHandle', wintypes.BOOL, wintypes.HANDLE)
    wait_process = native.signature(native.kernel32, 'WaitForSingleObject', wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
    tray = None
    try:
        tray = wait_for(lambda: find_tray(app), 'Start Menu shortcut did not create the installed tray')
        hwnd, handle, pid = tray
        base = f'http://127.0.0.1:{port}/'
        def lines():
            try:
                return browser_log.read_text().splitlines()
            except FileNotFoundError:
                return []
        wait_for(lambda: '--app=' + base + 'setup/' in lines(), 'Shortcut did not open first-run setup')
        native.post(hwnd, native.WM_COMMAND, 1, 0)
        wait_for(lambda: '--app=' + base in lines(), 'Installed tray did not open the dashboard')
        native.post(hwnd, native.WM_COMMAND, 3, 0)
        assert wait_process(handle, 15000) == 0, 'Installed tray did not finish quitting'
        print('Start Menu shortcut target, working directory, bundled runtime, first-run setup, dashboard and Quit passed')
    finally:
        if tray:
            if wait_process(tray[1], 0) != 0:
                # The process handle and executable identity were checked above.
                subprocess.run([str(system / 'taskkill.exe'), '/PID', str(tray[2]), '/T', '/F'],
                               creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, timeout=15)
            close_handle(tray[1])


def worker():
    # The embedded runtime's ._pth resolves these imports from the installed app.
    from elitelab import desktop
    from elitelab.core import config
    from elitelab.autostart import Autostart, RUN_KEY
    from elitelab.tray_control import TrayControl
    from elitelab import windows_tray as native
    import winreg

    name = 'EliteLab.Desktop.Test.' + uuid.uuid4().hex
    startup = Autostart(config.ROOT, value_name=name)
    control = TrayControl(config, refresh=lambda: importlib.reload(config),
                          autostart_factory=lambda root: Autostart(root, value_name=name))
    notifications = []
    tray = native.WindowsTray(control, notifications.append)
    finished = threading.Event()
    results = {}
    browser_log = Path(os.environ['ELITELAB_TEST_BROWSER_LOG'])
    state = native.signature(native.user32, 'GetMenuState', wintypes.UINT, wintypes.HMENU, wintypes.UINT, wintypes.UINT)
    count = native.signature(native.user32, 'GetMenuItemCount', ctypes.c_int, wintypes.HMENU)
    def menu_state():
        menu = tray._create_menu()
        try:
            assert count(menu) == 4
            return state(menu, 4, 0)
        finally:
            native.destroy_menu(menu)
    assert menu_state() == 0, 'Login must start unchecked'

    def supervise():
        try:
            results['server'] = desktop.run(config.DATA_DIR, config.SETTINGS_PATH, on_child=control.set_child)
        except BaseException as error:
            results['server_error'] = error
        finally:
            finished.set()
            tray.close()

    def command(number):
        assert native.post(tray.handle, native.WM_COMMAND, number, 0)

    def recorded():
        try:
            return browser_log.read_text().splitlines()
        except FileNotFoundError:
            return []

    def driver():
        try:
            url = wait_for(control.verified_url, 'Owned packaged server did not become ready')
            assert tray.icon_added
            wait_for(lambda: '--app=' + url + 'setup/' in recorded(), 'First launch did not open setup')
            command(1)
            wait_for(lambda: '--app=' + url in recorded(), 'Dashboard command did not reach the browser')
            before = recorded().count('--app=' + url + 'setup/')
            command(2)
            wait_for(lambda: recorded().count('--app=' + url + 'setup/') > before, 'Setup command did not reach the browser')
            assert '--user-data-dir=' + str(Path(config.DATA_DIR) / 'browser') in recorded()
            command(4)
            wait_for(lambda: startup.status() == 'enabled', 'Login menu did not enable the unique test entry')
            assert menu_state() & 0x0008, 'Enabled login must be checked'
            command(4)
            wait_for(lambda: startup.status() == 'disabled', 'Login menu did not remove its own entry')
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, 'synthetic-other-installation')
            assert menu_state() & 0x0003, 'Foreign login must disable the menu item'
            command(4)
            wait_for(lambda: notifications, 'Foreign entry conflict was not reported')
            assert startup.status() == 'conflict'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            notifications.clear()
            # Reproduce Explorer discarding its icon, then announcing a taskbar.
            assert native.notify_icon(native.NIM_DELETE, ctypes.byref(tray.icon))
            tray.icon_added = False
            native.post(tray.handle, tray.taskbar_created, 0, 0)
            wait_for(lambda: tray.icon_added, 'Tray icon did not recover after TaskbarCreated')
            original = control.child.pid
            request = urllib.request.Request(url + 'api/restart', data=b'{}', headers={'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=3) as response:
                assert json.load(response)['restarting']
            wait_for(lambda: control.child.pid != original and control.verified_url(), 'Tray did not follow the restarted child')
            command(3)
            assert finished.wait(15), 'Native Quit did not stop the owned server'
            assert results.get('server', (None,))[0] == 0, results
            assert not notifications, notifications
            results['passed'] = True
        except BaseException as error:
            results['driver_error'] = error
        finally:
            if not finished.is_set():
                control.shutdown()
                if not finished.wait(10) and control.child and control.child.poll() is None:
                    control.child.terminate()
            tray.close()

    supervisor = threading.Thread(target=supervise, name='desktop-smoke-supervisor')
    test = threading.Thread(target=driver, name='desktop-smoke-driver')
    supervisor.start()
    test.start()
    try:
        tray.loop()
        test.join(timeout=45)
        supervisor.join(timeout=15)
        for key in ('driver_error', 'server_error'):
            if key in results:
                raise results[key]
        assert results.get('passed') and not test.is_alive() and not supervisor.is_alive(), results
    finally:
        startup.remove_owned()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            try:
                if winreg.QueryValueEx(key, name)[0] == 'synthetic-other-installation':
                    winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    print('Native Windows tray: first-run setup, dashboard, login ownership, icon recovery, restart and Quit passed')


def smoke(app):
    if os.name != 'nt':
        raise RuntimeError('Windows desktop check requires Windows')
    app = Path(app).resolve()
    if not (app / '.windows-bundle').is_file():
        raise ValueError('Expected an extracted Windows bundle')
    with tempfile.TemporaryDirectory(prefix='EliteLab native desktop ') as tmp:
        root = Path(tmp)
        browser, system = browser_recorder(root)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if k.upper() in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC')}
        env.update(PATH=str(system), USERPROFILE=str(root), LOCALAPPDATA=str(root / 'local'), APPDATA=str(root / 'roaming'),
                   ELITELAB_SETTINGS=str(root / 'settings.json'), ELITELAB_DATA_DIR=str(root / 'data'),
                   ELITELAB_INSTANCE_DIR=str(root / 'instance'), ELITELAB_HOST='127.0.0.1', ELITELAB_PORT=str(port),
                   ELITELAB_OFFLINE='1', ELITELAB_JOURNAL_DIR=str(ROOT / 'tests/fixtures/journals'),
                   ELITELAB_BROWSER=str(browser), ELITELAB_TEST_BROWSER_LOG=str(root / 'browser.log'))
        with (root / 'worker.log').open('w') as log:
            result = subprocess.run([str(app / 'runtime/python.exe'), str(Path(__file__).resolve()), '--worker'],
                cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=150, creationflags=subprocess.CREATE_NO_WINDOW)
        output = (root / 'worker.log').read_text(errors='replace')
        print(output)
        if result.returncode:
            for log in (root / 'data/logs').glob('desktop-*.log'):
                print(log.read_text(errors='replace')[-6000:])
            raise RuntimeError('Native desktop smoke failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', nargs='?')
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    worker() if args.worker else smoke(args.app)
