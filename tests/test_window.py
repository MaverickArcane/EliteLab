"""Portable window launch and fallback behavior."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from elitelab import window

class WindowTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(ROOT='app', DATA_DIR='data folder', BROWSER='')

    def test_portable_launch_uses_argument_list_and_separate_profile(self):
        with patch('elitelab.window.portable_windows', return_value=True), patch(
                'elitelab.window.browser_candidates', return_value=['browser executable']), patch(
                'elitelab.window.subprocess.Popen') as process, patch('elitelab.window.webbrowser.open') as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:1234/setup/', self.config))
        args = process.call_args.args[0]
        self.assertEqual(args[0], 'browser executable')
        self.assertIn('--app=http://127.0.0.1:1234/setup/', args)
        self.assertIn('--user-data-dir=' + str(window.Path('data folder') / 'browser'), args)
        fallback.assert_not_called()

    def test_discovery_uses_known_folders_in_browser_order(self):
        with patch.dict(window.os.environ, {'PROGRAMFILES': 'programs', 'PROGRAMFILES(X86)': '', 'LOCALAPPDATA': ''}, clear=True), patch(
                'elitelab.window.os.path.isfile', return_value=True):
            candidates = window.browser_candidates()
        self.assertIn('msedge.exe', candidates[0])
        self.assertIn('Chrome', candidates[1])
        self.assertEqual(len(candidates), 4)

    def test_tries_the_next_installed_browser_after_launch_failure(self):
        with patch('elitelab.window.portable_windows', return_value=True), patch(
                'elitelab.window.browser_candidates', return_value=['broken', 'working']), patch(
                'elitelab.window.subprocess.Popen', side_effect=[OSError('missing'), object()]) as process, patch(
                'elitelab.window.webbrowser.open') as fallback:
            self.assertTrue(window.open_dashboard('http://127.0.0.1:8766/', self.config))
        self.assertEqual([call.args[0][0] for call in process.call_args_list], ['broken', 'working'])
        fallback.assert_not_called()

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
