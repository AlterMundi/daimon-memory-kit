"""Failed backups must never become resumable pre-write recovery checkpoints."""
import sqlite3

import pytest

import sqlite_snapshot


def test_timeout_retains_partial_but_retry_publishes_only_verified_bytes(tmp_path, monkeypatch):
    source, target = tmp_path/'source.db', tmp_path/'before.db'
    with sqlite3.connect(source) as con:
        con.execute('create table memories (content text)')
        con.execute('insert into memories values (?)', ('an original encounter',))
    ticks = iter([0, 31])
    with monkeypatch.context() as patch:
        patch.setattr(sqlite_snapshot.time, 'monotonic', lambda: next(ticks))
        with pytest.raises(TimeoutError):
            sqlite_snapshot.verified_snapshot(source, target)
    assert not target.exists()
    partials = list(tmp_path.glob('.before.db.partial-*'))
    assert len(partials) == 1
    before = partials[0].read_bytes()
    sqlite_snapshot.verified_snapshot(source, target)
    assert partials[0].read_bytes() == before
    with sqlite3.connect(target) as con:
        assert con.execute('pragma integrity_check').fetchone() == ('ok',)
        assert con.execute('select content from memories').fetchone() == ('an original encounter',)


def test_concurrent_recovery_file_is_never_replaced(tmp_path, monkeypatch):
    source, target = tmp_path/'source.db', tmp_path/'before.db'
    with sqlite3.connect(source) as con:
        con.execute('create table memories (content text)')
    link = sqlite_snapshot.os.link
    def race(candidate, destination):
        target.write_bytes(b'retained concurrent recovery')
        link(candidate, destination)
    monkeypatch.setattr(sqlite_snapshot.os, 'link', race)
    with pytest.raises(FileExistsError):
        sqlite_snapshot.verified_snapshot(source, target)
    assert target.read_bytes() == b'retained concurrent recovery'
    partial, = tmp_path.glob('.before.db.partial-*')
    with sqlite3.connect(partial) as con:
        assert con.execute('pragma integrity_check').fetchone() == ('ok',)
