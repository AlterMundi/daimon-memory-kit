"""Deterministic source windows with complete causal context and durable frontiers.

The inbox keeps full source bytes. A window limits model input, never corpus size
or retained history. Its frontier is committed only with the selection receipt.
"""
from copy import deepcopy

from capturectl import wire


def select(groups, progress, budget_bytes):
    """Return a prefix of new blocks plus transitive dependencies.

    Previously processed blocks are context only, even if needed by a later tool
    result. An indivisible dependency closure can request a larger caller budget;
    it is never truncated, skipped or acknowledged to get under the budget.
    """
    if type(budget_bytes) is not int or budget_bytes < 1:
        raise ValueError('positive source window byte budget required')
    if set(progress) - set(groups):
        raise ValueError('source progress refers to a different frozen group')
    positions, available = {}, {}
    for source, blocks in groups.items():
        start = progress.get(source, 0)
        if type(start) is not int or not 0 <= start <= len(blocks):
            raise ValueError('source frontier is outside its frozen group')
        for i, block in enumerate(blocks):
            if block['id'] in available:
                raise ValueError('duplicate source identity')
            available[block['id']] = block
            positions[block['id']] = (source, i)
    selected, frontier = {}, dict(progress)
    required_bytes = None
    used = 2  # JSON array brackets; each additional element needs a comma.
    stop = False
    for source, blocks in groups.items():
        for i in range(progress.get(source, 0), len(blocks)):
            block = blocks[i]
            if block['status'] != 'new':
                frontier[source] = i + 1
                continue
            pending, extra = [block['id']], {}
            while pending:
                ref = pending.pop()
                if ref in selected or ref in extra:
                    continue
                if ref not in available:
                    raise ValueError('missing source dependency')
                item = deepcopy(available[ref])
                owner, position = positions[ref]
                if position < progress.get(owner, 0):
                    item['status'] = 'earlier_context'
                extra[ref] = item
                pending.extend(item.get('dependencies', []))
            cost = sum(len(wire(s).encode()) + 1 for s in extra.values())
            total = used + cost - (1 if not selected and extra else 0)
            if total > budget_bytes:
                required_bytes = total if not selected else None
                stop = True
                break
            selected.update(extra)
            used = total
            frontier[source] = i + 1
        if stop:
            break
        frontier[source] = len(blocks)
    ordered = [selected[b['id']] for blocks in groups.values() for b in blocks if b['id'] in selected]
    return dict(sources=ordered,progress=frontier,
                complete=all(frontier.get(s,0)==len(v) for s,v in groups.items()),
                used_bytes=len(wire(ordered).encode()),minimum_required_bytes=required_bytes)


class ContextReader:
    """Navigate backwards within the frozen authorized sources, never live files."""
    def __init__(self, groups, budget_bytes):
        self.groups = groups
        self.budget_bytes = budget_bytes
        self.positions = {b['id']:(source,i) for source,blocks in groups.items()
                          for i,b in enumerate(blocks)}

    def order(self, blocks):
        known = {b['id'] for b in blocks}
        return [b['id'] for rows in self.groups.values() for b in rows if b['id'] in known]

    def before(self, anchor, known):
        if anchor not in known or anchor not in self.positions:
            return dict(status='unknown_source_anchor')
        source, position = self.positions[anchor]
        if position == 0:
            return dict(status='beginning_of_source',anchor=anchor)
        # Treat prior text solely as context. The selection writer still requires
        # a genuinely new block from the frozen processing window for admission.
        blocks = deepcopy(self.groups[source])
        for b in blocks:
            b['status'] = 'earlier_context'
        blocks[position-1]['status'] = 'new'
        result = select({source:blocks[:position]}, {source:position-1}, self.budget_bytes)
        if result['minimum_required_bytes'] is not None:
            return dict(status='source_context_budget_exceeded',anchor=anchor,
                        minimum_required_bytes=result['minimum_required_bytes'])
        for b in result['sources']:
            b['status'] = 'earlier_context'
        return dict(status='ok',anchor=anchor,previous_id=blocks[position-1]['id'],
                    sources=result['sources'],complete=True)
