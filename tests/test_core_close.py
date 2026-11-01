"""Core.close() flushes background writers so a data directory can be removed safely."""
import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from test_elitelab import Core, FIXTURES, config, loader


class CoreCloseTests(unittest.TestCase):
    def setUp(self):
        data = tempfile.TemporaryDirectory(prefix="elitelab-close-test-")
        self.addCleanup(data.cleanup)
        for key, value in (("DATA_DIR", data.name), ("JOURNAL_DIR", os.path.join(FIXTURES, "trade"))):
            p = patch.object(config, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.data = data.name
        self.core = Core()
        loader.load_all(self.core)
        self.core.watcher.replay()

    def test_close_flushes_the_ledger_writer_and_runs_shutdown_callbacks(self):
        trade = self.core.modules["trade"].trade
        # Same live event the trade tests use: the fixture commander is docked at the carrier, stock 440 -> 450.
        self.core.bus.emit("journal.CargoTransfer", {"event": "CargoTransfer", "timestamp": "2026-10-23T12:00:00Z",
                                                     "Transfers": [{"Type": "gold", "Count": 10, "Direction": "tocarrier"}]})
        self.assertEqual(trade.data["inventory"]["gold"]["stock"], 450)
        ran = []
        self.core.shutdown_callbacks.append(lambda: ran.append("callback"))
        self.core.close()
        self.assertEqual(ran, ["callback"])
        self.assertEqual(trade.saved, trade.version)
        with open(os.path.join(self.data, "trade.json")) as fh:
            self.assertEqual(json.load(fh)["inventory"]["gold"]["stock"], 450)
        self.core.close()  # idempotent

    def test_close_before_start_is_safe(self):
        core = Core()
        core.close()

    def test_flush_does_not_leave_a_captured_ledger_write_behind(self):
        trade = self.core.modules["trade"].trade
        captured, release = threading.Event(), threading.Event()
        original_io = trade.io
        writes = []
        original_write = self.core.write_data

        class PausedIO:
            def acquire(inner):
                if threading.current_thread().name == "trade-ledger-writer":
                    captured.set()
                    if not release.wait(5):
                        raise AssertionError("Writer was not released")
                return original_io.acquire()

            def release(inner):
                original_io.release()

            def __enter__(inner):
                inner.acquire()

            def __exit__(inner, *args):
                inner.release()

        def record(value, *parts):
            original_write(value, *parts)
            writes.append(threading.current_thread().name)

        with patch.object(trade, "io", PausedIO()), patch.object(self.core, "write_data", side_effect=record), ThreadPoolExecutor(1) as pool:
            with trade.lock:
                trade.changed_in_place()
            self.assertTrue(captured.wait(3))
            closing = pool.submit(self.core.close)
            try:
                threading.Event().wait(.05)
                self.assertFalse(closing.done(), "Close returned before its captured write")
            finally:
                release.set()
            closing.result(timeout=3)
            # The worker has either updated its saved version, or is about to;
            # neither path may schedule another write after close returns.
            with trade.lock:
                self.assertEqual(trade.saved, trade.version)
            count = len(writes)
            threading.Event().wait(.05)
            self.assertEqual(len(writes), count)


if __name__ == "__main__":
    unittest.main()
