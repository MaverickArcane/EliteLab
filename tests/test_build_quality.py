"""Grade and quality both affect build completion and material planning."""
import json
from pathlib import Path
import tempfile
import unittest

from test_elitelab import Core
from elitelab.core import gamedata as gd
from modules.build.module import Build
from modules.wishlist.module import Wishlist


class BuildQualityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.core = Core();self.addCleanup(self.core.close)
        self.core.data_path = lambda *parts: str(Path(temporary.name).joinpath(*parts))
        self.inventory = {}
        self.core.http.route('/fixture/inventory', lambda q: {'inventory': self.inventory, 'inventory_known': True},
                             tool='get_material_inventory')
        self.build = Build(self.core)
        self.pin()
        self.wishlist = Wishlist(self.core)

    def pin(self, target_quality=1):
        self.build.pin({'url': json.dumps({'Ship': 'sidewinder', 'Modules': [
            {'Slot': 'FrameShiftDrive', 'Item': 'int_hyperdrive_size2_class5',
             'Engineering': {'BlueprintName': 'FSD_LongRange', 'Level': 5, 'Quality': target_quality,
                             'ExperimentalEffect': 'special_fsd_heavy'}}]})})

    def ship(self, grade=5, quality=.4):
        self.core.store.update('journal', {'ship_info': {'internal': 'sidewinder', 'modules': [
            {'slot': 'FrameShiftDrive', 'item': 'int_hyperdrive_size2_class5',
             'engineering': {'blueprint': 'FSD_LongRange', 'level': grade, 'quality': quality,
                             'experimental': 'special_fsd_heavy'}}]}})
        return self.build.compute()['progress']

    def test_partial_final_grade_with_matching_experimental_needs_finishing_materials(self):
        p = self.ship()
        row = p['slots'][0]
        self.assertEqual(row['status'], 'engineer')
        self.assertEqual(row['current']['quality'], .4)
        self.assertEqual(row['finishing_rolls_estimate'], gd.ROLLS_PER_GRADE[5])
        self.assertEqual({r['key']:r['need'] for r in p['materials']}, gd.recipe_cost('FSD_LongRange', 5, 4))
        self.assertFalse(p['upgrade_complete'])
        self.assertTrue(p['completion_known'])
        self.assertNotIn('apply', ' '.join(row['todo']))

    def test_lower_partial_grade_adds_current_and_later_grade_budgets(self):
        p = self.ship(3, .5)
        self.assertEqual({r['key']:r['need'] for r in p['materials']}, gd.recipe_cost('FSD_LongRange',5,2))
        p = self.ship(3, 1)
        self.assertEqual({r['key']:r['need'] for r in p['materials']}, gd.recipe_cost('FSD_LongRange',5,3))

    def test_full_and_intentionally_partial_targets(self):
        p = self.ship(5,1)
        self.assertTrue(p['upgrade_complete']);self.assertEqual(p['materials'],[])
        self.pin(.4)
        self.assertTrue(self.ship(5,.4)['upgrade_complete'])
        self.assertFalse(self.ship(5,.2)['upgrade_complete'])
        self.assertTrue(self.ship(5,.8)['upgrade_complete'])

    def test_missing_invalid_quality_is_unknown_with_estimated_budget(self):
        for value in (None, -1, 2, '1', True, float('nan')):
            with self.subTest(quality=value):
                p = self.ship(5,value)
                self.assertFalse(p['upgrade_complete'])
                self.assertFalse(p['completion_known'])
                self.assertEqual(p['slots'][0]['status'],'check')
                self.assertIsNone(p['slots'][0]['current']['quality'])
                self.assertTrue(p['materials'])

    def test_live_wishlist_updates_but_frozen_snapshot_does_not(self):
        p = self.ship()
        entry = self.wishlist.add({'item':'build'})['entry']
        self.assertGreater(entry['units'],0)
        self.inventory.update({r['key']:r['need'] for r in p['materials']})
        entry = self.wishlist.compute()['entries'][0]
        self.assertTrue(entry['materials_covered'])
        self.assertFalse(entry['upgrade_complete'])
        self.wishlist.update({'id':entry['id'],'follow_ship':False})
        self.ship(5,1)
        frozen = self.wishlist.compute()['entries'][0]
        self.assertEqual(frozen['units'],entry['units'])
        self.assertIsNone(frozen['upgrade_complete'])
        self.wishlist.update({'id':entry['id'],'follow_ship':True})
        live = self.wishlist.compute()['entries'][0]
        self.assertEqual(live['units'],0)
        self.assertTrue(live['upgrade_complete'])
