import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['ELITELAB_OFFLINE'] = '1'
os.environ['ELITELAB_JOURNAL_DIR'] = str(ROOT / 'tests' / 'fixtures' / 'journals')
os.environ['ELITELAB_DATA_DIR'] = tempfile.mkdtemp(prefix='elitelab-browser-data-')
from elitelab.core import Core, loader
from elitelab.core.http import make_handler
from http.server import ThreadingHTTPServer
core = Core()
core.services.edsm_coords = lambda names: {}
loader.load_all(core)
core.watcher.replay()
core.http.route('/audit/emit', lambda q: core.bus.emit('journal.MaterialCollected', {'event': 'MaterialCollected', 'Name': 'iron', 'Count': 1, 'Category': 'Raw'}), method='POST')
def ship(q):
    core.store.update('journal', {'cmdr': q.get('cmdr', 'Testpilot'), 'cargo_capacity': q.get('capacity', 200),
        'cargo': {'count': q.get('count', 0), 'items': [{'key': 'gold', 'name': 'Gold', 'count': q.get('count', 0)}]},
        'status': {'vehicle': 'ship', 'game_running': True}})
    core.modules['party'].party.publish()
    return {'ok': True}
core.http.route('/audit/ship', ship, method='POST')
server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(core))
print(server.server_port, flush=True)
server.serve_forever()
