"""Inventory callbacks cannot deadlock concurrent wishlist requests."""
import tempfile
import threading
import unittest
import json
import copy
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core
from modules.materials.module import Materials
from modules.wishlist.module import Wishlist
from modules.build.module import Build
from elitelab.core import gamedata as gd


class EngineeringConcurrencyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.core = Core()
        self.core.data_path = lambda *p: str(Path(folder.name).joinpath(*p))
        self.materials = Materials(self.core)
        self.core.http.route('/inventory', lambda q: {'inventory':self.materials.inventory()}, tool='get_material_inventory')
        self.wishlist = Wishlist(self.core)

    def test_wishlist_edit_and_material_callback_both_finish(self):
        publishing, reading = threading.Event(), threading.Event()
        original = self.wishlist.inventory
        def inventory():
            reading.set()
            return original()
        self.wishlist.inventory = inventory
        def subscriber(ns, key, value, version):
            if (ns,key) == ('materials','inventory_version'):
                publishing.set()
                reading.wait(2)
        self.core.store.subscribe(subscriber)
        errors = []
        def run(fn):
            try:
                fn()
            except Exception as error:
                errors.append(error)
        watcher = threading.Thread(target=lambda:run(lambda:self.materials.on_event('journal.MaterialCollected',
            {'event':'MaterialCollected','Name':'iron','Count':1})), daemon=True)
        request = threading.Thread(target=lambda:run(lambda:self.wishlist.add({'item':'2 iron'})), daemon=True)
        watcher.start()
        self.assertTrue(publishing.wait(2))
        request.start()
        watcher.join(2); request.join(2)
        self.assertFalse(watcher.is_alive(), 'journal watcher blocked by wishlist')
        self.assertFalse(request.is_alive(), 'wishlist blocked by material inventory')
        self.assertEqual(errors, [])
        self.assertEqual(self.core.store.get('wishlist','needs')[0]['short'], 1)

    def test_trade_batches_fit_cap_and_keep_unresolved_need(self):
        donor,target = next((a,b) for a in gd.MATERIAL_BY_KEY for b in gd.MATERIAL_BY_KEY if gd.trade_ratio(a,b)==(1,3))
        cap = gd.MATERIAL_CAPS[gd.MATERIAL_BY_KEY[target]['grade']]
        for have,need,expected_get,expected_short in ((cap-1,cap,0,1),(cap-3,cap,3,0),(cap-3,cap+5,3,5),(cap,cap+5,0,5)):
            with self.subTest(have=have,need=need):
                row = self.wishlist.material_row(target,need,have)
                plan = self.wishlist.plan_trades([row],{target:have,donor:10})
                received = sum(t['get']['qty'] for t in plan['trades'])
                self.assertEqual(received,expected_get)
                self.assertLessEqual(have+received,cap)
                self.assertEqual(sum(r['short'] for r in plan['unresolved']),expected_short)

    def test_failed_wishlist_save_preserves_entries_and_published_state(self):
        self.wishlist.add({'item':'2 iron'})
        entries=copy.deepcopy(self.wishlist.entries)
        state=self.core.store.get('wishlist')
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            for fn in (lambda:self.wishlist.add({'item':'3 iron'}),lambda:self.wishlist.remove({'all':True})):
                with self.assertRaises(OSError):fn()
                self.assertEqual(self.wishlist.entries,entries)
                self.assertEqual(self.core.store.get('wishlist'),state)

    def test_failed_build_pin_and_unpin_preserve_previous_target(self):
        build=Build(self.core)
        target={'Ship':'sidewinder','ShipName':'Original','Modules':[{'Slot':'PowerPlant','Item':'int_powerplant_size2_class1'}]}
        build.pin({'url':json.dumps(target)})
        before=copy.deepcopy(build.compute())
        target['ShipName']='Replacement'
        with patch.object(self.core,'write_data',side_effect=OSError('disk full')):
            for fn in (lambda:build.pin({'url':json.dumps(target)}),lambda:build.unpin({})):
                with self.assertRaises(OSError):fn()
                self.assertEqual(build.compute(),before)
