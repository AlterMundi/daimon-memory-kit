import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from tests.test_forward_capture import context, append, turn
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
