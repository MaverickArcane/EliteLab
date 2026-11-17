"""Exercise invitation transactions without exposing a service."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from experimental.groups import invitations, plans


class InvitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'groups.sqlite'
        self.db = self.connect()
        self.addCleanup(lambda: self.db.close())
        self.leader = b'L' * 32
        self.db.execute('INSERT INTO devices(verifier,account_id) VALUES (?,?)',
                        (hashlib.sha256(self.leader).digest(), 'leader'))
        self.db.execute('INSERT INTO memberships VALUES (?,?,?)', ('g', 'leader', 'leader'))
        self.db.commit()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        plans.initialize(db)
        invitations.initialize(db)
        return db

    def test_one_use_and_membership_bound_to_new_device(self):
        secret = invitations.create(self.db, 'g', self.leader, 'member', 100, now=1000)
        self.assertNotIn(secret, self.path.read_bytes())
        account = invitations.redeem(self.db, secret, b'M' * 32, 'source', now=1001)
        self.assertEqual(self.db.execute('SELECT role FROM memberships WHERE account_id=?', (account,)).fetchone(), ('member',))
        with self.assertRaises(invitations.RedemptionFailed):
            invitations.redeem(self.db, secret, b'N' * 32, 'source', now=1002)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM memberships').fetchone()[0], 2)

    def test_concurrent_redemption_has_one_winner(self):
        secret = invitations.create(self.db, 'g', self.leader, 'viewer', 100, now=1000)
        barrier = threading.Barrier(2)
        results = []
        def redeem(index):
            db = self.connect()
            try:
                barrier.wait(timeout=5)
                try:
                    invitations.redeem(db, secret, bytes([index]) * 32, 'source' + str(index), now=1001)
                    results.append('success')
                except invitations.RedemptionFailed:
                    results.append('denied')
            finally:
                db.close()
        threads = [threading.Thread(target=redeem, args=(i,)) for i in (1, 2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ['success', 'denied'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM memberships').fetchone()[0], 2)

    def test_expiry_revocation_and_persistent_rate_limit(self):
        secret = invitations.create(self.db, 'g', self.leader, 'member', 10, now=1000)
        with self.assertRaises(invitations.RedemptionFailed):
            invitations.redeem(self.db, secret, b'M' * 32, 'expired', now=1010)
        other = invitations.create(self.db, 'g', self.leader, 'member', 100, now=1000)
        self.db.execute('UPDATE invitations SET revoked=1 WHERE verifier=?', (hashlib.sha256(other).digest(),))
        self.db.commit()
        with self.assertRaises(invitations.RedemptionFailed):
            invitations.redeem(self.db, other, b'M' * 32, 'revoked', now=1001)
        for _ in range(invitations.ATTEMPTS):
            with self.assertRaises(invitations.RedemptionFailed):
                invitations.redeem(self.db, b'wrong' * 6, b'M' * 32, 'limited', now=1001)
        self.db.close()
        self.db = self.connect()
        fresh = invitations.create(self.db, 'g', self.leader, 'member', 500, now=1000)
        with self.assertRaises(invitations.RedemptionFailed):
            invitations.redeem(self.db, fresh, b'M' * 32, 'limited', now=1002)
        self.assertTrue(invitations.redeem(self.db, fresh, b'M' * 32, 'limited', now=1302))


if __name__ == '__main__':
    unittest.main()
