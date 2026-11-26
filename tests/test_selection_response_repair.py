"""Explicit malformed-output repair retains dispatch/source history and authority."""
# ruff: noqa: F811
import json

import pytest
from tests.test_portable_producer import setup  # noqa: F401
from tests.test_memory_runtime import configuration
from codex_coordinator import checkpoint
from capturectl import digest
from provider_status import ProviderProblem
from portable_producer import process_once
from repair_selection_response import repair


def retained_failure(setup,tmp_path):
    memory,inbox,state,_,binding,_,_=setup
    value=configuration(tmp_path,memory,inbox,state,binding)
    paths=[]
    def malformed(request,directory):
        key=digest(request);path=directory/'requests'/f'{key}.json'
        checkpoint(path,request)
        checkpoint(directory/'dispatches'/path.name,dict(request_sha256=key,state='completed',
            finish_reason='stop',tool_calls_observed=False,content='<DSML>not JSON</DSML>'))
        paths.append(path)
        raise ProviderProblem('deepseek',key,{'code':'response_incomplete'})
    assert process_once(memory,inbox,state,malformed,binding,retrieval='lexical')['state']=='pending'
    return value,paths[0]


def test_explicit_repair_replays_once_then_original_validation_resumes(setup,tmp_path):
    value,path=retained_failure(setup,tmp_path)
    before=path.read_bytes()
    calls=[]
    def native(request,directory):
        calls.append(request)
        assert request['phase']=='consolidation_review'
        assert request['messages'][:-2]==json.loads(before)['messages']
        assert request['messages'][-2]['content']=='<DSML>not JSON</DSML>'
        return dict(selection=dict(outcome='omitted',reason='No durable change in fixture.',records=[],links=[]),dispatch=dict(provider='native-fixture'))
    first=repair(value,path,'Completed malformed text; one native repair.',models=native)
    assert first['state']=='repaired_for_validation' and not first['cursor_advanced']
    assert repair(value,path,'Completed malformed text; one native repair.',models=native)['state']=='replayed'
    assert len(calls)==1 and path.read_bytes()==before
    def forbidden(*a):raise AssertionError('repaired response must be reused')
    memory,inbox,state,_,binding,_,_=setup
    result=process_once(memory,inbox,state,forbidden,binding,retrieval='lexical')
    assert result['state']=='complete' and result['receipt']['state']=='omitted'
    assert list(path.parent.parent.glob('semantic-repair-*/job-before.json'))
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==0
        assert c.execute('select count(*) from capture_events').fetchone()[0]==1


@pytest.mark.parametrize('change',[{'state':'started'},{'tool_calls_observed':True},{'content':'{}'},{'finish_reason':'length'}])
def test_uncertain_tool_or_valid_completion_cannot_be_repaired(setup,tmp_path,change):
    value,path=retained_failure(setup,tmp_path)
    receipt=path.parent.parent/'dispatches'/path.name;d=json.loads(receipt.read_text());d.update(change);checkpoint(receipt,d)
    with pytest.raises(ValueError):repair(value,path,'Not eligible.',models=lambda *a:pytest.fail('must not dispatch'))


def test_foreign_request_and_changed_source_are_refused(setup,tmp_path):
    value,path=retained_failure(setup,tmp_path)
    with pytest.raises(ValueError,match='retained receiving'):
        repair(value,tmp_path/'foreign.json','No.',models=lambda *a:pytest.fail('must not dispatch'))
    with setup[1].connect() as c:c.execute("update revisions set delta=?",(b'changed',))
    with pytest.raises(ValueError,match='altered'):
        repair(value,path,'No.',models=lambda *a:pytest.fail('must not dispatch'))


def test_completed_framing_repair_removes_only_the_premature_close():
    from repair_selection_response import remove_early_close

    text = '{"outcome":"applied","reason":"keep } in text"}, "records": [{"title":"one"}],"links":[]}'
    assert remove_early_close(text) == {
        'outcome':'applied','reason':'keep } in text','records':[{'title':'one'}],'links':[],
    }
    with pytest.raises(ValueError):
        remove_early_close('{"outcome":"applied","reason":"a"}, "records": [],"links":[],"reason":"changed"}')
    with pytest.raises(ValueError):
        remove_early_close('{"outcome":"applied","reason":"a"}, "records": []')

@pytest.mark.parametrize('failure', [
    {'native_failure': {'code': 'terminal_failure'}},
    {'error_type': 'TimeoutError'},
])
def test_local_decision_resolves_source_work_without_resending_the_reserved_attempt(setup, tmp_path, failure):
    memory, inbox, state, _, binding, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, binding)
    paths = []

    def uncertain(request, directory):
        stored = dict(request, format='hmk-fictional-bounded-memory-operation/v1')
        key = digest(stored)
        request_path = directory/'requests'/f'{key}.json'
        receipt_path = directory/'dispatches'/request_path.name
        checkpoint(request_path, stored)
        checkpoint(receipt_path, dict(request_sha256=key, state='failed',
            provider_reservation=dict(ordinal=1), **failure))
        paths.extend([request_path, receipt_path])
        raise ProviderProblem('openai-codex-native', key, {'code': 'dispatch_unresolved'})

    assert process_once(memory, inbox, state, uncertain, binding, retrieval='lexical')['state'] == 'pending'
    path, receipt = paths
    before = receipt.read_bytes()

    def forbidden(*_args):
        pytest.fail('An owner-local decision has no model effect')

    local = dict(outcome='omitted', reason='The fixture source has no durable change.', records=[], links=[])
    with pytest.raises(ValueError):
        repair(value, path, 'Still deferred.', local_decision=dict(local, outcome='deferred'), models=forbidden)
    staged = repair(value, path, 'Review recorded separately.', local_decision=local, models=forbidden)
    assert staged == dict(state='local_decision_staged', model_invoked=False, cursor_advanced=False,
                          original_dispatch_outcome='unconfirmed')
    assert repair(value, path, 'Review recorded separately.', local_decision=local, models=forbidden)['state'] == 'replayed'
    with pytest.raises(ValueError, match='different decision'):
        repair(value, path, 'Review recorded separately.',
               local_decision=dict(local, reason='A different decision.'), models=forbidden)

    completed = process_once(memory, inbox, state, forbidden, binding, retrieval='lexical')
    assert completed['state'] == 'complete' and completed['receipt']['state'] == 'omitted'
    assert receipt.read_bytes() == before
    assert json.loads((path.parent.parent/'owner-local-review/result.json').read_text())[
        'dispatch']['recovery']['original_dispatch_outcome'] == 'unconfirmed'
