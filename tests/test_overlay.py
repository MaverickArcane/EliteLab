import time
import copy
import unittest

from elitelab.overlay import Feed, automatic_surface_card, mining_card, rhino_progress_card, surface_card
from modules.rhino.overlay import demo_state


class ActivityOverlayTests(unittest.TestCase):
    def sample(self):
        state = demo_state()
        state['session'] = {'active': True, 'total_t': 203, 'unloaded_t': 135, 'average_tph': 329.3,
                            'commodities': [{'name': 'Iridium', 'tonnes': 203}]}
        state['cargo']['rhino'] = {'count': 68, 'capacity': 72, 'free': 4}
        state['cargo']['ship'] = {'free': 1006}
        return state

    def test_already_mining_near_deposit_shows_deployment_progress(self):
        state = self.sample()
        state['navigation']['distance_m'] = 1117.1
        card = automatic_surface_card(state, True)
        self.assertEqual(card.primary, '203 t')
        self.assertEqual(card.secondary, '135 t unloaded')
        self.assertEqual(card.metric, '68/72 t')
        self.assertIn('unload', card.warning)
        self.assertIn('across deposits', card.note)
        self.assertEqual(card.visual['kind'], 'gauge')
        self.assertEqual(surface_card(state, True).visual['kind'], 'compass')

    def test_approach_arrival_and_new_target(self):
        state = self.sample()
        state['navigation']['distance_m'] = 2500
        self.assertEqual(automatic_surface_card(state, True).visual['kind'], 'compass')
        state['session']['total_t'] = 0
        state['navigation']['distance_m'] = 500
        self.assertEqual(automatic_surface_card(state, True).visual['kind'], 'compass')
        state['navigation']['distance_m'] = 24
        self.assertEqual(automatic_surface_card(state, True).primary, '0 t')
        state['session']['active'] = False
        self.assertEqual(automatic_surface_card(state, True).visual['kind'], 'compass')

    def test_auto_does_not_treat_stale_or_wrong_body_gps_as_arrival(self):
        for invalid in ({'timestamp': '2000-01-01T00:00:00Z'}, {'body': 'Other body'}):
            state = self.sample()
            state['navigation']['distance_m'] = 10
            state['position'].update(invalid)
            card = automatic_surface_card(state, True)
            self.assertEqual(card.visual['kind'], 'compass')
            self.assertIsNone(card.visual['turn'])

    def test_mining_without_a_target_and_missing_hold(self):
        state = self.sample()
        state['selected_site'] = None
        self.assertEqual(automatic_surface_card(state, True).primary, '203 t')
        state['cargo']['rhino']['count'] = None
        card = rhino_progress_card(state, True)
        self.assertEqual(card.metric, '--')
        self.assertIsNone(card.visual['value'])
        state['cargo']['rhino']['count'] = 0
        self.assertEqual(rhino_progress_card(state, True).metric, '0/72 t')
        state['session']['active'] = False
        self.assertEqual(rhino_progress_card(state, True).status, 'LAST DEPLOYMENT')

    def test_disconnect_does_not_retain_mining_values(self):
        for build in (automatic_surface_card, rhino_progress_card, mining_card):
            card = build(self.sample(), False)
            self.assertEqual(card.status, 'OFFLINE')
            self.assertEqual(card.metric, '--')
            self.assertNotIn('203', card.primary)

    def test_prospector_is_a_dated_report_without_navigation(self):
        state = {'last_prospect': {'timestamp': '2026-11-17T12:00:00Z', 'remaining': 0,
                 'materials': [{'name': 'Osmium', 'proportion': 3}, {'name': 'Platinum', 'proportion': 51.7}]},
                 'refined_tons': 0, 'tons_per_hour': None}
        card = mining_card(state, True)
        self.assertEqual(card.title, 'Platinum')
        self.assertEqual(card.primary, '51.7%')
        self.assertEqual(card.metric, '0 t')
        self.assertEqual(card.stats[0][1], '0%')
        self.assertEqual(card.stats[1][1], '--')
        self.assertIn('2026-11-17', card.context)
        self.assertEqual(card.status, 'LAST PROSPECTOR')
        self.assertEqual(card.visual['kind'], 'gauge')
        self.assertNotIn('bearing', card.visual)
        state['ended'] = True
        self.assertEqual(mining_card(state, True).status, 'LAST SESSION')

    def test_switch_rejects_inflight_reply_and_expiry_clears_values(self):
        feed = Feed(8766, mode='surface')
        feed.accept(0, self.sample())
        self.assertNotEqual(feed.view().status, 'OFFLINE')
        feed.select('mining')
        feed.accept(0, self.sample())
        self.assertEqual(feed.view().status, 'OFFLINE')
        feed.accept(1, {'refined_tons': 12})
        self.assertEqual(feed.view().metric, '12 t')
        feed.last_ok = time.monotonic() - 6
        self.assertEqual(feed.view().metric, '--')
        with self.assertRaises(ValueError):
            feed.select('https://untrusted.example')

    def test_rig_processing_keeps_progress_when_gps_goes_quiet(self):
        state = self.sample()
        state['session'].update(started_at='2026-11-17T12:00:00Z', total_t=0)
        state['navigation']['distance_m'] = 10
        feed = Feed(8766, mode='surface')
        feed.accept(0, state)
        self.assertEqual(feed.view().primary, '0 t')
        quiet = copy.deepcopy(state)
        quiet['position']['timestamp'] = '2000-01-01T00:00:00Z'
        quiet['navigation'] = {'distance_m': None, 'bearing': None}
        feed.accept(0, quiet)
        for _ in range(3):
            self.assertEqual(feed.view().visual['kind'], 'gauge')
            self.assertEqual(feed.view().primary, '0 t')
        # A network outage hides values but does not forget the same deployment's arrival.
        feed.last_ok -= 6
        self.assertEqual(feed.view().status, 'OFFLINE')
        feed.accept(0, quiet)
        self.assertEqual(feed.view().primary, '0 t')
        # Other HUD clients must not inherit this client's remembered arrival.
        fresh_feed = Feed(8766, mode='surface'); fresh_feed.accept(0, quiet)
        self.assertEqual(fresh_feed.view().visual['kind'], 'compass')

    def test_automatic_arrival_memory_resets_for_new_scope_or_departure(self):
        original = self.sample()
        original['commander_key'] = 'one'
        original['session']['started_at'] = '2026-11-17T12:00:00Z'
        original['navigation']['distance_m'] = 10
        for change in ('commander', 'deployment', 'target', 'coordinates', 'ended', 'body', 'far'):
            with self.subTest(change=change):
                feed = Feed(8766, mode='surface'); feed.accept(0, original)
                self.assertEqual(feed.view().visual['kind'], 'gauge')
                state = copy.deepcopy(original)
                if change == 'far':
                    state['navigation']['distance_m'] = 2500
                else:
                    state['position']['timestamp'] = '2000-01-01T00:00:00Z'
                    state['navigation'] = {'distance_m': None, 'bearing': None}
                if change == 'commander': state['commander_key'] = 'two'
                if change == 'deployment': state['session']['started_at'] = '2026-11-17T13:00:00Z'
                if change == 'target': state['selected_site']['id'] = 'new-target'
                if change == 'coordinates': state['selected_site']['latitude'] = 20
                if change == 'ended': state['session']['active'] = False
                if change == 'body': state['position']['body'] = 'Other body'
                feed.accept(0, state)
                self.assertEqual(feed.view().visual['kind'], 'compass')

    def test_nearby_motion_and_manual_navigation_do_not_erase_progress(self):
        state = self.sample(); state['navigation']['distance_m'] = 1900
        feed = Feed(8766, mode='surface'); feed.accept(0, state)
        self.assertEqual(feed.view().visual['kind'], 'gauge')
        state = copy.deepcopy(state); state['navigation']['distance_m'] = 2100
        feed.accept(0, state)
        self.assertEqual(feed.view().visual['kind'], 'gauge')
        feed.select('navigation'); feed.accept(1, state)
        self.assertEqual(feed.view().visual['kind'], 'compass')
        feed.select('surface'); feed.accept(2, state)
        self.assertEqual(feed.view().visual['kind'], 'gauge')


if __name__ == '__main__':
    unittest.main()
