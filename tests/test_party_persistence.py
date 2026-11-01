"""Deferred and synchronous receipts must reach disk in snapshot order."""
import builtins
import threading
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from test_elitelab import Core, loader


class PartyPersistenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.core = Core()
        self.core.data_path = lambda *parts: str(Path(folder.name).joinpath(*parts))
        loader.load_all(self.core)
        self.addCleanup(self.core.close)
        self.party = self.core.modules["party"].party
        self.api = self.core.modules["party"].instance

    def test_captured_deferred_batch_cannot_overwrite_manual_save(self):
        captured, release, attempted = (threading.Event() for _ in range(3))
        first = {"operation_id": "a" * 32, "loading": 10, "unloading": 0}
        newer = {**first, "loading": 20}

        def paused_next(*args):
            result = builtins.next(*args)
            if threading.current_thread().name == "party-writer":
                captured.set()
                if not release.wait(5):
                    raise AssertionError("Writer was not released")
            return result

        def manual_save():
            attempted.set()
            with self.party.lock:
                self.party.save_work(newer)

        with patch.object(self.api, "next", paused_next, create=True), ThreadPoolExecutor(1) as pool:
            with self.party.lock:
                self.party.save_work(first, deferred=True)
            self.assertTrue(captured.wait(3))
            saved = pool.submit(manual_save)
            try:
                self.assertTrue(attempted.wait(3))
                # Before the fix this completes while the old batch is paused.
                threading.Event().wait(.05)
                self.assertFalse(saved.done())
            finally:
                release.set()
            saved.result(timeout=3)
            self.assertTrue(self.party.flush(3))
        self.assertEqual(self.core.read_data("party-local.json")["work"], newer)
        self.assertEqual(self.party.work, newer)

    def test_deferred_write_waits_for_synchronous_write(self):
        entered, release = threading.Event(), threading.Event()
        first = {"operation_id": "a" * 32, "loading": 10, "unloading": 0}
        newer = {**first, "loading": 20}
        original = self.core.write_data
        writes = []

        def delayed(data, *parts):
            if data.get("work") == first:
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Save was not released")
            original(data, *parts)
            writes.append(data["work"]["loading"])

        with patch.object(self.core, "write_data", side_effect=delayed), ThreadPoolExecutor(1) as pool:
            saved = pool.submit(self.party.save_work, first)
            self.assertTrue(entered.wait(3))
            try:
                # queue_write must stay nonblocking while disk I/O is underway.
                self.party.queue_write({"work": newer}, None)
            finally:
                release.set()
            saved.result(timeout=3)
            self.assertTrue(self.party.flush(3))
        self.assertEqual(writes, [10, 20])
        self.assertEqual(self.core.read_data("party-local.json")["work"], newer)
