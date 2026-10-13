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
    pending=process_once(memory,inbox,state,concurrent,binding,retrieval='lexical')
    assert pending['state']=='pending' and 'context changed' in pending['reason']
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


def test_invalid_final_selection_gets_bounded_feedback_and_survives_resume(setup):
    memory,inbox,state,valid,binding,calls,_=setup
    def first_invalid(request,directory):
        result=valid(request,directory)
        result['selection']['records'][0]['memory']='unsupported-field'
        return result
    pending=process_once(memory,inbox,state,first_invalid,binding,navigation_steps=1,retrieval='lexical')
    assert pending['state']=='pending' and len(calls)==1
    assert not (state/'index.json').exists()
    def repaired(request,directory):
        feedback=json.loads(request['messages'][-1]['content'])
        assert 'unsupported fields: memory' in feedback['selection_error']
        return valid(request,directory)
    assert process_once(memory,inbox,state,repaired,binding,retrieval='lexical')['state']=='complete'
    job=json.loads((state/'batch-1.json').read_text())
    assert job['navigation']['steps'][0]['proposal']['selection']['records'][0]['memory']=='unsupported-field'
    assert len(calls)==2
    assert process_once(memory,inbox,state,repaired,binding,retrieval='lexical')['state']=='idle'


def test_invalid_selection_cannot_restart_its_correction_budget_each_invocation(setup):
    memory,inbox,state,_,binding,_,_=setup
    calls=[]
    def invalid(request,directory):
        calls.append(request)
        return {'selection':{'outcome':'applied','reason':'Invalid shape','records':[{}],'links':[]}}
    pending=process_once(memory,inbox,state,invalid,binding,retrieval='lexical')
    assert pending['state']=='pending' and 'two corrections' in pending['reason']
    assert len(calls)==3
    assert process_once(memory,inbox,state,invalid,binding,retrieval='lexical')['proposer_invoked'] is False
    assert len(calls)==3 and not (state/'index.json').exists()


def test_explicit_pre_stage_upgrade_reuses_saved_lookup_and_invalid_proposal(setup):
    from portable_producer import reprepare_pending
    memory,inbox,state,valid,binding,calls,_=setup
    def invalid(request,directory):
        result=valid(request,directory)
        result['selection']['records'][0]['memory']='unsupported'
        return result
    process_once(memory,inbox,state,invalid,binding,navigation_steps=1,retrieval='lexical')
    path=state/'batch-1.json'
    job=json.loads(path.read_text())
    # An earlier producer saved the final proposal and stopped before feedback.
    job['navigation']['steps'][-1].pop('feedback')
    job['proposal']=job['navigation']['steps'][-1]['proposal']
    job['code_hash']='earlier-implementation'
    path.write_text(json.dumps(job))
    with pytest.raises(ValueError,match='code/binding changed'):
        process_once(memory,inbox,state,valid,binding,retrieval='lexical')
    receipt=reprepare_pending(memory,inbox,state,'Adopt structural feedback',preserve_navigation=True)
    archived=json.loads(__import__('pathlib').Path(receipt['preserved_job']).read_text())
    assert archived['proposal']==job['proposal']
    def repair(request,directory):
        assert 'unsupported fields: memory' in json.loads(request['messages'][-1]['content'])['selection_error']
        return valid(request,directory)
    assert process_once(memory,inbox,state,repair,binding,retrieval='lexical')['state']=='complete'
    assert len(calls)==2


@pytest.mark.parametrize('crash_point',['before_stage','after_canon_commit'])
def test_revision_conflict_reconciles_same_event_and_preserves_attempts(setup, crash_point):
    memory,inbox,state,_,binding,_,_=setup
    cid=memory.add_text('episodes','Jo','Jo discussed a clamp.')
    uid=memory._read_chapter(cid)['record_uid']
    original_calls=[]
    original=correcting_selector(cid,uid,original_calls)
    def concurrent(request,directory):
        result=original(request,directory)
        if result['selection']['outcome']=='applied':
            memory.update_chapter(cid,content='Jo corrected the outcome: delivery failed.',expected_revision=1)
        return result
    first=process_once(memory,inbox,state,concurrent,binding,retrieval='lexical')
    assert first['state']=='pending'
    fresh_calls=[]
    def refreshed(request,directory):
        fresh_calls.append(request)
        supplied=json.loads(request['messages'][1]['content'])
        assert 'context_refresh' in supplied
        if not supplied['current_canon']:
            return lookup('read','',uid,revision=2)
        assert supplied['current_canon'][0]['revision']==2
        return {'selection':dict(outcome='applied',reason='Retain concurrent correction and new detail',records=[
            dict(key='jo',operation='update',chapter_id=cid,expected_revision=2,title='Jo',
                 source_ids=[f'memory:{cid}',supplied['sources'][0]['id']])],links=[])}
    def crash(at):
        if at==crash_point:
            raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError,match='interrupted'):
        process_once(memory,inbox,state,refreshed,binding,retrieval='lexical',_fault=crash)
    assert len(fresh_calls)==2
    final=process_once(memory,inbox,state,refreshed,binding,retrieval='lexical')
    assert final['state']=='complete' and not final['proposer_invoked']
    assert len(fresh_calls)==2
    current=memory._read_chapter(cid)
    assert current['revision']==3 and 'delivery failed' in current['raw'] and 'June 3' in current['raw']
    assert len(memory.history(cid))==2
    with memory.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM capture_events').fetchone()[0]==1
        row=con.execute('SELECT event_key,state FROM capture_events').fetchone()
        assert row['event_key']==first['event_key'] and row['state']=='applied'
    from codex_projection import load_learning
    originals=load_learning(memory,final['artifact_id'])
    attempts=json.loads(originals['prior-attempts.json'])
    assert len(attempts)==1
    assert attempts[0]['proposal']['selection']['records'][0]['expected_revision']==1
    assert json.loads(current['source_metadata_json'])['evidence']==['artifact:sha256:'+final['artifact_id']]
