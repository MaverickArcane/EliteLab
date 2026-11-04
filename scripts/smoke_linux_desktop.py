"""Run real GTK controls and a packaged server under a disposable Xvfb display."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def smoke(app, screenshots):
    app = Path(app).resolve()
    if not (app / '.linux-package').is_file():
        raise ValueError('Pass the application directory from an extracted Debian package')
    screenshots = Path(screenshots).resolve()
    screenshots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='elitelab-gtk-') as tmp:
        root = Path(tmp)
        browser = root / 'browser recorder'
        browser.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\n'
                           'Path(' + repr(str(root / 'browser.json')) + ').write_text(json.dumps(sys.argv[1:]))\n')
        browser.chmod(0o755)
        # Preserve only the disposable graphical session, not interpreter,
        # loader or application overrides from the invoking environment.
        session_keys = ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                        'XDG_RUNTIME_DIR', 'GDK_BACKEND', 'LANG', 'LC_ALL')
        env = {key:os.environ[key] for key in session_keys if key in os.environ}
        env.update(PATH=os.defpath, GSETTINGS_BACKEND='memory')
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        env.update(HOME=tmp, XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
                   ELITELAB_SETTINGS=str(root / 'settings.json'), ELITELAB_INSTANCE_DIR=str(root / 'instance'),
                   ELITELAB_OFFLINE='1', ELITELAB_JOURNAL_DIR=str(ROOT / 'tests/fixtures/journals'),
                   ELITELAB_HOST='127.0.0.1', ELITELAB_PORT=str(port))
        (root / 'settings.json').write_text(json.dumps({'browser':str(browser)}))
        os.environ.clear()
        os.environ.update(env)
        sys.path.insert(0, str(app))
        from elitelab.core import config
        from elitelab.tray_control import TrayControl
        from elitelab.linux_autostart import LinuxAutostart
        from elitelab.linux_tray import LinuxTray
        import gi
        gi.require_version('Gdk', '3.0')
        from gi.repository import Gdk, GLib, Gio
        watcher_xml = '''<node><interface name="org.kde.StatusNotifierWatcher">
          <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
          <property name="ProtocolVersion" type="i" access="read"/>
          <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
          <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
        </interface></node>'''
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        info = Gio.DBusNodeInfo.new_for_xml(watcher_xml)
        def method(_bus, _sender, _path, _iface, _method, _params, invocation):
            invocation.return_value(GLib.Variant('()', ()))
        def prop(_bus, _sender, _path, _iface, name):
            return {'ProtocolVersion':GLib.Variant('i', 0),
                    'IsStatusNotifierHostRegistered':GLib.Variant('b', True),
                    'RegisteredStatusNotifierItems':GLib.Variant('as', [])}[name]
        registration = bus.register_object('/StatusNotifierWatcher', info.interfaces[0], method, prop, None)
        owner = None
        with (root / 'server.log').open('w') as log:
            child = subprocess.Popen([sys.executable, '-m', 'elitelab', 'serve', '--no-browser'],
                                     cwd=app, env=env, stdout=log, stderr=log, shell=False)
            try:
                control = TrayControl(config, autostart_factory=LinuxAutostart)
                control.set_child(child)
                deadline = time.monotonic() + 30
                while not control.verified_url():
                    if child.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError((root / 'server.log').read_text())
                    time.sleep(.1)
                tray = LinuxTray(control, lambda message: None)
                errors = []
                stage = 0
                deadline = time.monotonic() + 20
                def tick():
                    nonlocal stage, owner
                    try:
                        assert time.monotonic() < deadline, 'GTK action timed out'
                        if stage == 0:
                            assert tray.window.get_visible(), 'No indicator host: fallback controls must remain visible'
                            drawable = tray.window.get_window()
                            width, height = tray.window.get_size()
                            shot = Gdk.pixbuf_get_from_window(drawable, 0, 0, width, height)
                            assert shot is not None
                            shot.savev(str(screenshots / 'linux-controls.png'), 'png', [], [])
                            assert control.autostart_status() == 'disabled'
                            tray.startup_button.clicked()
                            assert control.autostart_status() == 'enabled'
                            tray.startup_button.clicked()
                            assert control.autostart_status() == 'disabled'
                            tray._delete()
                            assert tray.window.get_visible()
                            tray.buttons['Open setup'].clicked()
                            stage = 1
                        elif stage == 1 and (root / 'browser.json').exists() and not tray.busy:
                            args = json.loads((root / 'browser.json').read_text())
                            assert '--app=' + control.verified_url() + 'setup/' in args
                            assert '--user-data-dir=' + str(Path(config.DATA_DIR) / 'browser') in args
                            # A foreign login entry is visibly unavailable and is not replaced.
                            setting = LinuxAutostart(config.ROOT)
                            setting.path.write_text('foreign entry')
                            tray._startup_label()
                            assert not tray.startup_button.get_sensitive()
                            assert setting.path.read_text() == 'foreign entry'
                            assert tray.indicator is not None, 'Packaged Ayatana indicator failed to initialize'
                            owner = Gio.bus_own_name_on_connection(bus, 'org.kde.StatusNotifierWatcher', Gio.BusNameOwnerFlags.NONE, None, None)
                            stage = 2
                        elif stage == 2 and tray.indicator.get_property('connected'):
                            assert not tray.window.get_visible(), 'Connected indicator must replace fallback window'
                            Gio.bus_unown_name(owner)
                            owner = None
                            stage = 3
                        elif stage == 3 and not tray.indicator.get_property('connected'):
                            assert tray.window.get_visible(), 'Losing the indicator host must restore controls'
                            tray.buttons['Quit EliteLab'].clicked()
                            stage = 4
                        elif stage == 4 and child.poll() is not None:
                            assert child.returncode == 0
                            tray.close()
                            return False
                    except Exception as error:
                        errors.append(error)
                        tray.close()
                        return False
                    return True
                GLib.timeout_add(100, tick)
                tray.loop()
                if errors:
                    raise errors[0]
                assert stage == 4
            finally:
                if owner is not None:
                    Gio.bus_unown_name(owner)
                bus.unregister_object(registration)
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
    print('Linux GTK fallback, indicator connect/disconnect, setup app window arguments, login ownership and verified server shutdown passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app')
    parser.add_argument('--screenshots', default='linux-desktop-screenshots')
    args = parser.parse_args()
    smoke(args.app, args.screenshots)
