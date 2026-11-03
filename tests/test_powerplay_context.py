"""Recorded merit gains and explicitly uncertain nearby journal activity."""
import json
from datetime import datetime, timedelta, timezone
import unittest

import test_mining


class PowerplayContextTests(unittest.TestCase):
    setUp = test_mining.MiningTests.setUp
    emit = test_mining.MiningTests.emit

    def state(self):
        return self.core.http.tools['get_powerplay_status'].fn({})

    def test_sale_context_is_uncertain_and_unknown_stays_unknown(self):
        self.emit('LoadGame', '2026-11-02T12:00:00Z', Commander='A', FID='F1')
        self.emit('PowerplayJoin', '2026-11-02T12:00:01Z', Power='Edmund Mahon')
        self.emit('MarketSell', '2026-11-02T12:00:03Z', Type='platinum', Type_Localised='<Platinum>', Count=10, TotalSale=4000000)
        self.emit('PowerplayMerits', '2026-11-02T12:00:05Z', Power='Edmund Mahon', MeritsGained=190, TotalMerits=190)
        self.emit('PowerplayMerits', '2026-11-02T12:00:40Z', Power='Edmund Mahon', MeritsGained=30, TotalMerits=220)
        state = self.state()
        self.assertEqual(state['session_merits'], 220)
        self.assertEqual(state['merits'], 220)
        self.assertEqual(state['merit_log'][0]['context'], {'kind':'sale','detail':'<Platinum>',
            'at':'2026-11-02T12:00:03Z','delay_s':2.0,'basis':'nearby journal event'})
        self.assertIsNone(state['merit_log'][1]['context'])
        self.assertEqual(state['session_started_at'], '2026-11-02T12:00:00Z')
        self.assertEqual(state['pledge_changed_at'], '2026-11-02T12:00:01Z')
        self.assertIn('not a confirmed reward source',self.core.http.tools['get_powerplay_status'].description)
        json.dumps(state, allow_nan=False)

    def test_duplicate_and_out_of_order_events_keep_one_stable_timeline(self):
        self.emit('LoadGame','2026-11-02T12:00:00Z',Commander='A',FID='F1')
        newer = {'Power':'Edmund Mahon','MeritsGained':30,'TotalMerits':220}
        self.emit('PowerplayMerits','2026-11-02T12:00:40Z',**newer)
        self.emit('PowerplayMerits','2026-11-02T12:00:40Z',**newer)
        self.emit('PowerplayMerits','2026-11-02T12:00:05Z',Power='Edmund Mahon',MeritsGained=190,TotalMerits=190)
        state=self.state()
        self.assertEqual([m['gained'] for m in state['merit_log']],[190,30])
        self.assertEqual(state['session_merits'],220)
        self.assertEqual(state['merits'],220)
        self.assertEqual(self.core.http.tools['get_merits_summary'].fn({})['session_merits'],220)

    def test_session_pledge_and_commander_boundaries_clear_context(self):
        self.emit('LoadGame','2026-11-02T12:00:00Z',Commander='A',FID='F1')
        self.emit('MarketSell','2026-11-02T12:00:01Z',Type='platinum')
        self.emit('PowerplayDefect','2026-11-02T12:00:02Z',ToPower='Aisling Duval')
        self.emit('PowerplayMerits','2026-11-02T12:00:03Z',Power='Aisling Duval',MeritsGained=10,TotalMerits=10)
        self.assertIsNone(self.state()['merit_log'][0]['context'])
        self.emit('PowerplayMerits','2026-11-02T12:00:01Z',Power='Edmund Mahon',MeritsGained=190,TotalMerits=190)
        self.assertEqual(self.state()['session_merits'],10)
        self.assertEqual(self.core.http.tools['get_merits_summary'].fn({})['session_merits'],10)
        self.emit('Commander','2026-11-02T12:00:04Z',Name='A',FID='F1')
        self.assertEqual(self.state()['session_merits'],10)
        self.emit('Commander','2026-11-02T12:00:05Z',Name='B',FID='F2')
        self.assertEqual(self.state()['merit_log'],[])
        self.assertEqual(self.state()['power'],'Aisling Duval')
        self.assertFalse(self.state()['power_observed_this_session'])
        self.assertIsNone(self.state()['merits'])
        self.emit('LoadGame','2026-11-02T12:01:00Z',Commander='B',FID='F2')
        self.assertEqual(self.state()['session_started_at'],'2026-11-02T12:01:00Z')

    def test_invalid_gain_does_not_pollute_recorded_totals(self):
        self.emit('LoadGame','2026-11-02T12:00:00Z',Commander='A',FID='F1')
        for value in (True,-1,float('nan'),'100'):
            self.emit('PowerplayMerits','2026-11-02T12:00:01Z',MeritsGained=value,TotalMerits=100)
        self.assertEqual(self.state()['session_merits'],0)
        self.assertEqual(self.state()['merit_log'],[])

    def test_merit_rate_accepts_offset_time_and_rejects_future_cause(self):
        self.emit('LoadGame','2026-11-02T12:00:00+00:00',Commander='A',FID='F1')
        self.emit('MarketSell','2026-11-02T12:00:03+00:00',Type='platinum',Count=10,TotalSale=4000000)
        self.emit('PowerplayMerits','2026-11-02T12:00:05+00:00',Power='Edmund Mahon',MeritsGained=190,TotalMerits=190)
        summary=self.core.http.tools['get_merits_summary'].fn({})
        self.assertEqual(summary['by_activity']['trade']['merits'],190)
        self.emit('MarketSell','2026-11-02T12:00:50+00:00',Type='platinum',Count=10,TotalSale=4000000)
        self.emit('PowerplayMerits','2026-11-02T12:00:40+00:00',Power='Edmund Mahon',MeritsGained=30,TotalMerits=220)
        summary=self.core.http.tools['get_merits_summary'].fn({})
        self.assertEqual(summary['by_activity']['unattributed']['merits'],30)

    def test_recent_offset_gain_counts_in_last_hour(self):
        now=datetime.now(timezone.utc)
        self.emit('LoadGame',(now-timedelta(minutes=2)).isoformat(),Commander='A',FID='F1')
        self.emit('PowerplayMerits',(now-timedelta(seconds=20)).isoformat(),Power='Edmund Mahon',MeritsGained=20,TotalMerits=20)
        self.assertEqual(self.core.http.tools['get_merits_summary'].fn({})['last_hour'],20)
