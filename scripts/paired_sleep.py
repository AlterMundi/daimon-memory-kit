"""Run Decisions over one explicitly approved, forward-only general conversation."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from capture_inbox import Inbox
from codex_coordinator import checkpoint
from codex_hook_capture import capture
import forward_capture
from provider_status import Alerts, ProviderProblem

SCHEMA = 'dmk.paired-sleep/v1'


def readonly(path):
    return closing(sqlite3.connect(Path(path).resolve(strict=True).as_uri() + '?mode=ro', uri=True))


def enrolled_thread(profile):
    """Resolve only the current paired human's enrolled general entry."""
    with readonly(profile['conversation_db']) as con:
        rows = con.execute('''
            SELECT s.creator_user_id, s.codex_thread_id
              FROM sessions s JOIN users u ON u.tg_user_id = s.creator_user_id
             WHERE u.allowed=1 AND s.chat_id = u.tg_user_id AND s.thread_id=1
               AND s.force_fresh_thread=0 AND length(s.codex_thread_id)>0
        ''').fetchall()
    if len(rows) != 1:
        raise ValueError('one active paired general conversation is required')
    with readonly(profile['native_db']) as con:
        row = con.execute('SELECT rollout_path, cwd FROM threads WHERE id=? AND archived=0',
                          (rows[0][1],)).fetchone()
    if not row:
        raise ValueError('native source is not available')
    return (*rows[0], *row)


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


def run(profile, root):
    config = json.loads((root/'binding.json').read_bytes())
    if config['schema'] != SCHEMA:
        raise ValueError('unsupported paired binding')
    binding = config['binding']
    inbox = Inbox(binding['inbox'], binding)
    alerts = Alerts(inbox)
    operation = 'paired-sleep-input'
    try:
        actual = enrolled_thread(profile)
        if actual != (config['human_id'], binding['selected_session_id'], config['transcript'], config['cwd']):
            raise ValueError('the authorized native entry has changed')
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
    run_sleep_triage(dict(state_dir=str(root), sleep_triage=dict(
        state_dir=str(triage), initial_after=initial, steps=4, human_id=config['human_id'],
        credential_env='DMK_DECISIONS_API_KEY', max_age_seconds=93600,
        source_review_report=profile.get('source_review_report'))), inbox, binding, saved)
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
