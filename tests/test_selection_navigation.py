"""Actual producer navigation, resumed pages and concurrent correction boundaries."""
# ruff: noqa: F811
import json

import pytest

from tests.test_portable_producer import setup  # noqa: F401
from portable_producer import process_once


def lookup(action='search', query='Jo clamp', uid='', offset=0, revision=0):
    return {'selection':{'outcome':'lookup','requests':[dict(action=action,query=query,
        record_uid=uid,offset=offset,expected_revision=revision)]}}


def test_navigation_uses_launchers_backend_not_import_time_provider(setup,monkeypatch):
    import memory_navigation
    import deep_recall
    memory,inbox,state,_,binding,_,_=setup
    assert memory is not deep_recall.memory
    observed=[]
    def search(backend,query,**kwargs):
        observed.append(backend)
        assert backend is memory
        return dict(items=[],historical_matches=[],retrieval_status='ok',backend_errors=[],coverage='fixture')
    monkeypatch.setattr(memory_navigation,'search',search)
    calls=[]
    def propose(request,directory):
        calls.append(request)
        return lookup() if len(calls)==1 else {'selection':dict(outcome='omitted',reason='Fixture',records=[],links=[])}
    assert process_once(memory,inbox,state,propose,binding)['state']=='complete'
    assert observed==[memory]


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


def test_large_lookup_journal_uses_complete_source_and_canonical_evidence(monkeypatch):
    import portable_capture
    import selection_navigation

    monkeypatch.setattr(selection_navigation, 'MAX_SELECTION_CONTEXT_BYTES', 20_000)
    step = dict(proposal=lookup(), results=[dict(status='ok', raw='x' * 30_000)])
    original = dict(record_uid='read', revision=1, raw='Complete original.')
    inputs = dict(sources=[dict(id='source', text='Selected source.')], context={})
    job = dict(inputs=inputs, navigation=dict(canon=[original], steps=[step]))
    request = selection_navigation.request_for(job)
    assert request['response_schema'] == portable_capture.block_schema()
    payload = json.loads(request['messages'][1]['content'])
    assert payload['sources'] == inputs['sources']
    assert payload['current_canon'] == [original]
    assert step['results'][0]['raw'] == 'x' * 30_000


def test_reprepare_only_rejected_step_and_keep_its_exact_request(setup):
    from pathlib import Path
    from capturectl import digest
    from portable_producer import reprepare_pending

    memory,inbox,state,valid,binding,_,_=setup

    def refuse(request, work):
        wire_request = dict(request, phase='capture')
        key = digest(wire_request)
        for dirname, payload in (
            ('requests', wire_request),
            ('dispatches', dict(request_sha256=key, state='failed', provider_reservation=True,
                 native_failure=dict(code='admission_refused', stage='bounded_turn_start', rpc_code=-32602))),
        ):
            (work/dirname).mkdir(exist_ok=True)
            (work/dirname/(key+'.json')).write_text(json.dumps(payload))
        raise ValueError('simulated native refusal')

    with pytest.raises(ValueError,match='simulated native refusal'):
        process_once(memory,inbox,state,refuse,binding,retrieval='lexical')
    path = state/'batch-1.json'
    original = json.loads(path.read_text())
    request_path, = state.glob('batch-1-dispatch-*/navigation-1/requests/*.json')
    arguments = dict(preserve_navigation=True, refused_navigation_request=request_path)
    with pytest.raises(ValueError,match='before any provider reservation'):
        reprepare_pending(memory,inbox,state,'Shorten verified refusal',**arguments)
    assert json.loads(path.read_text()) == original

    receipt_path = request_path.parent.parent/'dispatches'/request_path.name
    failed = json.loads(receipt_path.read_text())
    failed.pop('provider_reservation')
    receipt_path.write_text(json.dumps(failed))
    result = reprepare_pending(memory,inbox,state,'Shorten verified refusal',**arguments)
    assert json.loads(Path(result['preserved_job']).read_text()) == original
    assert json.loads(receipt_path.read_text()) == failed
    assert json.loads(path.read_text())['inputs'] == original['inputs']
    assert process_once(memory,inbox,state,valid,binding,retrieval='lexical')['state']=='complete'


def test_reprepare_local_native_renderer_refusal_with_no_attempt(setup):
    from pathlib import Path
    from capturectl import digest
    from portable_capture import block_schema
    from portable_producer import reprepare_pending

    memory, inbox, state, valid, binding, _, _ = setup

    def stop(request, work):
        raise ValueError('stop before locally preparing invalid render')

    with pytest.raises(ValueError, match='stop before'):
        process_once(memory, inbox, state, stop, binding, retrieval='lexical')
    path = state/'batch-1.json'
    job = json.loads(path.read_text())
    step = job['navigation']['steps'][0]
    step['request']['response_schema'] = block_schema()
    work, = state.glob('batch-1-dispatch-*/navigation-1')
    requests = work/'requests'
    requests.mkdir()

    def save_fixture():
        path.write_text(json.dumps(job))
        request = dict(step['request'], format='hmk-fictional-bounded-memory-operation/v1')
        file = requests/(digest(request)+'.json')
        file.write_text(json.dumps(request))
        return file

    args = dict(preserve_navigation=True, refused_navigation_request=save_fixture())
    with pytest.raises(ValueError, match='absent receipt alone'):
        reprepare_pending(memory, inbox, state, 'Verify local renderer refusal', **args)

    step['request']['messages'].append(dict(role='user', content='Consecutive user turn'))
    args['refused_navigation_request'] = save_fixture()
    result = reprepare_pending(memory, inbox, state, 'Verify local renderer refusal', **args)
    assert json.loads(Path(result['preserved_job']).read_text()) == job
    assert args['refused_navigation_request'].exists()
    new = json.loads(path.read_text())['navigation']['steps'][0]['request']
    assert [message['role'] for message in new['messages']] == ['system', 'user']
    assert process_once(memory, inbox, state, valid, binding, retrieval='lexical')['state'] == 'complete'
