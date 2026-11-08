"""Real EliteLab HTTP/SSE with offline PTN provider and journal fixtures."""
from http.server import ThreadingHTTPServer
import copy
from test_ptn import PTNTests
from elitelab.core.http import make_handler

fixture = PTNTests()
fixture.setUp()
core = fixture.core
original_buy, original_sell = copy.deepcopy(fixture.buy), copy.deepcopy(fixture.sell)


def visit(q):
    side = q.get('side','buy')
    return fixture.capture(side)


def move(q):
    fixture.carrier(system=q.get('system','Source'),free_space=q.get('free_space',25000))
    return fixture.desk.view()


def order(q):
    quantity, price = q.get('quantity', 19898), q.get('price', 24000)
    core.store.set('trade', 'orders', {'liquor': dict(side='buy', price=price,
        quantity=quantity, updated_at=fixture.time())})
    fixture.carrier(system='Source', free_space=0, reserved_space=quantity)
    return fixture.desk.view()


def scenario(q):
    fixture.buy, fixture.sell = copy.deepcopy(original_buy), copy.deepcopy(original_sell)
    if q.get('name')=='ordinary':
        fixture.sell.update(sellPrice=30000,demand=5000)
    if q.get('name')=='unlimited':
        fixture.sell['demand']=0
    if q.get('name')=='surface':
        fixture.buy.update(stationType='OnFootSettlement',isPlanetary=True)
    if q.get('name')=='injection':
        fixture.buy['stationName']='<img src=x onerror="globalThis.ptnInjected=true">'
        fixture.board['missions'][0]['carrier_name']='<svg onload="globalThis.ptnInjected=true">'
    fixture.core.store.update('journal',dict(system='Sol',star_pos=[0,0,0]))
    fixture.carrier(system='Sol')
    return {'ok':True}


core.http.route('/audit/ptn/visit',visit,method='POST')
core.http.route('/audit/ptn/move',move,method='POST')
core.http.route('/audit/ptn/order',order,method='POST')
core.http.route('/audit/ptn/scenario',scenario,method='POST')
server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(core))
print(server.server_port,flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    fixture.doCleanups()
