"""Opt-in per-user sign-in startup for the Windows portable bundle."""
import argparse
import ctypes
from pathlib import Path

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'MaverickArcane.EliteLab'


def system_wscript():
    """Use the Windows API's system directory, not PATH or an environment override."""
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise OSError('Cannot locate the Windows system directory')
    return str(Path(buffer.value) / 'wscript.exe')


class Autostart:
    def __init__(self, root, registry=None, value_name=VALUE_NAME, executable=None):
        if registry is None:
            import winreg as registry
        self.registry = registry
        self.root = Path(root).resolve()
        self.value_name = value_name
        self.executable = executable or system_wscript()
        self.script = self.root / 'Launch EliteLab.vbs'
        # Windows filenames cannot contain a double quote. No cmd.exe or shell.
        self.command = '"' + self.executable + '" "' + str(self.script) + '"'

    def _read(self, key):
        try:
            value, kind = self.registry.QueryValueEx(key, self.value_name)
        except FileNotFoundError:
            return None
        if kind == self.registry.REG_SZ and value == self.command:
            return 'enabled'
        return 'conflict'

    def status(self):
        try:
            with self.registry.OpenKey(self.registry.HKEY_CURRENT_USER, RUN_KEY, 0, self.registry.KEY_QUERY_VALUE) as key:
                return self._read(key) or 'disabled'
        except FileNotFoundError:
            return 'disabled'

    def set_enabled(self, enabled):
        if enabled and (not (self.root / '.windows-bundle').is_file() or not self.script.is_file() or not Path(self.executable).is_file()):
            raise ValueError('The Windows bundle launcher is missing.')
        try:
            if enabled:
                key_context = self.registry.CreateKeyEx(self.registry.HKEY_CURRENT_USER, RUN_KEY, 0,
                                                        self.registry.KEY_QUERY_VALUE | self.registry.KEY_SET_VALUE)
            else:
                key_context = self.registry.OpenKey(self.registry.HKEY_CURRENT_USER, RUN_KEY, 0,
                                                    self.registry.KEY_QUERY_VALUE | self.registry.KEY_SET_VALUE)
        except FileNotFoundError:
            if not enabled:
                return False
            raise
        with key_context as key:
            state = self._read(key)
            if state == 'conflict':
                raise ValueError('Another startup entry already uses the EliteLab name. Change it in Windows Startup apps first.')
            if enabled and state != 'enabled':
                self.registry.SetValueEx(key, self.value_name, 0, self.registry.REG_SZ, self.command)
            elif not enabled and state == 'enabled':
                self.registry.DeleteValue(key, self.value_name)
        return bool(enabled)

    def remove_owned(self):
        """Remove this installation's entry, leaving absent or foreign entries alone."""
        state = self.status()
        if state == 'enabled':
            self.set_enabled(False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove-owned', action='store_true', required=True)
    parser.add_argument('--value-name', default=VALUE_NAME)
    args = parser.parse_args(argv)
    # The uninstaller passes its own validated application ID. Never accept a
    # value name with separators or control characters.
    if not args.value_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in args.value_name):
        return 1
    try:
        Autostart(Path(__file__).resolve().parents[1], value_name=args.value_name).remove_owned()
        return 0
    except (OSError, ValueError):
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
