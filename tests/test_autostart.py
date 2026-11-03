"""Opt-in sign-in startup: no overwrite or removal of another entry."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from elitelab import autostart
from elitelab.autostart import Autostart


class FakeKey:
    def __enter__(self): return self
    def __exit__(self, *args): pass


class FakeRegistry:
    HKEY_CURRENT_USER=1; KEY_QUERY_VALUE=1; KEY_SET_VALUE=2; REG_SZ=1
    def __init__(self): self.values={}; self.created=0
    def OpenKey(self, *args): return FakeKey()
    def CreateKeyEx(self, *args): self.created+=1; return FakeKey()
    def QueryValueEx(self, key, name):
        if name not in self.values: raise FileNotFoundError(name)
        return self.values[name]
    def SetValueEx(self, key, name, reserved, kind, value): self.values[name]=(value,kind)
    def DeleteValue(self, key, name): del self.values[name]


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'app folder'; self.root.mkdir()
        (self.root/'.windows-bundle').write_text('marker',encoding='ascii')
        (self.root/'Launch EliteLab.vbs').write_text('fixture',encoding='ascii')
        self.executable=Path(self.tmp.name)/'wscript.exe'; self.executable.write_text('fixture',encoding='ascii')
        self.reg=FakeRegistry()
        self.start=Autostart(self.root,registry=self.reg,value_name='test',executable=str(self.executable))

    def test_explicit_enable_then_disable(self):
        self.assertEqual(self.start.status(),'disabled'); self.assertEqual(self.reg.created,0)
        self.assertTrue(self.start.set_enabled(True)); self.assertEqual(self.start.status(),'enabled')
        self.assertEqual(self.reg.values['test'][0], '"'+str(self.executable)+'" "'+str(self.root.resolve()/'Launch EliteLab.vbs')+'"')
        self.assertFalse(self.start.set_enabled(False)); self.assertEqual(self.start.status(),'disabled')

    def test_foreign_entry_is_never_overwritten_or_removed(self):
        self.reg.values['test']=('another program',self.reg.REG_SZ)
        self.assertEqual(self.start.status(),'conflict')
        with self.assertRaises(ValueError): self.start.set_enabled(True)
        with self.assertRaises(ValueError): self.start.set_enabled(False)
        self.start.remove_owned()
        self.assertEqual(self.reg.values['test'][0],'another program')

    def test_enabling_requires_bundle_launcher_and_executable(self):
        (self.root/'Launch EliteLab.vbs').unlink()
        with self.assertRaises(ValueError): self.start.set_enabled(True)
        self.assertEqual(self.reg.values,{})

    def test_uninstall_removes_only_owned_entry(self):
        self.start.set_enabled(True); self.start.remove_owned()
        self.assertEqual(self.start.status(),'disabled')

    def test_helper_returns_error_if_registry_is_unavailable(self):
        fake=Mock(); fake.remove_owned.side_effect=PermissionError('denied')
        with patch('elitelab.autostart.Autostart', return_value=fake):
            self.assertEqual(autostart.main(['--remove-owned','--value-name','test']),1)
        with patch('elitelab.autostart.Autostart') as factory:
            self.assertEqual(autostart.main(['--remove-owned','--value-name','../bad']),1)
            factory.assert_not_called()

    def test_conflicting_registry_type_is_not_owned(self):
        self.reg.values['test']=(self.start.command, 999)
        self.assertEqual(self.start.status(),'conflict')
        self.start.remove_owned()
        self.assertIn('test', self.reg.values)
