"""Regressions from real title-collision and opaque native-source stalls."""
import json
from pathlib import Path

import pytest
# ruff: noqa: F811
from tests.test_portable_producer import setup  # noqa: F401
import portable_producer as producer
import selection_navigation
from portable_capture import codex_sources, block_sources, selected_decision


def test_title_collision_requires_current_read_not_silent_duplicate(setup):
    memory,inbox,state,propose,binding,calls,_=setup
    memory.add_text('episodes','Jo','Jo previously discussed clamps.')
    result=producer.process_once(memory,inbox,state,propose,binding,retrieval='lexical')
    assert result['state']=='pending' and 'two corrections' in result['reason']
    job=json.loads((state/'batch-1.json').read_text())
    assert job['title_conflicts'][0]['title']=='Jo'
    assert len(calls)==3
    assert 'do not rename' in json.dumps(calls).lower()
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==1
        if c.execute("select 1 from sqlite_master where name='capture_events'").fetchone():
            assert c.execute('select count(*) from capture_events').fetchone()[0]==0


def test_failed_legacy_title_reopens_same_event_and_preserves_sources(setup,monkeypatch):
    memory,inbox,state,propose,binding,_,_=setup
    memory.add_text('episodes','Jo','Jo previously discussed clamps.')
    # Old selector did not check title collisions until the ledger write.
    with monkeypatch.context() as m:
        m.setattr(selection_navigation,'title_conflicts',lambda *a:[])
        result=producer.process_once(memory,inbox,state,propose,binding,retrieval='lexical')
    assert result['state']=='pending'
    job=json.loads((state/'batch-1.json').read_text())
    # Qualify actual legacy generic reason, without relaxing the failed-event gate.
    with memory.connect() as c:
        c.execute("update capture_events set reason='ValueError'")
    receipt=producer.reconcile_failed_title(memory,inbox,state)
    assert Path(receipt['preserved_job']).is_file()
    assert json.loads(Path(receipt['preserved_job']).read_text())==job
    assert receipt['model_calls']==0 and not receipt['cursor_advanced']
    def omit(request,path):
        assert json.loads(request['messages'][1]['content'])['title_conflicts']
        return {'selection':dict(outcome='omitted',reason='This fixture provides no new learning.',records=[],links=[])}
    result=producer.process_once(memory,inbox,state,omit,binding,retrieval='lexical')
    assert result['state']=='complete'
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==1
        assert c.execute('select count(*) from capture_events').fetchone()[0]==1
        assert c.execute('select state from capture_events').fetchone()[0]=='omitted'
    assert producer.process_once(memory,inbox,state,omit,binding,retrieval='lexical')['state']=='idle'


def test_failed_recovery_refuses_uncertain_or_committed_event(setup,monkeypatch):
    memory,inbox,state,propose,binding,_,_=setup
    def crash(at):
        if at=='after_stage':
            raise RuntimeError('crash')
    with pytest.raises(RuntimeError):
        producer.process_once(memory,inbox,state,propose,binding,_fault=crash)
    memory.add_text('episodes','Jo','Concurrent older material')
    with pytest.raises(ValueError,match='exact failed'):
        producer.reconcile_failed_title(memory,inbox,state)


def test_mixed_native_content_preserves_attribution_bytes_and_unknowns():
    payloads=[dict(type='message',role='user',content=[dict(type='input_text',text='Mira sent this drawing; interpretation pending.'),
        dict(type='input_image',image_url='data:image/png;base64,PRIVATE_IMAGE')]),
        dict(type='agent_message',author='local-worker',recipient='parent',content=[dict(type='input_text',text='Proposal only; no successful test.'),dict(type='encrypted_content',encrypted_content='PRIVATE_CIPHERTEXT')])]
    raw=b''.join((json.dumps(dict(type='response_item',payload=p))+'\n').encode() for p in payloads)
    normalized=codex_sources(raw,source='fictional')
    assert normalized['unsupported']==[]
    assert [i['payload'] for i in normalized['sources']]==payloads
    blocks=block_sources(normalized,'fixture:desk')
    text=json.dumps(blocks)
    assert 'PRIVATE_IMAGE' not in text and 'PRIVATE_CIPHERTEXT' not in text
    assert 'semantic content not interpreted' in text
    assert blocks[1]['channel']=='attributed_agent_message'
    assert 'local-worker' in blocks[1]['content'] and 'not signed being identity' in blocks[1]['content']
    selected=selected_decision(dict(outcome='applied',reason='Retain attributed proposal',records=[dict(key='m',operation='add',shelf='episodes',title='Proposal only',source_ids=[blocks[1]['id']])],links=[]),blocks,[])
    assert 'Opaque source part' in selected['records'][0]['raw']
    assert codex_sources(raw,source='fictional',previous=raw)['sources'][0]['status']=='earlier_context'


def test_unknown_native_content_still_blocks_and_recall_alias_is_context():
    raw=(json.dumps(dict(type='response_item',payload=dict(type='message',role='user',content=[dict(type='future_kind')])) )+'\n').encode()
    assert codex_sources(raw,source='fixture')['unsupported']
    for alias in ['dmk_recall','mcp__hmk__dmk_recall','hmk_recall']:
        raw=(json.dumps(dict(type='response_item',payload=dict(type='function_call',call_id='r',name=alias,arguments='{}')))+'\n').encode()
        assert codex_sources(raw,source='fixture')['sources'][0]['status']=='earlier_context'
