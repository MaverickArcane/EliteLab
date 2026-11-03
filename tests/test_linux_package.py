"""Debian package staging and isolated per-user data defaults."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from test_elitelab import config

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_debian', ROOT/'scripts'/'build_debian.py')
package=importlib.util.module_from_spec(spec); spec.loader.exec_module(package)


class DebianPackageTests(unittest.TestCase):
    def fixture(self, root):
        files=['elitelab/__main__.py','elitelab/desktop.py','modules/setup/module.json','web/index.html']
        for name in files:
            path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('fixture',encoding='ascii')
        manifest=root/'installer'/'debian'/'manifest.txt'; manifest.parent.mkdir(parents=True)
        manifest.write_text('\n'.join(files)+'\n',encoding='ascii')
        (root/'LICENSE').write_text('license',encoding='ascii')
        return manifest

    def test_staging_contains_only_manifest_and_package_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();self.fixture(root)
            (root/'elitelab'/'secret.json').write_text('private',encoding='ascii')
            (root/'elitelab'/'extra.py').write_text('unlisted',encoding='ascii')
            stage=Path(tmp)/'stage';package.stage(root,stage)
            app=stage/'usr'/'lib'/'elitelab'
            self.assertFalse((app/'elitelab'/'secret.json').exists())
            self.assertFalse((app/'elitelab'/'extra.py').exists())
            self.assertTrue((app/'.linux-package').is_file())
            self.assertIn('Terminal=false',(stage/'usr'/'share'/'applications'/'elitelab.desktop').read_text())
            self.assertTrue((stage/'usr'/'bin'/'elitelab-desktop').read_bytes().startswith(b'#!/bin/sh\n'))

    def test_manifest_traversal_duplicate_or_missing_files_fail(self):
        for invalid in ('../outside.py','elitelab/../outside.py','elitelab/__main__.py','web/missing.js'):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'source';root.mkdir();manifest=self.fixture(root)
                with manifest.open('a',encoding='ascii') as f:f.write(invalid+'\n')
                with self.assertRaises(ValueError):package.stage(root,Path(tmp)/'stage')

    def test_linux_data_dir_uses_absolute_xdg_or_home_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'app';root.mkdir();(root/'.linux-package').write_text('marker')
            data=Path(tmp)/'data'
            with patch.dict(os.environ,{'XDG_DATA_HOME':str(data)},clear=False):
                self.assertEqual(config._default_data_dir(str(root),'posix'),str(data/'elitelab'))
            with patch.dict(os.environ,{'XDG_DATA_HOME':'relative'},clear=False), patch('elitelab.core.config.os.path.expanduser', return_value=str(Path(tmp)/'home')):
                self.assertEqual(config._default_data_dir(str(root),'posix'),str(Path(tmp)/'home'/'.local'/'share'/'elitelab'))
            (root/'.linux-package').unlink()
            self.assertEqual(config._default_data_dir(str(root),'posix'),str(root/'data'))

    def test_manifest_covers_tracked_application_files(self):
        if not (ROOT/'.git').exists(): self.skipTest('source archive has no git metadata')
        try: tracked=subprocess.check_output(['git','ls-files','elitelab','modules','web'],cwd=ROOT,text=True).splitlines()
        except (OSError, subprocess.CalledProcessError): self.skipTest('git unavailable')
        expected=sorted(p for p in tracked if Path(p).suffix in package.ALLOWED)
        actual=(ROOT/'installer'/'debian'/'manifest.txt').read_text(encoding='ascii').splitlines()
        self.assertEqual(actual,expected)
