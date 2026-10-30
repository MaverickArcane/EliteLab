import importlib
import json
import logging
import os
import tempfile
import unittest
from unittest.mock import patch
from test_elitelab import config


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'settings.json')
        self.addCleanup(lambda: importlib.reload(config))

    def test_save_preserves_unknown_and_connections(self):
        before = {'future': 1, 'connections': {'inara': {'k': 'v'}}}
        config.save_settings(before, self.path)
        result = config.save_settings({'port': 8767}, self.path)
        self.assertEqual(result, {**before, 'port': 8767})
        self.assertEqual(config.load_settings(self.path), result)

    def test_bad_file_and_missing_file(self):
        self.assertEqual(config.load_settings(self.path), {})
        for raw in ('{bad', '[1,2]', '"text"'):
            with open(self.path, 'w') as f:
                f.write(raw)
            disabled = logging.root.manager.disable
            logging.disable(logging.NOTSET)
            try:
                with self.assertLogs(config.__name__, level='WARNING') as logs:
                    self.assertEqual(config.load_settings(self.path), {})
                self.assertEqual(len(logs.output), 1)
            finally:
                logging.disable(disabled)
        self.assertEqual(config.save_settings({'port': 8767}, self.path), {'port': 8767})

    def test_failed_atomic_replace_preserves_original_and_cleans_temp(self):
        before = {'port': 8766, 'future': 1}
        config.save_settings(before, self.path)
        with patch.object(config.os, 'replace', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                config.save_settings({'port': 8767}, self.path)
        self.assertEqual(config.load_settings(self.path), before)
        self.assertEqual(os.listdir(self.tmp.name), ['settings.json'])

    def test_precedence_and_port_validation(self):
        for file_port, env_port, expected, source in [('8767', None, 8767, 'file'), (80, None, 8766, 'default'),
                (True, None, 8766, 'default'), (8767, '9000', 9000, 'env'), (None, None, 8766, 'default')]:
            with self.subTest(file_port=file_port, env_port=env_port):
                with open(self.path, 'w') as f:
                    json.dump({} if file_port is None else {'port': file_port}, f)
                with patch.dict(os.environ, {'ELITELAB_SETTINGS': self.path}):
                    os.environ.pop('ELITELAB_PORT', None)
                    if env_port:
                        os.environ['ELITELAB_PORT'] = env_port
                    importlib.reload(config)
                    self.assertEqual((config.PORT, config.SOURCES['port']), (expected, source))

    def test_paths_and_location(self):
        with patch.dict(os.environ, {'ELITELAB_SETTINGS': self.path}):
            self.assertEqual(config.settings_path(), self.path)
            config.save_settings({'journal_dir': '~/j/', 'data_dir': '~/d'}, self.path)
            os.environ.pop('ELITELAB_JOURNAL_DIR', None)
            os.environ.pop('ELITELAB_DATA_DIR', None)
            importlib.reload(config)
            self.assertEqual(config.JOURNAL_DIR, os.path.abspath(os.path.expanduser('~/j')))
            self.assertEqual(config.DATA_DIR, os.path.abspath(os.path.expanduser('~/d')))
        with patch.dict(os.environ, {'APPDATA': self.tmp.name, 'XDG_CONFIG_HOME': self.tmp.name}):
            os.environ.pop('ELITELAB_SETTINGS', None)
            with patch.object(config.os, 'name', 'nt'):
                self.assertEqual(config.settings_path(), os.path.join(self.tmp.name, 'EliteLab', 'settings.json'))
            with patch.object(config.os, 'name', 'posix'):
                self.assertEqual(config.settings_path(), os.path.join(self.tmp.name, 'elitelab', 'settings.json'))
                os.environ.pop('XDG_CONFIG_HOME', None)
                self.assertEqual(config.settings_path(), os.path.join(os.path.expanduser('~/.config'), 'elitelab', 'settings.json'))
