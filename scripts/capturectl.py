#!/usr/bin/env python3
"""Finite, explicitly invoked HMK delta capture; no listeners or model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import time

import memoryctl as mc
import native_records
from capture_schema import RECORD_FIELDS, decision_schema
from sqlite_snapshot import verified_snapshot


def wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(wire(value).encode()).hexdigest()


class CaptureLedger:
    """Journal pending source deltas separately from selected autobiography.

    The caller selects the authorized stream and supplies source-qualified
    selection decisions. This ledger validates persistence, not factual meaning
    or permission. An event outcome, native writes and cursor commit atomically.
    """

    def __init__(self, memory=mc):
        self.mc = memory
        memory.init_db()
        con = memory.connect()
        try:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='capture_events'").fetchone():
                return
            if con.execute('SELECT 1 FROM chapters LIMIT 1').fetchone():
                verified_snapshot(memory.DB_PATH, f'{memory.DB_PATH}.bak.precapture.{time.time_ns()}')
            con.executescript("""BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS capture_streams (
                  stream_id TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS capture_events (
                  event_key TEXT PRIMARY KEY, stream_id TEXT NOT NULL REFERENCES capture_streams(stream_id),
                  sequence INTEGER NOT NULL, event_id TEXT NOT NULL, source_version TEXT NOT NULL,
                  payload_hash TEXT NOT NULL, payload_json TEXT, state TEXT NOT NULL DEFAULT 'pending'
                    CHECK(state IN ('pending','deferred','failed','applied','omitted')),
                  reason TEXT, decision_hash TEXT, receipt_json TEXT,
                  staged_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                  UNIQUE(stream_id,sequence), UNIQUE(stream_id,event_id,source_version));
                COMMIT;""")
        finally:
            con.close()

    def stage(self, event):
        required = {'stream_id', 'sequence', 'event_id', 'source_version', 'content', 'metadata'}
        if not isinstance(event, dict) or set(event) != required:
            raise ValueError('event requires stream_id, sequence, event_id, source_version, content and metadata')
        if any(not isinstance(event[key], str) or not event[key].strip()
               for key in required - {'sequence', 'metadata'}):
            raise ValueError('event identifiers and content must be nonempty strings')
        if type(event['sequence']) is not int or event['sequence'] <= 0:
            raise ValueError('stream sequence must be a positive integer; gaps remain pending')
        source = native_records.metadata(event['metadata'])
        if 'mode' not in source:
            raise ValueError('source mode must be explicit')
        for key, value in [('source_event_id', event['event_id']), ('source_version', event['source_version'])]:
            if key in source and source[key] != value:
                raise ValueError('source identity/version conflicts with event envelope')
            source[key] = value
        event = dict(event, metadata=source)
        key = digest([event['stream_id'], event['event_id'], event['source_version']])
        con = self.mc.connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM capture_events WHERE event_key=?', (key,)).fetchone()
            if old:
                if old['payload_hash'] != digest(event):
                    raise ValueError('source version reused with different content; existing event preserved')
                return self._receipt(con, old)
            con.execute('INSERT OR IGNORE INTO capture_streams(stream_id) VALUES(?)', (event['stream_id'],))
            cursor = con.execute('SELECT cursor FROM capture_streams WHERE stream_id=?', (event['stream_id'],)).fetchone()[0]
            if event['sequence'] <= cursor:
                raise ValueError('sequence precedes processed cursor')
            now = self.mc.now_ts()
            con.execute('INSERT INTO capture_events(event_key,stream_id,sequence,event_id,source_version,payload_hash,payload_json,staged_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                        (key, event['stream_id'], event['sequence'], event['event_id'], event['source_version'], digest(event), wire(event), now, now))
            con.commit()
            return self._receipt(con, con.execute('SELECT * FROM capture_events WHERE event_key=?', (key,)).fetchone())
        finally:
            con.close()

    def _receipt(self, con, row):
        receipt = json.loads(row['receipt_json']) if row['receipt_json'] else {}
        cursor = con.execute('SELECT cursor FROM capture_streams WHERE stream_id=?', (row['stream_id'],)).fetchone()[0]
        return {**receipt, 'event_key': row['event_key'], 'state': row['state'],
                'processed_through': cursor, 'reason': row['reason']}

    def pending(self, stream_id):
        con = self.mc.connect()
        try:
            rows = con.execute("SELECT * FROM capture_events WHERE stream_id=? AND state NOT IN ('applied','omitted') ORDER BY sequence", (stream_id,)).fetchall()
            return [{**self._receipt(con, row), 'event': json.loads(row['payload_json'])} for row in rows]
        finally:
            con.close()

    def assess(self, key, decision, *, _validator=None, _fault_hook=None):
        if not isinstance(decision, dict) or set(decision) - {'outcome','reason','records','links','selection_version'}:
            raise ValueError('unsupported selection fields')
        outcome = decision.get('outcome')
        if outcome not in {'applied','omitted','deferred'} or not isinstance(decision.get('reason'), str) or not decision['reason'].strip():
            raise ValueError('selection requires an outcome and explicit reason')
        records, links = decision.get('records', []), decision.get('links', [])
        if not isinstance(records, list) or not isinstance(links, list):
            raise ValueError('records and links must be lists')
        if (outcome != 'applied' and (records or links)) or (outcome == 'applied' and not (records or links)):
            raise ValueError('applied requires selected work; other outcomes cannot write memories')
        selection = decision.get('selection_version')
        if not isinstance(selection, str) or not selection.strip():
            raise ValueError('selection_version must identify the policy/model decision')
        con = self.mc.connect()
        try:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM capture_events WHERE event_key=?', (key,)).fetchone()
            if not row:
                raise ValueError('event not staged')
            if row['state'] in {'applied','omitted'}:
                if row['decision_hash'] != digest(decision):
                    raise ValueError('terminal decision replay differs; stage an attributed correction')
                return self._receipt(con, row)
            event = json.loads(row['payload_json'])
            if _validator:
                _validator(con)
            selected = {}
            for record in records:
                cid = self._write_record(con, event, record, selection, selected)
                chapter = dict(con.execute('SELECT * FROM chapters WHERE id=?', (cid,)).fetchone())
                try:
                    cfg = self.mc.embeddings_runtime_config()
                    embedded = con.execute('SELECT 1 FROM chapter_embeddings WHERE chapter_id=? AND provider=? AND model=? AND input_text_hash=?',
                                           (cid, cfg['provider'], cfg['model'], self.mc.text_hash(self.mc.embed_input_text(chapter)))).fetchone()
                    readiness = 'ready' if embedded else 'pending'
                except (ValueError, TypeError):
                    readiness = 'configuration_unavailable'
                selected[record['key']] = {'chapter_id': cid, 'record_uid': chapter['record_uid'],
                                           'revision': chapter['revision'], 'lexical_ready': True,
                                           'embedding_status': 'disabled' if chapter['embed_disabled'] else readiness}
            for link in links:
                if not isinstance(link, dict) or set(link) - {'source','target','link_type','weight','note'} or not {'source','target','link_type'}.issubset(link):
                    raise ValueError('invalid selected link')
                def resolve(value):
                    if type(value) is int:
                        if not con.execute('SELECT 1 FROM chapters WHERE id=?', (value,)).fetchone():
                            raise ValueError('link references an unknown chapter ID')
                        return value
                    if isinstance(value, str) and value in selected:
                        return selected[value]['chapter_id']
                    raise ValueError('link reference must be a selected record key or an existing integer chapter ID')
                self.mc.add_link(resolve(link['source']), resolve(link['target']), link['link_type'],
                                 weight=link.get('weight', 1.0), note=link.get('note'), _con=con)
            con.execute('UPDATE capture_events SET state=?,reason=?,decision_hash=?,receipt_json=?,payload_json=?,updated_at=? WHERE event_key=?',
                        (outcome, decision['reason'], digest(decision), wire({'records': selected, 'selection_version': selection}),
                         None if outcome in {'applied','omitted'} else row['payload_json'], self.mc.now_ts(), key))
            self._advance(con, row['stream_id'])
            if _fault_hook:
                _fault_hook('before_commit')
            con.commit()
            receipt = self._receipt(con, con.execute('SELECT * FROM capture_events WHERE event_key=?', (key,)).fetchone())
        except (Exception, SystemExit) as exc:
            con.rollback()
            # Preserve a retryable source payload. Don't echo arbitrary tool
            # exceptions, which can contain private source/endpoint material.
            if 'row' in locals() and row and row['state'] not in {'applied','omitted'}:
                code = 'native_revision_conflict' if isinstance(exc, SystemExit) and 'revision conflict' in str(exc) else type(exc).__name__
                con.execute("UPDATE capture_events SET state='failed',reason=?,decision_hash=?,updated_at=? WHERE event_key=?",
                            (code, digest(decision), self.mc.now_ts(), key))
                con.commit()
            raise
        finally:
            con.close()
        if _fault_hook:
            _fault_hook('after_commit')
        return receipt

    def _write_record(self, con, event, record, selection, selected):
        if not isinstance(record, dict) or set(record) - RECORD_FIELDS:
            raise ValueError('unsupported selected record fields; use capturectl decision-schema')
        if not isinstance(record.get('key'), str) or not record['key'] or record['key'] in selected:
            raise ValueError('invalid or duplicate selected record key')
        source = {**event['metadata'], **native_records.metadata(record.get('metadata')), 'selection_version': selection}
        for field in ('source_instance', 'source_uri'):
            if field in event['metadata'] and source.get(field) != event['metadata'][field]:
                raise ValueError('selection cannot silently change the originating source')
        source['source_event_id'], source['source_version'] = event['event_id'], event['source_version']
        if source.get('mode') == 'observed' and event['metadata']['mode'] != 'observed':
            raise ValueError('reported/inferred/generated source cannot become an independent observation')
        options = {key: record[key] for key in ('summary','tags','importance','engram_type','event_ts','actor','location') if key in record}
        options['metadata'] = source
        if record.get('operation') == 'add':
            if not all(isinstance(record.get(key), str) and record[key].strip() for key in ('shelf','title','raw')):
                raise ValueError('new selected records require shelf, title and self-contained raw text')
            if con.execute('SELECT 1 FROM books b JOIN shelves s ON s.id=b.shelf_id WHERE s.name=? AND b.title=?', (record['shelf'],record['title'])).fetchone():
                raise ValueError('selected title already exists; reconcile by explicit expected-revision update')
            return self.mc.add_text(record['shelf'], record['title'], record['raw'], source_kind='capture', _con=con, **options)
        if record.get('operation') == 'update' and type(record.get('chapter_id')) is int and type(record.get('expected_revision')) is int:
            return self.mc.update_chapter(record['chapter_id'], content=record.get('raw'), title=record.get('title'),
                                          expected_revision=record['expected_revision'], _con=con, **options)['chapter_id']
        raise ValueError('update requires chapter_id and observed expected_revision')

    def _advance(self, con, stream):
        cursor = con.execute('SELECT cursor FROM capture_streams WHERE stream_id=?', (stream,)).fetchone()[0]
        while True:
            row = con.execute('SELECT state FROM capture_events WHERE stream_id=? AND sequence=?', (stream, cursor+1)).fetchone()
            if not row or row[0] not in {'applied','omitted'}:
                break
            cursor += 1
        con.execute('UPDATE capture_streams SET cursor=? WHERE stream_id=?', (cursor, stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('decision-schema', help='Print the structural proposal schema without opening a pool')
    stage = sub.add_parser('stage'); stage.add_argument('--file', required=True)
    pending = sub.add_parser('pending'); pending.add_argument('--stream', required=True)
    assess = sub.add_parser('assess'); assess.add_argument('--event-key', required=True); assess.add_argument('--file', required=True)
    args = parser.parse_args()
    if args.action == 'decision-schema':
        print(json.dumps(decision_schema(), indent=2, ensure_ascii=False))
        return
    ledger = CaptureLedger()
    if args.action == 'pending':
        result = ledger.pending(args.stream)
    else:
        with open(args.file, encoding='utf-8') as handle:
            value = json.load(handle)
        result = ledger.stage(value) if args.action == 'stage' else ledger.assess(args.event_key, value)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
