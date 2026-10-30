"""Recover a real CLI process after abrupt termination, using isolated data."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]


class RestartReliabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="elitelab-restart-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        journals = self.directory / "journals"
        journals.mkdir()
        self.journal = journals / "Journal.restart.log"
        fixture = ROOT / "tests/fixtures/journals/Journal.2026-10-22T100000.01.log"
        shutil.copyfile(fixture, self.journal)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = {k: v for k, v in os.environ.items() if not k.upper().startswith("ELITELAB_")}
        self.env.update(ELITELAB_INSTANCE_DIR=str(self.directory / "instance"),
                        ELITELAB_DATA_DIR=str(self.directory / "data"),
                        ELITELAB_JOURNAL_DIR=str(journals),
                        ELITELAB_OFFLINE="1", ELITELAB_POLL_SECONDS="0.05")
        self.process = None
        self.starts = 0
        self.addCleanup(self.crash)

    def request(self, path, body=None):
        request = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.load(response)

    def wait_for(self, path, predicate):
        deadline = time.monotonic() + 15
        last = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail(self.log.read_text(encoding="utf-8", errors="replace"))
            try:
                last = self.request(path)
            except OSError as error:
                last = str(error)
            else:
                if predicate(last):
                    return last
            time.sleep(.05)
        self.fail(f"Timed out waiting for {path}: {last}")

    def start(self):
        self.starts += 1
        self.log = self.directory / f"server-{self.starts}.log"
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        with self.log.open("w", encoding="utf-8") as output:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "elitelab", "serve", "--no-browser",
                 "--host", "127.0.0.1", "--port", str(self.port)],
                cwd=ROOT, env=self.env, stdout=output, stderr=output, **flags)
        health = self.wait_for("/api/health", lambda value: value.get("ready"))
        self.assertEqual(health["pid"], self.process.pid)

    def crash(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()  # No shutdown endpoint or graceful cleanup.
            self.process.wait(timeout=8)
            self.process = None

    def append(self, text):
        with self.journal.open("ab") as output:
            output.write(text.encode())
            output.flush()
            os.fsync(output.fileno())

    def delivery(self, tonnes):
        return json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                           "event": "MarketSell", "Type": "gold",
                           "MarketID": 123, "Count": tonnes})

    def settled(self, tonnes):
        state = self.wait_for("/api/state", lambda value:
            (value.get("trade", {}).get("operation") or {}).get("loaded") == tonnes
            and not value.get("party", {}).get("recovery", {}).get("running", True))
        self.assertIsNone(state["party"]["recovery"]["error"])
        op = state["trade"]["operation"]
        self.assertEqual(op["id"], self.operation_id)
        self.assertEqual((op["stage"], op["quantity"], op["unloaded"]), ("loading", 1000, 0))
        self.assertEqual(state["party"]["work"]["loading"], tonnes)
        return state

    def test_crash_partial_write_offline_delivery_and_repeated_restart(self):
        self.start()
        self.wait_for("/api/state", lambda state: state.get("journal", {}).get("cmdr") == "Testpilot")
        self.request("/api/trade/plan", {"commodity": "gold", "source": "Buy / Sol",
            "destination": "Sell / Lave", "source_price": 100, "destination_price": 300,
            "target": 1000, "planned_quantity": 1000, "carrier_market_id": 123,
            "destination_market_id": 789})
        started = self.request("/api/trade/operation", {"action": "start"})
        self.operation_id = started["operation"]["id"]
        self.wait_for("/api/party", lambda state: not state["recovery"]["running"])
        first = self.delivery(100)
        self.append(first + "\n")
        self.settled(100)
        identity = json.loads((self.directory / "data/party-local.json").read_text())["id"]

        # Crash with an incomplete game write, then complete it while offline.
        self.append(self.delivery(50))
        self.crash()
        self.append("\n" + first + "\n")  # Duplicate evidence must not be credited.
        self.start()
        recovered = self.settled(150)
        self.assertEqual(recovered["party"]["mode"], "idle")
        self.assertEqual(json.loads((self.directory / "data/party-local.json").read_text())["id"], identity)

        # The restarted watcher must also tail new deliveries, then survive again.
        self.append(self.delivery(25) + "\n")
        self.settled(175)
        self.crash()
        self.start()
        again = self.settled(175)
        self.assertEqual(again["party"]["recovery"]["recovered"], 0)
        saved = json.loads((self.directory / "data/party-local.json").read_text())
        self.assertEqual(saved["work"]["loading"], 175)
        self.assertEqual(len(saved["auto_seen"]), 3)


if __name__ == "__main__":
    unittest.main()
