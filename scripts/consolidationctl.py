#!/usr/bin/env python3
"""Preview and apply finite, evidence-linked dream proposals; no model or timer."""
from __future__ import annotations

import argparse
import json

import memoryctl as mc
from capturectl import CaptureLedger, digest
from support_currency import check, references


AUTO_SUPPORT_NOTE = 'Derived account; the source episode is not superseded.'
FIELDS = ('id','record_uid','revision','title','raw','spr','engram_type','event_ts','source_metadata_json')
ACCOUNT_SHELVES = ('library','plans','mc-social','mc-skills','mc-places')


def reconciliation_plan(memory=mc, *, limit=32):
    """Discover existing stale native accounts, without a persisted second queue.

    Current support must be reconciled before its dependents. Each result is a
    navigation hint: callers still read the full target and preview its current
    sources before proposing an update. A version check proves currency, not
    factual correctness. Missing/cyclic/protected support never becomes ready.
    `limit` bounds returned hints, not how much of the corpus can be discovered.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError('positive reconciliation result budget required')
    with memory.connect() as con:
        con.execute('BEGIN')
        rows = con.execute('''SELECT c.id,c.record_uid,c.revision,c.source_metadata_json,
            b.source_kind FROM chapters c JOIN books b ON b.id=c.book_id
            JOIN shelves s ON s.id=b.shelf_id
            WHERE c.engram_type IN ('semantic','procedural')
            AND json_extract(c.source_metadata_json,'$.mode') IN ('inferred','generated')
            AND b.source_kind IN ('text','capture','auto')
            AND s.name IN (SELECT value FROM json_each(?))
            AND NOT EXISTS (SELECT 1 FROM daimon_projections p WHERE p.chapter_id=c.id)
            ORDER BY c.id''', (json.dumps(ACCOUNT_SHELVES),)).fetchall()
        refs = {r['record_uid']:references(json.loads(r['source_metadata_json'] or '{}'),r['source_kind'])
                for r in rows}
        rows = [r for r in rows if refs[r['record_uid']]]
        wanted = sorted({uid for pairs in refs.values() for uid,_ in pairs})
        sources = {r['record_uid']:dict(r) for r in con.execute('''
            SELECT c.id,c.record_uid,c.revision,b.source_kind,
            EXISTS (SELECT 1 FROM daimon_projections p WHERE p.chapter_id=c.id) AS protected
            FROM chapters c JOIN books b ON b.id=c.book_id
            WHERE c.record_uid IN (SELECT value FROM json_each(?))''', (json.dumps(wanted),))}
        roots = [(r['record_uid'],r['revision']) for r in rows]
        roots.extend((r['record_uid'],r['revision']) for r in sources.values())
        currency = {(r['record_uid'],r['revision']):r for r in check(con,roots)}
        ready,blocked = [],[]
        for row in rows:
            state = currency[(row['record_uid'],row['revision'])]
            if state['status']=='current':
                continue
            item = dict(chapter_id=row['id'],record_uid=row['record_uid'],
                        expected_revision=row['revision'],support_checks=state,
                        supports=[],blockers=[])
            for uid,old_revision in refs[row['record_uid']]:
                current = sources.get(uid)
                if current is None:
                    item['blockers'].append(dict(record_uid=uid,reason='missing_support'))
                    continue
                status = currency[(uid,current['revision'])]['status']
                item['supports'].append(dict(chapter_id=current['id'],record_uid=uid,
                    previous_revision=old_revision,revision=current['revision']))
                reason = ('protected_support' if current['protected'] or current['source_kind'] not in {'text','capture','auto'}
                          else 'support_needs_reconciliation' if status!='current' else None)
                if reason:
                    item['blockers'].append(dict(record_uid=uid,reason=reason,status=status))
            (blocked if item['blockers'] else ready).append(item)
    return dict(schema='hmk.reconciliation-plan/v1',state='pending' if ready or blocked else 'idle',
                ready=ready[:limit],blocked=blocked[:limit],
                ready_count=len(ready),blocked_count=len(blocked),
                interpretation='Version currency only; full-source semantic assessment is required before writing.')


def snapshot(row):
    return {key: row[key] for key in FIELDS}


def preview(chapter_ids, memory=mc, *, profile='episodes'):
    """Full selected episode input, without a hidden per-source text cutoff."""
    if not chapter_ids or len(set(chapter_ids)) != len(chapter_ids):
        raise ValueError('select a nonempty finite set of distinct episodes')
    if profile not in {'episodes', 'native'}:
        raise ValueError('preview profile must be episodes or native')
    supports = []
    for cid in chapter_ids:
        row = memory._read_chapter(cid)
        if (row['origin']['kind'] == 'daimon-projection' or
                (profile == 'episodes' and row['engram_type'] != 'episodic') or
                (profile == 'native' and row['source_kind'] not in {'text', 'capture', 'auto'})):
            raise ValueError('generic dream input must be native episodes; protected sources keep their owner contract')
        with memory.connect() as con:
            stale = any(item['status'] != 'current' for item in check(con, references(
                json.loads(row['source_metadata_json'] or '{}'), row['source_kind'])))
        if row.get('support_status') == 'needs_reconciliation' or stale:
            raise ValueError('reconcile derived support before using it for consolidation')
        supports.append(dict(snapshot(row), source_kind=row['source_kind'])
                        if profile == 'native' else snapshot(row))
    return {'schema': 'hmk-dream-preview/v2' if profile == 'native' else 'hmk-dream-preview/v1', 'supports': supports,
            'fingerprint': digest(supports), 'input_count': len(supports),
            'independence': 'Input count does not establish independent corroboration.'}


def apply(manifest, decision, *, stream_id, sequence, event_id, selection_version, memory=mc, supports_by_record=None, _fault_hook=None):
    """Apply a reviewed proposal; evidence and writes share one transaction.

    A structurally valid inference is not evidence that its prose is true.
    The selecting body must inspect all supplied inputs, preserve uncertainty
    and evaluate the output against the capture/recall pilot contract.
    """
    if (not isinstance(manifest, dict) or manifest.get('schema') not in {'hmk-dream-preview/v1', 'hmk-dream-preview/v2'}
            or not isinstance(manifest.get('supports'), list) or not manifest['supports']
            or manifest.get('fingerprint') != digest(manifest['supports'])):
        raise ValueError('invalid evidence manifest')
    supports = manifest['supports']
    ids = [entry['id'] for entry in supports]
    if len(set(ids)) != len(ids):
        raise ValueError('a repeated episode does not provide independent corroboration')
    if decision.get('outcome') != 'applied' or not decision.get('records'):
        raise ValueError('consolidation requires selected account/learning proposals')
    keys = [item.get('key') for item in decision['records']]
    if any(not isinstance(key, str) or not key.strip() for key in keys):
        raise ValueError('consolidation record keys must be nonempty strings')
    if len(set(keys)) != len(keys):
        raise ValueError('consolidation record keys must be distinct')
    if supports_by_record is None:
        if manifest['schema'] == 'hmk-dream-preview/v2':
            raise ValueError('native consolidation needs explicit supports for every record')
        supports_by_record = {key: ids for key in keys}
    if not isinstance(supports_by_record, dict) or set(supports_by_record) != set(keys):
        raise ValueError('support map must cover every proposal record exactly')
    for key, selected in supports_by_record.items():
        if (not isinstance(selected, list) or not selected
                or any(type(cid) is not int or cid not in ids for cid in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError('record supports must be a nonempty distinct subset of the manifest')
    records = []
    for item in decision['records']:
        record = dict(item)
        if record.get('engram_type', 'semantic') not in {'semantic','procedural'}:
            raise ValueError('consolidation cannot create or replace lived episodes')
        if record.get('operation') == 'add' and record.get('shelf') not in {'library','plans','mc-social','mc-skills','mc-places'}:
            raise ValueError('generic dream proposals target knowledge/procedure shelves')
        selected = supports_by_record[record['key']]
        if (manifest['schema'] == 'hmk-dream-preview/v2' and
                record.get('operation') == 'update' and record.get('chapter_id') in selected):
            raise ValueError('a derived account cannot support its own update')
        metadata = dict(record.get('metadata') or {})
        if metadata.get('mode', 'inferred') not in {'inferred','generated'}:
            raise ValueError('consolidation is inferred/generated, not an independent observation')
        metadata.setdefault('mode', 'inferred')
        metadata['evidence'] = [f"mem:{entry['record_uid']}@{entry['revision']}" for entry in supports if entry['id'] in selected]
        records.append(dict(record, metadata=metadata, engram_type=record.get('engram_type','semantic')))
    if manifest['schema'] == 'hmk-dream-preview/v2':
        referenced = {cid for selected in supports_by_record.values() for cid in selected}
        if any(record.get('operation') == 'update' and record.get('chapter_id') in referenced
               for record in records):
            raise ValueError('a consolidation batch cannot update a record it also uses as support')
    links = list(decision.get('links', []))
    for record in records:
        links.extend({'source': record['key'], 'target': cid, 'link_type': 'supported-by',
                      'note': AUTO_SUPPORT_NOTE} for cid in supports_by_record[record['key']])
    proposal = dict(decision, records=records, links=links, selection_version=selection_version)
    ledger = CaptureLedger(memory)
    event = {'stream_id': stream_id, 'sequence': sequence, 'event_id': event_id,
             'source_version': manifest['fingerprint'],
             'content': json.dumps({'manifest': manifest, 'proposal': proposal}, ensure_ascii=False),
             'metadata': {'mode': 'inferred', 'evidence': [f"mem:{entry['record_uid']}@{entry['revision']}" for entry in supports]}}
    staged = ledger.stage(event)

    def validate(con):
        for entry in supports:
            row = con.execute('SELECT c.*,b.source_kind FROM chapters c JOIN books b ON b.id=c.book_id WHERE c.id=?', (entry['id'],)).fetchone()
            native = manifest['schema'] == 'hmk-dream-preview/v2'
            current = (dict(snapshot(row), source_kind=row['source_kind']) if native else snapshot(row)) if row else None
            if (not row or current != entry or
                    (not native and row['engram_type'] != 'episodic') or
                    (native and row['source_kind'] not in {'text', 'capture', 'auto'})):
                raise ValueError('support changed since preview; inspect a fresh manifest')
            if any(item['status'] != 'current' for item in check(con, references(
                    json.loads(row['source_metadata_json'] or '{}'), row['source_kind']))):
                raise ValueError('support dependency changed; reconcile before consolidation')
            if con.execute('SELECT 1 FROM daimon_projections WHERE chapter_id=?', (entry['id'],)).fetchone():
                raise ValueError('protected source cannot enter generic consolidation')
        for record in records:
            if record.get('operation') == 'update':
                target = con.execute('SELECT c.engram_type,s.name FROM chapters c JOIN books b ON b.id=c.book_id JOIN shelves s ON s.id=b.shelf_id WHERE c.id=?', (record.get('chapter_id'),)).fetchone()
                if not target or target[0] == 'episodic' or target[1] not in {'library','plans','mc-social','mc-skills','mc-places'}:
                    raise ValueError('consolidation cannot overwrite episodes/identity')

        for record in records:
            if record.get('operation') != 'update':
                continue
            cid = record['chapter_id']
            selected = supports_by_record[record['key']]
            for edge in con.execute("SELECT * FROM chapter_links WHERE src_chapter_id=? AND link_type='supported-by' AND note=?", (cid, AUTO_SUPPORT_NOTE)).fetchall():
                if edge['dst_chapter_id'] not in selected:
                    con.execute('INSERT OR IGNORE INTO chapter_links(src_chapter_id,dst_chapter_id,link_type,weight,note,created_at) '
                                'VALUES(?,?,?,?,?,?)', (cid,edge['dst_chapter_id'],'formerly-supported-by',edge['weight'],
                                'Earlier account support; inspect native revision evidence. '+(edge['note'] or ''),edge['created_at']))
                    con.execute("DELETE FROM chapter_links WHERE src_chapter_id=? AND dst_chapter_id=? AND link_type='supported-by'",
                                (cid, edge['dst_chapter_id']))

    return ledger.assess(staged['event_key'], proposal, _validator=validate, _fault_hook=_fault_hook)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    inspect = sub.add_parser('preview'); inspect.add_argument('--ids', nargs='+', type=int, required=True)
    inspect.add_argument('--profile', choices=('episodes','native'), default='episodes')
    reconcile = sub.add_parser('reconcile-plan')
    reconcile.add_argument('--limit', type=int, default=32)
    commit = sub.add_parser('apply'); commit.add_argument('--manifest', required=True); commit.add_argument('--proposal', required=True)
    commit.add_argument('--stream', required=True); commit.add_argument('--sequence', type=int, required=True)
    commit.add_argument('--record-supports', help='JSON map of proposal keys to selected manifest IDs')
    commit.add_argument('--event-id', required=True); commit.add_argument('--selection-version', required=True)
    args = parser.parse_args()
    if args.action == 'reconcile-plan':
        result = reconciliation_plan(limit=args.limit)
    elif args.action == 'preview':
        result = preview(args.ids, profile=args.profile)
    else:
        with open(args.manifest, encoding='utf-8') as handle:
            manifest = json.load(handle)
        with open(args.proposal, encoding='utf-8') as handle:
            proposal = json.load(handle)
        supports_by_record = None
        if args.record_supports:
            with open(args.record_supports, encoding='utf-8') as handle:
                supports_by_record = json.load(handle)
        result = apply(manifest, proposal, supports_by_record=supports_by_record,
                       stream_id=args.stream, sequence=args.sequence,
                       event_id=args.event_id, selection_version=args.selection_version)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
