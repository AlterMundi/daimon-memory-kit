"""Recovery changes only unsupported recognition titles, never selected meaning."""
# ruff: noqa: F811
import copy
import json

import pytest
from tests.test_portable_producer import setup  # noqa: F401
from tests.test_memory_runtime import configuration
from portable_producer import process_once
from repair_selection_titles import repair


def halted(setup,tmp_path):
    memory,inbox,state,propose,binding,_,_=setup
    value=configuration(tmp_path,memory,inbox,state,binding)
    def invalid(request,directory):
        result=propose(request,directory)
        result['selection']['records'][0]['title']='Unsupported invented heading'
        return result
    result=process_once(memory,inbox,state,invalid,binding,retrieval='lexical')
    assert result['state']=='pending'
    job=json.loads((state/'batch-1.json').read_text())
    assert job['navigation']['halted_reason']
    assert 'records[0].title' in job['navigation']['steps'][-1]['feedback']['selection_error']
    return value,job


def fixed(job):
    result=copy.deepcopy(job['navigation']['steps'][-1]['proposal'])
    result['selection']['records'][0]['title']='Jo'
    return result


def test_title_recovery_preserves_halt_and_admits_once_after_explicit_resume(setup,tmp_path):
    value,job=halted(setup,tmp_path);calls=[]
    def native(request,directory):
        calls.append(request)
        assert request['phase']=='consolidation_review'
        return fixed(job)
    assert repair(value,1,'Repair unsupported title only.',models=native)['state']=='repaired_for_validation'
    assert repair(value,1,'Repair unsupported title only.',models=native)['state']=='replayed'
    assert len(calls)==1
    memory,inbox,state,_,binding,_,_=setup
    saved=json.loads((state/'batch-1.json').read_text())
    assert saved['navigation']==job['navigation']
    with memory.connect() as c:assert c.execute('select count(*) from chapters').fetchone()[0]==0
    def forbidden(*a):pytest.fail('retained proposal must be reused')
    result=process_once(memory,inbox,state,forbidden,binding,retrieval='lexical')
    assert result['state']=='complete' and result['receipt']['state']=='applied'
    assert process_once(memory,inbox,state,forbidden,binding,retrieval='lexical')['state']=='idle'
    assert repair(value,1,'Repair unsupported title only.',models=native)['state']=='replayed'
    with memory.connect() as c:
        assert c.execute('select count(*) from chapters').fetchone()[0]==1
        assert c.execute('select count(*) from capture_events').fetchone()[0]==1


@pytest.mark.parametrize('change',['omit','source','link','reason','unsupported_title'])
def test_review_cannot_drop_work_or_change_meaning_and_rejected_result_is_reused(setup,tmp_path,change):
    value,job=halted(setup,tmp_path);result=fixed(job);s=result['selection']
    if change=='omit':s.update(outcome='omitted',records=[],links=[])
    if change=='source':s['records'][0]['source_ids']=['guessed']
    if change=='link':s['links']=[dict(source='jo',target='jo',link_type='changed')]
    if change=='reason':s['reason']='Different interpretation'
    if change=='unsupported_title':s['records'][0]['title']='Still invented'
    calls=[]
    def native(*a):calls.append(1);return result
    for _ in range(2):
        with pytest.raises(ValueError,match='retained title repair rejected'):
            repair(value,1,'One correction.',models=native)
    assert len(calls)==1
    assert json.loads((setup[2]/'batch-1.json').read_text())==job


def test_changed_sources_or_reason_cannot_authorize_another_review(setup,tmp_path):
    value,job=halted(setup,tmp_path)
    repair(value,1,'Original reason.',models=lambda *a:fixed(job))
    with pytest.raises(ValueError,match='recovery differs'):
        repair(value,1,'New reason.',models=lambda *a:pytest.fail('no redispatch'))
    with setup[1].connect() as c:c.execute('update revisions set delta=?',(b'changed',))
    with pytest.raises(ValueError,match='altered'):
        repair(value,1,'Original reason.',models=lambda *a:pytest.fail('no redispatch'))


def test_uncertain_review_keeps_original_job_and_uses_same_dispatch_directory(setup,tmp_path):
    value,job=halted(setup,tmp_path);paths=[]
    def uncertain(request,directory):
        paths.append(directory);raise ConnectionError('retained uncertain transport')
    for _ in range(2):
        with pytest.raises(ConnectionError):repair(value,1,'Original reason.',models=uncertain)
    assert paths[0]==paths[1]  # Models owns no-implicit-retry receipts at this path.
    assert json.loads((setup[2]/'batch-1.json').read_text())==job


def test_repaired_title_collision_is_not_renamed_away(setup,tmp_path):
    value,job=halted(setup,tmp_path)
    setup[0].add_text('episodes','Jo','An existing retained encounter.')
    with pytest.raises(ValueError,match='retained title repair rejected'):
        repair(value,1,'Repair title.',models=lambda *a:fixed(job))
    assert json.loads((setup[2]/'batch-1.json').read_text())==job
