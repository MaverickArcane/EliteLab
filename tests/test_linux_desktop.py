"""Login-entry ownership and installed Linux browser selection."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from elitelab.linux_autostart import LinuxAutostart, ENTRY
from elitelab import window


class LinuxDesktopTests(unittest.TestCase):
    def test_login_is_opt_in_and_removes_only_the_owned_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.linux-package').touch()
            setting = LinuxAutostart(root, root / 'config')
            self.assertEqual(setting.status(), 'disabled')
            self.assertFalse(setting.path.exists())
            self.assertTrue(setting.set_enabled(True))
            self.assertEqual(setting.path.read_bytes(), ENTRY.encode('ascii'))
            self.assertEqual(setting.status(), 'enabled')
            self.assertTrue(setting.set_enabled(True))
            self.assertFalse(setting.set_enabled(False))
            self.assertFalse(setting.path.exists())
            setting.path.write_text('foreign entry')
            for enabled in (True, False):
                with self.assertRaises(ValueError): setting.set_enabled(enabled)
            self.assertEqual(setting.path.read_text(), 'foreign entry')

    def test_source_checkout_cannot_enable_installed_login_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting = LinuxAutostart(tmp, tmp)
            with self.assertRaises(ValueError): setting.set_enabled(True)
            self.assertFalse(setting.path.exists())

    def test_relative_xdg_uses_home(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME':'relative'}), patch('pathlib.Path.home', return_value=Path('/home/test')):
            self.assertEqual(LinuxAutostart('/app').path, Path('/home/test/.config/autostart/elitelab.desktop'))

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink ownership')
    def test_symlink_entry_is_never_followed_or_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            setting = LinuxAutostart(tmp, tmp)
            setting.path.parent.mkdir()
            target = Path(tmp) / 'other'
            target.write_text(ENTRY)
            setting.path.symlink_to(target)
            self.assertEqual(setting.status(), 'conflict')
            for enabled in (True, False):
                with self.assertRaises(ValueError): setting.set_enabled(enabled)
            self.assertTrue(setting.path.is_symlink())
            self.assertEqual(target.read_text(), ENTRY)

    def test_installed_linux_browser_uses_own_profile_and_argument_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.linux-package').touch()
            config = SimpleNamespace(ROOT=tmp, DATA_DIR=str(root / 'saved data'), BROWSER='/browser with spaces')
            with patch('elitelab.window.sys.platform', 'linux'), patch('elitelab.window.subprocess.Popen') as launch:
                self.assertTrue(window.open_dashboard('http://127.0.0.1:8123/setup/', config))
            args = launch.call_args.args[0]
            self.assertEqual(args[0], '/browser with spaces')
            self.assertIn('--app=http://127.0.0.1:8123/setup/', args)
            self.assertIn('--user-data-dir=' + str(root / 'saved data/browser'), args)
            self.assertNotIn('shell', launch.call_args.kwargs)

    def test_linux_browser_discovery_and_tab_fallback(self):
        with patch('elitelab.window.shutil.which', side_effect=lambda name:'/usr/bin/chromium' if name=='chromium' else None):
            self.assertEqual(window.linux_browsers(), ['/usr/bin/chromium'])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / '.linux-package').touch()
            config = SimpleNamespace(ROOT=tmp, DATA_DIR=tmp, BROWSER='')
            with patch('elitelab.window.sys.platform', 'linux'), patch('elitelab.window.linux_browsers', return_value=[]), patch('elitelab.window.webbrowser.open', return_value=True) as fallback:
                self.assertTrue(window.open_dashboard('http://127.0.0.1:8123/', config))
            fallback.assert_called_once()
