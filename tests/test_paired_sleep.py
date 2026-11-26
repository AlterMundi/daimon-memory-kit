"""A new pair worker captures only prospective, authenticated human input."""
import json
import sqlite3

import pytest

import paired_sleep
import sleep_triage
from capturectl import CaptureLedger
from sleep_memory_review import apply_review, read_candidate
from tests.test_durable_memory_foundation import mc
from tests.test_forward_capture import append, line, turn
from tests.test_sleep_triage import fake_decisions


@pytest.mark.parametrize('configured_entry', [False, True])
def test_paired_scope_survives_restart_and_refuses_replacement(tmp_path, monkeypatch, configured_entry, mc):
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
        con.executescript('create table sessions(id integer primary key,creator_user_id,chat_id,thread_id,force_fresh_thread,codex_thread_id);'
                          'create table users(tg_user_id,allowed); insert into users values(501,1)')
        chat, topic = (-100500, 73) if configured_entry else (501, 1)
        con.execute('insert into sessions values(1,501,?,?,0,?)', (chat, topic, native_id))
        if configured_entry:
            con.execute("insert into sessions values(2,501,501,1,0,'unrelated-native-thread')")
            con.executescript('create table conversation_inputs(id, human_id, session_id, native_thread,'
                              'phase, local_turn, retired, doc, created_at);'
                              'create table turns(id, session_id, from_user_id, native_thread_id, status);')
            original = 'c095b1da-26d2-4d2c-8eff-7c1ddaf5fa70'
            gateway_text = 'We watched the sunrise together at the lake.'
            con.execute("insert into turns values('turn-1',1,501,?,'sending')", (native_id,))
            con.execute("insert into conversation_inputs values(?,501,1,?,'sending','turn-1',0,?,?)",
                        (original, native_id, json.dumps(dict(text=gateway_text)), '2026-11-26T03:00:00+00:00'))
    root = tmp_path/'sleep'
    root.mkdir(mode=0o700)
    profile = dict(source_root=str(journal), native_db=str(native), conversation_db=str(gateway),
                   being_ref='fictional-being', body_ref='fictional-body')
    if configured_entry:
        config = tmp_path/'conversation.toml'
        config.write_text(f'db_path = {json.dumps(str(gateway))}\n[interaction]\n'
                          f'human_id = 501\nchat_id = {chat}\ntopic_id = {topic}\n')
        profile['conversation_config'] = str(config)
        with pytest.raises(ValueError, match='configuration and registry differ'):
            paired_sleep.enroll(dict(profile, conversation_db=str(native)), root)
    paired_sleep.enroll(profile, root)
    paired_sleep.enroll(profile, root)

    def entry(author, text):
        meta = dict(author=None, authorized_human=author, original_human_author=author)
        return ('[Interaction controller]\nTransport provenance: '+json.dumps(meta)
                +'\nCurrent attributed input:\n'+text+'\n\nReturn your answer followed by <daimon-result>')

    append(source, turn('unframed', 'A local operator prompt.')
           + turn('other', entry(999, 'Another conversation participant.'))
           + turn('authorized', entry(501, 'Renata came to visit.')))
    if configured_entry:
        frame = '[Original conversation input]\n' + json.dumps(dict(input_ref=original)) + '\nmetadata\n\n'
        append(source, turn('altered', frame+'This is fabricated text.')
               + turn('gateway', frame+gateway_text))

    real_run = sleep_triage.run
    observed = []

    def decide(request, **kwargs):
        observed.append(request.data)
        return fake_decisions(request, **kwargs)

    monkeypatch.setenv('DMK_DECISIONS_API_KEY','fictional')
    monkeypatch.setattr(sleep_triage,'run',lambda *a, **kw: real_run(*a, **kw, opener=decide))
    if configured_entry:
        blocked = paired_sleep.run(profile, root)
        if blocked['state'] == 'pending':
            blocked = paired_sleep.run(profile, root)
        assert blocked['state'] == 'blocked', blocked
        assert len(observed) == 1 and gateway_text.encode() not in observed[0]
        with sqlite3.connect(gateway) as con:
            con.execute("update conversation_inputs set phase='accepted'")
            con.execute("update turns set status='completed'")
    result = paired_sleep.run(profile, root)
    assert result['triage']['classified_pages'] == 1 and result['state'] == 'caught_up'
    health = json.loads((root/'worker-status.json').read_text())['sleep_health']
    assert health['matrix']['source_review']['status'] == 'unobserved'
    assert b'Renata came' in b''.join(observed)
    for forbidden in (b'Pre-authorization', b'operator prompt', b'Another conversation'):
        assert forbidden not in b''.join(observed)
    if configured_entry:
        sent = b''.join(observed)
        assert gateway_text.encode() in sent and original.encode() not in sent
        assert b'fabricated text' not in sent
        triage = root/'triage'
        packet, = [file for file in (triage/'packets').glob('*.json')
                   if any(row.get('original_input_ref') == original
                          for row in json.loads(file.read_text())['sources'])]
        binding = json.loads((root/'binding.json').read_text())['binding']
        with paired_sleep.original_resolver(profile, binding) as resolver:
            candidate = read_candidate(binding, triage, packet.stem, 0, gateway_original=resolver)
        assert candidate['source']['text'] == gateway_text
        assert candidate['source']['original_input_ref'] == original
        ledger = CaptureLedger(mc)
        decision = dict(outcome='applied', reason='first shared sunrise',
                        selection_version='fixture-review/v1',
                        records=[dict(operation='add', key='sunrise', shelf='episodes',
                                      title='Sunrise at the lake', engram_type='episodic', raw=gateway_text)])
        saved = apply_review(ledger, binding, candidate, candidate['fingerprint'], decision)
        assert apply_review(ledger, binding, candidate, candidate['fingerprint'], decision) == saved
        record = mc._read_chapter(saved['records']['sunrise']['chapter_id'])
        assert 'conversation:'+original in json.loads(record['source_metadata_json'])['evidence']
    paired_sleep.run(profile, root)
    assert len(observed) == (2 if configured_entry else 1)

    with sqlite3.connect(gateway) as con:
        con.execute('update sessions set force_fresh_thread=1')
    assert paired_sleep.run(profile, root)['state'] == 'blocked'
    assert len(observed) == (2 if configured_entry else 1)
