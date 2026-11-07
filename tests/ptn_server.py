"""Real EliteLab HTTP/SSE with offline PTN provider and journal fixtures."""
from http.server import ThreadingHTTPServer
from test_ptn import PTNTests
from elitelab.core.http import make_handler

fixture = PTNTests()
fixture.setUp()
core = fixture.core


def visit(q):
    side = q.get('side','buy')
    return fixture.capture(side)


def move(q):
    fixture.carrier(system=q.get('system','Source'))
    return fixture.desk.view()


core.http.route('/audit/ptn/visit',visit,method='POST')
core.http.route('/audit/ptn/move',move,method='POST')
server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(core))
print(server.server_port,flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    fixture.doCleanups()
