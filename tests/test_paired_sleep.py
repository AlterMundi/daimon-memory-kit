"""A new pair worker captures only prospective, authenticated human input."""
import json
import sqlite3

import pytest

import paired_sleep
import sleep_triage
from tests.test_forward_capture import append, line, turn
from tests.test_sleep_triage import fake_decisions


def test_paired_scope_survives_restart_and_refuses_replacement(tmp_path, monkeypatch):
    journal = tmp_path/'sessions'
    journal.mkdir()
    native_id = '00839024-0abc-410c-8001-3eecbe2ab250'
    source = journal/f'rollout-2026-11-26-{native_id}.jsonl'
    source.write_bytes(line('session_meta', dict(id=native_id, cwd='/work', timestamp='2026-10-13T00:00:00Z'))
                       + turn('old', 'Pre-authorization transcript.'))
    native, gateway = tmp_path/'native.sqlite', tmp_path/'gateway.sqlite'
    with sqlite3.connect(native) as con:
        con.execute('create table threads(id, rollout_path, cwd, archived)')
        con.execute('insert into threads values(?,?,?,0)',(native_id,str(source),'/work'))
    with sqlite3.connect(gateway) as con:
        con.executescript('create table sessions(creator_user_id,chat_id,thread_id,force_fresh_thread,codex_thread_id);'
                          'create table users(tg_user_id,allowed); insert into users values(501,1)')
        con.execute('insert into sessions values(501,501,1,0,?)',(native_id,))
    root = tmp_path/'sleep'
    root.mkdir(mode=0o700)
    profile = dict(source_root=str(journal), native_db=str(native), conversation_db=str(gateway),
                   being_ref='fictional-being', body_ref='fictional-body')
    paired_sleep.enroll(profile, root)
    paired_sleep.enroll(profile, root)

    def entry(author, text):
        meta = dict(author=None, authorized_human=author, original_human_author=author)
        return ('[Interaction controller]\nTransport provenance: '+json.dumps(meta)
                +'\nCurrent attributed input:\n'+text+'\n\nReturn your answer followed by <daimon-result>')

    append(source, turn('unframed', 'A local operator prompt.')
           + turn('other', entry(999, 'Another conversation participant.'))
           + turn('authorized', entry(501, 'Renata came to visit.')))
    real_run = sleep_triage.run
    observed = []

    def decide(request, **kwargs):
        observed.append(request.data)
        return fake_decisions(request, **kwargs)

    monkeypatch.setenv('DMK_DECISIONS_API_KEY','fictional')
    monkeypatch.setattr(sleep_triage,'run',lambda *a, **kw: real_run(*a, **kw, opener=decide))
    result = paired_sleep.run(profile, root)
    assert result['triage']['classified_pages'] == 1 and result['state'] == 'caught_up'
    health = json.loads((root/'worker-status.json').read_text())['sleep_health']
    assert health['matrix']['source_review']['status'] == 'unobserved'
    assert b'Renata came' in b''.join(observed)
    for forbidden in (b'Pre-authorization', b'operator prompt', b'Another conversation'):
        assert forbidden not in b''.join(observed)
    paired_sleep.run(profile, root)
    assert len(observed) == 1

    with sqlite3.connect(gateway) as con:
        con.execute('update sessions set force_fresh_thread=1')
    assert paired_sleep.run(profile, root)['state'] == 'blocked'
    assert len(observed) == 1
