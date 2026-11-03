#!/usr/bin/env python3
"""Explicitly rebind a migrated forward cursor after checking retained bytes.

No source discovery, cursor advancement, intake, policy change or model calls.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from capture_inbox import Inbox, sha, wire
from forward_capture import guard


def rebind(binding, payload, *, reason, _fault=None):
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ValueError('bounded explicit reason required')
    if binding.get('schema') != 'hmk.codex-hook-binding/v2':
        raise ValueError('scoped binding required')
    sid = payload.get('session_id')
    if not isinstance(sid, str) or not sid or payload.get('cwd') not in binding['allowed_cwds']:
        raise ValueError('selected source required')
    root = Path(binding['source_root']).resolve(strict=True)
    path = Path(payload['transcript_path']).absolute()
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError('safe source path required')
    path = path.resolve(strict=True)
    inbox = Inbox(binding['inbox'], binding)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('regular source required')
        with inbox.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            selected = json.loads(con.execute('SELECT value FROM forward_policy').fetchone()[0])
            if selected['binding_sha256'] != sha(inbox.binding.encode()):
                raise ValueError('forward policy binding differs')
            row = con.execute('SELECT value FROM forward_cursors WHERE source=?', (sid,)).fetchone()
            if not row:
                raise ValueError('existing cursor required; baseline-only migration needs separate evidence')
            original = row[0]; cursor = json.loads(original)
            if cursor['path'] != str(path) or before.st_size < cursor['offset']:
                raise ValueError('source path or length differs')
            header = os.pread(fd, binding['max_source_bytes'] + 1, 0).split(b'\n', 1)[0] + b'\n'
            if len(header) > binding['max_source_bytes'] or sha(header) != cursor['header_sha256'] or json.loads(header)['payload']['id'] != sid:
                raise ValueError('source header differs')
            if guard(fd, cursor['offset']) != cursor['guard']:
                raise ValueError('source boundary differs')
            checked = 0; ranges = 0; proof = hashlib.sha256()
            legacy = con.execute('SELECT r.* FROM heads h JOIN revisions r ON r.id=h.revision WHERE h.source=?', (sid,)).fetchone()
            if legacy:
                prior = inbox.restore(legacy['id'])
                if len(prior) > cursor['offset'] or os.pread(fd, len(prior), 0) != prior:
                    raise ValueError('retained legacy prefix differs')
                checked += len(prior)
                proof.update(wire(['legacy', legacy['id'], sha(prior)]).encode())
            for r in con.execute('SELECT * FROM forward_ranges WHERE source=? ORDER BY revision', (sid,)):
                start, end = r['file_start'], r['file_end']
                if not 0 <= start < end <= cursor['offset']:
                    raise ValueError('invalid retained range')
                restored = inbox.restore(r['revision'])
                delta = restored[-(end-start):]
                if len(delta) != end-start or sha(delta) != r['delta_sha256'] or os.pread(fd, end-start, start) != delta:
                    raise ValueError('retained source range differs')
                proof.update(wire([r['revision'], start, end, r['delta_sha256']]).encode())
                checked += end-start; ranges += 1
            if _fault:
                _fault()
            after = os.fstat(fd); live = path.stat()
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or (live.st_dev, live.st_ino) != (before.st_dev, before.st_ino):
                raise ValueError('source changed during verification')
            con.execute('CREATE TABLE IF NOT EXISTS forward_rebindings(source TEXT PRIMARY KEY, value TEXT NOT NULL)')
            old_identity = [cursor['device'], cursor['inode']]
            new_identity = [before.st_dev, before.st_ino]
            previous = con.execute('SELECT value FROM forward_rebindings WHERE source=?', (sid,)).fetchone()
            if old_identity == new_identity:
                return dict(rebound=False, source_offset=cursor['offset'], checked_bytes=checked, checked_ranges=ranges)
            receipt = dict(schema='dmk.forward-rebinding/v1', source=sid, reason=reason.strip(),
                           at_ns=time.time_ns(), previous_cursor=cursor, new_identity=new_identity,
                           verified_bytes=checked, verified_ranges=ranges, ranges_sha256=proof.hexdigest(),
                           earlier_rebindings=0 if previous is None else json.loads(previous[0])['earlier_rebindings']+1,
                           previous_receipt_sha256=None if previous is None else sha(previous[0].encode()))
            # One bounded receipt per source, preserving the immediate prior cursor.
            # Native originals, ranges and all source offsets remain untouched.
            cursor.update(device=before.st_dev, inode=before.st_ino)
            con.execute('UPDATE forward_cursors SET value=? WHERE source=?', (wire(cursor), sid))
            con.execute('INSERT INTO forward_rebindings VALUES(?,?) ON CONFLICT(source) DO UPDATE SET value=excluded.value', (sid, wire(receipt)))
            return dict(rebound=True, source_offset=cursor['offset'], checked_bytes=checked, checked_ranges=ranges,
                        preservation_scope='retained ranges, header and cursor boundary; unavailable baseline prefix not attested')
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binding', type=Path, required=True)
    p.add_argument('--payload', type=Path, required=True)
    p.add_argument('--reason', required=True)
    a = p.parse_args()
    print(json.dumps(rebind(json.loads(a.binding.read_text()), json.loads(a.payload.read_text()), reason=a.reason)))


if __name__ == '__main__':
    main()
