"""Opt-in XDG login startup for the installed Debian desktop application."""
import os
from pathlib import Path

ENTRY = ('[Desktop Entry]\nType=Application\nName=EliteLab\n'
         'Exec=/usr/bin/elitelab-desktop\nTryExec=/usr/bin/elitelab-desktop\n'
         'Terminal=false\nX-EliteLab-Owned=true\n')


class LinuxAutostart:
    def __init__(self, root, config_home=None):
        self.root = Path(root)
        base = config_home if config_home is not None else os.environ.get('XDG_CONFIG_HOME', '')
        base = Path(base) if base and Path(base).is_absolute() else Path.home() / '.config'
        self.path = base / 'autostart' / 'elitelab.desktop'

    def status(self):
        if self.path.is_symlink():
            return 'conflict'
        try:
            return 'enabled' if self.path.read_bytes() == ENTRY.encode('ascii') else 'conflict'
        except FileNotFoundError:
            return 'disabled'

    def set_enabled(self, enabled):
        state = self.status()
        if state == 'conflict':
            raise ValueError('An existing EliteLab login entry was changed outside this app. Manage it in your desktop startup settings.')
        if enabled and not (self.root / '.linux-package').is_file():
            raise ValueError('Install the Debian package before enabling login startup.')
        if enabled and state == 'disabled':
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation never replaces an entry created by another app.
            with self.path.open('xb') as stream:
                stream.write(ENTRY.encode('ascii'))
        elif not enabled and state == 'enabled':
            self.path.unlink()
        return bool(enabled)
