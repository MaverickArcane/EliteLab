"""Experimental invitation transactions, not an HTTP or enrollment service."""
import hashlib
import hmac
import secrets
import time
import uuid

from .plans import Forbidden, role

WINDOW_SECONDS = 300
ATTEMPTS = 10
MAX_LIFETIME = 24 * 60 * 60
MAX_BUCKETS = 10000


class RedemptionFailed(Exception):
    """A generic error which does not reveal invitation status."""


def initialize(connection):
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS invitations (
            verifier BLOB PRIMARY KEY, group_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('member', 'viewer')),
            expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0,
            revoked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS redemption_limits (
            bucket BLOB PRIMARY KEY, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL
        );
    ''')


def create(connection, group_id, leader_credential, invited_role, lifetime, now=None):
    if invited_role not in ('member', 'viewer') or not isinstance(lifetime, int) or isinstance(lifetime, bool) or not 1 <= lifetime <= MAX_LIFETIME:
        raise ValueError('invalid invitation')
    now = int(time.time()) if now is None else int(now)
    secret = secrets.token_bytes(32)
    verifier = hashlib.sha256(secret).digest()
    connection.execute('BEGIN IMMEDIATE')
    try:
        role(connection, group_id, leader_credential, ('leader',))
        connection.execute('INSERT INTO invitations(verifier,group_id,role,expires) VALUES (?,?,?,?)',
                           (verifier, group_id, invited_role, now + lifetime))
        connection.commit()
        return secret
    except BaseException:
        connection.rollback()
        raise


def redeem(connection, secret, device_credential, source, now=None):
    """Consume a single invitation and enroll one device, in one transaction.

    The future authenticated transport must supply a normalized trusted source;
    arbitrary forwarding headers cannot be used. The prototype currently has
    only source and invitation throttling; production enrollment needs the full
    rate-limiting and recovery controls in the design.
    """
    now = int(time.time()) if now is None else int(now)
    if not isinstance(source, str) or not 1 <= len(source) <= 200:
        raise ValueError('invalid source')
    valid_secret = isinstance(secret, bytes) and len(secret) == 32
    valid_device = isinstance(device_credential, bytes) and len(device_credential) == 32
    verifier = hashlib.sha256(secret if valid_secret else b'invalid').digest()
    buckets = (hashlib.sha256(b'source:' + source.encode('utf-8')).digest(),
               hashlib.sha256(b'invitation:' + verifier).digest())
    connection.execute('BEGIN IMMEDIATE')
    try:
        connection.execute('DELETE FROM redemption_limits WHERE window_start <= ?', (now - WINDOW_SECONDS,))
        missing = sum(not connection.execute('SELECT 1 FROM redemption_limits WHERE bucket=?', (bucket,)).fetchone()
                      for bucket in buckets)
        if connection.execute('SELECT COUNT(*) FROM redemption_limits').fetchone()[0] + missing > MAX_BUCKETS:
            connection.commit()
            raise RedemptionFailed()
        limited = False
        for bucket in buckets:
            row = connection.execute('SELECT window_start,attempts FROM redemption_limits WHERE bucket=?', (bucket,)).fetchone()
            start, count = (now, 0) if not row or now < row[0] or now - row[0] >= WINDOW_SECONDS else row
            count += 1
            connection.execute('''INSERT INTO redemption_limits VALUES (?,?,?)
                ON CONFLICT(bucket) DO UPDATE SET window_start=excluded.window_start,attempts=excluded.attempts''',
                (bucket, start, count))
            limited |= count > ATTEMPTS
        invite = connection.execute('SELECT verifier,group_id,role,expires,used,revoked FROM invitations WHERE verifier=?',
                                    (verifier,)).fetchone()
        if (limited or not valid_secret or not valid_device or not invite or
                not hmac.compare_digest(invite[0], verifier) or invite[3] <= now or invite[4] or invite[5]):
            connection.commit()
            raise RedemptionFailed()
        device_hash = hashlib.sha256(device_credential).digest()
        if connection.execute('SELECT 1 FROM devices WHERE verifier=?', (device_hash,)).fetchone():
            connection.commit()
            raise RedemptionFailed()
        account_id = uuid.uuid4().hex
        connection.execute('INSERT INTO devices(verifier,account_id) VALUES (?,?)', (device_hash, account_id))
        connection.execute('INSERT INTO memberships VALUES (?,?,?)', (invite[1], account_id, invite[2]))
        connection.execute('UPDATE invitations SET used=1 WHERE verifier=?', (verifier,))
        connection.commit()
        return account_id
    except RedemptionFailed:
        raise
    except BaseException:
        connection.rollback()
        raise
