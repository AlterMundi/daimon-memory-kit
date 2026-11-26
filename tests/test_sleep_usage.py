"""Decisions usage survives receipt replay without conflating unknown with zero."""
from datetime import datetime
import json

from sleep_usage import report


def test_usage_windows_use_reported_receipts_and_disclose_missing_cost(tmp_path):
    root = tmp_path / 'triage'
    root.mkdir(mode=0o700)
    packets = root / 'packets'
    packets.mkdir()
    stamp = int(datetime.fromisoformat('2026-11-26T02:30:00+00:00').timestamp()) * 10**9
    known = dict(state='complete', request_sha256='a', completed_at_ns=stamp,
                 usage=dict(input_tokens=800, output_tokens=0, cached_input_tokens=500),
                 scores={'memory_0': 0.99}, response_id='private-id')
    followup = dict(state='complete', request_sha256='b', completed_at_ns=stamp,
                    usage={'input_tokens': 200, 'output_tokens': 0})
    unknown = dict(state='complete', request_sha256='c', completed_at_ns=stamp, usage=None)
    legacy = dict(state='complete', request_sha256='d',
                  usage={'input_tokens': 130, 'output_tokens': 0})
    for n, (initial, context) in enumerate(((known, followup), (unknown, legacy))):
        (packets / f'{n}.json').write_text(json.dumps(dict(decision=initial, context_decision=context)))
    (root / 'dispatch.json').write_text(json.dumps(known))
    (root / 'context-dispatch.json').write_text(json.dumps(dict(state='started', request_sha256='e')))

    totals = report(root, now_ns=stamp)
    assert totals['days']['2026-11-25'] == dict(
        received=3, metered=2, input_tokens=1000, output_tokens=0,
        cached_input_tokens=500, cached_input_reports=1, unknown_usage=1)
    assert totals['windows']['7'] == totals['windows']['30']
    assert totals['undated']['input_tokens'] == 130
    assert totals['retained']['received'] == 4
    assert totals['unresolved_attempts'] == 1
    assert 'private-id' not in json.dumps(totals)
