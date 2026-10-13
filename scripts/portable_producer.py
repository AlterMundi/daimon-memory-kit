"""Finite resumable capture processing through existing HMK selection writers.

The caller owns invocation and the stateless proposer. No timer, listener,
provider credential discovery, source scan or native memory is activated here.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import time

from capturectl import CaptureLedger, digest, wire
from codex_coordinator import checkpoint, sync_directory
import codex_projection as artifacts
import portable_capture as selection
from sqlite_snapshot import verified_snapshot

SCHEMA = 'hmk.portable-producer/v1'


def _canon(memory, maximum=256):
    con = memory.connect()
    try:
        rows = [dict(r) for r in con.execute('''SELECT c.id,c.record_uid,c.revision,c.raw,c.title,c.source_metadata_json,
            c.engram_type,s.name AS shelf FROM chapters c JOIN books b ON c.book_id=b.id
            JOIN shelves s ON b.shelf_id=s.id ORDER BY c.id LIMIT ?''', (maximum+1,))]
        if len(rows) > maximum or len(wire(rows).encode()) > 512 * 1024:
            raise ValueError('canonical context exceeds this bounded producer profile; defer without truncation')
        return rows
    finally:
        con.close()


def process_once(memory, inbox, state_dir, proposer, context, *, limit=32,
                 _fault=None):
    """Process at most one frozen batch. Reinvocation resumes uncertain commits.

    proposer(request, directory) returns an auditable JSON object containing
    `selection` and dispatch evidence. It must replay an existing successful
    response and expose unresolved transport attempts rather than silently retry.
    """
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('finite batch limit required')
    binding = json.loads(inbox.binding)
    if any(context.get(k) != binding[k] for k in ('subject','source_instance')):
        raise ValueError('producer context conflicts with capture binding')
    state_dir = Path(state_dir).absolute()
    if any(p.is_symlink() for p in [state_dir, *state_dir.parents]):
        raise ValueError('producer state directory cannot contain symlinks')
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    owner = dict(schema=SCHEMA, database=str(Path(memory.DB_PATH).resolve()),
                 state_dir=str(state_dir), capture_binding=digest(binding), context=context)
    # One coordinator location per inbox prevents separate launchers from creating
    # independent processing cursors. Capture uses another lock and can continue.
    with open(str(inbox.path)+'.producer.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with inbox.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS producer_owner(value TEXT NOT NULL)')
            con.execute('BEGIN IMMEDIATE')
            stored = con.execute('SELECT value FROM producer_owner').fetchone()
            if stored and stored[0] != wire(owner):
                raise ValueError('inbox is bound to a different producer destination')
            if stored is None:
                con.execute('INSERT INTO producer_owner VALUES(?)', (wire(owner),))
        index_path = state_dir/'index.json'
        index = json.loads(index_path.read_text()) if index_path.exists() else {
            'owner':owner,'after':0,'sequence':0,'source_revisions':{}}
        if index['owner'] != owner:
            raise ValueError('producer index binding differs')
        sequence = index['sequence']+1
        job_path = state_dir/f'batch-{sequence}.json'
        code_hash = digest([Path(selection.__file__).read_text(),
                            Path(selection.source_decision.__code__.co_filename).read_text(),
                            Path(__file__).read_text()])
        if job_path.exists():
            job = json.loads(job_path.read_text())
            if job['owner'] != owner or job['code_hash'] != code_hash:
                raise ValueError('pending producer code/binding changed; preserve and reconcile explicitly')
            if digest(job['inputs']) != job['input_hash']:
                raise ValueError('producer inputs changed')
        else:
            observations = inbox.observations(index['after'], limit)
            if not observations:
                return {'state':'idle','processed_through':index['after'],'proposer_invoked':False}
            latest = {}
            # A boundary hook may precede its prompt. Resolve bounded source
            # dependencies against the latest captured observation in one read
            # transaction, even when its event lies after this batch's cursor.
            with inbox.connect() as con:
                con.execute('BEGIN')
                for row in observations:
                    source = row['source']
                    if source not in latest:
                        latest[source] = dict(con.execute(
                            'SELECT * FROM observations WHERE source=? ORDER BY id DESC LIMIT 1',
                            (source,)).fetchone())
            if any(row['error'] or row['revision'] is None for row in latest.values()):
                return {'state':'deferred','reason':'incomplete source capture',
                        'processed_through':index['after'],'proposer_invoked':False}
            sources, revisions = [], {}
            for source, row in latest.items():
                snapshot = inbox.restore(row['revision'])
                previous = index['source_revisions'].get(source)
                normalized = selection.codex_sources(snapshot, source=source,
                    previous=inbox.restore(previous) if previous else None)
                if normalized['unsupported']:
                    return {'state':'deferred','reason':'unsupported source items',
                            'source':source,'details':normalized['unsupported'],
                            'processed_through':index['after'],'proposer_invoked':False}
                sources.extend(selection.block_sources(normalized, binding['source_instance']))
                revisions[source] = {'revision':row['revision'],'sha256':normalized['sha256']}
            # Do not consume an early hook prompt that has not yet reached its
            # transcript. A later Stop/Interrupt capture can complete that input.
            for row in observations:
                payload = json.loads(row['payload'])
                prompt = payload.get('prompt')
                if prompt and not any(prompt == s['content'] for s in sources):
                    return {'state':'deferred','reason':'prompt not yet in captured transcript',
                            'processed_through':index['after'],'proposer_invoked':False}
            memory.init_db()
            canon = _canon(memory)
            inputs = dict(observations=observations, sources=sources, revisions=revisions,
                          canon=canon, context=context, supporting_observations=list(latest.values()))
            if len(wire(inputs).encode()) > 1024 * 1024:
                return {'state':'deferred','reason':'batch exceeds bounded processing bytes',
                        'processed_through':index['after'],'proposer_invoked':False}
            request = dict(messages=selection.block_messages(sources,canon,context),
                           response_schema=selection.block_schema())
            job = dict(owner=owner, sequence=sequence, inputs=inputs,
                       input_hash=digest(inputs), code_hash=code_hash, request=request,
                       created_ns=time.time_ns(), state='prepared')
            checkpoint(job_path,job)
        inputs = job['inputs']
        # Each resume verifies the original dependency chain; metadata IDs alone
        # never prove that the source bytes needed by this job survived.
        originals = {}
        for source, revision in inputs['revisions'].items():
            data = inbox.restore(revision['revision'])
            if artifacts.sha(data) != revision['sha256']:
                raise ValueError('prepared source differs from retained bytes')
            originals['sources/'+digest(source)+'.jsonl'] = data
        proposer_invoked = False
        if 'proposal' not in job:
            if any(s['status']=='new' for s in inputs['sources']):
                work = state_dir/f"batch-{sequence}-dispatch-{job['created_ns']}"
                work.mkdir(exist_ok=True,mode=0o700)
                proposal = proposer(job['request'],work)
                proposer_invoked = True
            else:
                proposal = {'selection':dict(outcome='omitted',reason='No new source items; lifecycle metadata only.',records=[],links=[]),
                            'dispatch':{'model_calls':0}}
            # Preserve the untouched proposal before structural validation/writes.
            job['proposal'] = proposal
            job['state'] = 'proposed'
            checkpoint(job_path,job)
        decision = selection.selected_decision(job['proposal']['selection'], inputs['sources'], inputs['canon'])
        if decision['outcome'] == 'deferred':
            return {'state':'deferred','reason':decision['reason'],
                    'processed_through':index['after'],'proposer_invoked':proposer_invoked}
        originals.update({'request.json':wire(job['request']).encode(),
                          'proposal.json':wire(job['proposal']).encode(),
                          'capture.json':wire(inputs['observations']).encode(),
                          'producer.json':wire({'schema':SCHEMA,'owner':owner,
                            'code_hash':code_hash,'input_hash':job['input_hash']}).encode()})
        bundle = artifacts.learning_bundle(originals,source_instance=binding['source_instance'],
            subject=binding['subject'],source_event_id='portable-batch:'+job['input_hash'])
        backup = state_dir/f'batch-{sequence}-before.sqlite'
        if not backup.exists():
            verified_snapshot(memory.DB_PATH,backup)
        ledger = CaptureLedger(memory)
        event = dict(stream_id='portable:'+digest(owner),sequence=sequence,
            event_id='portable-batch:'+job['input_hash'],source_version=digest(inputs['revisions']),
            content=wire(inputs),metadata=dict(mode='reported',source_instance=binding['source_instance'],
                subject=binding['subject'],evidence=['artifact:sha256:'+bundle['artifact_id']]))
        staged = ledger.stage(event)
        if _fault:
            _fault('after_stage')
        def preserve(con):
            if decision['outcome'] != 'applied':
                return
            con.execute('CREATE TABLE IF NOT EXISTS native_learning_artifacts(artifact_id TEXT PRIMARY KEY,envelope_json TEXT NOT NULL)')
            con.execute('INSERT OR IGNORE INTO native_learning_artifacts VALUES(?,?)',(bundle['artifact_id'],wire(bundle)))
            if con.execute('SELECT envelope_json FROM native_learning_artifacts WHERE artifact_id=?',(bundle['artifact_id'],)).fetchone()[0] != wire(bundle):
                raise ValueError('retained producer artifact differs')
        receipt = ledger.assess(staged['event_key'],decision,_validator=preserve)
        if decision['outcome'] == 'applied' and artifacts.load_learning(memory,bundle['artifact_id']) != originals:
            raise ValueError('selected artifact did not survive intake')
        if _fault:
            _fault('after_canon_commit')
        artifact_id = bundle['artifact_id'] if decision['outcome'] == 'applied' else None
        job.update(state='complete',decision=decision,receipt=receipt,artifact_id=artifact_id)
        checkpoint(job_path,job)
        index['after'] = max(r['id'] for r in inputs['observations'])
        index['sequence'] = sequence
        index['source_revisions'].update({s:r['revision'] for s,r in inputs['revisions'].items()})
        checkpoint(index_path,index)
        return {'state':'complete','processed_through':index['after'],'receipt':receipt,
                'proposer_invoked':proposer_invoked,'artifact_id':artifact_id}


def reprepare_pending(memory, inbox, state_dir, reason):
    """Explicitly supersede a pre-stage proposal without dropping its sources.

    This is for changed representation or an invalid pre-stage decision, not for
    replacing committed memory. Dispatched attempts and exact jobs remain. A
    staged event must resume through its original writer or an attributed repair.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('explicit reconciliation reason required')
    state_dir = Path(state_dir).absolute()
    with open(str(inbox.path)+'.producer.lock','a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        index_path=state_dir/'index.json'
        sequence=json.loads(index_path.read_text())['sequence']+1 if index_path.exists() else 1
        path=state_dir/f'batch-{sequence}.json'
        job=json.loads(path.read_text())
        owner=job['owner']
        if (owner['database'] != str(Path(memory.DB_PATH).resolve()) or
                owner['state_dir'] != str(state_dir) or
                owner['capture_binding'] != digest(json.loads(inbox.binding))):
            raise ValueError('pending job binding differs')
        with memory.connect() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='capture_events'").fetchone():
                if con.execute('SELECT 1 FROM capture_events WHERE stream_id=? AND sequence=?',
                    ('portable:'+digest(owner),sequence)).fetchone():
                    raise ValueError('staged work cannot be replaced; resume its original decision')
        archive=state_dir/f"batch-{sequence}-superseded-{digest(job)}.json"
        checkpoint(archive.with_suffix('.reason.json'),dict(reason=reason,job_hash=digest(job)))
        os.replace(path,archive)
        sync_directory(state_dir)
        return {'state':'reprepare_required','preserved_job':str(archive),'cursor_advanced':False}
