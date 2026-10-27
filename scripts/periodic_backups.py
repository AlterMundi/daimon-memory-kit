"""Shared periodic SQLite baselines, independent of ordinary operation count.

No scheduler, model, delta-log guarantee or live-database restore. Ordinary
writes never call refresh: the existing finite worker or an explicit operator
does. Missing/failed backup protection is reported separately from write success.
"""
from contextlib import closing
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid

from codex_coordinator import checkpoint, sync_directory
from sqlite_snapshot import verified_snapshot

NAME = re.compile(r'baseline-[0-9]+-[a-f0-9]{12}\.sqlite\Z')


class BackupCapacityError(OSError):
    pass


def configuration(value):
    if (not isinstance(value,dict) or set(value) != {'directory','subject','interval_seconds'}
            or not isinstance(value['subject'],str) or not value['subject'].strip()
            or type(value['interval_seconds']) is not int or value['interval_seconds'] < 1):
        raise ValueError('explicit periodic backup directory, subject and positive interval required')
    root = Path(value['directory'])
    if not root.is_absolute() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('periodic backup directory must be absolute and without symlinks')
    return value


class Baselines:
    def __init__(self, database, policy):
        self.policy = policy
        self.config = configuration(policy['routine_backup'])
        self.database = Path(database).resolve()
        if not self.database.is_file():
            raise ValueError('existing canonical database required')
        self.root = Path(self.config['directory'])
        if self.root == Path(policy['directory']):
            raise ValueError('periodic baselines and operation checkpoints need distinct directories')
        self.owner = dict(database=str(self.database),subject=self.config['subject'])
        self.manifest_path = self.root/'manifest.json'

    def read(self):
        if not self.manifest_path.exists():
            if list(self.root.glob('*.sqlite')) or list(self.root.glob('.*.partial-*')):
                raise ValueError('periodic manifest lost; preserve unregistered recovery files')
            return dict(schema='dmk.periodic-backups/v1',owner=self.owner,entries={})
        value = json.loads(self.manifest_path.read_text())
        if value.get('schema') != 'dmk.periodic-backups/v1' or value.get('owner') != self.owner:
            raise ValueError('periodic backup owner differs')
        for name, entry in value['entries'].items():
            if (not NAME.fullmatch(name) or entry['path'] != str(self.root/name)
                    or entry['state'] not in {'ready','retiring','retired','quarantined'}):
                raise ValueError('periodic backup destination changed')
        return value

    def fingerprint(self):
        # A cheap dirty hint, not a cryptographic audit. WAL/checkpoint changes
        # may cause an extra daily backup; they may not skip a known mutation.
        values=[]
        for p in (self.database,Path(str(self.database)+'-wal')):
            if p.exists():
                s=p.stat(); values.append([str(p),s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns])
            else:
                values.append([str(p),None])
        return values

    def status(self):
        value=self.read()
        ready=[e for e in value['entries'].values() if e['state']=='ready']
        latest=max(ready,key=lambda e:e['created_ns']) if ready else None
        result=dict(state='unobserved',last_verified_ns=None,recovery_scope='periodic_database',
                    interval_seconds=self.config['interval_seconds'],verified_baselines=len(ready),
                    quarantined_baselines=sum(e['state']=='quarantined' for e in value['entries'].values()))
        for entry in ready:
            p=Path(entry['path'])
            if (not p.is_file() or p.is_symlink() or p.stat().st_size != entry['bytes']
                    or p.stat().st_mtime_ns != entry['file_mtime_ns']
                    or p.stat().st_ctime_ns != entry['file_ctime_ns']):
                return dict(result,state='failed',reason_code='baseline_changed')
        if latest:
            age=max(0,(time.time_ns()-latest['created_ns'])//1_000_000_000)
            unchanged=latest.get('source_fingerprint') == self.fingerprint()
            result.update(state='current' if unchanged or age < self.config['interval_seconds'] else 'due',
                          last_verified_ns=latest['created_ns'],age_seconds=age,
                          snapshot=latest['path'],sha256=latest['sha256'])
        if value.get('failure'):
            result.update(state='failed',reason_code=value['failure']['reason_code'],
                          episode=value['failure']['episode'])
        return result

    def _check(self, entry):
        from snapshot_store import Store
        if Path(entry['path']).is_symlink():raise ValueError('periodic baseline destination changed')
        return Store._check(self,entry)

    def refresh(self, *, recover=False):
        from snapshot_store import verified
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        with (self.root/'.lock').open('a+b') as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                return dict(self.status(),state='pending',reason_code='backup_in_progress')
            value=self.read()
            known=set(value['entries'])
            if value.get('attempt'):known.add(value['attempt']['name'])
            if any(p.name not in known for p in self.root.glob('*.sqlite')):
                raise ValueError('unregistered periodic recovery file; inspect before maintenance')
            current=self.status()
            if current.get('reason_code')=='baseline_changed':
                if not recover:return dict(current,created=False)
                for e in value['entries'].values():
                    if e['state']!='ready':continue
                    p=Path(e['path'])
                    if (not p.is_file() or p.is_symlink() or p.stat().st_size!=e['bytes']
                            or p.stat().st_mtime_ns!=e['file_mtime_ns'] or p.stat().st_ctime_ns!=e['file_ctime_ns']):
                        e['state']='quarantined'
                checkpoint(self.manifest_path,value)
            if current['state']=='current' and not value.get('attempt'):
                # An unchanged database needs an audit, not another full copy.
                latest=max((e for e in value['entries'].values() if e['state']=='ready'),key=lambda e:e['created_ns'])
                if time.time_ns()-latest.get('audited_ns',latest['created_ns']) >= self.config['interval_seconds']*1_000_000_000:
                    try:
                        self._check(latest)
                        latest['audited_ns']=time.time_ns();checkpoint(self.manifest_path,value)
                    except (OSError,ValueError) as error:
                        value['failure']=dict(episode=uuid.uuid4().hex,reason_code='baseline_changed',error_type=type(error).__name__)
                        checkpoint(self.manifest_path,value)
                        return dict(self.status(),created=False)
                return dict(current,created=False)
            if value.get('attempt') and not recover:
                return dict(current,state='failed',reason_code='retained_backup_attempt',created=False)
            episode=value.get('failure',{}).get('episode') or uuid.uuid4().hex
            try:
                ready=[e for e in value['entries'].values() if e['state']=='ready']
                # No paid calls or canonical mutation. Reserve enough for one
                # complete new baseline and keep both old points until verified.
                with closing(sqlite3.connect(self.database.as_uri()+'?mode=ro',uri=True)) as c:
                    size=c.execute('pragma page_count').fetchone()[0]*c.execute('pragma page_size').fetchone()[0]
                partials=list(self.root.glob('.*.partial-*'))
                existing = self.root/value['attempt']['name'] if value.get('attempt') else None
                published = bool(existing and existing.exists())
                if partials and not (recover and published and all(p.samefile(existing) for p in partials)):
                    raise RuntimeError('retained partial needs explicit inspection')
                retained=[e for e in value['entries'].values() if e['state']!='retired']
                budget=max(self.policy['max_bytes'],(self.policy['keep_latest']+1)*max([size]+[e['bytes'] for e in retained]))
                registered=bool(published and existing.name in value['entries'])
                if sum(e['bytes'] for e in retained)+(0 if registered else size) > budget:
                    raise BackupCapacityError('backup byte budget exceeded')
                if len(retained)+(0 if registered else 1)>self.policy['max_count']:
                    raise BackupCapacityError('backup count budget exceeded')
                if shutil.disk_usage(self.root).free < (0 if published else size)+self.policy['min_free_bytes']:
                    raise BackupCapacityError('backup storage reserve unavailable')
                if not value.get('attempt'):
                    name=f'baseline-{time.time_ns()}-{uuid.uuid4().hex[:12]}.sqlite'
                    value['attempt']=dict(name=name,started_ns=time.time_ns(),source_fingerprint=self.fingerprint())
                    checkpoint(self.manifest_path,value)
                attempt=value['attempt'];name=attempt['name'];target=self.root/name
                if not target.exists():
                    verified_snapshot(self.database,target,timeout=self.policy.get('timeout_seconds',300))
                info=verified(target)
                for partial in partials:
                    if partial.samefile(target):partial.unlink()
                st=target.stat()
                value['entries'][name]=dict(info,path=str(target),state='ready',
                    created_ns=attempt['started_ns'],file_mtime_ns=st.st_mtime_ns,file_ctime_ns=st.st_ctime_ns,
                    source_fingerprint=(attempt['source_fingerprint']
                        if attempt['source_fingerprint']==self.fingerprint() else None))
                value.pop('failure',None)
                checkpoint(self.manifest_path,value)
                # Only periodic baselines rotate here. Operation-bound legacy
                # checkpoints/pins and their unfinished journals are untouched.
                names=sorted((n for n,e in value['entries'].items() if e['state'] in {'ready','retiring'}),
                    key=lambda n:value['entries'][n]['created_ns'],reverse=True)
                for old in names[self.policy['keep_latest']:]:
                    entry=value['entries'][old];path=Path(entry['path'])
                    if path.exists():self._check(entry)
                    elif entry['state']!='retiring':raise ValueError('periodic baseline missing')
                    entry['state']='retiring';checkpoint(self.manifest_path,value)
                    if path.exists():path.unlink();sync_directory(self.root)
                    entry['state']='retired';checkpoint(self.manifest_path,value)
                value.pop('attempt',None);checkpoint(self.manifest_path,value)
                return dict(self.status(),created=True)
            except (OSError,ValueError,RuntimeError,sqlite3.Error) as error:
                value['failure']=dict(episode=episode,reason_code=('backup_capacity' if isinstance(error,BackupCapacityError)
                    else 'backup_verification_or_interruption'),error_type=type(error).__name__)
                checkpoint(self.manifest_path,value)
                return dict(self.status(),state='failed',created=False)

    def restore(self, name, destination):
        from snapshot_store import Store
        if not NAME.fullmatch(name):raise ValueError('exact baseline name required')
        if Path(destination).resolve().is_relative_to(self.root.resolve()):
            raise ValueError('restore outside the managed baseline directory')
        self.manifest=self.read()
        return Store.restore(self,name,destination)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['status','refresh','restore'])
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--recover',action='store_true')
    parser.add_argument('--name');parser.add_argument('--destination',type=Path)
    args=parser.parse_args();v=json.loads(args.profile.read_text())
    bound=os.environ.get('HMK_DB_PATH')
    if bound and Path(bound).resolve()!=Path(v['database']).resolve():
        raise ValueError('receiving database binding differs')
    pool=Baselines(v['database'],v['snapshots'])
    if args.command=='status':result=pool.status()
    elif args.command=='refresh':result=pool.refresh(recover=args.recover)
    else:
        if not args.name or not args.destination:parser.error('restore requires name and new destination')
        result=pool.restore(args.name,args.destination)
    if args.command=='refresh' and 'inbox' in v:
        from capture_inbox import Inbox
        from memory_runtime import backup_notice
        binding=json.loads(Path(v['binding']).read_text())
        safe=backup_notice(v,Inbox(v['inbox'],binding),result)
        if 'alert_id' in safe:result['alert_id']=safe['alert_id']
    print(json.dumps(result))
    return 2 if result.get('state') in {'failed','unobserved'} else 0


if __name__=='__main__':raise SystemExit(main())
