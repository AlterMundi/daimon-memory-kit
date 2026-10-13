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
import selection_navigation
import source_windows
from provider_status import Alerts, ProviderProblem, classify
from sqlite_snapshot import verified_snapshot

SCHEMA = 'hmk.portable-producer/v1'


class CanonicalContextChanged(ValueError):
    """A concurrent canonical write invalidated the selection's read evidence."""


def _code_hash():
    return digest([Path(selection.__file__).read_text(),
                   Path(selection.source_decision.__code__.co_filename).read_text(),
                   Path(selection_navigation.__file__).read_text(),
                   Path(source_windows.__file__).read_text(),
                   Path(__file__).read_text()])


def _refresh_changed_context(memory, job, job_path):
    """Only a proven uncommitted revision conflict may reopen a selection.

    CaptureLedger's failed state is authoritative, including a crash before the
    producer could checkpoint the failure. The source event stays immutable.
    """
    with memory.connect() as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='capture_events'").fetchone():
            return
        row = con.execute('SELECT state,reason,payload_json,decision_hash FROM capture_events WHERE stream_id=? AND sequence=?',
            ('portable:'+digest(job['owner']),job['sequence'])).fetchone()
    if row is None or row['state'] != 'failed' or row['reason'] != 'CanonicalContextChanged':
        return
    if 'proposal' not in job:
        return  # Already reopened; do not discard the new attempt on each call.
    if not row['decision_hash'] or row['decision_hash'] != job.get('decision_hash'):
        return  # An earlier failed attempt cannot invalidate a newer proposal.
    event = json.loads(row['payload_json'])
    if event['content'] != wire(job['inputs']) or event['event_id'] != 'portable-batch:'+job['input_hash']:
        raise ValueError('failed source event does not match frozen producer input')
    job.setdefault('prior_attempts',[]).append(dict(reason='canonical_context_changed',
        proposal=job.pop('proposal'),navigation=job.pop('navigation',{})))
    job['context_attempt'] = job.get('context_attempt',0)+1
    job.pop('decision_hash',None)
    job['state'] = 'prepared'
    checkpoint(job_path,job)


def process_once(memory, inbox, state_dir, proposer, context, *, limit=32,
                 navigation_steps=4, retrieval='hybrid', source_budget_bytes=64000, notice_sender=None, _fault=None):
    """Process at most one frozen batch. Reinvocation resumes uncertain commits.

    proposer(request, directory) returns an auditable JSON object containing
    `selection` and dispatch evidence. It must replay an existing successful
    response and expose unresolved transport attempts rather than silently retry.
    """
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError('finite batch limit required')
    if type(navigation_steps) is not int or not 1 <= navigation_steps <= 32:
        raise ValueError('finite navigation step budget required')
    if retrieval not in {'lexical','hybrid'}:
        raise ValueError('unsupported retrieval mode')
    if type(source_budget_bytes) is not int or source_budget_bytes < 1:
        raise ValueError('positive source window byte budget required')
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
        code_hash = _code_hash()
        if job_path.exists():
            job = json.loads(job_path.read_text())
            if job['owner'] != owner or job['code_hash'] != code_hash:
                raise ValueError('pending producer code/binding changed; preserve and reconcile explicitly')
            if digest(job['inputs']) != job['input_hash']:
                raise ValueError('producer inputs changed')
        else:
            group_path = state_dir/f"source-group-after-{index['after']}.json"
            if group_path.exists():
                saved = json.loads(group_path.read_text())
                group = saved['group']
                if (saved['hash'] != digest(group) or group['owner'] != owner
                        or group['after'] != index['after']
                        or group['base_revisions'] != index['source_revisions']
                        or index.get('window_group',saved['hash']) != saved['hash']):
                    raise ValueError('frozen source group differs from committed progress')
                observations, latest = group['observations'], group['latest']
            else:
                if index.get('window_group') or index.get('window_progress'):
                    raise ValueError('missing frozen source group; preserve pending progress')
                observations = inbox.observations(index['after'], limit)
                if not observations:
                    return {'state':'idle','processed_through':index['after'],'proposer_invoked':False}
                latest = {}
                # Resolve early boundary prompts against one captured snapshot.
                # Once a window is prepared these revisions remain pinned until
                # the entire group finishes; later capture cannot move the target.
                with inbox.connect() as con:
                    con.execute('BEGIN')
                    for row in observations:
                        source = row['source']
                        if source not in latest:
                            latest[source] = dict(con.execute(
                                'SELECT * FROM observations WHERE source=? ORDER BY id DESC LIMIT 1',
                                (source,)).fetchone())
                group = dict(owner=owner,after=index['after'],observations=observations,
                             latest=latest,base_revisions=index['source_revisions'])
            if any(row['error'] or row['revision'] is None for row in latest.values()):
                return {'state':'deferred','reason':'incomplete source capture',
                        'processed_through':index['after'],'proposer_invoked':False}
            sources, revisions, groups = [], {}, {}
            for source, row in latest.items():
                snapshot = inbox.restore(row['revision'])
                previous = index['source_revisions'].get(source)
                prior = inbox.restore(previous) if previous else None
                dependencies = [r['revision'] for r in observations
                                if r['source'] == source and r['revision'] is not None]
                # A late older capture or in-place rewrite cannot erase an
                # intermediate acknowledged source or reset the novelty baseline.
                # Stock rollouts in this profile are append-only. Preserve any
                # divergent branch as pending until explicitly reconciled.
                if (prior is not None and not snapshot.startswith(prior)) or any(
                        not snapshot.startswith(inbox.restore(revision))
                        for revision in dependencies):
                    return {'state':'deferred','reason':'source revision branch requires reconciliation',
                            'source':source,'processed_through':index['after'],
                            'proposer_invoked':False}
                normalized = selection.codex_sources(snapshot, source=source, previous=prior)
                if normalized['unsupported']:
                    return {'state':'deferred','reason':'unsupported source items',
                            'source':source,'details':normalized['unsupported'],
                            'processed_through':index['after'],'proposer_invoked':False}
                groups[source] = selection.block_sources(normalized, binding['source_instance'])
                sources.extend(groups[source])
                revisions[source] = {'revision':row['revision'],'sha256':normalized['sha256']}
            # Do not consume an early hook prompt that has not yet reached its
            # transcript. A later Stop/Interrupt capture can complete that input.
            for row in observations:
                payload = json.loads(row['payload'])
                prompt = payload.get('prompt')
                if prompt and not any(prompt == s['content'] for s in sources):
                    return {'state':'deferred','reason':'prompt not yet in captured transcript',
                            'processed_through':index['after'],'proposer_invoked':False}
            if not group_path.exists():
                checkpoint(group_path,dict(group=group,hash=digest(group)))
            window = source_windows.select(groups,index.get('window_progress',{}),source_budget_bytes)
            if window['minimum_required_bytes'] is not None:
                return {'state':'pending','reason':'source dependency closure exceeds invocation budget',
                        'minimum_required_bytes':window['minimum_required_bytes'],
                        'source_budget_bytes':source_budget_bytes,
                        'processed_through':index['after'],'proposer_invoked':False}
            sources = window['sources']
            memory.init_db()
            inputs = dict(observations=observations, sources=sources, revisions=revisions,
                          context=context, supporting_observations=list(latest.values()),
                          source_window=dict(group_hash=digest(group),progress=window['progress'],
                              complete=window['complete'],budget_bytes=source_budget_bytes,
                              used_bytes=window['used_bytes']))
            request = dict(messages=selection.block_messages(sources,[],context),
                           response_schema=selection_navigation.response_schema())
            job = dict(owner=owner, sequence=sequence, inputs=inputs,
                       input_hash=digest(inputs), code_hash=code_hash, request=request,
                       retrieval=retrieval, created_ns=time.time_ns(), state='prepared')
            checkpoint(job_path,job)
        inputs = job['inputs']
        if job['retrieval'] != retrieval:
            raise ValueError('pending retrieval configuration changed; reconcile explicitly')
        _refresh_changed_context(memory,job,job_path)
        # Each resume verifies the original dependency chain; metadata IDs alone
        # never prove that the source bytes needed by this job survived.
        originals, source_groups = {}, {}
        for source, revision in inputs['revisions'].items():
            data = inbox.restore(revision['revision'])
            if artifacts.sha(data) != revision['sha256']:
                raise ValueError('prepared source differs from retained bytes')
            originals['sources/'+digest(source)+'.jsonl'] = data
            source_groups[source] = selection.block_sources(selection.codex_sources(data,source=source),binding['source_instance'])
        proposer_invoked = False
        if 'proposal' not in job:
            if any(s['status']=='new' for s in inputs['sources']):
                work = state_dir/f"batch-{sequence}-dispatch-{job['created_ns']}"
                if job.get('context_attempt'):
                    work = work/f"context-{job['context_attempt']}"
                work.mkdir(parents=True,exist_ok=True,mode=0o700)
                try:
                    proposal, dispatches = selection_navigation.advance(job,job_path,work,proposer,
                        database=memory.DB_PATH,steps=navigation_steps,retrieval=retrieval,
                        source_reader=source_windows.ContextReader(source_groups,source_budget_bytes))
                except ProviderProblem as failure:
                    alerts=Alerts(inbox)
                    alert_id=alerts.report(job['input_hash'],'selection',failure)
                    status=alerts.deliver(notice_sender) if notice_sender is not None else alerts.status()
                    delivery=next(r['delivery'] for r in status['alerts'] if r['id']==alert_id)
                    return {'state':'pending','reason':str(failure),'provider_problem':failure.problem,
                        'alert_id':alert_id,'notification_pending':delivery!='delivered','notification_delivery':delivery,
                        'processed_through':index['after'],
                        'proposer_invoked':True}
                proposer_invoked = bool(dispatches)
                if proposal is None:
                    pending = job['navigation'].get('source_budget_pending',{})
                    return {'state':'pending','reason':pending.get('reason') or job['navigation'].get('halted_reason','navigation invocation budget reached'),
                        'processed_through':index['after'],'proposer_invoked':proposer_invoked,
                        'minimum_required_bytes':pending.get('minimum_required_bytes'),
                        'navigation_steps':len(job['navigation']['steps'])}
            else:
                proposal = {'selection':dict(outcome='omitted',reason='No new source items; lifecycle metadata only.',records=[],links=[]),
                            'dispatch':{'model_calls':0}}
            # Preserve the untouched proposal before structural validation/writes.
            job['proposal'] = proposal
            job['state'] = 'proposed'
            checkpoint(job_path,job)
        canon = job.get('navigation',{}).get('canon',[])
        decision = selection.selected_decision(job['proposal']['selection'], selection_navigation.effective_sources(job), canon)
        if decision['outcome'] == 'deferred':
            return {'state':'deferred','reason':decision['reason'],
                    'processed_through':index['after'],'proposer_invoked':proposer_invoked}
        originals.update({'request.json':wire(job['request']).encode(),
                          'navigation.json':wire(job.get('navigation',{})).encode(),
                          'prior-attempts.json':wire(job.get('prior_attempts',[])).encode(),
                          'proposal.json':wire(job['proposal']).encode(),
                          'capture.json':wire(inputs['observations']).encode(),
                          'producer.json':wire({'schema':SCHEMA,'owner':owner,
                            'code_hash':code_hash,'input_hash':job['input_hash']}).encode()})
        bundle = artifacts.learning_bundle(originals,source_instance=binding['source_instance'],
            subject=binding['subject'],source_event_id='portable-batch:'+job['input_hash'])
        for record in decision['records']:
            record['metadata']['evidence'] = ['artifact:sha256:'+bundle['artifact_id']]
        backup = state_dir/f'batch-{sequence}-before.sqlite'
        if not backup.exists():
            verified_snapshot(memory.DB_PATH,backup)
        ledger = CaptureLedger(memory)
        event = dict(stream_id='portable:'+digest(owner),sequence=sequence,
            event_id='portable-batch:'+job['input_hash'],source_version=digest(inputs['revisions']),
            content=wire(inputs),metadata=dict(mode='reported',source_instance=binding['source_instance'],
                subject=binding['subject']))
        job['decision_hash'] = digest(decision)
        checkpoint(job_path,job)
        if _fault:
            _fault('before_stage')
        staged = ledger.stage(event)
        if _fault:
            _fault('after_stage')
        def preserve(con):
            if decision['outcome'] != 'applied':
                return
            # The reads and model calls occur outside the writer transaction.
            # Check their observed versions inside the same transaction as the
            # write; another session's correction must not be overwritten.
            for record in canon:
                current = con.execute('SELECT record_uid,revision FROM chapters WHERE id=?',
                                      (record['id'],)).fetchone()
                if current is None or tuple(current) != (record['record_uid'],record['revision']):
                    raise CanonicalContextChanged('navigated canonical evidence changed; reconcile pending work')
            con.execute('CREATE TABLE IF NOT EXISTS native_learning_artifacts(artifact_id TEXT PRIMARY KEY,envelope_json TEXT NOT NULL)')
            con.execute('INSERT OR IGNORE INTO native_learning_artifacts VALUES(?,?)',(bundle['artifact_id'],wire(bundle)))
            if con.execute('SELECT envelope_json FROM native_learning_artifacts WHERE artifact_id=?',(bundle['artifact_id'],)).fetchone()[0] != wire(bundle):
                raise ValueError('retained producer artifact differs')
        try:
            receipt = ledger.assess(staged['event_key'],decision,_validator=preserve)
        except CanonicalContextChanged:
            return {'state':'pending','reason':'canonical context changed; next invocation refreshes evidence',
                'processed_through':index['after'],'proposer_invoked':proposer_invoked,
                'event_key':staged['event_key']}
        if decision['outcome'] == 'applied' and artifacts.load_learning(memory,bundle['artifact_id']) != originals:
            raise ValueError('selected artifact did not survive intake')
        if _fault:
            _fault('after_canon_commit')
        artifact_id = bundle['artifact_id'] if decision['outcome'] == 'applied' else None
        job.update(state='complete',decision=decision,receipt=receipt,artifact_id=artifact_id)
        checkpoint(job_path,job)
        window = inputs.get('source_window')
        if window is None or window['complete']:
            index['after'] = max(r['id'] for r in inputs['observations'])
            index['source_revisions'].update({s:r['revision'] for s,r in inputs['revisions'].items()})
            index.pop('window_group',None)
            index.pop('window_progress',None)
        else:
            index['window_group'] = window['group_hash']
            index['window_progress'] = window['progress']
        index['sequence'] = sequence
        Alerts(inbox).resolve(job['input_hash'])
        checkpoint(index_path,index)
        return {'state':'complete','processed_through':index['after'],'receipt':receipt,
                'proposer_invoked':proposer_invoked,'artifact_id':artifact_id,
                'source_group_complete':window is None or window['complete'],
                'source_progress':window['progress'] if window else None}


def maintain_index_once(memory, inbox, state_dir, *, limit=32, batch_size=8, notice_sender=None, _fault=None, kind='capture'):
    """Explicit bounded index work from committed capture receipts, independently resumable.

    This cannot acknowledge capture or invoke selection. The receiving launcher
    schedules both operations; no native learning, timer or background job starts.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError('positive index work budget required')
    if kind not in {'capture','organization'}:
        raise ValueError('index only owner-bound capture or organization receipts')
    state_dir = Path(state_dir).absolute()
    if any(p.is_symlink() for p in [state_dir,*state_dir.parents]):
        raise ValueError('producer state directory cannot contain symlinks')
    with open(str(inbox.path)+'.producer.lock','a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        with inbox.connect() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='producer_owner'").fetchone():
                raise ValueError('index work requires an established producer binding')
            row = con.execute('SELECT value FROM producer_owner').fetchone()
        owner = json.loads(row[0]) if row else {}
        if (owner.get('database') != str(Path(memory.DB_PATH).resolve())
                or owner.get('state_dir') != str(state_dir)
                or owner.get('capture_binding') != digest(json.loads(inbox.binding))):
            raise ValueError('index work binding differs')
        cfg = memory.embeddings_runtime_config()
        path = state_dir/('embedding-index.json' if kind=='capture' else 'embedding-organization-index.json')
        state = json.loads(path.read_text()) if path.exists() else dict(owner=owner,space=cfg,after=0)
        if state['owner'] != owner or state['space'] != cfg:
            raise ValueError('index space or binding changed; explicit migration required')
        # The canonical ledger is authoritative, even after a crash before the
        # capture index checkpoint. Never scan other streams or private pools.
        with memory.connect() as con:
            if not con.execute("SELECT 1 FROM sqlite_master WHERE name='capture_events'").fetchone():
                return dict(state='idle',indexed_through=state['after'],space=cfg)
            row = con.execute("SELECT sequence,state,receipt_json FROM capture_events WHERE stream_id=? AND sequence>? ORDER BY sequence LIMIT 1",
                (('portable:' if kind=='capture' else 'organization:')+digest(owner),state['after'])).fetchone()
        if row is None:
            return dict(state='idle',indexed_through=state['after'],space=cfg)
        if row['state'] not in {'applied','omitted'}:
            return dict(state='pending',reason='capture event is not committed',indexed_through=state['after'])
        receipt = json.loads(row['receipt_json'])
        uids = sorted({r['record_uid'] for r in receipt['records'].values()})
        with memory.connect() as con:
            found = {r[0] for r in con.execute('SELECT record_uid FROM chapters WHERE record_uid IN (SELECT value FROM json_each(?))',(wire(uids),))}
        if found != set(uids):
            return dict(state='pending',reason='committed records missing',indexed_through=state['after'])
        operation = 'embedding:'+digest([owner,row['sequence'],cfg] if kind=='capture'
                                        else [owner,kind,row['sequence'],cfg])
        if not path.exists():
            checkpoint(path,state)  # Pin the space before any paid work, including failures.
        pending = memory.embedding_candidates(provider=cfg['provider'],model=cfg['model'],record_uids=uids,limit=limit)
        processed = 0
        if pending:
            prefix='embedding' if kind=='capture' else 'embedding-organization'
            backup = state_dir/f"{prefix}-{row['sequence']}-before.sqlite"
            if not backup.exists():
                verified_snapshot(memory.DB_PATH,backup)
            try:
                result = memory.backfill_embeddings(provider=cfg['provider'],model=cfg['model'],
                    record_uids=uids,limit=limit,batch_size=batch_size)
                processed = result['processed']
            except memory.EmbeddingBackendError as error:
                problem = classify(error.__cause__ if error.__cause__ is not None else error)
                alerts = Alerts(inbox)
                alert_id = alerts.report(operation,'embedding',ProviderProblem(cfg['provider'],operation,problem))
                status = alerts.deliver(notice_sender) if notice_sender is not None else alerts.status()
                return dict(state='pending',reason='embedding backend unavailable',provider_problem=problem,
                    alert_id=alert_id,notification_pending=bool(status['undelivered']),indexed_through=state['after'])
        if _fault:
            _fault('after_embedding_commit')
        pending = memory.embedding_candidates(provider=cfg['provider'],model=cfg['model'],record_uids=uids,limit=1)
        if pending:
            return dict(state='pending',reason='index work remains',processed=processed,indexed_through=state['after'])
        Alerts(inbox).resolve(operation)
        state['after'] = row['sequence']
        checkpoint(path,state)
        return dict(state='complete',processed=processed,indexed_through=state['after'],space=cfg)


def reprepare_pending(memory, inbox, state_dir, reason, *, preserve_navigation=False):
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
        if preserve_navigation:
            if 'navigation' not in job or digest(job['inputs']) != job['input_hash']:
                raise ValueError('verified frozen navigation is required')
            checkpoint(archive,job)
            job.pop('proposal',None)
            job['code_hash'] = _code_hash()
            job['state'] = 'prepared'
            # Retain every response, including invalid ones. The new validator
            # can process the saved final response before another dispatch.
            # A code upgrade never resets the persisted correction budget.
            checkpoint(path,job)
            return {'state':'navigation_preserved','preserved_job':str(archive),'cursor_advanced':False}
        os.replace(path,archive)
        sync_directory(state_dir)
        return {'state':'reprepare_required','preserved_job':str(archive),'cursor_advanced':False}
