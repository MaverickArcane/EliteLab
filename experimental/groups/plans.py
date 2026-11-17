"""Transactional group plans for a future isolated prototype.

This is not a network service. Device enrollment, invitation redemption,
browser sessions and transport have not been implemented. Each operation checks
the enrolled device and membership together in its transaction.
"""
import hashlib
import hmac
import json
import sqlite3
import uuid


class Forbidden(Exception):
    pass


class Conflict(Exception):
    pass


def initialize(connection):
    connection.executescript('''
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS devices (
            verifier BLOB PRIMARY KEY, account_id TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1))
        );
        CREATE TABLE IF NOT EXISTS memberships (
            group_id TEXT NOT NULL, account_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('leader', 'member', 'viewer')),
            PRIMARY KEY(group_id, account_id)
        );
        CREATE TABLE IF NOT EXISTS plans (
            group_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
            title TEXT NOT NULL, destination TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS steps (
            group_id TEXT NOT NULL, id TEXT NOT NULL, position INTEGER,
            description TEXT NOT NULL, PRIMARY KEY(group_id, id),
            UNIQUE(group_id, position), FOREIGN KEY(group_id) REFERENCES plans(group_id)
        );
        CREATE TABLE IF NOT EXISTS progress (
            group_id TEXT NOT NULL, step_id TEXT NOT NULL, account_id TEXT NOT NULL,
            done INTEGER NOT NULL CHECK(done IN (0, 1)),
            PRIMARY KEY(group_id, step_id, account_id),
            FOREIGN KEY(group_id, step_id) REFERENCES steps(group_id, id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS plan_history (
            group_id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
            PRIMARY KEY(group_id, revision), FOREIGN KEY(group_id) REFERENCES plans(group_id)
        );
    ''')


def role(connection, group_id, credential, allowed):
    if not isinstance(credential, bytes) or len(credential) != 32:
        raise Forbidden()
    verifier = hashlib.sha256(credential).digest()
    device = connection.execute('SELECT verifier,account_id,revoked FROM devices WHERE verifier=?', (verifier,)).fetchone()
    if not device or not hmac.compare_digest(device[0], verifier) or device[2]:
        raise Forbidden()
    account_id = device[1]
    row = connection.execute('SELECT role FROM memberships WHERE group_id=? AND account_id=?',
                             (group_id, account_id)).fetchone()
    if not row or row[0] not in allowed:
        raise Forbidden()
    return account_id


def read_plan(connection, group_id, credential):
    connection.execute('BEGIN')
    try:
        role(connection, group_id, credential, ('leader', 'member', 'viewer'))
        plan = connection.execute('SELECT revision,title,destination FROM plans WHERE group_id=?', (group_id,)).fetchone()
        if not plan:
            connection.commit()
            return None
        steps = connection.execute('''SELECT id,description FROM steps
                                      WHERE group_id=? AND position IS NOT NULL ORDER BY position''', (group_id,)).fetchall()
        connection.commit()
        return {'revision': plan[0], 'title': plan[1], 'destination': plan[2],
                'steps': [{'id': step[0], 'description': step[1]} for step in steps]}
    except BaseException:
        connection.rollback()
        raise


def update_plan(connection, group_id, credential, revision, title, destination, steps):
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError('invalid revision')
    if not isinstance(title, str) or not 1 <= len(title) <= 200 or not isinstance(destination, str) or len(destination) > 200:
        raise ValueError('invalid plan')
    if not isinstance(steps, list) or len(steps) > 100:
        raise ValueError('invalid steps')
    normalized, seen = [], set()
    for step in steps:
        if not isinstance(step, dict) or set(step) - {'id', 'description'}:
            raise ValueError('invalid step')
        description = step.get('description')
        identity = step.get('id')
        if not isinstance(description, str) or not 1 <= len(description) <= 500:
            raise ValueError('invalid description')
        if identity is not None and (not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity)):
            raise ValueError('invalid step id')
        identity = identity or uuid.uuid4().hex
        if identity in seen:
            raise ValueError('duplicate step id')
        seen.add(identity)
        normalized.append((identity, description))
    connection.execute('BEGIN IMMEDIATE')
    try:
        role(connection, group_id, credential, ('leader',))
        current = connection.execute('SELECT revision FROM plans WHERE group_id=?', (group_id,)).fetchone()
        if (current[0] if current else 0) != revision:
            raise Conflict()
        existing = {row[0] for row in connection.execute('SELECT id FROM steps WHERE group_id=? AND position IS NOT NULL', (group_id,))}
        supplied = {step['id'] for step in steps if step.get('id') is not None}
        if not supplied <= existing:
            raise ValueError('unknown step id')
        if current:
            connection.execute('UPDATE plans SET revision=?,title=?,destination=? WHERE group_id=?',
                               (revision + 1, title, destination, group_id))
        else:
            connection.execute('INSERT INTO plans VALUES (?,?,?,?)', (group_id, 1, title, destination))
        # Removed steps stay tombstoned to preserve history and progress.
        connection.execute('UPDATE steps SET position=NULL WHERE group_id=?', (group_id,))
        for position, (identity, description) in enumerate(normalized):
            if identity in existing:
                connection.execute('UPDATE steps SET position=?,description=? WHERE group_id=? AND id=?',
                                   (position, description, group_id, identity))
            else:
                connection.execute('INSERT INTO steps VALUES (?,?,?,?)', (group_id, identity, position, description))
        snapshot = {'title': title, 'destination': destination,
                    'steps': [{'id': identity, 'description': description} for identity, description in normalized]}
        connection.execute('INSERT INTO plan_history VALUES (?,?,?)',
                           (group_id, revision + 1, json.dumps(snapshot, ensure_ascii=False)))
        connection.commit()
        return revision + 1
    except BaseException:
        connection.rollback()
        raise


def set_progress(connection, group_id, credential, step_id, done):
    if not isinstance(done, bool):
        raise ValueError('done must be boolean')
    connection.execute('BEGIN IMMEDIATE')
    try:
        account_id = role(connection, group_id, credential, ('leader', 'member'))
        if not connection.execute('SELECT 1 FROM steps WHERE group_id=? AND id=? AND position IS NOT NULL', (group_id, step_id)).fetchone():
            raise ValueError('unknown step')
        connection.execute('''INSERT INTO progress VALUES (?,?,?,?)
            ON CONFLICT(group_id,step_id,account_id) DO UPDATE SET done=excluded.done''',
            (group_id, step_id, account_id, int(done)))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def read_own_progress(connection, group_id, credential):
    connection.execute('BEGIN')
    try:
        account_id = role(connection, group_id, credential, ('leader', 'member'))
        result = {step_id: bool(done) for step_id, done in connection.execute(
            '''SELECT progress.step_id,progress.done FROM progress JOIN steps
               ON progress.group_id=steps.group_id AND progress.step_id=steps.id
               WHERE progress.group_id=? AND progress.account_id=? AND steps.position IS NOT NULL''',
            (group_id, account_id))}
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
