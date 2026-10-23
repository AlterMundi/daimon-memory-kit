"""Finite unsigned native-memory exchange through the current DMK write API.

Packets are private migration input, never signed Matrix autobiography or
execution instructions. The caller supplies the receiving owner's existing
binding and pre-write backup lifecycle. No models, embedding, service control,
credentials, startup attention or whole-database replacement.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

SCHEMA = 'dmk.same-being-native/v1'
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 128
BINDING_FIELDS = {'being_ref', 'body_ref', 'embodiment_id', 'incarnation_id', 'pool_lineage'}
VOLATILE = {'last_access', 'access_count'}
PREFIX = 'dmk:same-being:'


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(wire(value)).hexdigest()


def binding(value):
    if (not isinstance(value, dict) or set(value) != BINDING_FIELDS
            or any(not isinstance(v, str) or not 1 <= len(v) <= 256 for v in value.values())):
        raise ValueError('explicit receiving owner/pool binding required')
    return dict(value)


def database(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('native database alias requires local reconciliation')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('existing owner native database required')
    return path


def table(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def record(con, chapter_id):
    row = con.execute('SELECT c.*,b.title AS book_title,b.slug AS book_slug,'
        'b.source_path AS book_source_path,b.source_kind AS book_source_kind,'
        's.name AS shelf_name FROM chapters c JOIN books b ON b.id=c.book_id '
        'JOIN shelves s ON s.id=b.shelf_id WHERE c.id=?', (chapter_id,)).fetchone()
    return {k: v for k, v in dict(row).items() if k not in VOLATILE} if row else None


def protected(con, chapter_id):
    return table(con, 'daimon_projections') and con.execute(
        'SELECT 1 FROM daimon_projections WHERE chapter_id=?', (chapter_id,)).fetchone() is not None


def uid(row):
    return row.get('record_uid') or 'legacy-row:' + str(row['id'])


def logical_key(owner, row):
    return digest(dict(being_ref=owner['being_ref'], pool_lineage=owner['pool_lineage'], record_uid=uid(row)))


def _document(con, chapter_id, owner):
    row = record(con, chapter_id)
    if row is None or protected(con, chapter_id) or row['book_source_kind'] == 'daimon-projection':
        return None
    if (row.get('book_source_path') or '').startswith(('hmk-native-sync:v1:','hmk-snapshot:')):
        raise ValueError('legacy native provenance needs the existing selected sidecar adapter')
    prior = []
    if table(con, 'dmk_sync_bindings') and row.get('record_uid'):
        saved = con.execute('SELECT b.origin_hash,b.applied_hash,o.document FROM dmk_sync_bindings b '
            'JOIN dmk_sync_origins o ON o.origin_hash=b.origin_hash WHERE b.target_uid=?',
            (row['record_uid'],)).fetchall()
        exact=[item for item in saved if item['applied_hash']==digest(row)]
        if len(exact)>1:
            raise ValueError('ambiguous native origin representation; preserve variants')
        if exact:
            return json.loads(exact[0]['document'])
        prior=sorted(item['origin_hash'] for item in saved)
    history = []
    if row.get('record_uid') and table(con, 'chapter_revisions'):
        history = [dict(r) for r in con.execute('SELECT * FROM chapter_revisions '
            'WHERE record_uid=? ORDER BY revision,id', (row['record_uid'],))]
    # Export observation is in the packet header. Unknown historical record
    # incarnation must not be assigned the incarnation that merely read it.
    source_owner=dict(owner,incarnation_id=None)
    return dict(source_binding=source_owner, logical_key=logical_key(owner, row),
        record=row, history=history, prior_origins=prior,
        provenance='unsigned-native-record' if row.get('record_uid') else 'unsigned-legacy-pool-lineage')


def export(database_path, owner, *, after=0, limit=64, known=()):
    """One consistent bounded page, without mutating even an older source pool."""
    owner = binding(owner)
    path = database(database_path)
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= MAX_RECORDS:
        raise ValueError('bounded native page required')
    if not isinstance(known, (list, tuple, set)) or any(not re.fullmatch('[0-9a-f]{64}', k) for k in known):
        raise ValueError('exact known native origin hashes required')
    known = set(known)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        con.row_factory = sqlite3.Row
        con.execute('BEGIN')
        candidates = con.execute('SELECT id FROM chapters WHERE id>? ORDER BY id LIMIT ?', (after, limit + 1)).fetchall()
        selected = candidates[:limit]
        documents, by_id, omissions = [], {}, []
        for item in selected:
            doc = _document(con, item['id'], owner)
            if doc is None:
                omissions.append(dict(chapter_id=item['id'], reason='signed_projection_uses_matrix_adapter'))
                continue
            key = digest(doc)
            by_id[item['id']] = key
            if key not in known:
                documents.append(dict(origin_hash=key, document=doc))
        edges = []
        if selected and table(con, 'chapter_links'):
            ids = [r['id'] for r in selected]
            placeholders = ','.join('?' for _ in ids)
            for edge in con.execute(f'SELECT * FROM chapter_links WHERE src_chapter_id IN ({placeholders}) '
                                    f'OR dst_chapter_id IN ({placeholders}) ORDER BY id', (*ids, *ids)):
                row = dict(edge)
                endpoints = []
                for endpoint in ('src_chapter_id', 'dst_chapter_id'):
                    if row[endpoint] not in by_id:
                        doc = _document(con, row[endpoint], owner)
                        by_id[row[endpoint]] = digest(doc) if doc else None
                    endpoints.append(by_id[row[endpoint]])
                edges.append(dict(source_origin=endpoints[0], target_origin=endpoints[1], original=row))
    packet = dict(schema=SCHEMA, being_ref=owner['being_ref'], exporter=owner,
        records=documents, links=edges, omissions=omissions,
        cursor=selected[-1]['id'] if selected else after, more=len(candidates) > limit)
    if len(wire(packet)) > MAX_BYTES:
        raise ValueError('native packet exceeds budget; select a smaller page, preserve originals')
    return packet


def _validate_packet(packet, owner):
    owner = binding(owner)
    if (not isinstance(packet, dict) or set(packet) != {'schema','being_ref','exporter','records','links','omissions','cursor','more'}
            or packet['schema'] != SCHEMA or packet['being_ref'] != owner['being_ref']
            or binding(packet['exporter'])['being_ref'] != owner['being_ref']
            or len(wire(packet)) > MAX_BYTES or not isinstance(packet['records'], list)
            or len(packet['records']) > MAX_RECORDS or type(packet['cursor']) is not int
            or packet['cursor']<0 or type(packet['more']) is not bool
            or not isinstance(packet['links'],list) or not isinstance(packet['omissions'],list)):
        raise ValueError('same-being bounded native packet required')
    seen = set()
    for entry in packet['records']:
        if not isinstance(entry, dict) or set(entry) != {'origin_hash','document'}:
            raise ValueError('closed native origin entry required')
        doc = entry['document']
        if (not isinstance(doc, dict) or set(doc) != {'source_binding','logical_key','record','history','prior_origins','provenance'}
                or digest(doc) != entry['origin_hash'] or entry['origin_hash'] in seen
                or binding(dict(doc['source_binding'],incarnation_id='unknown-record-origin'))['being_ref'] != owner['being_ref']
                or doc['source_binding']['incarnation_id'] is not None
                or logical_key(doc['source_binding'], doc['record']) != doc['logical_key']
                or doc['record']['book_source_kind'] == 'daimon-projection'
                or doc['record']['shelf_name'] == 'daimon-projection'
                or not isinstance(doc['history'], list)):
            raise ValueError('native origin history/hash mismatch')
        row = doc['record']
        if (not isinstance(doc['prior_origins'],list)
                or doc['prior_origins']!=sorted(set(doc['prior_origins']))
                or any(not re.fullmatch('[0-9a-f]{64}',item) for item in doc['prior_origins'])):
            raise ValueError('exact prior native origins required')
        if doc['provenance'] not in {'unsigned-native-record','unsigned-legacy-pool-lineage'}:
            raise ValueError('unsigned native provenance required')
        for revision in doc['history']:
            if not isinstance(revision,dict) or not {'snapshot_json','record_uid','revision','reason','archived_at'} <= set(revision):
                raise ValueError('complete native revision snapshot required')
            snapshot=json.loads(revision['snapshot_json'])
            if (not isinstance(snapshot,dict) or not isinstance(snapshot.get('raw'),str)
                    or not isinstance(snapshot.get('spr'),str) or revision['record_uid']!=row.get('record_uid')):
                raise ValueError('native revision source differs')
        if (not isinstance(row['raw'], str) or not isinstance(row['spr'], str)
                or not isinstance(json.loads(row['tags_json']), list)
                or not isinstance(row['importance'], (int,float)) or not math.isfinite(row['importance'])):
            raise ValueError('native content is not representable')
        seen.add(entry['origin_hash'])
    for edge in packet['links']:
        if not isinstance(edge,dict) or set(edge) != {'source_origin','target_origin','original'}:
            raise ValueError('closed native edge required')
        for key in ('source_origin','target_origin'):
            if edge[key] is not None and not re.fullmatch('[0-9a-f]{64}', edge[key]):
                raise ValueError('exact native edge reference required')
    return owner


def _schema(con, owner):
    con.execute('CREATE TABLE IF NOT EXISTS dmk_sync_owner(being_ref TEXT PRIMARY KEY)')
    prior = con.execute('SELECT being_ref FROM dmk_sync_owner').fetchall()
    if prior and (len(prior) != 1 or prior[0][0] != owner['being_ref']):
        raise ValueError('native pool belongs to another being')
    con.execute('INSERT OR IGNORE INTO dmk_sync_owner VALUES(?)', (owner['being_ref'],))
    con.execute('CREATE TABLE IF NOT EXISTS dmk_sync_origins(origin_hash TEXT PRIMARY KEY,'
        'logical_key TEXT NOT NULL,document TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS dmk_sync_bindings(origin_hash TEXT PRIMARY KEY '
        'REFERENCES dmk_sync_origins(origin_hash),target_uid TEXT NOT NULL,applied_hash TEXT NOT NULL,original_native INTEGER NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS dmk_sync_operations(operation_id TEXT PRIMARY KEY,'
        'packet_hash TEXT NOT NULL,binding_hash TEXT NOT NULL,result TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS dmk_sync_edges(edge_hash TEXT PRIMARY KEY,'
        'document TEXT NOT NULL,state TEXT NOT NULL)')


def _bound_record(con, origin):
    saved = con.execute('SELECT target_uid,applied_hash FROM dmk_sync_bindings WHERE origin_hash=?', (origin,)).fetchone()
    if not saved:
        return None
    row = con.execute('SELECT id FROM chapters WHERE record_uid=?', (saved['target_uid'],)).fetchone()
    if row is None or protected(con,row['id']) or digest(record(con, row['id'])) != saved['applied_hash']:
        raise ValueError('imported native record changed; preserve local variant before reconciliation')
    return row['id']


def _continues(doc, previous):
    current,old=doc['record'],previous['record']
    if (not current.get('record_uid') or current.get('record_uid')!=old.get('record_uid')
            or doc['source_binding']!=previous['source_binding']
            or current.get('revision',0)<=old.get('revision',0)):
        return False
    fields=('raw','spr','title','tags_json','importance','engram_type','event_ts',
            'actor','location_json','source_metadata_json')
    return any(all(json.loads(v['snapshot_json']).get(k)==old.get(k) for k in fields)
               for v in doc['history'])


def _import(memory, con, entry, owner):
    origin, doc = entry['origin_hash'], entry['document']
    old = con.execute('SELECT document FROM dmk_sync_origins WHERE origin_hash=?', (origin,)).fetchone()
    if old:
        if json.loads(old['document']) != doc:
            raise ValueError('native origin bytes changed')
        target = _bound_record(con, origin)
        if target is None:
            raise ValueError('native origin lost its receiving binding')
        return target, False
    source = doc['record']
    if memory.normalize_text(source['raw']) != source['raw'] or memory.normalize_text(source['spr']) != source['spr']:
        raise ValueError('native import would normalize original content')
    if doc['source_binding']['pool_lineage']==owner['pool_lineage']:
        own=con.execute('SELECT id FROM chapters WHERE record_uid=?', (source.get('record_uid'),)).fetchone() if source.get('record_uid') else con.execute('SELECT id FROM chapters WHERE id=?',(source['id'],)).fetchone()
        if own:
            actual=record(con,own['id'])
            if protected(con,own['id']) or any(actual.get(k)!=v for k,v in source.items()):
                raise ValueError('original native record changed; retain its local correction')
            con.execute('INSERT INTO dmk_sync_origins VALUES(?,?,?)', (origin,doc['logical_key'],wire(doc).decode()))
            con.execute('INSERT INTO dmk_sync_bindings VALUES(?,?,?,1)',(origin,actual['record_uid'],digest(actual)))
            return own['id'],False
    title = 'Sync ' + origin[:16] + ' ' + str(source['title'] or source['book_title'])
    if con.execute('SELECT 1 FROM books b JOIN shelves s ON s.id=b.shelf_id WHERE s.name=? AND b.slug=?',
                   (source['shelf_name'], memory.slugify(title))).fetchone():
        raise ValueError('native import title collision; existing content preserved')
    metadata = json.loads(source.get('source_metadata_json') or '{}')
    mirrors=con.execute('SELECT b.target_uid,b.applied_hash,o.document FROM dmk_sync_bindings b '
        'JOIN dmk_sync_origins o ON o.origin_hash=b.origin_hash WHERE o.logical_key=? '
        'AND b.original_native=0',(doc['logical_key'],)).fetchall()
    continuing=[]
    for mirror in mirrors:
        native=con.execute('SELECT id FROM chapters WHERE record_uid=?',(mirror['target_uid'],)).fetchone()
        if (native and digest(record(con,native['id']))==mirror['applied_hash']
                and _continues(doc,json.loads(mirror['document']))):
            continuing.append(native['id'])
    if len(set(continuing))>1:
        raise ValueError('ambiguous receiving correction; preserve variants')
    if continuing:
        target=continuing[0]
        before=record(con,target)
        memory.update_chapter(target,content=source['raw'],title=title,
            tags=json.loads(source['tags_json']),importance=source['importance'],
            source_path=PREFIX+origin,source_kind=source['book_source_kind'],
            engram_type=source.get('engram_type'),event_ts=source.get('event_ts'),actor=source.get('actor'),
            location=json.loads(source['location_json']) if source.get('location_json') else None,
            metadata=metadata,summary=source['spr'],expected_revision=before['revision'],_con=con)
    else:
        target = memory.add_text(source['shelf_name'], title, source['raw'],
        tags=json.loads(source['tags_json']), importance=source['importance'],
        source_path=PREFIX + origin, source_kind=source['book_source_kind'], replace=False,
        engram_type=source.get('engram_type'), event_ts=source.get('event_ts'), actor=source.get('actor'),
        location=json.loads(source['location_json']) if source.get('location_json') else None,
        metadata=metadata, summary=source['spr'], _con=con)
    copied = record(con, target)
    if source.get('embed_disabled') and not copied.get('embed_disabled'):
        raise ValueError('native import would relax original embedding policy')
    # The canonical native API creates receiving identity/history. Original UID,
    # full fields and revisions stay immutable in the attributed origin ledger.
    con.execute('INSERT INTO dmk_sync_origins VALUES(?,?,?)', (origin, doc['logical_key'], wire(doc).decode()))
    con.execute('INSERT INTO dmk_sync_bindings VALUES(?,?,?,0)', (origin, copied['record_uid'], digest(copied)))
    return target, True


def _edges(memory, con):
    for saved in con.execute("SELECT edge_hash,document,state FROM dmk_sync_edges WHERE state IN ('pending','waiting_for_endpoint')").fetchall():
        edge = json.loads(saved['document'])
        if edge['source_origin'] is None or edge['target_origin'] is None:
            state = 'signed_or_missing_endpoint_retained'
        else:
            try:
                source,target=(_bound_record(con,edge[k]) for k in ('source_origin','target_origin'))
            except ValueError:
                state='conflicting_endpoint_preserved'
            else:
                if source is None or target is None:
                    state='waiting_for_endpoint'
                else:
                    row=edge['original']
                    existing=con.execute('SELECT weight,note FROM chapter_links WHERE src_chapter_id=? '
                        'AND dst_chapter_id=? AND link_type=?',(source,target,row['link_type'])).fetchone()
                    if existing and (existing['weight'],existing['note'])!=(row['weight'],row['note']):
                        state='conflicting_edge_preserved'
                    else:
                        if not existing:
                            memory.add_link(source,target,row['link_type'],weight=row['weight'],note=row['note'],_con=con)
                        state='applied'
        con.execute('UPDATE dmk_sync_edges SET state=? WHERE edge_hash=?',(state,saved['edge_hash']))


def _link_states(con, packet, *, verify=False):
    counts=dict(applied=0,pending=0,preserved_conflicts=0)
    for edge in packet['links']:
        saved=con.execute('SELECT state FROM dmk_sync_edges WHERE edge_hash=?',(digest(edge),)).fetchone()
        if saved is None:
            raise ValueError('native edge receipt unavailable')
        state=saved['state']
        if state=='applied':
            if verify:
                source,target=(_bound_record(con,edge[k]) for k in ('source_origin','target_origin'))
                row=edge['original']
                observed=con.execute('SELECT weight,note FROM chapter_links WHERE src_chapter_id=? '
                    'AND dst_chapter_id=? AND link_type=?',(source,target,row['link_type'])).fetchone()
                if observed is None or (observed['weight'],observed['note'])!=(row['weight'],row['note']):
                    raise ValueError('native edge effect changed; preserve local relationship')
            counts['applied']+=1
        elif state in ('conflicting_endpoint_preserved','conflicting_edge_preserved'):
            counts['preserved_conflicts']+=1
        else:
            counts['pending']+=1
    return counts


def apply(memory, packet, owner, *, operation_id, after_effect=None):
    """Atomic additive write plus receipt; a lost response retries without a duplicate.

    The target must already use a compatible initialized native API. SQLite fences
    only the actual memory resource, not harness/Matrix processes. Unrelated target
    additions and recall/access counters do not invalidate an unchanged selection.
    """
    owner = _validate_packet(packet, owner)
    path=database(memory.DB_PATH)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as preflight:
        columns={r[1] for r in preflight.execute('PRAGMA table_info(chapters)')}
        if not {'record_uid','source_metadata_json','revision'} <= columns:
            raise ValueError('receiving native schema needs supported upgrade first')
    for method in (memory.add_text, memory.add_link, memory.update_chapter):
        if '_con' not in inspect.signature(method).parameters:
            raise ValueError('receiving native API lacks transactional composition')
    if not isinstance(operation_id,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',operation_id):
        raise ValueError('stable receiving operation identifier required')
    packet_hash, owner_hash = digest(packet), digest(owner)
    with closing(memory.connect()) as con:
        con.execute('BEGIN IMMEDIATE')
        try:
            columns = {r[1] for r in con.execute('PRAGMA table_info(chapters)')}
            if not {'record_uid','source_metadata_json','revision'} <= columns:
                raise ValueError('receiving native schema needs supported upgrade first')
            _schema(con, owner)
            previous = con.execute('SELECT * FROM dmk_sync_operations WHERE operation_id=?', (operation_id,)).fetchone()
            if previous:
                if previous['packet_hash'] != packet_hash or previous['binding_hash'] != owner_hash:
                    raise ValueError('retained operation selection changed')
                result = json.loads(previous['result'])
                for entry in packet['records']:
                    _bound_record(con,entry['origin_hash'])
                current_links=_link_states(con,packet,verify=True)
                con.rollback()
                return dict(result,reused=True,current_links=current_links)
            result = dict(schema='dmk.same-being-native-result/v1',operation_id=operation_id,
                packet_hash=packet_hash, imported=0,reused_origins=0,entries=[],
                source_authority='unsigned-native',models_started=0)
            for entry in packet['records']:
                target, added = _import(memory,con,entry,owner)
                result['imported' if added else 'reused_origins'] += 1
                variants = con.execute('SELECT count(*) FROM dmk_sync_origins WHERE logical_key=?',
                                      (entry['document']['logical_key'],)).fetchone()[0]
                result['entries'].append(dict(origin_hash=entry['origin_hash'],target_chapter_id=target,
                                              preserved_variants=variants))
                if after_effect:
                    after_effect(entry['origin_hash'])
            for edge in packet['links']:
                key = digest(edge)
                con.execute('INSERT OR IGNORE INTO dmk_sync_edges VALUES(?,?,?)', (key,wire(edge).decode(),'pending'))
            _edges(memory,con)
            result['links'] = _link_states(con,packet,verify=True)
            result['current_links']=result['links']
            result['reused'] = False
            con.execute('INSERT INTO dmk_sync_operations VALUES(?,?,?,?)',
                        (operation_id,packet_hash,owner_hash,wire(result).decode()))
            con.commit()
            return result
        except BaseException:
            con.rollback()
            raise


def source_history(con, chapter_id):
    """Original source versions through the ordinary native history reader.

    Original source UID/revision remain attributed, never renumbered as receiving
    native edits or represented as signed Matrix events.
    """
    if not table(con,'dmk_sync_bindings') or protected(con,chapter_id):
        return []
    rows=con.execute('SELECT o.origin_hash,o.document,b.original_native,b.applied_hash FROM chapters c '
        'JOIN dmk_sync_bindings b ON b.target_uid=c.record_uid '
        'JOIN dmk_sync_origins o ON o.origin_hash=b.origin_hash WHERE c.id=?', (chapter_id,)).fetchall()
    if not rows or all(r['original_native'] for r in rows):
        return []
    current=digest(record(con,chapter_id))
    exact=[r for r in rows if r['applied_hash']==current]
    if len(exact)>1:
        raise ValueError('ambiguous native origin history')
    # Local later edits retain source originals too; they cannot choose a
    # source version by timestamp. All retained origins remain attributed.
    if not exact:
        versions=[]
        for row in rows:
            doc=json.loads(row['document']);versions.append(dict(doc['record'],
                revision_reason='retained-source-variant',same_being_native_origin=dict(
                    origin_hash=row['origin_hash'],source_binding=doc['source_binding'],authority=doc['provenance'])))
        return versions
    row=exact[0]
    doc=json.loads(row['document'])
    attribution=dict(origin_hash=row['origin_hash'],source_binding=doc['source_binding'],
                     authority=doc['provenance'])
    versions=[dict(json.loads(v['snapshot_json']),revision_reason=v['reason'],
                   archived_at=v['archived_at'],same_being_native_origin=attribution)
              for v in doc['history']]
    versions.append(dict(doc['record'],revision_reason='source-current-at-import',
                         same_being_native_origin=attribution))
    return versions


def status(memory, *, operation_id, packet=None, owner=None):
    """Read-only reconciliation of a retained receipt, never a recovery dispatch."""
    path=database(memory.DB_PATH)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row
        con.execute('BEGIN')
        if not table(con,'dmk_sync_operations'):
            return None
        saved=con.execute('SELECT * FROM dmk_sync_operations WHERE operation_id=?', (operation_id,)).fetchone()
        if saved is None:
            return None
        if packet is not None:
            _validate_packet(packet,owner)
            if saved['packet_hash']!=digest(packet) or saved['binding_hash']!=digest(binding(owner)):
                raise ValueError('retained operation selection changed')
        result=json.loads(saved['result'])
        for entry in result['entries']:
            _bound_record(con,entry['origin_hash'])
        current_links=_link_states(con,packet,verify=True) if packet is not None else None
        return dict(result,reused=True,current_links=current_links)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    exporting=commands.add_parser('export')
    exporting.add_argument('--database',type=Path,required=True)
    exporting.add_argument('--binding',type=Path,required=True)
    exporting.add_argument('--after',type=int,default=0)
    exporting.add_argument('--limit',type=int,default=64)
    exporting.add_argument('--known',type=Path)
    exporting.add_argument('--output',type=Path,required=True)
    for name in ('apply','status'):
        command=commands.add_parser(name)
        command.add_argument('--binding',type=Path,required=True)
        command.add_argument('--packet',type=Path,required=True)
        command.add_argument('--packet-sha256',required=True)
        command.add_argument('--operation',required=True)
        if name=='apply':
            command.add_argument('--backup-config',type=Path,required=True)
            command.add_argument('--checkpoint-operation',required=True)
    args=parser.parse_args()
    os.umask(0o077)
    try:
        owner=binding(json.loads(args.binding.read_text()))
        if args.command=='export':
            known=json.loads(args.known.read_text()) if args.known else []
            packet=export(args.database,owner,after=args.after,limit=args.limit,known=known)
            fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:
                stream.write(wire(packet)+b'\n');stream.flush();os.fsync(stream.fileno())
            print(json.dumps(dict(schema=SCHEMA,packet_hash=digest(packet),records=len(packet['records']),
                                  cursor=packet['cursor'],more=packet['more'],models_started=0)))
            return 0
        import memoryctl as memory
        raw=args.packet.read_bytes()
        if len(raw)>MAX_BYTES:
            raise ValueError('bounded native packet required')
        packet=json.loads(raw)
        if digest(packet)!=args.packet_sha256:
            raise ValueError('native packet hash mismatch')
        _validate_packet(packet,owner)
        existing=status(memory,operation_id=args.operation,packet=packet,owner=owner)
        if args.command=='status' or existing is not None:
            print(json.dumps(existing or dict(state='not-observed',models_started=0)))
            return 0
        import backupctl
        backup=json.loads(args.backup_config.read_text())
        if Path(backup['database']).resolve()!=Path(memory.DB_PATH).resolve():
            raise ValueError('checkpoint destination differs from receiving memory')
        backupctl.operate(backup,'begin',operation=args.checkpoint_operation,
                          reason='Before selected same-being integration '+args.checkpoint_operation)
        result=apply(memory,packet,owner,operation_id=args.operation)
        print(json.dumps(result))
        # The parent integration owns completion of its one shared checkpoint.
        # Do not create/complete a full DB snapshot separately for each page.
        return 0
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error):
        print(json.dumps(dict(error='same_being_native_operation_unconfirmed',
                              preserve_packet_and_checkpoint=True)))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
