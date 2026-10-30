"""Setup module: read, save and restart, against a temp settings file."""
import importlib
import json
import os
import tempfile
import unittest
from unittest import mock

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
                         ({"data_dir": "  "}, "data_dir"), ({"browser": 5}, "browser")):
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
            self.assertEqual(str(cm.exception), "Only journal_dir, port, host, data_dir and browser can be saved here.")
        self.assertEqual(self.file()["connections"], {"inara": {}})

    def test_restart_tool_requests_restart(self):
        with mock.patch.object(self.core, "request_restart") as m:
            r = self.call("restart_elitelab")
        self.assertEqual(r, {"restarting": True, "exit_code": 75})
        m.assert_called_once_with()

    def test_tools_have_descriptions(self):
        for name in ("get_setup", "save_setup", "restart_elitelab"):
            self.assertTrue(self.core.http.tools[name].schema()["description"].strip(), name)


if __name__ == "__main__":
    unittest.main()
