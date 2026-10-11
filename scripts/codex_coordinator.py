#!/usr/bin/env python3
"""Explicit, resumable native-view renewal. No listener, model call or admission.

The caller stops native writers and supplies a source-qualified novelty decision.
Archives/journals live outside the receiving home; native sessions stay in place.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import time

import codex_projection as projection
from publish_collective import write_json_atomic

REQUEST = 'hmk.codex-coordinator.request/v1'
STATE = 'hmk.codex-coordinator.state/v1'


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def checkpoint(path, value):
    write_json_atomic(path, value)
    sync_directory(path.parent)


def tree(root):
    if root.is_symlink():
        raise ValueError('native view cannot be a symlink')
    if not root.exists():
        return {}
    if not root.is_dir():
        raise ValueError('native view must be a directory')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink in native view')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = projection.regular(path)
    return result


def fingerprint(files):
    return {name: projection.sha(data) for name, data in sorted(files.items())}


def inherited(files, selection):
    if not files:
        return None
    manifest = json.loads(files[projection.MANIFEST_FILE])
    unsigned = {k: v for k, v in manifest.items() if k != 'projection_id'}
    if (manifest.get('schema') != projection.MANIFEST
            or projection.digest(unsigned) != manifest.get('projection_id')):
        raise ValueError('inherited projection manifest changed')
    if any(manifest[key] != selection[key] for key in ('being_ref', 'body_ref')):
        raise ValueError('different being or body; renewal is not enrollment')
    return manifest


def qualify(files, manifest, learning):
    """Validate explicit support for new bytes, not the truth of their meaning."""
    records = learning.get('records', [])
    if not isinstance(records, list) or not learning.get('reason'):
        raise ValueError('explicit selected/omitted novelty decision required')
    baseline = manifest['members'] if manifest else {}
    originals = []
    if records:
        for name, member in baseline.items():
            if name.startswith('originals/'):
                if name not in files or projection.sha(files[name]) != member['sha256']:
                    raise ValueError('inert originals changed; preserve and reconcile before new intake')
                original = json.loads(files[name])['original']
                originals.extend(original[k].encode() for k in ('raw', 'spr') if original.get(k))
    changed = {name: data for name, data in files.items()
               if name != projection.MANIFEST_FILE
               and projection.sha(data) != baseline.get(name, {}).get('sha256')}
    support = learning.get('support', {})
    applicability = learning.get('applicability', {})
    if set(support) != {r['key'] for r in records} or set(applicability) != set(support):
        raise ValueError('each selected record needs new-byte support and applicability')
    for record in records:
        if record.get('operation') != 'add':
            raise ValueError('new-learning intake only; corrections use existing revision APIs')
        projection.scope(applicability[record['key']])
        witnesses = support[record['key']]
        if not witnesses:
            raise ValueError('new learning needs a source witness')
        for witness in witnesses:
            name, text = witness['member'], witness['text']
            if (not isinstance(text, str) or not text.strip() or name not in changed
                    or text.encode() not in changed[name]):
                raise ValueError('support must identify actual changed native bytes')
            # Copies of projected originals are not new experiences, even at a
            # new filename. Meaning/partial paraphrases still need source review.
            if (any(text.encode() in data for data in originals)
                    or any(text.encode() in data for name, data in files.items()
                           if name in baseline and projection.sha(data) == baseline[name]['sha256'])):
                raise ValueError('projected support cannot be promoted as new experience')
    return records


def renew(memory, state_dir, operation_id, *, request=None, writers_stopped=False,
          _fault_hook=None):
    """Resume exactly one immutable operation, including uncertain commit results."""
    if not writers_stopped:
        raise ValueError('native writers must be stopped before renewal or resume')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', operation_id):
        raise ValueError('invalid operation identifier')
    state_dir = Path(state_dir).absolute()
    if any(p.is_symlink() for p in [state_dir, *state_dir.parents]):
        raise ValueError('state path cannot contain symlinks')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    job = state_dir/operation_id
    job.mkdir(exist_ok=True, mode=0o700)
    if job.is_symlink():
        raise ValueError('operation path cannot be a symlink')
    state_path = job/'state.json'
    with open(state_dir/'.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.exists():
            state = json.loads(projection.regular(state_path))
            inputs = state['inputs']
            if state['schema'] != STATE or projection.digest(inputs) != state['input_hash']:
                raise ValueError('operation inputs changed')
            if request is not None and request != inputs['request']:
                raise ValueError('operation replay differs; use a new operation')
        else:
            if request is None or request.get('schema') != REQUEST:
                raise ValueError('new operation needs a versioned request')
            if any(not Path(request[key]).is_absolute() for key in ('database', 'codex_home')):
                raise ValueError('canon and receiving home need explicit absolute paths')
            home = Path(request['codex_home']).absolute()
            if home.is_symlink() or not home.is_dir():
                raise ValueError('receiving home must already exist as a real directory')
            if (home == state_dir or home in state_dir.parents or state_dir in home.parents
                    or home == Path(memory.DB_PATH).parent or home in Path(memory.DB_PATH).parents):
                raise ValueError('canon, journals and native home must be separated')
            if home.stat().st_dev != state_dir.stat().st_dev:
                raise ValueError('atomic renewal needs home and journal on the same filesystem')
            binding_path = home/'.hmk-coordinator-binding.json'
            binding = dict(schema='hmk.codex-coordinator.binding/v1', state_dir=str(state_dir))
            if binding_path.exists() and json.loads(projection.regular(binding_path)) != binding:
                raise ValueError('receiving home already bound to another journal')
            for path in state_dir.glob('*/state.json'):
                other = json.loads(projection.regular(path))
                if (other['inputs']['request']['codex_home'] == str(home)
                        and other['phase'] != 'complete'):
                    raise ValueError('receiving home has a pending operation; resume it explicitly')
            checkpoint(binding_path, binding)
            files = tree(home/'memories')
            manifest = inherited(files, request['selection'])
            learning = request['learning']
            qualify(files, manifest, learning)
            evidence = {name: projection.regular(Path(path))
                        for name, path in request.get('evidence_files', {}).items()}
            bundle = projection.learning_bundle(
                {**{'memory/'+name: data for name, data in files.items()},
                 **{'evidence/'+name: data for name, data in evidence.items()}}
                or {'availability.json': b'{"previous_view":false}'},
                source_instance=request['selection']['body_ref'],
                subject=request['selection']['being_ref'],
                source_event_id=learning['source_event_id'], inherited_projection=manifest)
            inputs = dict(request=request, bundle=bundle, previous=fingerprint(files))
            state = dict(schema=STATE, inputs=inputs, input_hash=projection.digest(inputs),
                         phase='frozen', build=0, receipt=None)
            checkpoint(state_path, state)
        if Path(request['database'] if request else inputs['request']['database']).absolute() != Path(memory.DB_PATH).absolute():
            raise ValueError('bound canon differs from the operation')
        request = inputs['request']
        home = Path(request['codex_home']).absolute()
        active = home/'memories'
        previous = job/'previous'
        bundle = inputs['bundle']
        projection.restore_learning(bundle)

        def save(phase):
            state['phase'] = phase
            checkpoint(state_path, state)

        def fault(point):
            if _fault_hook:
                _fault_hook(point)

        while state['phase'] != 'complete':
            phase = state['phase']
            candidate = job/f"next-{state['build']}"
            if phase == 'frozen':
                if fingerprint(tree(active)) != inputs['previous']:
                    raise ValueError('native files changed after freezing; keep work and reconcile')
                learning = request['learning']
                records = learning['records']
                if records:
                    result = projection.incorporate(
                        memory, bundle, sequence=learning['sequence'], selected_records=records,
                        reason=learning['reason'], selection_version=learning['selection_version'])
                    state['receipt'] = result['receipt']
                    state['backup'] = str(result['backup'])
                    fault('after_capture_commit')
                save('captured')
            elif phase == 'captured':
                selection = json.loads(json.dumps(request['selection']))
                for key, record in (state['receipt'] or {}).get('records', {}).items():
                    selection['records'].append(dict(record_uid=record['record_uid'],
                        revision=record['revision'], applicability=request['learning']['applicability'][key]))
                if candidate.exists():
                    pending = json.loads(projection.regular(candidate/projection.MANIFEST_FILE))
                    until = pending['temporary_valid_until']
                    if until is not None and int(time.time()) >= until:
                        state['build'] += 1
                        save('captured')
                        continue
                    manifest = projection.verify(candidate, database=memory.DB_PATH)
                else:
                    manifest = projection.publish(memory.DB_PATH, selection, candidate,
                                                  writers_stopped=True)
                state['selection'] = selection
                state['projection_id'] = manifest['projection_id']
                state['view_fingerprint'] = fingerprint(tree(candidate))
                fault('after_build')
                save('built')
            elif phase == 'built':
                manifest = json.loads(projection.regular(candidate/projection.MANIFEST_FILE))
                until = manifest['temporary_valid_until']
                if until is not None and int(time.time()) >= until:
                    state['build'] += 1
                    save('captured')
                    continue
                projection.verify(candidate, database=memory.DB_PATH)
                if active.exists():
                    if previous.exists() or fingerprint(tree(active)) != inputs['previous']:
                        raise ValueError('native writer drift or conflicting previous view')
                    os.rename(active, previous)
                    sync_directory(home)
                    sync_directory(job)
                    fault('after_archive')
                elif inputs['previous'] and fingerprint(tree(previous)) != inputs['previous']:
                    raise ValueError('previous view missing or changed')
                save('archived')
            elif phase == 'archived':
                if not active.exists():
                    os.rename(candidate, active)
                    sync_directory(home)
                    sync_directory(job)
                    fault('after_activate')
                elif candidate.exists():
                    raise ValueError('unexpected active view; preserve it before reconciliation')
                if fingerprint(tree(active)) != state['view_fingerprint']:
                    raise ValueError('activated view differs from the qualified generation')
                projection.verify(active, database=memory.DB_PATH)
                save('complete')
            else:
                raise ValueError('unknown renewal phase')
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--writers-stopped', action='store_true')
    args = parser.parse_args()
    request = json.loads(projection.regular(args.request)) if args.request else None
    saved = (json.loads(projection.regular(args.state_dir/args.operation/'state.json'))
             ['inputs']['request']) if request is None else request
    database = Path(saved['database']).absolute()
    os.environ['HMK_AGENT_MEMORY_BASE'] = str(database.parent)
    os.environ['HMK_DB_PATH'] = str(database)
    spec = importlib.util.spec_from_file_location('coordinator_bound_memory',
                                               Path(__file__).with_name('memoryctl.py'))
    memory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory)
    result = renew(memory, args.state_dir, args.operation, request=request,
                   writers_stopped=args.writers_stopped)
    print(projection.wire(dict(phase=result['phase'], projection_id=result['projection_id'],
                              receipt=result['receipt'])))


if __name__ == '__main__':
    main()
