"""Source loss, uncertain commits and concurrent capture must not destroy evidence."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from capture_inbox import Inbox
from codex_hook_capture import capture


@pytest.fixture
def bound(tmp_path):
    root = tmp_path/'sources';root.mkdir()
    binding = dict(schema='hmk.codex-hook-binding/v1', subject='fixture:ilex',
        source_instance='fixture:desk', source_root=str(root), allowed_cwds=['/work'],
        inbox=str(tmp_path/'inbox.sqlite'), max_source_bytes=1048576)
    source = root/'session.jsonl'
    source.write_text(json.dumps({'type':'session_meta','payload':{'id':'session-a'}})+'\n')
    payload = dict(hook_event_name='Stop', session_id='session-a', turn_id='turn-a',
                   cwd='/work', transcript_path=str(source), last_assistant_message='failed')
    return binding, source, payload


def test_append_replay_and_source_loss_restore_exact_bytes(bound):
    b, source, event = bound
    first = capture(b,event)
    original = source.read_bytes()
    source.write_bytes(original+b'{"failure":"authentication_failed"}\n')
    second = capture(b,event)
    replay = capture(b,event)
    assert second['event_key'] == replay['event_key']
    inbox=Inbox(b['inbox'],b)
    source.unlink()
    assert inbox.restore(first['revision']) == original
    assert inbox.restore(second['revision']) == original+b'{"failure":"authentication_failed"}\n'
    with inbox.connect() as c:
        assert c.execute('select length(delta) from revisions where id=?',(second['revision'],)).fetchone()[0] == len(b'{"failure":"authentication_failed"}\n')
    missing=capture(b,event)
    assert not missing['capture_complete'] and missing['error']=='transcript_missing'
    assert len(inbox.observations())==3


@pytest.mark.parametrize('point',['before_commit','after_commit'])
def test_interruption_recovery_is_idempotent(bound,point):
    b,source,event=bound
    def crash(at):
        if at==point:raise RuntimeError('interruption')
    with pytest.raises(RuntimeError):capture(b,event,_fault=crash)
    receipt=capture(b,event)
    inbox=Inbox(b['inbox'],b)
    assert len(inbox.observations())==1
    assert inbox.restore(receipt['revision'])==source.read_bytes()


def test_concurrent_duplicate_hooks_and_distinct_sessions(bound):
    b,source,event=bound
    Inbox(b['inbox'],b)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:capture(b,event),range(8)))
    assert len({r['event_key'] for r in results})==1
    other=source.with_name('other.jsonl')
    other.write_text(json.dumps({'type':'session_meta','payload':{'id':'session-b'}})+'\n')
    capture(b,{**event,'session_id':'session-b','transcript_path':str(other)})
    assert len(Inbox(b['inbox'],b).observations())==2


def test_rewrite_and_reversion_preserve_available_history(bound):
    b,source,event=bound
    original=source.read_bytes()
    first=capture(b,event)
    source.write_bytes(original+b'{"proposal":"initial"}\n')
    second=capture(b,event)
    source.write_bytes(original+b'{"proposal":"corrected"}\n')
    corrected=capture(b,event)
    source.write_bytes(original)
    reverted=capture(b,event)
    inbox=Inbox(b['inbox'],b)
    assert len({x['revision'] for x in (first,second,corrected,reverted)})==4
    assert b'initial' in inbox.restore(second['revision'])
    assert b'corrected' in inbox.restore(corrected['revision'])
    assert inbox.restore(reverted['revision'])==original


def test_missing_transcript_preserves_prompt_without_claiming_capture(bound):
    b,_,event=bound
    receipt=capture(b,{**event,'hook_event_name':'UserPromptSubmit','transcript_path':None,'prompt':'a meaningful human report'})
    inbox=Inbox(b['inbox'],b)
    assert not receipt['capture_complete']
    assert json.loads(inbox.observations()[0]['payload'])['prompt']=='a meaningful human report'


def test_over_limit_defers_without_truncating_or_advancing_source(bound):
    b,source,event=bound
    b={**b,'max_source_bytes':50}
    receipt=capture(b,event)
    assert not receipt['capture_complete'] and receipt['revision'] is None
    with Inbox(b['inbox'],b).connect() as c:
        assert c.execute('select count(*) from heads').fetchone()[0]==0


def test_altered_or_lost_dependency_is_detected(bound):
    b,source,event=bound
    r=capture(b,event)
    inbox=Inbox(b['inbox'],b)
    with inbox.connect() as c:c.execute('update revisions set delta=?',(b'corruption',))
    with pytest.raises(ValueError,match='altered'):inbox.restore(r['revision'])


def test_scope_session_and_binding_mismatch_do_not_redirect_capture(bound,tmp_path):
    b,source,event=bound
    capture(b,event)
    with pytest.raises(ValueError,match='binding differs'):capture({**b,'subject':'fixture:other'},event)
    with pytest.raises(ValueError,match='session differs'):capture(b,{**event,'session_id':'other'})
    with pytest.raises(ValueError,match='working directory'):capture(b,{**event,'cwd':'/private'})
    outside=tmp_path/'outside.jsonl';outside.write_bytes(source.read_bytes())
    with pytest.raises(ValueError,match='outside selected'):capture(b,{**event,'transcript_path':str(outside)})
    assert len(Inbox(b['inbox'],b).observations())==1


@pytest.mark.parametrize('created,expected', [
    ('2026-10-12T23:59:59Z', 'old'),
    ('2026-10-13T00:00:00Z', 'accepted'),
    ('2026-10-12T21:00:00-03:00', 'accepted'),
    ('2026-10-13T00:00:00', 'unverified'),
    (None, 'unverified'),
])
def test_forward_only_scope_uses_session_creation_not_hook_time(bound,created,expected):
    binding,source,event=bound
    binding.update(schema='hmk.codex-hook-binding/v2',
                   sessions_started_at_or_after='2026-10-13T00:00:00Z')
    source.write_text(json.dumps(dict(type='session_meta',
        payload=dict(id='session-a',timestamp=created,cwd='/work')))+'\n')
    event['timestamp']='2026-11-01T00:00:00Z'
    receipt=capture(binding,event)
    if expected=='accepted':
        assert receipt['capture_complete']
        assert Inbox(binding['inbox'],binding).restore(receipt['revision'])==source.read_bytes()
    else:
        assert not receipt['capture_complete']
        assert not Path(binding['inbox']).exists()
        if expected=='old':
            assert receipt['skipped'] and receipt['reason']=='session_precedes_selected_boundary'
        else:
            assert receipt['error']=='session_scope_unverified'


def test_scoped_unselected_or_unverifiable_event_does_not_journal_payload(bound):
    binding,source,event=bound
    binding.update(schema='hmk.codex-hook-binding/v2',
                   sessions_started_at_or_after='2026-10-13T00:00:00Z')
    assert capture(binding,{**event,'cwd':'/private'})['skipped']
    source.write_text(json.dumps(dict(type='session_meta',payload=dict(
        id='session-a',cwd='/private',timestamp='2026-10-14T00:00:00Z')))+'\n')
    assert capture(binding,event)['reason']=='unselected_session_working_directory'
    source.unlink()
    result=capture(binding,event)
    assert result['error']=='transcript_missing' and not result['scope_verified']
    assert not Path(binding['inbox']).exists()


@pytest.mark.parametrize('cwd,created,reason', [
    ('/private', '2026-10-14T00:00:00Z', 'unselected_session_working_directory'),
    ('/work', '2026-10-12T00:00:00Z', 'session_precedes_selected_boundary'),
    ('/work', '2026-10-14T00:00:00Z', 'source_exceeds_capture_limit'),
])
def test_oversized_session_checks_verified_scope_before_size(bound, cwd, created, reason):
    binding, source, event = bound
    binding.update(schema='hmk.codex-hook-binding/v2', max_source_bytes=4096,
                   sessions_started_at_or_after='2026-10-13T00:00:00Z')
    header = json.dumps(dict(type='session_meta', payload=dict(
        id=event['session_id'], cwd=cwd, timestamp=created))).encode() + b'\n'
    with source.open('wb') as stream:
        stream.write(header)
        stream.truncate(65 * 1024 * 1024)
    result = capture(binding, event)
    assert not result['capture_complete']
    assert result.get('reason', result.get('error')) == reason
    assert bool(result.get('skipped')) == (reason != 'source_exceeds_capture_limit')
    assert not Path(binding['inbox']).exists()
    assert source.stat().st_size == 65 * 1024 * 1024


def test_oversized_exclusion_does_not_accept_mismatched_or_unbounded_header(bound):
    binding, source, event = bound
    binding.update(schema='hmk.codex-hook-binding/v2', max_source_bytes=4096,
                   sessions_started_at_or_after='2026-10-13T00:00:00Z')
    source.write_text(json.dumps(dict(type='session_meta',payload=dict(
        id='different-session',cwd='/private',timestamp='2026-10-12T00:00:00Z')))+'\n'+'x'*8192)
    with pytest.raises(ValueError, match='session differs'):
        capture(binding,event)
    source.write_bytes(b'x'*8192)
    result=capture(binding,event)
    assert result['error']=='source_header_incomplete' and not result.get('skipped')
    assert not Path(binding['inbox']).exists()
