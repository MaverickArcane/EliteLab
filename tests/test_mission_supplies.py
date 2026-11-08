"""Mission logistics must not send pilots shopping for assigned or salvage cargo."""
import json
from pathlib import Path
import shutil
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from test_progression_sourcing import FixtureMixin


class MissionSuppliesTests(FixtureMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).parent / 'fixtures/journals/missions/Journal.20261101.010000.01.log'
        shutil.copy(fixture, self.logs / fixture.name)
        self.core = self.make_core()

    def event(self, event, **fields):
        self.emit(event, timestamp='2026-11-01T02:00:00Z', **fields)

    def cargo(self, items, at='2026-11-01T02:01:00Z'):
        self.core.bus.emit('journal.file.Cargo', {'timestamp':at, 'Vessel':'Ship', 'Inventory':items})

    def plan(self):
        return self.call('get_mission_plan')

    def mission(self, mid):
        return next(m for m in self.plan()['missions'] if m['mission_id'] == mid)

    def test_real_mission_types_and_return_locations(self):
        p = self.plan()
        self.assertEqual({r['commodity_key']:r['quantity'] for r in p['shopping_list']}, {'bauxite':81,'onionheadc':72})
        self.assertEqual(self.mission(3)['hand_in']['station'], 'Magnus Gateway')
        self.assertEqual(self.mission(3)['destination']['system'], 'Ross 780')
        self.assertEqual(self.mission(4)['aboard_allocated'], 98)
        self.assertEqual(self.mission(4)['remaining_to_deliver'], 98)  # Progress 1.0 is not completion.
        self.assertEqual(self.mission(4)['remaining_at_origin_depot'], 0)
        self.assertFalse(p['fits_current_hold'])

    def test_generic_cargo_allocated_once_and_stolen_excluded(self):
        self.event('MissionAccepted', MissionID=5, Name='Mission_Collect', Commodity='$Bauxite_Name;', Count=20, Expiry='2099-02-01T00:00:00Z')
        self.cargo([{'Name':'bauxite','Count':90,'Stolen':5}])
        self.assertEqual(self.mission(1)['shortfall'], 0)
        self.assertEqual(self.mission(5)['shortfall'], 16)
        filtered = self.call('get_mission_plan', mission_id='5')
        self.assertEqual(filtered['shopping_list'][0]['quantity'], 16)
        self.assertEqual(filtered['shopping_tonnes'], 16)

    def test_mission_tagged_cargo_never_shared_or_replaced_with_generic(self):
        self.cargo([{'Name':'bauxite','MissionID':999,'Count':100}, {'Name':'usscargoblackbox','Count':2},
                    {'Name':'advancedmedicines','Count':98}])
        self.assertEqual(self.mission(1)['shortfall'],81)
        self.assertEqual(self.mission(3)['shortfall'],2)
        self.assertEqual(self.mission(4)['shortfall'],98)
        self.cargo([{'Name':'usscargoblackbox','MissionID':3,'Count':2,'Stolen':2}])
        self.assertEqual(self.mission(3)['shortfall'],0)

    def test_partial_deliveries_and_old_cargo_snapshot(self):
        self.event('CargoDepot', MissionID=1, ItemsDelivered=30, ItemsCollected=0, TotalItemsToDeliver=81)
        self.assertIsNone(self.mission(1)['shortfall'])
        self.cargo([{'Name':'bauxite','Count':20}])
        self.assertEqual(self.mission(1)['shortfall'],31)
        self.event('CargoDepot', MissionID=1, ItemsDelivered=30, TotalItemsToDeliver=81)
        self.assertEqual(self.mission(1)['shortfall'],31)  # Cumulative, not incremental.

    def test_completed_failed_abandoned_expired_and_ready_not_shopped(self):
        self.event('MissionCompleted', MissionID=1)
        self.event('MissionAbandoned', MissionID=2)
        self.event('MissionFailed', MissionID=3)
        self.assertEqual([m['mission_id'] for m in self.plan()['missions']], [4])
        self.event('MissionAccepted', MissionID=6, Name='Mission_Collect', Commodity='gold', Count=3, Expiry='2001-01-01T00:00:00Z')
        self.event('MissionAccepted', MissionID=7, Name='Mission_Collect', Commodity='gold', Count=3)
        self.event('Missions', Active=[{'MissionID':4},{'MissionID':6}], Complete=[{'MissionID':7}])
        self.assertEqual(self.plan()['shopping_list'], [])
        self.assertTrue(self.mission(6)['expired'])

    def test_commander_and_session_isolation(self):
        self.event('Commander', FID='OTHER', Name='Other')
        self.assertEqual(self.plan()['missions'], [])
        self.assertIsNone(self.plan()['cargo_observed_at'])
        self.event('Commander', FID='FMISSIONS', Name='Mission Pilot')
        self.assertIsNone(self.mission(1)['shortfall'])
        self.cargo([], at='2026-11-01T01:01:00Z')
        self.assertIsNone(self.mission(1)['shortfall'])

    def test_replay_backfills_requirements_without_resurrecting_outcomes(self):
        self.event('MissionCompleted', MissionID=1)
        self.core = self.make_core()
        self.assertNotIn(1, [m['mission_id'] for m in self.plan()['missions']])
        self.assertEqual(self.mission(3)['origin_station'], 'Magnus Gateway')
        self.assertEqual(self.mission(4)['depot']['ItemsCollected'],98)

    def test_redirect_changes_destination_not_status(self):
        self.event('MissionRedirected', MissionID=4, DestinationSystem='Sol', DestinationStation='Galileo')
        self.assertEqual(self.mission(4)['hand_in']['station'], 'Galileo')
        self.assertEqual(self.mission(4)['status'], 'accepted')

    def test_network_search_aliases_radius_pad_and_shared_stop(self):
        seen = []
        def fetch(url, **kw):
            seen.append(url)
            if url.endswith('/commodities'):
                return [{'commodityName':'bauxite'}, {'commodityName':'onionheadc'}]
            name = 'bauxite' if '/bauxite/' in url else 'onionheadc'
            return [{'commodityName':name, 'marketId':123, 'systemName':'Nearby', 'stationName':'Port',
                'stationType':'Coriolis Starport', 'buyPrice':10, 'stock':500, 'maxLandingPadSize':3,
                'systemX':3,'systemY':4,'systemZ':0,'updatedAt':datetime.now(timezone.utc).isoformat()}]
        with patch.object(self.core.services, 'fetch_json', side_effect=fetch):
            p = self.call('find_mission_sources')
        self.assertEqual(len(p['suggested_buy_stops']),1)
        self.assertEqual(p['suggested_buy_stops'][0]['estimated_cost'],1530)
        self.assertEqual(p['supplies'][1]['status'],'sources_found')
        self.assertTrue(all('maxDistance=25' in u and 'fleetCarriers=0' in u for u in seen if not u.endswith('/commodities')))
        self.assertFalse(any('blackbox' in u or 'advancedmedicines' in u for u in seen))

    def test_partial_provider_failure_preserves_checklist(self):
        from elitelab.core.commodity_sources import Sourcing
        def find(_, q):
            if q['commodity_key'] == 'bauxite':
                raise TimeoutError('provider timed out')
            return {'status':'no_matching_reports_within_radius', 'sources':[]}
        with patch.object(Sourcing, 'find', find):
            p = self.call('find_mission_sources')
        self.assertEqual(len(p['missions']),4)
        self.assertEqual([r['status'] for r in p['supplies']],['lookup_failed','no_matching_reports_within_radius'])

    def test_no_network_from_journal_updates_or_local_checklist(self):
        with patch.object(self.core.services,'fetch_json',side_effect=AssertionError('network')) as fetch:
            self.cargo([{'Name':'bauxite','Count':81}, {'Name':'onionheadc','Count':72}])
            self.assertEqual(self.plan()['shopping_list'],[])
            self.assertEqual(self.call('find_mission_sources')['supplies'],[])
            fetch.assert_not_called()
        self.assertEqual(self.core.store.get('missions','plan')['shopping_tonnes'],0)

    def test_search_parameter_bounds_apply_with_no_shortages(self):
        for opts in ({'max_distance_ly':501}, {'max_days':0}, {'limit':11}, {'pad':'X'}, {'carriers':'private'}):
            with self.assertRaises(ValueError):
                self.call('find_mission_sources', **opts)

    def test_cargo_marker_invalidates_old_inventory_until_snapshot_arrives(self):
        self.cargo([{'Name':'bauxite','Count':81}])
        self.emit('Cargo', timestamp='2026-11-01T02:02:00Z', Vessel='Ship', Count=0)
        self.assertIsNone(self.mission(1)['shortfall'])
        self.assertFalse(self.plan()['cargo_current'])
        self.cargo([], at='2026-11-01T02:02:00Z')
        self.assertEqual(self.mission(1)['shortfall'],81)
