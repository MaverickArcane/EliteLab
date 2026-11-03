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
        assert (app / "runtime" / "pythonw.exe").is_file()
        assert (app / "Launch EliteLab.vbs").is_file()
        assert (app / "elitelab" / "windows_tray.py").is_file()
        assert (app / "elitelab" / "tray_control.py").is_file()
        assert (app / "elitelab" / "autostart.py").is_file()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        system = Path(os.environ["SystemRoot"]) / "System32"
        env = dict(os.environ)
        for key in list(env):
            if key.upper().startswith(("ELITELAB_", "PYTHON")):
                del env[key]
        env["LOCALAPPDATA"] = str(directory / "user-local")
        env.update(PATH=str(system), PYTHONHOME=str(directory / "missing-python"),
                   PYTHONPATH=str(directory / "missing-packages"), ELITELAB_HOST="127.0.0.1",
                   ELITELAB_INSTANCE_DIR=str(directory / "instance"),
                   ELITELAB_SETTINGS=str(directory / "settings.json"),
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
                setup = json.loads(get("/api/setup"))
                data_dir = directory / "user-local" / "EliteLab" / "data"
                assert Path(setup["values"]["data_dir"]) == data_dir, setup
                wishlist = urllib.request.Request(f"http://127.0.0.1:{port}/api/materials/wishlist",
                    data=json.dumps({"items": {"arsenic": 10}}).encode(),
                    headers={"Content-Type": "application/json"})
                with opener.open(wishlist, timeout=2) as response:
                    assert response.status == 200
                assert b"EliteLab" in get("/")
                get("/modules/trade/card.js")
                get("/modules/party/card.js")
                assert b'Round trip' in get("/modules/personal/card.js")
                original_pid = health["pid"]
                request = urllib.request.Request(f"http://127.0.0.1:{port}/api/restart", data=b"{}",
                                                 headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=2) as response:
                    assert json.load(response)["exit_code"] == 75
                deadline = time.monotonic() + 30
                while True:
                    try:
                        restarted = json.loads(get("/api/health"))
                        if restarted.get("ready") and restarted.get("pid") != original_pid:
                            break
                    except (OSError, ValueError):
                        pass
                    assert process.poll() is None and time.monotonic() < deadline, "Bundle failed to restart"
                    time.sleep(.1)
                rows = json.loads(get("/api/materials/wishlist"))["wishlist"]
                assert any(row.get("key") == "arsenic" and row.get("need") == 10 for row in rows), rows
                assert data_dir.is_dir() and not (app / "data").exists()
                # A separate extraction resolves the same per-user folder on upgrade.
                upgrade = directory / "upgrade"
                with zipfile.ZipFile(bundle) as archive:
                    archive.extractall(upgrade)
                upgraded_app = upgrade / "EliteLab"
                resolved = subprocess.check_output(
                    [str(upgraded_app / "runtime" / "python.exe"), "-c",
                     "from elitelab.core import config; print(config.DATA_DIR)"],
                    cwd=upgraded_app, env=env, text=True, creationflags=subprocess.CREATE_NO_WINDOW).strip()
                assert Path(resolved) == data_dir, resolved
                print("Bundle passed: embedded Python, fixture replay, per-user data and launcher restart without system Python on PATH.")
            finally:
                subprocess.run([str(system / "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, nargs="?", default=ROOT / "dist" / "EliteLab-windows-x64.zip")
    smoke(parser.parse_args().bundle)
