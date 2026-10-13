"""Local durable source handoff, separate from canonical selection and model work.

Only caller-authorized bytes belong here. This journal neither discovers sources
nor grants identity. A receipt means exact bytes/payload survived a transaction,
not that anything was selected as memory. No retention or model calls are implicit.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time


def wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def sha(value):
    return hashlib.sha256(value).hexdigest()


class Inbox:
    def __init__(self, path, binding):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.binding = wire(binding)
        with self.connect() as con:
            con.executescript('''
              BEGIN IMMEDIATE;
              CREATE TABLE IF NOT EXISTS binding(value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS revisions(
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, parent INTEGER REFERENCES revisions(id),
                supersedes INTEGER REFERENCES revisions(id), offset INTEGER NOT NULL,
                size INTEGER NOT NULL, sha256 TEXT NOT NULL, delta BLOB NOT NULL,
                recorded_ns INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS heads(source TEXT PRIMARY KEY, revision INTEGER NOT NULL REFERENCES revisions(id));
              CREATE TABLE IF NOT EXISTS observations(
                id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
                revision INTEGER REFERENCES revisions(id), payload TEXT NOT NULL, error TEXT,
                recorded_ns INTEGER NOT NULL);
            ''')
            rows = con.execute('SELECT value FROM binding').fetchall()
            if not rows:
                con.execute('INSERT INTO binding VALUES(?)', (self.binding,))
            elif len(rows) != 1 or rows[0][0] != self.binding:
                raise ValueError('inbox binding differs; existing data preserved')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=1)
        try:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA synchronous=FULL')
            with con:
                yield con
        finally:
            con.close()

    def observe(self, source, payload, snapshot, *, error=None, _fault=None):
        if not isinstance(source, str) or not source or not isinstance(payload, dict):
            raise ValueError('explicit source and object payload required')
        if snapshot is not None and not isinstance(snapshot, bytes):
            raise ValueError('snapshot must be exact bytes or unavailable')
        if (snapshot is None) != (isinstance(error, str) and bool(error)):
            raise ValueError('unavailable snapshot requires an explicit error')
        serialized = wire(payload)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT value FROM binding').fetchone()[0] != self.binding:
                raise ValueError('inbox binding changed')
            head = con.execute('SELECT r.* FROM heads h JOIN revisions r ON r.id=h.revision WHERE h.source=?', (source,)).fetchone()
            revision = head['id'] if head is not None and snapshot is not None else None
            if snapshot is not None:
                checksum = sha(snapshot)
                if head is None or (head['sha256'], head['size']) != (checksum, len(snapshot)):
                    append = head is not None and len(snapshot) >= head['size'] and sha(snapshot[:head['size']]) == head['sha256']
                    offset = head['size'] if append else 0
                    revision = con.execute(
                        'INSERT INTO revisions(source,parent,supersedes,offset,size,sha256,delta,recorded_ns) VALUES(?,?,?,?,?,?,?,?)',
                        (source, head['id'] if append else None, head['id'] if head else None,
                         offset, len(snapshot), checksum, snapshot[offset:], time.time_ns())).lastrowid
                    con.execute('INSERT INTO heads VALUES(?,?) ON CONFLICT(source) DO UPDATE SET revision=excluded.revision', (source, revision))
            event_key = sha(wire([source, revision, payload, error]).encode())
            con.execute('INSERT OR IGNORE INTO observations(event_key,source,revision,payload,error,recorded_ns) VALUES(?,?,?,?,?,?)',
                        (event_key, source, revision, serialized, error, time.time_ns()))
            row = con.execute('SELECT * FROM observations WHERE event_key=?', (event_key,)).fetchone()
            if _fault:
                _fault('before_commit')
        if _fault:
            _fault('after_commit')
        return {'observation_id': row['id'], 'event_key': event_key, 'revision': revision,
                'capture_complete': snapshot is not None, 'error': error}

    def restore(self, revision):
        with self.connect() as con:
            chunks = []
            seen = set()
            current = revision
            while current is not None:
                if current in seen:
                    raise ValueError('cyclic inbox revision chain')
                seen.add(current)
                row = con.execute('SELECT * FROM revisions WHERE id=?', (current,)).fetchone()
                if row is None:
                    raise ValueError('missing inbox revision dependency')
                chunks.append(row)
                current = row['parent']
            content = b''
            source = chunks[0]['source'] if chunks else None
            for row in reversed(chunks):
                if row['source'] != source or len(content) != row['offset']:
                    raise ValueError('invalid inbox revision dependency')
                content += row['delta']
                if len(content) != row['size'] or sha(content) != row['sha256']:
                    raise ValueError('altered inbox source bytes')
            if not chunks:
                raise ValueError('a preserved revision is required')
            return content

    def observations(self, after=0, limit=32):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError('finite observation range required')
        with self.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM observations WHERE id>? ORDER BY id LIMIT ?', (after, limit))]
