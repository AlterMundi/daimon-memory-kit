#!/usr/bin/env python3
"""Qualify a selected native DMK generation boundary without authorizing a model call."""
import argparse
import json
import os
from pathlib import Path
import tempfile

import bounded_native_turn
from codex_memory_provider import command
from memory_runtime import profile
from selection_navigation import response_schema


class ReservationReached(Exception):
    """Stop before the bounded client can acknowledge the reservation."""


def preflight(value, binary=None):
    generation, reviewer = value['generation'], value['review']
    if generation['provider'] != 'openai-codex-native':
        raise ValueError('selected generation does not use the native route')
    request = {
        'model': generation['model'],
        'format': 'hmk-fictional-bounded-memory-operation/v1',
        'source_scope': 'fictional',
        'fresh_context': True,
        'tools_allowed': False,
        'native_memory_allowed': False,
        'reasoning_effort': 'low',
        'phase': 'capture',
        'output_token_limit': generation['output_token_limit'],
        'response_schema': response_schema(),
        'messages': [{'role': 'system', 'content': 'Synthetic validation only.'},
                     {'role': 'user', 'content': 'No source data is available.'}],
    }
    codex_home = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))).resolve()
    credential = reviewer.get('credential_file') or codex_home/'auth.json'
    with tempfile.TemporaryDirectory(prefix='native-preflight-', dir=Path(value['state_dir']).parent) as temporary:
        root = Path(temporary)
        cwd, logs = root/'empty', root/'logs'
        cwd.mkdir(mode=0o700)
        logs.mkdir(mode=0o700)
        argv, text = command(request, Path(reviewer['catalog']), cwd, logs,
                             binary=str(binary or reviewer.get('binary', 'codex')))
        fd = os.open(credential, os.O_RDONLY)
        try:
            isolated = [
                'bwrap', '--die-with-parent', '--bind', '/', '/', '--tmpfs', str(codex_home),
                '--ro-bind', f'/proc/self/fd/{fd}', str(codex_home/'auth.json'), '--', *argv,
            ]

            def retain(key, _):
                if key == 'provider_reservation':
                    raise ReservationReached()

            try:
                bounded_native_turn.execute(
                    isolated, credential_fd=fd, timeout=12, model=request['model'], cwd=str(cwd),
                    text=text, schema=request['response_schema'],
                    output_limit=request['output_token_limit'], retain=retain,
                )
            except ReservationReached:
                return {'state': 'reservation_reached', 'provider_authorized': False}
            except bounded_native_turn.BoundedTurnFailure as error:
                return {'state': 'failed', 'provider_authorized': False, 'failure': error.evidence}
            except (EOFError, OSError, ValueError) as error:
                return {'state': 'failed', 'provider_authorized': False,
                        'error_type': type(error).__name__}
        finally:
            os.close(fd)
    raise RuntimeError('native preflight unexpectedly returned past the reservation boundary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--binary', type=Path)
    args = parser.parse_args()
    if args.binary and not args.binary.is_absolute():
        parser.error('--binary must select an absolute candidate path')
    result = preflight(profile(args.profile), args.binary)
    print(json.dumps(result))
    return 0 if result['state'] == 'reservation_reached' else 2


if __name__ == '__main__':
    raise SystemExit(main())
