"""Setup module: read, save and restart, against a temp settings file."""
import importlib
import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer
import tempfile
import unittest
from unittest import mock

from elitelab.core.http import make_handler
from test_elitelab import config, make_core


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="elitelab-setup-")
        self.path = os.path.join(self.tmp, "settings.json")
        saved = dict(os.environ)
        self.addCleanup(self._restore, saved)
        os.environ["ELITELAB_SETTINGS"] = self.path
        importlib.reload(config)
        self.core = make_core()
        home = tempfile.mkdtemp(prefix="elitelab-home-")        # candidates must not depend on the real home
        real = os.path.expanduser
        patcher = mock.patch("os.path.expanduser", lambda p: home if p == "~" else real(p))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _restore(self, saved):
        os.environ.clear()
        os.environ.update(saved)
        importlib.reload(config)

    def call(self, name, **q):
        return self.core.http.tools[name].fn(q)

    def file(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_get_setup_reports_values_sources_candidates_and_path(self):
        r = self.call("get_setup")
        self.assertEqual(r["path"], self.path)
        self.assertFalse(r["exists"])
        self.assertEqual(r["values"], {"journal_dir": config.JOURNAL_DIR, "port": config.PORT, "host": config.HOST,
                                       "data_dir": config.DATA_DIR, "browser": config.BROWSER})
        self.assertEqual(set(r["sources"]), {"journal_dir", "port", "host", "data_dir", "browser"})
        self.assertEqual(r["pending"], {})
        self.assertFalse(r["restart_required"])
        self.assertTrue(r["journal_found"])
        sel = [c for c in r["journal_candidates"] if c["selected"]]
        self.assertEqual([c["path"] for c in sel], [config.JOURNAL_DIR])
        self.assertEqual(r["journal_candidates"][0]["path"], config.JOURNAL_DIR)

    def test_save_port_writes_only_that_key_and_flags_restart(self):
        r = self.call("save_setup", port=8767)
        self.assertEqual(self.file(), {"port": 8767})
        self.assertEqual(r["saved"], ["port"])
        self.assertEqual(r["pending"], {"port": 8767})
        self.assertTrue(r["restart_required"])
        self.assertTrue(r["exists"])
        self.assertTrue(self.core.store.get("setup", "restart_required"))
        self.assertEqual(self.core.store.get("setup", "settings_path"), self.path)
        self.assertEqual(config.PORT, r["values"]["port"])       # nothing applied live

    def test_save_same_port_is_not_a_restart(self):
        r = self.call("save_setup", port=config.PORT)
        self.assertEqual(r["saved"], [])
        self.assertFalse(r["restart_required"])
        self.assertEqual(r["pending"], {})

    def test_save_journal_dir_normalises_and_warns_when_missing(self):
        r = self.call("save_setup", journal_dir=self.tmp + "/nope/")
        self.assertEqual(self.file(), {"journal_dir": os.path.join(self.tmp, "nope")})
        self.assertEqual(len(r["warnings"]), 1)
        self.assertIn("Folder does not exist yet", r["warnings"][0])
        self.assertTrue(r["restart_required"])

    def test_save_rejects_bad_values(self):
        for q, field in (({"port": 80}, "port"), ({"port": "x"}, "port"), ({"port": True}, "port"),
                         ({"host": "example.com"}, "host"), ({"journal_dir": ""}, "journal_dir"),
                         ({"data_dir": "  "}, "data_dir")):
            with self.assertRaises(ValueError, msg=q) as cm:
                self.call("save_setup", **q)
            self.assertIn(field, str(cm.exception))
        self.assertFalse(os.path.exists(self.path))

    def test_bad_value_blocks_the_whole_save(self):
        with self.assertRaises(ValueError):
            self.call("save_setup", port=8767, host="example.com")
        self.assertFalse(os.path.exists(self.path))

    def test_connections_and_unknown_keys_survive_a_save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"connections": {"inara": {}}, "future": 1}, f)
        self.call("save_setup", port=8767)
        self.assertEqual(self.file(), {"connections": {"inara": {}}, "future": 1, "port": 8767})
        for q in ({"connections": {"x": {}}}, {"future": 2}):
            with self.assertRaises(ValueError) as cm:
                self.call("save_setup", **q)
            self.assertEqual(str(cm.exception), "Only journal_dir, port, host and data_dir can be saved here.")
        self.assertEqual(self.file()["connections"], {"inara": {}})

    def test_browser_cannot_be_saved_and_an_existing_value_survives(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"browser": "firefox"}, f)
        for value in ("calc.exe", ""):
            with self.assertRaises(ValueError) as cm:
                self.call("save_setup", browser=value)
            self.assertEqual(str(cm.exception), "browser can only be set in the settings file or with ELITELAB_BROWSER.")
        self.call("save_setup", port=8767)
        self.assertEqual(self.file(), {"browser": "firefox", "port": 8767})
        self.assertIn("browser", self.call("get_setup")["values"])

    def test_host_all_interfaces_is_accepted(self):
        r = self.call("save_setup", host="0.0.0.0")
        self.assertEqual(self.file(), {"host": "0.0.0.0"})
        self.assertEqual(r["saved"], ["host"])

    def test_journal_found_is_false_when_the_folder_is_missing(self):
        with mock.patch.object(config, "JOURNAL_DIR", os.path.join(self.tmp, "none")):
            self.assertFalse(self.call("get_setup")["journal_found"])

    def test_restart_tool_requests_restart(self):
        with mock.patch.object(self.core, "request_restart") as m:
            r = self.call("restart_elitelab")
        self.assertEqual(r, {"restarting": True, "exit_code": 75})
        m.assert_called_once_with()

    def test_tools_have_descriptions(self):
        for name in ("get_setup", "save_setup", "restart_elitelab"):
            self.assertTrue(self.core.http.tools[name].schema()["description"].strip(), name)


class HostCheckTests(unittest.TestCase):
    """POST routes on a loopback bind only answer to loopback Host names (DNS rebinding)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="elitelab-host-")
        self.path = os.path.join(self.tmp, "settings.json")
        saved = dict(os.environ)
        self.addCleanup(SetupTests._restore, self, saved)
        os.environ["ELITELAB_SETTINGS"] = self.path
        importlib.reload(config)
        self.core = make_core()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.core))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, host, origin=None, body=b'{"port": 8767}'):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host}
        if method == "POST":
            headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = origin
        conn.request(method, "/api/setup", body=body if method == "POST" else None, headers=headers)
        r = conn.getresponse()
        r.read()
        conn.close()
        return r.status

    def test_post_with_attacker_host_is_refused_and_writes_nothing(self):
        host = f"attacker.example:{self.port}"
        self.assertEqual(self.request("POST", host, "http://" + host), 403)
        self.assertFalse(os.path.exists(self.path))

    def test_post_with_loopback_host_is_accepted(self):
        for name in ("127.0.0.1", "localhost"):
            host = f"{name}:{self.port}"
            self.assertEqual(self.request("POST", host, "http://" + host), 200)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"port": 8767})

    def test_get_is_unaffected_by_the_host_rule(self):
        self.assertEqual(self.request("GET", f"attacker.example:{self.port}"), 200)
        self.assertEqual(self.request("GET", f"127.0.0.1:{self.port}"), 200)

    def test_lan_bind_keeps_todays_behaviour(self):
        host = f"lab.lan:{self.port}"
        with mock.patch.object(config, "HOST", "0.0.0.0"):
            self.assertEqual(self.request("POST", host, "http://" + host, body=b"{}"), 200)


if __name__ == "__main__":
    unittest.main()
