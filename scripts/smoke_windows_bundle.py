"""Extract and launch the Windows bundle with no system Python on PATH."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def smoke(bundle):
    if os.name != "nt":
        raise RuntimeError("The Windows bundle smoke test must run on Windows")
    with tempfile.TemporaryDirectory(prefix="EliteLab bundle test ") as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(directory)
        app = directory / "EliteLab"
        assert not (app / "data").exists(), "Bundle must not contain local state"
        assert not (app / ".env").exists(), "Bundle must not contain credentials"
        assert (app / "runtime" / "LICENSE.txt").is_file()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        system = Path(os.environ["SystemRoot"]) / "System32"
        env = dict(os.environ)
        for key in list(env):
            if key.upper().startswith(("ELITELAB_", "PYTHON")):
                del env[key]
        env.update(PATH=str(system), PYTHONHOME=str(directory / "missing-python"),
                   PYTHONPATH=str(directory / "missing-packages"), ELITELAB_HOST="127.0.0.1",
                   ELITELAB_INSTANCE_DIR=str(directory / "instance"),
                   ELITELAB_OFFLINE="1", ELITELAB_JOURNAL_DIR=str(ROOT / "tests" / "fixtures" / "journals"))
        env["ELITELAB_INSTANCE_DIR"] = str(directory / "instance")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def get(path):
            with opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                return response.read()

        log_path = directory / "startup.log"
        with log_path.open("w") as log:
            process = subprocess.Popen(
                [str(system / "cmd.exe"), "/d", "/c", "call", "Start EliteLab.cmd",
                 "--no-browser", "--port", str(port)], cwd=app, env=env,
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 30
                while True:
                    try:
                        health = json.loads(get("/api/health"))
                        break
                    except (OSError, ValueError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError("Bundle did not start:\n" + log_path.read_text(errors="replace"))
                        time.sleep(0.25)
                assert health["ok"] and {"trade", "party", "personal"}.issubset(health["modules"]), health
                deadline = time.monotonic() + 10
                while True:
                    journal = json.loads(get("/api/journal"))
                    if journal.get("cmdr") == "Testpilot":
                        break
                    assert time.monotonic() < deadline, journal
                    time.sleep(0.1)
                assert b"EliteLab" in get("/")
                get("/modules/trade/card.js")
                get("/modules/party/card.js")
                assert b'Round trip' in get("/modules/personal/card.js")
                print("Bundle passed: launcher, embedded Python, dashboard, modules and fixture journal; no system Python on PATH.")
            finally:
                subprocess.run([str(system / "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, nargs="?", default=ROOT / "dist" / "EliteLab-windows-x64.zip")
    smoke(parser.parse_args().bundle)
