"""The journal watcher follows the standard Thread shutdown contract."""
import unittest
from unittest.mock import Mock

from elitelab.core.watcher import JournalWatcher


class WatcherLifecycleTests(unittest.TestCase):
    def test_stopped_watcher_can_be_joined_and_inspected(self):
        watcher = JournalWatcher(Mock())
        watcher.replay = Mock()
        watcher.start()
        self.assertTrue(watcher.is_alive())
        watcher.stop()
        watcher.join(timeout=5)
        self.assertFalse(watcher.is_alive())
        watcher.join(timeout=1)


if __name__ == '__main__':
    unittest.main()
