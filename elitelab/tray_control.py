"""Verified local actions for the Windows desktop tray."""
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit

from .instance import InstanceGuard, health
from .window import open_dashboard
from .autostart import Autostart


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class TrayControl:
    def __init__(self, config, refresh=None):
        self.config = config
        self.refresh = refresh
        self.child = None

    def set_child(self, child):
        self.child = child

    def verified_url(self):
        """Only address the healthy loopback server owned by our live child."""
        child = self.child
        if child is None or child.poll() is not None:
            return None
        path = InstanceGuard().directory / 'instance.lock'
        try:
            with path.open('rb') as f:
                f.seek(1)
                record = json.loads(f.read(16384))
            url = record.get('url', '')
            parsed = urlsplit(url)
            if (record.get('pid') != child.pid or parsed.scheme != 'http' or
                    parsed.hostname not in ('127.0.0.1', 'localhost') or not parsed.port or
                    parsed.username is not None or parsed.password is not None or
                    parsed.path != '/' or parsed.query or parsed.fragment):
                return None
            if parsed.hostname == 'localhost':
                url = f'http://127.0.0.1:{parsed.port}/'
            state = health(url, self.config.AUTH_TOKEN)
            if not state or not state.get('ready') or state.get('pid') != child.pid or child.poll() is not None:
                return None
            return url
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def open(self, setup=False):
        url = self.verified_url()
        if not url:
            return False
        if self.refresh:
            self.config = self.refresh()
        return bool(open_dashboard(url + ('setup/' if setup else ''), self.config))

    def autostart_status(self):
        return Autostart(self.config.ROOT).status()

    def toggle_autostart(self):
        setting = Autostart(self.config.ROOT)
        state = setting.status()
        if state == 'conflict':
            raise ValueError('Another EliteLab startup entry exists. Change it in Windows Startup apps first.')
        return setting.set_enabled(state != 'enabled')

    def shutdown(self):
        url = self.verified_url()
        if not url:
            return False
        headers = {'Content-Type': 'application/json'}
        if self.config.AUTH_TOKEN:
            headers['Authorization'] = 'Bearer ' + self.config.AUTH_TOKEN
        request = urllib.request.Request(url + 'api/shutdown', data=b'{}', headers=headers, method='POST')
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=2) as response:
                return json.loads(response.read(4096)).get('stopping') is True
        except (OSError, ValueError, TypeError, AttributeError):
            return False
