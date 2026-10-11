"""Canonical/view loss, replay and origin witnesses on fictional HMK only."""
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    base = tmp_path/'canon'
    base.mkdir()
    monkeypatch.setenv('HMK_AGENT_MEMORY_BASE', str(base))
    monkeypatch.setenv('HMK_DB_PATH', str(base/'library.db'))
    spec = importlib.util.spec_from_file_location('projection_memory_fixture', SCRIPTS/'memoryctl.py')
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    mc.init_db()
    import codex_projection as projection
    return mc, projection


def select(mc, projection, records):
    return dict(schema=projection.SELECTION, being_ref='fixture:being:ilex', body_ref='fixture:body:voice',
                records=[dict(record_uid=mc._read_chapter(cid)['record_uid'],
                              revision=mc._read_chapter(cid)['revision'],
                              applicability=dict(kind='being', targets=[])) for cid in records])


def test_original_meaning_unknown_fields_and_provenance_survive_source_free_projection(setup, tmp_path):
    mc, p = setup
    cid = mc.add_text('episodes', 'Failed invitation', 'Ren drafted an invitation, but delivery failed.',
                     metadata=dict(mode='observed', source_instance='fixture:body:code'), event_ts=42)
    selection = select(mc, p, [cid])
    selection['unknown_extension'] = {'retained': True}
    selection['records'][0]['future_field'] = 'keep this original'
    root = tmp_path/'view'
    before = mc.DB_PATH.read_bytes()
    manifest = p.publish(mc.DB_PATH, selection, root, writers_stopped=True)
    assert mc.DB_PATH.read_bytes() == before
    original = json.loads(next((root/'originals').glob('*.json')).read_text())
    assert original['original']['raw'] == mc._read_chapter(cid)['raw']
    assert original['selection_original']['future_field'] == 'keep this original'
    assert manifest['selection_original']['unknown_extension']['retained']
    assert 'delivery failed' in next((root/'rollout_summaries').glob('*.md')).read_text()
    mc.DB_PATH.rename(tmp_path/'unavailable-canon.db')
    assert p.verify(root)['projection_id'] == manifest['projection_id']
    with pytest.raises(ValueError, match='existing regular'):
        p.verify(root, database=mc.DB_PATH)


def test_correction_invalidates_old_view_preserves_original_history_and_rebuilds(setup, tmp_path):
    mc, p = setup
    cid = mc.add_text('library', 'Replay result', 'All three nodes recovered.')
    old = select(mc, p, [cid])
    p.publish(mc.DB_PATH, old, tmp_path/'old', writers_stopped=True)
    mc.update_chapter(cid, content='Two nodes recovered; the third lost readings.', expected_revision=1)
    with pytest.raises(ValueError, match='missing or changed'):
        p.verify(tmp_path/'old', database=mc.DB_PATH)
    with pytest.raises(ValueError, match='missing or changed'):
        p.publish(mc.DB_PATH, old, tmp_path/'stale', writers_stopped=True)
    assert not (tmp_path/'stale').exists()
    p.publish(mc.DB_PATH, select(mc, p, [cid]), tmp_path/'new', writers_stopped=True)
    assert 'third lost' in next((tmp_path/'new/rollout_summaries').glob('*.md')).read_text()
    assert mc.history(cid)[0]['raw'] == 'All three nodes recovered.'
    assert 'All three' in next((tmp_path/'old/rollout_summaries').glob('*.md')).read_text()


def test_dependent_account_cannot_be_projected_after_its_support_changes(setup, tmp_path):
    mc, p = setup
    source = mc.add_text('episodes', 'Trial', 'A broad successful trial was reported.')
    ref = mc._read_chapter(source)
    account = mc.add_text('library', 'Project account', 'The trial succeeded.',
                         metadata=dict(evidence=[f'mem:{ref["record_uid"]}@1']))
    selection = select(mc, p, [account])
    mc.update_chapter(source, content='Correction: only two nodes recovered.')
    with pytest.raises(ValueError, match='reconciliation'):
        p.publish(mc.DB_PATH, selection, tmp_path/'unsafe', writers_stopped=True)


def test_temporary_expiry_requires_refresh_without_canonical_writes(setup, tmp_path):
    mc, p = setup
    cid = mc.add_text('library', 'Reusable procedure', 'Preserve event timestamps during replay.')
    selection = select(mc, p, [cid])
    selection['temporary_context'] = [dict(key='ci', text='Job 719 is pending.', expires_at=20,
                                         applicability=dict(kind='project', targets=['HarborMesh']))]
    before = mc.DB_PATH.read_bytes()
    p.publish(mc.DB_PATH, selection, tmp_path/'early', writers_stopped=True, now=10)
    assert (tmp_path/'early/temporary_context.md').exists()
    with pytest.raises(ValueError, match='expired'):
        p.verify(tmp_path/'early', now=20)
    p.publish(mc.DB_PATH, selection, tmp_path/'late', writers_stopped=True, now=20)
    assert not (tmp_path/'late/temporary_context.md').exists()
    assert '719' not in (tmp_path/'late/memory_summary.md').read_text()
    assert mc.DB_PATH.read_bytes() == before


@pytest.mark.parametrize('failure', ['missing', 'altered', 'extra', 'symlink'])
def test_view_loss_and_unpreserved_native_changes_are_detected(setup, tmp_path, failure):
    mc, p = setup
    selection = select(mc, p, [mc.add_text('library', 'Lesson', 'Verify an actual result.')])
    root = tmp_path/'view'
    p.publish(mc.DB_PATH, selection, root, writers_stopped=True)
    target = root/'MEMORY.md'
    if failure == 'missing':
        target.unlink()
    elif failure == 'altered':
        target.write_text('Invented success')
    elif failure == 'extra':
        (root/'new-native-lesson.md').write_text('Unpreserved native learning')
    else:
        data = target.read_bytes()
        target.unlink()
        outside = tmp_path/'outside.md'
        outside.write_bytes(data)
        target.symlink_to(outside)
    with pytest.raises(ValueError):
        p.verify(root)
    with pytest.raises(ValueError, match='new projection root'):
        p.publish(mc.DB_PATH, selection, root, writers_stopped=True)


def test_origin_is_not_applicability_and_remembered_skill_is_not_a_grant(setup, tmp_path):
    mc, p = setup
    cid = mc.add_text('library', 'Sensor calibration skill', 'The physical body could calibrate sensors.',
                     metadata=dict(mode='observed', source_instance='fixture:body:physical'))
    selection = select(mc, p, [cid])
    selection['records'][0]['applicability'] = dict(kind='body', targets=['fixture:body:physical'])
    manifest = p.publish(mc.DB_PATH, selection, tmp_path/'view', writers_stopped=True)
    text = next((tmp_path/'view/rollout_summaries').glob('*.md')).read_text()
    assert 'fixture:body:physical' in text
    assert manifest['body_ref'] == 'fixture:body:voice'
    assert 'not current grants' in (tmp_path/'view/MEMORY.md').read_text()


def test_native_original_bytes_selected_learning_and_replay_are_preserved(setup):
    mc, p = setup
    mc.add_text('library', 'Existing memory', 'Keep previous shared experience.')
    files = {'skills/replay/SKILL.md': b'Use the explicit offline fixture.\n',
             'original.bin': b'\xff\x00\n'}
    bundle = p.learning_bundle(files, source_instance='fixture:body:code', subject='fixture:being:ilex',
                               source_event_id='native-thread:one', inherited_projection={'projection_id':'old'})
    selected = [dict(key='lesson', operation='add', shelf='library', title='Replay lesson',
                     raw='Choose the explicit offline fixture before trusting the check.',
                     engram_type='procedural')]
    result = p.incorporate(mc, bundle, sequence=1, selected_records=selected,
                          reason='Source-grounded new lesson.', selection_version='fixture:v1')
    old_count = len(mc.search('fixture'))
    replay = p.incorporate(mc, bundle, sequence=1, selected_records=selected,
                          reason='Source-grounded new lesson.', selection_version='fixture:v1')
    assert replay['receipt'] == result['receipt']
    assert len(mc.search('fixture')) == old_count
    assert p.load_learning(mc, bundle['artifact_id']) == files
    lesson = result['receipt']['records']['lesson']['chapter_id']
    assert json.loads(mc._read_chapter(lesson)['source_metadata_json'])['source_instance'] == 'fixture:body:code'
    assert 'artifact:sha256:'+bundle['artifact_id'] in json.loads(mc._read_chapter(lesson)['source_metadata_json'])['evidence']
    assert len(mc.search('Native learned artifact')) == 0
    with mc.connect() as con:
        assert con.execute('SELECT count(*) FROM chapters').fetchone()[0] == 2
    with sqlite3.connect(result['backup']) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert con.execute('SELECT count(*) FROM chapters').fetchone()[0] == 1


def test_invalid_artifact_cannot_mutate_canon_and_replay_cannot_change_selection(setup):
    mc, p = setup
    mc.add_text('library', 'Existing', 'Existing')
    bundle = p.learning_bundle({'lesson.md':b'An actual lesson'}, source_instance='body:a',
                               subject='being:a', source_event_id='thread:a')
    bad = json.loads(json.dumps(bundle))
    bad['members']['lesson.md']['base64'] = 'AAAA'
    before = mc.DB_PATH.read_bytes()
    with pytest.raises(ValueError, match='integrity'):
        p.incorporate(mc, bad, sequence=1, selected_records=[{}], reason='invalid', selection_version='v1')
    assert mc.DB_PATH.read_bytes() == before
    selected = [dict(key='lesson', operation='add', shelf='library', title='A lesson', raw='An actual lesson')]
    p.incorporate(mc, bundle, sequence=1, selected_records=selected, reason='Source support', selection_version='v1')
    selected[0]['raw'] = 'An invented lesson'
    with pytest.raises(ValueError, match='replay differs'):
        p.incorporate(mc, bundle, sequence=1, selected_records=selected, reason='Source support', selection_version='v1')
    assert not mc.search('invented')


def test_publishing_needs_quiescence_and_never_replaces_a_canon(setup, tmp_path):
    mc, p = setup
    selection = select(mc, p, [])
    with pytest.raises(ValueError, match='writers must be stopped'):
        p.publish(mc.DB_PATH, selection, tmp_path/'view')
    with pytest.raises(ValueError, match='new projection root'):
        p.publish(mc.DB_PATH, selection, mc.DB_PATH.parent, writers_stopped=True)


def test_failed_selection_preserves_pending_source_without_partial_artifact_commit(setup):
    mc, p = setup
    cid = mc.add_text('library', 'Current account', 'A legitimate subsequent correction.')
    bundle = p.learning_bundle({'lesson.md': b'A new learning candidate'}, source_instance='body:a',
                               subject='being:a', source_event_id='thread:a')
    invalid = [dict(key='lesson', operation='update', chapter_id=cid, expected_revision=9,
                    raw='Stale overwrite')]
    with pytest.raises(SystemExit, match='revision conflict'):
        p.incorporate(mc, bundle, sequence=1, selected_records=invalid, reason='Candidate', selection_version='v1')
    assert mc._read_chapter(cid)['raw'] == 'A legitimate subsequent correction.'
    with mc.connect() as con:
        assert con.execute('SELECT count(*) FROM native_learning_artifacts').fetchone()[0] == 0
        assert con.execute('SELECT state,payload_json IS NOT NULL FROM capture_events').fetchone()[:] == ('failed', 1)


def test_artifact_loss_blocks_successful_replay_and_subject_mixing_is_refused(setup):
    mc, p = setup
    mc.add_text('library', 'Existing', 'Keep this')
    bundle = p.learning_bundle({'lesson.md': b'An actual lesson'}, source_instance='body:a',
                               subject='being:a', source_event_id='thread:a')
    records = [dict(key='lesson', operation='add', shelf='library', title='A lesson', raw='An actual lesson')]
    wrong = [dict(records[0], metadata=dict(subject='being:b'))]
    before = mc.DB_PATH.read_bytes()
    with pytest.raises(ValueError, match='another subject'):
        p.incorporate(mc, bundle, sequence=1, selected_records=wrong, reason='Candidate', selection_version='v1')
    assert mc.DB_PATH.read_bytes() == before
    p.incorporate(mc, bundle, sequence=1, selected_records=records, reason='Candidate', selection_version='v1')
    with mc.connect() as con:
        con.execute('DELETE FROM native_learning_artifacts')
        con.commit()
    with pytest.raises(ValueError, match='artifact missing'):
        p.incorporate(mc, bundle, sequence=1, selected_records=records, reason='Candidate', selection_version='v1')
