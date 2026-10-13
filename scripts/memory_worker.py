"""Finite foreground owner of capture, organization and selected index work.

The receiving launcher supplies the reviewed organization adapter and provider
client. This module starts no timer, detached process or inference on import.
Status is a small receiving projection; source journals remain private.
"""
from __future__ import annotations

import fcntl
import json
from pathlib import Path
import time

from capturectl import digest
from codex_coordinator import checkpoint
from consolidationctl import reconciliation_plan
from portable_producer import process_once, maintain_index_once
from provider_status import ACTIONS, Alerts, ProviderProblem
from sqlite_snapshot import verified_snapshot

SCHEMA = 'hmk.worker-status/v1'
PHASES = ('capture','organization','index')


def observe(state_dir):
    """Read the last observation, without treating absent/stale data as healthy.

    An observer must compare updated_ns with its own receiving supervision policy.
    A running receipt does not prove the process still exists. No source names,
    exception text, credentials or private paths are exposed by this projection.
    """
    path = Path(state_dir)/'worker-status.json'
    if not path.is_file():
        return dict(schema=SCHEMA,state='unobserved',observed=False)
    value = json.loads(path.read_text())
    if value.get('schema') != SCHEMA or value.get('phase') not in (*PHASES,None):
        raise ValueError('unsupported worker status projection')
    return value


def run(memory, inbox, state_dir, proposer, context, *, organize=None, max_steps=6,
        source_budget_bytes=64000, navigation_steps=4, retrieval='hybrid',
        capture_limit=32, index_limit=32, notice_sender=None):
    """Invoke finite phases under one launcher lock, preserving each phase journal.

    `organize()` must return idle/complete/pending/deferred and own resumable,
    source-verified consolidation receipts. No configured adapter is an explicit
    unfinished phase, not a claim that accounts are current. A pending phase is
    not retried in this invocation. Other already-committed work may progress.
    """
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError('positive worker step budget required')
    for value in (capture_limit,index_limit):
        if type(value) is not int or value < 1:
            raise ValueError('positive phase work budget required')
    state_dir=Path(state_dir).absolute()
    if any(p.is_symlink() for p in [state_dir,*state_dir.parents]):
        raise ValueError('worker directory cannot contain symlinks')
    if any(context.get(k)!=v for k,v in json.loads(inbox.binding).items()):
        raise ValueError('worker context differs from capture binding')
    state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    owner=digest(dict(database=str(Path(memory.DB_PATH).resolve()),
                      inbox=str(inbox.path.resolve()),state_dir=str(state_dir),context=context))
    # The lock is adjacent to the inbox: a second caller cannot bypass it by
    # selecting another status directory. Existing producer locks still protect
    # individual APIs invoked independently of this foreground coordinator.
    with open(str(inbox.path)+'.worker.lock','a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        with inbox.connect() as con:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='producer_owner'").fetchone():
                producer=con.execute('SELECT value FROM producer_owner').fetchone()
                if producer:
                    selected=json.loads(producer[0])
                    if (selected['database']!=str(Path(memory.DB_PATH).resolve())
                            or selected['state_dir']!=str(state_dir)
                            or selected['context']!=context):
                        raise ValueError('worker conflicts with established producer destination')
            exists=con.execute("SELECT 1 FROM sqlite_master WHERE name='worker_owner'").fetchone()
        if not exists:
            verified_snapshot(inbox.path,state_dir/'capture-before-worker.sqlite')
        with inbox.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('CREATE TABLE IF NOT EXISTS worker_owner(value TEXT NOT NULL)')
            prior=con.execute('SELECT value FROM worker_owner').fetchone()
            if prior and prior[0]!=owner:
                raise ValueError('worker destination changed; explicit reconciliation required')
            if not prior:
                con.execute('INSERT INTO worker_owner VALUES(?)',(owner,))
        started=time.time_ns()
        status=dict(schema=SCHEMA,owner=owner,state='running',observed=True,
                    started_ns=started,updated_ns=started,phase=None,steps=0,phases={},
                    observation='Last foreground receipt, not proof of current process liveness.')
        path=state_dir/'worker-status.json'
        checkpoint(path,status)
        held=set()
        outcomes=[]
        cursor=0
        while len(outcomes)<max_steps:
            available=[p for p in PHASES if p not in held]
            if not available:
                break
            phase=PHASES[cursor%len(PHASES)]
            cursor+=1
            if phase in held:
                continue
            status.update(phase=phase,updated_ns=time.time_ns())
            checkpoint(path,status)
            operation='worker:'+owner+':'+phase
            try:
                if phase=='capture':
                    result=process_once(memory,inbox,state_dir,proposer,context,
                        limit=capture_limit,
                        navigation_steps=navigation_steps,retrieval=retrieval,
                        source_budget_bytes=source_budget_bytes,notice_sender=notice_sender)
                elif phase=='organization':
                    if organize:
                        result=organize()
                    else:
                        backlog=reconciliation_plan(memory,limit=1)
                        result=dict(state='pending',reason_code='organization_adapter_unconfigured',
                                    ready_accounts=backlog['ready_count'],blocked_accounts=backlog['blocked_count'])
                else:
                    result=maintain_index_once(memory,inbox,state_dir,limit=index_limit,
                                               notice_sender=notice_sender)
                    if result['state']=='idle':
                        capture_cursor=result.get('indexed_through')
                        result=maintain_index_once(memory,inbox,state_dir,limit=index_limit,
                            notice_sender=notice_sender,kind='organization')
                        result=dict(result,organization_indexed_through=result.get('indexed_through'),
                                    indexed_through=capture_cursor)
                if not isinstance(result,dict) or result.get('state') not in {'idle','complete','pending','deferred'}:
                    raise ValueError('phase returned an unsupported progress receipt')
            except ProviderProblem as failure:
                alerts=Alerts(inbox)
                alert_id=alerts.report(operation,phase,failure)
                if notice_sender is not None:
                    alerts.deliver(notice_sender)
                result=dict(state='pending',alert_id=alert_id,reason_code=failure.problem['code'])
            except Exception as error:
                # The phase's own journal, rather than arbitrary exception text,
                # establishes whether any transaction or remote request committed.
                result=dict(state='pending',reason_code='phase_failed',error_type=type(error).__name__)
            if result['state'] in {'idle','complete'}:
                Alerts(inbox).resolve(operation)
            outcomes.append(dict(phase=phase,result=result))
            safe={k:result[k] for k in ('state','reason_code','error_type','alert_id',
                'processed_through','indexed_through','source_group_complete',
                'minimum_required_bytes','processed','proposer_invoked',
                'ready_accounts','blocked_accounts','organized_through','organization_indexed_through') if k in result}
            problem=result.get('provider_problem',{})
            code=problem.get('code') or result.get('reason_code')
            if code in ACTIONS:
                safe.update(reason_code=code,action=ACTIONS[code])
            elif result.get('minimum_required_bytes'):
                safe['reason_code']='source_context_budget_exceeded'
            elif result['state'] in {'pending','deferred'} and not safe.get('reason_code'):
                safe['reason_code']='inspect_retained_phase_work'
            status['phases'][phase]=safe
            status.update(steps=len(outcomes),updated_ns=time.time_ns())
            checkpoint(path,status)
            if result['state'] in {'idle','pending','deferred'}:
                held.add(phase)
            elif phase=='capture':
                # A new canonical receipt invalidates earlier idle observations.
                for downstream in ('organization','index'):
                    if status['phases'].get(downstream,{}).get('state')=='idle':
                        held.discard(downstream)
            elif phase=='organization' and status['phases'].get('index',{}).get('state')=='idle':
                held.discard('index')
        states=[status['phases'].get(p,{}).get('state') for p in PHASES]
        status.update(state='idle' if states==['idle']*len(PHASES) else 'pending',
                      phase=None,updated_ns=time.time_ns(),budget_exhausted=len(outcomes)==max_steps)
        checkpoint(path,status)
        return dict(status=status,outcomes=outcomes)


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Read the last foreground worker observation; no processing or liveness claim.')
    parser.add_argument('command',choices=['status'])
    parser.add_argument('--state-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(observe(args.state_dir)))


if __name__=='__main__':
    main()
