"""Quoted selection retains attribution and collapses exact overlapping evidence."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from portable_capture import selected_decision, codex_sources


def sources():
    return [dict(id='human',channel='human_message',content='Tavi reported meeting Jo; year unknown.',originating_body='fixture:desk',received_at='2026-10-13',status='new'),
            dict(id='tool',channel='tool_response',content='authentication_failed; delivered=false',originating_body='fixture:desk',received_at='2026-10-13',status='new')]


def candidate():
    return dict(outcome='applied',reason='Significant failed outreach',records=[
        dict(key='episode',operation='add',shelf='episodes',title='authentication_failed',source_ids=['human','tool']),
        dict(key='person',operation='add',shelf='library',title='meeting Jo',source_ids=['human'])],
        links=[dict(source='episode',target='person',link_type='related_to')])


def test_collapse_keeps_all_selected_originals_and_recognition_alias():
    result=selected_decision(candidate(),sources(),[])
    assert len(result['records'])==1 and result['links']==[]
    record=result['records'][0]
    assert record['tags']==['meeting Jo']
    assert 'Human report;' in record['raw'] and 'tool_response;' in record['raw']
    assert all(json.dumps(s['content']) in record['raw'] for s in sources())
    assert 'year unknown' in record['raw']


def test_discarded_duplicate_cannot_hide_fabricated_title_or_prose():
    value=candidate();value['records'][1]['title']='Jo attended with Ilex'
    with pytest.raises(ValueError,match='exact recognition'):selected_decision(value,sources(),[])
    value=candidate();value['records'][1]['raw']='fabrication'
    with pytest.raises(ValueError,match='closed block'):selected_decision(value,sources(),[])


def test_old_context_alone_cannot_become_a_new_episode():
    old=[dict(s,status='earlier_context') for s in sources()]
    with pytest.raises(ValueError,match='genuinely new'):selected_decision(candidate(),old,[])


def test_normalization_preserves_response_sources_but_not_compacted_replay():
    def line(t,p):return (json.dumps(dict(type=t,payload=p))+'\n').encode()
    first=line('response_item',dict(type='message',role='user',content=[dict(type='input_text',text='Tavi reports an encounter.')]))
    now=first+line('compacted',dict(message='I attended'))+line('response_item',dict(type='function_call',call_id='x',name='message_send',arguments='{}'))+line('response_item',dict(type='function_call_output',call_id='x',output='failure'))
    result=codex_sources(now,source='fictional',previous=first)
    assert [r['status'] for r in result['sources']]==['earlier_context','new','new']
    assert not result['unsupported']
    assert all('I attended' not in json.dumps(r) for r in result['sources'])
    with pytest.raises(ValueError,match='incomplete'):codex_sources(now[:-1],source='fictional')


def test_tool_reply_keeps_request_pointer_and_turn_context():
    from portable_capture import block_sources
    def line(t,p):return (json.dumps(dict(type=t,payload=p))+'\n').encode()
    raw=line('response_item',dict(type='message',role='user',content=[dict(type='input_text',text='On 2024-08-03, revisit this issue.')]))
    raw+=line('response_item',dict(type='function_call',call_id='issue',name='repo_issue_read',arguments='{"url":"https://forge.example/issue/37"}'))
    raw+=line('response_item',dict(type='function_call_output',call_id='issue',output='Mira offered a relay proposal.'))
    blocks=block_sources(codex_sources(raw,source='fixture'),'fixture:desk')
    value=dict(outcome='applied',reason='Encounter',records=[dict(key='x',operation='add',shelf='episodes',title='Mira',source_ids=[blocks[-1]['id']])],links=[])
    result=selected_decision(value,blocks,[])
    assert 'https://forge.example/issue/37' in result['records'][0]['raw']
    assert '2024-08-03' in result['records'][0]['raw']


def test_retrieval_is_context_even_when_its_bytes_are_new():
    from portable_capture import block_sources
    def line(p):return (json.dumps(dict(type='response_item',payload=p))+'\n').encode()
    raw=line(dict(type='function_call',call_id='r',name='hmk_recall',arguments='{}'))
    raw+=line(dict(type='function_call_output',call_id='r',output='Existing encounter'))
    blocks=block_sources(codex_sources(raw,source='fixture'),'fixture:desk')
    assert all(s['status']=='earlier_context' for s in blocks)
    value=dict(outcome='applied',reason='Copy',records=[dict(key='x',operation='add',shelf='episodes',title='Existing',source_ids=[blocks[-1]['id']])],links=[])
    with pytest.raises(ValueError,match='retrieved memory'):selected_decision(value,blocks,[])


def test_recall_request_cannot_launder_retrieved_memory_into_an_update():
    blocks=sources()
    blocks[1].update(retrieved_context=True,status='earlier_context')
    value=candidate()
    with pytest.raises(ValueError,match='retrieved memory'):
        selected_decision(value,blocks,[])


def test_retrieval_context_supplies_date_without_becoming_new_experience():
    from portable_capture import block_sources
    def line(p):return (json.dumps(dict(type='response_item',payload=p))+'\n').encode()
    raw=line(dict(type='function_call',call_id='r',name='hmk_recall',arguments='{}'))
    raw+=line(dict(type='function_call_output',call_id='r',output='Earlier memory recorded_at=2024-06-21: Leto proposed it.'))
    raw+=line(dict(type='message',role='user',content=[dict(type='input_text',text='That entry is wrong. Mira proposed it; June 21 was when the incorrect entry was written.')]))
    blocks=block_sources(codex_sources(raw,source='fixture'),'fixture:desk')
    value=dict(outcome='applied',reason='New correction',records=[dict(key='x',operation='add',shelf='episodes',title='That entry is wrong',source_ids=[blocks[-1]['id']])],links=[])
    result=selected_decision(value,blocks,[])
    assert 'retrieved_memory_context;' in result['records'][0]['raw']
    assert '2024-06-21' in result['records'][0]['raw']
    assert len(result['records'])==1
