"""Core.close() flushes background writers so a data directory can be removed safely."""
import json
import os
import tempfile
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


if __name__ == "__main__":
    unittest.main()
