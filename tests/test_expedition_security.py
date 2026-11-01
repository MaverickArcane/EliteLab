"""Adversarial checks for the HTTP and community-API trust boundaries."""
import io
import gzip
import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

import unittest
import test_regressions as transport
from elitelab.core import config
from elitelab.core.http import Route
from elitelab.core.services import read_json, MAX_RESPONSE_BYTES
from elitelab.core import coriolis


class ExpeditionSecurityTests(unittest.TestCase):
    def setUp(self):
        transport.IsolatedCoreTests.setUp(self)
        self.server = transport.ThreadingHTTPServer(("127.0.0.1", 0), transport.make_handler(self.core))
        self.server.daemon_threads = True
        self.thread = transport.threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port

    request = transport.TransportTests.request
    call = transport.IsolatedCoreTests.call

    def test_dns_rebinding_rejected_even_with_matching_origin(self):
        body = json.dumps({"items": {"iron": 1}})
        headers = {"Host":"rebind.attacker.example", "Origin":"http://rebind.attacker.example", "Content-Type":"application/json"}
        self.assertEqual(self.request("POST", "/api/materials/wishlist", body, headers)[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"Host":"rebind.attacker.example"})[0], 403)
        with patch.object(config, "ALLOWED_HOSTS", {"lab.example"}):
            self.assertEqual(self.request("GET", "/api/health", headers={"Host":"lab.example"})[0], 200)
        for host in ["localhost@evil.example", "localhost/evil", "localhost:bad", "evil.example#localhost"]:
            with self.subTest(host=host):
                self.assertEqual(self.request("GET", "/api/health", headers={"Host":host})[0], 403)

    def test_framing_and_cross_site_api_read_rejected(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"Sec-Fetch-Site":"cross-site"})[0], 403)
        for headers in [{"Content-Length":"invalid"}, {"Content-Length":"-1"}, {"Content-Length":"1000001"}, {"Transfer-Encoding":"chunked"}]:
            with self.subTest(headers=headers):
                status, _ = self.request("POST", "/api/synthesis/plan", "{}", {"Content-Type":"application/json", **headers})
                self.assertEqual(status, 400)

    def test_auth_covers_new_endpoints_and_error_redaction(self):
        with patch.object(config, "AUTH_TOKEN", "fixture-secret"):
            for path in ["/api/neutron/route", "/api/synthesis/status", "/api/synthesis/recipes"]:
                self.assertEqual(self.request("GET", path)[0], 401)
                self.assertEqual(self.request("GET", path, headers={"Authorization":"Bearer fixture-secret"})[0], 200)
        def failure(q):
            raise RuntimeError("private C:/secret/token.txt")
        self.core.http.route("/api/fixture-failure", failure)
        with patch.object(self.core.log, "exception") as log:
            status, body = self.request("GET", "/api/fixture-failure")
            log.assert_called_once()
        self.assertEqual(status, 500)
        self.assertNotIn(b"token.txt", body)

    def test_external_json_bounded_and_schema_preserves_array_items(self):
        with self.assertRaises(ValueError):
            read_json(io.BytesIO(b" " * (MAX_RESPONSE_BYTES + 1)))
        self.assertEqual(read_json(io.BytesIO(b'{"ok":true}')), {"ok":True})
        schema = self.core.http.tools["plan_synthesis"].schema()["input_schema"]
        self.assertEqual(schema["properties"]["items"]["items"]["required"], ["key"])
        self.assertIn("items", schema["required"])

    def test_static_symlink_cannot_escape_root(self):
        base = Path(self.tmp.name) / "static"
        base.mkdir()
        secret = Path(self.tmp.name) / "outside.txt"
        secret.write_text("private")
        try:
            (base / "escape.txt").symlink_to(secret)
        except OSError:
            self.skipTest("Symlinks require privileges on this Windows installation")
        self.core.http.mount("/audit-static", str(base))
        self.assertEqual(self.request("GET", "/audit-static/escape.txt")[0], 404)

    def test_compressed_build_bomb_rejected_before_parsing(self):
        data = base64.b64encode(gzip.compress(b"x" * (coriolis.MAX_MODIFICATION_BYTES + 1))).decode()
        with patch.object(coriolis, "_parse_mods") as parser, self.assertRaises(ValueError):
            coriolis._mods(data)
        parser.assert_not_called()
