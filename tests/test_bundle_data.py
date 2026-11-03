"""Windows portable data location and existing settings precedence."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_elitelab import config

class BundleDataTests(unittest.TestCase):
    def test_new_bundle_uses_user_data_and_existing_data_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            root.mkdir()
            user = Path(temp) / 'user'
            with mock.patch.dict(os.environ, {'LOCALAPPDATA': str(user)}):
                self.assertEqual(config._default_data_dir(str(root), 'nt'), str(root / 'data'))
                (root / '.windows-bundle').write_text('bundle', encoding='ascii')
                expected = str(user / 'EliteLab' / 'data')
                self.assertEqual(config._default_data_dir(str(root), 'nt'), expected)
                self.assertEqual(config._default_data_dir(str(root), 'posix'), str(root / 'data'))
                (root / 'data').mkdir()
                self.assertEqual(config._default_data_dir(str(root), 'nt'), str(root / 'data'))

    def test_explicit_settings_and_environment_override_bundle_default(self):
        with mock.patch.dict(config.SETTINGS, {'data_dir': 'saved'}, clear=True), mock.patch.dict(config.SOURCES), mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config._pick('data_dir', 'ELITELAB_DATA_DIR', lambda: 'default'), 'saved')
            with mock.patch.dict(os.environ, {'ELITELAB_DATA_DIR': 'environment'}):
                self.assertEqual(config._pick('data_dir', 'ELITELAB_DATA_DIR', lambda: 'default'), 'environment')
