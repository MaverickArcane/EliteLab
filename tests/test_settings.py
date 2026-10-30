"""Settings file: location, load/save, and precedence env over file over default."""
import importlib
import json
import logging
import os
import tempfile
import threading
import unittest
from unittest import mock

from test_elitelab import config


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="elitelab-settings-")
        self.path = os.path.join(self.tmp, "sub", "settings.json")
        saved = dict(os.environ)
        self.addCleanup(self._restore, saved)

    def _restore(self, saved):
        os.environ.clear()
        os.environ.update(saved)
        importlib.reload(config)

    def _reload(self, env=None, file_data=None):
        """Reload config with a clean ELITELAB_* environment plus env, and a settings file."""
        for k in [k for k in os.environ if k.startswith("ELITELAB_")]:
            del os.environ[k]
        os.environ["ELITELAB_OFFLINE"] = "1"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if file_data is not None:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(file_data, f)
        os.environ["ELITELAB_SETTINGS"] = self.path
        os.environ.update(env or {})
        return importlib.reload(config)

    def test_settings_path_prefers_env_override(self):
        with mock.patch.dict(os.environ, {"ELITELAB_SETTINGS": "/x/y.json"}):
            self.assertEqual(config.settings_path(), "/x/y.json")

    def test_settings_path_windows_and_xdg(self):
        env = {k: v for k, v in os.environ.items() if k != "ELITELAB_SETTINGS"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(config.os, "name", "nt"), mock.patch.dict(os.environ, {"APPDATA": "C:\\Roam"}):
                self.assertEqual(config.settings_path(), os.path.join("C:\\Roam", "EliteLab", "settings.json"))
            with mock.patch.object(config.os, "name", "posix"), mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/xdg"}):
                self.assertEqual(config.settings_path(), os.path.join("/xdg", "elitelab", "settings.json"))
        with mock.patch.dict(os.environ, env, clear=True):
            os.environ.pop("XDG_CONFIG_HOME", None)
            with mock.patch.object(config.os, "name", "posix"):
                self.assertEqual(config.settings_path(),
                                 os.path.join(os.path.expanduser("~"), ".config", "elitelab", "settings.json"))

    def test_missing_file_loads_empty(self):
        self.assertEqual(config.load_settings(self.path), {})

    def test_invalid_json_and_non_object_load_empty_with_one_warning(self):
        os.makedirs(os.path.dirname(self.path))
        logging.disable(logging.NOTSET)         # test_elitelab silences logging globally
        self.addCleanup(logging.disable, logging.CRITICAL)
        for text in ("{bad", "[1,2]"):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(text)
            with self.assertLogs("elitelab.config", level="WARNING") as cm:
                self.assertEqual(config.load_settings(self.path), {})
            self.assertEqual(len(cm.records), 1)

    def test_save_merges_preserves_unknown_keys_and_connections(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"port": 8766, "future": 1, "connections": {"inara": {"k": "v"}}}, f)
        merged = config.save_settings({"port": 8767}, self.path)
        self.assertEqual(merged, {"port": 8767, "future": 1, "connections": {"inara": {"k": "v"}}})
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), merged)
        self.assertFalse(os.path.exists(self.path + ".tmp"))

    def test_save_creates_parent_dir(self):
        self.assertFalse(os.path.isdir(os.path.dirname(self.path)))
        self.assertEqual(config.save_settings({"host": "0.0.0.0"}, self.path), {"host": "0.0.0.0"})
        self.assertTrue(os.path.isfile(self.path))

    def test_precedence_flag_env_file_default(self):
        c = self._reload(env={"ELITELAB_PORT": "9000"}, file_data={"port": 8767})
        self.assertEqual((c.PORT, c.SOURCES["port"]), (9000, "env"))
        c = self._reload(file_data={"port": 8767})
        self.assertEqual((c.PORT, c.SOURCES["port"]), (8767, "file"))
        os.remove(self.path)
        c = self._reload()
        self.assertEqual((c.PORT, c.SOURCES["port"]), (8766, "default"))
        self.assertEqual(c.RESTART_EXIT_CODE, 75)
        self.assertEqual(c.BROWSER, "")
        self.assertEqual(c.SETTINGS_PATH, self.path)

    def test_string_port_in_file_is_cast_and_bad_port_falls_back(self):
        c = self._reload(file_data={"port": "8767"})
        self.assertEqual((c.PORT, c.SOURCES["port"]), (8767, "file"))
        c = self._reload(file_data={"port": 80})
        self.assertEqual((c.PORT, c.SOURCES["port"]), (8766, "default"))

    def test_data_dir_and_journal_dir_expand_user(self):
        c = self._reload(file_data={"journal_dir": "~/j", "data_dir": "~/d"})
        self.assertEqual(c.JOURNAL_DIR, os.path.abspath(os.path.expanduser("~/j")))
        self.assertEqual(c.DATA_DIR, os.path.abspath(os.path.expanduser("~/d")))
        self.assertEqual(c.SOURCES["journal_dir"], "file")


    def _logs(self):
        logging.disable(logging.NOTSET)         # test_elitelab silences logging globally
        self.addCleanup(logging.disable, logging.CRITICAL)

    def test_concurrent_saves_both_land(self):
        os.makedirs(os.path.dirname(self.path))
        real = config.load_settings
        gate = threading.Barrier(2, timeout=1)

        def slow_load(path):
            data = real(path)
            try:
                gate.wait()                     # without the lock both threads read before either writes
            except threading.BrokenBarrierError:
                pass
            return data
        with mock.patch.object(config, "load_settings", slow_load):
            threads = [threading.Thread(target=config.save_settings, args=({k: v}, self.path))
                       for k, v in (("port", 8767), ("host", "0.0.0.0"))]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"port": 8767, "host": "0.0.0.0"})
        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["settings.json"])     # no temp files left

    def test_saving_over_a_corrupt_file_keeps_it_as_bad(self):
        self._logs()
        os.makedirs(os.path.dirname(self.path))
        with open(self.path + ".bad", "w", encoding="utf-8") as f:
            f.write("older")
        for text in ("{bad", "[1,2]"):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(text)
            with self.assertLogs("elitelab.config", level="WARNING") as cm:
                self.assertEqual(config.save_settings({"port": 8767}, self.path), {"port": 8767})
            self.assertTrue(any(self.path + ".bad" in r.getMessage() for r in cm.records), cm.output)
            with open(self.path + ".bad", encoding="utf-8") as f:
                self.assertEqual(f.read(), text)
            with open(self.path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"port": 8767})

    def test_saving_over_an_empty_object_makes_no_backup(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{}")
        config.save_settings({"port": 8767}, self.path)
        self.assertFalse(os.path.exists(self.path + ".bad"))

    def test_invalid_host_in_file_falls_back_to_default_with_a_warning(self):
        self._logs()
        for bad in ("::1", "bad host!", 5, "999.1.1.1"):
            with self.assertLogs("elitelab.config", level="WARNING") as cm:
                c = self._reload(file_data={"host": bad})
            self.assertEqual((c.HOST, c.SOURCES["host"]), ("127.0.0.1", "default"), bad)
            self.assertTrue(any("host" in r.getMessage() for r in cm.records), cm.output)
        for good in ("0.0.0.0", "192.168.1.5", "localhost", "lab.example"):
            c = self._reload(file_data={"host": good})
            self.assertEqual((c.HOST, c.SOURCES["host"]), (good, "file"))

    def test_empty_host_env_means_the_default(self):
        c = self._reload(env={"ELITELAB_HOST": ""})
        self.assertEqual((c.HOST, c.SOURCES["host"]), ("127.0.0.1", "default"))

    def test_allowed_hosts_env_is_a_lower_case_set(self):
        c = self._reload(env={"ELITELAB_ALLOWED_HOSTS": " Lab.Lan, nas.local ,,"})
        self.assertEqual(c.ALLOWED_HOSTS, {"lab.lan", "nas.local"})

if __name__ == "__main__":
    unittest.main()
