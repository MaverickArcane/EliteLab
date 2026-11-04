"""Installed browser choice, app windows and profile isolation."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from elitelab import window


class WindowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.config = SimpleNamespace(ROOT=self.root, DATA_DIR=self.root / 'saved data', BROWSER='')
        self.settings = self.root / 'desktop-browser.ini'
        for name, result in [('installed_windows_browsers', {'chrome': 'Chrome executable', 'edge': 'Edge executable'}),
                             ('default_windows_browser', 'edge')]:
            patcher = patch('elitelab.window.' + name, return_value=result)
            patcher.start(); self.addCleanup(patcher.stop)

    def test_installed_choice_opens_guest_app_window_without_browser_fallback(self):
        self.settings.write_text('[Desktop]\nBrowser=chrome\nProfile=guest\n')
        with patch('elitelab.window.portable_windows', return_value=True), patch(
                'elitelab.window.subprocess.Popen') as launch, patch('elitelab.window.webbrowser.open') as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:1234/setup/', self.config))
        args = launch.call_args.args[0]
        self.assertEqual(args[0], 'Chrome executable')
        self.assertIn('--app=http://127.0.0.1:1234/setup/', args)
        self.assertIn('--guest', args)
        self.assertIn('--disable-sync', args)
        self.assertIn('--user-data-dir=' + str(self.config.DATA_DIR / 'browser-chrome'), args)
        self.assertNotIn('shell', launch.call_args.kwargs)
        fallback.assert_not_called()

    def test_explicit_persistent_profile_uses_separate_engine_folder(self):
        self.settings.write_text('[Desktop]\nBrowser=edge\nProfile=persistent\n')
        with patch('elitelab.window.portable_windows', return_value=True), patch('elitelab.window.subprocess.Popen') as launch:
            window.open_dashboard('http://127.0.0.1:1234/', self.config)
        args = launch.call_args.args[0]
        self.assertEqual(args[0], 'Edge executable')
        self.assertNotIn('--guest', args)
        self.assertIn('--user-data-dir=' + str(self.config.DATA_DIR / 'browser-edge'), args)

    def test_portable_default_prefers_supported_windows_default(self):
        self.assertEqual(window.windows_browser(self.config), ('edge', 'Edge executable', True))
        with patch('elitelab.window.default_windows_browser', return_value='firefox'):
            self.assertEqual(window.windows_browser(self.config), ('chrome', 'Chrome executable', True))

    def test_removed_selected_browser_never_silently_switches_to_a_tab(self):
        self.settings.write_text('[Desktop]\nBrowser=brave\nProfile=guest\n')
        with patch('elitelab.window.portable_windows', return_value=True), patch('elitelab.window.webbrowser.open') as fallback:
            with self.assertRaisesRegex(OSError, 'installer again'):
                window.open_dashboard('http://127.0.0.1:1234/', self.config)
        fallback.assert_not_called()

    def test_bad_settings_cannot_supply_an_executable_or_change_profile_policy(self):
        for value in ('[Desktop]\nBrowser=calc.exe', '[Desktop]\nBrowser=chrome\nProfile=unexpected', 'not ini'):
            with self.subTest(value=value):
                self.settings.write_text(value)
                with self.assertRaisesRegex(OSError, 'invalid'):
                    window.windows_browser(self.config)

    def test_custom_override_and_launch_failure_stay_in_app_mode(self):
        self.config.BROWSER = 'custom browser'
        with patch('elitelab.window.portable_windows', return_value=True), patch(
                'elitelab.window.subprocess.Popen', side_effect=OSError('missing')) as launch, patch(
                'elitelab.window.webbrowser.open') as fallback:
            with self.assertRaises(OSError):
                window.open_dashboard('http://127.0.0.1:1234/', self.config)
        self.assertEqual(launch.call_args.args[0][0], 'custom browser')
        self.assertIn('--guest', launch.call_args.args[0])
        fallback.assert_not_called()

    def test_source_checkout_keeps_standard_browser(self):
        with patch('elitelab.window.portable_windows', return_value=False), patch(
                'elitelab.window.subprocess.Popen') as launch, patch('elitelab.window.webbrowser.open', return_value=True) as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:1234/', self.config))
        launch.assert_not_called()
        fallback.assert_called_once()
