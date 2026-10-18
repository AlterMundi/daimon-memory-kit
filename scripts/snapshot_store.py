"""Owner-bound pre-write checkpoints. Caller holds the producer lock.

Only registered, completed checkpoints can be retired. Database-wide retention
explicitly includes historical imports; legacy policies preserve the archive.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time

from capturectl import digest
from codex_coordinator import checkpoint, sync_directory
from sqlite_snapshot import verified_snapshot

NAME = re.compile(r'(batch|embedding|organization|embedding-organization)-([1-9][0-9]*)-before\.sqlite\Z')


class SnapshotCapacityError(RuntimeError):
    pass


def policy(value):
    required = {'directory', 'max_count', 'max_bytes', 'min_free_bytes', 'keep_latest', 'pins'}
    if not isinstance(value, dict) or set(value)-{'timeout_seconds', 'retention_scope'} != required:
        raise ValueError('explicit snapshot placement, limits and rollback pins required')
    if value.get('retention_scope', 'class') not in ('class', 'database'):
        raise ValueError('unsupported checkpoint retention scope')
    if 'timeout_seconds' in value and (type(value['timeout_seconds']) is not int or value['timeout_seconds']<1):
        raise ValueError('positive snapshot timeout required')
    root = Path(value['directory'])
    if not root.is_absolute() or any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError('snapshot storage must be an absolute non-symlink directory')
    for key in ('max_count', 'max_bytes', 'min_free_bytes', 'keep_latest'):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError('positive snapshot limits required')
    if value['keep_latest'] > value['max_count']:
        raise ValueError('retained checkpoints exceed count budget')
    if not isinstance(value['pins'], list) or any(not isinstance(n, str) or not NAME.fullmatch(n) for n in value['pins']):
        raise ValueError('rollback pins must be exact checkpoint names')
    return value


def verified(path):
    """Read-only standalone SQLite check and exact byte/schema identity."""
    path = Path(path)
    if not path.is_file() or any(Path(str(path.resolve())+s).exists() for s in ('-wal', '-journal')):
        raise ValueError('standalone snapshot required; journal companions preserved')
    before = path.stat()
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as con:
        if con.execute('pragma integrity_check').fetchall() != [('ok',)] or con.execute('pragma foreign_key_check').fetchall():
            raise ValueError('invalid recovery snapshot')
        schema = con.execute('select type,name,tbl_name,sql from sqlite_master order by type,name').fetchall()
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    after = path.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError('snapshot changed during verification')
    return dict(bytes=after.st_size,sha256=h.hexdigest(),schema_sha256=digest(schema))


class Store:
    def __init__(self, memory, state_dir, configuration, owner):
        self.memory, self.state = memory, Path(state_dir)
        self.policy = policy(configuration)
        self.root = Path(configuration['directory'])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.state/'snapshot-manifest.json'
        self.owner = dict(database=str(Path(memory.DB_PATH).resolve()),state_dir=str(self.state.resolve()),producer=digest(owner))
        if self.path.exists():
            self.manifest = json.loads(self.path.read_text())
            if self.manifest.get('schema')!='dmk.snapshot-store/v1' or self.manifest['owner']!=self.owner or self.manifest['directory']!=str(self.root):
                raise ValueError('snapshot owner or placement changed; explicit migration required')
        else:
            self.manifest = dict(schema='dmk.snapshot-store/v1',owner=self.owner,directory=str(self.root),entries={})
        marker=self.root/'owner.json'
        if marker.exists():
            if json.loads(marker.read_text())!=self.owner: raise ValueError('snapshot directory belongs to another owner')
        else:
            # Exclusive publication also protects simultaneous first adopters.
            fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:
                json.dump(self.owner,f);f.flush();os.fsync(f.fileno())
            sync_directory(self.root)
        self.producer = owner

    def save(self):
        checkpoint(self.path, self.manifest)

    def _check(self, entry):
        # Registration already verified integrity and schema. Exact unchanged
        # bytes preserve that proof; do not rescan all SQLite indexes on every
        # maintenance pass. Restore still verifies the newly materialized DB.
        path = Path(entry['path'])
        if not path.is_file() or any(Path(str(path.resolve())+s).exists() for s in ('-wal','-journal')):
            raise ValueError('standalone snapshot required; journal companions preserved')
        before = path.stat()
        if before.st_size != entry['bytes']:
            raise ValueError('recovery checkpoint content changed')
        h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):
                h.update(block)
        after = path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('snapshot changed during verification')
        if h.hexdigest() != entry['sha256']:
            raise ValueError('recovery checkpoint content changed')
        return {k:entry[k] for k in ('bytes','sha256','schema_sha256')}

    def terminal(self, name):
        kind, sequence = NAME.fullmatch(name).groups(); sequence = int(sequence)
        organization = kind in ('organization','embedding-organization')
        cursor = self.state/('organization-index.json' if organization else 'index.json')
        index = self.state/('embedding-organization-index.json' if organization else 'embedding-index.json')
        if not cursor.exists() or not index.exists(): return False
        for path, key in [(cursor,'after' if organization else 'sequence'), (index,'after')]:
            value = json.loads(path.read_text())
            if value.get('owner')!=self.producer or value.get(key,0)<sequence: return False
        with closing(self.memory.connect()) as con:
            if not con.execute("select 1 from sqlite_master where name='capture_events'").fetchone(): return False
            row = con.execute('select state from capture_events where stream_id=? and sequence=?',
                (('organization:' if organization else 'portable:')+digest(self.producer),sequence)).fetchone()
        return bool(row and row[0] in ('applied','omitted'))

    def maintain(self, reserve=0):
        """Reserve count/bytes before paid work. Unknown/protected entries block."""
        entries = self.manifest['entries']
        database_scope = self.policy.get('retention_scope') == 'database'
        states = ('ready','retiring','creating','archive') if database_scope else ('ready','retiring','creating')
        active = {n:e for n,e in entries.items() if e['state'] in states}
        keep = set(self.policy['pins'])
        if database_scope:
            # Sequence numbers belong to separate streams. Snapshot creation order
            # determines recent database recovery points, not cross-stream seqno.
            for e in active.values():
                if e['state'] in ('ready','archive') and 'created_ns' not in e:
                    e['created_ns'] = Path(e['path']).stat().st_mtime_ns
            names = [n for n,e in active.items() if e['state'] in ('ready','archive')]
            keep.update(sorted(names, key=lambda n:(active[n]['created_ns'],n), reverse=True)[:self.policy['keep_latest']])
        else:
            for kind in ('batch','embedding','organization','embedding-organization'):
                names = [n for n,e in active.items() if NAME.fullmatch(n)[1]==kind and e['state']=='ready']
                keep.update(sorted(names,key=lambda n:int(NAME.fullmatch(n)[2]),reverse=True)[:self.policy['keep_latest']])
        partials=[p for p in self.root.glob('.*.partial-*') if p.is_file()]
        partial_bytes=sum(p.stat().st_size for p in partials)
        free = shutil.disk_usage(self.root).free
        def excess():
            return (len(active)+len(partials)+(1 if reserve else 0)>self.policy['max_count'] or
                    sum(e.get('bytes',e.get('reserved_bytes',0)) for e in active.values())+reserve+partial_bytes>self.policy['max_bytes'] or
                    free-reserve<self.policy['min_free_bytes'])
        checked_recovery = False
        for n in sorted(active,key=lambda n:(active[n].get('created_ns',0),int(NAME.fullmatch(n)[2]))):
            e = active[n]
            if not database_scope and not excess() and e['state']!='retiring': continue
            if n in keep or e['state']=='creating' or not self.terminal(n): continue
            # A verified retained checkpoint is required before each retirement.
            if not keep: raise ValueError('no retained recovery checkpoint')
            if not checked_recovery:
                for retained in keep:
                    if retained not in entries or entries[retained]['state'] not in ('ready','archive'):
                        raise ValueError('rollback pin unavailable')
                    self._check(entries[retained])
                checked_recovery = True
            path = Path(e['path'])
            legacy = None
            if 'legacy_path' in e:
                legacy = Path(e['legacy_path'])
                if legacy != self.state/n or (os.path.lexists(legacy) and
                    (not legacy.is_symlink() or legacy.resolve()!=path)):
                    raise ValueError('archive compatibility path changed')
                if not os.path.lexists(legacy) and e['state']!='retiring':
                    raise ValueError('archive compatibility path lost')
            elif path != self.root/n:
                raise ValueError('managed checkpoint path changed')
            if path.is_symlink() or path != path.resolve():
                raise ValueError('checkpoint destination changed')
            if path.exists(): self._check(e)
            elif e['state']!='retiring': raise ValueError('recovery checkpoint lost')
            e['state']='retiring'; self.save()  # Interrupted deletion is resumable.
            if path.exists(): path.unlink(); sync_directory(path.parent)
            if legacy is not None and os.path.lexists(legacy):
                legacy.unlink(); sync_directory(legacy.parent)
            e['state']='retired'; self.save()
            active.pop(n)
            free = shutil.disk_usage(self.root).free
        if excess():
            raise SnapshotCapacityError('protected checkpoints or storage headroom prevent reservation')
        return dict(active_count=len(active),active_bytes=sum(e.get('bytes',e.get('reserved_bytes',0)) for e in active.values()),
                    archive_count=sum(e['state']=='archive' for e in entries.values()),free_bytes=free)

    def preflight(self, name):
        if not NAME.fullmatch(name): raise ValueError('unsupported checkpoint class')
        entry = self.manifest['entries'].get(name)
        if entry and entry['state'] in ('ready','archive'):
            self._check(entry); self.maintain(); return
        if entry is None and os.path.lexists(self.state/name):
            raise ValueError('existing checkpoint requires explicit archive migration')
        if entry and entry['state']=='retired': raise ValueError('retired operation cannot be replayed as new work')
        with closing(self.memory.connect()) as con:
            size = con.execute('pragma page_count').fetchone()[0]*con.execute('pragma page_size').fetchone()[0]
        # Bound target and failed partials separately; never silently delete them.
        partial_bytes = sum(p.stat().st_size for p in self.root.glob('.*.partial-*') if p.is_file())
        if partial_bytes+size>self.policy['max_bytes']:
            raise SnapshotCapacityError('retained partial snapshots require explicit recovery')
        self.maintain(reserve=size if not entry else 0)
        if shutil.disk_usage(self.root).free < size+self.policy['min_free_bytes']:
            raise SnapshotCapacityError('insufficient snapshot storage headroom')
        return size

    def ensure(self, name):
        size = self.preflight(name)
        entry = self.manifest['entries'].get(name)
        if entry and entry['state'] in ('ready','archive'): return Path(entry['path'])
        legacy = self.state/name
        if os.path.lexists(legacy):
            raise ValueError('existing checkpoint needs explicit archive migration before processing')
        target = self.root/name
        if entry is None:
            if os.path.lexists(target): raise ValueError('unregistered checkpoint destination exists')
            entry = dict(state='creating',path=str(target),reserved_bytes=size)
            self.manifest['entries'][name]=entry; self.save()
        if not target.exists(): verified_snapshot(self.memory.DB_PATH,target,timeout=self.policy.get('timeout_seconds',30))
        entry.update(verified(target),state='ready',created_ns=time.time_ns());entry.pop('reserved_bytes',None);self.save()
        self.maintain()
        return target

    def migrate(self):
        """Preserve existing checkpoints as a fixed archive; no age deletion.

        Existing data-volume links are retained. Regular legacy files are copied,
        checked, then atomically replaced by a compatible link. Interrupted copies
        are never mistaken for a completed receipt.
        """
        for source in sorted(self.state.glob('*-before.sqlite')):
            if not NAME.fullmatch(source.name): continue
            if source.name in self.manifest['entries']:
                self._check(self.manifest['entries'][source.name]); continue
            info = verified(source)
            if source.is_symlink():
                target = source.resolve()
                if target.stat().st_dev != self.root.stat().st_dev:
                    raise ValueError('legacy link is not on the selected storage filesystem')
            else:
                archive=self.root/'archive';archive.mkdir(exist_ok=True,mode=0o700)
                target=archive/source.name
                if not target.exists():
                    if shutil.disk_usage(self.root).free < info['bytes']+self.policy['min_free_bytes']:
                        raise SnapshotCapacityError('archive migration requires storage headroom')
                    partial=target.with_name('.'+target.name+'.copying')
                    with source.open('rb') as src, partial.open('wb') as dst:
                        os.chmod(partial,0o600);shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
                    if verified(partial)!=info: raise ValueError('archive copy differs')
                    os.link(partial,target);partial.unlink();sync_directory(archive)
                if verified(target)!=info or verified(source)!=info: raise ValueError('legacy snapshot changed')
                link=source.with_name('.'+source.name+'.relocating')
                if os.path.lexists(link):
                    if not link.is_symlink() or link.resolve()!=target: raise ValueError('migration link conflict')
                else: link.symlink_to(target)
                os.replace(link,source);sync_directory(self.state)
            self.manifest['entries'][source.name]=dict(state='archive',path=str(target),legacy_path=str(source),**info)
            self.save()
        return self.maintain()

    def restore(self, name, destination):
        entry=self.manifest['entries'][name]
        if entry['state'] not in ('ready','archive'): raise ValueError('checkpoint unavailable for restore')
        self._check(entry)
        destination=Path(destination)
        if os.path.lexists(destination): raise FileExistsError(destination)
        partial=destination.with_name('.'+destination.name+'.restoring')
        with open(entry['path'],'rb') as src, partial.open('xb') as dst:
            os.chmod(partial,0o600);shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        if verified(partial)!={k:entry[k] for k in ('bytes','sha256','schema_sha256')}:
            raise ValueError('restored bytes or schema differ')
        os.link(partial,destination);partial.unlink();sync_directory(destination.parent)
        return dict(restored=True,**verified(destination))


def ensure(memory, state_dir, name, configuration, owner):
    if configuration is not None:
        return Store(memory,state_dir,configuration,owner).ensure(name)
    path=Path(state_dir)/name
    if not path.exists(): verified_snapshot(memory.DB_PATH,path)
    return path
