"""Content-free accounting for retained Decisions receipts."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

LOCAL_ZONE = ZoneInfo('America/Argentina/Buenos_Aires')


def summarize(receipts):
    """Count matched requests once and keep missing usage visible."""
    totals = dict(received=0, metered=0, input_tokens=0, output_tokens=0,
                  cached_input_tokens=0, cached_input_reports=0)
    seen = set()
    for receipt in receipts:
        if receipt.get('state') != 'complete' or receipt['request_sha256'] in seen:
            continue
        seen.add(receipt['request_sha256'])
        totals['received'] += 1
        usage = receipt.get('usage')
        if not isinstance(usage, dict) or not all(
            type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens', 'output_tokens')
        ):
            continue
        totals['metered'] += 1
        totals['input_tokens'] += usage['input_tokens']
        totals['output_tokens'] += usage['output_tokens']
        cached = usage.get('cached_input_tokens')
        if type(cached) is int and 0 <= cached <= usage['input_tokens']:
            totals['cached_input_tokens'] += cached
            totals['cached_input_reports'] += 1
    totals['unknown_usage'] = totals['received'] - totals['metered']
    return totals


def day(timestamp_ns):
    return datetime.fromtimestamp(timestamp_ns / 1e9, timezone.utc).astimezone(LOCAL_ZONE).date()


def report(root, *, now_ns=None):
    """Read only committed receipts plus the existing bounded dispatch state."""
    from sleep_triage import MAX_PACKETS, MODEL

    root = Path(root)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError('private triage state required')
    paths = (root / 'packets').glob('*.json')
    receipts = {}
    def remember(receipt):
        if receipt and receipt.get('state') == 'complete':
            key = receipt['request_sha256']
            previous = receipts.setdefault(key, receipt)
            if previous != receipt:
                raise ValueError('conflicting copies of a Decisions receipt')

    for index, path in enumerate(paths):
        if index >= MAX_PACKETS or path.is_symlink() or path.stat().st_size > 262144:
            raise ValueError('unsupported retained receipt inventory')
        packet = json.loads(path.read_bytes())
        for key in ('decision', 'context_decision'):
            remember(packet.get(key))
    unresolved = 0
    for name in ('dispatch.json', 'context-dispatch.json'):
        path = root / name
        try:
            if path.is_symlink() or path.stat().st_size > 262144:
                raise ValueError('invalid active Decisions receipt')
            receipt = json.loads(path.read_bytes())
        except FileNotFoundError:
            continue
        if receipt.get('state') == 'complete':
            remember(receipt)
        else:
            unresolved += 1
    dated, undated = {}, []
    for receipt in receipts.values():
        stamp = receipt.get('completed_at_ns')
        if type(stamp) is int and stamp > 0:
            dated.setdefault(day(stamp), []).append(receipt)
        else:
            undated.append(receipt)
    today = day(time.time_ns() if now_ns is None else now_ns)
    return dict(schema='dmk.sleep-usage/v1', model=MODEL, timezone=LOCAL_ZONE.key,
                coverage='retained_decisions_receipts',
                as_of_day=today.isoformat(), unresolved_attempts=unresolved,
                retained=summarize(receipts.values()), undated=summarize(undated),
                days={date.isoformat(): summarize(dated[date]) for date in sorted(dated)
                      if 0 <= (today - date).days < 30},
                windows={str(days): summarize(receipt for date, receipts in dated.items()
                                              if 0 <= (today - date).days < days
                                              for receipt in receipts) for days in (7, 30)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(report(options.state_dir)))


if __name__ == '__main__':
    main()
