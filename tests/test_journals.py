import os
import tempfile
import unittest
from unittest.mock import patch
from test_elitelab import config
from elitelab.core import journals


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name

    def test_windows_first_and_extra_normalized(self):
        rows = journals.candidates(self.home, 'nt')
        self.assertEqual(rows[0]['source'], 'windows')
        path = rows[0]['path']
        rows = journals.candidates(self.home, 'nt', [path + os.sep, path])
        self.assertEqual(len([r for r in rows if r['path'] == path]), 1)
        self.assertEqual(rows[0]['source'], 'saved')

    def test_steam_libraries_and_proton(self):
        roots = ['.steam/steam', '.local/share/Steam', '.var/app/com.valvesoftware.Steam/.local/share/Steam']
        extra = os.path.join(self.home, 'extra')
        for rel in roots:
            root = os.path.join(self.home, rel)
            os.makedirs(os.path.join(root, 'steamapps'))
        with open(os.path.join(self.home, roots[0], 'steamapps', 'libraryfolders.vdf'), 'w') as f:
            f.write('"libraryfolders" { "1" { "path" "' + extra.replace('\\', '\\\\') + '" } }')
        target = os.path.join(extra, 'steamapps', 'compatdata', '359320', 'pfx', 'drive_c', 'users', 'steamuser',
                              'Saved Games', 'Frontier Developments', 'Elite Dangerous')
        os.makedirs(target)
        with open(os.path.join(target, 'Journal.2026-10-30T100000.01.log'), 'w') as f:
            f.write('{}\n')
        rows = journals.candidates(self.home, 'posix')
        self.assertEqual(len([r for r in rows if r['source'] == 'steam']), 4)
        found = next(r for r in rows if r['journals'])
        self.assertEqual(found['path'], target)
        self.assertEqual(found['newest'], '2026-10-30T100000.01')
        self.assertTrue(any(r['source'] == 'mac' for r in rows))
        with patch.object(journals, 'candidates', return_value=rows), patch.object(config.os.path, 'isdir', return_value=False):
            self.assertEqual(config._default_journal_dir(), target)
