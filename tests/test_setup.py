import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from test_elitelab import Core, config, loader, FIXTURES
from elitelab.core.http import make_handler


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, 'settings.json')
        for key, value in [('SETTINGS_PATH', self.path), ('JOURNAL_DIR', FIXTURES), ('DATA_DIR', self.temp.name)]:
            p = patch.object(config, key, value); p.start(); self.addCleanup(p.stop)
        self.core = Core(); loader.load_all(self.core)

    def call(self, name, **values):
        return self.core.http.tools[name].fn(values)

    def test_status_and_real_journal_detection_before_replay(self):
        state = self.call('get_setup')
        self.assertTrue(state['journal_found'])
        self.assertFalse(state['exists'])
        self.assertTrue(any(c['selected'] for c in state['journal_candidates']))
        self.assertEqual(state['values']['port'], config.PORT)

    def test_save_and_revert_pending_changes(self):
        port = 8799 if config.PORT != 8799 else 8800
        result = self.call('save_setup', port=port)
        self.assertEqual(result['pending'], {'port': port})
        with open(self.path) as stream: self.assertEqual(json.load(stream), {'port': port})
        self.assertTrue(self.core.store.get('setup', 'restart_required'))
        self.assertFalse(self.call('save_setup', port=config.PORT)['restart_required'])

    def test_same_value_does_not_write(self):
        self.assertEqual(self.call('save_setup', port=config.PORT)['saved'], [])
        self.assertFalse(os.path.exists(self.path))

    def test_unknown_keys_preserved_and_validation_atomic(self):
        original = {'future':1, 'connections':{'inara':{}}}
        with open(self.path, 'w') as stream: json.dump(original, stream)
        for values in ({'port':80}, {'port':'8767'}, {'host':'example.com'}, {'journal_dir':''}, {'connections':{}}):
            with self.subTest(values=values), self.assertRaises(ValueError): self.call('save_setup', **values)
        self.call('save_setup', port=8799)
        with open(self.path) as stream: saved = json.load(stream)
        self.assertEqual(saved['future'], 1); self.assertEqual(saved['connections'], original['connections'])

    def test_paths_normalized_and_missing_folder_warns(self):
        folder = os.path.join(self.temp.name, 'missing')
        result = self.call('save_setup', journal_dir=folder + os.sep)
        self.assertEqual(result['pending']['journal_dir'], folder)
        self.assertEqual(len(result['warnings']), 2 if config.SOURCES['journal_dir'] in ('env','flag') else 1)

    def test_restart_and_schema(self):
        with patch.object(self.core, 'request_restart') as restart:
            self.assertEqual(self.call('restart_elitelab'), {'restarting':True,'exit_code':75})
            restart.assert_called_once()
        for name in ('get_setup','save_setup','restart_elitelab'):
            self.assertTrue(self.core.http.tools[name].description)

    def test_page_served_and_traversal_rejected(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.core))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/setup/') as response:
            self.assertIn('text/html', response.headers['Content-Type'])
            page = response.read().decode(); self.assertIn('data-setup-form', page); self.assertIn('Connections', page)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/setup/../module.py')
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_remote_setup_requires_configured_authentication(self):
        base = make_handler(self.core)
        class RemoteHandler(base):
            def setup(self):
                super().setup()
                self.client_address = ('192.168.1.20', self.client_address[1])
        server = ThreadingHTTPServer(('127.0.0.1',0), RemoteHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        for path in ('/api/setup', '/api/restart'):
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', data=b'{}', headers={'Content-Type':'application/json'})
            with patch.object(config, 'AUTH_TOKEN', ''), self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,403); caught.exception.close()
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/setup', data=b'{}', headers={'Content-Type':'application/json', 'Authorization':'Bearer test-token'})
        with patch.object(config, 'AUTH_TOKEN', 'test-token'), urllib.request.urlopen(request) as response:
            self.assertEqual(response.status,200)
