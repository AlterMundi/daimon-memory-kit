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
