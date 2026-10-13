"""Safe provider failure classification and durable operational alert receipts.

This state belongs to processing, never autobiography. Delivery is invoked by the
owning launcher; the module starts no watcher, timer or model. No exception text,
response body, credential or source content is copied into a human notice.
"""
from __future__ import annotations

import json
import time
import urllib.error

from capturectl import digest, wire

ACTIONS = {
    'payment_required':'Restore provider credit, then explicitly resume the pending request.',
    'quota_exhausted':'Restore API quota or credit, then explicitly resume the pending request.',
    'authentication_failed':'Repair the configured API credential, then resume the pending request.',
    'access_denied':'Check model/account API access, then resume the pending request.',
    'rate_limited':'Wait for provider capacity, then resume the pending request.',
    'service_unavailable':'Check provider availability, then resume the pending request.',
    'timeout':'Check the recorded dispatch before retrying; remote completion is unknown.',
    'transport_error':'Check connectivity and the recorded dispatch; remote completion is unknown.',
    'invalid_request':'Correct the API request configuration before resuming.',
    'response_incomplete':'Inspect the retained response and output limit before resuming.',
    'dispatch_unresolved':'Reconcile the retained dispatch before another billable request.',
    'provider_error':'Inspect the retained provider status before resuming.',
}


def classify(error):
    status = error.code if isinstance(error,urllib.error.HTTPError) else None
    code = {400:'invalid_request',401:'authentication_failed',402:'payment_required',
            403:'access_denied',429:'rate_limited'}.get(status,'provider_error')
    if status is not None and 500 <= status < 600:
        code='service_unavailable'
    if isinstance(error,TimeoutError):
        code='timeout'
    elif isinstance(error,urllib.error.URLError) and status is None:
        code='timeout' if isinstance(error.reason,TimeoutError) else 'transport_error'
    # Some APIs report exhausted credit as 429. Read only a bounded JSON code;
    # retain neither the response text nor arbitrary strings in public status.
    if status == 429:
        try:
            payload=json.loads(error.read(8192))
            detail=payload.get('error',{})
            if isinstance(detail,dict) and any(isinstance(detail.get(k),str) and detail[k] in {
                    'insufficient_quota','insufficient_balance','credit_balance_too_low'} for k in ('code','type')):
                code='quota_exhausted'
        except (ValueError, OSError, AttributeError):
            pass
    return dict(code=code,http_status=status,action=ACTIONS[code],remote_completion='unknown')


class ProviderProblem(ValueError):
    def __init__(self, provider, request_id, problem):
        if problem.get('code') not in ACTIONS:
            raise ValueError('unsupported provider problem')
        self.provider=provider
        self.request_id=request_id
        self.problem=dict(code=problem['code'],action=ACTIONS[problem['code']],
            http_status=problem.get('http_status'),remote_completion=problem.get('remote_completion','unknown'))
        super().__init__(f"{provider}: {self.problem['code']}. {self.problem['action']}")


class Alerts:
    """An outbox in the bound capture journal; acknowledged delivery is explicit."""
    def __init__(self,inbox):
        self.inbox=inbox
        with inbox.connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS operational_alerts (
                id TEXT PRIMARY KEY, operation_key TEXT NOT NULL, phase TEXT NOT NULL,
                provider TEXT NOT NULL, problem_json TEXT NOT NULL, state TEXT NOT NULL,
                delivery TEXT NOT NULL, receipt_json TEXT, created_ns INTEGER NOT NULL,
                updated_ns INTEGER NOT NULL)''')

    def report(self, operation_key, phase, failure):
        key=digest([self.inbox.binding,operation_key,phase,failure.provider,failure.request_id,failure.problem['code']])
        now=time.time_ns()
        with self.inbox.connect() as con:
            con.execute('INSERT OR IGNORE INTO operational_alerts VALUES(?,?,?,?,?,?,?,?,?,?)',
                (key,operation_key,phase,failure.provider,wire(failure.problem),'open','pending',None,now,now))
        return key

    def resolve(self, operation_key):
        with self.inbox.connect() as con:
            con.execute("UPDATE operational_alerts SET state='resolved',updated_ns=? WHERE operation_key=? AND state='open'",
                (time.time_ns(),operation_key))

    def status(self):
        with self.inbox.connect() as con:
            rows=[dict(r) for r in con.execute('SELECT * FROM operational_alerts ORDER BY created_ns')]
        return dict(healthy=not any(r['state']=='open' for r in rows),
            undelivered=sum(r['state']=='open' and r['delivery']!='delivered' for r in rows),alerts=rows)

    def deliver(self, send):
        """Call a bound human-notice adapter once per notice; no implicit retry.

        `send` must return an observed delivery receipt with confirmed=True.
        After a crash or transport exception, delivery stays uncertain and visible.
        The caller must reconcile that outcome rather than risking duplicate sends.
        """
        for row in self.status()['alerts']:
            if row['state']!='open' or row['delivery']!='pending':
                continue
            with self.inbox.connect() as con:
                changed=con.execute("UPDATE operational_alerts SET delivery='uncertain',updated_ns=? WHERE id=? AND delivery='pending' AND state='open'",
                    (time.time_ns(),row['id'])).rowcount
            if not changed:
                continue
            problem=json.loads(row['problem_json'])
            notice=dict(id=row['id'],phase=row['phase'],provider=row['provider'],
                code=problem['code'],action=problem['action'],work_preserved=True)
            try:
                receipt=send(notice)
                if not isinstance(receipt,dict) or receipt.get('confirmed') is not True or not receipt.get('message_id'):
                    continue
                # Persist only delivery identifiers, never arbitrary adapter data.
                safe={k:receipt[k] for k in ('message_id','destination_id') if k in receipt}
                with self.inbox.connect() as con:
                    con.execute("UPDATE operational_alerts SET delivery='delivered',receipt_json=?,updated_ns=? WHERE id=?",
                        (wire(safe),time.time_ns(),row['id']))
            except Exception:
                # Do not hide it: status remains unhealthy with an undelivered
                # uncertain notice. No source work is acknowledged by this path.
                continue
        return self.status()


def safe_projection(inbox, *, after=0, limit=100):
    """Bounded read-only Alerts projection for the independent receiving observer.

    The caller supplies a read-only, binding-checked inbox connection. This reads
    the producer's operational outbox, never canonical memory or source bytes.
    Exporters own monotonic HTTP revisions; updated_ns remains source evidence.
    Service acceptance is not recorded as Telegram delivery in this journal.
    """
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('bounded operational projection required')
    with inbox.connect() as con:
        rows=con.execute('''SELECT rowid,id,operation_key,phase,problem_json,state,
            created_ns,updated_ns FROM operational_alerts WHERE rowid>?
            ORDER BY rowid LIMIT ?''',(after,limit+1)).fetchall()
    more=len(rows)>limit
    rows=rows[:limit]
    items=[]
    for row in rows:
        problem=json.loads(row['problem_json'])
        code=problem.get('code')
        phase=row['phase']
        if code not in ACTIONS or phase not in {'capture','selection','organization','consolidation','index'}:
            raise ValueError('unsupported operational projection')
        if row['state'] not in {'open','resolved'}:
            raise ValueError('unsupported processing state')
        created=row['created_ns']//1_000_000_000
        updated=row['updated_ns']//1_000_000_000
        items.append(dict(incident_id=digest(['hmk-alert',row['id']]),
            operation_id=digest(['hmk-operation',row['operation_key']]),phase=phase,
            severity='error' if row['state']=='open' else 'info',problem_code=code,
            summary=(f'Memory {phase} pending: {code.replace("_"," ")}.' if row['state']=='open'
                     else f'Memory {phase} completed after explicit producer recovery.'),
            action=ACTIONS[code],source_at=created,updated_at=max(created,updated),
            processing_state=row['state'],work_preserved=True))
    return dict(items=items,next_cursor=rows[-1]['rowid'] if more else None)
