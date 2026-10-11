"""Interrupted native renewal, provenance and preservation on fictional stores."""
import json

import pytest

from tests.test_codex_projection import setup, select


def operation(setup, tmp_path):
    mc, p = setup
    import codex_coordinator as coordinator
    cid = mc.add_text('library', 'Old encounter', 'Mara suggested a local queue; the trial was partial.')
    selection = select(mc, p, [cid])
    home = tmp_path/'receiver'
    home.mkdir()
    p.publish(mc.DB_PATH, selection, home/'memories', writers_stopped=True)
    note = home/'memories/extensions/ad_hoc/notes/units.md'
    note.parent.mkdir(parents=True)
    note.write_text('The local sample check failed without units. Explicit millivolt units passed locally.\n')
    request = dict(schema=coordinator.REQUEST, database=str(mc.DB_PATH), codex_home=str(home),
        selection=selection, learning=dict(source_event_id='native-turn:units', sequence=1,
        selection_version='fixture:source-qualified:v1', reason='Actual new local outcomes; no deployed effect.',
        records=[dict(key='units', operation='add', shelf='library', title='Explicit sample units',
                      raw=note.read_text(), engram_type='procedural')],
        support={'units':[dict(member=note.relative_to(home/'memories').as_posix(),
                               text='Explicit millivolt units passed locally.')]},
        applicability={'units':dict(kind='environment', targets=['fixture:lab-beta'])}))
    return mc, p, coordinator, home, request


def count(mc):
    with mc.connect() as con:
        return con.execute('SELECT count(*) FROM chapters').fetchone()[0]


@pytest.mark.parametrize('point', ['after_capture_commit', 'after_build', 'after_archive', 'after_activate'])
def test_resume_across_commit_and_rename_preserves_originals_and_replays_once(setup, tmp_path, point):
    mc, p, c, home, request = operation(setup, tmp_path)
    note = (home/'memories/extensions/ad_hoc/notes/units.md').read_bytes()
    journal = tmp_path/'journal'
    def interrupt(actual):
        if actual == point:
            raise InterruptedError(point)
    with pytest.raises(InterruptedError):
        c.renew(mc, journal, 'units', request=request, writers_stopped=True, _fault_hook=interrupt)
    state = c.renew(mc, journal, 'units', writers_stopped=True)
    assert state['phase'] == 'complete'
    assert count(mc) == 2
    assert (journal/'units/previous/extensions/ad_hoc/notes/units.md').read_bytes() == note
    assert p.load_learning(mc, state['inputs']['bundle']['artifact_id'])[
        'memory/extensions/ad_hoc/notes/units.md'] == note
    assert p.verify(home/'memories', database=mc.DB_PATH)['projection_id'] == state['projection_id']
    assert state['receipt']['records']['units']['lexical_ready']
    # A completed operation replay must not overwrite legitimate subsequent work.
    later = home/'memories/later-native.md'
    later.write_text('Subsequent native work remains pending.')
    assert c.renew(mc, journal, 'units', request=request, writers_stopped=True) == state
    assert later.read_text() == 'Subsequent native work remains pending.'
    assert count(mc) == 2


def test_projected_recollection_cannot_be_reselected_by_copying_it_to_a_note(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    text = 'Mara suggested a local queue; the trial was partial.'
    (home/'memories/extensions/ad_hoc/notes/units.md').write_text(text)
    request['learning']['records'][0]['raw'] = text
    request['learning']['support']['units'][0]['text'] = text
    with pytest.raises(ValueError, match='projected support'):
        c.renew(mc, tmp_path/'journal', 'copy', request=request, writers_stopped=True)
    assert count(mc) == 1


def test_multiline_original_copy_is_detected_even_when_registry_crops_it(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    cid = mc.add_text('episodes', 'Long episode', 'Navigation prefix '*50+'\nOld partial result.\nNo deployment.')
    # Use another fresh receiver view; inert JSON escapes the newline but the
    # semantic original is decoded when identifying copied source support.
    other = tmp_path/'long-receiver'
    other.mkdir()
    request['codex_home'] = str(other)
    request['selection'] = select(mc, p, [cid])
    p.publish(mc.DB_PATH, request['selection'], other/'memories', writers_stopped=True)
    text = 'Old partial result.\nNo deployment.'
    note = other/'memories/extensions/ad_hoc/notes/units.md'
    note.parent.mkdir(parents=True)
    note.write_text(text)
    request['learning']['support']['units'][0]['text'] = text
    with pytest.raises(ValueError, match='projected support'):
        c.renew(mc, tmp_path/'journal', 'long', request=request, writers_stopped=True)
    assert count(mc) == 2


def test_pending_operation_blocks_another_renewal_and_journal_rebinding(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    def interrupt(point):
        if point == 'after_capture_commit':
            raise InterruptedError()
    with pytest.raises(InterruptedError):
        c.renew(mc, tmp_path/'journal', 'pending', request=request,
                writers_stopped=True, _fault_hook=interrupt)
    with pytest.raises(ValueError, match='pending operation'):
        c.renew(mc, tmp_path/'journal', 'replacement', request=request, writers_stopped=True)
    with pytest.raises(ValueError, match='another journal'):
        c.renew(mc, tmp_path/'other-journal', 'replacement', request=request, writers_stopped=True)
    result = c.renew(mc, tmp_path/'journal', 'pending', writers_stopped=True)
    assert result['phase'] == 'complete'
    assert count(mc) == 2


def test_later_native_writer_drift_blocks_activation_without_losing_either_work(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    def interrupt(point):
        if point == 'after_build':
            raise InterruptedError()
    with pytest.raises(InterruptedError):
        c.renew(mc, tmp_path/'journal', 'drift', request=request, writers_stopped=True, _fault_hook=interrupt)
    pending = home/'memories/later.md'
    pending.write_text('An unquiesced writer added a later outcome.')
    with pytest.raises(ValueError, match='writer drift'):
        c.renew(mc, tmp_path/'journal', 'drift', writers_stopped=True)
    assert pending.read_text() == 'An unquiesced writer added a later outcome.'
    assert count(mc) == 2
    assert (tmp_path/'journal/drift/next-0/hmk-projection.json').exists()


def test_foreign_binding_and_changed_replay_are_refused(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    foreign = json.loads(json.dumps(request))
    foreign['selection']['being_ref'] = 'fixture:being:someone-else'
    with pytest.raises(ValueError, match='different being'):
        c.renew(mc, tmp_path/'journal', 'foreign', request=foreign, writers_stopped=True)
    assert count(mc) == 1
    c.renew(mc, tmp_path/'journal', 'valid', request=request, writers_stopped=True)
    request['learning']['reason'] = 'A changed decision cannot replace its predecessor.'
    with pytest.raises(ValueError, match='replay differs'):
        c.renew(mc, tmp_path/'journal', 'valid', request=request, writers_stopped=True)
    assert count(mc) == 2


def test_relative_home_cannot_change_meaning_after_process_restart(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    request['codex_home'] = 'receiver'
    with pytest.raises(ValueError, match='absolute paths'):
        c.renew(mc, tmp_path/'journal', 'relative', request=request, writers_stopped=True)
    assert count(mc) == 1


def test_no_writer_quiescence_and_corrupt_candidate_cannot_replace_the_view(setup, tmp_path):
    mc, p, c, home, request = operation(setup, tmp_path)
    with pytest.raises(ValueError, match='writers must be stopped'):
        c.renew(mc, tmp_path/'journal', 'candidate', request=request)
    def interrupt(point):
        if point == 'after_build':
            raise InterruptedError()
    with pytest.raises(InterruptedError):
        c.renew(mc, tmp_path/'journal', 'candidate', request=request,
                writers_stopped=True, _fault_hook=interrupt)
    (tmp_path/'journal/candidate/next-0/MEMORY.md').write_text('Altered content')
    with pytest.raises(ValueError, match='content mismatch'):
        c.renew(mc, tmp_path/'journal', 'candidate', writers_stopped=True)
    assert (home/'memories/extensions/ad_hoc/notes/units.md').exists()
    assert not (tmp_path/'journal/candidate/previous').exists()


def test_expired_unpublished_candidate_is_retained_and_rebuilt_after_resume(setup, tmp_path, monkeypatch):
    mc, p, c, home, request = operation(setup, tmp_path)
    clock = [50]
    monkeypatch.setattr(c.time, 'time', lambda: clock[0])
    request['selection']['temporary_context'] = [dict(key='job', text='Job919 is pending.',
        expires_at=60, applicability=dict(kind='project', targets=['fixture:HarborMesh']))]
    def interrupt(point):
        if point == 'after_build':
            clock[0] = 61
            raise InterruptedError()
    with pytest.raises(InterruptedError):
        c.renew(mc, tmp_path/'journal', 'expiry', request=request,
                writers_stopped=True, _fault_hook=interrupt)
    result = c.renew(mc, tmp_path/'journal', 'expiry', writers_stopped=True)
    assert result['build'] == 1
    assert (tmp_path/'journal/expiry/next-0/temporary_context.md').exists()
    assert not (home/'memories/temporary_context.md').exists()
    assert all(b'Job919 is pending.' not in path.read_bytes()
               for path in (home/'memories').rglob('*') if path.is_file())
    assert count(mc) == 2
