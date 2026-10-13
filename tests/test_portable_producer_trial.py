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
