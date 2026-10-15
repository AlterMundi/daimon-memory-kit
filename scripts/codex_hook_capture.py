#!/usr/bin/env python3
"""Opt-in Codex source capture into a bound inbox. No models, canon writes or scans."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import stat
import sys
import time

from capture_inbox import Inbox

EVENTS = {'SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop', 'PreCompact', 'PostCompact', 'Interrupt', 'SessionEnd'}


def timestamp(value):
    if not isinstance(value,str):
        raise ValueError('explicit timezone-aware session boundary required')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('explicit timezone-aware session boundary required')
    return result


def capture(binding, payload, *, _fault=None):
    started = time.monotonic()
    scoped = binding.get('schema') == 'hmk.codex-hook-binding/v2'
    if binding.get('schema') not in {'hmk.codex-hook-binding/v1','hmk.codex-hook-binding/v2'}:
        raise ValueError('unsupported explicit hook binding')
    required = {'schema','subject','source_instance','source_root','allowed_cwds','inbox','max_source_bytes'}
    if scoped:
        required.add('sessions_started_at_or_after')
        boundary=timestamp(binding.get('sessions_started_at_or_after'))
    if set(binding) != required or not all(isinstance(binding[k], str) and binding[k] for k in ('subject','source_instance','source_root','inbox')):
        raise ValueError('complete source and receiving binding required')
    limit = binding['max_source_bytes']
    if type(limit) is not int or not 1 <= limit <= 64 * 1024 * 1024:
        raise ValueError('bounded source byte limit required')
    if not isinstance(binding['allowed_cwds'], list) or not binding['allowed_cwds']:
        raise ValueError('explicit selected working directories required')
    if not isinstance(payload, dict) or payload.get('hook_event_name') not in EVENTS:
        raise ValueError('unsupported hook event')
    if payload.get('cwd') not in binding['allowed_cwds']:
        if scoped:
            return dict(capture_complete=False,skipped=True,reason='unselected_working_directory')
        raise ValueError('working directory outside selected scope')
    sid = payload.get('session_id')
    if not isinstance(sid, str) or not sid:
        raise ValueError('session ID required')
    source_root = Path(binding['source_root']).resolve(strict=True)
    transcript = payload.get('transcript_path')
    data, error = None, None
    if not transcript:
        error = 'transcript_unavailable'
    else:
        path = Path(transcript).resolve(strict=False)
        if not path.is_relative_to(source_root) or path == source_root:
            raise ValueError('transcript outside selected source root')
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as source:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError('transcript must be a regular file')
                if scoped:
                    # Scope depends on the session header, not the growing body.
                    # Read at most the configured bound even for excluded sources.
                    header = source.readline(limit + 1)
                    try:
                        meta = json.loads(header) if len(header) <= limit else None
                    except (ValueError, UnicodeError):
                        meta = None
                    if not isinstance(meta, dict) or meta.get('type') != 'session_meta' or not isinstance(meta.get('payload'), dict):
                        return dict(capture_complete=False, error='source_header_incomplete', scope_verified=False)
                    if meta['payload'].get('id') != sid:
                        raise ValueError('transcript session differs from hook')
                    if meta['payload'].get('cwd') not in binding['allowed_cwds']:
                        return dict(capture_complete=False, skipped=True,
                                    reason='unselected_session_working_directory')
                    try:
                        session_started = timestamp(meta['payload'].get('timestamp'))
                    except (ValueError, TypeError):
                        return dict(capture_complete=False, error='session_scope_unverified', scope_verified=False)
                    if session_started < boundary:
                        return dict(capture_complete=False, skipped=True,
                                    reason='session_precedes_selected_boundary')
                    source.seek(0)
                if before.st_size > limit:
                    error = 'source_exceeds_capture_limit'
                else:
                    data = source.read(limit + 1)
                    after = os.fstat(source.fileno())
                    if len(data) > limit or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        data, error = None, 'source_changed_during_capture'
                    else:
                        try:
                            meta = json.loads(data.split(b'\n', 1)[0])
                        except (ValueError, UnicodeError):
                            data, error = None, 'source_header_incomplete'
                        else:
                            if (not isinstance(meta, dict) or meta.get('type') != 'session_meta'
                                    or not isinstance(meta.get('payload'), dict)
                                    or meta['payload'].get('id') != sid):
                                raise ValueError('transcript session differs from hook')
                            if scoped:
                                if meta['payload'].get('cwd') not in binding['allowed_cwds']:
                                    return dict(capture_complete=False,skipped=True,
                                        reason='unselected_session_working_directory')
                                try:
                                    session_started=timestamp(meta['payload'].get('timestamp'))
                                except (ValueError,TypeError):
                                    data,error=None,'session_scope_unverified'
                                else:
                                    if session_started < boundary:
                                        return dict(capture_complete=False,skipped=True,
                                            reason='session_precedes_selected_boundary')
        except FileNotFoundError:
            error = 'transcript_missing'
    # Null/unavailable transcripts still retain the event payload and a visible gap.
    # Only a successful exact snapshot receives capture_complete=true.
    if scoped and data is None:
        # Without a verified source header, this event is not authorized intake.
        # Report a gap to the caller; do not journal private prompt/answer bytes
        # from a possibly older session merely because its hook ran today.
        return dict(capture_complete=False,error=error,scope_verified=False)
    inbox = Inbox(binding['inbox'], binding)
    result = inbox.observe(sid, payload, data, error=error, _fault=_fault)
    result['handler_seconds'] = time.monotonic() - started
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    args = parser.parse_args()
    binding = json.loads(args.binding.read_text())
    payload = json.load(sys.stdin)
    receipt = capture(binding, payload)
    # Valid hook output must not block the user's turn or inject memory prose.
    print(json.dumps({} if receipt['capture_complete'] or receipt.get('skipped') else {
        'systemMessage': 'HMK source capture deferred: ' + receipt['error']}))


if __name__ == '__main__':
    main()
