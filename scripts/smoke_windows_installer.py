"""Smoke-test a test-ID Windows installer in an isolated temporary directory.

Compile with a unique --app-id reserved for the test; never run this against a
release installer because setup and uninstall modify that ID's user registry.
"""
import argparse
import configparser
import hashlib
import json
import msvcrt
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import winreg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from elitelab.autostart import Autostart, RUN_KEY
from elitelab.window import installed_windows_browsers
from smoke_windows_desktop import smoke_shortcut


def smoke(installer):
    installer = Path(installer).resolve()
    metadata_path = installer.with_suffix(installer.suffix + '.build.json')
    metadata = json.loads(metadata_path.read_text(encoding='ascii'))
    app_id = metadata.get('app_id', '')
    if not app_id.startswith('EliteLab.Installer.Test.') or len(app_id) < 32:
        raise ValueError('installer must have a unique test application ID')
    group = 'EliteLab test ' + app_id
    if metadata.get('group') != group:
        raise ValueError('installer must have a unique compiled Start Menu group')
    if hashlib.sha256(installer.read_bytes()).hexdigest() != metadata.get('sha256'):
        raise ValueError('installer does not match its build metadata')
    with tempfile.TemporaryDirectory(prefix='EliteLab installer test ') as tmp:
        root = Path(tmp).resolve()
        app = root / 'Installed EliteLab'
        assert app.resolve().parent == root
        profile = root / 'Test user profile'
        instance = profile / '.elitelab'
        instance.mkdir(parents=True)
        lock_path = instance / 'instance.lock'
        lock_path.write_bytes(b' ')
        data = root / 'user-data'
        data.mkdir()
        sentinel = data / 'wishlist-test.json'
        sentinel.write_text('preserve', encoding='ascii')
        env = dict(os.environ)
        for key in list(env):
            if key.upper().startswith(('ELITELAB_', 'PYTHON')):
                del env[key]
        env['ELITELAB_HOST'] = '127.0.0.1'
        env['ELITELAB_OFFLINE'] = '1'
        env['ELITELAB_JOURNAL_DIR'] = str(Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'journals')
        # Exercise the ordinary launch path: no test-only instance override.
        # A private profile still keeps the guard away from the current user.
        env['USERPROFILE'] = str(profile)
        env['ELITELAB_DATA_DIR'] = str(data)
        env['ELITELAB_SETTINGS'] = str(root / 'settings.json')
        fallback_env = {k: v for k, v in env.items() if k.upper() != 'USERPROFILE'}
        fallback_env.update(HOMEDRIVE=profile.drive, HOMEPATH=str(profile)[len(profile.drive):])
        flags = subprocess.CREATE_NO_WINDOW
        startup = Autostart(app, value_name=app_id)
        # Resolve shell folders in the installer's private profile environment,
        # not the parent process's real user profile.
        programs = subprocess.check_output([sys.executable, '-c',
            'import ctypes; p = ctypes.create_unicode_buffer(32768); '
            'result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x4002, None, 0, p); '
            'assert result == 0, result; print(p.value)'],
            env={**env, 'PYTHONIOENCODING': 'utf-8'}, encoding='utf-8',
            creationflags=flags, timeout=15).strip()
        shortcut = Path(programs) / group / 'EliteLab.lnk'
        assert not shortcut.parent.exists(), 'Unique test shortcut folder already exists'
        # Inno ignores /GROUP when DisableProgramGroupPage=yes; the builder
        # embeds the unique group so even failed tests cannot touch a user's link.
        args = [str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                '/TASKS=', '/DIR=' + str(app)]
        try:
            for invalid in ('/APPBROWSER=calc.exe', '/BROWSERPROFILE=unexpected'):
                refused = subprocess.run(args + [invalid], env=env, creationflags=flags, timeout=90)
                assert refused.returncode != 0 and not app.exists(), 'Invalid browser choices must fail before installing'
            relative_env = {**env, 'ELITELAB_INSTANCE_DIR':'relative-instance'}
            refused = subprocess.run(args, env=relative_env, creationflags=flags, timeout=90)
            assert refused.returncode != 0 and not app.exists(), 'Relative guard paths must fail closed'
            missing_profile = {k: v for k, v in env.items() if k.upper() not in ('USERPROFILE', 'HOMEDRIVE', 'HOMEPATH')}
            refused = subprocess.run(args, env=missing_profile, creationflags=flags, timeout=90)
            assert refused.returncode != 0 and not app.exists(), 'Missing home must fail before installing'
            with lock_path.open('r+b', buffering=0) as guard:
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                for guard_env in (env, fallback_env, {**env, 'ELITELAB_INSTANCE_DIR': str(instance)}):
                    blocked = subprocess.run(args, env=guard_env, creationflags=flags, timeout=90)
                    assert blocked.returncode != 0 and not app.exists(), 'Installer must refuse a live instance'
                guard.seek(0); msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
            unrelated = root / 'Unrelated folder'
            unrelated.mkdir()
            unrelated_file = unrelated / 'keep.txt'
            unrelated_file.write_text('leave alone', encoding='ascii')
            unsafe_args = args[:-1] + ['/DIR=' + str(unrelated)]
            refused = subprocess.run(unsafe_args, env=env, creationflags=flags, timeout=90)
            assert refused.returncode != 0 and unrelated_file.read_text(encoding='ascii') == 'leave alone'
            assert not (unrelated / 'runtime').exists(), 'Installer must not overwrite an unrelated folder'
            setup_log = root / 'setup.log'
            installed = subprocess.run(args + ['/LOG=' + str(setup_log)], env=env, creationflags=flags, timeout=120)
            if installed.returncode:
                raise RuntimeError('Default-profile install failed: ' + setup_log.read_text(errors='replace')[-4000:])
            for name in ('runtime/pythonw.exe', '.windows-bundle', 'Launch EliteLab.vbs', 'elitelab/windows_tray.py'):
                assert (app / name).is_file(), name
            def browser_settings():
                saved = configparser.ConfigParser()
                saved.read(app / 'desktop-browser.ini', encoding='utf-8-sig')
                return dict(saved['Desktop'])
            choices = installed_windows_browsers()
            initial_browser = browser_settings()
            assert initial_browser['browser'] in choices and initial_browser['profile'] == 'guest', initial_browser
            assert not (root / 'settings.json').exists(), 'Installer browser choice must not skip first-run journal setup'
            assert shortcut.is_file(), 'Installer did not create the Start Menu shortcut at ' + str(shortcut) + '\n' + setup_log.read_text(errors='replace')[-4000:]
            smoke_shortcut(shortcut, app, env, root / 'shortcut-test')
            assert startup.status() == 'disabled', 'Unique test startup value already exists'
            startup.set_enabled(True)
            assert startup.status() == 'enabled'
            local_data = app / 'data'; local_data.mkdir()
            legacy = local_data / 'legacy-user-data.json'; legacy.write_text('keep', encoding='ascii')
            selected = next((name for name in choices if name != initial_browser['browser']), initial_browser['browser'])
            subprocess.run(args + ['/APPBROWSER=' + selected, '/BROWSERPROFILE=persistent'], env=fallback_env,
                           creationflags=flags, timeout=120, check=True)
            assert browser_settings() == {'browser': selected, 'profile': 'persistent'}
            subprocess.run(args, env=env, creationflags=flags, timeout=120, check=True)
            assert browser_settings() == {'browser': selected, 'profile': 'persistent'}
            # Start the installed embedded Python with a synthetic journal and no user data.
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
            base = f'http://127.0.0.1:{port}/'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with (root / 'installed-server.log').open('w', encoding='utf-8') as log:
                server = subprocess.Popen([str(app/'runtime'/'python.exe'), '-m', 'elitelab', 'serve',
                                           '--no-browser', '--port', str(port)], cwd=app, env=env,
                                          stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
                try:
                    deadline = time.monotonic() + 30
                    while True:
                        try:
                            with opener.open(base+'api/health', timeout=1) as response:
                                state = json.load(response)
                            if state.get('ready'): break
                        except (OSError, ValueError):
                            pass
                        if server.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError('Installed server did not become ready')
                        time.sleep(.1)
                    assert state.get('journal_found') and state.get('pid') == server.pid, state
                    request = urllib.request.Request(base+'api/shutdown', data=b'{}', headers={'Content-Type':'application/json'})
                    with opener.open(request, timeout=2) as response:
                        assert json.load(response).get('stopping') is True
                    assert server.wait(timeout=10) == 0
                finally:
                    if server.poll() is None:
                        server.terminate(); server.wait(timeout=10)
            assert sentinel.read_text(encoding='ascii') == 'preserve' and legacy.read_text(encoding='ascii') == 'keep'
            uninstaller = app / 'unins000.exe'
            assert uninstaller.is_file()
            uninstall = [str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART']
            runtime = app / 'runtime' / 'pythonw.exe'
            backup_runtime = app / 'runtime' / 'pythonw.test-backup'
            runtime.rename(backup_runtime)
            try:
                damaged = subprocess.run(uninstall, env=env, creationflags=flags, timeout=90)
                assert damaged.returncode != 0 and (app/'.windows-bundle').exists(), 'Uninstall must fail before removal when startup cleanup is unavailable'
                assert startup.status() == 'enabled', 'A failed uninstall must preserve sign-in settings'
            finally:
                backup_runtime.rename(runtime)
            # The failed uninstaller's clone may still hold the instance guard.
            deadline = time.monotonic() + 10
            while True:
                with lock_path.open('r+b', buffering=0) as guard:
                    try:
                        msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Failed uninstaller did not release the instance guard')
                    else:
                        guard.seek(0); msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
                        break
                time.sleep(.1)
            with lock_path.open('r+b', buffering=0) as guard:
                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                blocked = subprocess.run(uninstall, env=env, creationflags=flags, timeout=90)
                assert blocked.returncode != 0 and (app/'runtime'/'pythonw.exe').exists(), 'Uninstall must refuse a live instance'
                assert startup.status() == 'enabled', 'Blocked uninstall must not change sign-in settings'
                guard.seek(0); msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
            subprocess.run(uninstall, env=env, creationflags=flags, timeout=120, check=True)
            deadline = time.monotonic() + 10
            while (app/'runtime'/'pythonw.exe').exists() and time.monotonic() < deadline:
                time.sleep(.1)
            assert not (app/'runtime'/'pythonw.exe').exists(), 'Application was not removed'
            assert not shortcut.exists(), 'Uninstall retained the test Start Menu shortcut'
            assert startup.status() == 'disabled', 'Owned sign-in entry should be removed on uninstall'
            assert sentinel.read_text(encoding='ascii') == 'preserve' and legacy.read_text(encoding='ascii') == 'keep'
            # The uninstaller clone can briefly retain the guard after its
            # parent exits. Wait for the actual lock before the next install.
            deadline = time.monotonic() + 10
            while True:
                with lock_path.open('r+b', buffering=0) as guard:
                    try:
                        msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError('Uninstaller did not release the instance guard')
                    else:
                        guard.seek(0); msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)
                        break
                time.sleep(.1)
            # A different value in the unique test slot is not this installation's
            # entry; uninstall must leave it alone.
            second = root / 'Second test install'
            second_log = root / 'second-setup.log'
            second_args = args[:-1] + ['/DIR=' + str(second), '/LOG=' + str(second_log)]
            result = subprocess.run(second_args, env=env, creationflags=flags, timeout=120)
            if result.returncode:
                raise RuntimeError('Second test install failed: ' + second_log.read_text(errors='replace')[-4000:])
            foreign = 'synthetic-other-installation'
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, app_id, 0, winreg.REG_SZ, foreign)
            foreign_startup = Autostart(second, value_name=app_id)
            assert foreign_startup.status() == 'conflict'
            subprocess.run([str(second/'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                           env=env, creationflags=flags, timeout=120, check=True)
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                assert winreg.QueryValueEx(key, app_id)[0] == foreign, 'Uninstall removed a foreign startup entry'
                winreg.DeleteValue(key, app_id)
            print('Installer passed: browser selection and upgrade persistence, default user profile, home fallback, explicit guard override, running guard, install, upgrade, uninstall, user-data and startup-entry preservation.')
        finally:
            # This installer was built with a unique test ID and its target is
            # inside the temporary test directory. Remove its registry entry if
            # an earlier assertion failed after installation.
            uninstaller = app / 'unins000.exe'
            if uninstaller.is_file():
                subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                               env=env, creationflags=flags, timeout=120, check=False)
            startup.remove_owned()
            second_uninstaller = root / 'Second test install' / 'unins000.exe'
            if second_uninstaller.is_file():
                subprocess.run([str(second_uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                               env=env, creationflags=flags, timeout=120, check=False)
            # Remove only the synthetic value created by this test, never a
            # value another process may have placed in the same slot.
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
                    if winreg.QueryValueEx(key, app_id)[0] == 'synthetic-other-installation':
                        winreg.DeleteValue(key, app_id)
            except FileNotFoundError:
                pass



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    parser.add_argument('--test-id-confirmed', action='store_true', help='Confirm installer was built with a unique test application ID')
    args = parser.parse_args()
    if not args.test_id_confirmed:
        parser.error('build with a unique test app ID and pass --test-id-confirmed')
    if os.name != 'nt':
        parser.error('Windows is required')
    smoke(args.installer)
