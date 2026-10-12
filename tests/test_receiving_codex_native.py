"""Native fictional receiver isolation controls and failed-attempt accounting."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def native(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root/'scripts'))
    monkeypatch.syspath_prepend(str(root/'research/agent-memory-2026-10-06/pilots'))
    spec = importlib.util.spec_from_file_location('native_receiver_test',
        root/'research/agent-memory-2026-10-06/pilots/receiving_codex_native.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def inputs(native, path):
    request = dict(format='hmk-fictional-receiving-request/v1', model='gpt-6.1-sol',
        phase='narrative_generation', reasoning_effort='low', fresh_context=True,
        tools_allowed=False, native_memory_allowed=False,
        messages=[dict(role='system', content='Fictional JSON only.'),
                  dict(role='user', content='Supplied fictional evidence.')], response_schema={'type':'object'})
    request_path = path/(native.exchange.pilot.digest(request)+'.json')
    native.exchange.pilot.save(request_path, request)
    catalog = path/'catalog.json'
    native.exchange.pilot.save(catalog, {'models':[dict(slug='gpt-6.1-sol',
        apply_patch_tool_type=None, shell_type='disabled', experimental_supported_tools=[],
        supports_search_tool=False, node_repl_disabled=True)]})
    return request_path, request, catalog


def test_native_controls_and_usage_do_not_claim_an_invoice_or_model_label(native, tmp_path):
    path, request, catalog = inputs(native, tmp_path)
    credential = tmp_path/'fixture-auth.json'; credential.write_text('{}')
    def runner(argv, **kwargs):
        assert argv[0] == 'bwrap' and '--tmpfs' in argv
        argv = argv[argv.index('--')+1:]
        assert argv[0:2] == ['codex', 'exec']
        assert '--ignore-user-config' in argv and '--ephemeral' in argv
        assert 'forced_login_method="chatgpt"' in argv and 'model_provider="openai"' in argv
        assert 'project_doc_max_bytes=0' in argv and 'orchestrator.mcp.enabled=false' in argv
        assert kwargs['input'] == request['messages'][1]['content']
        assert kwargs['timeout'] == 300
        events = [dict(type='item.completed', item=dict(type='agent_message', text='{}')),
            dict(type='turn.completed', usage=dict(input_tokens=30, output_tokens=4, cached_input_tokens=10))]
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, events)), stderr='private stderr')
    receipt = native.dispatch(path, tmp_path, catalog, runner, credential)
    data = json.loads(receipt.read_text())
    assert data['usage']['total_tokens'] == 34 and data['native_usage']['cached_input_tokens'] == 10
    assert data['billed_cost_usd'] is None and data['actual_response_model'] is None
    assert 'private stderr' not in receipt.read_text()
    with pytest.raises(ValueError, match='no implicit retry'):
        native.dispatch(path, tmp_path, catalog, lambda *_a, **_k: pytest.fail('repeated'), credential)


def test_observed_tool_use_is_preserved_but_cannot_enter_receiving(native, tmp_path):
    path, _request, catalog = inputs(native, tmp_path)
    credential = tmp_path/'fixture-auth.json'; credential.write_text('{}')
    def runner(*_a, **_k):
        events = [dict(type='item.completed', item=dict(type='mcp_tool_call')),
            dict(type='turn.completed', usage=dict(input_tokens=8, output_tokens=2))]
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, events)))
    with pytest.raises(ValueError, match='used tools'):
        native.dispatch(path, tmp_path, catalog, runner, credential)
    receipt = json.loads((tmp_path/'dispatches'/path.name).read_text())
    assert receipt['state'] == 'failed' and receipt['usage']['total_tokens'] == 10
    assert not (tmp_path/'responses'/path.name).exists()


def test_review_and_revision_preserve_only_explicit_task_transcript(native, tmp_path):
    _path, request, catalog = inputs(native, tmp_path)
    request['phase'] = 'narrative_review'
    _argv, stdin = native.command(request, catalog, tmp_path, tmp_path)
    assert stdin == request['messages'][1]['content']
    request['phase'] = 'narrative_revision'
    request['messages'] += [dict(role='assistant', content='A mistaken candidate.'),
                            dict(role='user', content='Correct the source attribution.')]
    _argv, stdin = native.command(request, catalog, tmp_path, tmp_path)
    transcript = json.loads(stdin[stdin.index('\n')+1:])
    assert transcript == request['messages'][1:]
    request['messages'][2]['role'] = 'tool'
    with pytest.raises(ValueError, match='alternating'):
        native.command(request, catalog, tmp_path, tmp_path)


def test_medium_is_an_explicit_review_only_profile_with_actual_receipt_effort(native, tmp_path):
    _path, request, catalog = inputs(native, tmp_path)
    request['reasoning_effort'] = 'medium'
    with pytest.raises(ValueError, match='medium review profile'):
        native.command(request, catalog, tmp_path, tmp_path)
    request['phase'] = 'narrative_review'
    argv, _stdin = native.command(request, catalog, tmp_path, tmp_path)
    assert 'model_reasoning_effort="medium"' in argv
    path = tmp_path/(native.exchange.pilot.digest(request)+'.json')
    native.exchange.pilot.save(path, request)
    with pytest.raises(ValueError, match='medium reasoning support'):
        native.dispatch(path, tmp_path, catalog, lambda *_a, **_k:pytest.fail('dispatched'))
    data = json.loads(catalog.read_text())
    data['models'][0]['supported_reasoning_levels'] = [{'effort':'medium'}]
    native.exchange.pilot.save(catalog, data)
    credential = tmp_path/'fixture-auth.json'; credential.write_text('{}')
    def runner(argv, **kwargs):
        assert 'model_reasoning_effort="medium"' in argv
        events = [dict(type='item.completed', item=dict(type='agent_message', text='{}')),
                  dict(type='turn.completed', usage=dict(input_tokens=10, output_tokens=2))]
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, events)), stderr='')
    receipt = native.dispatch(path, tmp_path, catalog, runner, credential)
    assert json.loads(receipt.read_text())['reasoning_effort'] == 'medium'


def test_unsupported_model_or_tool_capable_catalog_never_dispatches(native, tmp_path):
    path, request, catalog = inputs(native, tmp_path)
    request['model'] = 'openai/gpt-6.1-sol'
    with pytest.raises(ValueError, match='native Sol low'):
        native.command(request, catalog, tmp_path, tmp_path)
    data = json.loads(catalog.read_text()); data['models'][0]['apply_patch_tool_type'] = 'freeform'
    native.exchange.pilot.save(catalog, data)
    with pytest.raises(ValueError, match='disable all'):
        native.dispatch(path, tmp_path, catalog, lambda *_a, **_k: pytest.fail('dispatched'))


def test_selected_context_requires_explicit_scope_and_keeps_isolation(native, tmp_path):
    _path, request, catalog = inputs(native, tmp_path)
    request['format'] = 'hmk-selected-receiving-request/v1'
    with pytest.raises(ValueError, match='explicit isolated'):
        native.command(request, catalog, tmp_path, tmp_path)
    request['source_scope'] = 'human-authorized-selected-context'
    request['messages'][1]['content'] = 'Selected authorized evidence only.'
    path = tmp_path/(native.exchange.pilot.digest(request)+'.json')
    native.exchange.pilot.save(path, request)
    credential = tmp_path/'fixture-auth.json'; credential.write_text('{}')
    def runner(argv, **kwargs):
        assert '--ephemeral' in argv and '--ignore-user-config' in argv
        assert kwargs['input'] == 'Selected authorized evidence only.'
        events = [dict(type='item.completed', item=dict(type='agent_message', text='{}')),
                  dict(type='turn.completed', usage=dict(input_tokens=10, output_tokens=2))]
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, events)), stderr='')
    receipt = native.dispatch(path, tmp_path, catalog, runner, credential)
    data = json.loads(receipt.read_text())
    assert data['source_scope'] == 'human-authorized-selected-context'
    assert not data['native_memory_allowed'] and not data['tools_allowed']
    request['format'] = 'hmk-fictional-receiving-request/v1'
    with pytest.raises(ValueError, match='explicit isolated'):
        native.command(request, catalog, tmp_path, tmp_path)


def test_native_interruption_records_failed_attempt_and_closes_credential_fd(native,tmp_path):
    import os
    path,_request,catalog=inputs(native,tmp_path)
    credential=tmp_path/'fixture-auth.json';credential.write_text('{}');fds=[]
    def runner(*_a,**kwargs):
        fds.extend(kwargs['pass_fds']);raise KeyboardInterrupt('PRIVATE_INTERRUPT_DETAIL')
    with pytest.raises(KeyboardInterrupt):native.dispatch(path,tmp_path,catalog,runner,credential)
    receipt=tmp_path/'dispatches'/path.name;data=json.loads(receipt.read_text())
    assert data['state']=='failed' and data['error_type']=='KeyboardInterrupt'
    assert data['usage'] is None and 'PRIVATE_INTERRUPT_DETAIL' not in receipt.read_text()
    assert not (tmp_path/'responses'/path.name).exists()
    with pytest.raises(OSError):os.fstat(fds[0])
    with pytest.raises(ValueError,match='no implicit retry'):
        native.dispatch(path,tmp_path,catalog,lambda *_a,**_k:pytest.fail('Repeated interrupted dispatch'),credential)
