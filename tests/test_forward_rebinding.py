import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from tests.test_forward_capture import context, append, line, turn
from capture_inbox import Inbox
from codex_hook_capture import capture
from rebind_forward_source import rebind


def relocate(f):
    copy = f.with_suffix('.copy'); copy.write_bytes(f.read_bytes()); copy.replace(f)


def test_rebind_preserves_pending_ranges_pause_and_replay(context):
    b,f,e=context
    append(f,turn('one','Remember the actual failure.')); capture(b,e)
    append(f,turn('two','Still pending.')); relocate(f)
    assert capture(b,e)['error']=='source_changed_during_capture'
    inbox=Inbox(b['inbox'],b)
    with inbox.connect() as c:
        before=c.execute('select value from forward_cursors').fetchone()[0]
        rows=c.execute('select count(*) from revisions').fetchone()[0]
    result=rebind(b,e,reason='Verified host move')
    assert result['rebound'] and result['checked_ranges']==1
    with inbox.connect() as c:
        after=json.loads(c.execute('select value from forward_cursors').fetchone()[0])
        assert {k:v for k,v in after.items() if k not in ('device','inode')}=={k:v for k,v in json.loads(before).items() if k not in ('device','inode')}
        assert c.execute('select count(*) from revisions').fetchone()[0]==rows
    assert not rebind(b,e,reason='Verified host move')['rebound']
    assert capture(b,e)['capture_complete']
    assert capture(b,e)['revisions']==[]


def test_rebind_requires_exact_bytes_for_retained_scope_gap(context):
    b, f, e = context
    append(f, line('event_msg', dict(type='task_started', turn_id='unknown'))
           + line('response_item', dict(type='message', role='user', content=['PRESERVE']))
           + line('event_msg', dict(type='task_complete', turn_id='unknown'))
           + turn('known', 'Later selected source.'))
    assert capture(b, e)['error'] == 'session_scope_unverified'
    relocate(f)
    assert rebind(b, e, reason='Same retained bytes after move')['rebound']
    relocate(f)
    f.write_bytes(f.read_bytes().replace(b'PRESERVE', b'ALTERED!'))
    with pytest.raises(ValueError, match='retained scope gap differs'):
        rebind(b, e, reason='Changed unverified original')


def test_rebind_migrated_baseline_without_opening_pre_activation_history(context):
    b, f, e = context
    offset = f.stat().st_size
    inbox = Inbox(b['inbox'], b)
    with inbox.connect() as con:
        baseline = dict(con.execute('SELECT * FROM forward_baselines').fetchone())
    append(f, line('response_item', dict(type='message', role='user', content=['old trailing bytes'])))
    selected = turn('later', 'Selected after the activation boundary.')
    append(f, selected)
    relocate(f)
    source_ref = hashlib.sha256(e['session_id'].encode()).hexdigest()
    with pytest.raises(ValueError, match='select a retained baseline source'):
        rebind(b, e, reason='Missing explicit baseline selection')
    with pytest.raises(ValueError, match='match the retained attempt'):
        rebind(b, e, reason='Mismatched attempt', baseline_source_ref='0' * 64)
    with pytest.raises(RuntimeError, match='interrupted'):
        def interrupt():
            raise RuntimeError('interrupted')
        rebind(b, e, reason='Verified migration', baseline_source_ref=source_ref, _fault=interrupt)
    proof = rebind(b, e, reason='Verified migration', baseline_source_ref=source_ref)
    assert proof['rebound'] and proof['source_offset'] == offset and proof['checked_ranges'] == 0
    with inbox.connect() as con:
        assert dict(con.execute('SELECT * FROM forward_baselines').fetchone()) == baseline
        assert con.execute('SELECT count(*) FROM revisions').fetchone()[0] == 0
        receipt = json.loads(con.execute('SELECT value FROM forward_rebindings').fetchone()[0])
        assert receipt['activation_baseline'] == baseline
    assert not rebind(b, e, reason='Read back', baseline_source_ref=source_ref)['rebound']
    final = capture(b, e)
    assert final['capture_complete']
    assert inbox.restore(final['revisions'][0]).endswith(selected)
    assert b'old trailing bytes' not in inbox.restore(final['revisions'][0])
    assert b'old story' not in inbox.restore(final['revisions'][0])
    assert capture(b, e)['revisions'] == []


def test_rebind_migrated_baseline_refuses_changed_boundary(context):
    b, f, e = context
    relocate(f)
    raw = f.read_bytes()
    f.write_bytes(raw[:-2]+b'x\n')
    with pytest.raises(ValueError, match='source boundary differs'):
        rebind(b, e, reason='Different baseline guard',
               baseline_source_ref=hashlib.sha256(e['session_id'].encode()).hexdigest())
    with Inbox(b['inbox'], b).connect() as con:
        assert con.execute('SELECT count(*) FROM forward_cursors').fetchone()[0] == 0


@pytest.mark.parametrize('damage',['header','range','boundary','truncate','race'])
def test_rebind_rejects_changed_source_without_cursor_write(context,damage):
    b,f,e=context
    append(f,turn('one','Remember this exact evidence.'));capture(b,e);relocate(f)
    inbox=Inbox(b['inbox'],b)
    with inbox.connect() as c:before=c.execute('select value from forward_cursors').fetchone()[0]
    raw=f.read_bytes()
    if damage=='header':f.write_bytes(raw.replace(b'"cwd": "/old"',b'"cwd": "/bad"'))
    if damage=='range':f.write_bytes(raw.replace(b'Remember',b'Falsify!'))
    if damage=='boundary':f.write_bytes(raw[:-3]+b'x\n')
    if damage=='truncate':f.write_bytes(raw[:100])
    fault=(lambda:append(f,b'\n')) if damage=='race' else None
    with pytest.raises(ValueError):rebind(b,e,reason='Host move',_fault=fault)
    with inbox.connect() as c:assert c.execute('select value from forward_cursors').fetchone()[0]==before
