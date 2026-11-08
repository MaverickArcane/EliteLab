"""PTN security boundaries through the real HTTP handler, with offline providers."""
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import test_ptn as fixtures
from elitelab.core.http import make_handler


class PTNSecurityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PTNTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.core=self.fixture.core
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.core))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(5)

    def request(self,path,body=None,headers=None):
        raw=json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(self.base+path,data=raw,
            headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(request,timeout=5) as response:
                return response.status,dict(response.headers),json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code,dict(error.headers),json.load(error)

    def test_token_protects_reads_searches_and_plan_writes(self):
        with patch.object(fixtures.config,'AUTH_TOKEN','ptn-test-token'):
            for path,body in (('/api/ptn',None),('/api/ptn/search',None),
                              ('/api/ptn/select',{'id':'forged','revision':0})):
                self.assertEqual(self.request(path,body)[0],401)
            self.assertEqual(self.request('/api/ptn',headers={'Authorization':'Bearer ptn-test-token'})[0],200)
        self.assertIsNone(self.fixture.desk.results)
        self.assertIsNone(self.fixture.desk.data['plan'])

    def test_csrf_rebinding_and_non_json_forms_cannot_change_plan(self):
        self.fixture.choose()
        before=copy.deepcopy(self.fixture.desk.data)
        body={'revision':before['revision'],'action':'stage','stage':'cancelled'}
        for headers,status in (({'Origin':'https://attacker.invalid'},403),
                               ({'Sec-Fetch-Site':'cross-site'},403),
                               ({'Host':'attacker.invalid'},403),
                               ({'Content-Type':'text/plain'},415)):
            self.assertEqual(self.request('/api/ptn/update',body,headers)[0],status)
        self.assertEqual(self.fixture.desk.data,before)
        self.assertEqual(self.request('/api/ptn/search',headers={'Sec-Fetch-Site':'cross-site'})[0],403)

    def test_unknown_ids_and_party_members_cannot_replace_plan(self):
        self.fixture.choose()
        before=copy.deepcopy(self.fixture.desk.data)
        self.assertEqual(self.request('/api/ptn/select',{'revision':before['revision'],'id':'../../ptn.json'})[0],400)
        self.core.store.set('party','mode','member')
        self.assertEqual(self.request('/api/ptn/update',{'revision':before['revision'],'action':'remaining','remaining':0})[0],400)
        self.assertEqual(self.fixture.desk.data,before)

    def test_bad_search_arguments_are_rejected_before_any_network_or_state_change(self):
        for query in ('quantity=Infinity','breadth=999999','haul_mode=https://127.0.0.1',
                      'min_quantity=-1','payout_target=NaN','allow_partial=yes'):
            with patch.object(self.core.services,'fetch_json',side_effect=AssertionError('no network')):
                self.assertEqual(self.request('/api/ptn/search?'+query)[0],400)
        self.assertFalse(self.fixture.desk.searching)
        self.assertIsNone(self.fixture.desk.results)

    def test_provider_failures_do_not_leak_exception_details(self):
        with patch.object(self.core.services,'fetch_json',side_effect=RuntimeError('secret=test-path')):
            status,_,body=self.request('/api/ptn/board')
        self.assertEqual(status,200)
        self.assertFalse(body['available'])
        self.assertNotIn('secret',json.dumps(body))

    def test_browser_responses_keep_csp_and_nosniff(self):
        status,headers,_=self.request('/api/ptn')
        self.assertEqual(status,200)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertNotIn('Access-Control-Allow-Origin',headers)
