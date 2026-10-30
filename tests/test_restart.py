"""Cooperative restart: exit status 75, --settings, and the start script loop."""
import contextlib
import io
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from test_elitelab import Core, config, ROOT  # noqa: F401  (imports first: sets the test environment)


class _TmpMixin:
    def _tmp(self):
        d = tempfile.TemporaryDirectory(prefix="elitelab-test-")
        self.addCleanup(d.cleanup)
        return d.name


class StartReturnTests(_TmpMixin, unittest.TestCase):
    def _run(self, action):
        tmp = self._tmp()
        result = {}
        def serve():
            with contextlib.redirect_stdout(io.StringIO()):
                result.update(rc=core.start("127.0.0.1", 0))
        with mock.patch.object(config, "DATA_DIR", tmp):
            core = Core()
            t = threading.Thread(target=serve, daemon=True)
            t.start()
            deadline = time.time() + 5
            while time.time() < deadline and not core.ready:
                time.sleep(0.02)
            self.assertTrue(core.ready)
            action(core)
            t.join(5)
            self.assertFalse(t.is_alive(), "start() did not return")
        self.assertFalse(core.ready)
        return result["rc"]

    def test_restart_requested_before_start_is_not_lost(self):
        tmp = self._tmp()
        result = {}

        def serve():
            with contextlib.redirect_stdout(io.StringIO()):
                result.update(rc=core.start("127.0.0.1", 0))
        with mock.patch.object(config, "DATA_DIR", tmp):
            core = Core()
            core.request_restart()
            time.sleep(0.3)   # the stop timer fires while nothing is bound
            t = threading.Thread(target=serve, daemon=True)
            t.start()
            t.join(5)
            self.assertFalse(t.is_alive(), "start() ignored a restart requested before the bind")
        self.assertEqual(result["rc"], 75)

    def test_start_returns_75_after_request_restart(self):
        self.assertEqual(self._run(lambda c: c.request_restart()), 75)

    def test_start_returns_0_on_normal_stop(self):
        self.assertEqual(self._run(lambda c: c._server.stop()), 0)

    def test_port_in_use_prints_one_plain_line_and_returns_non_zero(self):
        tmp = self._tmp()
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        self.addCleanup(busy.close)
        port = busy.getsockname()[1]
        out = io.StringIO()
        with mock.patch.object(config, "DATA_DIR", tmp), mock.patch.dict(config.SOURCES, {"host": "file", "port": "env"}):
            core = Core()
            with contextlib.redirect_stdout(out):
                rc = core.start("127.0.0.1", port)
        self.assertNotIn(rc, (0, config.RESTART_EXIT_CODE))
        self.assertFalse(core.ready)
        lines = [l for l in out.getvalue().splitlines() if "127.0.0.1" in l and str(port) in l]
        self.assertEqual(len(lines), 1, out.getvalue())
        for part in ("host from settings file", "port from environment variable", config.SETTINGS_PATH):
            self.assertIn(part, lines[0])
        self.assertNotIn("listening on", out.getvalue())


class MainSettingsTests(_TmpMixin, unittest.TestCase):
    def test_main_settings_flag_sets_env_before_import(self):
        tmp = self._tmp()
        path = os.path.join(tmp, "s.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"port": 8799}, f)
        env = dict(os.environ)
        env.pop("ELITELAB_PORT", None)
        env["ELITELAB_SETTINGS"] = os.path.join(tmp, "other.json")   # the flag must win over this
        r = subprocess.run([sys.executable, "-m", "elitelab", "--settings", path, "modules"],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        env["ELITELAB_SETTINGS"] = path
        r = subprocess.run([sys.executable, "-c", "from elitelab.core import config; print(config.PORT)"],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "8799", r.stderr)


class LauncherTests(unittest.TestCase):
    def test_windows_launcher_runs_the_loop_by_relative_path(self):
        # cmd /c strips the outer quotes of "%~dp0scripts\serve-loop.cmd" and breaks on paths with parentheses;
        # the launcher already cd's to its own folder, so a relative path needs no quotes.
        with open(os.path.join(ROOT, "Start EliteLab.cmd"), encoding="ascii") as f:
            text = f.read()
        self.assertIn('cd /d "%~dp0"', text)
        self.assertIn("cmd /c scripts\\serve-loop.cmd", text)
        self.assertNotIn("%~dp0scripts", text)

@unittest.skipUnless(os.name == "posix", "start.sh is a POSIX shell script")
class StartShTests(_TmpMixin, unittest.TestCase):
    def _run(self, codes):
        tmp = self._tmp()
        log = os.path.join(tmp, "log")
        counter = os.path.join(tmp, "n")
        fake = os.path.join(tmp, "python3")
        codes_s = " ".join(str(c) for c in codes)
        with open(fake, "w") as f:
            f.write(f"""#!/bin/sh
echo "$@" >> "{log}"
n=$(cat "{counter}" 2>/dev/null || echo 0)
n=$((n+1))
echo $n > "{counter}"
i=0
for c in {codes_s}; do
  i=$((i+1))
  [ "$i" -eq "$n" ] && exit "$c"
done
exit 0
""")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"])
        r = subprocess.run(["sh", os.path.join(ROOT, "start.sh"), "serve"], env=env, timeout=30)
        with open(log) as f:
            return r.returncode, f.read().splitlines()

    def test_start_sh_restarts_on_75_and_stops_otherwise(self):
        rc, lines = self._run([75, 0])
        self.assertEqual((rc, len(lines)), (0, 2))
        rc, lines = self._run([1])
        self.assertEqual((rc, len(lines)), (1, 1))


if __name__ == "__main__":
    unittest.main()
