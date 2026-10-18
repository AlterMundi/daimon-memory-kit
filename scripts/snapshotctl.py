"""Explicit checkpoint migration, retention and restore; never dispatch models."""
import argparse
import fcntl
import json
from pathlib import Path
from contextlib import ExitStack
from memory_runtime import profile, load_memory
from capture_inbox import Inbox
from capturectl import digest
from snapshot_store import Store


def operate(value, command, *, name=None, destination=None):
    if 'snapshots' not in value: raise ValueError('explicit snapshot policy required')
    memory=load_memory(value)
    binding=json.loads(Path(value['binding']).read_text())
    inbox=Inbox(value['inbox'],binding)
    with ExitStack() as stack:
        for suffix in ('.worker.lock','.producer.lock'):
            lock=stack.enter_context(open(str(inbox.path)+suffix,'a+b'))
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with inbox.connect() as con:
            row=con.execute('select value from producer_owner').fetchone()
        owner=json.loads(row[0])
        if (owner.get('database')!=str(Path(memory.DB_PATH).resolve()) or
            owner.get('state_dir')!=str(Path(value['state_dir']).resolve()) or
            owner.get('context')!=value['context'] or owner.get('capture_binding')!=digest(binding)):
            raise ValueError('checkpoint operation differs from producer binding')
        store=Store(memory,value['state_dir'],value['snapshots'],owner)
        if command=='migrate': return store.migrate()
        if command=='maintain': return store.maintain()
        if command=='restore': return store.restore(name,destination)
        raise ValueError('unsupported checkpoint operation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['migrate','maintain','restore'])
    p.add_argument('--profile',required=True,type=Path)
    p.add_argument('--name');p.add_argument('--destination',type=Path)
    args=p.parse_args()
    if args.command=='restore' and not (args.name and args.destination): p.error('restore needs name and a new destination')
    result=operate(profile(args.profile),args.command,name=args.name,destination=args.destination)
    print(json.dumps(result))


if __name__=='__main__': main()
