"""Account replay/conflict/index mechanics; fabricated reviewer is not quality evidence."""
import json
import pytest

from tests.test_portable_producer import setup  # noqa: F401
from portable_producer import process_once as capture, maintain_index_once
from account_reconciliation import process_once


def prepare(fixture):
    memory,inbox,state,propose,context,*_=fixture
    capture(memory,inbox,state,propose,context)
    original=memory.add_text('episodes','Delivery report','The human reported a successful delivery.')
    row=memory._read_chapter(original)
    target=memory.add_text('library','Delivery account','The human reported successful delivery.',metadata={
        'mode':'inferred','evidence':[f"mem:{row['record_uid']}@1"]})
    memory.update_chapter(original,content='Human correction: delivery failed; no receipt was observed.')
    return memory,inbox,state,context,original,target


def client(calls, *, reject=False, change=None):
    def invoke(request,path):
        calls.append(request['phase'])
        packet=json.loads(request['messages'][1]['content'])
        if request['phase']=='consolidation':
            source=packet['manifest']['supports'][0]
            value={'claims':[dict(text=source['raw'],support=[source['id']])]}
        else:
            text=packet['candidate']['claims'][0]['text']
            cid=packet['evidence'][0]['id']
            passage=next(p['passage'] for p in packet['evidence'][0]['proof_passages'] if text in p['quote'])
            verdict='unsupported' if reject else 'supported'
            value=dict(claims=[dict(index=0,verdict=verdict,reason='Fixture source assessment.',
                assertions=[dict(span=text,verdict=verdict,reason='Fixture comparison.',basis='memory',
                    source_fact=packet['evidence'][0]['text'],binding_fields=[],proof=[dict(id=cid,passage=passage)])])],missing=[])
            if change:
                change()
        return dict(selection=value,dispatch=dict(model='fixture',usage=None))
    return invoke


def test_commit_crash_replays_without_model_and_indexes_organization_stream(setup,monkeypatch):  # noqa: F811
    memory,inbox,state,context,original,target=prepare(setup)
    calls=[]
    model=client(calls)
    def crash(stage):
        raise RuntimeError(stage)
    with pytest.raises(RuntimeError,match='after_canon_commit'):
        process_once(memory,inbox,state,model,context,model_policy='fixture',_fault=crash)
    row=memory._read_chapter(target)
    assert row['revision']==2 and row['support_status']=='current'
    assert 'successful delivery' in memory.history(target)[0]['raw']
    assert process_once(memory,inbox,state,model,context,model_policy='fixture')['replayed']
    assert process_once(memory,inbox,state,model,context,model_policy='fixture')['state']=='idle'
    assert calls==['consolidation','consolidation_review']
    embeddings=[]
    monkeypatch.setattr(memory,'embeddings_runtime_config',lambda **kw:dict(provider='local',model='fixture',output_dimensionality=None))
    def embed(provider,texts,**kw):
        embeddings.extend(texts)
        return [[1.0,0.0] for _ in texts]
    monkeypatch.setattr(memory,'embed_texts',embed)
    result=maintain_index_once(memory,inbox,state,kind='organization')
    assert result['state']=='complete' and result['processed']==1
    assert maintain_index_once(memory,inbox,state,kind='organization')['state']=='idle'
    assert len(embeddings)==1
    assert not (state/'embedding-index.json').exists()


def test_rejected_review_retains_work_without_repeated_requests(setup):  # noqa: F811
    memory,inbox,state,context,original,target=prepare(setup)
    calls=[]
    for _ in range(2):
        result=process_once(memory,inbox,state,client(calls,reject=True),context,model_policy='fixture',max_revisions=0)
        assert result['reason_code']=='account_review_rejected'
    assert memory._read_chapter(target)['revision']==1
    assert calls==['consolidation','consolidation_review']
    assert (state/'organization-1.json').exists()


def test_changed_source_archives_candidate_then_regenerates_from_current_revision(setup):  # noqa: F811
    memory,inbox,state,context,original,target=prepare(setup)
    calls=[]
    def changed():
        memory.update_chapter(original,content='The human later confirmed delivery; preserve the earlier failed attempt.')
    result=process_once(memory,inbox,state,client(calls,change=changed),context,model_policy='fixture')
    assert result['reason_code']=='canonical_context_changed'
    assert memory._read_chapter(target)['revision']==1
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture')
    assert result['reason_code']=='canonical_context_changed'
    assert (state/'organization-1-superseded-0.json').exists()
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture')
    assert result['state']=='complete' and len(calls)==4
    assert memory._read_chapter(target)['support_status']=='current'


def test_context_budget_preserves_whole_sources_without_model_or_acknowledgment(setup):  # noqa: F811
    memory,inbox,state,context,original,target=prepare(setup)
    calls=[]
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture',source_budget_bytes=1)
    assert result['reason_code']=='source_context_budget_exceeded' and not calls
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture',
                        source_budget_bytes=result['minimum_required_bytes'])
    assert result['state']=='complete' and len(calls)==2


def test_source_race_inside_application_preserves_failed_event_and_resumes_new_sources(setup,monkeypatch):  # noqa: F811
    import account_reconciliation as module
    memory,inbox,state,context,original,target=prepare(setup)
    apply=module.consolidation.apply
    raced=[]
    def concurrent(*args,**kwargs):
        if not raced:
            raced.append(True)
            memory.update_chapter(original,content='New human correction: delivery still unconfirmed after retry.')
        return apply(*args,**kwargs)
    monkeypatch.setattr(module.consolidation,'apply',concurrent)
    calls=[]
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture')
    assert result['reason_code']=='canonical_context_changed'
    assert memory._read_chapter(target)['revision']==1
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture')
    assert result['reason_code']=='canonical_context_changed' and result['organized_through']==1
    with memory.connect() as con:
        row=con.execute("SELECT state,reason FROM capture_events WHERE stream_id LIKE 'organization:%' AND sequence=1").fetchone()
    assert row['state']=='omitted' and 'sources changed' in row['reason']
    result=process_once(memory,inbox,state,client(calls),context,model_policy='fixture')
    assert result['state']=='complete' and result['organized_through']==2
    assert len(calls)==4 and memory._read_chapter(target)['support_status']=='current'


def test_explicit_reviewer_change_preserves_generation_and_prior_verdict(setup):  # noqa: F811
    from account_reconciliation import reprepare_review
    memory,inbox,state,context,original,target=prepare(setup)
    calls=[]
    assert process_once(memory,inbox,state,client(calls,reject=True),context,
                        model_policy='first',max_revisions=0)['reason_code']=='account_review_rejected'
    reprepare_review(memory,inbox,state,context,model_policy='second',max_revisions=0,reason='Compare a different reviewer after a retained rejection.')
    result=process_once(memory,inbox,state,client(calls),context,model_policy='second',max_revisions=0)
    assert result['state']=='complete'
    assert calls==['consolidation','consolidation_review','consolidation_review']
    prior=json.loads(next(state.glob('organization-1-reprepared-*.json')).read_text())
    assert prior['job']['review']['selection']['claims'][0]['verdict']=='unsupported'


def test_one_review_guided_revision_is_bounded_and_plain_sources_remain_quotable(setup):  # noqa: F811
    from account_reconciliation import source_evidence
    from assertion_review import proof_passages
    memory,inbox,state,context,original,target=prepare(setup)
    source=memory._read_chapter(original)
    assert source['raw'] in [p['quote'] for p in proof_passages(source_evidence(source))]
    calls=[]
    assert process_once(memory,inbox,state,client(calls,reject=True),context,
                        model_policy='fixture')['reason_code']=='account_revision_pending'
    assert process_once(memory,inbox,state,client(calls,reject=True),context,
                        model_policy='fixture')['reason_code']=='account_review_rejected'
    assert process_once(memory,inbox,state,client(calls,reject=True),context,
                        model_policy='fixture')['reason_code']=='account_review_rejected'
    assert len(calls)==4 and memory._read_chapter(target)['revision']==1
