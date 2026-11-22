#!/usr/bin/env python3
"""Read existing DMK and Matrix observations without starting either worker."""
import argparse
import json
from pathlib import Path
import time

from memory_worker import observe


def fresh(timestamp, now, max_age):
    return type(timestamp) is int and 0 <= now - timestamp <= max_age


def health(worker_dir, source_report, *, max_age_seconds, now_ns=None):
    if type(max_age_seconds) is not int or max_age_seconds < 1:
        raise ValueError('positive freshness limit required')
    now = time.time_ns() if now_ns is None else now_ns
    limit = max_age_seconds * 1_000_000_000
    try:
        worker = observe(worker_dir)
    except (OSError, ValueError):
        worker = {}
    phases = worker.get('phases', {})
    fresh_worker = fresh(worker.get('updated_ns'), now, limit)
    dmk = {}
    for phase in ('capture', 'organization', 'index', 'backup'):
        row = worker.get('backup', {}) if phase == 'backup' else phases.get(phase, {})
        state = row.get('state', 'unobserved')
        healthy = {'current'} if phase == 'backup' else {'idle', 'complete'}
        if not fresh_worker:
            status = 'stale' if worker.get('observed') else 'unobserved'
        elif phase == 'backup' and state == 'current' and not fresh(row.get('last_verified_ns'), now, limit):
            status = 'stale'
        elif state in healthy:
            status = 'observed'
        elif state in {'pending', 'deferred', 'failed'}:
            status = 'blocked'
        else:
            status = 'unobserved'
        dmk[phase] = dict(status=status, phase_state=state, reason_code=row.get('reason_code'))
        if type(row.get('minimum_required_bytes')) is int:
            dmk[phase]['minimum_required_bytes'] = row['minimum_required_bytes']
    try:
        report = json.loads(Path(source_report).read_text())
        if report.get('schema') != 'dm.source-review/v2' or type(report['observed_at_ms']) is not int:
            raise ValueError('unsupported Matrix Source review receipt')
        seen = report['observed_at_ms'] * 1_000_000
        unavailable = report['unavailable']
        unconfirmed = report['unconfirmed_targets']
        if not isinstance(unavailable, list) or not isinstance(unconfirmed, list):
            raise ValueError('invalid Matrix Source review coverage')
        state = ('stale' if not fresh(seen, now, limit) else
                 'partial' if unavailable or unconfirmed else 'observed')
        discovery = dict(status=state, observed_at_ms=report['observed_at_ms'],
                         unavailable=len(unavailable), unconfirmed=len(unconfirmed))
    except (OSError, ValueError, KeyError, AttributeError):
        discovery = dict(status='unobserved')
    return dict(
        dmk=dmk,
        matrix=dict(source_review=discovery, receiving_learning='requires_receiving_evidence'),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-dir', type=Path, required=True)
    parser.add_argument('--source-review-report', type=Path, required=True)
    parser.add_argument('--max-age-seconds', type=int, required=True)
    args = parser.parse_args()
    result = health(args.worker_dir, args.source_review_report, max_age_seconds=args.max_age_seconds)
    print(json.dumps(result))
    # A metadata-only check can never certify uptake. Its exit code covers
    # only the observed operational phases and offer discovery.
    return 0 if (all(row['status'] == 'observed' for row in result['dmk'].values())
                 and result['matrix']['source_review']['status'] == 'observed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
