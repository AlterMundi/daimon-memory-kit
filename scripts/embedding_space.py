"""Select a fully populated embedding space in an existing DMK receiver."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import tempfile

from capture_inbox import Inbox
from capturectl import digest
from codex_coordinator import checkpoint, sync_directory
from memory_runtime import load_memory, profile


def write_bytes(path, data, mode):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.embedding-space-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def update_selection(raw, selection):
    lines = raw.decode('utf-8').splitlines(keepends=True)
    for key, value in selection.items():
        matching = [i for i, line in enumerate(lines) if line.startswith(key + '=')]
        if len(matching) > 1:
            raise ValueError(f'duplicate {key} assignment')
        replacement = f'{key}={value}\n'
        if matching:
            lines[matching[0]] = replacement
        else:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.append(replacement)
    return ''.join(lines).encode()


def select_space(config, target, receipt_dir):
    env = Path(config['embedding_env_file'])
    state = Path(config['state_dir'])
    binding = json.loads(Path(config['binding']).read_bytes())
    if any(binding.get(key) != config['context'][key] for key in ('subject', 'source_instance')):
        raise ValueError('capture binding differs from worker context')
    if binding.get('inbox') and Path(binding['inbox']).resolve() != Path(config['inbox']).resolve():
        raise ValueError('capture binding selects another inbox')
    if env.is_symlink() or not env.is_file() or not Path(config['inbox']).is_file():
        raise ValueError('existing regular environment and capture inbox required')
    if any(k.startswith('HERMES_EMBED_') for k in os.environ):
        raise ValueError('remove inherited embedding environment overrides')
    memory = load_memory(config)
    inbox = Inbox(config['inbox'], binding)
    old_space = memory.embeddings_runtime_config()
    if target == old_space:
        raise ValueError('target space is already selected')
    target_model = target['model']
    if not target_model or '\n' in target_model or '\r' in target_model:
        raise ValueError('invalid model name or path')
    with ExitStack() as locks:
        for suffix in ('.worker.lock', '.producer.lock'):
            lock = locks.enter_context(open(str(inbox.path) + suffix, 'a+b'))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = memory._lock_maintenance()
        locks.callback(memory._unlock_maintenance, fd)
        with inbox.connect() as con:
            owner_row = con.execute('SELECT value FROM producer_owner').fetchone()
        owner = json.loads(owner_row[0]) if owner_row else {}
        if (owner.get('database') != str(Path(memory.DB_PATH).resolve())
                or owner.get('state_dir') != str(state.resolve())
                or owner.get('capture_binding') != digest(binding)):
            raise ValueError('index work binding differs')
        pending = memory.embedding_candidates(provider=target['provider'], model=target_model, limit=1)
        if pending:
            raise ValueError('target space has missing or outdated eligible vectors')
        with memory.connect() as con:
            observed = con.execute('SELECT DISTINCT dims FROM chapter_embeddings WHERE provider=? AND model=?',
                                   (target['provider'], target_model)).fetchall()
        if {row[0] for row in observed} != {target['output_dimensionality']}:
            raise ValueError('target embedding dimensions differ')
        image = {}
        updates = {}
        for name in ('embedding-index.json', 'embedding-organization-index.json'):
            path = state / name
            if not path.exists():
                continue
            raw = path.read_bytes()
            cursor = json.loads(raw)
            if (cursor.get('owner') != owner or cursor.get('space') != old_space
                    or type(cursor.get('after')) is not int or cursor['after'] < 0):
                raise ValueError('index cursor is not in the selected source space')
            image[path] = raw
            updates[path] = dict(cursor, space=target)
        original = env.read_bytes()
        changed = update_selection(original, {
            'HERMES_EMBED_PROVIDER': target['provider'],
            'HERMES_EMBED_MODEL': target_model,
            'HERMES_EMBED_OUTPUT_DIMS': target['output_dimensionality'],
        })
        receipt_dir.mkdir(mode=0o700)
        write_bytes(receipt_dir/'embedding-environment.before', original, 0o600)
        for path, raw in image.items():
            write_bytes(receipt_dir/(path.name+'.before'), raw, 0o600)
        result = {'previous_space': old_space, 'selected_space': target,
                  'preserved_cursors': {p.name: d['after'] for p,d in updates.items()}}
        checkpoint(receipt_dir/'selection.prepared.json', result)
        mode = env.stat().st_mode & 0o777
        try:
            for path, value in updates.items():
                checkpoint(path, value)
            write_bytes(env, changed, mode)
            if memory.embeddings_runtime_config() != target:
                raise ValueError('environment did not select the target space')
            checkpoint(receipt_dir/'selection.applied.json', result)
        except BaseException:
            for path, raw in image.items():
                write_bytes(path, raw, 0o600)
            write_bytes(env, original, mode)
            raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--provider', required=True, choices=('model2vec', 'nvidia', 'google', 'local'))
    parser.add_argument('--model', required=True)
    parser.add_argument('--dimensions', type=int, required=True)
    parser.add_argument('--receipt-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.dimensions < 1:
        parser.error('positive dimensions required')
    os.umask(0o077)
    print(json.dumps(select_space(profile(args.profile),
        dict(provider=args.provider, model=args.model, output_dimensionality=args.dimensions),
        args.receipt_dir)))


if __name__ == '__main__':
    main()
