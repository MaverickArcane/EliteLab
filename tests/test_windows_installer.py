"""Reject unsafe installer input and preserve the verified bundle structure."""
import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_windows_installer', ROOT / 'scripts' / 'build_windows_installer.py')
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)

class InstallerStageTests(unittest.TestCase):
    def make_bundle(self, path, extra=()):
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('EliteLab/', '')
            z.writestr('EliteLab/runtime/', '')
            for name in ('.windows-bundle', 'Launch EliteLab.vbs', 'runtime/pythonw.exe', 'elitelab/desktop.py'):
                z.writestr('EliteLab/' + name, 'synthetic')
            for name in extra:
                info = zipfile.ZipInfo('placeholder')
                info.filename = name
                z.writestr(info, 'invalid')

    def test_valid_bundle_stages_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'; self.make_bundle(bundle)
            stage=Path(tmp)/'stage'; installer.stage_bundle(bundle, stage)
            self.assertEqual((stage/'elitelab'/'desktop.py').read_text(), 'synthetic')
            self.assertTrue((stage/'.windows-bundle').is_file())

    def test_unsafe_names_and_case_collisions_are_rejected(self):
        names=['../escape', 'EliteLab/../escape', 'EliteLab/a/../escape', 'EliteLab/a\\escape',
               'EliteLab/file:stream', 'EliteLab/CON.txt', 'EliteLab/foo.', 'EliteLab/RUNTIME/pythonw.exe']
        for index,name in enumerate(names):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                bundle=Path(tmp)/'bundle.zip'; self.make_bundle(bundle,[name])
                with self.assertRaises(ValueError): installer.stage_bundle(bundle,Path(tmp)/'stage')

    def test_symlink_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'; self.make_bundle(bundle)
            with zipfile.ZipFile(bundle,'a') as z:
                info=zipfile.ZipInfo('EliteLab/link'); info.create_system=3
                info.external_attr=(0o120777 << 16); z.writestr(info,'target')
            with self.assertRaises(ValueError):installer.stage_bundle(bundle,Path(tmp)/'stage')

    def test_expanded_size_is_bounded(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'; self.make_bundle(bundle)
            with patch.object(installer,'MAX_TOTAL', 1):
                with self.assertRaises(ValueError):installer.stage_bundle(bundle,Path(tmp)/'stage')

    def test_missing_required_files_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'
            with zipfile.ZipFile(bundle,'w') as z:z.writestr('EliteLab/example','value')
            with self.assertRaises(ValueError):installer.stage_bundle(bundle,Path(tmp)/'stage')

    def test_bundle_checksum_rejects_corruption_and_wrong_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle.zip'; self.make_bundle(bundle)
            checksum=bundle.with_suffix('.zip.sha256')
            digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
            checksum.write_text(f'{digest}  {bundle.name}\n', encoding='ascii')
            installer.verify_bundle(bundle)
            checksum.write_text(f'{digest}  another.zip\n', encoding='ascii')
            with self.assertRaises(ValueError): installer.verify_bundle(bundle)
            checksum.write_text(f'{digest}  {bundle.name}\n', encoding='ascii')
            with bundle.open('ab') as out: out.write(b'changed')
            with self.assertRaises(ValueError): installer.verify_bundle(bundle)

    def test_installer_output_requires_exe(self):
        with self.assertRaises(ValueError):
            installer.build('bundle', 'compiler', 'not-an-installer.zip')
