"""Current inventory and gross gains are distinct and survive journal replay."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_elitelab import Core, config, loader, FIXTURES


class MaterialSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        for key, value in (("DATA_DIR", temporary.name),
                           ("JOURNAL_DIR", str(Path(FIXTURES) / "material-session"))):
            setting = patch.object(config, key, value)
            setting.start()
            self.addCleanup(setting.stop)
        self.core = self.client()

    def client(self):
        core = Core()
        loader.load_all(core)
        self.addCleanup(core.close)
        return core

    def materials(self, core=None):
        return (core or self.core).http.tools['get_materials'].fn({})

    def emit(self, event, **values):
        self.core.bus.emit('journal.' + event, {'event': event, **values})

    def test_replay_preserves_inventory_and_gross_gains_across_restart(self):
        self.core.watcher.replay()
        result = self.materials()
        rows = {r['key']: (r['count'], r['gained']) for r in result['materials']}
        self.assertEqual(rows, {'iron': (10, 3), 'nickel': (4, 5), 'carbon': (6, 6)})
        self.assertEqual(result['session']['gained'], 14)
        self.assertEqual(result['session']['totals'], {'Raw': 14, 'Manufactured': 0, 'Encoded': 0})
        self.assertEqual(result['session']['last_gain']['key'], 'carbon')
        restarted = self.client()
        restarted.watcher.replay()
        self.assertEqual(self.materials(restarted), result)

    def test_new_game_resets_gains_but_inventory_dump_is_not_a_pickup(self):
        self.core.watcher.replay()
        self.emit('LoadGame', timestamp='2026-10-30T11:00:00Z')
        self.emit('Materials', Raw=[{'Name':'iron','Count':50}])
        result = self.materials()
        self.assertEqual(result['session']['gained'], 0)
        self.assertIsNone(result['session']['last_gain'])
        self.assertEqual(result['materials'][0]['count'], 50)
        self.emit('MaterialCollected', Name='iron', Count=3, Category='Raw', timestamp='2026-10-30T11:01:00Z')
        row = self.materials()['materials'][0]
        self.assertEqual((row['count'],row['gained']), (53,3))

    def test_unknown_session_is_reported_as_unknown(self):
        self.emit('Materials', Raw=[{'Name':'iron','Count':10}])
        self.emit('MaterialCollected', Name='iron', Count=3, Category='Raw')
        result = self.materials()
        self.assertEqual(result['materials'][0]['count'], 13)
        self.assertIsNone(result['materials'][0]['gained'])
        self.assertIsNone(result['session']['gained'])

    def test_spent_material_remains_visible_in_gains_and_wishlist_uses_current_count(self):
        self.core.watcher.replay()
        self.core.http.tools['wishlist_add'].fn({'item':'iron', 'qty':12})
        self.emit('Synthesis', Materials=[{'Name':'iron','Count':10}])
        self.emit('Materials', Raw=[{'Name':'carbon','Count':6},{'Name':'nickel','Count':4}])
        row = next(r for r in self.materials()['materials'] if r['key']=='iron')
        self.assertEqual((row['count'],row['gained']), (0,3))
        needs = self.core.http.tools['get_engineering_wishlist'].fn({})['needs']
        iron = next(r for r in needs if r['key']=='iron')
        self.assertEqual((iron['have'],iron['need'],iron['short']), (0,12,12))


if __name__ == '__main__':
    unittest.main()
