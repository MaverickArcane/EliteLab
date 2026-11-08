"""Trader destinations preserve unknown distances and expose useful station details."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_elitelab import Core
from modules.wishlist.module import Wishlist
from modules.materials.module import Materials


class MaterialTraderDetailsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.core = Core()
        self.addCleanup(self.core.close)
        self.core.data_path = lambda *p: str(Path(folder.name).joinpath(*p))
        self.core.store.update('journal', {'system': 'Leesti', 'jump_range_now': 10})
        self.wishlist = Wishlist(self.core)

    def station(self, **changes):
        return {'system_name': 'Destination', 'name': 'Trade Port', 'distance': 20.04,
                'distance_to_arrival': 1234.5, 'has_large_pad': True,
                'type': 'Coriolis Starport', 'primary_economy': 'Industrial', **changes}

    def test_station_details_and_pad_filter_keep_unrounded_jump_estimate(self):
        with patch.object(self.core.services, 'spansh_stations', return_value={'results': [self.station()]}) as search:
            result = self.wishlist.traders({'types': 'Manufactured', 'pad': 'L', 'limit': 5})
        row = result['traders']['Manufactured'][0]
        self.assertEqual((row['dist'], row['ls'], row['jumps']), (20.0, 1234, 3))
        self.assertEqual((row['pad'], row['type'], row['economy']), ('L', 'Coriolis Starport', 'Industrial'))
        self.assertEqual(search.call_args.args, ({'material_trader': {'value': ['Manufactured']}, 'has_large_pad': {'value': True}}, 'Leesti'))
        self.assertEqual(search.call_args.kwargs['size'], 5)

    def test_missing_and_invalid_distances_stay_unknown_but_zero_is_valid(self):
        for value, expected in ((None, None), (-1, None), (float('nan'), None), (True, None), (0, 0)):
            with self.subTest(value=value), patch.object(self.core.services, 'spansh_stations', return_value={
                    'results': [self.station(distance=value, distance_to_arrival=value)]}):
                row = self.wishlist.traders({'types': 'Raw'})['traders']['Raw'][0]
                self.assertEqual((row['dist'], row['ls'], row['jumps']), (expected, expected, expected))

    def test_one_provider_failure_does_not_hide_other_trader_categories(self):
        def search(filters, *args, **kwargs):
            if filters['material_trader']['value'] == ['Encoded']:
                raise OSError('Provider unavailable')
            return {'results': [self.station()]}
        with patch.object(self.core.services, 'spansh_stations', side_effect=search):
            result = self.wishlist.traders({'types': 'Raw,Encoded'})
        self.assertEqual(len(result['traders']['Raw']), 1)
        self.assertIn('Provider unavailable', result['traders']['Encoded']['error'])

    def test_inventory_includes_material_family(self):
        materials = Materials(self.core)
        self.assertEqual(materials.info('chemicalmanipulators')['family'], 'Chemical')
        self.assertEqual(materials.info('dataminedwake')['family'], 'Wake Scans')
