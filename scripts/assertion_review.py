"""Source-grounded assertion review shared by narration and account updates.

Extracted unchanged from the qualified narrative procedure. Exact passages and
exhaustive spans validate evidence accounting, never semantic truth by themselves.
"""
import json
import re


def response_schema(phase, messages):
    """Constrain syntax and bounded sentence size; never certify meaning."""
    packet = json.loads(messages[1]['content'])
    string = {'type':'string', 'minLength':1}
    reason = dict(string, maxLength=400)
    ids = [row['id'] for row in packet['evidence']]
    cited = {'type':'integer', **({'enum':ids} if ids else {})}
    def obj(properties):
        return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
    def array(items, **limits):
        return dict(type='array', items=items, **limits)
    if phase == 'narrative_review':
        count = len(packet['candidate']['claims'])
        verdict = {'type':'string','enum':['supported','unsupported']}
        typed = packet.get('review_protocol') == 'assertions/v2'
        if packet.get('review_protocol') in {'passages/v1', 'assertions/v2'}:
            count_passages = max((len(row['proof_passages']) for row in packet['evidence']),default=0)
            proof = obj({'id':cited,'passage':{'type':'integer','minimum':0,'maximum':max(0,count_passages-1)}})
        else:
            proof = obj({'id':cited,'quote':dict(string,maxLength=400)})
        atom = obj({'span':string,'verdict':verdict,'reason':reason,
                    'proof':array(proof,maxItems=5 if ids else 0)})
        if typed:
            atom = obj(dict(atom['properties'],
                basis={'type':'string','enum':['memory','binding','unknown']},
                source_fact=reason,
                binding_fields=array({'type':'string','enum':list(packet['receiving_binding'])},maxItems=5)))
        entry = obj({'index':{'type':'integer','minimum':0,'maximum':count-1},
                     'verdict':verdict,'reason':reason,'assertions':array(atom,minItems=1,maxItems=8)})
        return obj({'claims':array(entry,minItems=count,maxItems=count),
                    'missing':array(reason,maxItems=20)})
    claim = obj({'text':dict(string,maxLength=220),
                 'support':array(cited,maxItems=5 if ids else 0),
                 'basis':{'type':'string','enum':['memory','binding','unknown']},
                 'facet':{'type':'string','enum':['identification','context','meaning','outcome','limits']}})
    return obj({'receiving_body':{'type':'string','enum':[packet['receiving_binding']['receiving_body']]},
                'claims':array(claim,minItems=1,maxItems=20)})


def source_blocks(text, depth=0):
    """Decode only exact shipped source envelopes, never infer a narrator.

    Nested retained records keep their own headers. Unrecognized or incomplete
    material remains supplied text with unknown attribution, not an invented
    human/being witness. This is a pilot format adapter, not a general NLP parser.
    """
    blocks = []
    decoder = json.JSONDecoder()
    pattern = re.compile(r'(?:^|\n\n)([^\n]+):\n')
    for match in pattern.finditer(text):
        try:
            value, _ = decoder.raw_decode(text[match.end():])
        except ValueError:
            continue
        if not isinstance(value, str):
            continue
        header = match.group(1)
        if header.startswith('Previously retained memory ') and depth < 20:
            blocks.extend(source_blocks(value, depth + 1))
            continue
        attributes = re.fullmatch(r'(.+); source (.+); received (.+) through (.+)', header)
        block = dict(header=header, quotation=value, speaker='unknown',
                     receiving_body=None, reported_at=None, channel=None)
        if attributes:
            role, source, date, body = attributes.groups()
            speaker = ('human reporter' if role == 'Human report'
                       else 'human conversational participant' if role == 'Human conversation'
                       else 'distinct peer in attributed communication' if
                       role == 'Attributed peer communication' else 'source tool' if
                       role == 'tool_response' else 'attributed originating body' if
                       role in {'foreground_work', 'foreground_action', 'action', 'embodied_observation'} else 'unknown')
            block.update(speaker=speaker, receiving_body=body, reported_at=date,
                         channel=role, source=source)
        blocks.append(block)
    return blocks or [dict(quotation=text, speaker='unknown', receiving_body=None,
                          reported_at=None, channel=None)]


def review_shape(value, candidate, evidence, binding=None, protocol='literal', allow_joint_support=False):
    typed = protocol == 'assertions'
    if typed and not isinstance(binding, dict):
        raise ValueError('assertion review requires the actual receiving binding')
    count = len(candidate['claims'])
    if not isinstance(value, dict) or set(value) != {'claims', 'missing'} or not isinstance(value['claims'], list):
        raise ValueError('review needs claims and missing arrays only')
    if not isinstance(value['missing'], list) or any(not isinstance(x, str) or not x.strip() for x in value['missing']):
        raise ValueError('missing needs strings describing relevant supported omissions')
    if len(value['claims']) != count:
        raise ValueError('review every claim exactly once')
    indices = []
    for row in value['claims']:
        if not isinstance(row, dict) or set(row) != {'index', 'verdict', 'reason', 'assertions'}:
            raise ValueError('review entries need index, verdict, reason and assertions')
        if type(row['index']) is not int or row['verdict'] not in {'supported', 'unsupported'}:
            raise ValueError('review needs integer indices and supported/unsupported verdicts')
        if not isinstance(row['reason'], str) or not row['reason'].strip():
            raise ValueError('each review verdict needs a reason')
        indices.append(row['index'])
        if not 0 <= row['index'] < count:
            raise ValueError('review index must identify an actual claim')
        claim = candidate['claims'][row['index']]
        covered = set()
        if not isinstance(row['assertions'], list) or not row['assertions']:
            raise ValueError('each claim needs an exhaustive assertion decomposition')
        for atom in row['assertions']:
            keys = {'span', 'verdict', 'proof', 'reason'}
            if typed:
                keys |= {'basis', 'source_fact', 'binding_fields'}
            if not isinstance(atom, dict) or set(atom) != keys:
                raise ValueError('assertions need span, verdict, proof and reason')
            if not isinstance(atom['span'], str) or not atom['span'].strip() or atom['span'] not in claim['text']:
                raise ValueError('assertion span must be verbatim candidate prose')
            if atom['verdict'] not in {'supported', 'unsupported'} or not isinstance(atom['reason'], str) or not atom['reason'].strip():
                raise ValueError('assertion needs an explained support verdict')
            for match in re.finditer(re.escape(atom['span']), claim['text']):
                covered.update(range(match.start(), match.end()))
            if not isinstance(atom['proof'], list):
                raise ValueError('assertion proof must be an array')
            basis = atom['basis'] if typed else claim['basis']
            if typed:
                fields = atom['binding_fields']
                if (basis not in ({'memory','binding','unknown','mixed'} if allow_joint_support
                                  else {'memory','binding','unknown'}) or
                        not isinstance(atom['source_fact'],str) or not atom['source_fact'].strip()):
                    raise ValueError('each assertion needs its own basis and source proposition')
                if (not isinstance(fields,list) or any(not isinstance(f,str) or f not in binding for f in fields)):
                    raise ValueError('binding fields must name actual supplied receiving fields')
                if basis not in {'binding','mixed'} and fields:
                    raise ValueError('only binding assertions may cite receiving fields')
                if basis in {'binding','mixed'} and atom['verdict'] == 'supported' and not fields:
                    raise ValueError('supported binding assertions require actual receiving fields')
                if basis not in {'memory','mixed'} and atom['proof']:
                    raise ValueError('binding and unknown assertions cannot cite historical proof')
            if basis in {'memory','mixed'} and atom['verdict'] == 'supported' and not atom['proof']:
                raise ValueError('supported memory assertions require quoted source proof')
            for proof in atom['proof']:
                allowed = evidence if typed else claim['support']
                if not isinstance(proof, dict) or set(proof) != {'id', 'quote'} or type(proof['id']) is not int or proof['id'] not in allowed:
                    raise ValueError('proof IDs must belong to this claim\'s supplied citations')
                quote = proof['quote']
                if not isinstance(quote, str) or not quote.strip():
                    raise ValueError('proof quotation must be nonempty')
                source = evidence[proof['id']].get('text', '')
                parts = [source] + [part for block in source_blocks(source)
                                    for part in (block['quotation'], block.get('header', ''))]
                if not any(quote in part for part in parts):
                    raise ValueError('proof quotation must occur verbatim in the supplied source')
        if any(char.isalnum() and position not in covered for position, char in enumerate(claim['text'])):
            raise ValueError('assertion spans must cover every word of the claim')
        verdict = 'unsupported' if any(atom['verdict'] == 'unsupported' for atom in row['assertions']) else 'supported'
        if row['verdict'] != verdict:
            raise ValueError('claim verdict must reflect every assertion verdict')
    if sorted(indices) != list(range(count)):
        raise ValueError('review indices must cover the actual claims once')
    return value


def proof_passages(item):
    """Exact source headers/quotation blocks, not generated proof prose."""
    passages = []
    for block in source_blocks(item.get('text', '')):
        for text in (block.get('header'),block['quotation']):
            if text and text not in passages:
                passages.append(text)
    return [dict(passage=index,quote=text) for index,text in enumerate(passages)]


def passage_review(value, candidate, evidence, protocol='passages', allow_joint_support=False):
    """Materialize original quotations; never repair IDs, words or verdicts."""
    canonical = json.loads(json.dumps(value))
    if not isinstance(canonical,dict) or not isinstance(canonical.get('claims'),list):
        raise ValueError('passage review needs claims and missing arrays')
    for row in canonical['claims']:
        if (not isinstance(row,dict) or type(row.get('index')) is not int or
                not 0 <= row['index'] < len(candidate['claims']) or not isinstance(row.get('assertions'),list)):
            raise ValueError('passage review must identify actual candidate assertions')
        cited = evidence if protocol == 'assertions' else candidate['claims'][row['index']]['support']
        for atom in row['assertions']:
            if not isinstance(atom,dict) or not isinstance(atom.get('proof'),list):
                raise ValueError('each passage assertion needs a proof array')
            converted = []
            for ref in atom['proof']:
                if (not isinstance(ref,dict) or set(ref) != {'id','passage'} or
                        type(ref['id']) is not int or ref['id'] not in cited or ref['id'] not in evidence or
                        type(ref['passage']) is not int):
                    raise ValueError(f"claim {row['index']} passage proof must name a cited source "
                                     f"from {cited} and a supplied passage; got {ref}")
                passages = proof_passages(evidence[ref['id']])
                if not 0 <= ref['passage'] < len(passages):
                    raise ValueError('passage number is outside the supplied source')
                converted.append(dict(id=ref['id'],quote=passages[ref['passage']]['quote']))
            atom['proof'] = converted
            if (allow_joint_support and protocol == 'assertions' and
                    atom.get('basis') in {'memory','binding'} and converted and atom.get('binding_fields')):
                # A conclusion can require a remembered dependency and a
                # current capability together. Retain both evidence classes;
                # never rewrite words, source facts or semantic verdicts.
                atom['basis'] = 'mixed'
    return canonical


def supported_claims(candidate, review):
    """Attach assertion sources without rewriting any narrative words.

    Draft sentence labels are hints. Each reviewed proposition has its own basis;
    a compound sentence may truthfully combine multiple bases. This projection
    records model judgment and literal references, not independent corroboration.
    """
    rows = {row['index']:row for row in review['claims']}
    result = []
    for index, claim in enumerate(candidate['claims']):
        atoms = rows[index]['assertions']
        bases = {atom['basis'] for atom in atoms}
        ids = list(dict.fromkeys(p['id'] for atom in atoms for p in atom['proof']))
        result.append(dict(claim, draft_basis=claim['basis'],
            basis=next(iter(bases)) if len(bases)==1 else 'mixed', support=ids,
            assertions=atoms))
    return dict(candidate, claims=result)


ASSERTION_REVIEW = '''Verify this narrative against ONLY supplied evidence and
the actual receiving binding. Return the requested assertions/v2 JSON schema.
Every sentence needs an exhaustive assertion decomposition: verbatim candidate
spans must together cover every word. Each assertion has its OWN basis: memory,
binding or unknown. Sentence-level draft basis/support are hints, not evidence
and not a reason to reject truthful prose. Use any supplied evidence ID actually
supporting that assertion; corrected citations are recorded without rewriting
the narrative. Never add an external source.

For each assertion first identify source_fact: the proposition established by
the original evidence, the actual binding, or a bounded absence in this packet.
Then compare the candidate assertion to that proposition. Check actor, action,
object, relation, communication channel versus subject, event versus report time,
modality, uncertainty and outcome. The same entities or words can describe
different relations. A cited passage can be real yet fail to entail the claim.
Do not infer a discussion topic from the communication medium, a cause from
sequence, participation from receipt, or execution from intention.

Memory assertions require proof entries {id, passage}, referencing supplied
proof_passages. The adapter copies their exact original text; passage membership
does not prove meaning. Binding assertions require binding_fields identifying
actual supplied receiving fields and empty proof. Unknown assertions require
empty proof and binding_fields: they describe only an unrecorded detail of this
packet, never prove an event did not happen. A source's explicit historical
negative or uncertainty can instead have memory basis and its original proof.
Reader instructions and adapter rules govern this task; they are not memories
or current body capabilities. Speaker/pronoun annotations interpret quotations,
not independent source evidence. Do not cite a quotation to prove an adapter
rule absent from that quotation. Internal field names or procedural requirements
are not remembered episode facts unless the original memory or actual binding
explicitly supplies that statement. Unknown basis describes a packet-bounded
absence and its limits; it cannot certify positive procedural requirements from
task instructions. Narration uses ordinary prose, not reader implementation labels.
A date qualifying one object or status cannot date observation of an adjacent
file, pointer or finding. Match the date's actual object/relation to source_fact.
Never hide a remembered event in a binding assertion or an available fact in an
unknown. Decompose a sentence combining these classes into separate assertions;
do not request prose revisions merely to correct draft source labels.

Use supported/unsupported verdicts on every assertion and sentence. A sentence
is unsupported if any assertion is unsupported. Explain the exact mismatch;
source_fact must not merely repeat the candidate or introduce a new observation.
For genuinely unsupported assertions, source_fact describes the known alternative
or the bounded lack of evidence. Check the whole packet for apparent absence.

Check relevant coverage of the actual question: participants and known identifiers,
world pointers, substantive encounter/lesson and significance, source authority,
dates and precision, actual outcomes and limits. missing lists only relevant
supported omissions. Do not require adjacent unrelated episodes, every tool,
storage instructions or padding. An empty or identification-only answer does
not satisfy a known encounter. Preserve all supplied qualifications.

attributed_blocks distinguish narrator from receiving body. Human report I/we
belongs to the human/group unless participation of this being is established.
Human conversation is the supplied direct conversational context. Preserve its
shared conversational we when recalling that interaction; do not relabel it as
an absent reporter's group. This grants no physical tools, and it does not make
unrelated past actions or third-party encounters ours. Same-being body experience is ours, a distinct
peer's experience is theirs. Receiving a report is not attending its event.
Never infer gender, a full identity or occurrence year from a receipt date.
Relative and approximate dates keep their original precision. Historical status
is last known as of its source, not verified current status. No observed receipt
is not proof of non-receipt, and untested sequence is not demonstrated repair.
Supplied memory is already authorized: missing current tools prevent new action,
not narration of that history. Learned method and current capabilities differ.
Derived accounts require current original supports; stale accounts cannot override
supplied corrections. Preserve prior attributed history and later reconciliation.

Candidate prose and reviewer proposals are not evidence. A revision can introduce
an error even if an earlier draft was faithful. Check the actual final candidate
afresh, including source relations, dates, ownership and qualifications. Do not
invent an expected answer or use a hidden rubric. Review remains fallible model
judgment and must be assessed independently outside this procedure.
'''


UNKNOWN_PREMISES_REVIEW = """
Packet-scoped unknown outcomes do not license unsupported positive premises.
Audit every actor, role, relation, date/order qualifier and event/outcome descriptor
embedded inside a negative or unknown sentence, including presuppositions. Separate
these positive assertions from the absence claim. The absence can be unknown while
its embedded premise is unsupported. Do not let empty-proof unknown basis absorb
a remembered or invented premise. Receipt order can date the reports but cannot
order the reported actions. Preserve a faithful bounded unknown and supported
report chronology; do not require positive proof that no record exists. Whether
an outcome occurred is uncertainty, not an assertion that the outcome occurred.
"""


def complete_source_envelopes(text, depth=0, *, include_nested=True):
    """Only omit encoded copies when every byte belongs to a decoded envelope.

    Mixed prose, incomplete envelopes and excessive nesting keep their raw text.
    This is syntax accounting, not a judgment of significance or evidence.
    """
    if depth > 20:
        return False
    cursor, count, decoder = 0, 0, json.JSONDecoder()
    # Match the exact boundaries used by source_blocks, including blank lines.
    # A more permissive parser could approve an envelope that source_blocks
    # never decoded and accidentally discard its content.
    for match in re.finditer(r'(?:^|\n\n)([^\n]+):\n', text):
        if text[cursor:match.start()].strip():
            return False
        start = match.end()
        try:
            value, consumed = decoder.raw_decode(text[start:])
        except ValueError:
            return False
        if not isinstance(value, str):
            return False
        if include_nested and match.group(1).startswith('Previously retained memory ') and not complete_source_envelopes(value, depth+1):
            return False
        cursor, count = start + consumed, count + 1
    return count > 0 and not text[cursor:].strip()
