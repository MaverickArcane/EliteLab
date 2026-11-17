import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from elitelab import hud_activities as a
from elitelab.hud_samples import SAMPLES, JOURNAL
from elitelab.overlay import CATALOG, MODES, Feed, demo_card, mode_from_uri


class HudActivityTests(unittest.TestCase):
    def test_catalog_covers_dashboard_cards_and_matches_providers(self):
        covered = [card for row in CATALOG for card in row['cards']]
        self.assertEqual(len(covered), len(set(covered)))
        root = Path(__file__).resolve().parents[1]
        cards = [c['id'] for file in (root/'modules').glob('*/module.json')
                 for c in json.loads(file.read_text())['cards']]
        self.assertEqual(set(covered), set(cards))
        self.assertEqual(set(MODES), {r['id'] for r in CATALOG})
        for key, mode in MODES.items():
            with self.subTest(mode=key):
                self.assertTrue(mode.endpoint.startswith('/api/'))
                for word in ('/search', '/plan?', '/refresh', '/join', '/advert', '/select'):
                    self.assertNotIn(word, mode.endpoint)
                sample = demo_card(key)
                self.assertIsInstance(sample.primary, str)
                self.assertEqual(mode.build({}, False).status, 'OFFLINE')
                self.assertEqual(mode.build({}, False).metric, '--')

    def test_uri_only_selects_known_modes(self):
        self.assertIsNone(mode_from_uri('elitelab-hud:open'))
        for key in MODES:
            self.assertEqual(mode_from_uri('elitelab-hud:open?mode='+key), key)
        for uri in ('https://example.com', 'elitelab-hud://open', 'elitelab-hud:open?mode=missing',
                    'elitelab-hud:open?mode=flight&mode=cargo', 'elitelab-hud:open?path=c:/file',
                    'elitelab-hud:open?mode=flight#part', 'elitelab-hud:open?mode=flight" --demo',
                    'elitelab-hud:open?mode=%22', 'elitelab-hud:open?mode=flight\n', 'elitelab-hud:open?mode='):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                mode_from_uri(uri)

    def test_flight_never_suggests_a_next_jump_when_off_route(self):
        sample = copy.deepcopy(SAMPLES['flight'])
        sample['status'] = 'off_route'
        card = a.flight(sample)
        self.assertNotEqual(card.primary, 'Sample B')
        self.assertEqual(card.metric, '--')
        self.assertEqual(card.visual['kind'], 'badge')

    def test_stale_combat_status_does_not_keep_shields_or_fuel_live(self):
        sample = copy.deepcopy(JOURNAL)
        sample['status']['timestamp'] = '2000-01-01T00:00:00Z'
        sample['status']['in_danger'] = True
        card = a.combat(sample)
        self.assertEqual(card.primary, 'Status unavailable')
        self.assertEqual(card.stats[0][1], '--')
        self.assertEqual(card.warning, '')
        self.assertEqual(card.metric, '92%')
        self.assertIn('LAST REPORTED', card.metric_label)

    def test_changed_ship_hides_build_and_neutron_progress(self):
        sample = copy.deepcopy(SAMPLES['build']); sample['progress']['same_ship'] = False
        self.assertIsNone(a.build(sample).visual['value'])
        self.assertEqual(a.build(sample).metric, '--')
        sample = copy.deepcopy(SAMPLES['neutron']); sample['ship_changed'] = True
        self.assertNotIn('Sample Neutron', a.neutron(sample).primary)
        self.assertEqual(a.neutron(sample).metric, '--')

    def test_paused_crew_does_not_offer_a_load(self):
        sample = copy.deepcopy(SAMPLES['hauling']); sample['stale'] = True
        self.assertEqual(a.hauling(sample).metric, '--')
        self.assertEqual(a.hauling(sample).status, 'PAUSED')

    def test_credits_and_quantities_keep_unknown_separate_from_zero(self):
        self.assertEqual(a.money(None), '--')
        self.assertEqual(a.money(0), '0 Cr')
        self.assertEqual(a.cargo({'cargo': {'count': 0, 'items': []}, 'cargo_capacity': 72}).primary, '0 t')
        self.assertEqual(a.cargo({'cargo': {'count': None}, 'cargo_capacity': 72}).primary, '--')
        sample = copy.deepcopy(SAMPLES['wishlist']); sample['wishlist']['inventory_known'] = False
        self.assertEqual(a.wishlist(sample).primary, '--')
        self.assertIsNone(a.wishlist(sample).visual['value'])

    def test_sale_plan_changes_and_ptn_blockers_stay_visible(self):
        sample = copy.deepcopy(SAMPLES['selling']); sample['plan']['cargo_changed'] = True
        self.assertIn('Cargo changed', a.selling(sample).warning)
        sample = copy.deepcopy(SAMPLES['ptn']); sample['operation']['blockers'] = ['Recheck price']
        self.assertEqual(a.ptn(sample).warning, 'Recheck price')

    def test_trade_leg_is_human_numbered_and_profit_is_estimated(self):
        card = a.personal(SAMPLES['personal'])
        self.assertEqual(card.stats[0][1], '1/2')
        self.assertIn('EST.', card.stats[1][0])

    def test_profit_hud_separates_receipts_estimates_and_missing_costs(self):
        sample = copy.deepcopy(SAMPLES['profits'])
        card = a.profits(sample)
        self.assertEqual(card.primary, '2.48M Cr')
        self.assertEqual(card.metric, '640.00k Cr')
        self.assertIn('ESTIMATE', card.metric_label)
        sample['session'].update(profit=None, unknown_sales=1)
        self.assertEqual(a.profits(sample).primary, '--')
        self.assertIn('unknown', a.profits(sample).warning)
        self.assertEqual(a.profits(sample, False).status, 'OFFLINE')

    def test_real_http_feed_mode_change_and_missing_module(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                if self.path.startswith('/api/flight/navigation'):
                    payload = json.dumps(SAMPLES['flight']).encode()
                    self.send_response(200); self.end_headers(); self.wfile.write(payload)
                else:
                    self.send_error(404)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        feed = Feed(server.server_port, interval=.03, mode='flight')
        def wait(predicate):
            end = time.monotonic() + 3
            while time.monotonic() < end:
                if predicate(): return
                time.sleep(.02)
            self.fail('HUD feed did not reach expected state')
        try:
            feed.start(); wait(lambda: feed.view().primary == 'Sample B')
            feed.select('missions'); wait(lambda: feed.view().status == 'UNAVAILABLE')
            self.assertEqual(feed.view().metric, '--')
            self.assertTrue(all(path.startswith(('/api/flight/navigation', '/api/missions/plan')) for path in calls))
        finally:
            feed.close(); feed.thread.join(timeout=4)
            server.shutdown(); server.server_close()
