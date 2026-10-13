"""Source-scoped navigation through HMK's existing lexical/hybrid retrieval.

Search is bounded evidence navigation, not an inventory or proof of absence.
Callers read originals before using a hit as factual support. No corpus mutation.
"""
from __future__ import annotations

import json
import time


def search(memory, query, *, mode='hybrid', record_uids=None, limit=12):
    if mode not in {'lexical', 'hybrid'}:
        raise ValueError('retrieval mode must be lexical or hybrid')
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError('a focused query of at most 2000 characters is required')
    if type(limit) is not int or not 1 <= limit <= 64:
        raise ValueError('navigation limit must be 1..64')
    started = time.monotonic()
    errors, details = [], {}
    if mode == 'hybrid':
        try:
            memory.embeddings_runtime_config()
        except ValueError:
            # Only configuration errors warrant this fallback, not arbitrary
            # ValueErrors raised by ranking or database adapters.
            rows = memory.search(query, limit=limit, record_uids=record_uids)
            errors = ['embedding_configuration_unavailable']
            status = 'degraded' if rows else 'unavailable'
        else:
            pack = memory.hybrid_candidates(query, limit=limit, record_uids=record_uids)
            rows = pack['items'][:limit]
            errors = pack.get('backend_errors', [])
            status = pack['retrieval_status']
            details = {k:pack[k] for k in ('provider','model','score_space','reason','used_tokens_estimate') if k in pack}
    else:
        rows = memory.search(query, limit=limit, record_uids=record_uids)
        status = 'ok'
    history = memory.history_search(query, limit=min(limit,4), record_uids=record_uids)
    def nav(row):
        result = {k:row[k] for k in ('id','record_uid','revision','title','engram_type','support_status','score') if k in row}
        # Pack summaries intentionally omit most source metadata. Read only the
        # selected hit's applicability, never the entire pool's metadata.
        con = memory.connect()
        try:
            source = con.execute('SELECT source_metadata_json,revision FROM chapters WHERE record_uid=?',
                                 (row['record_uid'],)).fetchone()
        finally:
            con.close()
        result['relevance'] = 'unassessed; read current evidence before use'
        result['applicability'] = json.loads(source[0] or '{}').get('applicability',
            {'kind':'unknown','targets':[]}) if source else {'kind':'unknown','targets':[]}
        if row.get('historical'):
            result['historical'] = True
            result['current_revision'] = source[1] if source else None
        return result
    return dict(query=query, mode=mode, retrieval_status=status, backend_errors=errors,
                items=[nav(row) for row in rows], historical_matches=[nav(row) for row in history],
                navigation_only=True, coverage='ranked candidates; not an exhaustive absence check',
                seconds=round(time.monotonic()-started,6), **details)
