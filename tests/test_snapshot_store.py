"""Checkpoint bounds must preserve pending work, original bytes and replay."""
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from tests.test_portable_producer import setup  # noqa: F401
from portable_producer import process_once
from memory_worker import run
from codex_coordinator import checkpoint
from capturectl import digest
from snapshot_store import Store, SnapshotCapacityError, verified


def config(tmp_path, **kw):
    return dict(directory=str(tmp_path/'data'),max_count=3,max_bytes=32*1024*1024,
                min_free_bytes=1,keep_latest=1,pins=[],**kw)


def owned(setup,tmp_path):
    memory,inbox,state,propose,context,calls,raw=setup
    state.mkdir()
    owner=dict(database=str(memory.DB_PATH.resolve()),state_dir=str(state),context=context,capture_binding=digest(json.loads(inbox.binding)),schema='hmk.portable-producer/v1')
    return Store(memory,state,config(tmp_path),owner)


def complete(store, seq, organization=False):
    owner=store.producer
    checkpoint(store.state/('organization-index.json' if organization else 'index.json'),dict(owner=owner,after=seq,sequence=seq))
    checkpoint(store.state/('embedding-organization-index.json' if organization else 'embedding-index.json'),dict(owner=owner,after=seq))
    # Only authoritative terminal ledger receipts authorize retention.
    from capturectl import CaptureLedger
    ledger=CaptureLedger(store.memory)
    row=ledger.stage(dict(stream_id=('organization:' if organization else 'portable:')+digest(owner),sequence=seq,event_id='fixture:'+str(seq),source_version='fixture',content='original',metadata={'mode':'reported'}))
    ledger.assess(row['event_key'],dict(outcome='omitted',reason='fixture lifecycle only',selection_version='fixture-v1'))


@pytest.mark.parametrize('kind',['batch','embedding','organization','embedding-organization'])
def test_retention_restoration_and_no_reinterpretation_of_retired_work(setup,tmp_path,kind):
    store=owned(setup,tmp_path)
    for seq in range(1,5):
        store.ensure(f'{kind}-{seq}-before.sqlite')
        complete(store,seq,'organization' in kind)
    entries=store.manifest['entries']
    assert entries[f'{kind}-1-before.sqlite']['state']=='retired'
    assert not Path(entries[f'{kind}-1-before.sqlite']['path']).exists()
    assert store.maintain()['active_count']==3
    with pytest.raises(ValueError,match='retired'): store.ensure(f'{kind}-1-before.sqlite')
    dest=tmp_path/'restored.sqlite'
    report=store.restore(f'{kind}-4-before.sqlite',dest)
    assert report['sha256']==entries[f'{kind}-4-before.sqlite']['sha256']
    assert report['schema_sha256']==entries[f'{kind}-4-before.sqlite']['schema_sha256']
    with pytest.raises(FileExistsError): store.restore(f'{kind}-4-before.sqlite',dest)


def test_unknown_unindexed_and_pinned_checkpoints_cannot_be_retired(setup,tmp_path):
    store=owned(setup,tmp_path)
    for seq in range(1,4): store.ensure(f'batch-{seq}-before.sqlite')
    with pytest.raises(SnapshotCapacityError): store.ensure('batch-4-before.sqlite')
    for seq in range(1,4): complete(store,seq)
    store.policy['pins']=['batch-1-before.sqlite','batch-2-before.sqlite']
    with pytest.raises(SnapshotCapacityError): store.ensure('batch-4-before.sqlite')
    assert all(Path(e['path']).exists() for e in store.manifest['entries'].values())


def test_altered_retained_recovery_prevents_deletion(setup,tmp_path):
    store=owned(setup,tmp_path)
    for seq in range(1,4):
        store.ensure(f'batch-{seq}-before.sqlite');complete(store,seq)
    p=Path(store.manifest['entries']['batch-3-before.sqlite']['path'])
    with sqlite3.connect(p) as con: con.execute('create table altered(x)')
    with pytest.raises(ValueError,match='content changed'): store.ensure('batch-4-before.sqlite')
    assert Path(store.manifest['entries']['batch-1-before.sqlite']['path']).exists()


def test_migrate_symlinks_and_regular_files_restores_exact_bytes(setup,tmp_path):
    store=owned(setup,tmp_path)
    from sqlite_snapshot import verified_snapshot
    legacy=store.state/'batch-1-before.sqlite'
    verified_snapshot(store.memory.DB_PATH,legacy)
    prior=verified(legacy)
    other=tmp_path/'previous-data-move.sqlite'
    verified_snapshot(store.memory.DB_PATH,other)
    (store.state/'embedding-1-before.sqlite').symlink_to(other)
    report=store.migrate()
    assert report['archive_count']==2 and legacy.is_symlink()
    assert verified(legacy)==prior
    assert (store.state/'embedding-1-before.sqlite').resolve()==other
    assert store.migrate()['archive_count']==2
    assert store.restore('batch-1-before.sqlite',tmp_path/'restored.db')['sha256']==prior['sha256']
    assert store.maintain()['active_count']==0  # Fixed history is explicitly archived.


def test_interrupted_snapshot_and_retirement_resume(setup,tmp_path,monkeypatch):
    store=owned(setup,tmp_path)
    import snapshot_store
    create=snapshot_store.verified_snapshot
    def interrupted(*args,**kw):
        create(*args,**kw);raise RuntimeError('after publish')
    with monkeypatch.context() as patch:
        patch.setattr(snapshot_store,'verified_snapshot',interrupted)
        with pytest.raises(RuntimeError): store.ensure('batch-1-before.sqlite')
    assert store.manifest['entries']['batch-1-before.sqlite']['state']=='creating'
    store.ensure('batch-1-before.sqlite')
    complete(store,1)
    for seq in (2,3):store.ensure(f'batch-{seq}-before.sqlite');complete(store,seq)
    save=store.save
    def fail_after_delete():
        if store.manifest['entries']['batch-1-before.sqlite']['state']=='retired': raise RuntimeError('after unlink')
        save()
    with monkeypatch.context() as patch:
        patch.setattr(store,'save',fail_after_delete)
        with pytest.raises(RuntimeError):store.ensure('batch-4-before.sqlite')
    resumed=Store(store.memory,store.state,store.policy,store.producer)
    resumed.ensure('batch-4-before.sqlite')
    assert resumed.manifest['entries']['batch-1-before.sqlite']['state']=='retired'


def test_capacity_failure_is_visible_before_models_and_pending_job_survives(setup,tmp_path,monkeypatch):
    memory,inbox,state,propose,context,calls,raw=setup
    p=config(tmp_path);p['min_free_bytes']=10**30
    result=run(memory,inbox,state,propose,context,snapshot_policy=p,max_steps=1)
    assert result['status']['phases']['capture']['reason_code']=='snapshot_capacity_exceeded'
    assert result['status']['phases']['capture']['capacity']['min_free_bytes']==10**30
    assert not calls and (state/'batch-1.json').exists()
    pending=json.loads((state/'batch-1.json').read_text())['input_hash']
    p['min_free_bytes']=1
    result=process_once(memory,inbox,state,propose,context,snapshot_policy=p)
    assert result['state']=='complete' and len(calls)==1
    assert json.loads((state/'batch-1.json').read_text())['input_hash']==pending
    assert not (state/'batch-1-before.sqlite').exists()
    assert (Path(p['directory'])/'batch-1-before.sqlite').exists()


def test_capacity_resume_reuses_completed_provider_call(setup,tmp_path,monkeypatch):
    memory,inbox,state,propose,context,calls,raw=setup
    p=config(tmp_path)
    def crash(at):
        if at=='after_stage':raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):process_once(memory,inbox,state,propose,context,snapshot_policy=p,_fault=crash)
    assert len(calls)==1
    result=process_once(memory,inbox,state,propose,context,snapshot_policy=p)
    assert result['state']=='complete' and len(calls)==1
    with memory.connect() as con:assert con.execute('select count(*) from chapters').fetchone()[0]==1


def test_byte_bound_and_missing_or_failed_checkpoint_never_authorize_retirement(setup,tmp_path):
    store=owned(setup,tmp_path)
    first=store.ensure('batch-1-before.sqlite')
    size=first.stat().st_size
    store.policy['max_count']=20;store.policy['max_bytes']=size+1
    with pytest.raises(SnapshotCapacityError):store.ensure('batch-2-before.sqlite')
    assert first.exists()
    store.policy['max_bytes']=32*1024*1024
    for seq in (2,3):store.ensure(f'batch-{seq}-before.sqlite')
    store.policy['max_count']=3
    # Cursor claims alone cannot authorize retirement of uncertain/failed work.
    checkpoint(store.state/'index.json',dict(owner=store.producer,sequence=3))
    checkpoint(store.state/'embedding-index.json',dict(owner=store.producer,after=3))
    with pytest.raises(SnapshotCapacityError):store.ensure('batch-4-before.sqlite')
    complete(store,1)
    first.unlink()
    with pytest.raises(ValueError,match='lost'):store.ensure('batch-4-before.sqlite')


def test_retained_partials_are_bounded_but_never_silently_removed(setup,tmp_path):
    store=owned(setup,tmp_path)
    for i in range(3): (store.root/f'.batch-1-before.sqlite.partial-{i}').write_bytes(b'')
    with pytest.raises(SnapshotCapacityError):store.ensure('batch-1-before.sqlite')
    assert len(list(store.root.glob('.*.partial-*')))==3


def test_profile_accepts_explicit_policy_and_rejects_invalid_limits(setup,tmp_path):
    from tests.test_memory_runtime import configuration
    from memory_runtime import profile
    memory,inbox,state,_,context,_,_=setup
    value=configuration(tmp_path,memory,inbox,state,context);value['snapshots']=config(tmp_path)
    path=tmp_path/'profile.json';checkpoint(path,value)
    assert profile(path)['snapshots']==value['snapshots']
    value['snapshots']['max_count']=True;checkpoint(path,value)
    with pytest.raises(ValueError):profile(path)


def test_verification_closes_sqlite_handles_on_success_and_rejection(tmp_path,monkeypatch):
    import snapshot_store
    path=tmp_path/'checkpoint.db'
    with sqlite3.connect(path) as con:con.execute('create table original(x)')
    connect=sqlite3.connect;closed=[]
    class Tracked(sqlite3.Connection):
        def close(self):
            closed.append(True);return super().close()
    monkeypatch.setattr(snapshot_store.sqlite3,'connect',lambda *a,**k:connect(*a,**k,factory=Tracked))
    verified(path);assert len(closed)==1
    with connect(path) as con:
        con.execute('create table child(parent references original(x))')
        con.execute('insert into child values(5)')
    with pytest.raises((ValueError,sqlite3.DatabaseError)):verified(path)
    assert len(closed)==2


def test_configured_copy_timeout_preserves_partial_and_resumes(setup,tmp_path,monkeypatch):
    import snapshot_store
    store=owned(setup,tmp_path);store.policy['timeout_seconds']=300
    original=snapshot_store.verified_snapshot;seen=[]
    def timeout_once(source,destination,*,timeout):
        seen.append(timeout)
        if len(seen)==1:
            (Path(destination).parent/('.'+Path(destination).name+'.partial-fixture')).write_bytes(b'failed copy')
            raise TimeoutError('bounded copy interrupted')
        return original(source,destination,timeout=timeout)
    monkeypatch.setattr(snapshot_store,'verified_snapshot',timeout_once)
    with pytest.raises(TimeoutError):store.ensure('batch-1-before.sqlite')
    store.ensure('batch-1-before.sqlite')
    assert seen==[300,300]
    assert (store.root/'.batch-1-before.sqlite.partial-fixture').read_bytes()==b'failed copy'


def test_database_retention_keeps_two_points_across_all_operation_classes(setup,tmp_path):
    store=owned(setup,tmp_path)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=8)
    names=['batch-1-before.sqlite','embedding-1-before.sqlite',
           'organization-1-before.sqlite','embedding-organization-1-before.sqlite']
    for name in names:
        store.ensure(name)
        complete(store,1,'organization' in name)
    result=store.maintain()
    assert result['active_count']==2
    assert [n for n,e in store.manifest['entries'].items() if e['state']=='ready']==names[-2:]
    assert store.restore(names[-1],tmp_path/'restore.sqlite')['restored']


def test_database_archive_retirement_preserves_pending_and_pin_then_reconciles(setup,tmp_path):
    from sqlite_snapshot import verified_snapshot
    store=owned(setup,tmp_path)
    for seq in range(1,5):
        verified_snapshot(store.memory.DB_PATH,store.state/f'batch-{seq}-before.sqlite')
    store.migrate()
    for seq in (1,3,4):complete(store,seq)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=5,
                        pins=['batch-1-before.sqlite'])
    assert store.maintain()['active_count']==4  # seq2 has no terminal event.
    store.policy['pins']=[]
    assert store.maintain()['active_count']==3
    entry=store.manifest['entries']['batch-1-before.sqlite']
    assert entry['state']=='retired' and entry['sha256']
    assert not Path(entry['path']).exists() and not (store.state/'batch-1-before.sqlite').is_symlink()
    complete(store,2)
    assert store.maintain()['active_count']==2
    assert store.maintain()['active_count']==2  # idempotent maintenance
    store.restore('batch-4-before.sqlite',tmp_path/'restored.sqlite')


def test_database_archive_is_in_capacity_budget(setup,tmp_path):
    from sqlite_snapshot import verified_snapshot
    store=owned(setup,tmp_path)
    for seq in (1,2):verified_snapshot(store.memory.DB_PATH,store.state/f'batch-{seq}-before.sqlite')
    store.migrate()
    store.policy.update(retention_scope='database',max_count=1)
    with pytest.raises(SnapshotCapacityError):store.maintain()
    assert all(Path(e['path']).exists() for e in store.manifest['entries'].values())


def test_database_archive_retirement_resumes_after_unlink(setup,tmp_path,monkeypatch):
    from sqlite_snapshot import verified_snapshot
    store=owned(setup,tmp_path)
    for seq in (1,2):
        verified_snapshot(store.memory.DB_PATH,store.state/f'batch-{seq}-before.sqlite')
        complete(store,seq)
    store.migrate()
    store.policy.update(retention_scope='database')
    original=Path.unlink
    def interrupted(path,*a,**kw):
        result=original(path,*a,**kw)
        if path==Path(store.manifest['entries']['batch-1-before.sqlite']['path']):
            raise RuntimeError('after archive unlink')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(Path,'unlink',interrupted)
        with pytest.raises(RuntimeError,match='after archive unlink'):store.maintain()
    resumed=Store(store.memory,store.state,store.policy,store.producer)
    assert resumed.maintain()['active_count']==1
    assert not (store.state/'batch-1-before.sqlite').is_symlink()
    assert resumed.manifest['entries']['batch-1-before.sqlite']['state']=='retired'


def test_database_archive_changed_link_blocks_retirement(setup,tmp_path):
    from sqlite_snapshot import verified_snapshot
    store=owned(setup,tmp_path)
    for seq in (1,2):
        verified_snapshot(store.memory.DB_PATH,store.state/f'batch-{seq}-before.sqlite')
        complete(store,seq)
    store.migrate()
    store.policy.update(retention_scope='database')
    legacy=store.state/'batch-1-before.sqlite'
    legacy.unlink();legacy.symlink_to(tmp_path/'foreign')
    with pytest.raises(ValueError,match='compatibility path changed'):store.maintain()
    assert Path(store.manifest['entries']['batch-1-before.sqlite']['path']).exists()


def test_registered_checkpoint_hash_proof_rejects_later_journal(setup,tmp_path):
    store=owned(setup,tmp_path)
    path=store.ensure('batch-1-before.sqlite')
    Path(str(path)+'-wal').write_bytes(b'unresolved writer state')
    with pytest.raises(ValueError,match='standalone'):
        store._check(store.manifest['entries']['batch-1-before.sqlite'])


def test_archive_recency_uses_source_time_not_migration_copy_order(setup,tmp_path):
    import os
    from sqlite_snapshot import verified_snapshot
    store=owned(setup,tmp_path)
    # Alphabetical copy order and stream sequence order both differ from time.
    times={'batch-2-before.sqlite':30,'embedding-1-before.sqlite':10,
           'organization-1-before.sqlite':20}
    for name,stamp in times.items():
        path=store.state/name;verified_snapshot(store.memory.DB_PATH,path)
        os.utime(path,ns=(stamp,stamp))
        complete(store,int(name.split('-')[1]),'organization' in name)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=6)
    store.migrate()
    assert store.manifest['entries']['embedding-1-before.sqlite']['state']=='retired'
    assert store.manifest['entries']['batch-2-before.sqlite']['created_ns']==30
    assert store.manifest['entries']['organization-1-before.sqlite']['state']=='archive'


def test_preserved_history_counts_in_same_budget_and_is_never_pruned(setup,tmp_path):
    import hashlib
    store=owned(setup,tmp_path)
    archive=store.root/'history.tar.zst';archive.write_bytes(b'preserved original history')
    store.policy.update(retention_scope='database',retained_files=[{
        'name':archive.name,'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}])
    first=store.ensure('batch-1-before.sqlite');complete(store,1)
    store.policy['max_bytes']=first.stat().st_size+1
    with pytest.raises(SnapshotCapacityError):store.maintain()
    assert first.exists() and archive.exists()
    store.policy['max_bytes']=32*1024*1024
    assert store.maintain()['retained_file_bytes']==archive.stat().st_size
    archive.write_bytes(b'x'*archive.stat().st_size)
    with pytest.raises(ValueError,match='content changed'):store.maintain()


def test_preserved_history_cannot_escape_storage_or_alias_a_checkpoint(tmp_path):
    from snapshot_store import policy
    import hashlib
    p=config(tmp_path)
    for name in ('../private','/elsewhere','owner.json','batch-1-before.sqlite'):
        p['retained_files']=[dict(name=name,bytes=1,sha256=hashlib.sha256(b'x').hexdigest())]
        with pytest.raises(ValueError):policy(p)


def test_growth_budget_rotates_two_verified_points_and_restores_after_growth(setup,tmp_path):
    store=owned(setup,tmp_path)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=6,
                        max_bytes=1,database_copies=3)
    old_budget=store.byte_budget()
    for seq in range(1,7):
        with store.memory.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS growth_test(data BLOB)')
            con.execute('INSERT INTO growth_test VALUES(zeroblob(32768))')
            con.commit()
        store.ensure(f'batch-{seq}-before.sqlite');complete(store,seq)
        if seq>=2: assert store.maintain()['active_count']==2
    assert store.byte_budget()>old_budget
    assert store.restore('batch-6-before.sqlite',tmp_path/'restored.sqlite')['restored']
    with sqlite3.connect(tmp_path/'restored.sqlite') as con:
        assert con.execute('SELECT count(*) FROM growth_test').fetchone()[0]==6


def test_growth_budget_still_protects_pending_work_and_storage_headroom(setup,tmp_path,monkeypatch):
    store=owned(setup,tmp_path)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=6,
                        max_bytes=1,database_copies=3)
    for seq in range(1,4): store.ensure(f'batch-{seq}-before.sqlite')
    with pytest.raises(SnapshotCapacityError) as exc: store.ensure('batch-4-before.sqlite')
    assert exc.value.capacity['required_bytes']>exc.value.capacity['byte_budget']
    assert all(e['state']=='ready' and Path(e['path']).exists() for e in store.manifest['entries'].values())
    for seq in range(1,4):complete(store,seq)
    store.maintain()
    from types import SimpleNamespace
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=0))
    with pytest.raises(SnapshotCapacityError) as exc: store.ensure('batch-4-before.sqlite')
    assert exc.value.capacity['free_bytes']==0
    assert len([e for e in store.manifest['entries'].values() if e['state']=='ready'])==2


@pytest.mark.parametrize('copies',[True,0,2,7,3.5])
def test_growth_budget_rejects_missing_creation_margin_and_unbounded_count(tmp_path,copies):
    from snapshot_store import policy
    p=config(tmp_path);p.update(retention_scope='database',keep_latest=2,max_count=6,database_copies=copies)
    with pytest.raises(ValueError,match='database copies'):policy(p)


def test_growth_budget_allows_compaction_and_keeps_old_points_until_new_is_verified(setup,tmp_path,monkeypatch):
    import snapshot_store
    store=owned(setup,tmp_path)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=6,
                        max_bytes=1,database_copies=3)
    with store.memory.connect() as con:
        con.execute('CREATE TABLE growth_test(data BLOB)')
        con.execute('INSERT INTO growth_test VALUES(zeroblob(65536))');con.commit()
    for seq in (1,2):store.ensure(f'batch-{seq}-before.sqlite');complete(store,seq)
    large_budget=store.byte_budget()
    with store.memory.connect() as con:
        con.execute('DROP TABLE growth_test');con.commit();con.execute('VACUUM')
    assert store.byte_budget()==large_budget
    original=snapshot_store.verified_snapshot
    def interrupted(*args,**kwargs):raise TimeoutError('fixture interrupted copy')
    with monkeypatch.context() as patch:
        patch.setattr(snapshot_store,'verified_snapshot',interrupted)
        with pytest.raises(TimeoutError):store.ensure('batch-3-before.sqlite')
    assert all(Path(store.manifest['entries'][f'batch-{n}-before.sqlite']['path']).exists() for n in (1,2))
    store.ensure('batch-3-before.sqlite');complete(store,3)
    store.ensure('batch-4-before.sqlite');complete(store,4)
    assert store.maintain()['active_count']==2
    assert store.byte_budget()<large_budget


def test_growth_budget_reserves_registered_history_without_losing_rotation_slot(setup,tmp_path):
    import hashlib
    store=owned(setup,tmp_path)
    store.policy.update(retention_scope='database',keep_latest=2,max_count=6,
                        max_bytes=1,database_copies=3)
    history=store.root/'history.tar.zst';history.write_bytes(b'fixed preserved history')
    store.policy['retained_files']=[dict(name=history.name,bytes=history.stat().st_size,
                                       sha256=hashlib.sha256(history.read_bytes()).hexdigest())]
    for seq in range(1,5):
        store.ensure(f'batch-{seq}-before.sqlite');complete(store,seq)
    assert store.maintain()['active_count']==2
    assert history.read_bytes()==b'fixed preserved history'
    history.write_bytes(b'changed')
    with pytest.raises(ValueError,match='content changed'):store.ensure('batch-5-before.sqlite')
