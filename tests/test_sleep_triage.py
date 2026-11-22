from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from tests.test_forward_capture import append, context, line, turn
from codex_hook_capture import capture
import sleep_triage
from sleep_health import health


def fake_decisions(request, timeout):
    payload = json.loads(request.data)
    assert request.full_url.endswith('/v1/decisions') and timeout == 30
    assert payload['model'] == 'gpt-6-luna'
    return BytesIO(json.dumps({'answers': [
        dict(type='predicate', name=q['name'], probability=0.9)
        for q in payload['questions']
    ], 'usage': {'input_tokens': 100}}).encode())


def test_forward_delta_receipt_recovers_after_local_interruption(context, tmp_path, monkeypatch):
    binding, source, event = context
    append(source, turn('incident', 'Esta mañana Renata nos visitó mientras probábamos el prototipo.'))
    capture(binding, event)
    seen = []

    def classify(request, timeout):
        seen.append(json.loads(request.data))
        return fake_decisions(request, timeout)

    original = sleep_triage.write_packet
    with monkeypatch.context() as patch:
        def interrupted(*args):
            raise RuntimeError('local interruption after provider receipt')
        patch.setattr(sleep_triage, 'write_packet', interrupted)
        with pytest.raises(RuntimeError):
            sleep_triage.run(binding, tmp_path / 'triage', after=0, api_key='fixture', opener=classify)

    # The completed dispatch remains reusable even without an API credential.
    assert sleep_triage.write_packet is original
    state = tmp_path / 'triage'
    result = sleep_triage.run(binding, state, steps=1, opener=classify)
    assert result['state'] == 'caught_up'
    assert len(seen) == 1
    assert 'Renata' in json.dumps(seen[0]) and 'old story' not in json.dumps(seen[0])
    assert set(q['name'] for q in seen[0]['questions']) == {'memory_0', 'work_map_0', 'bitacora_0'}
    packet = json.loads(next((state / 'packets').glob('*.json')).read_text())
    assert packet['decision']['scores']['memory_0'] == 0.9
    assert packet['sources'][0]['source_id'] and 'Renata' not in json.dumps(packet)
    assert sleep_triage.run(binding, state, opener=classify)['completed_pages'] == 0


def test_quota_failure_does_not_consume_or_redispatch(context, tmp_path):
    binding, source, event = context
    append(source, turn('incident', 'Renata visited.'))
    capture(binding, event)
    calls = []

    def reject(request, timeout):
        calls.append(True)
        raise HTTPError(request.full_url, 429, 'fixture quota', {}, BytesIO(
            b'{"error":{"code":"insufficient_quota"}}'))

    state = tmp_path / 'quota'
    with pytest.raises(ValueError, match='quota_exhausted'):
        sleep_triage.run(binding, state, after=0, api_key='fixture', opener=reject)
    with pytest.raises(ValueError, match='no automatic retry'):
        sleep_triage.run(binding, state, api_key='fixture', opener=reject)
    assert len(calls) == 1
    assert json.loads((state / 'cursor.json').read_text())['after'] == 0
    assert not list((state / 'packets').glob('*.json'))


def test_distinct_conversations_are_not_mixed_and_long_dialogue_has_no_dropped_text(context, tmp_path):
    binding, source, event = context
    # Let capture store each complete message in the test fixture.
    append(source, turn('one', 'a' * 3000))
    # The paging check is independent of the capture fixture's 2 KiB budget.
    pages = list(sleep_triage.pages_for(turn('one', 'a' * 9001), 'first', 'fixture'))
    assert ''.join(item['text'] for page in pages for item in page) == 'a' * 9001
    assert all(len(sleep_triage.wire(page).encode()) <= sleep_triage.PAGE_BYTES for page in pages)

    # A second test source is admitted under its own conversation ID.
    from datetime import datetime, timezone
    second = source.with_name('second.jsonl')
    second.write_bytes(line('session_meta', dict(id='second', cwd='/work',
                       timestamp=datetime.now(timezone.utc).isoformat())) + turn('second', 'Second conversation.'))
    assert capture(binding, {**event, 'session_id': 'second', 'transcript_path': str(second)})['capture_complete']
    first = source.with_name('first.jsonl')
    first.write_bytes(line('session_meta', dict(id='first', cwd='/work',
                      timestamp=datetime.now(timezone.utc).isoformat())) + turn('first', 'First conversation.'))
    assert capture(binding, {**event, 'session_id': 'first', 'transcript_path': str(first)})['capture_complete']
    state = tmp_path / 'separate'
    sleep_triage.run(binding, state, after=0, api_key='fixture', opener=fake_decisions)
    packets = [json.loads(p.read_text()) for p in (state / 'packets').glob('*.json')]
    assert {p['conversation'] for p in packets} == {'first', 'second'}
    assert all(len(p['sources']) == 1 for p in packets)


def test_metadata_is_not_learning_and_blocked_capture_is_visible(tmp_path):
    worker = dict(schema='hmk.worker-status/v1', state='pending', phase=None, observed=True,
                  updated_ns=100_000_000_000, phases={'capture': dict(state='pending',
                  reason_code='source_context_budget_exceeded')})
    (tmp_path / 'worker-status.json').write_text(json.dumps(worker))
    report = tmp_path / 'source.json'
    report.write_text(json.dumps(dict(schema='dm.source-review/v2',
                                      observed_at_ms=100_000, unavailable=[], unconfirmed_targets=[])))
    result = health(tmp_path, report, max_age_seconds=30, now_ns=110_000_000_000)
    assert result['dmk']['capture']['status'] == 'blocked'
    assert result['matrix']['source_review']['status'] == 'observed'
    assert result['matrix']['receiving_learning'] == 'requires_receiving_evidence'
    assert health(tmp_path, report, max_age_seconds=30, now_ns=150_000_000_000)['matrix']['source_review']['status'] == 'stale'


def test_selected_worker_exports_triage_receipt_and_current_health(context, tmp_path, monkeypatch):
    import memory_runtime
    from capture_inbox import Inbox

    binding, source, event = context
    append(source, turn('incident', 'Renata visited.'))
    capture(binding, event)
    inbox = Inbox(binding['inbox'], binding)
    selected = tmp_path / 'worker'
    selected.mkdir()
    status = dict(schema='hmk.worker-status/v1', state='pending', observed=True, phase=None,
                  updated_ns=sleep_triage.time.time_ns(), owner='fixture-owner',
                  phases={'capture': {'state': 'pending', 'reason_code': 'source_context_budget_exceeded'}})
    (selected / 'worker-status.json').write_text(json.dumps(status))
    monkeypatch.setenv('DMK_TEST_DECISIONS_KEY', 'fictional-test')
    real_run = sleep_triage.run
    monkeypatch.setattr(sleep_triage, 'run', lambda *a, **kw: real_run(*a, **kw, opener=fake_decisions))

    result = {'status': status}
    memory_runtime.run_sleep_triage(dict(state_dir=str(selected), sleep_triage=dict(
        state_dir=str(selected / 'triage'), initial_after=0, steps=1,
        credential_env='DMK_TEST_DECISIONS_KEY', source_review_report=str(tmp_path / 'missing'),
        max_age_seconds=60,
    )), inbox, binding, result)
    observed = json.loads((selected / 'worker-status.json').read_text())
    assert observed['sleep_triage']['state'] == 'caught_up'
    assert observed['sleep_health']['dmk']['capture']['status'] == 'blocked'
    assert observed['sleep_health']['matrix']['source_review']['status'] == 'unobserved'
    assert observed['state'] == 'pending'
