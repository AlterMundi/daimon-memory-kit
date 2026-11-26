"""Run Decisions over one explicitly approved, forward-only general conversation."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
from functools import partial
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import tomllib
import uuid

from capture_inbox import Inbox
from codex_coordinator import checkpoint
from codex_hook_capture import capture
import forward_capture
from provider_status import Alerts, ProviderProblem

SCHEMA = 'dmk.paired-sleep/v1'


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


def gateway_original(con, coordinates, native, block, *, not_before=None):
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
    if not isinstance(original, str) or text != original or value.get('tribu_source'):
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
    return dict(text=original, original_input_ref=ref, received_at=received_at)


@contextmanager
def original_resolver(profile, binding):
    registry, coordinates = conversation_registry(profile)
    if coordinates is None:
        yield None
    else:
        with readonly(registry) as con:
            boundary = datetime.fromisoformat(binding['sessions_started_at_or_after'])
            yield partial(gateway_original, con, coordinates, binding['selected_session_id'], not_before=boundary)


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
    try:
        verified_binding(profile, config)
        payload = dict(hook_event_name='Stop', session_id=binding['selected_session_id'],
                       transcript_path=config['transcript'], cwd=config['cwd'])
        source = capture(binding, payload)
        if source['error'] not in (None, 'capture_deferred'):
            raise ValueError('captured source is unavailable')
    except (ValueError, KeyError, OSError, sqlite3.Error):
        error = ProviderProblem('dmk', operation, dict(code='observation_unreadable'))
        alert = alerts.report(operation, 'selection', error, reopen=True)
        return dict(state='blocked', reason_code='observation_unreadable', alert_id=alert)
    if source['capture_complete']:
        alerts.resolve(operation)
    triage = root/'triage'
    initial = None if (triage/'cursor.json').exists() else 0
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
    with original_resolver(profile, binding) as resolver:
        run_sleep_triage(value, inbox, binding, saved, gateway_original=resolver)
    out = saved['status']['sleep_triage']
    return dict(triage=out, state=('pending' if out['state'] != 'blocked' and not source['capture_complete'] else out['state']),
                capture_complete=source['capture_complete'])


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
        credential = os.environ.get('CREDENTIALS_DIRECTORY')
        key = (Path(credential)/'dmk-decisions').read_text().strip() if credential else sys.stdin.read(1025).strip()
        if not 10 < len(key) <= 1024 or any(char.isspace() for char in key):
            raise ValueError('existing scoped Decisions credential required')
        os.environ['DMK_DECISIONS_API_KEY'] = key
        outcome = run(profile, root)
        checkpoint(root/'receiving.json', outcome)
        print(json.dumps(outcome))
        if outcome['state'] == 'blocked':
            raise SystemExit(2)


if __name__ == '__main__':
    main()
