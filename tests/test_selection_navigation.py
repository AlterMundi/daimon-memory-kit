"""Actual producer navigation, resumed pages and concurrent correction boundaries."""
# ruff: noqa: F811
import json

import pytest

from tests.test_portable_producer import setup  # noqa: F401
from portable_producer import process_once


def lookup(action='search', query='Jo clamp', uid='', offset=0, revision=0):
    return {'selection':{'outcome':'lookup','requests':[dict(action=action,query=query,
        record_uid=uid,offset=offset,expected_revision=revision)]}}


def correcting_selector(cid, uid, calls):
    def propose(request, directory):
        calls.append(request)
        supplied = json.loads(request['messages'][1]['content'])
        observed = [json.loads(m['content'])['lookup_results'][0] for m in request['messages'][2:] if m['role']=='user']
        if not observed:
            assert supplied['current_canon'] == []
            return lookup()
        if observed[-1].get('navigation_only'):
            assert any(r['record_uid']==uid for r in observed[-1]['items'])
            return lookup('read','',uid,revision=1)
        if observed[-1].get('next_offset') is not None:
            assert supplied['current_canon'] == []
            return lookup('read','',uid,observed[-1]['next_offset'],1)
        assert supplied['current_canon'][0]['record_uid'] == uid
        return {'selection':dict(outcome='applied',reason='New attributed detail',records=[
            dict(key='jo',operation='update',chapter_id=cid,expected_revision=1,title='Jo',
                 source_ids=[f'memory:{cid}', supplied['sources'][0]['id']])],links=[])}
    return propose


def test_large_pool_uses_focused_navigation_and_resumes_without_repeating_calls(setup):
    memory,inbox,state,_,binding,_,_=setup
    for index in range(260):
        memory.add_text('library',f'Routine {index}',f'Unrelated routine {index}.')
    cid = memory.add_text('episodes','Jo','Jo discussed an instrument fixture. ' + 'Observed. '*1800 + '\nOutcome remained unknown.')
    uid = memory._read_chapter(cid)['record_uid']
    calls=[]
    propose=correcting_selector(cid,uid,calls)
    first = process_once(memory,inbox,state,propose,binding,navigation_steps=1,retrieval='lexical')
    assert first['state']=='pending' and len(calls)==1
    assert not (state/'index.json').exists()
    # Bounded dispatches leave pages pending, not an ever-larger corpus prompt.
    for _ in range(15):
        result=process_once(memory,inbox,state,propose,binding,navigation_steps=1,retrieval='lexical')
        if result['state']=='complete':
            break
    assert result['state']=='complete'
    assert len(calls) == len(list((state).glob('batch-1-dispatch-*/navigation-*')))
    assert 'Unrelated routine' not in json.dumps(calls)
    current=memory._read_chapter(cid)
    assert current['revision']==2 and 'Outcome remained unknown.' in current['raw']
    assert 'June 3' in current['raw']
    assert memory.history(cid)[0]['revision']==1
    assert process_once(memory,inbox,state,propose,binding,retrieval='lexical')['state']=='idle'
    with memory.connect() as con:
        assert con.execute('select count(*) from chapters').fetchone()[0] == 261


def test_lookup_success_survives_provider_failure_on_next_request(setup):
    memory,inbox,state,_,binding,_,_=setup
    cid=memory.add_text('episodes','Jo','Jo discussed a clamp.')
    uid=memory._read_chapter(cid)['record_uid']
    calls=[]
    propose=correcting_selector(cid,uid,calls)
    def fail_after_search(request,directory):
        if len(calls)==1:
            raise ConnectionError('temporary provider outage')
        return propose(request,directory)
    with pytest.raises(ConnectionError):
        process_once(memory,inbox,state,fail_after_search,binding,retrieval='lexical')
    assert len(calls)==1
    result=process_once(memory,inbox,state,propose,binding,retrieval='lexical')
    assert result['state']=='complete' and len(calls)==3


def test_unread_update_and_changed_evidence_never_overwrite_memory(setup):
    memory,inbox,state,_,binding,_,_=setup
    cid=memory.add_text('episodes','Jo','Jo discussed a clamp.')
    uid=memory._read_chapter(cid)['record_uid']
    calls=[]
    propose=correcting_selector(cid,uid,calls)
    def concurrent(request,directory):
        result=propose(request,directory)
        if result['selection']['outcome']=='applied':
            memory.update_chapter(cid,content='Jo corrected the outcome: delivery failed.',expected_revision=1)
        return result
    with pytest.raises(ValueError,match='evidence changed'):
        process_once(memory,inbox,state,concurrent,binding,retrieval='lexical')
    assert memory._read_chapter(cid)['raw']=='Jo corrected the outcome: delivery failed.'
    assert not (state/'index.json').exists()
    import portable_capture
    with pytest.raises(ValueError,match='completely read'):
        portable_capture.selected_decision(dict(outcome='applied',reason='Unsafe',records=[
            dict(key='jo',operation='update',chapter_id=cid,expected_revision=2,title='Jo',source_ids=['s'])],links=[]),
            [{'id':'s','content':'Jo reported something','status':'new'}],[])


def test_stable_reference_preserves_correction_and_coalesces_redundant_new_episode(setup):
    memory,_,_,_,_,_,_=setup
    import portable_capture
    cid=memory.add_text('episodes','Jo','Jo reported delivery success.')
    original=memory._read_chapter(cid)
    source=dict(id='new',content='Jo corrected it: delivery failed.',status='new',originating_body='fixture:body')
    proposal=dict(outcome='applied',reason='Correction',records=[
        dict(key='update',operation='update',chapter_id=cid,expected_revision=1,title='Jo',
            source_ids=['memory:'+original['record_uid'],'new']),
        dict(key='duplicate',operation='add',shelf='episodes',title='delivery failed',source_ids=['new'])],
        links=[dict(source='duplicate',target='update',link_type='corrects')])
    decision=portable_capture.selected_decision(proposal,[source],[original])
    assert len(decision['records'])==1 and decision['records'][0]['operation']=='update'
    assert 'delivery failed' in decision['records'][0]['tags']
    assert 'delivery success' in decision['records'][0]['raw'] and 'delivery failed' in decision['records'][0]['raw']
    assert decision['links']==[]
    proposal['records'][0]['source_ids'][0]='memory:external-unread-uid'
    with pytest.raises(ValueError,match='supplied'):
        portable_capture.selected_decision(proposal,[source],[original])
