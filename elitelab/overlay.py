"""Activity-independent HUD cards, local data feed and desktop entry point."""
import argparse
import json
import logging
import os
from pathlib import Path
import threading
import time
import urllib.request

from modules.rhino.overlay import NoRedirect, degrees, demo_state, guidance
from .hud_model import Card, Mode, finite, number
from .hud_activities import PROVIDERS
from urllib.parse import urlsplit, parse_qs

log = logging.getLogger(__name__)


def surface_card(state, connected):
    data = guidance(state, connected)
    return Card(title=data['site'], context=data['body'], status=data['status'],
                primary=degrees(data['bearing']) if data['bearing'] is not None else data['title'],
                primary_label='STEER' if data['bearing'] is not None else '',
                secondary=data['title'] if data['bearing'] is not None else '',
                metric=data['distance'] or '--', metric_label='TO SAVED POINT',
                stats=(('YOUR HEADING', degrees(data['heading'])), ('RHINO HOLD', data['hold'])),
                note=data['detail'], warning=data['warning'],
                tone='green' if data['mode'] in ('aligned', 'arrived') else 'amber',
                visual={'kind': 'compass', 'heading': data['heading'], 'turn': data['turn'], 'arrived': data['mode'] == 'arrived'})


def rhino_progress_card(state, connected):
    if not connected:
        return Card(title='Rhino mining', status='OFFLINE', primary='Connection lost', note='Reconnecting to EliteLab. Readouts paused.')
    run = state.get('session') or {}
    cargo = state.get('cargo') or {}
    hold, ship = cargo.get('rhino') or {}, cargo.get('ship') or {}
    fill = hold['count'] / hold['capacity'] * 100 if finite(hold.get('count')) and finite(hold.get('capacity')) and hold['capacity'] > 0 else None
    rows = run.get('commodities') or []
    context = ' / '.join(str(row.get('name') or 'Unknown') + ' ' + number(row.get('tonnes'), ' t') for row in rows[:3])
    active = run.get('active') is True
    known_hold = number(hold.get('count')) + '/' + number(hold.get('capacity'), ' t') if finite(hold.get('count')) else '--'
    free = hold.get('free')
    return Card(title='Rhino mining progress', context=context or 'Collections appear here as you mine',
                status='THIS DEPLOYMENT' if active else 'LAST DEPLOYMENT' if run else 'READY',
                primary=number(run.get('total_t'), ' t') if run else 'Ready to mine', primary_label='COLLECTED' if run else '',
                secondary=number(run.get('unloaded_t'), ' t unloaded') if run else 'Launch the Rhino to start a deployment',
                metric=known_hold, metric_label='RHINO HOLD / CAPACITY',
                stats=(('SHIP SPACE FREE', number(ship.get('free'), ' t')), ('RUN AVERAGE', number(run.get('average_tph'), ' t/h'))),
                note='Observed collections; earlier receipts may be missing.' if run.get('partial') else 'Deployment total across deposits.',
                warning='Rhino hold nearly full - unload when safe.' if finite(free) and free < 12 else '',
                tone='green' if active else 'amber', visual={'kind': 'gauge', 'value': fill, 'label': 'HOLD'})


def rhino_progress_ready(state, connected):
    run, nav = state.get('session') or {}, state.get('navigation') or {}
    distance = nav.get('distance_m')
    # A deployment receipt is progress across the whole run, never proof of output at this deposit.
    valid_position = guidance(state, connected)['distance'] is not None
    nearby = valid_position and finite(distance) and 0 <= distance < 2000
    arrived = nearby and distance < 25
    collected = finite(run.get('total_t')) and run['total_t'] > 0
    return connected and run.get('active') is True and (arrived or (collected and (nearby or not state.get('selected_site'))))


def automatic_surface_card(state, connected):
    return rhino_progress_card(state, connected) if rhino_progress_ready(state, connected) else surface_card(state, connected)


class RhinoAutomatic:
    """Remember an observed arrival while an unchanged deployment is still active.

    Quiet Status.json files can age out while rigs process. That removes steering
    evidence, not the observed collections or the fact that this run reached its
    target. Keep this memory per feed, never in a shared module-level mode object.
    """
    def __init__(self):
        self.scope = None
        self.progress = False

    def __call__(self, state, connected):
        if not connected:
            return surface_card(state, False)
        run, site = state.get('session') or {}, state.get('selected_site') or {}
        position, nav = state.get('position') or {}, state.get('navigation') or {}
        scope = (state.get('commander_key') or state.get('commander'), run.get('started_at'),
                 tuple(site.get(k) for k in ('id', 'system', 'body', 'latitude', 'longitude')))
        if scope != self.scope or run.get('active') is not True:
            self.scope, self.progress = scope, False
        # Explicit travel evidence still wins, even when a former GPS fix is old.
        elsewhere = any(position.get(k) and site.get(k) and
                        str(position[k]).casefold() != str(site[k]).casefold() for k in ('system', 'body'))
        elsewhere = elsewhere or (site.get('travel') or {}).get('stage') == 'system'
        valid_position = guidance(state, True)['distance'] is not None
        distance = nav.get('distance_m')
        # A modest exit margin avoids alternating views around the 2 km entry edge.
        left_area = valid_position and finite(distance) and distance >= 2500
        if elsewhere or left_area:
            self.progress = False
        if not elsewhere and rhino_progress_ready(state, True):
            self.progress = True
        if self.progress:
            return rhino_progress_card(state, True)
        return surface_card(state, True)


def mining_card(state, connected):
    """Existing journal receipts, with no asteroid identity or space navigation implied."""
    if not connected:
        return Card(title='Asteroid mining', status='OFFLINE', primary='Connection lost',
                    note='Reconnecting to EliteLab. Readouts paused.', visual={'kind': 'gauge', 'value': None})
    prospect = state.get('last_prospect') or {}
    rows = [r for r in prospect.get('materials', []) if isinstance(r, dict) and finite(r.get('proportion')) and 0 <= r['proportion'] <= 100]
    rows.sort(key=lambda r: -r['proportion'])
    row = rows[0] if rows else None
    stamp = prospect.get('timestamp') or ''
    timestamp = stamp.replace('T', ' ').replace('Z', ' UTC') if isinstance(stamp, str) else ''
    return Card(title=str(row.get('name') or 'Unknown mineral') if row else 'Asteroid mining',
                context=f'Prospector report: {timestamp}' if timestamp else 'Prospect an asteroid to see its composition',
                status='LAST SESSION' if state.get('ended') else 'LAST PROSPECTOR' if row else 'WAITING',
                primary=f"{row['proportion']:.1f}%" if row else 'Ready to prospect',
                primary_label='COMPOSITION' if row else '',
                secondary=' / '.join(str(r.get('name') or 'Unknown') + ' ' + number(r['proportion'], '%') for r in rows[1:3]),
                metric=number(state.get('refined_tons'), ' t'), metric_label='REFINED THIS SESSION',
                stats=(('REMAINING IN REPORT', number(prospect.get('remaining'), '%')), ('SESSION AVERAGE', number(state.get('tons_per_hour'), ' t/h'))),
                note='Core reported: ' + str(prospect['motherlode']) if prospect.get('motherlode') else 'Last observed composition; reports are not unique rocks.',
                visual={'kind': 'gauge', 'value': row['proportion'] if row else None})


MODES = {
    'surface': Mode('Rhino - automatic', '/api/rhino', 'navigation', automatic_surface_card),
    'navigation': Mode('Surface navigation', '/api/rhino', 'navigation', surface_card),
    'rhino': Mode('Rhino mining progress', '/api/rhino', 'navigation', rhino_progress_card),
    'mining': Mode('Mining readouts', '/api/mining', 'refined_tons', mining_card),
}


CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'web' / 'hud-modes.json').read_text(encoding='utf-8'))
for entry in CATALOG:
    key = entry['id']
    if key in PROVIDERS:
        endpoint, required, build, interval = PROVIDERS[key]
        MODES[key] = Mode(entry['label'], endpoint, required, build, entry['group'], interval)
MODES = {entry['id']: MODES[entry['id']] for entry in CATALOG}


def mode_from_uri(uri):
    """The external protocol can only choose a known activity. No paths or commands."""
    if not isinstance(uri, str) or len(uri) > 120 or any(ord(c) < 33 or c in '\\"\'' for c in uri):
        raise ValueError('Invalid HUD link')
    parsed = urlsplit(uri)
    if parsed.scheme != 'elitelab-hud' or parsed.path != 'open' or parsed.netloc or parsed.fragment:
        raise ValueError('Invalid HUD link')
    # Python 3.10's strict query parser rejects an empty query string.
    if not parsed.query:
        return None
    params = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if set(params) != {'mode'} or len(params['mode']) != 1 or params['mode'][0] not in MODES:
        raise ValueError('Unknown HUD activity')
    return params['mode'][0]


def demo_card(mode='surface'):
    if mode in ('surface', 'navigation'):
        return surface_card(demo_state(), True)
    if mode == 'rhino':
        return rhino_progress_card({'session': {'active': True, 'total_t': 157, 'unloaded_t': 135, 'average_tph': 215,
                                   'commodities': [{'name': 'Iridium', 'tonnes': 157}]},
                                   'cargo': {'rhino': {'count': 22, 'capacity': 72, 'free': 50}, 'ship': {'free': 540}}}, True)
    if mode not in ('surface', 'navigation', 'rhino', 'mining'):
        from .hud_samples import SAMPLES
        return MODES[mode].build(SAMPLES.get(mode, {}), True)
    return mining_card({'last_prospect': {'materials': [{'name': 'Platinum', 'proportion': 51.7}, {'name': 'Osmium', 'proportion': 8.2}],
                        'remaining': 100, 'timestamp': '2026-11-17T12:00:00Z'}, 'refined_tons': 168, 'tons_per_hour': 215}, True)


class Feed:
    """A single bounded poller; generation checks reject replies from an old mode."""
    def __init__(self, port, token='', interval=None, mode='overview'):
        if type(port) is not int or not 1 <= port <= 65535 or mode not in MODES:
            raise ValueError('Invalid HUD port or activity')
        self.base, self.token, self.interval = f'http://127.0.0.1:{port}', token, interval
        self.lock, self.wake, self.stop_event = threading.Lock(), threading.Event(), threading.Event()
        self.mode, self.generation = mode, 0
        self.state, self.last_ok, self.connected = {}, 0, False
        self.thread = None
        self.unavailable = False
        self.rhino_automatic = RhinoAutomatic()

    def select(self, mode):
        if mode not in MODES:
            raise ValueError('Unknown HUD activity')
        with self.lock:
            if mode == self.mode:
                return
            self.mode, self.generation = mode, self.generation + 1
            self.state, self.last_ok, self.connected = {}, 0, False
            self.unavailable = False
        self.wake.set()

    def accept(self, generation, state):
        with self.lock:
            if generation != self.generation:
                return
            self.state, self.connected, self.last_ok = state, True, time.monotonic()
            self.unavailable = False

    def start(self):
        self.thread = threading.Thread(target=self._run, name='elitelab-hud-feed', daemon=True)
        self.thread.start()

    def _run(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        while not self.stop_event.is_set():
            self.wake.clear()
            with self.lock:
                mode, generation = MODES[self.mode], self.generation
            try:
                with opener.open(urllib.request.Request(self.base + mode.endpoint, headers=headers), timeout=3) as response:
                    payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError('Response too large')
                state = json.loads(payload)
                if not isinstance(state, dict) or mode.required_key not in state:
                    raise ValueError('Unexpected activity response')
                self.accept(generation, state)
            except (OSError, ValueError) as error:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                with self.lock:
                    if generation == self.generation:
                        self.connected = False
                        self.unavailable = getattr(error, 'code', None) == 404 or isinstance(error, ValueError)
            self.wake.wait(self.interval if self.interval is not None else mode.interval)

    def view(self):
        with self.lock:
            mode, state = MODES[self.mode], self.state
            connected = self.connected and time.monotonic() - self.last_ok < max(5, mode.interval * 2 + 3)
            if self.unavailable:
                return Card(title=mode.label, status='UNAVAILABLE', primary='Module unavailable', note='Enable or update this module in EliteLab.')
            try:
                build = self.rhino_automatic if self.mode == 'surface' else mode.build
                return build(state, connected)
            except (TypeError, ValueError, AttributeError, KeyError):
                log.exception('Invalid %s HUD payload', mode.label)
                return Card(title=mode.label, status='DATA UNAVAILABLE', primary='Waiting for data', note='Readout paused while data recovers.')

    def close(self):
        self.stop_event.set(); self.wake.set()


def main():
    parser = argparse.ArgumentParser(description='EliteLab HUD: a transparent window for your current activity.')
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--mode', choices=MODES)
    parser.add_argument('--uri', help=argparse.SUPPRESS)
    parser.add_argument('--close-after', type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.uri:
        if args.mode or args.demo or args.close_after:
            parser.error('A HUD link cannot include other options')
        try:
            args.mode = mode_from_uri(args.uri)
        except ValueError as error:
            parser.error(str(error))
    if os.name != 'nt':
        parser.error('The native HUD requires Windows; use the browser overlay on other platforms.')
    from .core import config
    from .windows_overlay import load_preferences, run, save_preferences
    prefs = Path(config.DATA_DIR) / 'overlay.json'
    if not args.demo and not prefs.exists():
        old = Path(config.DATA_DIR) / 'rhino-overlay.json'
        if old.exists():
            save_preferences(prefs, load_preferences(old))
    settings = load_preferences(prefs)
    mode = args.mode or settings.get('activity', 'overview')
    feed = None if args.demo else Feed(config.PORT, config.AUTH_TOKEN, mode=mode)
    log_dir = Path(config.DATA_DIR) / 'logs'; log_dir.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.WARNING, handlers=[RotatingFileHandler(log_dir / 'overlay.log', maxBytes=250000, backupCount=1, encoding='utf-8')])
    try:
        run(feed, prefs, args.demo, max(0, args.close_after), activity=mode, requested_activity=args.mode)
    except Exception:
        log.exception('HUD stopped unexpectedly')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, 'The HUD stopped. Open EliteLab HUD again to recover. Details are in ' + str(log_dir / 'overlay.log'), 'EliteLab HUD', 0x10)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
