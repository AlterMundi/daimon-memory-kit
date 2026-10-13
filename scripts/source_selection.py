"""Source-block selection reused from the qualified durable-recall pilot."""
import json

READING_GUIDANCE = (
    "Retained source blocks preserve speakers and evidence modes. A Human report "
    "is something the human told the being, not proof of the receiving body's "
    "attendance or independent observation. Preserve that attribution in your "
    "narration; an ambiguous 'we' does not establish its membership. Distinguish "
    "tool outcomes from assistant claims and another being's experience from "
    "this being's own. Recording timestamps are not occurrence dates. Keep the "
    "precision of each event's stated date: do not fill an omitted year or other "
    "component from a nearby event. Label an inference as such or leave it "
    "unknown. Cite the "
    "retained record supporting historical assertions, while explaining their "
    "meaning in your own words. Present capabilities come from the current "
    "receiving binding and tools, not historical memory."
)


def source_decision(value, sources, canon):
    """Select source blocks; never let generated prose become factual raw text.

    This pilot adapter preserves the native writer's closed decision schema.
    Original blocks remain quoted with their channel/receiver, including their
    qualifications. Existing memory blocks carry stable ID/revision provenance.
    """
    if not isinstance(value, dict) or not isinstance(value.get('records'), list):
        raise ValueError('source selection needs a records array')
    available = {s['id']: s for s in sources}
    available.update({'memory:'+str(r['id']): r for r in canon})
    # Stable UIDs and legacy local integer handles address the same completely
    # supplied original. Never resolve a guessed/external UID against the DB.
    available.update({'memory:'+r['record_uid']: r for r in canon if r.get('record_uid')})
    decision = json.loads(json.dumps(value))
    for record in decision['records']:
        refs = record.pop('source_ids', None)
        if not isinstance(refs, list) or not refs or any(
                not isinstance(ref, str) or ref not in available for ref in refs):
            raise ValueError('each record needs source_ids from supplied sources or memory:<supplied ID or UID>')
        if 'raw' in record or 'summary' in record:
            raise ValueError('source selection uses source_ids, not generated raw or summary')
        blocks = []
        for ref in dict.fromkeys(refs):
            source = available[ref]
            if ref.startswith('memory:'):
                text = source['raw']
                label = f"Previously retained memory {source['id']}, revision {source['revision']}"
            else:
                text = source['content']
                channel = source.get('channel', 'reported source')
                role = ('Human report' if channel == 'human_message' else
                        'Human conversation' if channel == 'human_conversation' else
                        'Attributed peer communication' if channel == 'authorized_peer_message' else channel)
                label = (f"{role}; source {ref}; received {source.get('received_at', 'unknown')} "
                         f"through {source['originating_body']}")
            blocks.append(label + ':\n' + json.dumps(text, ensure_ascii=False))
        title = record.get('title')
        if not isinstance(title, str) or not title.strip() or not any(
                title in (available[ref].get('content') or available[ref].get('raw', '')) for ref in refs):
            raise ValueError('title must be an exact recognition phrase in a selected source block')
        record['raw'] = '\n\n'.join(blocks)
        record['metadata'] = {'mode':'reported'}
    return decision
