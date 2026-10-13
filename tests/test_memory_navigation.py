"""Scope-before-ranking and explicit hybrid availability for bounded navigation."""
# ruff: noqa: F811
import json

import pytest

from tests.test_codex_projection import setup, select  # noqa: F401


def test_selected_match_survives_more_than_256_unselected_distractors(setup):
    mc, p = setup
    import deep_recall
    for index in range(270):
        mc.add_text('library', 'Clamp', f'Clamp unrelated routine {index}.')
    cid = mc.add_text('episodes', 'Jo encounter', 'Jo proposed a clamp for the old instrument. ' + 'Context. ' * 80)
    selection = select(mc, p, [cid])
    reader = deep_recall.Reader(mc.DB_PATH, selection)
    result = reader.call(dict(action='search', query='clamp', record_uid='', offset=0))
    assert [r['record_uid'] for r in result['items']] == [selection['records'][0]['record_uid']]
    assert 'unrelated routine' not in json.dumps(result)
    mc.update_chapter(cid, content='Correction: the instrument used a brace.')
    with mc.read_scope(mc.DB_PATH):
        assert mc.search('clamp', record_uids=[]) == []
        assert mc.history_search('clamp', record_uids=[] ) == []
        assert mc.history_search('clamp', record_uids=[selection['records'][0]['record_uid']])[0]['revision'] == 1


def test_hybrid_finds_paraphrase_without_unselected_neighbors_or_writes(setup, monkeypatch):
    mc, p = setup
    import deep_recall
    m = deep_recall.memory
    cid = mc.add_text('episodes', 'Jo encounter', 'Jo proposed a clamp for the old instrument.')
    # A preserved extension from an imported record; native add_text does not
    # author this optional projection field.
    with mc.connect() as con:
        con.execute('UPDATE chapters SET source_metadata_json=? WHERE id=?',
            (json.dumps({'applicability': {'kind':'embodiment','targets':['fixture:workshop']}}), cid))
    other = mc.add_text('library', 'Unselected', 'Private marker')
    mc.add_link(cid, other, 'related')
    monkeypatch.setenv('HMK_EMBED_PROVIDER', 'local')
    monkeypatch.setenv('HMK_EMBED_MODEL', 'fixture')
    # This is a deterministic adapter contract test, not a model quality claim.
    monkeypatch.setattr(m, 'embeddings_runtime_config', lambda **kw: dict(provider='local',model='fixture',output_dimensionality=None))
    monkeypatch.setattr(m, 'embed_texts', lambda *a, **kw: [[1.0, 0.0]])
    monkeypatch.setattr(m, 'rerank_provider_default', lambda: 'none')
    texts = {record:mc.embed_input_text(mc._read_chapter(record)) for record in (cid,other)}
    with mc.connect() as con:
        for record, text in texts.items():
            mc.upsert_embedding(con, record, 'local', 'fixture', text, [1., 0.])
    selection = select(mc, p, [cid])
    uid = selection['records'][0]['record_uid']
    before = mc.DB_PATH.read_bytes()
    with m.read_scope(mc.DB_PATH):
        assert m.search('fastening apparatus', record_uids=[uid]) == []
        pack = m.hybrid_pack('fastening apparatus', record_uids=[uid], _record_access=False)
        assert [r['record_uid'] for r in pack['items']] == [uid]
        assert pack['items'][0]['neighbors'] == []
    reader = deep_recall.Reader.live_pool(mc.DB_PATH,being_ref='fixture:being',body_ref='fixture:body',retrieval='hybrid')
    result = reader.call(dict(action='search',query='fastening apparatus',record_uid='',offset=0))
    retained = next(r for r in result['items'] if r['record_uid'] == uid)
    assert retained['applicability'] == {'kind':'embodiment','targets':['fixture:workshop']}
    assert mc.DB_PATH.read_bytes() == before


def test_backend_outage_preserves_lexical_access_and_does_not_claim_absence(setup, monkeypatch):
    mc, _ = setup
    import memory_navigation as navigation
    mc.add_text('episodes', 'Jo', 'Jo proposed a clamp.')
    def unavailable(*a, **kw):
        raise mc.EmbeddingBackendError('not copied into result')
    monkeypatch.setattr(mc, 'embed_texts', unavailable)
    before = mc.DB_PATH.read_bytes()
    with mc.read_scope(mc.DB_PATH):
        result = navigation.search(mc,'clamp')
        assert result['items'] and result['retrieval_status'] == 'degraded'
        missing = navigation.search(mc,'fastening apparatus')
        assert missing['retrieval_status'] == 'unavailable'
        assert missing['backend_errors'] == ['embedding_backend_unavailable']
    assert mc.DB_PATH.read_bytes() == before
    def bug(*a, **kw):
        raise ValueError('ranking implementation defect')
    monkeypatch.setattr(mc,'hybrid_candidates',bug)
    with pytest.raises(ValueError, match='implementation defect'):
        navigation.search(mc,'clamp')


def test_history_only_match_exposes_current_revision_for_reading(setup):
    mc, _ = setup
    from deep_recall import Reader
    cid = mc.add_text('episodes', 'Earlier', 'Jo proposed a clamp.')
    mc.update_chapter(cid, content='Correction: Jo used a brace.')
    reader = Reader.live_pool(mc.DB_PATH, being_ref='fixture:being', body_ref='fixture:body')
    result = reader.call(dict(action='search', query='clamp', record_uid='', offset=0))
    historical = result['historical_matches'][0]
    assert historical['historical'] is True
    assert historical['revision'] == 1 and historical['current_revision'] == 2
    current = reader.call(dict(action='read', query='', record_uid=historical['record_uid'], offset=0))
    assert current['record']['revision'] == historical['current_revision']
    assert 'used a brace' in current['raw']


def test_candidates_can_be_explored_without_relaxing_context_admission(setup, monkeypatch):
    mc, _ = setup
    import memory_navigation as navigation
    cid = mc.add_text('episodes', 'Jo encounter', 'Jo proposed a clamp for the old instrument.')
    text = mc.embed_input_text(mc._read_chapter(cid))
    with mc.connect() as con:
        mc.upsert_embedding(con, cid, 'local', 'fixture', text, [0.2, 0.98])
    monkeypatch.setattr(mc, 'embeddings_runtime_config', lambda **kw: dict(
        provider='local',model='fixture',output_dimensionality=None))
    monkeypatch.setattr(mc, 'embed_texts', lambda *a, **kw: [[1.,0.]])
    monkeypatch.setattr(mc, 'rerank_provider_default', lambda: 'none')
    before = mc.DB_PATH.read_bytes()
    with mc.read_scope(mc.DB_PATH):
        automatic = mc.hybrid_pack('fastening apparatus', _record_access=False)
        assert automatic['null_retrieval'] and automatic['threshold'] == 0.4
        candidate = navigation.search(mc, 'fastening apparatus')['items'][0]
        assert candidate['record_uid'] == mc._read_chapter(cid)['record_uid']
        assert candidate['relevance'].startswith('unassessed')
        assert candidate['score'] < automatic['threshold']
        assert 'raw' not in candidate  # Search metadata is not an accepted answer.
    assert mc.DB_PATH.read_bytes() == before
