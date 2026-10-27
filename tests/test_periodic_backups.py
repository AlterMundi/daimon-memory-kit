"""Periodic recovery protection costs scale with intervals, not ordinary writes."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tests.test_backupctl import config  # noqa: F401
from backupctl import operate
from periodic_backups import Baselines
import periodic_backups
import snapshot_store


def configured(config,tmp_path):
    config['snapshots']['routine_backup']=dict(directory=str(tmp_path/'baselines'),subject='fixture:being',interval_seconds=86400)
    return config,Baselines(config['database'],config['snapshots'])


def test_many_manual_and_worker_writes_share_baseline_without_copy_or_full_scan(config,tmp_path,monkeypatch):
    value,pool=configured(config,tmp_path)
    assert pool.refresh()['created']
    def forbidden(*a,**kw):pytest.fail('ordinary writes must not copy/hash/scan the database')
    monkeypatch.setattr(periodic_backups,'verified_snapshot',forbidden)
    monkeypatch.setattr(snapshot_store.Store,'_check',forbidden)
    for i in range(20):
        receipt=operate(value,'begin',operation=str(i),reason='Remember encounter')
        assert receipt['snapshot'] is None and receipt['recovery_scope']=='periodic_database'
        with sqlite3.connect(value['database']) as c:c.execute('insert into memories values(?)',(i,))
        operate(value,'complete',operation=str(i),reason='Write verified')
    owner=dict(database=value['database'],context=dict(subject='fixture:being'))
    worker_policy=dict(value['snapshots'],directory=str(tmp_path/'worker-checkpoints'))
    worker_state=tmp_path/'worker';worker_state.mkdir()
    store=snapshot_store.Store(type('Memory',(),{'DB_PATH':Path(value['database'])})(),worker_state,worker_policy,owner)
    assert store.preflight('batch-1-before.sqlite')==0
    assert store.ensure('batch-1-before.sqlite') is None
    assert not pool.refresh()['created']
    assert len(list(pool.root.glob('baseline-*.sqlite')))==1
    assert not list(Path(value['snapshots']['directory']).glob('*-before.sqlite'))


def test_changed_database_rotates_by_interval_and_restore_matches_committed_bytes(config,tmp_path,monkeypatch):
    value,pool=configured(config,tmp_path);clock=[1000000000000]
    monkeypatch.setattr(periodic_backups.time,'time_ns',lambda:clock[0])
    assert pool.refresh()['created']
    for i in range(3):
        with sqlite3.connect(value['database']) as c:c.execute('insert into memories values(?)',(i,))
        clock[0]+=86401*1000000000
        assert pool.refresh()['created']
    names=[n for n,e in pool.read()['entries'].items() if e['state']=='ready']
    assert len(names)==2 and len(list(pool.root.glob('baseline-*.sqlite')))==2
    latest=max(names,key=lambda n:pool.read()['entries'][n]['created_ns'])
    destination=tmp_path/'restored.sqlite';receipt=pool.restore(latest,destination)
    assert receipt['restored']
    with sqlite3.connect(destination) as c:assert c.execute('select value from memories order by value').fetchall()==[(0,),(1,),(2,)]
    with pytest.raises(FileExistsError):pool.restore(latest,destination)


def test_no_change_means_audit_instead_of_another_full_copy(config,tmp_path,monkeypatch):
    value,pool=configured(config,tmp_path);clock=[1000000000000]
    monkeypatch.setattr(periodic_backups.time,'time_ns',lambda:clock[0]);pool.refresh()
    monkeypatch.setattr(periodic_backups,'verified_snapshot',lambda *a,**kw:pytest.fail('unchanged database'))
    clock[0]+=86401*1000000000
    assert pool.refresh()['created'] is False
    assert len(list(pool.root.glob('baseline-*.sqlite')))==1


def test_backup_space_failure_does_not_prevent_normal_remembering_but_critical_is_blocked(config,tmp_path,monkeypatch):
    value,pool=configured(config,tmp_path)
    monkeypatch.setattr(periodic_backups.shutil,'disk_usage',lambda p:type('Usage',(),{'free':0})())
    assert pool.refresh()['state']=='failed'
    assert pool.status()['reason_code']=='backup_capacity'
    receipt=operate(value,'begin',operation='ordinary',reason='Human encounter')
    assert receipt['backup']['state']=='failed'
    with sqlite3.connect(value['database']) as c:c.execute('insert into memories values(?)',('remembered',))
    operate(value,'complete',operation='ordinary',reason='Write verified')
    with pytest.raises(snapshot_store.SnapshotCapacityError):
        operate(value,'begin',operation='schema-change',reason='Before schema migration',critical=True)
    with sqlite3.connect(value['database']) as c:assert c.execute('select value from memories').fetchone()[0]=='remembered'


def test_critical_maintenance_has_its_own_exact_snapshot_and_cannot_downgrade(config,tmp_path):
    value,pool=configured(config,tmp_path)
    receipt=operate(value,'begin',operation='critical',reason='Before destructive repair',critical=True)
    assert Path(receipt['snapshot']).is_file()
    with pytest.raises(ValueError,match='retain --critical'):
        operate(value,'begin',operation='critical',reason='Before destructive repair')
    assert operate(value,'restore',operation='critical',destination=tmp_path/'before.sqlite')['sha256']==receipt['sha256']
    operate(value,'complete',operation='critical',reason='Repair verified')
    operate(value,'begin',operation='routine',reason='Ordinary memory')
    with pytest.raises(ValueError,match='no per-operation restore'):
        operate(value,'restore',operation='routine',destination=tmp_path/'false-undo.sqlite')


def test_existing_pending_manual_operation_keeps_its_original_recovery_contract(config,tmp_path):
    before=operate(config,'begin',operation='old',reason='Existing pending work')
    value,pool=configured(config,tmp_path)
    assert operate(value,'begin',operation='old',reason='Existing pending work')==before
    assert operate(value,'restore',operation='old',destination=tmp_path/'old.sqlite')['sha256']==before['sha256']


def test_interruption_retains_attempt_without_repeated_copy_and_recovers_published_point(config,tmp_path,monkeypatch):
    value,pool=configured(config,tmp_path);real=periodic_backups.verified_snapshot;calls=[]
    def crash(source,target,**kw):
        calls.append(1);real(source,target,**kw);raise RuntimeError('after atomic publication')
    monkeypatch.setattr(periodic_backups,'verified_snapshot',crash)
    assert pool.refresh()['state']=='failed'
    assert pool.refresh()['state']=='failed' and len(calls)==1
    monkeypatch.setattr(periodic_backups,'verified_snapshot',lambda *a,**kw:pytest.fail('published point must be reused'))
    assert pool.refresh(recover=True)['state']=='current'
    assert len(list(pool.root.glob('baseline-*.sqlite')))==1


def test_changed_or_missing_baseline_detected_and_foreign_owner_refused(config,tmp_path):
    value,pool=configured(config,tmp_path);receipt=pool.refresh();path=Path(receipt['snapshot'])
    path.write_bytes(path.read_bytes()+b'altered')
    assert pool.status()['state']=='failed'
    path.unlink();assert pool.status()['state']=='failed'
    other=tmp_path/'other.sqlite';other.write_bytes(Path(value['database']).read_bytes())
    with pytest.raises(ValueError,match='owner differs'):Baselines(other,value['snapshots']).status()


from tests.test_portable_producer import setup  # noqa: E402,F401
from tests.test_memory_runtime import configuration as worker_configuration  # noqa: E402


def test_real_worker_keeps_committed_memory_and_projects_backup_failure_then_resolution(setup,tmp_path,monkeypatch):
    import memory_runtime
    from provider_status import safe_projection
    memory,inbox,state,propose,context,calls,_=setup
    value=worker_configuration(tmp_path,memory,inbox,state,context)
    value['snapshots']=dict(directory=str(tmp_path/'old-worker'),retention_scope='database',max_count=3,
        max_bytes=1024**2,min_free_bytes=1,keep_latest=2,pins=[],
        routine_backup=dict(directory=str(tmp_path/'baselines'),subject=context['subject'],interval_seconds=86400))
    propose.policy={}
    monkeypatch.setattr(memory_runtime,'load_memory',lambda _:memory)
    monkeypatch.setattr(memory_runtime,'Models',lambda *a:propose)
    monkeypatch.setattr(memory,'embeddings_runtime_config',lambda **kw:dict(provider='local',model='fixture',output_dimensionality=None))
    monkeypatch.setattr(memory,'embed_texts',lambda provider,texts,**kw:[[1.0,0.0] for _ in texts])
    original=periodic_backups.shutil.disk_usage
    monkeypatch.setattr(periodic_backups.shutil,'disk_usage',lambda p:type('Usage',(),{'free':0})())
    first=memory_runtime.run(value)
    assert first['backup']['state']=='failed' and first['status']['state']=='pending'
    assert len(calls)==1
    with memory.connect() as c:assert c.execute('select count(*) from chapters').fetchone()[0]==1
    notices=safe_projection(inbox)['items']
    assert len(notices)==1 and notices[0]['phase']=='backup' and notices[0]['problem_code']=='storage_pressure'
    assert str(tmp_path) not in json.dumps(notices)
    # A later invocation restores backup protection without another paid selection
    # or another copy of the already-committed memory.
    monkeypatch.setattr(periodic_backups.shutil,'disk_usage',original)
    second=memory_runtime.run(value)
    assert second['backup']['state']=='current' and len(calls)==1
    resolved=safe_projection(inbox)['items']
    assert resolved[0]['incident_id']==notices[0]['incident_id'] and resolved[0]['processing_state']=='resolved'
    assert not memory_runtime.run(value)['backup']['created']


def test_manifest_loss_refuses_to_reassign_existing_files(config,tmp_path):
    value,pool=configured(config,tmp_path);receipt=pool.refresh()
    pool.manifest_path.unlink()
    with pytest.raises(ValueError,match='manifest lost'):pool.refresh()
    assert Path(receipt['snapshot']).exists()


def test_corrupted_backup_requires_explicit_recovery_and_preserves_quarantined_bytes(config,tmp_path):
    value,pool=configured(config,tmp_path);receipt=pool.refresh();bad=Path(receipt['snapshot'])
    original=bad.read_bytes();bad.write_bytes(original+b'damaged')
    assert pool.refresh()['state']=='failed'
    assert len(list(pool.root.glob('baseline-*.sqlite')))==1
    recovered=pool.refresh(recover=True)
    assert recovered['state']=='current' and recovered['quarantined_baselines']==1
    assert bad.read_bytes()==original+b'damaged'
    assert pool.read()['entries'][bad.name]['state']=='quarantined'


def test_recovered_publication_does_not_claim_later_changes_were_backed_up(config,tmp_path,monkeypatch):
    value,pool=configured(config,tmp_path);original=periodic_backups.verified_snapshot
    def crash(source,target,**kw):original(source,target,**kw);raise RuntimeError('after publication')
    monkeypatch.setattr(periodic_backups,'verified_snapshot',crash)
    assert pool.refresh()['state']=='failed'
    with sqlite3.connect(value['database']) as c:c.execute('insert into memories values(?)',('later',))
    monkeypatch.setattr(periodic_backups,'verified_snapshot',lambda *a,**kw:pytest.fail('reuse published candidate'))
    result=pool.refresh(recover=True);dest=tmp_path/'restored-earlier.sqlite'
    pool.restore(Path(result['snapshot']).name,dest)
    with sqlite3.connect(dest) as c:assert c.execute('select count(*) from memories').fetchone()[0]==0
    with sqlite3.connect(value['database']) as c:assert c.execute('select value from memories').fetchone()[0]=='later'
