"""Console-free supervisor lifecycle and launch arguments."""
from pathlib import Path
import tempfile
import unittest
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch
from elitelab import desktop


class DesktopTests(unittest.TestCase):
    def test_linux_package_selects_linux_controls_and_login_backend(self):
        closed = threading.Event()
        captured = []
        class FakeTray:
            def __init__(self, control, notify): captured.append(control)
            def close(self): closed.set()
            def loop(self):
                if not closed.wait(2): raise RuntimeError('tray was not closed')
        config = SimpleNamespace(DATA_DIR='unused', SETTINGS_PATH='unused')
        from elitelab.linux_autostart import LinuxAutostart
        with patch('elitelab.desktop.linux_package', return_value=True), patch.dict(sys.modules, {'elitelab.linux_tray':SimpleNamespace(LinuxTray=FakeTray)}), patch('elitelab.desktop.run', return_value=(0, Path('log'))):
            self.assertEqual(desktop.tray_main(config), (0, Path('log')))
        self.assertIs(captured[0].autostart_factory, LinuxAutostart)

    def test_first_run_opens_setup_and_restart_does_not_open_another_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            children = [Mock(wait=Mock(return_value=75)), Mock(wait=Mock(return_value=0))]
            popen = Mock(side_effect=children)
            status, log = desktop.run(Path(tmp) / 'data', Path(tmp) / 'missing.json', executable='pythonw', popen=popen)
            self.assertEqual(status, 0)
            self.assertTrue(log.exists())
        self.assertEqual(popen.call_args_list[0].args[0], ['pythonw', '-m', 'elitelab', 'serve', '--open-browser', '--setup'])
        self.assertEqual(popen.call_args_list[1].args[0], ['pythonw', '-m', 'elitelab', 'serve', '--no-browser'])
        self.assertNotIn('shell', popen.call_args.kwargs)

    def test_existing_settings_open_dashboard_and_failure_returns_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / 'settings.json'
            settings.write_text('{}', encoding='ascii')
            popen = Mock(return_value=Mock(wait=Mock(return_value=1)))
            status, log = desktop.run(Path(tmp) / 'data', settings, executable='pythonw', popen=popen)
            self.assertEqual(status, 1)
            self.assertTrue(log.exists())
            self.assertEqual(popen.call_args.args[0][-1], '--open-browser')

    def test_restart_loop_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            popen = Mock(return_value=Mock(wait=Mock(return_value=75)))
            status, log = desktop.run(Path(tmp) / 'data', Path(tmp) / 'missing.json', executable='pythonw', popen=popen)
            self.assertEqual(status, 75)
            self.assertEqual(popen.call_count, 5)
            self.assertIn('Too many restart requests', log.read_text(encoding='utf-8'))

    def test_start_failure_reports_log_location(self):
        with patch('elitelab.desktop.tray_enabled', return_value=False), patch('elitelab.desktop.run', return_value=(1, Path('error.log'))), patch('elitelab.desktop.notify') as notify:
            self.assertEqual(desktop.main(), 1)
        self.assertIn('error.log', notify.call_args.args[0])

    def test_unwritable_log_directory_reports_error(self):
        with patch('elitelab.desktop.tray_enabled', return_value=False), patch('elitelab.desktop.run', side_effect=OSError('access denied')), patch('elitelab.desktop.notify') as notify:
            self.assertEqual(desktop.main(), 1)
        self.assertIn('access denied', notify.call_args.args[0])

    def test_supervisor_reports_each_child_during_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            children = [Mock(wait=Mock(return_value=75)), Mock(wait=Mock(return_value=0))]
            popen = Mock(side_effect=children)
            seen = []
            desktop.run(Path(tmp) / 'data', Path(tmp) / 'missing', executable='pythonw', popen=popen, on_child=seen.append)
            self.assertEqual(seen, children)

    def test_tray_supervisor_closes_icon_after_child_exits(self):
        closed = threading.Event()
        class FakeTray:
            def __init__(self, control, notify): self.control = control
            def close(self): closed.set()
            def loop(self): self.assert_closed()
            def assert_closed(self):
                if not closed.wait(2): raise RuntimeError('tray was not closed')
        fake_module = SimpleNamespace(WindowsTray=FakeTray)
        config = SimpleNamespace(DATA_DIR='unused', SETTINGS_PATH='unused')
        def run(*args, **kwargs):
            kwargs['on_child'](SimpleNamespace(pid=123))
            return (0, Path('log'))
        with patch.dict(sys.modules, {'elitelab.windows_tray':fake_module}), patch('elitelab.desktop.run', side_effect=run), patch('elitelab.desktop.notify') as notify:
            self.assertEqual(desktop.tray_main(config), (0, Path('log')))
        notify.assert_not_called()

    def test_tray_failure_falls_back_to_dashboard_controls(self):
        fake_module = SimpleNamespace(WindowsTray=Mock(side_effect=OSError('no tray')))
        config = SimpleNamespace(DATA_DIR='data', SETTINGS_PATH='settings')
        with patch.dict(sys.modules, {'elitelab.windows_tray':fake_module}), patch('elitelab.desktop.run', return_value=(0, Path('log'))) as run, patch('elitelab.desktop.notify') as notify:
            self.assertEqual(desktop.tray_main(config), (0, Path('log')))
        run.assert_called_once_with('data','settings')
        self.assertIn('dashboard', notify.call_args.args[0])
