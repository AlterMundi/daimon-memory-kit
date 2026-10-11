#!/usr/bin/env python3
"""Explicit, local HMK-native projections into Codex memory v1.

No model, listener, native configuration change or Matrix admission occurs here.
The caller selects an authorized canon and quiesces the destination's writers.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import uuid

import support_currency
from capturectl import CaptureLedger, digest, wire
from sqlite_snapshot import verified_snapshot

SELECTION = 'hmk.codex-projection.selection/v1'
MANIFEST = 'hmk.codex-projection.manifest/v1'
ARTIFACT = 'hmk.native-learning-artifact/v1'
MANIFEST_FILE = 'hmk-projection.json'
VOLATILE_COLUMNS = {'last_access', 'access_count'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('expected a regular file, not a symlink')
    return path.read_bytes()


def scope(value):
    if (not isinstance(value, dict) or set(value) != {'kind', 'targets'}
            or value['kind'] not in {'being', 'body', 'project', 'environment'}
            or not isinstance(value['targets'], list)
            or any(not isinstance(x, str) or not x for x in value['targets'])
            or len(set(value['targets'])) != len(value['targets'])
            or bool(value['targets']) == (value['kind'] == 'being')):
        raise ValueError('explicit applicability kind and targets required')
    return value


def load_sources(database, selection):
    """One read transaction; no schema migration, access touching or embeddings."""
    if (selection.get('schema') != SELECTION
            or any(not isinstance(selection.get(k), str) or not selection[k]
                   for k in ('being_ref', 'body_ref'))
            or not isinstance(selection.get('records'), list)):
        raise ValueError('versioned selection and explicit being/body binding required')
    if Path(database).is_symlink() or not Path(database).is_file():
        raise ValueError('canon must be an existing regular SQLite file')
    con = sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        con.execute('BEGIN')
        rows, seen = [], set()
        for entry in selection['records']:
            uid, revision = entry['record_uid'], entry['revision']
            if (not isinstance(uid, str) or str(uuid.UUID(uid)) != uid
                    or uid in seen or type(revision) is not int or revision < 1):
                raise ValueError('duplicate record or invalid revision')
            seen.add(uid)
            row = con.execute('SELECT c.*,b.source_kind,b.title AS book_title,s.name AS shelf '
                              'FROM chapters c JOIN books b ON b.id=c.book_id '
                              'JOIN shelves s ON s.id=b.shelf_id WHERE c.record_uid=?', (uid,)).fetchone()
            if row is None or row['revision'] != revision:
                raise ValueError('missing or changed canonical record')
            if row['source_kind'] == 'daimon-projection' or row['shelf'] == 'daimon-projection':
                raise ValueError('accepted Matrix records require their verified owning adapter')
            currency = support_currency.check(con, [(uid, revision)])[0]
            if currency['status'] != 'current':
                raise ValueError('canonical support needs reconciliation')
            record = {k: row[k] for k in row.keys() if k not in VOLATILE_COLUMNS}
            rows.append(dict(original=record, applicability=scope(entry['applicability']),
                             selection_original=entry))
        return rows
    finally:
        con.close()


def render(database, selection, *, now=None):
    now = int(time.time()) if now is None else now
    rows = load_sources(database, selection)
    files = {}
    header = ('# Canonical memory projection\n\n'
              'These are retained HMK records, not original Codex sessions. '
              'A record UID is not a Codex rollout ID. Source attribution and '
              'applicability are distinct; remembered capabilities are not current grants.\n')
    registry = [header]
    summary = ['# Memory navigation\n', f"Being: {selection['being_ref']}\n",
               f"Receiving body: {selection['body_ref']}\n",
               'Use MEMORY.md for source-backed prior experiences, relationships, '
               'projects and lessons. Its linked originals retain meaning and uncertainty. '
               'Environment and skill applicability must be checked against this body.\n']
    dependencies = []
    for item in rows:
        row = item['original']
        uid, revision = row['record_uid'], row['revision']
        title = row['title'] or row['book_title'] or uid
        name = f'rollout_summaries/hmk-{uid}-r{revision}.md'
        source = json.loads(row['source_metadata_json'])
        details = dict(record_uid=uid, revision=revision, engram_type=row['engram_type'],
                       event_ts=row.get('event_ts'), actor=row.get('actor'),
                       source=source, applicability=item['applicability'])
        files[name] = (f'# {title}\n\nCanonical reference: mem:{uid}@{revision}\n'
                       f'Attribution and applicability: {wire(details)}\n\n'
                       '## Retained original\n\n'+row['raw']+'\n').encode()
        # Keep unrecognized source/selection fields in an inert original sidecar.
        files[f'originals/{uid}-r{revision}.json'] = wire(item).encode()
        snippet = row['spr'].replace('\n', ' ')[:500]
        registry.append(f'\n## {title}\n- Reference: mem:{uid}@{revision}\n'
                        f'- Original: {name}\n- Applicability: {wire(item["applicability"])}\n'
                        f'- Navigation excerpt (may be incomplete): {snippet}\n')
        summary.append(f'- {title}: {snippet[:160]}\n')
        dependencies.append(dict(record_uid=uid, revision=revision,
                                 source_sha256=digest(item), member=name))
    temporary = selection.get('temporary_context', [])
    if not isinstance(temporary, list):
        raise ValueError('temporary context must be a list')
    active = []
    for entry in temporary:
        if (not isinstance(entry, dict) or type(entry.get('expires_at')) is not int
                or not isinstance(entry.get('text'), str) or not entry.get('key')):
            raise ValueError('temporary context needs key, text and explicit expiry')
        scope(entry['applicability'])
        if entry['expires_at'] > now:
            active.append(entry)
    if active:
        files['temporary_context.md'] = ('# Temporary working context\n\n'+wire(active)+'\n').encode()
        summary.append('Temporary working context is in temporary_context.md; '
                       'it is not durable autobiography and has explicit expiry.\n')
    summary_text = ''.join(summary)
    if len(summary_text.encode()) > 8_000:
        raise ValueError('selection exceeds initial summary budget; select a smaller view')
    files['memory_summary.md'] = summary_text.encode()
    files['MEMORY.md'] = ''.join(registry).encode()
    manifest = dict(schema=MANIFEST, native_layout='codex-memory-v1',
                    being_ref=selection['being_ref'], body_ref=selection['body_ref'],
                    selection_original=selection, source_records=dependencies,
                    temporary_valid_until=min((e['expires_at'] for e in active), default=None),
                    members={name: dict(sha256=sha(data), bytes=len(data))
                             for name, data in sorted(files.items())},
                    losses=['Registry excerpts are cropped; linked originals are complete.',
                            'Native v1 is a selected head view; prior revisions remain in canonical HMK.',
                            'No Codex rollout identity is invented for HMK originals.'])
    manifest['projection_id'] = digest(manifest)
    files[MANIFEST_FILE] = (wire(manifest)+'\n').encode()
    return files, manifest


def verify(root, *, database=None, now=None):
    """Check exact view and dependencies before starting a receiving session."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('projection root must be a real directory')
    manifest = json.loads(regular(root/MANIFEST_FILE))
    unsigned = {k: v for k, v in manifest.items() if k != 'projection_id'}
    if manifest.get('schema') != MANIFEST or digest(unsigned) != manifest.get('projection_id'):
        raise ValueError('projection manifest integrity mismatch')
    now = int(time.time()) if now is None else now
    until = manifest['temporary_valid_until']
    if until is not None and now >= until:
        raise ValueError('temporary context expired; rebuild before receiving use')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(manifest['members']) | {MANIFEST_FILE}:
        raise ValueError('missing or unexpected view member; preserve native changes before publication')
    for name, expected in manifest['members'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('invalid projection member path')
        path = root/relative
        if any(p.is_symlink() for p in [path, *path.parents] if p != root.parent):
            raise ValueError('symlink in projection member path')
        data = regular(path)
        if len(data) != expected['bytes'] or sha(data) != expected['sha256']:
            raise ValueError('projection content mismatch')
    if database is not None:
        sources = load_sources(database, manifest['selection_original'])
        expected = [d['source_sha256'] for d in manifest['source_records']]
        if [digest(x) for x in sources] != expected:
            raise ValueError('canonical source content drift')
    return manifest


def publish(database, selection, root, *, writers_stopped=False, now=None):
    """Create a view only at a new root; retain older views and native learning.

    Selecting a fresh test profile/generation avoids overwriting a native writer.
    In-place publication is deliberately unsupported until its seam is qualified.
    """
    if not writers_stopped:
        raise ValueError('destination writers must be stopped')
    root, database = Path(root).absolute(), Path(database).absolute()
    if any(p.is_symlink() for p in root.parents):
        raise ValueError('symlink in destination parent path')
    if root.exists() or root.is_symlink() or root in database.parents:
        raise ValueError('use a new projection root disjoint from the canon')
    root.parent.mkdir(parents=True, exist_ok=True)
    with open(root.parent/'.hmk-projection.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        files, manifest = render(database, selection, now=now)
        staging = Path(tempfile.mkdtemp(prefix='.hmk-projection-', dir=root.parent))
        try:
            for name, data in files.items():
                target = staging/name
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, 'xb') as out:
                    os.chmod(target, 0o600)
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
            verify(staging, database=database, now=now)
            for directory in sorted([staging, *[p for p in staging.rglob('*') if p.is_dir()]],
                                    key=lambda p: len(p.parts), reverse=True):
                directory_fd = os.open(directory, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            if root.exists() or root.is_symlink():
                raise ValueError('projection root appeared during publication')
            os.rename(staging, root)
            parent_fd = os.open(root.parent, os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return manifest


def learning_bundle(files, *, source_instance, subject, source_event_id, inherited_projection=None):
    """Preserve exact producer bytes; this is not a semantic novelty decision."""
    if not files or any(not isinstance(k, str) or not k for k in files):
        raise ValueError('explicit artifact members required')
    if any(not isinstance(x, str) or not x for x in (source_instance, subject, source_event_id)):
        raise ValueError('explicit source attribution required')
    members = {}
    for name, data in sorted(files.items()):
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not isinstance(data, bytes):
            raise ValueError('artifact names must be relative; contents must be exact bytes')
        members[name] = dict(sha256=sha(data), bytes=len(data), base64=base64.b64encode(data).decode())
    bundle = dict(schema=ARTIFACT, source_instance=source_instance, subject=subject,
                  source_event_id=source_event_id, inherited_projection=inherited_projection,
                  members=members)
    bundle['artifact_id'] = digest(bundle)
    return bundle


def restore_learning(bundle):
    unsigned = {k: v for k, v in bundle.items() if k != 'artifact_id'}
    if bundle.get('schema') != ARTIFACT or digest(unsigned) != bundle.get('artifact_id'):
        raise ValueError('artifact manifest integrity mismatch')
    restored = {}
    for name, member in bundle['members'].items():
        data = base64.b64decode(member['base64'], validate=True)
        if sha(data) != member['sha256'] or len(data) != member['bytes']:
            raise ValueError('artifact bytes mismatch')
        restored[name] = data
    # Re-run producer envelope validation, including member names and attribution.
    if learning_bundle(restored, source_instance=bundle['source_instance'], subject=bundle['subject'],
                       source_event_id=bundle['source_event_id'],
                       inherited_projection=bundle['inherited_projection']) != bundle:
        raise ValueError('artifact envelope mismatch')
    return restored


def incorporate(memory, bundle, *, sequence, selected_records, reason, selection_version):
    """Back up, retain artifact, and apply an explicit source-qualified decision.

    Canonical evidence is retained outside ordinary selected recall. The caller
    judges genuinely new learning against its source; hashes cannot prove meaning.
    No native output is automatically considered true or admitted into Matrix.
    """
    restore_learning(bundle)
    if not selected_records:
        raise ValueError('explicit new-learning selection required')
    for record in selected_records:
        if record.get('metadata', {}).get('subject', bundle['subject']) != bundle['subject']:
            raise ValueError('selected learning belongs to another subject')
    backup = Path(str(memory.DB_PATH)+'.bak.native-learning.'+str(time.time_ns()))
    verified_snapshot(memory.DB_PATH, backup)
    ledger = CaptureLedger(memory)
    con = memory.connect()
    try:
        con.execute('CREATE TABLE IF NOT EXISTS native_learning_artifacts ('
                    'artifact_id TEXT PRIMARY KEY, envelope_json TEXT NOT NULL)')
        con.commit()
    finally:
        con.close()
    event = dict(stream_id='codex-native:'+bundle['source_instance'], sequence=sequence,
                 event_id=bundle['source_event_id'], source_version=bundle['artifact_id'],
                 content=wire(bundle), metadata=dict(mode='generated', source_instance=bundle['source_instance'],
                    subject=bundle['subject'], source_uri='artifact:sha256:'+bundle['artifact_id']))
    staged = ledger.stage(event)
    reference = 'artifact:sha256:'+bundle['artifact_id']
    records = []
    for record in selected_records:
        source = dict(record.get('metadata', {}))
        source['evidence'] = list(dict.fromkeys([*source.get('evidence', []), reference]))
        records.append(dict(record, metadata=source))
    decision = dict(outcome='applied', reason=reason, selection_version=selection_version,
                    records=records, links=[])

    def preserve_original(con):
        con.execute('INSERT OR IGNORE INTO native_learning_artifacts VALUES(?,?)',
                    (bundle['artifact_id'], wire(bundle)))
        row = con.execute('SELECT envelope_json FROM native_learning_artifacts WHERE artifact_id=?',
                          (bundle['artifact_id'],)).fetchone()
        if row[0] != wire(bundle):
            raise ValueError('existing original artifact differs')

    # Original bytes and selected memory commit in the same existing capture
    # transaction. They are not chapters or embedding/ordinary recall inputs.
    receipt = ledger.assess(staged['event_key'], decision, _validator=preserve_original)
    if load_learning(memory, bundle['artifact_id']) != restore_learning(bundle):
        raise ValueError('canonical artifact unavailable after capture')
    return dict(receipt=receipt, backup=backup)


def load_learning(memory, artifact_id):
    con = memory.connect()
    try:
        row = con.execute('SELECT envelope_json FROM native_learning_artifacts WHERE artifact_id=?',
                          (artifact_id,)).fetchone()
        if row is None:
            raise ValueError('canonical original artifact missing')
        return restore_learning(json.loads(row[0]))
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('publish')
    build.add_argument('--database', type=Path, required=True)
    build.add_argument('--selection', type=Path, required=True)
    build.add_argument('--root', type=Path, required=True)
    build.add_argument('--writers-stopped', action='store_true')
    check = sub.add_parser('verify')
    check.add_argument('--root', type=Path, required=True)
    check.add_argument('--database', type=Path)
    args = parser.parse_args()
    if args.action == 'publish':
        manifest = publish(args.database, json.loads(regular(args.selection)), args.root,
                           writers_stopped=args.writers_stopped)
    else:
        manifest = verify(args.root, database=args.database)
    print(wire(dict(projection_id=manifest['projection_id'], records=len(manifest['source_records']),
                    members=len(manifest['members']), losses=manifest['losses'])))


if __name__ == '__main__':
    main()
