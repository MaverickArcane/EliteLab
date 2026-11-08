"""Offline review probes. Run: python repro_review.py CHECKOUT SCENARIO."""
import contextlib
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root / 'tests')]
temp = tempfile.TemporaryDirectory(prefix='elitelab-audit-probe-')
os.environ.update(ELITELAB_SETTINGS=str(Path(temp.name)/'settings.json'),
                  ELITELAB_DATA_DIR=str(Path(temp.name)/'data'),
                  ELITELAB_INSTANCE_DIR=str(Path(temp.name)/'instance'),
                  ELITELAB_OFFLINE='1', ELITELAB_AUTH_TOKEN='audit-fixture-token')

@contextlib.contextmanager
def server(handler):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(3)

def sse_expiry():
    from elitelab.core import Core
    from elitelab.core.http import make_handler
    core = Core()
    core.store.set('audit', 'value', 'before-expiry')
    expires = int(time.time()) + 2
    value = f'{expires}.fixture-nonce'
    signature = hmac.new(b'audit-fixture-token', value.encode(), hashlib.sha256).hexdigest()
    cookie = 'elitelab_session=' + value + '.' + signature
    def read_event(response):
        lines = []
        while True:
            line = response.readline().decode().strip()
            if not line:
                return lines
            lines.append(line)
    with server(make_handler(core)) as srv:
        stream = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=5)
        stream.request('GET', '/events', headers={'Cookie': cookie})
        response = stream.getresponse()
        initial = read_event(response)
        time.sleep(max(0, expires-time.time()) + .1)
        check = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=5)
        check.request('GET', '/api/state', headers={'Cookie':cookie})
        denied = check.getresponse()
        denied.read()
        core.store.set('audit', 'value', 'private-update-after-expiry')
        later = read_event(response)
        result = dict(stream_status=response.status, initial=initial,
                      expired_request_status=denied.status, after_expiry=later)
        assert response.status == 200 and denied.status == 401
        assert any('private-update-after-expiry' in line for line in later)
        response.close(); stream.close(); check.close()
        return result

def mcp_redirect():
    from elitelab import mcp
    captured = []
    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            captured.append(self.headers.get('Authorization'))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
    with server(Sink) as sink:
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', f'http://127.0.0.1:{sink.server_port}/untrusted')
                self.end_headers()
        with server(Redirect) as origin:
            mcp.BASE = f'http://127.0.0.1:{origin.server_port}'
            result = mcp._http('GET', '/api/schema')
    assert captured == ['Bearer audit-fixture-token']
    return dict(result=result, destination_authorization=captured,
                different_origin=True, traffic='loopback only; synthetic token')

def ptn_failed_capture():
    from test_ptn import PTNTests
    fixture = PTNTests()
    fixture.setUp()
    try:
        fixture.confirmed()
        desk = fixture.desk
        before = desk.operation(desk.data['plan'])
        target = fixture.buy
        stamp = fixture.time()
        desk.dock_event('journal.Docked', {'timestamp': stamp})
        fixture.core.store.update('journal', dict(docked=True, system=target['systemName'],
            station=target['stationName'], station_type=target['stationType']))
        fixture.core.bus.emit('journal.file.Market', dict(timestamp=fixture.time(),
            MarketID=target['marketId'], StationName=target['stationName'],
            StarSystem=target['systemName'], Items=[dict(Name='$liquor_name;',
                Name_Localised='Liquor', BuyPrice=4000, SellPrice=3900,
                Stock=500000, Demand=10, MeanPrice=10000, Producer=False)]))
        try:
            desk.capture(dict(revision=desk.data['revision'], side='buy'))
        except ValueError as error:
            rejected = str(error)
        else:
            raise AssertionError('Expected invalid-market rejection')
        after = desk.operation(desk.data['plan'])
        advert = desk.make_advert(dict(revision=desk.data['revision']))
        assert before['ready'] and after['ready'] and not after['blockers']
        return dict(ready_before=before['ready'], capture_error=rejected,
                    ready_after=after['ready'], blockers=after['blockers'], advert=advert)
    finally:
        fixture.doCleanups()

def partial_quality():
    from elitelab.core import Core
    from modules.build.module import Build
    core = Core()
    build = Build(core)
    core.store.set('journal', 'ship_info', dict(internal='sidewinder', modules=[
        dict(slot='FrameShiftDrive', item='int_hyperdrive_size2_class5', engineering=dict(
            blueprint='FSD_LongRange', level=5, quality=.4))]))
    target = dict(Ship='sidewinder', Modules=[dict(Slot='FrameShiftDrive',
        Item='int_hyperdrive_size2_class5', Engineering=dict(BlueprintName='FSD_LongRange', Level=5, Quality=1))])
    build.pin(dict(url=json.dumps(target)))
    progress = build.compute()['progress']
    row = progress['slots'][0]
    assert row['status'] == 'ok' and not progress['materials']
    return dict(existing_issue=111, current_quality=.4, target_quality=1,
                reported_status=row['status'], todo=row['todo'], materials=progress['materials'])

def mcp_ptn_timeout():
    from test_ptn import PTNTests
    from elitelab import mcp
    from elitelab.core.http import make_handler
    fixture = PTNTests()
    fixture.setUp()
    original = fixture.core.services.fetch_json
    first = True
    def slow_catalog(url, *args, **kwargs):
        nonlocal first
        # Many individually quick commodity requests can take over 90 seconds
        # in total. Delay the first fixture request to reproduce that duration.
        if first:
            first = False
            time.sleep(91)
        return original(url, *args, **kwargs)
    fixture.core.services.fetch_json = slow_catalog
    try:
        with server(make_handler(fixture.core)) as srv:
            mcp.BASE = f'http://127.0.0.1:{srv.server_port}'
            started = time.monotonic()
            try:
                mcp._call('find_ptn_routes', dict(commodities='liquor', avoid_active=False))
            except TimeoutError as error:
                failure = type(error).__name__
            else:
                raise AssertionError('Expected the real 90-second MCP timeout')
            elapsed = time.monotonic()-started
            deadline = time.monotonic()+10
            while fixture.desk.searching and time.monotonic()<deadline:
                time.sleep(.2)
            result = fixture.desk.results or {}
            assert result.get('rows'), result
            return dict(client_error=failure, client_seconds=round(elapsed,2),
                        server_completed=not fixture.desk.searching,
                        server_rows=len(result['rows']), scan_budget_seconds=300,
                        fixture_note='Offline providers delayed for 91 seconds; no external requests')
    finally:
        fixture.doCleanups()

result = globals()[sys.argv[2]]()
print(json.dumps(dict(scenario=sys.argv[2], checkout=str(root),
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
    python=sys.version, result=result), indent=2))
