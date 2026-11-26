"""Check evidence verification and canonical replay after source loss."""
import json

import pytest

from capturectl import CaptureLedger
from codex_hook_capture import capture
import sleep_memory_review as review
import sleep_triage
from tests.test_durable_memory_foundation import mc
from tests.test_forward_capture import append, context, turn
from tests.test_sleep_triage import fake_decisions


def test_review_survives_source_loss_and_replays_exactly(mc, context, tmp_path):
    binding, log, event = context
    append(log, turn('episode', 'Renata came to visit and we planted the first olive tree.'))
    capture(binding, event)
    triage = tmp_path / 'triage'
    sleep_triage.run(binding, triage, after=0, api_key='fixture', opener=fake_decisions)
    packet = next((triage / 'packets').glob('*.json'))
    log.unlink()

    candidate = review.read_candidate(binding, triage, packet.stem, 0)
    assert candidate['source']['text'].startswith('Renata')
    assert candidate['probability'] == 0.9
    decision = dict(
        outcome='applied', reason='Distinct human report of a shared milestone',
        selection_version='fixture-review/v1',
        records=[dict(operation='add', key='episode', shelf='episodes',
                      title='The first olive tree', engram_type='episodic',
                      raw='Nicolás reported that Renata visited and they planted their first olive tree.')],
    )
    ledger = CaptureLedger(mc)
    with pytest.raises(ValueError, match='exact candidate'):
        review.apply_review(ledger, binding, candidate, 'old fingerprint', decision)
    with mc.connect() as con:
        assert con.execute('select count(*) from chapters').fetchone()[0] == 0
    receipt = review.apply_review(ledger, binding, candidate, candidate['fingerprint'], decision)
    assert receipt['state'] == 'applied'
    assert review.apply_review(ledger, binding, candidate, candidate['fingerprint'], decision) == receipt
    cid = receipt['records']['episode']['chapter_id']
    record = mc._read_chapter(cid)
    source = json.loads(record['source_metadata_json'])
    assert source['mode'] == 'reported'
    assert source['evidence'] == [source['source_uri']]
    assert candidate['delta_sha256'] in source['source_uri']
    with mc.connect() as con:
        assert con.execute('select count(*) from chapters').fetchone()[0] == 1

    altered = json.loads(packet.read_bytes())
    altered['sources'][0]['start_char'] = 1
    packet.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='source pointers differ'):
        review.read_candidate(binding, triage, packet.stem, 0)
