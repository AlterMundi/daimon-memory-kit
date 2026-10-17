"""Scope-before-ranking and explicit hybrid availability for bounded navigation."""
# ruff: noqa: F811
import json

import pytest

from tests.test_codex_projection import setup, select  # noqa: F401


def test_cli_navigation_exposes_candidates_without_lowering_pack_admission(setup, monkeypatch, capsys):
    import sys
    mc, _ = setup
    cid=mc.add_text('episodes','Brace proposal','Jo proposed a removable brace; delivery failed.')
    other=mc.add_text('episodes','Unselected proposal','Private unrelated account.')
    row=mc._read_chapter(cid)
    # Isolate the navigation/admission boundary from provider availability.
    monkeypatch.setattr(mc,'embeddings_runtime_config',lambda **kw: dict(provider='fixture',model='fixture',output_dimensionality=None))
    def candidates(query,**kw):
        assert kw.get('record_uids')==[row['record_uid']]
        return dict(items=[dict(row,score=0.34)],retrieval_status='ok',backend_errors=[])
    monkeypatch.setattr(mc,'hybrid_candidates',candidates)
    before=mc.DB_PATH.read_bytes()
    assert mc.hybrid_pack('brace',threshold=0.4,record_uids=[row['record_uid']],_record_access=False)['items']==[]
    monkeypatch.setitem(sys.modules,mc.__name__,mc)
    monkeypatch.setattr(sys,'argv',['memoryctl.py','hybrid-search','--query','brace','--record-uid',row['record_uid']])
    mc.main()
    result=json.loads(capsys.readouterr().out)
    assert result['navigation_only'] and [x['id'] for x in result['items']]==[cid]
    assert result['items'][0]['relevance'].startswith('unassessed')
    assert 'Private unrelated' not in json.dumps(result)
    assert mc.DB_PATH.read_bytes()==before and mc._read_chapter(other)['revision']==1


def test_source_excerpt_is_navigation_only_and_does_not_replace_evidence(setup):
    from tests.test_source_preview import envelope
    import deep_recall
    mc, p = setup
    raw=envelope('assistant_statement','Jo proposed a brace; delivery was not confirmed.')
    cid=mc.add_text('episodes','Yes, please proceed',raw)
    uid=mc._read_chapter(cid)['record_uid']
    reader=deep_recall.Reader(mc.DB_PATH,select(mc,p,[cid]))
    before=mc.DB_PATH.read_bytes()
    args=dict(action='search',query='brace',record_uid='',offset=0)
    found=reader.call(args)['items'][0]
    assert found['source_excerpt']['quote']=='Jo proposed a brace; delivery was not confirmed.'
    assert found['source_excerpt']['navigation_only']
    assert reader.call(dict(args,action='read',query='',record_uid=uid))['raw']==raw
    assert mc.DB_PATH.read_bytes()==before
    mc.update_chapter(cid,content='Correction: Jo proposed a wedge.')
    reader=deep_recall.Reader(mc.DB_PATH,select(mc,p,[cid]))
    old=reader.call(args)['historical_matches'][0]
    assert old['historical'] and 'source_excerpt' not in old


def test_optional_excerpt_does_not_break_small_response_budget(setup):
    from tests.test_source_preview import envelope
    import deep_recall
    mc, p=setup
    ids=[mc.add_text('episodes','Brace '+str(i),envelope('Human report','Brace '+('context '*80))) for i in range(3)]
    reader=deep_recall.Reader(mc.DB_PATH,select(mc,p,ids),max_bytes=2000)
    result=reader.call(dict(action='search',query='brace',record_uid='',offset=0))
    assert result['status']=='ok' and len(result['items'])==3
    assert all('source_excerpt' not in row for row in result['items'])


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
