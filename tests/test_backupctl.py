import sqlite3
import json
from pathlib import Path
import pytest
from backupctl import operate
from snapshot_store import SnapshotCapacityError


@pytest.fixture
def config(tmp_path,monkeypatch):
    monkeypatch.delenv('HMK_DB_PATH',raising=False)
    db=tmp_path/'memory.db'
    with sqlite3.connect(db) as con:con.execute('create table memories(value)')
    return {'database':str(db),'snapshots':dict(directory=str(tmp_path/'snapshots'),
        retention_scope='database',max_count=3,max_bytes=1024**2,min_free_bytes=1,
        keep_latest=2,pins=[])}


def test_unfinished_manual_write_survives_later_completions_and_exact_restore(config,tmp_path):
    first=operate(config,'begin',operation='first',reason='Before first write')
    for i in (2,3):
        operate(config,'begin',operation=str(i),reason='Before write')
        with sqlite3.connect(config['database']) as con:con.execute('insert into memories values(?)',(i,))
        operate(config,'complete',operation=str(i),reason='Write verified')
    with pytest.raises(SnapshotCapacityError):operate(config,'begin',operation='4',reason='Before write')
    restored=tmp_path/'restored.db'
    assert operate(config,'restore',operation='first',destination=restored)['sha256']==first['sha256']
    with sqlite3.connect(restored) as con:assert con.execute('select count(*) from memories').fetchone()[0]==0
    operate(config,'complete',operation='first',reason='Cancelled; original needed no longer')
    assert not Path(first['snapshot']).exists()
    operate(config,'begin',operation='4',reason='Before write')
    with sqlite3.connect(config['database']) as con:assert con.execute('select count(*) from memories').fetchone()[0]==2


def test_replay_does_not_create_new_snapshot_or_reuse_completed_point(config):
    a=operate(config,'begin',operation='one',reason='Before correction')
    assert operate(config,'begin',operation='one',reason='Before correction')==a
    operate(config,'complete',operation='one',reason='Correction verified')
    operate(config,'complete',operation='one',reason='Correction verified')
    with pytest.raises(ValueError,match='already completed'):
        operate(config,'begin',operation='one',reason='Before correction')


def test_binding_and_owner_separation(config,monkeypatch,tmp_path):
    monkeypatch.setenv('HMK_DB_PATH',str(tmp_path/'another.db'))
    with pytest.raises(ValueError,match='receiving binding'):operate(config,'maintain')
    monkeypatch.delenv('HMK_DB_PATH')
    operate(config,'begin',operation='one',reason='Before correction')
    other=tmp_path/'another.db';other.write_bytes(Path(config['database']).read_bytes())
    config['database']=str(other)
    with pytest.raises(ValueError,match='owner'):operate(config,'maintain')


def test_interrupted_completion_resumes_retention(config,monkeypatch):
    import backupctl
    for i in range(3):
        operate(config,'begin',operation=str(i),reason='Before correction')
    maintain=backupctl.ManualStore.maintain
    def interrupt(self,*a,**kw):raise RuntimeError('after completion receipt')
    with monkeypatch.context() as patch:
        patch.setattr(backupctl.ManualStore,'maintain',interrupt)
        with pytest.raises(RuntimeError):operate(config,'complete',operation='0',reason='Verified')
    result=operate(config,'complete',operation='0',reason='Verified')
    assert result['retention']['active_count']==2


def test_missing_operation_journal_cannot_reassign_an_old_checkpoint(config):
    first=operate(config,'begin',operation='one',reason='Before correction')
    (Path(config['snapshots']['directory'])/'control/operations.json').unlink()
    with pytest.raises(ValueError,match='journal lost'):
        operate(config,'begin',operation='new',reason='Before different correction')
    assert Path(first['snapshot']).exists()
