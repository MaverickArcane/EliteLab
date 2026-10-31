import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['ELITELAB_OFFLINE'] = '1'
os.environ['ELITELAB_JOURNAL_DIR'] = str(ROOT / 'tests' / 'fixtures' / 'journals')
os.environ['ELITELAB_DATA_DIR'] = tempfile.mkdtemp(prefix='elitelab-browser-data-')
os.environ['ELITELAB_SETTINGS'] = os.path.join(os.environ['ELITELAB_DATA_DIR'], 'settings.json')
from elitelab.core import Core, loader
from elitelab.core.http import make_handler
from http.server import ThreadingHTTPServer
core = Core()
loader.load_all(core)
core.watcher.replay()
core.http.route('/audit/emit', lambda q: core.bus.emit('journal.MaterialCollected', {'event': 'MaterialCollected', 'Name': 'iron', 'Count': 1, 'Category': 'Raw'}), method='POST')
server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(core))
print(server.server_port, flush=True)
server.serve_forever()
