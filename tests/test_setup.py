"""Setup module: read, save and restart, against a temp settings file."""
import importlib
import http.client
import json
import os
import socket
import threading
from http.server import ThreadingHTTPServer
import tempfile
import unittest
from unittest import mock

from test_elitelab import config, make_core  # first: sets ELITELAB_SETTINGS and the fixtures before config is imported
from elitelab.core.http import make_handler  # noqa: E402


IMPORT_SETTINGS_PATH = config.SETTINGS_PATH      # what config read when this module imported it


class HermeticImportTests(unittest.TestCase):
    def test_config_was_first_imported_with_the_test_settings_file(self):
        self.assertTrue(os.path.realpath(IMPORT_SETTINGS_PATH).startswith(os.path.realpath(tempfile.gettempdir())),
                        IMPORT_SETTINGS_PATH)

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
        self.assertEqual(len([w for w in r["warnings"] if "Folder does not exist yet" in w]), 1)
        self.assertTrue(r["restart_required"])

    def test_env_and_flag_sources_warn_that_the_save_will_not_apply(self):
        with mock.patch.dict(config.SOURCES, {"journal_dir": "env", "host": "flag", "data_dir": "file"}):
            r = self.call("save_setup", journal_dir=self.tmp, host="0.0.0.0", data_dir=self.tmp)
        self.assertIn("ELITELAB_JOURNAL_DIR is set, so this value will not apply until it is unset.", r["warnings"])
        self.assertIn("The --host flag is set, so this value will not apply until it is removed.", r["warnings"])
        self.assertFalse([w for w in r["warnings"] if "DATA_DIR" in w], r["warnings"])
        with mock.patch.dict(config.SOURCES, {"port": "env"}):
            r = self.call("save_setup", port=8768)
        self.assertIn("ELITELAB_PORT is set, so this value will not apply until it is unset.", r["warnings"])
        with mock.patch.dict(config.SOURCES, {"journal_dir": "flag"}):
            r = self.call("save_setup", journal_dir=self.tmp + "/other")
        self.assertIn("The --journals flag is set, so this value will not apply until it is removed.", r["warnings"])

    def test_port_change_warns_about_the_launcher(self):
        r = self.call("save_setup", port=8767)
        self.assertIn(f"The launcher and ELITELAB_URL still point at port {config.PORT}; update them if you use them.",
                      r["warnings"])
        r = self.call("save_setup", host="0.0.0.0")
        self.assertFalse([w for w in r["warnings"] if "launcher" in w])

    def test_unwritable_settings_file_is_a_plain_error(self):
        os.makedirs(self.path)                              # a folder where the file should be
        with self.assertRaises(ValueError) as cm:
            self.call("save_setup", port=8767)
        self.assertTrue(str(cm.exception).startswith(f"Could not write the settings file at {self.path}: "), cm.exception)
        self.assertEqual(os.listdir(self.path), [])
        self.assertEqual(os.listdir(self.tmp), ["settings.json"])     # no temp file left behind

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores folder permissions")
    @unittest.skipIf(os.name == "nt", "chmod does not make a folder read-only on Windows")
    def test_read_only_folder_is_a_plain_error(self):
        os.chmod(self.tmp, 0o500)
        self.addCleanup(os.chmod, self.tmp, 0o700)
        with self.assertRaises(ValueError) as cm:
            self.call("save_setup", port=8767)
        self.assertTrue(str(cm.exception).startswith(f"Could not write the settings file at {self.path}: "), cm.exception)

    def test_port_in_use_is_refused_and_writes_nothing(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        self.addCleanup(busy.close)
        port = busy.getsockname()[1]
        with mock.patch.object(config, "HOST", "127.0.0.1"):
            with self.assertRaises(ValueError) as cm:
                self.call("save_setup", port=port)
        self.assertEqual(str(cm.exception), f"Port {port} is already in use on 127.0.0.1.")
        self.assertFalse(os.path.exists(self.path))

    def test_host_change_on_the_running_port_is_not_refused(self):
        busy = socket.socket()                                  # stands in for this lab's own listening socket
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        self.addCleanup(busy.close)
        with mock.patch.object(config, "HOST", "127.0.0.1"), mock.patch.object(config, "PORT", busy.getsockname()[1]):
            r = self.call("save_setup", host="0.0.0.0")
        self.assertEqual(r["saved"], ["host"])

    def test_address_not_on_this_machine_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            self.call("save_setup", host="192.0.2.1")           # TEST-NET-1, never assigned
        self.assertIn("192.0.2.1", str(cm.exception))
        self.assertFalse(os.path.exists(self.path))

    def test_ipv6_host_is_refused_with_a_plain_message(self):
        for host in ("::1", "fe80::1"):
            with self.assertRaises(ValueError) as cm:
                self.call("save_setup", host=host)
            self.assertEqual(str(cm.exception),
                             "host must be an IPv4 address such as 127.0.0.1 or 0.0.0.0, or a host name such as localhost.")

    def test_save_rejects_bad_values(self):
        for q, field in (({"port": 80}, "port"), ({"port": "x"}, "port"), ({"port": True}, "port"),
                         ({"host": "::1"}, "host"), ({"host": "bad host!"}, "host"), ({"journal_dir": ""}, "journal_dir"),
                         ({"data_dir": "  "}, "data_dir")):
            with self.assertRaises(ValueError, msg=q) as cm:
                self.call("save_setup", **q)
            self.assertIn(field, str(cm.exception))
        self.assertFalse(os.path.exists(self.path))

    def test_bad_value_blocks_the_whole_save(self):
        with self.assertRaises(ValueError):
            self.call("save_setup", port=8767, host="::1")
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

    def test_inspect_journal_folder_describes_a_typed_path(self):
        fixtures = config.JOURNAL_DIR
        r = self.call("inspect_journal_folder", path=fixtures + os.sep)
        self.assertEqual(r["path"], os.path.normpath(fixtures))
        self.assertTrue(r["exists"])
        self.assertGreater(r["journals"], 0)
        self.assertTrue(r["newest"])
        self.assertEqual(self.call("inspect_journal_folder", path=os.path.join(self.tmp, "none")),
                         {"path": os.path.join(self.tmp, "none"), "exists": False, "journals": 0, "newest": None})
        with self.assertRaises(ValueError) as cm:
            self.call("inspect_journal_folder", path="  ")
        self.assertEqual(str(cm.exception), "path is required.")
        route = self.core.http.tools["inspect_journal_folder"]
        self.assertEqual((route.path, route.method), ("/api/setup/journals", "GET"))
        self.assertIn("path", route.schema()["input_schema"]["required"])

    def test_tools_have_descriptions(self):
        for name in ("get_setup", "save_setup", "restart_elitelab", "inspect_journal_folder"):
            self.assertTrue(self.core.http.tools[name].schema()["description"].strip(), name)


class HostCheckTests(unittest.TestCase):
    """Without a token, POST routes only answer to IP literals, loopback names, the bind host, this machine's name and
    ELITELAB_ALLOWED_HOSTS, on every bind (DNS rebinding needs a DNS name)."""

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

    def request(self, method, host, origin=None, body=b'{"port": 8767}', headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host, **(headers or {})}
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

    def post(self, host, **kw):
        return self.request("POST", host, "http://" + host, body=b"{}", **kw)

    def test_attacker_name_is_refused_on_an_all_interfaces_bind(self):
        host = f"attacker.example:{self.port}"
        with mock.patch.object(config, "HOST", "0.0.0.0"):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            conn.request("POST", "/api/setup", body=b"{}", headers={"Host": host, "Content-Type": "application/json"})
            r = conn.getresponse()
            body = json.loads(r.read())
            conn.close()
        self.assertEqual(r.status, 403)
        self.assertEqual(body, {"error": "requests for host attacker.example are not accepted; "
                                         "set ELITELAB_ALLOWED_HOSTS=attacker.example to allow it"})

    def test_ip_literals_are_accepted_on_any_bind(self):
        for bind in ("0.0.0.0", "127.0.0.1", "192.168.1.5"):
            with mock.patch.object(config, "HOST", bind):
                for host in (f"192.168.1.20:{self.port}", "192.168.1.20", f"[::1]:{self.port}", "[::1]",
                             f"[fe80::1]:{self.port}", f"127.0.0.1:{self.port}"):
                    self.assertEqual(self.post(host), 200, (bind, host))

    def test_machine_hostname_is_accepted_without_dns(self):
        from elitelab.core import http as core_http
        core_http.machine_name.cache_clear()
        self.addCleanup(core_http.machine_name.cache_clear)
        no_dns = AssertionError("no DNS lookups in the Host rule")
        with mock.patch.object(config, "HOST", "0.0.0.0"), \
                mock.patch("socket.gethostname", return_value="Lab-PC") as hostname, \
                mock.patch("socket.getfqdn", side_effect=no_dns), \
                mock.patch("socket.gethostbyaddr", side_effect=no_dns):   # getaddrinfo stays: the test client needs it
            for name in ("lab-pc", "LAB-PC", "Lab-PC."):
                self.assertEqual(self.post(f"{name}:{self.port}"), 200, name)
            self.assertEqual(self.post(f"lab-pc.example.com:{self.port}"), 403)    # an FQDN needs ELITELAB_ALLOWED_HOSTS
        self.assertEqual(hostname.call_count, 1)                                     # computed once, on first use

    def test_importing_http_does_no_lookups(self):
        import importlib as il
        from elitelab.core import http as core_http
        boom = AssertionError("lookup at import")
        with mock.patch("socket.gethostname", side_effect=boom), mock.patch("socket.getfqdn", side_effect=boom):
            il.reload(core_http)
        self.addCleanup(il.reload, core_http)

    def test_named_bind_host_is_accepted(self):
        with mock.patch.object(config, "HOST", "lab.example"):
            self.assertEqual(self.post(f"LAB.example:{self.port}"), 200)
        with mock.patch.object(config, "HOST", "0.0.0.0"):
            self.assertEqual(self.post(f"0.0.0.0:{self.port}"), 200)     # an IP literal, not the bind exemption

    def test_allow_listed_name_is_accepted(self):
        with mock.patch.object(config, "HOST", "0.0.0.0"), mock.patch.object(config, "ALLOWED_HOSTS", {"lab.lan"}):
            self.assertEqual(self.post(f"Lab.Lan:{self.port}"), 200)
            self.assertEqual(self.post(f"other.lan:{self.port}"), 403)

    def test_malformed_hosts_are_refused(self):
        for host in ("", "[::1", "::1", "[::1]x", "[nothost]:80", "a:b:c"):
            self.assertEqual(self.post(host), 403, host)

    def test_any_host_is_accepted_with_a_valid_token(self):
        with mock.patch.object(config, "HOST", "0.0.0.0"), mock.patch.object(config, "AUTH_TOKEN", "s3cret"):
            self.assertEqual(self.post(f"attacker.example:{self.port}", headers={"Authorization": "Bearer s3cret"}), 200)
            self.assertEqual(self.post(f"attacker.example:{self.port}"), 401)

    def get_path(self, path, header="Content-Type"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        r = conn.getresponse()
        body = r.read().decode("utf-8", "replace")
        ctype = r.getheader(header, "")
        conn.close()
        return r.status, ctype, body

    def test_mount_without_trailing_slash_redirects(self):
        status, location, _ = self.get_path("/setup", header="Location")
        self.assertIn(status, (301, 302))
        self.assertEqual(location, "/setup/")
        self.assertEqual(self.get_path("/setupx")[0], 404)

    def test_inspect_journal_folder_over_http(self):
        import urllib.parse
        status, _, body = self.get_path("/api/setup/journals?path=" + urllib.parse.quote(config.JOURNAL_DIR))
        self.assertEqual(status, 200)
        self.assertGreater(json.loads(body)["journals"], 0)

    def test_setup_page_is_served(self):
        status, ctype, body = self.get_path("/setup/")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"), ctype)
        self.assertIn("data-setup-form", body)
        self.assertIn("Connections", body)
        self.assertEqual(self.get_path("/setup/setup.js")[0], 200)
        self.assertEqual(self.get_path("/setup/../module.py")[0], 404)


class MainFlagTests(unittest.TestCase):
    """serve --host/--port are written back to config before the Core starts, like --journals."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="elitelab-flags-")
        saved = dict(os.environ)
        self.addCleanup(SetupTests._restore, self, saved)
        os.environ["ELITELAB_SETTINGS"] = os.path.join(self.tmp, "settings.json")
        importlib.reload(config)

    def _main(self, *argv):
        """Run main() with Core.start replaced by a probe that loads modules and serves one test server."""
        from elitelab import __main__ as cli
        from elitelab.core import Core, loader
        seen = {}

        def fake_start(core, host=None, port=None):
            loader.load_all(core)
            seen["setup"] = core.http.tools["get_setup"].fn({})
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(core))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                for name in ("192.168.1.20", "lab.example"):
                    host = f"{name}:{server.server_address[1]}"
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                    conn.request("POST", "/api/setup", body=b"{}",
                                 headers={"Host": host, "Origin": "http://" + host, "Content-Type": "application/json"})
                    r = conn.getresponse(); r.read(); conn.close()
                    seen[name] = r.status
            finally:
                server.shutdown(); server.server_close()
            return 0
        with mock.patch.object(Core, "start", fake_start), mock.patch("logging.basicConfig"):
            self.assertEqual(cli.main(list(argv)), 0)
        return seen

    def test_host_and_port_flags_are_reported_with_source_flag(self):
        seen = self._main("serve", "--host", "0.0.0.0", "--port", "8791")
        self.assertEqual((config.HOST, config.PORT), ("0.0.0.0", 8791))
        self.assertEqual((seen["setup"]["values"]["host"], seen["setup"]["values"]["port"]), ("0.0.0.0", 8791))
        self.assertEqual((seen["setup"]["sources"]["host"], seen["setup"]["sources"]["port"]), ("flag", "flag"))
        self.assertEqual(seen["192.168.1.20"], 200)       # a LAN device reaching a 0.0.0.0 bind by IP

    def test_named_host_flag_is_the_bind_host_for_the_host_rule(self):
        seen = self._main("serve", "--host", "lab.example")
        self.assertEqual(seen["lab.example"], 200)
        self.assertEqual(seen["setup"]["sources"]["host"], "flag")
        self.assertNotEqual(seen["setup"]["sources"]["port"], "flag")

if __name__ == "__main__":
    unittest.main()
