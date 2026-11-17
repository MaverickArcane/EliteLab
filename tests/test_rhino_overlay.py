import json
from pathlib import Path
import tempfile
import time
import unittest

from modules.rhino.overlay import Feed, demo_state, guidance
from elitelab.rhino_overlay import load_preferences, save_preferences


class RhinoOverlayTests(unittest.TestCase):
    def test_turn_wrap_and_arrival(self):
        state = demo_state()
        state['position']['heading'] = 350
        state['navigation']['bearing'] = 10
        self.assertEqual(guidance(state)['turn'], 20)
        state['position']['heading'] = 10
        state['navigation']['bearing'] = 350
        self.assertEqual(guidance(state)['turn'], -20)
        state['navigation']['bearing'] = 12
        self.assertEqual(guidance(state)['mode'], 'aligned')
        state['navigation']['distance_m'] = 0
        self.assertEqual(guidance(state)['mode'], 'arrived')
        self.assertIsNone(guidance(state)['turn'])

    def test_missing_heading_keeps_compass_but_no_relative_arrow(self):
        state = demo_state()
        for heading in (None, True, '230', float('nan'), -1, 361):
            state['position']['heading'] = heading
            view = guidance(state)
            self.assertIsNone(view['turn'])
            self.assertEqual(view['status'], 'BEARING ONLY')
            self.assertEqual(view['bearing'], 207)

    def test_stale_gps_wrong_body_and_disconnect_clear_guidance(self):
        state = demo_state()
        for change in ({'timestamp': '2000-01-01T00:00:00Z'}, {'body': 'Other body'}, {'system': 'Other system'}, {'latitude': None}):
            sample = json.loads(json.dumps(state)); sample['position'].update(change)
            self.assertIsNone(guidance(sample)['turn'])
            self.assertIsNone(guidance(sample)['distance'])
        view = guidance(state, connected=False)
        self.assertEqual(view['status'], 'OFFLINE')
        self.assertIsNone(view['turn']); self.assertEqual(view['hold'], '--')
        self.assertIsNone(guidance(state, now=time.time() - 10)['turn'])

    def test_preserves_unknown_vs_zero_cargo_and_report_warning(self):
        state = demo_state()
        state['cargo']['rhino']['count'] = 0
        state['selected_site']['availability'] = 'reported_depleted'
        self.assertEqual(guidance(state)['hold'], '0/72 t')
        self.assertIn('depleted', guidance(state)['warning'])
        state['cargo']['rhino']['count'] = None
        self.assertEqual(guidance(state)['hold'], '--')

    def test_preferences_validate_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'overlay.json'
            self.assertEqual(load_preferences(path), {})
            save_preferences(path, dict(pinned=False, glass=True, opacity=70, x=-1200, y=40))
            self.assertEqual(load_preferences(path), dict(pinned=False, glass=True, opacity=70, x=-1200, y=40))
            save_preferences(path, dict(activity='rhino', locked=True))
            self.assertEqual(load_preferences(path), dict(activity='rhino'))
            save_preferences(path, dict(activity='unknown'))
            self.assertEqual(load_preferences(path), {})
            save_preferences(path, dict(activity=['rhino']))
            self.assertEqual(load_preferences(path), {})
            path.write_text('{"pinned":"false","glass":0,"opacity":2,"x":true,"y":100001}')
            self.assertEqual(load_preferences(path), {})
            path.write_text('not json')
            self.assertEqual(load_preferences(path), {})

    def test_feed_initial_and_expired_connection_pause(self):
        feed = Feed(8766)
        self.assertEqual(feed.url, 'http://127.0.0.1:8766/api/rhino')
        self.assertEqual(feed.view()['status'], 'OFFLINE')
        feed.state = demo_state(); feed.connected = True; feed.last_ok = time.monotonic()
        self.assertEqual(feed.view()['status'], 'SURFACE GPS')
        feed.last_ok -= 6
        self.assertIsNone(feed.view()['turn'])
        for invalid in (0, 65536, '8766'):
            with self.assertRaises(ValueError): Feed(invalid)


if __name__ == '__main__':
    unittest.main()
