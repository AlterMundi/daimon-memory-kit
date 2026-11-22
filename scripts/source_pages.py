"""Exact, deterministic UTF-8 views of oversized normalized capture items."""
from capture_inbox import sha
from capturectl import wire

SCHEMA = 'dmk.source-pages/v1'
GUIDANCE = """
A block with source_range is an exact excerpt, not the complete source item.
Offsets count UTF-8 bytes in the normalized text of that item. Pages share one
original identity and do not establish separate occurrences. Earlier pages of a
dependency are available via source_before on its supplied page. If the visible
evidence does not support a decision, read the needed pages or defer. Do not infer
what unseen ranges say. For selected evidence with a paged causal dependency,
cite the supporting dependency excerpts alongside the new evidence.
"""


def expand(groups, revisions, page_bytes):
    """Return paged blocks, and translate each original frontier by prefix length."""
    if type(page_bytes) is not int or not 4096 <= page_bytes <= 32768:
        raise ValueError('source pages require a byte target between 4096 and 32768')
    paged = {}
    boundaries = {}
    terminal = {}
    context_only = set()
    for source, blocks in groups.items():
        rows = []
        boundaries[source] = [0]
        for block in blocks:
            if block['id'] in terminal:
                raise ValueError('duplicate source identity')
            if block.get('retrieved_context') or block.get('instruction_context'):
                context_only.add(block['id'])
            pieces = spans(block, revisions[source], page_bytes)
            rows.extend(pieces)
            terminal[block['id']] = pieces[-1]['id']
            boundaries[source].append(len(rows))
        paged[source] = rows
    for rows in paged.values():
        for i, block in enumerate(rows):
            original = block.get('dependencies', [])
            if original:
                dependencies = [terminal[ref] for ref in original]
                changed = {ref: last for ref, last in zip(original, dependencies)
                           if ref != last and ref not in context_only}
                rows[i] = {**block, 'dependencies': dependencies}
                if changed:
                    rows[i]['paged_dependencies'] = changed
    return paged, boundaries


def spans(block, revision, page_bytes):
    if len(wire(block).encode()) <= page_bytes:
        return [block]
    text = block['content']
    raw = text.encode('utf-8')
    original_hash = sha(raw)
    size = len(raw)
    pieces = []
    offset = 0
    pos = 0
    while pos < len(text):
        # Probe only a bounded substring. Each character costs at least
        # one byte on the wire, and JSON escaping can make it longer.
        low, high = pos + 1, min(pos + page_bytes, len(text))
        best = None
        while low <= high:
            mid = (low + high) // 2
            excerpt = text[pos:mid]
            data = excerpt.encode('utf-8')
            end = offset + len(data)
            page = {
                **block, 'id': f"{block['id']}:utf8:{offset}-{end}", 'content': excerpt,
                'source_range': dict(original_id=block['id'], capture_revision=revision['revision'],
                                     capture_sha256=revision['sha256'], start_byte=offset,
                                     end_byte=end, total_bytes=size, content_sha256=original_hash,
                                     range_sha256=sha(data)),
            }
            if len(wire(page).encode()) <= page_bytes:
                best = (mid, end, page)
                low = mid + 1
            else:
                high = mid - 1
        if best is None:
            raise ValueError('source page metadata exceeds selected budget')
        pos, offset, page = best
        pieces.append(page)
    if not pieces:
        raise ValueError('empty oversized source block cannot be paged')
    return pieces


def validate_citations(value, sources):
    """A selected dependent excerpt must carry an actually supplied causal excerpt."""
    known = {block['id']: block for block in sources}
    for record in value.get('records', []):
        chosen = [known[ref] for ref in record['source_ids'] if ref in known]
        cited = {block.get('source_range', {}).get('original_id', block['id']) for block in chosen}
        for block in chosen:
            if set(block.get('paged_dependencies', {})) - cited:
                raise ValueError('selected evidence requires a supplied citation from each paged causal original')
