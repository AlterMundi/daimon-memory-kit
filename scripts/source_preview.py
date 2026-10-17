"""Quoted navigation excerpts; never a summary, replacement or support verdict."""
import re

from assertion_review import complete_source_envelopes, source_blocks


def excerpt(raw, query, *, limit=500):
    """Expose readable dialogue from exact envelopes without changing canon.

    A single contiguous quote keeps attribution and offsets. Tool payloads and
    unknown formats stay available through ordinary full reads; this helper does
    not interpret them or promote assistant claims into observed outcomes.
    """
    if not complete_source_envelopes(raw):
        return None
    tokens = set(re.findall(r'\w{3,}', query.casefold()))
    candidates = []
    for block in source_blocks(raw):
        if block.get('channel') not in {
            'Human report', 'Human conversation', 'assistant_statement',
            'Attributed peer communication', 'attributed_agent_message',
        }:
            continue
        text = block['quotation']
        if text.strip().startswith('<environment_context>'):
            continue
        matches = [m for m in re.finditer(r'\w{3,}', text)
                   if m.group().casefold() in tokens]
        score = len({m.group().casefold() for m in matches})
        candidates.append((score, block, matches))
    if not candidates:
        return None
    # Stable source order resolves ties; do not infer truth from recency.
    _, block, matches = max(candidates, key=lambda item: item[0])
    text = block['quotation']
    start = max(0, matches[0].start() - 100) if matches else 0
    start = min(start, max(0, len(text) - limit))
    end = min(len(text), start + limit)
    return dict(header=block['header'], quote=text[start:end],
                quotation_offset=start, omitted_before=start > 0,
                omitted_after=end < len(text), navigation_only=True,
                detail='One quoted source fragment; read the complete record, including outcomes and corrections.')
