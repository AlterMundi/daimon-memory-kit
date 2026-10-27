"""Bound manual pre-write recovery points without expiring unfinished operations.

Explicit begin/complete/restore calls; no scheduler, canonical writes or models.
Uses the same verified snapshot, retention and restoration implementation as the
worker, with a separate owner-bound manual-operation journal.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re

from codex_coordinator import checkpoint
from snapshot_store import Store, policy


class Database:
    def __init__(self, path):
        self.DB_PATH = path

    def connect(self):
        import sqlite3
        return sqlite3.connect(self.DB_PATH.as_uri()+'?mode=ro', uri=True)


class ManualStore(Store):
    def terminal(self, name):
        # Only an explicit completion receipt releases this operation's backup.
        return any(v['name']==name and v['state']=='complete'
                   for v in self.operations['entries'].values())


def operate(configuration, command, *, operation=None, reason=None, destination=None, critical=False):
    required={'database','snapshots'}
    if not isinstance(configuration,dict) or set(configuration)!=required:
        raise ValueError('manual backup database and snapshots policy required')
    database=Path(configuration['database'])
    if not database.is_absolute() or not database.is_file():
        raise ValueError('existing absolute database required')
    bound=os.environ.get('HMK_DB_PATH')
    if bound and Path(bound).resolve()!=database.resolve():
        raise ValueError('manual backup database differs from receiving binding')
    p=policy(configuration['snapshots'])
    if p.get('retention_scope')!='database':
        raise ValueError('manual checkpoints require database-wide retention')
    root=Path(p['directory']);root.mkdir(mode=0o700,parents=True,exist_ok=True)
    state=root/'control';state.mkdir(mode=0o700,exist_ok=True)
    if state.is_symlink():raise ValueError('manual control state must not be a symlink')
    with open(state/'.lock','a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        store=ManualStore(Database(database.resolve()),state,p,
                          {'schema':'dmk.manual-backups/v1','database':str(database.resolve())})
        store._initialize()  # Explicit manual control also preserves legacy pending operations.
        path=state/'operations.json'
        if store.manifest['entries'] and not path.exists():
            raise ValueError('manual operations journal lost; preserve checkpoints')
        journal=json.loads(path.read_text()) if path.exists() else {
            'schema':'dmk.manual-operations/v1','next_sequence':1,'entries':{}}
        if journal.get('schema')!='dmk.manual-operations/v1':
            raise ValueError('unsupported manual-operation journal')
        store.operations=journal
        if command=='maintain':return store.maintain()
        if not isinstance(operation,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',operation):
            raise ValueError('stable operation identifier required')
        entries=journal['entries']
        if command=='begin':
            if not isinstance(reason,str) or not reason.strip():
                raise ValueError('pre-write checkpoint reason required')
            if operation not in entries:
                seq=journal['next_sequence'];journal['next_sequence']+=1
                if f'batch-{seq}-before.sqlite' in store.manifest['entries']:
                    raise ValueError('manual sequence overlaps retained history')
                entries[operation]={'name':f'batch-{seq}-before.sqlite','state':'pending','reason':reason}
                if 'routine_backup' in p:
                    entries[operation]['protection']='critical' if critical else 'periodic'
                checkpoint(path,journal)
            entry=entries[operation]
            if entry['state']!='pending' or entry['reason']!=reason:
                raise ValueError('operation already completed or reason changed; do not reuse its backup for a new write')
            if entry.get('protection')=='periodic':
                if critical:raise ValueError('ordinary operation cannot become critical after it began')
                from periodic_backups import Baselines
                return dict(operation=operation,state='pending',snapshot=None,sha256=None,
                    recovery_scope='periodic_database',backup=Baselines(database,p).status())
            if entry.get('protection')=='critical' and not critical:
                raise ValueError('critical operation must retain --critical on replay')
            saved=store.ensure(entry['name'],critical=True)
            return {'operation':operation,'state':'pending','snapshot':str(saved),
                    'sha256':store.manifest['entries'][entry['name']]['sha256']}
        if operation not in entries:raise ValueError('unknown manual operation')
        entry=entries[operation]
        if command=='restore' and entry.get('protection')=='periodic':
            raise ValueError('ordinary writes have no per-operation restore point; use a periodic baseline or logical correction')
        if command=='complete':
            if not isinstance(reason,str) or not reason.strip():
                raise ValueError('verified completion or cancellation reason required')
            if entry['state']=='pending':
                snapshot=store.manifest['entries'].get(entry['name'])
                if entry.get('protection')!='periodic' and (not snapshot or snapshot['state']!='ready'):
                    raise ValueError('pending snapshot creation must be recovered before completion')
                if entry.get('protection')!='periodic':store._check(snapshot)
                entry.update(state='complete',completion_reason=reason)
                checkpoint(path,journal)
            if entry.get('protection')=='periodic':
                return {'operation':operation,'state':'complete','recovery_scope':'periodic_database'}
            return {'operation':operation,'state':'complete','retention':store.maintain()}
        if command=='restore':
            if destination is None:raise ValueError('new restoration destination required')
            return store.restore(entry['name'],destination)
        raise ValueError('unsupported manual checkpoint operation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['begin','complete','maintain','restore'])
    p.add_argument('--profile',type=Path,default=Path.home()/'.config/daimon-memory-kit/backup.json')
    p.add_argument('--operation');p.add_argument('--reason');p.add_argument('--destination',type=Path)
    p.add_argument('--critical',action='store_true',help='Require a dedicated pre-write snapshot for consequential maintenance')
    a=p.parse_args()
    print(json.dumps(operate(json.loads(a.profile.read_text()),a.command,
                            operation=a.operation,reason=a.reason,destination=a.destination,critical=a.critical)))


if __name__=='__main__':main()
