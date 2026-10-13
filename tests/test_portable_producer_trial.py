"""Proposer dispatch resumes a completed response, never hides a failed attempt."""
import json
from pathlib import Path
import sys
import pytest

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'research/agent-memory-2026-10-06/pilots')]
import portable_producer_trial as trial


def test_recorded_success_replays_and_truncated_attempt_needs_explicit_retry(tmp_path,monkeypatch):
    count=[]
    def dispatch(path,root,key,provider):
        count.append(path)
        p=root/'dispatches'/(path.stem+'.json');p.parent.mkdir()
        p.write_text(json.dumps({'state':'completed','finish_reason':'length' if len(count)==1 else 'stop','content':'{"outcome":"omitted"}','tool_calls_observed':[]}))
    monkeypatch.setattr(trial.api,'dispatch',dispatch)
    request={'messages':[{'role':'system','content':'Fictional selection'}],'response_schema':{}}
    with pytest.raises(ValueError,match='incomplete'):trial.proposer('test-key')(request,tmp_path)
    with pytest.raises(ValueError,match='incomplete'):trial.proposer('test-key')(request,tmp_path)
    assert len(count)==1
    old=count[0].stem
    response=trial.proposer('test-key',output_limit=12000,retry_of=old)(request,tmp_path)
    assert response['selection']['outcome']=='omitted' and len(count)==2
    assert trial.proposer('test-key',output_limit=12000,retry_of=old)(request,tmp_path)==response
    assert len(count)==2 and (tmp_path/'dispatches'/f'{old}.json').exists()


def test_worker_cli_keeps_pending_visible_and_forwards_phase_budgets(tmp_path,monkeypatch,capsys):
    inbox=tmp_path/'capture.sqlite'
    inbox.touch()
    binding=tmp_path/'binding.json'
    binding.write_text('{}')
    context=tmp_path/'context.json'
    context.write_text('{}')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fictional-test-key')
    monkeypatch.setattr(trial,'load_memory',lambda path:object())
    monkeypatch.setattr(trial,'Inbox',lambda *args:object())
    calls=[]
    def worker(*args,**kwargs):
        calls.append(kwargs)
        return dict(status=dict(state='pending',phases={'organization':{'reason_code':'organization_adapter_unconfigured'}}))
    monkeypatch.setattr(trial.memory_worker,'run',worker)
    monkeypatch.setattr(sys,'argv',['trial','--inbox',str(inbox),'--binding',str(binding),
        '--context',str(context),'--canon',str(tmp_path/'canon'),'--state-dir',str(tmp_path/'state'),
        '--limit','7','--worker-steps','5','--fictional-isolated-profile'])
    assert trial.main()==2
    assert json.loads(capsys.readouterr().out)['state']=='pending'
    assert calls[0]['capture_limit']==calls[0]['index_limit']==7
    assert calls[0]['max_steps']==5


def test_native_account_reviewer_reuses_the_exact_completed_dispatch(tmp_path,monkeypatch):
    calls=[]
    def dispatch(path,root,catalog):
        calls.append(json.loads(path.read_text()))
        directory=root/'dispatches'
        directory.mkdir()
        (directory/path.name).write_text(json.dumps(dict(state='completed',content='{"claims":[],"missing":[]}',tool_calls_observed=[])))
    monkeypatch.setattr(trial.native,'dispatch',dispatch)
    request=dict(phase='consolidation_review',messages=[dict(role='system',content='Review fictional sources only.'),
        dict(role='user',content='{}')],response_schema={'type':'object'})
    review=trial.codex_reviewer(tmp_path/'catalog.json')
    assert review(request,tmp_path)==review(request,tmp_path)
    assert len(calls)==1 and calls[0]['model']=='gpt-6.1-sol'
    assert calls[0]['tools_allowed'] is calls[0]['native_memory_allowed'] is False
