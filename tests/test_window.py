"""Portable window launch and fallback behavior."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from elitelab import window

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(ROOT='app', DATA_DIR='data folder', BROWSER='')

    def test_portable_launch_uses_argument_list_and_separate_profile(self):
        self.config.BROWSER = 'browser executable'
        with patch('elitelab.window.portable_windows', return_value=True), patch(
                'elitelab.window.browser_candidates', return_value=['browser executable']), patch(
                'elitelab.window.subprocess.Popen') as process, patch('elitelab.window.webbrowser.open') as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:1234/setup/', self.config))
        args = process.call_args.args[0]
        self.assertEqual(args[0], 'browser executable')
        self.assertIn('--app=http://127.0.0.1:1234/setup/', args)
        self.assertIn('--user-data-dir=' + str(window.Path('data folder') / 'browser'), args)
        fallback.assert_not_called()

    def test_discovery_lists_only_installed_browsers_with_stable_ids(self):
        with patch.dict(window.os.environ, {'PROGRAMFILES': 'programs', 'PROGRAMFILES(X86)': '', 'LOCALAPPDATA': ''}, clear=True), patch(
                'elitelab.window.os.name', 'nt'), patch(
                'elitelab.window.os.path.isfile', side_effect=lambda p: 'Firefox' in p or 'Chrome' in p):
            candidates = window.installed_browsers()
            options = window.browser_options()
        self.assertEqual(set(candidates), {'chrome', 'firefox'})
        self.assertEqual(options[0], {'id': 'default', 'label': 'Windows default'})
        self.assertEqual([o['id'] for o in options], ['default', 'chrome', 'firefox'])
        self.assertTrue(all(set(o) == {'id', 'label'} for o in options))

    def test_default_does_not_discover_launch_or_create_a_browser_profile(self):
        with patch('elitelab.window.installed_browsers') as discovery, patch(
                'elitelab.window.subprocess.Popen') as process, patch(
                'elitelab.window.webbrowser.open', return_value=True) as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:8766/', self.config))
        discovery.assert_not_called()
        process.assert_not_called()
        fallback.assert_called_once_with('http://127.0.0.1:8766/')

    def test_selected_browser_opens_only_the_url_without_profile_or_app_flags(self):
        self.config.BROWSER_CHOICE = 'firefox'
        with patch('elitelab.window.installed_browsers', return_value={'firefox': 'Firefox with spaces'}), patch(
                'elitelab.window.subprocess.Popen') as process, patch('elitelab.window.webbrowser.open') as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:8766/setup/', self.config))
        process.assert_called_once_with(['Firefox with spaces', 'http://127.0.0.1:8766/setup/'], close_fds=True)
        fallback.assert_not_called()

    def test_removed_invalid_or_failed_selection_falls_back_to_default(self):
        for choice, installed in [('chrome', {}), ('calc.exe', {}), ('chrome', {'chrome': 'broken'})]:
            with self.subTest(choice=choice, installed=installed):
                self.config.BROWSER_CHOICE = choice
                with patch('elitelab.window.installed_browsers', return_value=installed), patch(
                        'elitelab.window.subprocess.Popen', side_effect=OSError('missing')), patch(
                        'elitelab.window.webbrowser.open', return_value=True) as fallback:
                    self.assertTrue(window.open_dashboard('http://127.0.0.1:8766/', self.config))
                fallback.assert_called_once_with('http://127.0.0.1:8766/')

    def test_unavailable_browser_falls_back_without_shell(self):
        self.config.BROWSER = 'bad executable'
        with patch('elitelab.window.portable_windows', return_value=True), patch(
                'elitelab.window.subprocess.Popen', side_effect=OSError('missing')) as process, patch(
                'elitelab.window.webbrowser.open', return_value=True) as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:8766/', self.config))
        self.assertEqual(process.call_args.args[0][0], 'bad executable')
        self.assertNotIn('shell', process.call_args.kwargs)
        fallback.assert_called_once_with('http://127.0.0.1:8766/')

    def test_source_checkout_keeps_standard_browser(self):
        with patch('elitelab.window.portable_windows', return_value=False), patch(
                'elitelab.window.subprocess.Popen') as process, patch('elitelab.window.webbrowser.open', return_value=True) as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:8766/', self.config))
        process.assert_not_called()
        fallback.assert_called_once()
