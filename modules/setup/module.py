"""Persist startup settings without changing the running commander's state."""
import ipaddress
import os
import threading
from elitelab.core import config, journals

KEYS = ('journal_dir', 'port', 'host', 'data_dir', 'browser')


class Setup:
    def __init__(self, core):
        self.core = core
        self.pending = {}
        self.lock = threading.RLock()
        self.publish()

    def status(self, q=None):
        with self.lock:
            values = {k: getattr(config, k.upper()) for k in KEYS}
            candidates = journals.candidates(os.path.expanduser('~'), extra=[values['journal_dir']])
            for candidate in candidates:
                candidate['selected'] = os.path.normcase(candidate['path']) == os.path.normcase(os.path.normpath(values['journal_dir']))
            return {'path': config.SETTINGS_PATH, 'exists': os.path.isfile(config.SETTINGS_PATH),
                    'values': values, 'sources': dict(config.SOURCES), 'pending': dict(self.pending),
                    'restart_required': bool(self.pending),
                    'journal_found': journals.describe(values['journal_dir'])['journals'] > 0,
                    'journal_candidates': candidates}

    def publish(self):
        state = self.status()
        self.core.store.update('setup', {'journal_found': state['journal_found'],
            'journal_dir': state['values']['journal_dir'], 'settings_path': state['path'],
            'restart_required': state['restart_required']})

    def save(self, q):
        if not isinstance(q, dict) or set(q) - set(KEYS):
            raise ValueError('Only journal_dir, port, host, data_dir and browser can be saved here.')
        changes, warnings = {}, []
        for key, value in q.items():
            if key == 'port':
                if type(value) is not int or not 1024 <= value <= 65535:
                    raise ValueError('port must be a whole number from 1024 to 65535.')
            elif key in ('journal_dir', 'data_dir'):
                if not isinstance(value, str) or not value.strip() or '\x00' in value:
                    raise ValueError(key + ' must be a non-empty folder path.')
                value = os.path.abspath(os.path.expanduser(value))
                if not os.path.isdir(value):
                    warnings.append('Folder does not exist yet: ' + value)
            elif key == 'host':
                if not isinstance(value, str):
                    raise ValueError('host must be localhost or an IP address.')
                if value != 'localhost':
                    try:
                        ipaddress.ip_address(value)
                    except ValueError:
                        raise ValueError('host must be localhost or an IP address.') from None
            elif not isinstance(value, str) or '\x00' in value:
                raise ValueError('browser must be text.')
            changes[key] = value
        with self.lock:
            running = self.status()['values']
            changes = {k: v for k, v in changes.items() if v != self.pending.get(k, running[k])}
            if changes:
                config.save_settings(changes, config.SETTINGS_PATH)
                for key, value in changes.items():
                    if value == running[key]:
                        self.pending.pop(key, None)
                    else:
                        self.pending[key] = value
                    if config.SOURCES.get(key) in ('env', 'flag'):
                        warnings.append(key + ' is overridden by ' + config.SOURCES[key] + '; remove that override to use the saved value.')
            self.publish()
            return {**self.status(), 'saved': list(changes), 'warnings': warnings}

    def restart(self, q):
        self.core.request_restart()
        return {'restarting': True, 'exit_code': config.RESTART_EXIT_CODE}


def setup(core, module):
    settings = Setup(core)
    core.http.route('/api/setup', settings.status, tool='get_setup', module=module.name,
        description='Read effective startup settings, their sources, detected journal folders and pending restart changes.')
    core.http.route('/api/setup', settings.save, method='POST', tool='save_setup', module=module.name,
        description='Save changed startup settings to disk. Nothing applies live; restart is required. Environment and CLI overrides still win.',
        params={k: {'type': 'integer' if k == 'port' else 'string'} for k in KEYS})
    core.http.route('/api/restart', settings.restart, method='POST', tool='restart_elitelab', module=module.name,
        description='Exit EliteLab with status 75. The start script or supervisor must restart it to apply saved settings.')
    core.http.mount('/setup/', os.path.join(module.path, 'web', 'page'))
