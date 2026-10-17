"""One finite launcher; no automatic retry, hidden provider failure or lost intake."""
# ruff: noqa: F811
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from tests.test_portable_producer import setup  # noqa: F401
from memory_worker import run, observe
from provider_status import ProviderProblem, Alerts


def no_organization():
    return dict(state='idle')


def indexing(monkeypatch):
    import memory_worker
    def step(*args,**kwargs):
        return dict(state='idle')
    monkeypatch.setattr(memory_worker,'maintain_index_once',step)


def test_finite_budget_retains_progress_and_idle_reentry_uses_no_inference(setup,monkeypatch):
    indexing(monkeypatch)
    memory,inbox,state,propose,binding,calls,_=setup
    first=run(memory,inbox,state,propose,binding,organize=no_organization,max_steps=1)
    assert first['status']['state']=='pending' and first['status']['budget_exhausted']
    assert first['outcomes'][0]['result']['source_group_complete']
    second=run(memory,inbox,state,propose,binding,organize=no_organization)
    assert second['status']['state']=='idle' and len(calls)==1
    assert observe(state)==second['status']
    assert observe(state/'missing')['state']=='unobserved'


def test_unconfigured_organization_is_not_healthy_or_a_repeated_model_loop(setup,monkeypatch):
    indexing(monkeypatch)
    memory,inbox,state,propose,binding,calls,_=setup
    result=run(memory,inbox,state,propose,binding,max_steps=100)
    assert result['status']['state']=='pending' and len(calls)==1
    assert result['status']['phases']['organization']['reason_code']=='organization_adapter_unconfigured'
    assert result['status']['phases']['organization']['ready_accounts']==0
    assert result['status']['phases']['organization']['blocked_accounts']==0
    assert len([s for s in result['outcomes'] if s['phase']=='organization'])==1
    assert result['status']['steps']<100


def test_provider_failure_visible_and_not_retried_in_same_invocation(setup,monkeypatch):
    indexing(monkeypatch)
    memory,inbox,state,propose,binding,_,_=setup
    calls=[]
    def organize():
        calls.append(1)
        raise ProviderProblem('deepseek','request',{'code':'payment_required'})
    result=run(memory,inbox,state,propose,binding,organize=organize,max_steps=100)
    assert len(calls)==1 and result['status']['state']=='pending'
    assert result['status']['phases']['organization']['reason_code']=='payment_required'
    assert Alerts(inbox).status()['undelivered']==1
    assert 'payment_required' in json.dumps(observe(state))


def test_status_keeps_errors_safe_and_missing_index_work_visible(setup,monkeypatch):
    import memory_worker
    memory,inbox,state,propose,binding,_,_=setup
    def failed(*args,**kwargs):
        raise RuntimeError('private source /private/path token=SECRET')
    monkeypatch.setattr(memory_worker,'maintain_index_once',failed)
    result=run(memory,inbox,state,propose,binding,organize=no_organization)
    projection=json.dumps(result['status'])
    assert 'SECRET' not in projection and '/private/path' not in projection
    assert result['status']['phases']['index']['error_type']=='RuntimeError'
    assert result['status']['state']=='pending'


def test_second_worker_cannot_run_while_foreground_invocation_owns_inbox(setup,monkeypatch):
    indexing(monkeypatch)
    memory,inbox,state,propose,binding,_,_=setup
    entered,release=Event(),Event()
    def held(request,path):
        entered.set()
        assert release.wait(5)
        return propose(request,path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(run,memory,inbox,state,held,binding,organize=no_organization)
        assert entered.wait(5)
        try:
            assert observe(state)['phase']=='capture'
            with pytest.raises(BlockingIOError):
                run(memory,inbox,state,propose,binding,organize=no_organization)
        finally:
            release.set()
        assert future.result()['status']['state']=='idle'


def test_provider_recovery_resolves_only_its_phase_and_preserves_capture(setup,monkeypatch):
    indexing(monkeypatch)
    memory,inbox,state,propose,binding,calls,_=setup
    def no_credit():
        raise ProviderProblem('deepseek','fixture',{'code':'payment_required'})
    first=run(memory,inbox,state,propose,binding,organize=no_credit)
    assert not Alerts(inbox).status()['healthy']
    second=run(memory,inbox,state,propose,binding,organize=no_organization)
    assert second['status']['state']=='idle' and Alerts(inbox).status()['healthy']
    assert len(calls)==1 and first['status']['owner']==second['status']['owner']


def test_wrong_destination_refused_before_organization_can_run(setup,monkeypatch,tmp_path):
    indexing(monkeypatch)
    memory,inbox,state,propose,binding,_,_=setup
    run(memory,inbox,state,propose,binding,organize=no_organization)
    calls=[]
    with pytest.raises(ValueError,match='producer destination'):
        run(memory,inbox,tmp_path/'other',propose,binding,organize=lambda:calls.append(1))
    assert not calls


def test_real_index_phase_runs_after_capture_and_empty_inbox_is_idle(setup,monkeypatch,tmp_path):
    from capture_inbox import Inbox
    memory,inbox,state,propose,binding,calls,_=setup
    embeddings=[]
    monkeypatch.setattr(memory,'embeddings_runtime_config',lambda **kw:dict(provider='local',model='fixture',output_dimensionality=None))
    def embed(provider,texts,**kwargs):
        embeddings.extend(texts)
        return [[1.0,0.0] for _ in texts]
    monkeypatch.setattr(memory,'embed_texts',embed)
    first=run(memory,inbox,state,propose,binding,organize=no_organization)
    assert first['status']['state']=='idle' and len(embeddings)==1
    assert first['status']['phases']['index']['indexed_through']==1
    run(memory,inbox,state,propose,binding,organize=no_organization)
    assert len(calls)==len(embeddings)==1
    # A fresh owner with no capture events needs no model work and no index table.
    with memory.connect() as con:
        con.execute('DROP TABLE capture_events')
        con.execute('DROP TABLE capture_streams')
    empty=Inbox(tmp_path/'empty.sqlite',binding)
    result=run(memory,empty,tmp_path/'empty-worker',propose,binding,organize=no_organization)
    assert result['status']['state']=='idle' and len(calls)==1

@pytest.mark.parametrize('reason,code',[
    ('navigation invocation budget reached','navigation_budget_exhausted'),
    ('index work remains','index_budget_exhausted'),
    ('capture event is not committed','waiting_for_capture'),
])
def test_bounded_progress_has_distinct_safe_receipt(setup,monkeypatch,reason,code):
    import memory_worker
    memory,inbox,state,propose,binding,_,_=setup
    monkeypatch.setattr(memory_worker,'process_once',lambda *a,**k:dict(state='pending',reason=reason))
    result=run(memory,inbox,state,propose,binding,organize=no_organization,max_steps=1)
    assert result['status']['phases']['capture']['reason_code']==code
