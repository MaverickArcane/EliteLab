"""Domain-level device and group checks; no network service is implemented."""
import hashlib
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from experimental.groups import plans


class GroupPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = sqlite3.connect(Path(self.tmp.name) / 'group.sqlite')
        self.addCleanup(lambda: self.db.close())
        plans.initialize(self.db)
        self.db.executemany('INSERT INTO memberships VALUES (?,?,?)', [
            ('a', 'leader', 'leader'), ('a', 'member', 'member'), ('a', 'viewer', 'viewer'),
            ('b', 'other', 'leader')])
        self.tokens = {name: bytes([i]) * 32 for i, name in enumerate(('leader', 'member', 'viewer', 'other', 'missing'), 1)}
        self.db.executemany('INSERT INTO devices(verifier,account_id) VALUES (?,?)',
                            [(hashlib.sha256(self.tokens[name]).digest(), name) for name in ('leader', 'member', 'viewer', 'other')])
        self.db.commit()
        plans.update_plan(self.db, 'a', self.tokens['leader'], 0, 'Plan', 'Sol', [{'description': 'Step'}])
        self.step = plans.read_plan(self.db, 'a', self.tokens['leader'])['steps'][0]['id']

    def test_membership_and_roles_are_checked_on_every_operation(self):
        self.assertEqual(plans.read_plan(self.db, 'a', self.tokens['viewer'])['title'], 'Plan')
        for account in ('member', 'viewer', 'other', 'missing'):
            with self.subTest(account=account), self.assertRaises(plans.Forbidden):
                plans.update_plan(self.db, 'a', self.tokens[account], 1, 'Changed', '', [])
        for account in ('viewer', 'other', 'missing'):
            with self.subTest(account=account), self.assertRaises(plans.Forbidden):
                plans.set_progress(self.db, 'a', self.tokens[account], self.step, True)
        self.db.execute('DELETE FROM memberships WHERE group_id=? AND account_id=?', ('a', 'member'))
        self.db.commit()
        with self.assertRaises(plans.Forbidden):
            plans.read_plan(self.db, 'a', self.tokens['member'])

    def test_progress_is_per_account_and_cross_group_steps_are_rejected(self):
        plans.set_progress(self.db, 'a', self.tokens['member'], self.step, True)
        self.assertEqual(plans.read_own_progress(self.db, 'a', self.tokens['member']), {self.step: True})
        self.assertEqual(plans.read_own_progress(self.db, 'a', self.tokens['leader']), {})
        plans.update_plan(self.db, 'b', self.tokens['other'], 0, 'Other', '', [{'description': 'B'}])
        foreign = plans.read_plan(self.db, 'b', self.tokens['other'])['steps'][0]['id']
        with self.assertRaises(ValueError):
            plans.set_progress(self.db, 'a', self.tokens['member'], foreign, True)
        with self.assertRaises(ValueError):
            plans.update_plan(self.db, 'a', self.tokens['leader'], 1, 'Plan', '', [{'id': foreign, 'description': 'B'}])

    def test_revoked_or_malformed_device_is_denied(self):
        verifier = hashlib.sha256(self.tokens['member']).digest()
        self.db.execute('UPDATE devices SET revoked=1 WHERE verifier=?', (verifier,))
        self.db.commit()
        for credential in (self.tokens['member'], b'', b'x' * 32, None, 'member'):
            with self.subTest(credential=type(credential)), self.assertRaises(plans.Forbidden):
                plans.read_plan(self.db, 'a', credential)
        with self.assertRaises(plans.Forbidden):
            plans.set_progress(self.db, 'a', self.tokens['member'], self.step, True)

    def test_revision_conflict_reorder_and_restart(self):
        plans.set_progress(self.db, 'a', self.tokens['member'], self.step, True)
        plans.update_plan(self.db, 'a', self.tokens['leader'], 1, 'Updated', '', [
            {'description': 'First'}, {'id': self.step, 'description': 'Retained'}])
        with self.assertRaises(plans.Conflict):
            plans.update_plan(self.db, 'a', self.tokens['leader'], 1, 'Stale', '', [])
        self.db.close()
        self.db = sqlite3.connect(Path(self.tmp.name) / 'group.sqlite')
        plans.initialize(self.db)
        self.assertEqual(plans.read_plan(self.db, 'a', self.tokens['member'])['revision'], 2)
        self.assertEqual(plans.read_own_progress(self.db, 'a', self.tokens['member']), {self.step: True})
        plans.update_plan(self.db, 'a', self.tokens['leader'], 2, 'Removed', '', [])
        self.assertEqual(plans.read_own_progress(self.db, 'a', self.tokens['member']), {})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM plan_history WHERE group_id=?', ('a',)).fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT done FROM progress WHERE group_id=? AND step_id=?', ('a', self.step)).fetchone()[0], 1)

    def test_concurrent_edits_have_one_winner(self):
        barrier = threading.Barrier(2)
        outcomes = []
        def edit(title):
            db = sqlite3.connect(Path(self.tmp.name) / 'group.sqlite', timeout=10)
            try:
                plans.initialize(db)
                barrier.wait(timeout=5)
                try:
                    plans.update_plan(db, 'a', self.tokens['leader'], 1, title, '', [])
                    outcomes.append('saved')
                except plans.Conflict:
                    outcomes.append('conflict')
            finally:
                db.close()
        workers = [threading.Thread(target=edit, args=(name,)) for name in ('One', 'Two')]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=15)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertCountEqual(outcomes, ['saved', 'conflict'])
        self.assertEqual(plans.read_plan(self.db, 'a', self.tokens['leader'])['revision'], 2)


if __name__ == '__main__':
    unittest.main()
