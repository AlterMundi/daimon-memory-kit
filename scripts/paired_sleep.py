"""Run Decisions over one explicitly approved, forward-only general conversation."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import tomllib
import uuid

from capture_inbox import Inbox, sha, wire
from codex_coordinator import checkpoint
from codex_hook_capture import capture
import forward_capture
from provider_status import Alerts, ProviderProblem

SCHEMA = 'dmk.paired-sleep/v1'
FOREGROUND_SCHEMA = 'dmk.paired-foreground-inputs/v1'


def readonly(path):
    return closing(sqlite3.connect(Path(path).resolve(strict=True).as_uri() + '?mode=ro', uri=True))


def conversation_registry(profile):
    registry = Path(profile['conversation_db']).resolve(strict=True)
    config_path = profile.get('conversation_config')
    if config_path is None:
        return registry, None
    with Path(config_path).open('rb') as source:
        config = tomllib.load(source)
    configured_registry = Path(config['db_path'])
    if not configured_registry.is_absolute() or configured_registry.resolve(strict=True) != registry:
        raise ValueError('Conversation configuration and registry differ')
    entry = config['interaction']
    coordinates = (entry['human_id'], entry['chat_id'], entry['topic_id'])
    if any(type(value) is not int or value == 0 for value in coordinates):
        raise ValueError('invalid configured Conversation coordinates')
    return registry, coordinates


def enrolled_thread(profile):
    """Resolve only the current paired human's enrolled general entry."""
    registry, coordinates = conversation_registry(profile)
    if coordinates is None:
        selection = 's.chat_id = u.tg_user_id AND s.thread_id = 1'
        coordinates = ()
    else:
        selection = 's.creator_user_id = ? AND s.chat_id = ? AND s.thread_id = ?'
    with readonly(registry) as con:
        rows = con.execute(f'''
            SELECT s.creator_user_id, s.codex_thread_id
              FROM sessions s JOIN users u ON u.tg_user_id = s.creator_user_id
             WHERE u.allowed=1 AND s.force_fresh_thread=0 AND length(s.codex_thread_id)>0
               AND {selection}
        ''', coordinates).fetchall()
    if len(rows) != 1:
        raise ValueError('one active paired general conversation is required')
    with readonly(profile['native_db']) as con:
        row = con.execute('SELECT rollout_path, cwd FROM threads WHERE id=? AND archived=0',
                          (rows[0][1],)).fetchone()
    if not row:
        raise ValueError('native source is not available')
    return (*rows[0], *row)


def gateway_original(con, coordinates, native, block, *, not_before=None,
                     voice_transcripts=False, foreground_voice_transcripts=False,
                     foreground_direct_inputs=False):
    """Accept a native reference only when its text and receiving journal agree."""
    header, separator, text = block.partition('\n\n')
    if header.startswith('[Device-reported playback context]\n'):
        header, separator, text = text.partition('\n\n')
    lines = header.splitlines()
    if (not separator or len(lines) < 2 or lines[0] not in {
            '[Original conversation input]', '[Device-reported conversational context]'}):
        return None
    try:
        ref = json.loads(lines[1])['input_ref']
        if str(uuid.UUID(ref)) != ref:
            return None
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    row = con.execute("""
        SELECT c.doc, c.phase, t.status, c.created_at,
               t.session_id=s.id AND t.from_user_id=c.human_id AND t.native_thread_id=c.native_thread
          FROM conversation_inputs c JOIN sessions s ON s.id=c.session_id
          LEFT JOIN turns t ON t.id=c.local_turn
         WHERE c.id=? AND c.human_id=? AND s.chat_id=? AND s.thread_id=?
           AND c.native_thread=? AND c.retired=0
    """, (ref, *coordinates, native)).fetchone()
    if row is None:
        return None
    doc, phase, turn, received_at, linked = row
    value = json.loads(doc)
    original = value.get('text')
    if not isinstance(original, str) or value.get('tribu_source'):
        return None
    foreground = text.startswith('[Voice foreground formulation]\n')
    if foreground:
        if not foreground_voice_transcripts:
            return None
        text = foreground_original(text, value)
        if text is None:
            return None
    live = foreground and text.startswith('[Live input transcript window]\n')
    voice = text.startswith('[Committed voice input]\n')
    if voice:
        if foreground and foreground_direct_inputs and direct_voice_input(value, ref):
            return None  # The Gateway feed owns this original before and after native delegation.
        if not voice_transcripts or not committed_voice_matches(text, ref, value):
            return None
    elif live:
        if not live_window_matches(text, value):
            return None
    elif foreground:
        return None
    elif text != original:
        return None
    if not_before is not None:
        received = datetime.fromisoformat(received_at)
        if received.tzinfo is None or received < not_before:
            return None
    if phase in {'sending', 'steering', 'uncertain'} or (
            phase == 'accepted' and (not linked or turn not in {'completed', 'failed', 'cancelled'})):
        raise ValueError('Gateway original has no settled native linkage')
    if phase != 'accepted':
        return None
    accepted = dict(text=original, original_input_ref=ref, received_at=received_at)
    if voice:
        accepted['channel'] = 'human_voice_transcription'
        if foreground and direct_voice_input(value, ref):
            accepted['foreground_direct'] = True
    if live:
        accepted['channel'] = 'live_input_transcription'
    return accepted


def direct_voice_input(doc, ref):
    voice = doc.get('voice')
    proof = voice.get('transcription') if isinstance(voice, dict) else None
    if not isinstance(proof, dict):
        return False
    audio = proof.get('audio_sha256')
    return (isinstance(audio, str) and len(audio) == 64 and audio == voice.get('audio_sha256')
            and proof.get('capture_id') == ref and bool(doc.get('foreground_dialogue'))
            and not doc.get('tribu_source'))


VOICE_WARNINGS = {
    'duration_limit': 'Device reports recording stopped at the duration limit. The ending may be missing. Do not assume this fragment is the complete request; wait for or clarify the continuation. This warning is system metadata, not human speech.\n',
    'audio_flush_unconfirmed': 'Device could not confirm the final audio buffer. The human explicitly chose to send the retained fragment; its ending may be missing. Do not assume the complete request was captured; wait for or clarify the continuation. This warning is system metadata, not human speech.\n',
}


def committed_voice_matches(rendered, ref, original):
    parsed = rendered.split('\n', 4)
    if len(parsed) != 5 or parsed[1] != 'Capture: ' + ref or not parsed[3].startswith('Provenance: '):
        return False
    try:
        proof = json.loads(parsed[3].removeprefix('Provenance: '))
    except ValueError:
        return False
    voice = original.get('voice')
    if not isinstance(voice, dict) or not isinstance(proof, dict) or not proof or proof != voice.get('transcription'):
        return False
    warning = VOICE_WARNINGS.get(proof.get('capture_stop'), '')
    return parsed[4] == warning + '\n' + original['text']


def foreground_original(rendered, original):
    header, separator, content = rendered.partition('\n\n')
    fields = header.split('\n', 2)
    retained = original.get('foreground_delegation')
    if not separator or len(fields) != 3 or not isinstance(retained, dict):
        return None
    try:
        metadata = json.loads(fields[1])
    except ValueError:
        return None
    if (metadata != retained or not original.get('foreground_dialogue')
            or retained.get('dialogue_id') != original['foreground_dialogue']):
        return None
    return content


def live_window_matches(rendered, original):
    fields = rendered.split('\n', 3)
    if len(fields) != 4 or not fields[2].startswith('Source: '):
        return False
    try:
        proof = json.loads(fields[2].removeprefix('Source: '))
    except ValueError:
        return False
    return (isinstance(proof, dict)
            and proof == original['foreground_delegation'].get('live_window')
            and proof.get('dialogue') == original.get('foreground_dialogue')
            and fields[3] == original['text']
            and proof.get('text_sha256') == hashlib.sha256(fields[3].encode()).hexdigest())


def telegram_original(con, coordinates, native, turn, text, *, not_before):
    """Accept a text update only through its exact retained native turn."""
    if not turn or text.startswith('/') or not text.strip():
        return None
    actor, chat, topic = coordinates
    matches = con.execute("""
        SELECT i.update_id, o.captured_at, t.status,
               EXISTS (SELECT 1 FROM interaction_native_messages m
                        WHERE m.local_turn=t.id AND m.native_thread=? AND m.native_turn=?) AS linked
          FROM incoming_updates i JOIN turns t ON t.id=i.turn_id
          JOIN sessions s ON s.id=t.session_id
          JOIN original_ingress_order o ON o.channel='telegram' AND o.event_id=CAST(i.update_id AS text)
         WHERE s.creator_user_id=? AND s.chat_id=? AND s.thread_id=?
           AND t.from_user_id=? AND t.native_thread_id=?
           AND i.status IN ('started','settled','steering')
           AND json_extract(i.payload_json,'$.message.from.id')=?
           AND json_extract(i.payload_json,'$.message.chat.id')=?
           AND json_extract(i.payload_json,'$.message.message_thread_id')=?
           AND json_extract(i.payload_json,'$.message.text')=?
           AND (linked OR t.status='running')
         ORDER BY linked DESC LIMIT 2
    """, (native, turn, *coordinates, actor, native, actor, chat, topic, text)).fetchall()
    if not matches or sum(row[3] for row in matches) > 1:
        return None
    update, received_at, status, linked = matches[0]
    received = datetime.fromisoformat(received_at)
    if received.tzinfo is None or received < not_before:
        return None
    if not linked or status not in {'completed', 'failed', 'cancelled'}:
        raise ValueError('Telegram original native turn is not settled')
    return dict(text=text, original_input_ref=str(update), original_channel='telegram',
                received_at=received_at)


@contextmanager
def original_resolver(profile, binding, human_id):
    registry, coordinates = conversation_registry(profile)
    coordinates = coordinates if coordinates is not None else (human_id, human_id, 1)
    if coordinates[0] != human_id:
        raise ValueError('Gateway actor differs from paired enrollment')
    boundary = datetime.fromisoformat(binding['sessions_started_at_or_after'])
    with readonly(registry) as con:
        native = binding['selected_session_id']
        original = partial(gateway_original, con, coordinates, native, not_before=boundary,
                           voice_transcripts=profile.get('voice_transcripts') is True,
                           foreground_voice_transcripts=profile.get('foreground_voice_transcripts') is True,
                           foreground_direct_inputs=profile.get('foreground_direct_inputs') is True)

        def resolve(text, *, turn=None):
            found = original(text)
            if found is None and profile.get('telegram_text') is True:
                found = telegram_original(con, coordinates, native, turn, text, not_before=boundary)
            return found

        yield resolve


def capture_foreground(profile, binding, human_id, inbox, *, after):
    """Seal one page of owner-bound Gateway originals inside the existing inbox."""
    registry, coordinates = conversation_registry(profile)
    if coordinates is None:
        coordinates = (human_id, human_id, 1)
    if coordinates[0] != human_id:
        raise ValueError('Gateway actor differs from paired enrollment')
    cutoff = datetime.fromisoformat(binding['sessions_started_at_or_after'])
    with readonly(registry) as conn:
        conn.execute('ATTACH DATABASE ? AS review', (inbox.path.resolve().as_uri() + '?mode=ro',))
        if conn.execute('''
            SELECT 1 FROM review.observations
            WHERE id > ? AND json_extract(payload,'$.schema')=? LIMIT 1
        ''', (after, FOREGROUND_SCHEMA)).fetchone():
            return True
        rows = conn.execute('''
            WITH captured AS MATERIALIZED (
                SELECT value AS ref FROM review.observations a, json_each(a.payload,'$.originals')
                WHERE json_extract(a.payload,'$.schema')=?
            )
            SELECT c.id,c.created_at,c.doc,c.session_id
            FROM conversation_inputs c JOIN sessions s ON s.id=c.session_id
            JOIN original_ingress_order g ON g.channel='conversation' AND g.event_id=c.id
            LEFT JOIN turns t ON t.id=c.local_turn AND t.session_id=c.session_id
                            AND t.from_user_id=c.human_id AND t.native_thread_id=c.native_thread
            WHERE c.human_id=? AND s.chat_id=? AND s.thread_id=? AND c.native_thread=?
              AND c.retired=0 AND c.created_at>=?
              AND ((c.phase='foreground' AND c.local_turn IS NULL) OR
                   (c.phase='accepted' AND t.status IN ('completed','failed','cancelled')))
              AND json_type(c.doc,'$.foreground_dialogue')='text'
              AND json_extract(c.doc,'$.tribu_source') IS NULL
              AND json_extract(c.doc,'$.voice.transcription.capture_id')=c.id
              AND json_extract(c.doc,'$.voice.transcription.audio_sha256')=json_extract(c.doc,'$.voice.audio_sha256')
              AND length(json_extract(c.doc,'$.text'))>0
              AND c.id NOT IN (SELECT ref FROM captured)
            ORDER BY g.id LIMIT 9
        ''', (FOREGROUND_SCHEMA, *coordinates, binding['selected_session_id'],
              cutoff.replace(microsecond=0).isoformat())).fetchall()
    items = []
    for ref, when, encoded, session in rows:
        received = datetime.fromisoformat(when)
        if received < cutoff:
            continue
        doc = json.loads(encoded)
        if (str(uuid.UUID(ref)) != ref or not direct_voice_input(doc, ref)
                or (doc['id'], doc['session'], doc['human'], doc['native'])
                   != (ref, session, human_id, binding['selected_session_id'])
                or not isinstance(doc['text'], str) or len(doc['text'].encode()) > 65536):
            raise ValueError('retained Avatar original differs from its Gateway capture binding')
        items.append(dict(ref=ref, received_at=when, text=doc['text']))
    if not items:
        return False
    batch = items[:8]
    raw = wire(batch).encode()
    payload = dict(schema=FOREGROUND_SCHEMA, originals=[item['ref'] for item in batch],
                   capture_range=dict(header_bytes=0))
    inbox.observe('gateway-foreground:' + sha(raw), payload, raw)
    return len(items) > len(batch)


@contextmanager
def supervised_foreground(path, binding):
    """Resolve an Avatar feed for an existing broad native capture inbox."""
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('private Avatar source profile required')
    profile = json.loads(path.read_text())
    if any(profile[k] != binding[v] for k,v in (('being_ref','subject'),('body_ref','source_instance'))):
        raise ValueError('Avatar source owner differs from the worker')
    human, thread, rollout, _ = enrolled_thread(profile)
    if not Path(rollout).resolve().is_relative_to(Path(binding['source_root']).resolve()):
        raise ValueError('Avatar source is outside the worker journal')
    cutoff = datetime.fromisoformat(profile['starts_at_or_after'])
    if cutoff.tzinfo is None or type(profile['native_observation_after']) is not int or profile['native_observation_after'] < 0:
        raise ValueError('Avatar source requires a fixed observation and time boundary')
    selected = dict(binding, selected_session_id=thread, sessions_started_at_or_after=cutoff.isoformat())
    registry, coordinates = conversation_registry(profile)
    if coordinates is None:
        coordinates = (human, human, 1)
    with readonly(registry) as conn:
        def exclude(block):
            if '[Voice foreground formulation]\n' not in block:
                return False
            original = gateway_original(conn, coordinates, thread, block, not_before=cutoff,
                                        voice_transcripts=True, foreground_voice_transcripts=True)
            return original is not None and original.get('foreground_direct') is True
        yield profile, selected, human, exclude


def enroll(profile, root):
    human, session, transcript, cwd = enrolled_thread(profile)
    source = Path(profile['source_root']).resolve(strict=True)
    path = Path(transcript)
    if path.resolve() != path or not path.is_relative_to(source):
        raise ValueError('native source is outside its owner journal')
    binding = dict(schema='hmk.codex-hook-binding/v2', subject=profile['being_ref'],
                   source_instance=profile['body_ref'], source_root=str(source),
                   allowed_cwds=[cwd], inbox=str(root/'capture.sqlite'),
                   max_source_bytes=32*1024*1024, selected_session_id=session,
                   sessions_started_at_or_after=datetime.now(timezone.utc).isoformat())
    config = dict(schema=SCHEMA, human_id=human, transcript=transcript, cwd=cwd, binding=binding)
    saved = root/'binding.json'
    if saved.exists():
        existing = json.loads(saved.read_bytes())
        config['binding']['sessions_started_at_or_after'] = existing['binding']['sessions_started_at_or_after']
        if existing != config or not forward_capture.policy(binding['inbox']):
            raise ValueError('existing paired source requires explicit reconciliation')
        return
    forward_capture.activate(binding, root/'capture-before.sqlite')
    checkpoint(saved, config)


def verified_binding(profile, config):
    binding = config['binding']
    if (binding['subject'] != profile['being_ref'] or binding['source_instance'] != profile['body_ref']
            or Path(binding['source_root']).resolve() != Path(profile['source_root']).resolve()):
        raise ValueError('the authorized paired source owner has changed')
    actual = enrolled_thread(profile)
    if actual != (config['human_id'], binding['selected_session_id'], config['transcript'], config['cwd']):
        raise ValueError('the authorized native entry has changed')
    return binding


def run(profile, root, *, worker_settings=None):
    config = json.loads((root/'binding.json').read_bytes())
    if config['schema'] != SCHEMA:
        raise ValueError('unsupported paired binding')
    binding = config['binding']
    inbox = Inbox(binding['inbox'], binding)
    alerts = Alerts(inbox)
    operation = 'paired-sleep-input'
    triage = root/'triage'
    cursor = triage/'cursor.json'
    initial = None if cursor.exists() else 0
    foreground_direct_inputs = profile.get('foreground_direct_inputs') is True
    try:
        verified_binding(profile, config)
        payload = dict(hook_event_name='Stop', session_id=binding['selected_session_id'],
                       transcript_path=config['transcript'], cwd=config['cwd'])
        source = capture(binding, payload)
        if source['error'] not in (None, 'capture_deferred'):
            raise ValueError('captured source is unavailable')
        foreground_remaining = False
        if foreground_direct_inputs:
            if profile.get('foreground_voice_transcripts') is not True:
                raise ValueError('Avatar source requires the selected foreground voice policy')
            current = json.loads(cursor.read_text()) if cursor.exists() else dict(after=0,page=0)
            if (not current.get('foreground_direct_inputs')
                    and (current['after'] or current['page'] or current.get('consumed_dispatches')
                         or any((triage / name).exists()
                                for name in ('dispatch.json','context-dispatch.json','rejections'))
                         or any((triage / 'packets').glob('*.json')))):
                raise ValueError('Avatar source selection requires an unadvanced triage cursor')
            foreground_remaining = capture_foreground(profile, binding, config['human_id'], inbox,
                                                       after=current['after'])
    except (ValueError, KeyError, OSError, sqlite3.Error):
        error = ProviderProblem('dmk', operation, dict(code='observation_unreadable'))
        alert = alerts.report(operation, 'selection', error, reopen=True)
        return dict(state='blocked', reason_code='observation_unreadable', alert_id=alert)
    if source['capture_complete']:
        alerts.resolve(operation)
    status = dict(schema='hmk.worker-status/v1', state='complete', observed=True,
                  owner='paired-sleep', updated_ns=time.time_ns(), phases={})
    # Reuse the owning DMK outbox and exact received-result reconciliation.
    from memory_runtime import run_sleep_triage
    checkpoint(root/'worker-status.json', status)
    saved = dict(status=status)
    settings = dict(state_dir=str(triage), initial_after=initial, steps=4,
                    human_id=config['human_id'], credential_env='DMK_DECISIONS_API_KEY',
                    max_age_seconds=93600, source_review_report=profile.get('source_review_report'))
    if worker_settings is not None:
        settings.update({key: worker_settings[key] for key in
                         ('steps', 'credential_env', 'max_age_seconds')})
        if 'provider_blocked' in worker_settings:
            settings['provider_blocked'] = worker_settings['provider_blocked']
    value = dict(state_dir=str(root), sleep_triage=settings)
    with original_resolver(profile, binding, config['human_id']) as resolver:
        run_sleep_triage(value, inbox, binding, saved, gateway_original=resolver,
                         telegram_text=profile.get('telegram_text') is True,
                         voice_transcripts=profile.get('voice_transcripts') is True,
                         foreground_voice_transcripts=profile.get('foreground_voice_transcripts') is True,
                         foreground_direct_inputs=foreground_direct_inputs)
    out = saved['status']['sleep_triage']
    capture_complete = source['capture_complete'] and not foreground_remaining
    return dict(triage=out, state=('pending' if out['state'] != 'blocked' and not capture_complete else out['state']),
                capture_complete=capture_complete)


def owner_backup_profile(profile, binding):
    import snapshot_store

    path = Path(profile['backup_profile'])
    if (not path.is_absolute() or path.is_symlink() or path.stat().st_uid != os.getuid()
            or path.stat().st_mode & 0o077):
        raise ValueError('private backup profile required')
    backup = json.loads(path.read_bytes())
    policy = snapshot_store.policy(backup['snapshots'])
    if policy['routine_backup']['subject'] != binding['subject']:
        raise ValueError('backup and paired source owner differ')
    return backup['database'], policy


def maintain_backup(profile, root):
    """Refresh the selected canonical owner's existing periodic protection."""
    from memory_runtime import backup_notice
    from periodic_backups import Baselines

    config = json.loads((root/'binding.json').read_bytes())
    binding = verified_binding(profile, config)
    inbox = Inbox(binding['inbox'], binding)
    database, policy = owner_backup_profile(profile, binding)
    try:
        pool = Baselines(database, policy)
        if not pool.manifest_path.is_file():
            raise ValueError('existing paired baseline enrollment required')
        result = pool.refresh()
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        result = dict(state='failed', reason_code='backup_state_unreadable')

    return backup_notice(dict(database=database, snapshots=policy,
                              context={k: binding[k] for k in ('subject', 'source_instance')}),
                         inbox, result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('enroll', 'run'))
    p.add_argument('--profile', required=True, type=Path)
    args = p.parse_args()
    os.umask(0o077)
    profile = json.loads(args.profile.read_bytes())
    root = Path(profile['state_dir'])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError('private owner state required')
    with (root/'paired.lock').open('ab') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'enroll':
            enroll(profile, root)
            print(json.dumps(dict(state='enrolled')))
            return
        backup = maintain_backup(profile, root) if 'backup_profile' in profile else None
        credential = os.environ.get('CREDENTIALS_DIRECTORY')
        key = (Path(credential)/'dmk-decisions').read_text().strip() if credential else sys.stdin.read(1025).strip()
        if not 10 < len(key) <= 1024 or any(char.isspace() for char in key):
            raise ValueError('existing scoped Decisions credential required')
        os.environ['DMK_DECISIONS_API_KEY'] = key
        outcome = run(profile, root)
        if backup is not None:
            outcome['backup'] = backup
        checkpoint(root/'receiving.json', outcome)
        print(json.dumps(outcome))
        if outcome['state'] == 'blocked' or (backup is not None and backup['state'] == 'failed'):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
