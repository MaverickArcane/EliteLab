"""Read-only navigation model and loopback client for the native Windows HUD."""
import datetime as dt
import json
import math
import threading
import time
import urllib.request


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def degrees(value):
    return f"{math.floor(value % 360 + .5) % 360:03d}\N{DEGREE SIGN}" if finite(value) else "--"


def guidance(state, connected=True, now=None):
    state = state if isinstance(state, dict) else {}
    site, pos, nav = state.get('selected_site') or {}, state.get('position') or {}, state.get('navigation') or {}
    result = dict(mode='waiting', title='Choose a mining spot', detail='Select Navigate in Rhino > Locations.',
                  status='WAITING', turn=None, distance=None, bearing=None, heading=None,
                  site=site.get('name') or 'No target selected', body=site.get('body') or '',
                  mineral=site.get('commodity') or 'SURFACE NAVIGATION', hold='--', warning='')
    if site.get('availability') == 'reported_depleted':
        result['warning'] = 'Reported depleted - check the deposit.'
    elif site.get('verification') == 'unconfirmed':
        result['warning'] = 'Unconfirmed location - verify on arrival.'
    if not connected:
        return dict(result, status='OFFLINE', title='Connection lost', detail='Reconnecting to EliteLab. Directions paused.')
    hold = (state.get('cargo') or {}).get('rhino') or {}
    if finite(hold.get('count')):
        result['hold'] = f"{hold['count']:g}" + (f"/{hold['capacity']:g}" if finite(hold.get('capacity')) else '') + ' t'
    if not site:
        return result
    if (site.get('travel') or {}).get('stage') == 'system':
        return dict(result, status='IN TRANSIT', title=f"Travel to {site.get('system', '')}", detail=f"Then approach {site.get('body', '')}.")
    try:
        age = (time.time() if now is None else now) - dt.datetime.fromisoformat(pos['timestamp'].replace('Z', '+00:00')).timestamp()
    except (KeyError, TypeError, ValueError, AttributeError):
        age = math.inf
    if not -5 <= age <= 120:
        return dict(result, title='Waiting for surface GPS', detail='Approach the target body for directions.')
    if any(str(pos.get(k) or '').casefold() != str(site.get(k) or '').casefold() for k in ('system', 'body')):
        return dict(result, status='IN TRANSIT', title='Approach the target body', detail=result['body'])
    if not all(finite(pos.get(k)) for k in ('latitude', 'longitude')) or not finite(nav.get('distance_m')) or nav['distance_m'] < 0:
        return dict(result, title='Surface position unavailable', detail=nav.get('reason') or 'Waiting for coordinates and planetary radius.')
    distance = nav['distance_m']
    result['distance'] = f'{math.floor(distance + .5)} m' if distance < 1000 else f'{distance / 1000:.2f} km' if distance < 10000 else f'{distance / 1000:.1f} km'
    for key, value in (('heading', pos.get('heading')), ('bearing', nav.get('bearing'))):
        if finite(value) and 0 <= value <= 360:
            result[key] = value % 360
    if distance < 25:
        return dict(result, mode='arrived', bearing=None, status='NEAR TARGET', title='At saved spot', detail='Within 25 m. Slow down and scan nearby.')
    if result['bearing'] is None:
        return dict(result, title='Bearing unavailable', detail='Waiting for a surface bearing.')
    if result['heading'] is None:
        return dict(result, status='BEARING ONLY', title='Steer to ' + degrees(result['bearing']), detail='Match the in-game compass. Heading unavailable.')
    turn = (result['bearing'] - result['heading'] + 540) % 360 - 180
    aligned = abs(turn) <= 5
    return dict(result, turn=turn, mode='aligned' if aligned else 'steering', status='SURFACE GPS',
                title='On course' if aligned else f"Turn {'left' if turn < 0 else 'right'} {math.floor(abs(turn) + .5)}\N{DEGREE SIGN}",
                detail='Slow down and scan nearby.' if distance < 100 else 'Direct bearing. Choose a clear path.')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Feed:
    """Poll only the configured local port; never send credentials through a proxy/redirect."""
    def __init__(self, port, token='', interval=1):
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError('Invalid local EliteLab port')
        self.url = f'http://127.0.0.1:{port}/api/rhino'
        self.token, self.interval = token, interval
        self.lock, self.stop_event = threading.Lock(), threading.Event()
        self.state, self.last_ok, self.connected = {}, 0, False
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name='rhino-overlay-feed', daemon=True)
        self.thread.start()

    def _run(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        headers = {'Authorization': 'Bearer ' + self.token} if self.token else {}
        while not self.stop_event.is_set():
            try:
                with opener.open(urllib.request.Request(self.url, headers=headers), timeout=3) as response:
                    payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError('Response too large')
                state = json.loads(payload)
                if not isinstance(state, dict) or 'navigation' not in state:
                    raise ValueError('Not a Rhino response')
                with self.lock:
                    self.state, self.last_ok, self.connected = state, time.monotonic(), True
            except (OSError, ValueError):
                with self.lock:
                    self.connected = False
            self.stop_event.wait(self.interval)

    def view(self):
        with self.lock:
            return guidance(self.state, self.connected and time.monotonic() - self.last_ok < 5)

    def close(self):
        self.stop_event.set()


def demo_state():
    """Synthetic sample for preview/acceptance, never used as a live-data fallback."""
    return {'selected_site': {'name': 'Sample iridium deposit', 'commodity': 'Iridium', 'system': 'Demo', 'body': 'Demo A 1', 'verification': 'confirmed'},
            'position': {'system': 'Demo', 'body': 'Demo A 1', 'latitude': 0, 'longitude': 0, 'heading': 230,
                         'timestamp': dt.datetime.now(dt.timezone.utc).isoformat()},
            'navigation': {'distance_m': 144, 'bearing': 207}, 'cargo': {'rhino': {'count': 48, 'capacity': 72}}}
