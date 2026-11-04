"""Opt-in, current-user LaunchAgent for an installed macOS application."""
from pathlib import Path
import plistlib

LABEL = 'net.elitelab.desktop'


class MacAutostart:
    def __init__(self, root, home=None):
        self.root = Path(root).resolve()
        self.app = self.root.parent.parent.parent
        self.path = Path(home or Path.home()) / 'Library/LaunchAgents' / (LABEL + '.plist')
        self.entry = plistlib.dumps({'Label': LABEL,
            'ProgramArguments': ['/usr/bin/open', '-a', str(self.app)],
            'RunAtLoad': True, 'LimitLoadToSessionType': 'Aqua'})

    def status(self):
        if self.path.is_symlink():
            return 'conflict'
        try:
            return 'enabled' if self.path.read_bytes() == self.entry else 'conflict'
        except FileNotFoundError:
            return 'disabled'

    def set_enabled(self, enabled):
        state = self.status()
        if state == 'conflict':
            raise ValueError('An existing EliteLab login entry was changed outside this app. Manage it in Library/LaunchAgents first.')
        if enabled and (self.root != self.app / 'Contents/Resources/app' or self.app.name != 'EliteLab.app'
                        or not (self.root / '.macos-bundle').is_file()
                        or not (self.app / 'Contents/MacOS/EliteLab').is_file()):
            raise ValueError('Install EliteLab.app before enabling login startup.')
        if enabled and state == 'disabled':
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('xb') as stream:
                stream.write(self.entry)
        elif not enabled and state == 'enabled':
            self.path.unlink()
        return bool(enabled)
