"""A completed network lookup cannot write or publish after Core.close()."""
import threading
import unittest
from unittest.mock import Mock, patch

from test_elitelab import Core
from elitelab.core.coords import CoordCache


class CoordinateCloseTests(unittest.TestCase):
    def test_late_network_result_is_discarded_after_close(self):
        core = Core()
        entered, release = threading.Event(), threading.Event()
        updated = Mock()
        cache = CoordCache(core, "test", on_update=updated)
        cache.cache_file = "late-cache.json"
        cache._wanted.add("Sol")

        def fetch(names):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Fetch was not released")
            return {"Sol": {"x": 0, "y": 0, "z": 0}}

        with patch.object(core.services, "edsm_coords", side_effect=fetch), patch.object(core, "write_data") as write:
            worker = threading.Thread(target=cache._fetch)
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                core.close()
            finally:
                release.set()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            write.assert_not_called()
            updated.assert_not_called()
            self.assertIsNone(cache.get("Sol"))
            with patch("elitelab.core.coords.threading.Thread") as thread:
                cache.request(["Achenar"])
                thread.assert_not_called()
