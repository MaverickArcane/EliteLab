"""Console-free supervisor lifecycle and launch arguments."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from elitelab import desktop


class DesktopTests(unittest.TestCase):
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
        with patch('elitelab.desktop.run', return_value=(1, Path('error.log'))), patch('elitelab.desktop.notify') as notify:
            self.assertEqual(desktop.main(), 1)
        self.assertIn('error.log', notify.call_args.args[0])

    def test_unwritable_log_directory_reports_error(self):
        with patch('elitelab.desktop.run', side_effect=OSError('access denied')), patch('elitelab.desktop.notify') as notify:
            self.assertEqual(desktop.main(), 1)
        self.assertIn('access denied', notify.call_args.args[0])
