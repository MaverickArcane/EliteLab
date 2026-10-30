"""Concurrent UI reports and heartbeats cannot roll back shared instructions."""
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_elitelab import Core, loader


class PartySyncTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.core = Core()
        self.core.data_path = lambda *parts: str(Path(folder.name).joinpath(*parts))
        loader.load_all(self.core)
        self.addCleanup(self.core.close)
        self.party = self.core.modules["party"].party
        self.api = self.core.modules["party"].instance
        # No background worker: schedule the same public methods deterministically.
        self.party.mode = "member"
        self.party.remote = {"members":[], "operation":{"stage":"loading"}}
        self.party.last_success = time.time()

    def test_overlapping_reports_are_serialized_and_capture_fresh_state(self):
        entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
        reports = []

        def exchange(url, token, body):
            reports.append(copy.deepcopy(body))
            if len(reports) == 1:
                entered.set()
                if not release.wait(3):
                    raise AssertionError("Test did not release the delayed heartbeat")
                return {"members":[],"operation":{"stage":"loading"}}
            second_entered.set()
            return {"members":[],"operation":{"stage":"transit"}}

        with patch.object(self.api,"exchange",side_effect=exchange), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.party.synchronize,self.party.generation,"offline")
            self.assertTrue(entered.wait(2))
            second = pool.submit(self.party.report_work,{"activity":"away"})
            try:
                # A local edit must not wait for the slow network request.
                deadline = time.monotonic()+2
                while self.party.activity != "away" and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(self.party.activity,"away")
                self.assertFalse(second_entered.wait(.05))
            finally:
                release.set()
            first.result(timeout=3)
            second.result(timeout=3)
        self.assertEqual([r["report"]["activity"] for r in reports],["ready","away"])
        self.assertEqual(self.party.remote["operation"]["stage"],"transit")

    def test_leave_is_sent_after_in_flight_report_and_old_response_is_ignored(self):
        entered, release = threading.Event(), threading.Event()
        messages = []

        def exchange(url, token, body):
            messages.append(body)
            if not body.get("leave"):
                entered.set()
                release.wait(3)
            return {"members":[],"operation":{"stage":"loading"}}

        with patch.object(self.api,"exchange",side_effect=exchange), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.party.synchronize,self.party.generation,"offline")
            self.assertTrue(entered.wait(2))
            leaving = pool.submit(self.party.leave)
            try:
                deadline = time.monotonic()+2
                while self.party.mode != "idle" and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(self.party.mode,"idle")
                self.assertEqual(len(messages),1)
            finally:
                release.set()
            first.result(timeout=3)
            leaving.result(timeout=3)
        self.assertTrue(messages[-1]["leave"])
        self.assertEqual(self.party.remote,{})
