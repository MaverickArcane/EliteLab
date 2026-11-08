"""Fixed build requirements survive ship changes while inventory stays live."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core
from modules.build.module import Build
from modules.wishlist.module import Wishlist


class WishlistFollowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.core = Core()
        self.core.data_path = lambda *p: str(Path(folder.name).joinpath(*p))
        self.inventory = {}
        self.core.http.route('/inventory', lambda q: {
            'inventory': dict(self.inventory), 'inventory_known': True}, tool='get_material_inventory')
        self.build = Build(self.core)
        self.ship(3)
        self.build.pin({'url': json.dumps({'Ship': 'sidewinder', 'ShipName': 'Engineering ship', 'Modules': [
            {'Slot': 'FrameShiftDrive', 'Item': 'int_hyperdrive_size2_class5',
             'Engineering': {'BlueprintName': 'FSD_LongRange', 'Level': 5}}]})})
        self.wishlist = Wishlist(self.core)

    def ship(self, grade, ship='sidewinder'):
        self.core.store.update('journal', {'ship_info': {'internal': ship, 'modules': [
            {'slot': 'FrameShiftDrive', 'item': 'int_hyperdrive_size2_class5',
             'engineering': {'blueprint': 'FSD_LongRange', 'level': grade}}]}})

    def entry(self):
        return self.wishlist.compute()['entries'][0]

    def test_live_build_tracks_engineering_until_switched_off(self):
        entry = self.wishlist.add({'item': 'build'})['entry']
        self.assertTrue(entry['follow_ship'])
        self.assertGreater(entry['units'], 0)
        self.ship(4)
        self.assertLess(self.entry()['units'], entry['units'])
        before = self.entry()
        self.wishlist.update({'id': entry['id'], 'follow_ship': False})
        self.ship(0, 'explorer_nx')
        self.assertEqual(self.entry()['units'], before['units'])
        self.assertEqual(self.entry()['id'], entry['id'])
        self.wishlist.update({'id': entry['id'], 'follow_ship': True})
        self.assertGreater(self.entry()['units'], before['units'])
        self.ship(5)
        self.assertEqual(self.entry()['units'], 0)

    def test_fixed_requirements_persist_and_material_shortfalls_stay_live(self):
        entry = self.wishlist.add({'item': 'build', 'follow_ship': False})['entry']
        self.ship(0, 'explorer_nx')
        self.wishlist = Wishlist(self.core)
        self.assertEqual(self.entry()['units'], entry['units'])
        self.assertFalse(self.entry()['follow_ship'])
        for row in entry['ingredients']:
            self.inventory[row['key']] = row['need']
        self.core.store.update('materials', {'inventory_version': 1})
        self.assertEqual(self.core.store.get('wishlist', 'summary')['units_short'], 0)
        self.assertEqual(self.entry()['units'], entry['units'])
        self.inventory.clear()
        self.core.store.update('materials', {'inventory_version': 2})
        self.assertEqual(self.entry()['short'], entry['units'])
        self.build.unpin({})
        self.assertEqual(self.entry()['units'], entry['units'])

    def test_legacy_entries_still_follow_and_repeat_freeze_keeps_snapshot(self):
        entry = self.wishlist.add({'item': 'build'})['entry']
        self.wishlist.entries[0].pop('follow_ship')
        self.ship(4)
        self.assertLess(self.entry()['units'], entry['units'])
        self.wishlist.update({'id': entry['id'], 'follow_ship': False})
        frozen = copy.deepcopy(self.wishlist.entries[0])
        self.ship(0, 'explorer_nx')
        self.wishlist.update({'id': entry['id'], 'follow_ship': False})
        self.assertEqual(self.wishlist.entries[0], frozen)
        duplicate = self.wishlist.add({'item': 'build'})['entry']
        self.assertFalse(duplicate['follow_ship'])
        self.assertEqual(duplicate['saved_needs'], frozen['saved_needs'])

    def test_toggle_validation_and_failed_save_preserve_previous_plan(self):
        build = self.wishlist.add({'item': 'build'})['entry']
        material = self.wishlist.add({'item': 'iron', 'qty': 2})['entry']
        for q in ({'id': build['id'], 'follow_ship': 'false'}, {'id': build['id']},
                  {'id': material['id'], 'follow_ship': False}, {'id': build['id'], 'qty': 2}):
            with self.assertRaises(ValueError):
                self.wishlist.update(q)
        before = copy.deepcopy(self.wishlist.entries)
        with patch.object(self.core, 'write_data', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.wishlist.update({'id': build['id'], 'follow_ship': False})
        self.assertEqual(self.wishlist.entries, before)
        self.wishlist.update({'id': material['id'], 'qty': 3})
        self.assertEqual(self.wishlist.entries[1]['qty'], 3)

    def test_completed_build_can_save_an_empty_requirement_set(self):
        self.ship(5)
        entry = self.wishlist.add({'item': 'build', 'follow_ship': False})['entry']
        self.assertEqual(entry['saved_needs'], {})
        self.ship(0, 'explorer_nx')
        self.assertEqual(self.entry()['units'], 0)

    def test_build_handoff_accepts_and_preserves_follow_choice(self):
        self.core.http.route('/wishlist', lambda q: self.wishlist.compute(), tool='get_engineering_wishlist')
        self.core.http.route('/wishlist/add', self.wishlist.add, tool='wishlist_add')
        saved = self.build.to_wishlist({'follow_ship': False})['entry']
        self.assertFalse(saved['follow_ship'])
        self.ship(0, 'explorer_nx')
        repeated = self.build.to_wishlist({})['entry']
        self.assertFalse(repeated['follow_ship'])
        self.assertEqual(repeated['saved_needs'], saved['saved_needs'])
        live = self.build.to_wishlist({'follow_ship': True})['entry']
        self.assertTrue(live['follow_ship'])
        self.assertGreater(live['units'], saved['units'])
