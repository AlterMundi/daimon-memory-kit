"""A new pair worker captures only prospective, authenticated human input."""
from datetime import datetime, timezone
import json
import sqlite3

import pytest

import memory_runtime
import paired_sleep
import sleep_triage
from capture_inbox import Inbox
from capturectl import CaptureLedger
from sleep_memory_review import apply_review, read_candidate, standalone_library
from tests.test_backupctl import config as backup_config
from tests.test_durable_memory_foundation import mc
from tests.test_forward_capture import append, context, line, turn
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
            proof = dict(source_sha256='typed-voice-proof')
            con.execute("insert into turns values('turn-1',1,501,?,'sending')", (native_id,))
            con.execute("insert into conversation_inputs values(?,501,1,?,'sending','turn-1',0,?,?)",
                        (original, native_id, json.dumps(dict(text=gateway_text, voice=dict(transcription=proof))), '2026-11-26T03:00:00+00:00'))
    root = tmp_path/'sleep'
    root.mkdir(mode=0o700)
    profile = dict(source_root=str(journal), native_db=str(native), conversation_db=str(gateway),
                   being_ref='fictional-being', body_ref='fictional-body')
    if configured_entry:
        config = tmp_path/'conversation.toml'
        config.write_text(f'db_path = {json.dumps(str(gateway))}\n[interaction]\n'
                          f'human_id = 501\nchat_id = {chat}\ntopic_id = {topic}\n')
        profile['conversation_config'] = str(config)
        profile['voice_transcripts'] = True
        with pytest.raises(ValueError, match='configuration and registry differ'):
            paired_sleep.enroll(dict(profile, conversation_db=str(native)), root)
    paired_sleep.enroll(profile, root)
    paired_sleep.enroll(profile, root)
    binding = json.loads((root/'binding.json').read_text())['binding']
    triage = root/'triage'
    assert sleep_triage.run(binding, triage, after=0, human_id=501)['state'] == 'caught_up'
    pending = triage/'dispatch.json'
    pending.write_text('{"request_sha256":"retained"}')
    with paired_sleep.original_resolver(profile, binding, 501) as resolver:
        with pytest.raises(ValueError, match='triage cursor binding or policy differs'):
            sleep_triage.run(binding, triage, human_id=501, gateway_original=resolver)
    assert pending.read_text() == '{"request_sha256":"retained"}'
    pending.unlink()

    def entry(author, text):
        meta = dict(author=None, authorized_human=author, original_human_author=author)
        return ('[Interaction controller]\nTransport provenance: '+json.dumps(meta)
                +'\nCurrent attributed input:\n'+text+'\n\nReturn your answer followed by <daimon-result>')

    append(source, turn('unframed', 'A local operator prompt.')
           + turn('other', entry(999, 'Another conversation participant.'))
           + turn('authorized', entry(501, 'Renata came to visit.')))
    if configured_entry:
        with sqlite3.connect(gateway) as con:
            con.execute('update conversation_inputs set created_at=? where id=?',
                        (datetime.now(timezone.utc).isoformat(), original))
        frame = '[Original conversation input]\n' + json.dumps(dict(input_ref=original)) + '\nmetadata\n\n'
        typed = ('[Committed voice input]\nCapture: '+original+'\nAutomatic interpretation.\nProvenance: '
                 +json.dumps(proof)+'\n\n')
        append(source, turn('altered', frame+typed+'This is fabricated text.')
               + turn('gateway', frame+typed+gateway_text))

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
        with paired_sleep.original_resolver(profile, binding, 501) as resolver:
            candidate = read_candidate(binding, triage, packet.stem, 0, gateway_original=resolver,
                                       voice_transcripts=True)
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
        assert 'automatic-transcript:'+original in json.loads(record['source_metadata_json'])['evidence']
    paired_sleep.run(profile, root)
    assert len(observed) == (2 if configured_entry else 1)

    with sqlite3.connect(gateway) as con:
        con.execute('update sessions set force_fresh_thread=1')
    assert paired_sleep.run(profile, root)['state'] == 'blocked'
    assert len(observed) == (2 if configured_entry else 1)

def test_supervised_paired_slot_inherits_budget_and_projects_failure(context, tmp_path, monkeypatch):
    binding, _, _ = context
    inbox = Inbox(binding['inbox'], binding)
    paired = tmp_path/'paired'
    paired.mkdir(mode=0o700)
    profile = tmp_path/'paired.json'
    profile.write_text(json.dumps(dict(state_dir=str(paired), being_ref=binding['subject'],
                                      body_ref=binding['source_instance'])))
    profile.chmod(0o600)
    legacy = tmp_path/'old-triage'
    legacy.mkdir()
    value = dict(state_dir=str(tmp_path), context=binding, sleep_triage=dict(
        state_dir=str(legacy), paired_profile=str(profile), steps=1,
        credential_env='EXISTING_DECISIONS', max_age_seconds=93600, source_review_report=None))
    status = tmp_path/'worker-status.json'
    calls = []
    result = dict(status=dict(state='idle'))

    def supervisor():
        status.write_text(json.dumps(result['status']))
        memory_runtime.run_paired_sleep(value, inbox, result)
        return json.loads(status.read_text())['sleep_triage']

    def one_slot(profile_value, root, *, worker_settings):
        calls.append((worker_settings['steps'], worker_settings['credential_env']))
        if len(calls) == 1:
            return dict(state='blocked', reason_code='observation_unreadable')
        return dict(state='caught_up', capture_complete=True, triage=dict(classified_pages=0))

    monkeypatch.setattr(paired_sleep, 'run', one_slot)
    attempted = legacy/'dispatch.json'
    attempted.write_bytes(b'retained')
    assert supervisor()['state'] == 'blocked'
    assert not calls and attempted.read_bytes() == b'retained'
    attempted.unlink()
    assert supervisor()['state'] == 'blocked'
    assert supervisor()['capture_complete']
    assert calls == [(1, 'EXISTING_DECISIONS')]*2
    with inbox.connect() as con:
        alert, = con.execute("select state from operational_alerts").fetchall()
        assert alert['state'] == 'resolved'

def test_paired_cycle_reuses_owner_baseline_without_copy(backup_config, context, tmp_path, monkeypatch):
    from periodic_backups import Baselines
    import periodic_backups

    binding, _, _ = context
    root = tmp_path/'selected'
    root.mkdir(mode=0o700)
    (root/'binding.json').write_text(json.dumps(dict(binding=binding)))
    monkeypatch.setattr(paired_sleep, 'verified_binding', lambda profile, config: config['binding'])
    policy = backup_config['snapshots']
    policy['routine_backup'] = dict(directory=str(tmp_path/'baselines'), subject=binding['subject'],
                                    interval_seconds=86400)
    pool = Baselines(backup_config['database'], policy)
    assert pool.refresh()['created']

    def no_copy(*args, **kwargs):
        pytest.fail('unchanged canonical owner does not need a new snapshot')

    monkeypatch.setattr(periodic_backups, 'verified_snapshot', no_copy)
    backup = tmp_path/'backup-profile.json'
    backup.write_text(json.dumps(backup_config))
    backup.chmod(0o600)
    info = paired_sleep.maintain_backup(dict(backup_profile=str(backup)), root)
    assert info['state'] == 'current' and not info['created']
    assert 'snapshot' not in info and 'sha256' not in info
    monkeypatch.delenv('HMK_DB_PATH', raising=False)
    monkeypatch.delenv('HMK_AGENT_MEMORY_BASE', raising=False)
    assert standalone_library(dict(backup_profile=str(backup)), binding) == dict(
        database=str(pool.database), memory_base=str(pool.database.parent))
    monkeypatch.setenv('HMK_DB_PATH', str(tmp_path/'another-library.db'))
    with pytest.raises(ValueError, match='database binding differs'):
        standalone_library(dict(backup_profile=str(backup)), binding)
    policy['routine_backup']['subject'] = 'foreign'
    backup.write_text(json.dumps(backup_config))
    with pytest.raises(ValueError, match='owner differ'):
        paired_sleep.maintain_backup(dict(backup_profile=str(backup)), root)

def test_committed_voice_requires_exact_retained_transcript_and_typed_proof(tmp_path):
    ref = 'c095b1da-26d2-4d2c-8eff-7c1ddaf5fa70'
    words = 'Nos encontramos mirando el amanecer.'
    proof = dict(capture_stop='duration_limit', source_sha256='fixture-voice-proof')
    original = dict(text=words, voice=dict(transcription=proof))
    typed = ('[Committed voice input]\nCapture: ' + ref
             + '\nAutomatic interpretation.\nProvenance: ' + json.dumps(proof) + '\n')
    rendered = typed + paired_sleep.VOICE_WARNINGS['duration_limit'] + '\n' + words
    assert paired_sleep.committed_voice_matches(rendered, ref, original)
    assert not paired_sleep.committed_voice_matches(rendered + ' Extra words.', ref, original)
    assert not paired_sleep.committed_voice_matches(rendered, 'another-original', original)
    assert not paired_sleep.committed_voice_matches(rendered.replace('fixture-voice-proof', 'changed-proof'), ref, original)


def test_telegram_text_requires_exact_owner_turn_and_text(tmp_path):
    registry = tmp_path/'gateway.sqlite'
    native = 'fixture-thread'
    selected_text = 'We watched the sunrise from the pier.'
    with sqlite3.connect(registry) as con:
        con.executescript("create table incoming_updates(update_id, turn_id, payload_json, status);"
                          "create table turns(id, session_id, from_user_id, native_thread_id, status);"
                          "create table sessions(id, creator_user_id, chat_id, thread_id);"
                          "create table original_ingress_order(channel, event_id, captured_at);"
                          "create table interaction_native_messages(local_turn, native_thread, native_turn);"
                          "insert into sessions values(1,501,-501,7);")
        payload = dict(message=dict(chat=dict(id=-501), message_thread_id=7, text=selected_text,
                                    **{'from':dict(id=501)}))
        con.execute("insert into turns values(1,1,501,?,'running')", (native,))
        con.execute("insert into incoming_updates values(111,1,?,'settled')", (json.dumps(payload),))
        con.execute("insert into original_ingress_order values('telegram','111','2026-11-26T03:00:00+00:00')")
        border = datetime.fromisoformat('2026-11-26T02:00:00+00:00')

        def resolve(text, *, turn=None):
            return paired_sleep.telegram_original(con, (501,-501,7), native, turn, text, not_before=border)

        with pytest.raises(ValueError, match='native turn is not settled'):
            list(sleep_triage.pages_for(turn('selected', selected_text), 'fixture', 'body',
                                       human_id=501, gateway_original=resolve))
        con.execute("insert into interaction_native_messages values(1,?,'selected')", (native,))
        con.execute("update turns set status='completed'")
        delta = turn('neighbor', selected_text) + turn('selected', selected_text) + turn('changed', 'Edited text.')
        page, = sleep_triage.pages_for(delta, 'fixture', 'body', human_id=501, gateway_original=resolve)
        item, = page
        assert item['text'] == selected_text and item['original_channel'] == 'telegram'
        assert item['original_input_ref'] == '111'
        assert not paired_sleep.telegram_original(con, (501,-501,7), native, 'selected', selected_text,
                                                  not_before=datetime.fromisoformat('2026-11-26T04:00:00+00:00'))
