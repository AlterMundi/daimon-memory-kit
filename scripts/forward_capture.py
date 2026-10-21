"""Explicit forward-only capture: baseline existing files, retain new turn segments.

No source discovery occurs on a hook. Activation inventories file metadata once;
source bytes are read only when a selected hook supplies its session and path.
The existing inbox/producer contract remains unchanged, with additive provenance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

from capture_inbox import Inbox, sha, wire
from sqlite_snapshot import verified_snapshot

SCHEMA = 'dmk.forward-capture/v1'
GUARD_BYTES = 256


def policy(inbox_path):
    if not Path(inbox_path).exists():
        return None
    # Hooks may be killed during a write. SQLite needs write access to roll back
    # a hot journal before even this SELECT; read-only mode strands every later
    # hook behind SQLITE_READONLY_ROLLBACK. Do not create a missing inbox here.
    with sqlite3.connect(Path(inbox_path).resolve().as_uri()+'?mode=rw', uri=True) as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='forward_policy'").fetchone():
            return None
        row = con.execute('SELECT value FROM forward_policy').fetchone()
        return json.loads(row[0]) if row else None


def guard(fd, offset):
    return sha(os.pread(fd, min(GUARD_BYTES, offset), max(0, offset-GUARD_BYTES)))


def activate(binding, backup, *, read_budget_bytes=4*1024*1024):
    """Explicitly inventory current EOFs; do not ingest existing conversations."""
    if binding.get('schema') != 'hmk.codex-hook-binding/v2':
        raise ValueError('scoped binding required')
    if type(read_budget_bytes) is not int or read_budget_bytes < 1:
        raise ValueError('positive capture read budget required')
    if policy(binding['inbox']):
        raise ValueError('forward policy already exists; preserve its cursors')
    inbox = Inbox(binding['inbox'], binding)
    verified_snapshot(inbox.path, backup)
    started = time.time_ns()
    root = Path(binding['source_root']).resolve(strict=True)
    baselines = []
    for path in root.rglob('*.jsonl'):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('source inventory contains an unsafe path')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('regular source files required')
            size = info.st_size
            aligned = not size or os.pread(fd, 1, size-1) == b'\n'
            baselines.append((str(path.resolve()), info.st_dev, info.st_ino, size,
                              guard(fd,size), int(aligned)))
        finally:
            os.close(fd)
    value = dict(schema=SCHEMA, enabled=True, activated_ns=started,
                 binding_sha256=sha(inbox.binding.encode()), baseline_files=len(baselines),
                 read_budget_bytes=min(read_budget_bytes,binding['max_source_bytes']))
    with inbox.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('CREATE TABLE forward_policy(value TEXT NOT NULL)')
        con.execute('CREATE TABLE forward_baselines(path TEXT PRIMARY KEY, device INTEGER, inode INTEGER, offset INTEGER, guard TEXT, aligned INTEGER)')
        con.execute('CREATE TABLE forward_cursors(source TEXT PRIMARY KEY, value TEXT NOT NULL)')
        con.execute('CREATE TABLE forward_ranges(revision INTEGER PRIMARY KEY REFERENCES revisions(id), source TEXT NOT NULL, segment TEXT NOT NULL, file_start INTEGER NOT NULL, file_end INTEGER NOT NULL, delta_sha256 TEXT NOT NULL)')
        con.executemany('INSERT INTO forward_baselines VALUES(?,?,?,?,?,?)', baselines)
        con.execute('INSERT INTO forward_policy VALUES(?)', (wire(value),))
    return value


def set_enabled(binding, enabled):
    """Pause/resume this policy without erasing cursors or falling back to v2."""
    inbox = Inbox(binding['inbox'], binding)
    with inbox.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        value = json.loads(con.execute('SELECT value FROM forward_policy').fetchone()[0])
        value['enabled'] = bool(enabled)
        con.execute('UPDATE forward_policy SET value=?', (wire(value),))
    return value


def deferred(reason='capture_deferred'):
    return dict(capture_complete=False, error=reason, scope_verified=False)


def capture(binding, payload, source, path, header, before, *, _fault=None):
    """Read only a bounded unread suffix; commit ranges and cursor atomically."""
    inbox = Inbox(binding['inbox'], binding)
    sid = payload['session_id']
    fd = source.fileno()
    with inbox.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        selected = json.loads(con.execute('SELECT value FROM forward_policy').fetchone()[0])
        if selected['schema'] != SCHEMA or selected['binding_sha256'] != sha(inbox.binding.encode()):
            raise ValueError('forward policy binding differs')
        if not selected['enabled']:
            return deferred()
        row = con.execute('SELECT value FROM forward_cursors WHERE source=?', (sid,)).fetchone()
        if row:
            cursor = json.loads(row[0])
        else:
            baseline = con.execute('SELECT * FROM forward_baselines WHERE path=?', (str(path),)).fetchone()
            # Previously admitted legacy streams retain their exact pending prefix.
            head = con.execute('SELECT r.* FROM heads h JOIN revisions r ON r.id=h.revision WHERE h.source=?', (sid,)).fetchone()
            cursor = dict(path=str(path), device=before.st_dev, inode=before.st_ino,
                          header_sha256=sha(header), segment=None, turn_id=None,
                          segment_start=None, awaiting_turn=True, aligned=True, admitted=None)
            if head:
                prior = inbox.restore(head['id'])
                if os.pread(fd,len(prior),0) != prior:
                    return deferred('source_changed_during_capture')
                cursor.update(offset=len(prior), segment=sid, segment_start=0,
                              awaiting_turn=False, admitted=True, guard=guard(fd,len(prior)))
            elif baseline:
                cursor.update(device=baseline['device'], inode=baseline['inode'],
                              offset=baseline['offset'], guard=baseline['guard'],
                              aligned=bool(baseline['aligned']))
            else:
                from codex_hook_capture import timestamp
                try:
                    created = timestamp(json.loads(header)['payload']['timestamp']).timestamp()
                except (KeyError, ValueError, TypeError):
                    return deferred('session_scope_unverified')
                if created < selected['activated_ns']/1e9:
                    # An old file moved in after activation is not a new session.
                    return deferred('session_scope_unverified')
                cursor.update(offset=len(header), guard=guard(fd,len(header)))
        if (cursor['path'] != str(path) or cursor['device'] != before.st_dev
                or cursor['inode'] != before.st_ino or before.st_size < cursor['offset']
                or cursor['header_sha256'] != sha(header)
                or cursor['guard'] != guard(fd,cursor['offset'])):
            return deferred('source_changed_during_capture')
        start = cursor['offset']
        limit = selected['read_budget_bytes']
        data = os.pread(fd, min(limit, before.st_size-start), start)
        # Never consume a partial JSONL record. A later invocation resumes it.
        complete = data.rfind(b'\n')+1
        data = data[:complete]
        if not data and start < before.st_size:
            return deferred('source_exceeds_capture_limit' if before.st_size-start >= limit else 'source_changed_during_capture')
        end = start+len(data)
        after = os.fstat(fd)
        if (after.st_size < before.st_size or guard(fd,start) != cursor['guard']
                or os.pread(fd,len(data),start) != data):
            return deferred('source_changed_during_capture')
        offset = start
        groups = []
        for line in data.splitlines(keepends=True):
            before_line = dict(cursor)
            line_start = offset
            offset += len(line)
            if not cursor['aligned']:
                cursor['aligned'] = True
                continue
            try:
                item = json.loads(line)
                event = item.get('payload',{})
                if not isinstance(event,dict):
                    return deferred('source_header_incomplete')
            except (ValueError, AttributeError):
                return deferred('source_header_incomplete')
            if item.get('type') == 'event_msg' and event.get('type') == 'task_started':
                turn_id = event.get('turn_id')
                if not isinstance(turn_id,str) or not turn_id:
                    return deferred('session_scope_unverified')
                cursor.update(awaiting_turn=False, segment=f'{sid}:forward:{line_start}',
                              turn_id=turn_id, segment_start=line_start, admitted=None)
            if cursor['awaiting_turn']:
                continue
            if not groups or groups[-1]['segment'] != cursor['segment']:
                groups.append(dict(segment=cursor['segment'],start=line_start,end=offset,
                                   turn_id=cursor['turn_id'],admitted=cursor['admitted'],
                                   cursor_before=before_line,parts=[line]))
            else:
                groups[-1]['parts'].append(line)
                groups[-1]['end'] = offset
            if item.get('type') == 'turn_context':
                if event.get('turn_id') != cursor['turn_id'] and cursor['turn_id'] is not None:
                    return deferred('session_scope_unverified')
                admitted = event.get('cwd') in binding['allowed_cwds']
                if cursor['admitted'] is not None and admitted != cursor['admitted']:
                    return deferred('session_scope_unverified')
                cursor['admitted'] = admitted
                groups[-1]['admitted'] = admitted
        # A chunk may end before a new turn's context arrives. Commit earlier
        # verified groups, but keep that turn's start for the next bounded read.
        for index, group in enumerate(groups):
            if group['admitted'] is None:
                end = group['start']
                cursor = group['cursor_before']
                groups = groups[:index]
                break
        revisions = []
        for group in groups:
            if not group['admitted']:
                continue
            segment = group['segment']; delta = b''.join(group['parts'])
            head = con.execute('SELECT r.* FROM heads h JOIN revisions r ON r.id=h.revision WHERE h.source=?', (segment,)).fetchone()
            prior = inbox.restore(head['id']) if head else header
            snapshot = prior+delta
            stored_delta = delta if head else snapshot
            revision = con.execute('INSERT INTO revisions(source,parent,supersedes,offset,size,sha256,delta,recorded_ns) VALUES(?,?,?,?,?,?,?,?)',
                (segment,head['id'] if head else None,head['id'] if head else None,
                 len(prior) if head else 0,len(snapshot),sha(snapshot),stored_delta,time.time_ns())).lastrowid
            con.execute('INSERT INTO heads VALUES(?,?) ON CONFLICT(source) DO UPDATE SET revision=excluded.revision',(segment,revision))
            provenance = dict(schema=SCHEMA, session_id=sid, turn_id=group['turn_id'],
                              file_start=group['start'],file_end=group['end'],
                              header_bytes=len(header),delta_sha256=sha(delta))
            observation = dict(hook_event_name=payload['hook_event_name'],capture_range=provenance)
            serialized = wire(observation); key = sha(wire([segment,revision,observation,None]).encode())
            con.execute('INSERT INTO observations(event_key,source,revision,payload,error,recorded_ns) VALUES(?,?,?,?,NULL,?)',
                        (key,segment,revision,serialized,time.time_ns()))
            con.execute('INSERT INTO forward_ranges VALUES(?,?,?,?,?,?)',
                        (revision,sid,segment,group['start'],group['end'],sha(delta)))
            revisions.append(revision)
        cursor.update(offset=end,guard=guard(fd,end))
        con.execute('INSERT INTO forward_cursors VALUES(?,?) ON CONFLICT(source) DO UPDATE SET value=excluded.value', (sid,wire(cursor)))
        if _fault:
            _fault('before_commit')
    if _fault:
        _fault('after_commit')
    return dict(capture_complete=end==before.st_size,error=None if end==before.st_size else 'capture_deferred',
                revisions=revisions,source_offset=end,remaining_bytes=before.st_size-end,
                awaiting_new_turn=cursor['awaiting_turn'],scope=SCHEMA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['activate','status','pause','resume','drain'])
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--read-budget-bytes',type=int,default=4*1024*1024)
    parser.add_argument('--payload',type=Path)
    parser.add_argument('--max-steps',type=int,default=32)
    args = parser.parse_args(); binding = json.loads(args.binding.read_text())
    if args.command == 'activate':
        if args.backup is None:
            parser.error('--backup is required for activation')
        result = activate(binding,args.backup,read_budget_bytes=args.read_budget_bytes)
    elif args.command == 'drain':
        if args.payload is None or args.max_steps < 1:
            parser.error('--payload and a positive --max-steps are required')
        from codex_hook_capture import capture as hook_capture
        payload = json.loads(args.payload.read_text()); previous = None
        for step in range(args.max_steps):
            result = hook_capture(binding,payload)
            if result['capture_complete'] or result.get('source_offset') == previous:
                break
            previous = result.get('source_offset')
        result = dict(result,steps=step+1,model_calls=0)
    elif args.command == 'status':
        result = policy(binding['inbox'])
    else:
        result = set_enabled(binding,args.command=='resume')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
