"""Forward coverage across old/new sessions, bounded reads and recovery."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from capture_inbox import Inbox
from codex_hook_capture import capture
from forward_capture import activate, set_enabled
from portable_capture import codex_sources


def test_capture_recovers_interrupted_sqlite_write(context):
    """A killed writer leaves a hot journal; the next hook must recover it."""
    import sqlite3
    import subprocess
    b, f, e = context
    with sqlite3.connect(b['inbox']) as con:
        con.execute('CREATE TABLE crash_fixture(value BLOB)')
        con.execute('INSERT INTO crash_fixture VALUES(zeroblob(200000))')
    child = subprocess.run([sys.executable, '-c', '''
import os, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute('PRAGMA cache_size=1')
con.execute('BEGIN IMMEDIATE')
con.execute('UPDATE crash_fixture SET value=randomblob(200000)')
os._exit(7)
''', b['inbox']], check=False)
    assert child.returncode == 7
    # Establish the precise failure, rather than merely creating a journal file.
    with sqlite3.connect(Path(b['inbox']).as_uri()+'?mode=ro', uri=True) as con:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            con.execute('SELECT value FROM forward_policy').fetchone()
    append(f, turn('after-crash', 'Remember the recovered turn.'))
    result = capture(b, e)
    assert result['capture_complete']
    inbox = Inbox(b['inbox'], b)
    assert b'Remember the recovered turn.' in inbox.restore(result['revisions'][0])
    with inbox.connect() as con:
        assert con.execute('SELECT value=zeroblob(200000) FROM crash_fixture').fetchone()[0]
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        count = con.execute('SELECT count(*) FROM revisions').fetchone()[0]
    assert capture(b, e)['capture_complete']
    with inbox.connect() as con:
        assert con.execute('SELECT count(*) FROM revisions').fetchone()[0] == count


def line(kind,payload):
    return (json.dumps(dict(type=kind,payload=payload))+'\n').encode()


def turn(name,text):
    return line('event_msg',dict(type='task_started',turn_id=name))+line('turn_context',dict(turn_id=name,cwd='/work'))+line('response_item',dict(type='message',role='user',content=[dict(type='input_text',text=text)]))


@pytest.fixture
def context(tmp_path):
    root=tmp_path/'sources';root.mkdir()
    b=dict(schema='hmk.codex-hook-binding/v2',subject='fixture:ilex',source_instance='fixture:desk',source_root=str(root),allowed_cwds=['/work'],inbox=str(tmp_path/'inbox.sqlite'),max_source_bytes=2048,sessions_started_at_or_after='2026-10-13T00:00:00Z')
    f=root/'old.jsonl';f.write_bytes(line('session_meta',dict(id='old',cwd='/old',timestamp='2026-01-01T00:00:00Z'))+turn('past','Do not import this old story.'))
    e=dict(hook_event_name='Stop',session_id='old',cwd='/work',transcript_path=str(f))
    activate(b,tmp_path/'before.sqlite')
    return b,f,e


def append(f,data):
    with f.open('ab') as s:s.write(data)


def test_old_session_keeps_new_turns_and_exact_provenance(context):
    b,f,e=context;boundary=f.stat().st_size
    append(f,line('response_item',dict(type='message',role='assistant',content=[dict(type='output_text',text='Old in-flight turn ending.')])) )
    first=capture(b,e);assert first['capture_complete'] and first['awaiting_new_turn']
    raw=turn('new','Jo proposed a reversible clamp.');start=f.stat().st_size;append(f,raw)
    result=capture(b,e);assert result['capture_complete']
    inbox=Inbox(b['inbox'],b);snapshot=inbox.restore(result['revisions'][0]);assert snapshot.endswith(raw) and b'old story' not in snapshot and b'in-flight' not in snapshot
    with inbox.connect() as con:
        r=con.execute('SELECT * FROM forward_ranges').fetchone();assert (r['file_start'],r['file_end'])==(start,f.stat().st_size)
    f.unlink();assert inbox.restore(result['revisions'][0])==snapshot
    assert boundary<start


def test_large_old_source_reads_only_unread_suffix(context):
    b,f,e=context
    # A second old file exists before a separate activation; its old body is never parsed.
    set_enabled(b,False)
    b={**b,'inbox':str(f.parent.parent/'large.sqlite')}
    with f.open('r+b') as s:s.truncate(70*1024*1024);s.seek(-1,2);s.write(b'\n')
    activate(b,f.parent.parent/'large-before.sqlite');append(f,turn('new','Recent contribution.'))
    assert capture(b,e)['capture_complete']
    with Inbox(b['inbox'],b).connect() as con:
        assert con.execute('select sum(length(delta)) from revisions').fetchone()[0]<2048


def test_new_sessions_and_current_working_directory(context):
    b,f,e=context
    new=f.with_name('new.jsonl');new.write_bytes(line('session_meta',dict(id='new',cwd='/different-original',timestamp=datetime.now(timezone.utc).isoformat()))+turn('fresh','New session report.'))
    assert capture(b,{**e,'session_id':'new','transcript_path':str(new)})['capture_complete']
    assert capture(b,{**e,'cwd':'/unselected'})['skipped']
    moved=f.with_name('moved.jsonl');moved.write_bytes(f.read_bytes())
    assert capture(b,{**e,'transcript_path':str(moved)})['error']=='session_scope_unverified'


@pytest.mark.parametrize('point',['before_commit','after_commit'])
def test_transaction_replay_preserves_one_range(context,point):
    b,f,e=context;append(f,turn('one','One contribution.'))
    def crash(at):
        if at==point:raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):capture(b,e,_fault=crash)
    assert capture(b,e)['capture_complete']
    with Inbox(b['inbox'],b).connect() as con:
        assert con.execute('select count(*) from observations').fetchone()[0]==1
        assert con.execute('select count(*) from forward_ranges').fetchone()[0]==1


def test_concurrent_hooks_do_not_duplicate(context):
    b,f,e=context;append(f,turn('one','Concurrent contribution.'))
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:capture(b,e),range(8)))
    assert all(r['capture_complete'] for r in results)
    assert sum(len(r['revisions']) for r in results)==1


def test_bounded_catchup_keeps_tool_dependencies(context):
    b,f,e=context
    data=turn('long','A long useful work session.')+line('response_item',dict(type='function_call',name='test',call_id='call-1',arguments='{}'))
    data+=b''.join(line('event_msg',dict(type='item_completed',padding='x'*180)) for _ in range(30))
    data+=line('response_item',dict(type='function_call_output',call_id='call-1',output='The action failed: device disconnected.'))
    append(f,data);results=[]
    for _ in range(10):
        result=capture(b,e);results.append(result)
        if result['capture_complete']:break
    assert len(results)>1 and results[-1]['capture_complete']
    assert all(r['error']=='capture_deferred' for r in results[:-1])
    inbox=Inbox(b['inbox'],b)
    with inbox.connect() as con:rows=con.execute('select source,revision from heads').fetchall()
    assert len(rows)==1
    normalized=codex_sources(inbox.restore(rows[0]['revision']),source=rows[0]['source'])
    assert not normalized['unsupported']
    assert normalized['sources'][-1]['dependencies']


def test_pause_resume_preserves_cursor_and_does_not_fallback(context):
    b,f,e=context;append(f,turn('one','First.'));first=capture(b,e)
    set_enabled(b,False);append(f,turn('two','Second.'));assert not capture(b,e)['capture_complete']
    set_enabled(b,True);second=capture(b,e);assert second['capture_complete']
    assert len(first['revisions'])==len(second['revisions'])==1
    assert capture(b,e)['revisions']==[]


@pytest.mark.parametrize('change',['truncate','replace','boundary'])
def test_changed_source_is_visible_without_advancing(context,change):
    b,f,e=context;append(f,turn('one','First.'));capture(b,e)
    if change=='truncate':f.write_bytes(f.read_bytes().split(b'\n',1)[0]+b'\n')
    elif change=='replace':
        copy=f.with_suffix('.swap');copy.write_bytes(f.read_bytes());copy.replace(f)
    else:
        with f.open('r+b') as s:s.seek(-2,2);s.write(b'x')
    assert capture(b,e)['error']=='source_changed_during_capture'
    with Inbox(b['inbox'],b).connect() as con:assert con.execute('select count(*) from observations').fetchone()[0]==1


def test_partial_record_and_oversized_single_record_are_visible(context):
    b,f,e=context;raw=turn('one','Incomplete now, complete later.')
    append(f,raw[:-3]);r=capture(b,e);assert not r['capture_complete']
    append(f,raw[-3:]);assert capture(b,e)['capture_complete']
    append(f,b'x'*4096);assert capture(b,e)['error']=='source_exceeds_capture_limit'


def test_legacy_pending_stream_is_preserved(tmp_path):
    root=tmp_path/'sources';root.mkdir();f=root/'session.jsonl'
    b=dict(schema='hmk.codex-hook-binding/v2',subject='fixture:ilex',source_instance='fixture:desk',source_root=str(root),allowed_cwds=['/work'],inbox=str(tmp_path/'inbox.sqlite'),max_source_bytes=2048,sessions_started_at_or_after='2026-10-13T00:00:00Z')
    f.write_bytes(line('session_meta',dict(id='existing',cwd='/work',timestamp='2026-10-14T00:00:00Z'))+turn('before','Already selected.'))
    e=dict(hook_event_name='Stop',session_id='existing',cwd='/work',transcript_path=str(f));prior=capture(b,e)
    activate(b,tmp_path/'before.sqlite');append(f,turn('after','New turn.'));assert capture(b,e)['capture_complete']
    inbox=Inbox(b['inbox'],b);assert b'Already selected.' in inbox.restore(prior['revision'])
    assert len(inbox.observations())==2


def test_existing_producer_accepts_segments_without_duplicate_learning(context,tmp_path,monkeypatch):
    from portable_producer import process_once
    b,f,e=context;append(f,turn('new','Mara proposed a better clamp, still untested.'));capture(b,e)
    monkeypatch.setenv('HMK_AGENT_MEMORY_BASE',str(tmp_path/'canon'));monkeypatch.setenv('HMK_DB_PATH',str(tmp_path/'canon/library.db'))
    spec=importlib.util.spec_from_file_location('forward_test_memory',SCRIPTS/'memoryctl.py');memory=importlib.util.module_from_spec(spec);spec.loader.exec_module(memory);memory.init_db()
    calls=[]
    def propose(request,path):
        sources=json.loads(request['messages'][1]['content'])['sources'];calls.append(sources)
        assert all('old story' not in s['content'] for s in sources)
        return {'selection':dict(outcome='applied',reason='Significant proposal',records=[dict(key='mara',operation='add',shelf='episodes',title='Mara',source_ids=[sources[0]['id']])],links=[])}
    inbox=Inbox(b['inbox'],b);state=tmp_path/'processor'
    result=process_once(memory,inbox,state,propose,b,retrieval='lexical')
    assert result['state']=='complete',result
    assert capture(b,e)['revisions']==[]
    assert process_once(memory,inbox,state,propose,b,retrieval='lexical')['state']=='idle'
    assert len(calls)==1


def test_unselected_intervening_turn_is_not_imported(context):
    b,f,e=context
    append(f,turn('unselected','PRIVATE elsewhere').replace(b'"cwd": "/work"',b'"cwd": "/elsewhere"'))
    append(f,turn('selected','Allowed report.'))
    result=capture(b,e);assert result['capture_complete']
    inbox=Inbox(b['inbox'],b)
    assert len(result['revisions'])==1
    assert b'PRIVATE' not in inbox.restore(result['revisions'][0])


def test_turn_scope_can_arrive_after_an_early_hook(context):
    b,f,e=context
    append(f,line('event_msg',dict(type='task_started',turn_id='new')))
    first=capture(b,e);assert not first['capture_complete'] and not first['revisions']
    append(f,line('turn_context',dict(turn_id='new',cwd='/work')))
    append(f,line('response_item',dict(type='message',role='user',content=[dict(type='input_text',text='Now scoped.')])))
    assert capture(b,e)['capture_complete']
