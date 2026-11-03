import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['ELITELAB_OFFLINE'] = '1'
os.environ['ELITELAB_JOURNAL_DIR'] = str(ROOT / 'tests' / 'fixtures' / 'journals')
SETTINGS = os.path.join(tempfile.mkdtemp(prefix='elitelab-browser-settings-'), 'settings.json')
os.environ['ELITELAB_SETTINGS'] = SETTINGS
os.environ['ELITELAB_DATA_DIR'] = tempfile.mkdtemp(prefix='elitelab-browser-data-')
# A fixed party identity keeps equal-share remainders (lowest id first) deterministic.
if os.environ.get('ELITELAB_TEST_PARTY_ID'):
    import json
    Path(os.environ['ELITELAB_DATA_DIR'], 'party-local.json').write_text(json.dumps({'id': os.environ['ELITELAB_TEST_PARTY_ID']}), encoding='utf-8')
from elitelab.core import Core, loader
from elitelab.core.http import make_handler
from http.server import ThreadingHTTPServer
core = Core()
core.services.edsm_coords = lambda names: {}
loader.load_all(core)
core.watcher.replay()
core.http.route('/audit/emit', lambda q: core.bus.emit('journal.MaterialCollected', {'event': 'MaterialCollected', 'Name': 'iron', 'Count': 1, 'Category': 'Raw'}), method='POST')
def trade_materials(q):
    core.bus.emit('journal.Materials', {'event': 'Materials', 'Raw': [], 'Encoded': [], 'Manufactured': [
        {'Name': 'fedproprietarycomposites', 'Count': 66},
        {'Name': 'protoradiolicalloys', 'Count': 4},
        {'Name': 'chemicalmanipulators', 'Count': 14}]})
    return {'ok': True}
core.http.route('/audit/trade-materials', trade_materials, method='POST')
def ship(q):
    core.store.update('journal', {'cmdr': q.get('cmdr', 'Testpilot'), 'cargo_capacity': q.get('capacity', 200),
        'cargo': {'count': q.get('count', 0), 'items': [{'key': 'gold', 'name': 'Gold', 'count': q.get('count', 0)}]},
        'status': {'vehicle': 'ship', 'game_running': True}})
    core.modules['party'].party.publish()
    return {'ok': True}
core.http.route('/audit/ship', ship, method='POST')
def trade_plan(q):
    """Inject a fixture trade route (no Spansh) and drive the journal evidence it follows."""
    from datetime import datetime, timezone
    from modules.personal import plan as planning
    personal, now = core.modules['personal'], datetime.now(timezone.utc).isoformat()
    stop = lambda mid, station, system, x, price, volume: {'market_id': mid, 'station': station, 'system': system, 'pad': 'L',
        'arrival_ls': 100, 'observed_at': now, 'price': price, 'volume': volume, 'pos': [x, 0, 0]}
    hostile = '<img src=x onerror=alert(1)>'
    step = q.get('step', 'select')
    if step == 'select':
        ship = core.store.get('journal', 'ship_info') or {}
        core.store.update('journal', {'cargo_capacity': 100, 'ship_info': {**ship, 'cargo_capacity': 100}})
        legs = [{'commodity': 'Gold', 'quantity': 100, 'buy': stop(1, 'Port 1', 'Sol', 0, 100, 1000), 'sell': stop(2, hostile, 'Alpha', 39, 400, 1000), 'per_ton': 300, 'profit': 30000, 'cost': 10000},
                {'commodity': 'Silver', 'quantity': 100, 'buy': stop(2, hostile, 'Alpha', 39, 200, 1000), 'sell': stop(1, 'Port 1', 'Sol', 0, 300, 1000), 'per_ton': 100, 'profit': 10000, 'cost': 20000}]
        row = {'legs': legs, 'route_type': 'round_trip', 'quantity': 100, 'commodity': 'Gold', 'profit': 40000, 'cost': 30000, 'required_credits': 10000,
               'return_on_cost': 133.3, 'per_ton': 400, 'distance': 39.0, 'total_distance': 78.0, 'estimated_jumps': 2}
        row['id'] = planning.route_id(row)
        personal.search.last, personal.search.last_source = {row['id']: row}, 'Fixture markets'
        return personal.plan.select({'id': row['id']})
    if step == 'dock_buy':
        core.bus.emit('journal.Docked', {'event': 'Docked', 'timestamp': now, 'StarSystem': 'Sol', 'StationName': 'Port 1', 'MarketID': 1})
    elif step in ('market_buy', 'market_wrong', 'market_missing'):
        core.bus.emit('journal.file.Market', {'timestamp': now, 'event': 'Market', 'MarketID': 99 if step == 'market_wrong' else 1,
            'StarSystem': 'Sol', 'StationName': 'Port 1', 'Items': [
                *([{'Name': '$gold_name;', 'Name_Localised': 'Gold', 'BuyPrice': 125, 'SellPrice': 0, 'Stock': 120, 'Demand': 0}] if step != 'market_missing' else []),
                {'Name': '$silver_name;', 'Name_Localised': 'Silver', 'BuyPrice': 0, 'SellPrice': 230, 'Stock': 0, 'Demand': 77}]})
    elif step == 'cargo_partial':
        core.bus.emit('journal.file.Cargo', {'Count': 33, 'timestamp': now, 'Inventory': [
            {'Name': 'gold', 'Name_Localised': 'Gold', 'Count': 25},
            {'Name': 'silver', 'Name_Localised': 'Silver', 'Count': 8}]})
    elif step == 'cargo':
        core.bus.emit('journal.file.Cargo', {'Count': 100, 'timestamp': now, 'Inventory': [{'Name': 'gold', 'Name_Localised': 'Gold', 'Count': 100}]})
    return core.store.get('personal')
core.http.route('/audit/trade-plan', trade_plan, method='POST')
def merit_context(q):
    """Synthetic gain with nearby sale, then an unrelated gain."""
    from datetime import datetime, timedelta, timezone
    at = datetime.now(timezone.utc)
    stamp = lambda n: (at + timedelta(seconds=n)).isoformat()
    for event in [
        {'event':'PowerplayJoin','timestamp':stamp(-65),'Power':'Edmund Mahon'},
        {'event':'MarketSell','timestamp':stamp(-60),'Type':'platinum','Type_Localised':'<Platinum>',
         'Count':10,'SellPrice':400000,'TotalSale':4000000},
        {'event':'PowerplayMerits','timestamp':stamp(-58),'Power':'Edmund Mahon','MeritsGained':190,'TotalMerits':190},
        {'event':'PowerplayMerits','timestamp':stamp(-20),'Power':'Edmund Mahon','MeritsGained':30,'TotalMerits':220},
    ]:
        core.bus.emit('journal.' + event['event'], event)
    return core.http.tools['get_powerplay_status'].fn({})
core.http.route('/audit/merit-context', merit_context, method='POST')
core.http.route('/audit/identity', lambda q: {'id': core.modules['party'].party.member_id, 'secret': core.modules['party'].party.secret})
server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(core))
print(server.server_port, flush=True)
print(SETTINGS, flush=True)
server.serve_forever()
