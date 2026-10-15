# Finite capture and consolidation

`capturectl.py` and `consolidationctl.py` are explicitly invoked building blocks.
They install no hooks, listeners, timers, automatic inbox reads or model calls.
The caller selects the authorized being binding and source scope. Attributed
labels are content, not authenticated membership or authority. Private native
conversations do not become shared memory merely through capture.

The [selection policy](../templates/skills/memory/librarian/references/durable-memory-selection.md)
decides what matters; these tools make a supplied decision durable and replayable.
An applied decision's `reason` should explain why its selected meaning remains
worth carrying after the current task ends. Operational urgency or a native
harness having saved the text is insufficient. Stage source material separately;
select lasting meaning before writing chapters. The ledger validates structure
and atomicity, so semantic selection quality must be evaluated independently.
Mechanical acceptance is separate from the [model capture/recall pilot](durable-recall-plan.md#run-a-capture-and-recall-pilot).
Verify the deployment's required recovery snapshot before using a live pool.
First ledger use on a populated pool snapshots before adding its schema.

## Source deltas

Stage a finite source event before acknowledging it as durably pending. Each
stream uses a local ordered sequence starting at one; external message/account
identifiers remain separate. Gaps block the processed cursor. To begin midway
through a source, start a new explicit stream rather than claiming earlier
unavailable events were processed.

An entirely fictional event:

```json
{
  "stream_id": "fixture:harbormesh-issue47",
  "sequence": 1,
  "event_id": "fixture:forge-comment1847",
  "source_version": "1",
  "content": "Mara Ibarra (@mara-river, Forge account 1847) proposed an offline replay queue for HarborMesh. We found it interesting because our sensor links disconnect. It remains a proposal.",
  "metadata": {
    "mode": "reported",
    "source_instance": "fixture:body",
    "source_uri": "fixture:issue47/comment1847"
  }
}
```

```bash
./scripts/dmk capturectl.py stage --file event.json
./scripts/dmk capturectl.py pending --stream fixture:harbormesh-issue47
```

Pending content is separate from selected autobiography. A later authorized
foreground invocation can resume after source/session loss. Repeated source
identity/version must have identical content. Daily triggers alone cannot protect
evidence lost earlier: staging or selection before that boundary is required.

## Selection outcomes

Supply the proposal schema to the selecting model rather than asking it to
imitate database rows:

```bash
./scripts/dmk capturectl.py decision-schema > decision-schema.json
```

This command opens no pool and installs nothing. Source modes are `observed`,
`reported`, `inferred` or `generated`; descriptive words such as “experienced”
belong in prose. Structured occurrence/report/end dates use integer Unix seconds
with explicit precision, or remain unknown and qualified in the account. Do not
send ISO strings into integer fields or copy internal `location_json` columns
as writer arguments. Schema conformity does not prove significance, truth,
source rights or a valid update; those remain separate checks.

Supply `applied`, `omitted` or `deferred`, a reason and `selection_version`
identifying the policy/model decision. A processing decision is not another
encounter. Failed writes retain retryable sources. Only contiguous applied/omitted
outcomes advance the cursor. Mechanical status need not become an episode.

Example selection:

```json
{
  "outcome": "applied",
  "reason": "Significant proposal in our own project",
  "selection_version": "fixture:durable-selection-v1",
  "records": [{
    "key": "encounter",
    "operation": "add",
    "shelf": "episodes",
    "title": "Mara's offline replay proposal in HarborMesh issue 47",
    "raw": "In HarborMesh issue 47, Mara Ibarra (@mara-river, Forge account 1847) proposed an offline replay queue. We considered it interesting because it could preserve sensor reports through disconnections. Implementation and occurrence date are unknown. This is a reported issue comment.",
    "importance": 0.8
  }]
}
```

```bash
./scripts/dmk capturectl.py assess --event-key EVENT_KEY --file selection.json
```

Updates require `chapter_id` and observed `expected_revision`. New records require
a noncolliding title; reconcile existing accounts explicitly. Optional summaries,
type/date/actor metadata and links use supported native writers. Link source/target
can name a selected record key or an existing chapter ID. Names alone never
authorize identity merges. Protected projections retain their owner contract.

Writes, links, receipt and cursor commit in one transaction. Failures roll back
the entire selection. A committed-but-lost response replays its receipt without
another encounter/revision. Terminal decisions are immutable: changed decisions
need explicit attributed correction/reflection and expected-revision writes.
Policy reruns must not invent encounters or silently change source versions.

Receipts separate lexical persistence from embedding readiness (`pending`, `ready`,
`disabled`, `configuration_unavailable`). Vector/configuration problems do not
block selection. Refresh vectors separately through the configured provider when
permitted; readiness does not prove answer quality. Applied/omitted events purge
temporary source payloads. Compact hashes/outcomes remain; snapshots have their
own retention policy.

## Capture-fragment navigation

One capture decision can select several records: for example, an attributed
collaborator account, an authorized handover attempt and a separate tool result.
The latter may not repeat the person's name. Pack/expand offer at most three
additional navigation neighbors when retained native capture records share the
same nonempty source instance, event ID, source version and selection version.
This uses retained provenance; no payload is reingested and no links or canon
are written. Explicit authored links take precedence over a duplicate target.

These neighbors are marked `same-capture-source`, with an explicit note that
they are navigation rather than independent corroboration. Similar names,
missing provenance, other versions/instances or file/signed-projection sources
do not create this group. The ordinary pack budget still includes the returned
metadata and hints. A selected attempt can therefore lead to its selected tool
result without claiming success, receipt, identity equivalence or current truth.

## Dream proposals

Select native episodes, inspect the full preview and propose accounts/learnings.
There is no minimum encounter count. Preview includes all selected text, stable
IDs, revisions, modes and dates with a fingerprint. Manage model input budgets
explicitly; there is no hidden per-source excerpt cutoff. Record count does not
establish independent corroboration. Generated summaries cannot confirm sources.

```bash
./scripts/dmk consolidationctl.py preview --ids 17 24 > dream-manifest.json
./scripts/dmk consolidationctl.py apply \
  --manifest dream-manifest.json --proposal dream-proposal.json \
  --stream fixture:dream --sequence 1 --event-id fixture:reflection1 \
  --selection-version fixture:policy-model-v1
```

Proposals use the applied-record shape above and target knowledge/procedure
shelves. They preserve episodes, mark output inferred/generated and retain
`supported-by` links and versioned evidence. They cannot overwrite episodes,
identity or signed projections. Sources are checked under the writer lock;
changed/deleted inputs reject the whole proposal. Account updates also require
their own expected revision.

If a support later changes/disappears, recall exposes `support_status` as
`needs_reconciliation`, with changed/missing checks. This is version currency,
not a truth score. Inspect corrections before presenting a derived claim as
current; no factual retraction or identity merge is inferred from a text edit.
Extracted facts with known native source revisions use the same qualification.

### Native accounts and selected support sets

The default episode-only v1 preview remains available. `preview --profile native`
creates a v2 manifest for native text/capture/auto records, including authored
project knowledge and derived accounts. File-authoritative indexes and signed
projections remain outside this generic writer. A v2 application requires
`--record-supports supports.json`, a map from every proposal key to its nonempty,
distinct subset of manifest IDs. Each output receives only those versioned
references and support links; source count is still not corroboration.

All manifest sources remain immutable preconditions, checked under the writer
transaction. The output cannot support its own update or depend on an old revision being
updated in that same batch, overwrite episodes or
identity, or relabel an inference as observation. Native source snapshots are
preserved; expected revisions and normal capture receipts/history still apply.
Removed automatically generated support links become `formerly-supported-by` navigation; native revision
evidence preserves the prior source versions. Link changes share the writer
transaction and roll back on a target revision conflict. Replaying an identical
decision returns its original receipt without new writes.
An original receipt does not establish that its supports remain current today.

Consolidation rejects stale dependent accounts even if the account's own revision
has not changed: an upstream original can change underneath it. It checks the
reachable source-version graph without recursive depth limits; missing/changed
sources and cyclic dependencies remain unresolved. Reconcile from inspected
current originals before publishing another dependent understanding. These are
mechanical source/version checks, not semantic verification of proposed prose.
Ordinary pack/expand retrieval uses the same transitive checks: an unchanged
dependent account is not current when its upstream original changed. After the
intermediate account is reconciled, downstream references to its former revision
remain stale until separately reconciled. These checks do not claim narrative
or three-pass consolidation acceptance.

## Qualification and later integration

Synthetic tests cover source loss, noise omission, gaps, deferred/failed work,
stale updates, batch rollback, crash/response-loss replay, correction history,
readiness and preserved consolidation evidence. They do not evaluate model
selection or factual synthesis. Run the insertion baseline, three consolidation
passes and replay in fictional bindings before automatic formation. A diary is
a rebuildable view, not canonical memory or independent evidence.

Codex observation can later feed candidates under [#11](https://github.com/nicoechaniz/hermes-memory-kit/issues/11)
and [#12](https://github.com/nicoechaniz/hermes-memory-kit/issues/12), after event
coverage is qualified. A native memory read is not another lived encounter.
These primitives do not promise complete `PostToolUse` coverage or activate
native memory generation/coexistence.
