# Integrated operational memory

Active work: [HMK #113](https://github.com/nicoechaniz/hermes-memory-kit/issues/113), under [#11](https://github.com/nicoechaniz/hermes-memory-kit/issues/11). This document records unfinished implementation, not operational qualification.

## Outcome

Deliver one operational HMK memory path on stock Codex: authorized capture → resumable batch learning with relevant prior context → supported consolidation/reconciliation → current hybrid recall. The human requested a single coherent deployment after the useful components are properly integrated, rather than treating separately qualified pilots as a finished operating system.

The 256-record all-canon prompt ceiling was an implementation shortcut, not a Codex/HMK constraint. Replace whole-corpus loading with query/read navigation over the existing retrieval APIs, explicit incomplete/readiness states and full source support for selected updates. A larger arbitrary constant is not the fix.

## Value before integration

For every selected integration, demonstrate an observable improvement over the current installation: more faithful old recall, useful corrections, preserved relations and outcomes, less manual intervention, or lower total cost/latency. Passing structural tests alone is insufficient. Exclude components that add complexity without demonstrated benefit. Native projections are optional, not a requirement to reuse every experiment.

## Work and acceptance

1. Use supported HMK retrieval to obtain pertinent prior memories; include exact references, current revisions and dependent-account navigation. Read complete originals before changing existing records. Corpus size must not impose a total-record admission ceiling. Work budgets constrain individual invocations and leave explicit resumable pending work.
2. Reuse the current embedding space and hybrid ranking in the receiving reader and the producer. Report unavailable backend and pending indices honestly. Complete selected embedding maintenance without rebuilding unrelated vectors. Preserve read-only receiving behavior and source/capability scope.
3. Connect the existing durable capture journal, automatic selection, consolidation/support reconciliation and reader. One learning owner; no competing native writer. Resume after crashes and API errors without repeated successful calls or skipped input.
4. Define a receiving launcher's processing ownership, batching/cadence, budget and persistent backlog visibility. Avoid inference per boundary and no detached hook subprocess assumed to survive shutdown. Human authorization still excludes autonomous Matrix attention/cross-being pooling.
5. Keep optional native projections separate from required integrations. Reuse their verified preservation contracts if useful, but do not enable a second memory authority just to reuse an experiment. Skills/artifact generation is an explicit remaining capability, not an implied property of memory capture.
6. Qualify the complete flow on a substantially larger fictional corpus, with old sparse matches, recent distractors, relevant entries beyond row 256, multiple concurrent sessions, correction/dependent-account reconciliation, no-op capture, unavailable services, source loss and configuration rollback preserving later learning. Reuse already-valid semantic fixtures and consolidation evidence; only rerun the paths changed.
7. Publish one reviewable integrated delivery. Deploy only after whole-flow acceptance, with verified backups, configuration rollback and receiving receipts. Record any remaining limit as unfinished work; do not equate a merged component or a documented limitation with operational completion.

## Boundaries and continuity

Owns the operational continuation under #11, reusing #12 / PR #112. Existing meaningful memory, historical failures, source provenance and other authors' work remain intact. Changes stay unactivated during implementation/qualification; real-source rollout needs explicit selected-source bindings. No private evidence or credentials in public artifacts. Keep the original embedding index and native memory disabled. Do not resume obsolete queues or repeat completed consolidations.

## Current implementation and continuation — 2026-10-13

The development branch adds source-scoped lexical/hybrid navigation before rank
limits, read-only receiving access, visible embedding outages and retained
applicability. The selector can request search, paginated originals and history;
its calls and results are checkpointed separately from frozen capture input.
Only completely read current originals can be update targets or existing link
endpoints. The whole-corpus 256-record load is removed. Per-invocation navigation
budgets leave explicit pending work and do not advance capture cursors.

The focused regression set passed 91 tests before the historical-search hint
refinement. These establish persistence and scope mechanics, not model quality.
The [isolated DeepSeek diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-navigation-receipt.json)
reused the qualified correction source with its target after 300 unrelated records.
Both attempts found and read the correct original without receiving the inventory.
Both intake attempts were rejected: first a stable UID alias unsupported by the
integer-only selector (now supported for supplied originals), then an unknown
record field. Six calls used 32,347 tokens and 50.60 seconds of HTTP time; price
is unverified. The target remains revision 1 and the capture cursor did not move.
This demonstrates useful navigation mechanics, not completed learning or receiving
acceptance. The failed proposals are retained and no factual repair was inserted.

### Resumable correction and provider visibility

The two failed diagnostic attempts above remain evidence of the original
implementation. A bounded schema-feedback step now retains those proposals and
all successful lookups. Resuming the second attempt required one additional
DeepSeek Flash low call (6,853 tokens, 5.79 seconds HTTP time). Intake committed
revision 2 of target 301 and one source-attributed lesson, retaining revision 1.
The redundant proposed correction episode was coalesced. Total diagnostic cost:
seven calls, 39,200 tokens, 56.39 seconds HTTP time; USD price remains unverified.
At that point embeddings were pending; the index/receiving follow-up below
records their later status. Resumed intake alone did not prove narrative utility
or the complete operational pipeline.

Concurrent canonical updates now invalidate the uncommitted selection while
preserving the source event, earlier decisions and successful calls. Focused
checks cover resuming with fresh revisions, interruption before staging and
replay after commit without duplicate canonical entries. Schema corrections have
a persistent budget; repeated invalid output halts visibly rather than looping.

Provider failures now have safe categories and durable incidents in the capture
journal. Payment, quota, authentication, throttling and availability failures
leave the source pending. Delivery receipts and resolution are separate: sending
an alert does not repair processing. The prototype preserves uncertain delivery
and reports an unhealthy state. These are local mechanisms tested with injected
failures, not evidence that a production human has received an alert. The current
worker integrates selection errors; full consolidation/index/launcher coverage
remains required.

### Infrastructure boundary for operational alerts

The human explicitly requires failed processing (including exhausted provider
credit) to become actionable rather than silently skipped. Use the receiving
infrastructure catalog and its maintained operational sources before selecting a
notification transport. HMK owns pending work and processing state; the receiving
supervisor/monitoring and notification infrastructure own observation and delivery.
Do not couple HMK to Telecodex or build another monitoring service by default.
The preliminary Telegram-specific adapter was removed; the launcher adapter
boundary is retained without assuming a destination or transport.

The 2026-10-13 lookup found an existing estate monitoring stack, but its maintained
observability and team-communications sources explicitly retain historical
notification failures and incomplete routing. Those dated records do not establish
current availability or this receiver's access. No matching loaded monitoring
systemd units were found locally; this narrow observation does not rule out other
collectors or prove the host is unmonitored. Confirm the actual current route and
permission holder before adoption. Shared/private topology and credentials stay
in the infrastructure's owning records, not this public project.

The human subsequently selected Telegram delivery and the Sessions Mini App,
and explicitly handed that work to Telecodex. [Telecodex #82](https://github.com/AlterMundi/telecodex/issues/82)
owns receiving-bound notification, presentation and independent observation of
worker absence/stale status, including while the Mini App is closed. HMK retains
durable pending work, safe incident state and the launcher adapter boundary;
no separate HMK notification stack or further Grafana integration is planned.
The issue includes the existing adapter fields, delivery/recovery distinction,
privacy boundary and real failure/recovery acceptance. It is a published handoff,
not a deployed or verified notification route. Complete the producer work without
waiting for that UI; operational adoption must accurately expose delivery readiness.

### Selected index maintenance and actual receiving diagnostic

`memoryctl.backfill_embeddings(record_uids=...)` and `embed-backfill --record-uid`
now restrict maintenance to selected stable records. Missing/stale input hashes
are checked before the work limit; current eligibility/content are checked again
inside the write transaction after HTTP. Invalid vectors or changed dimensions
fail visibly. Semantic search excludes stale legacy vectors. Other configured
spaces and unrelated records remain untouched.

`portable_producer.maintain_index_once` consumes committed capture receipts under
the producer binding and lock. It has a separate, space-pinned checkpoint and a
verified pre-index snapshot. Successful batches survive interruption; maintenance
cannot repeat selection or acknowledge source capture. Embedding-provider errors
enter the same durable operational incident path. This is an explicit callable
operation; receiving launcher integration and live notification remain pending.
The existing fictional pilot CLI accepts `--index-only` with the same selected
`--inbox`, `--binding`, `--context`, `--canon`, `--state-dir` and
`--fictional-isolated-profile` arguments. This requires only the configured
embedding credentials, not a narrator credential. Exit 2 means work is pending;
reinvoke explicitly after resolving the cause. It never reparses source sessions
or repeats the selected capture. The API and CLI are finite operations, not a
new scheduled service.

The [real-provider diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-index-recall-receipt.json)
indexed the two corrected records with the current NVIDIA Nemotron embedding
model. All 300 distractors were also indexed in that same space before retrieval.
The targeted question recovered the correction; one isolated DeepSeek Flash low
narration preserved proposer, reviewer, date, proposal, non-adoption and corrected
history with no unsupported claim found by direct source assessment (4,259 tokens,
7.38 seconds HTTP). The unrelated numeric distractor was ignored in narration,
but its retrieval admission is still a precision concern.

The weak paraphrase returned no admitted memory. The two relevant records ranked
first semantically, but below the unchanged admission threshold. Their automatic
previews emphasize source wrappers and the old erroneous claim. A supported,
compact current account may improve their representation; this remains a
hypothesis for the existing consolidation path, not a reason to lower thresholds.
No broad comparison, aging run or production acceptance is claimed here.

A [single follow-up consolidation](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-account-receipt.json)
reused the existing native organization contract and `consolidationctl` API.
Outside clause inspection found the account supported; replay and isolated
rollback verified original/history preservation. Only its new vector was added;
both frozen query vectors and the threshold were reused. Targeted recall surfaces
the new account, but the weak paraphrase still returns below threshold. This
rejects compactness alone as a sufficient fix. One DeepSeek call used 8,257 tokens
and 21.30 seconds HTTP, plus one document embedding; no further consolidation
passes or narrative calls were run. Candidate relevance/reranking is the next
component to diagnose; this finding does not qualify the account for deployment.

### Candidate navigation and native receiving

The [bounded navigation diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-navigation-receiving-receipt.json)
separates candidate discovery from automatic context admission. Two existing
local FlashRank models and the existing two-query planner did not fix the weak
cue; neither is selected for deployment. Reading complete candidate originals
let a DeepSeek receiver recognize the corrected encounter, but it still retold
unrelated facts for negative questions and used imperfect temporal wording.
Those API diagnostics are not recorded as full conversational acceptance.

`hybrid_candidates` now exposes the existing ranking before `_select_pack`.
Exploratory HMK search returns bounded metadata with an explicit unassessed
relevance marker; the receiver must read evidence and determine applicability.
`hybrid_pack` retains its automatic admission threshold, budgets and access
semantics. This does not admit extra records to canonical memory or treat low
scores as proof. It makes previously hidden candidates available for inspection.

Two fresh native Codex receivers used the real reader over verified source-free
SQLite snapshots of all 303 records. OpenAI Codex `gpt-6.1-sol`, low effort, native
memory disabled, no inherited context or unrelated tools: the weak question
elicited spontaneous search and complete reads of 301/302/303, followed by the
correct proposer, proposal and explicitly dated non-adoption. The CedarWorks
numeric-collision question elicited an evidence gap without unrelated retelling.
The unchanged automatic pack returned no records for the native weak search;
its first numeric-collision query still admits unrelated candidates. Thus the
observed improvement is tool-guided exploration, not improved automatic admission.

The two native turns took 39.72 and 36.55 seconds; reported usage totals 78,198
tokens including 48,896 cached input tokens and the harness context. Three new
query embeddings took 0.82 seconds. Separate API/local diagnostic costs and
responses remain in the receipt; USD amounts are unknown. These are development
diagnostics, not the cost of one production consolidation. The 79 affected
navigation, reader, MCP, foundation and selection tests passed. This qualifies
the navigation mechanism only, not full rollout, aging or other source families.

### Resumable source windows and earlier-context navigation

The old producer's 1 MiB whole-input guard could defer a small new correction
forever once its source history grew. The producer now pins a captured source
group and processes successive windows of new blocks with complete causal
closures. Window progress commits with the canonical capture receipt; the
observation cursor advances only after the group finishes. Later observations
continue accumulating independently and cannot replace the pinned source halfway
through processing. Originals stay in the inbox and selected artifact history.

`source_budget_bytes` (CLI `--source-budget-bytes`, default 64,000) budgets source
context for an invocation, not total corpus/history size. A block or dependency
closure is never truncated to fit. An indivisible closure reports the required
budget and remains pending. A retained source-context lookup similarly resumes
with a larger budget without repeating its paid model request. This is not a
claim that every individual input fits every provider's context capacity; a
paged-source design would need its own qualification if such an input appears.
No global source-length ceiling replaces the removed canonical-record ceiling.

The selector can request `source_before` from an already supplied source ID to
read earlier originals and their dependencies inside the frozen authorized source.
The host does not expose other sources or future blocks through invented anchors.
Read context cannot become a new event by itself. Final rendering preserves source
order, including when earlier context was retrieved after the new correction.
Canonical lookup remains separately bound to the existing complete-read API.

[One real DeepSeek Flash low diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-source-window-receipt.json)
started with a 366-byte new source window over a 1,100,862-byte retained fictional
source. The model requested the earlier context and searched canon, then selected
the correction with the human's original account: Jo Vale, Riverside workshop,
June 4 replacing June 3, and explicit non-attendance by the being. Two calls used
5,611 tokens and 10.42 seconds HTTP; USD unknown, no embedding calls. Unrelated
mechanical history was neither submitted nor admitted. This setup intentionally
omitted the prior source from canon, so it qualifies context resolution rather
than historical selection. The successful response was reused to check the final
chronological rendering; no extra provider call was made for that mechanical fix.

71 affected producer, source-window, navigation, capture, index, provider-error
and CLI checks pass. They cover >1 MiB first capture, crash after canonical commit,
concurrent later capture, dependency closure, missing group detection/recovery,
prior-context continuation and context-budget resume without repeated inference.
This is source-window qualification, not complete pipeline or production rollout.

### Finite foreground worker and restart

`memory_worker.run` now coordinates finite capture, organization and selected-index
phase calls under one inbox-bound worker lock. Pending phases are held for the
rest of the invocation; independent committed work can progress. The worker
validates the producer destination, snapshots before registering its owner and
publishes a small last-observed status before and after phase work. It creates no
background process, hook or timer. The [worker contract](memory-worker.md) defines
explicit budgets, receiving obligations and the current organization gap.

The [real-provider restart diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-worker-receipt.json)
reused the already-qualified source-window corpus, without selecting it again.
One current NVIDIA embedding request indexed its new record (0.34 seconds HTTP).
The first invocation took 22.01 seconds including setup, and the next explicit
invocation 0.54 seconds with no selector or embedding request. Both truthfully
report organization pending because its adapter is not implemented. This verifies
finite index integration and no-work reentry, not whole-flow readiness.

34 affected tests passed: worker ownership/concurrency, provider-credit failure
and recovery, original capture/index behavior, CLI budget forwarding and safe alert
projection. Existing internal `embedding` incidents now project as receiving
`index` incidents without rewriting historical journals, fixing a demonstrated
compatibility gap with the newly supplied Alerts exporter. Notification delivery
remains owned by Telecodex #82. Native memory and production remain unchanged.

Existing-account discovery is also implemented in `consolidationctl.reconcile-plan`.
It reads the canonical revision graph, returns ready accounts separately from
missing/cyclic/protected-support blockers, and allows a dependent only after its
current sources are reconciled. It does not create summaries, a second queue or
model calls. Worker status exposes counts while retaining the unconfigured-adapter
pending state. Nine focused discovery/consolidation/currency checks passed;
the worker integration also passed its ten affected checks. These validate work
discovery and ordering, not semantic generation or automatic application.

### Account reconciliation, review and organization indexing

The organization adapter now updates an existing stale inferred account through
`consolidationctl`, preserving its identity, revision history and exact supports.
It reuses the qualified assertion reviewer in `scripts/assertion_review.py`;
current pilot receipts also pin that shared implementation. No historical frozen
artifact was modified. A single bounded evidence-guided revision may follow a
rejection; the final candidate is reviewed again. Rejected or incomplete work
remains pending. Complete source fields now accompany raw prose in review,
avoiding a generation/review evidence mismatch. Canonical conflicts retain prior
attempts, and a committed account is not regenerated after process interruption.

The [new fictional correction diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-reconciliation-receipt.json)
used a verified copy of the existing 303-record corpus and its account. A new
human report describes an August 10 limited canary, seven dropped readings and
same-day rollback. DeepSeek drafted the account, but its review exhausted 12,000
reasoning tokens without a final answer. The identical candidate was then reviewed
by isolated OpenAI Codex Sol 6.1 low, which caught a report/event chronology error
and inappropriate binding/packet boilerplate. One DeepSeek revision fixed these;
Sol reviewed the final nine clauses. Direct source comparison found no unsupported
final assertion. The account advanced to revision 2; prior history and all 300
distractors remain intact. The account is still verbose; compression and full
conversational receiving are not claimed from this result.

Five model calls, including the failed reviewer: 95,394 reported tokens and 312.99
seconds of dispatch time. These include Codex harness context; USD is unknown.
One current-provider embedding indexed the updated account (0.39 seconds HTTP).
The worker then reached idle on its owned streams and a second explicit invocation
used no model or embedding calls (0.70 seconds). The source correction was applied
through the existing mutation API on the isolated copy, so this diagnostic does
not establish new capture selection or indexing of unrelated external writes.

145 affected checks passed across reconciliation, worker/index, shared narrative
review and pilot contracts; 69 targeted checks then passed after the explicit
native-review CLI and source-envelope adjustments. The real final review evidence
matches the final source adapter byte-for-byte. Production is unchanged.

### Installable launcher and explicit provider recovery

`scripts/memory_runtime.py` now supplies finite `run`, read-only `status` and an
explicit `retry` command over the same capture, account and index APIs. It requires
an existing canonical database and inbox, a private versioned receiving profile,
minimal model context matching the full capture binding and explicit budgets.
The operational binding's source roots/settings no longer have to be copied into
model context. DeepSeek Flash low drafts/revises; isolated native OpenAI Codex Sol
6.1 low reviews. There is no silent provider substitution. Research compatibility
entrypoints reuse the extracted transport implementations; current fingerprints
track those implementation files and historical evidence is untouched.

Credentials are resolved only on a real dispatch. Completed requests replay; an
uncertain/failed attempt remains visible. `retry` binds an explicit operator
reconciliation to the exact old receipt under the inbox worker lock, creates no
network effect itself and preserves failures in a separate attempt chain.
Successful output cannot be retried as a transport failure. Model-policy changes
remain an explicit reconciliation rather than an automatic retry. Launch failures
return nonzero with safe metadata; the supervisor must observe the process exit,
not assume an old worker-status file is fresh.

46 affected tests passed, including full capture binding with minimal model
context, capture/index/restart integration, missing credentials, selected-source
provider routes, actual request replay, credit failure and explicit recovery,
receipt tampering, changed model policy, historical clients and failure privacy.
Ruff passed for the changed runtime modules and new tests. These are mechanical
checks, not further semantic acceptance.

The [fresh-process launcher diagnostic](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-launcher-receipt.json)
reentered the completed 303-record fictional owner through the installable command
twice. It reached idle in 8.24 and 2.01 seconds, without a generation credential,
new model calls, changes to canonical database bytes or changes to retained
provider dispatches. This establishes fresh-process reentry only; it does not
claim fresh-source selection or conversational quality.

### Integrated correction, failed action and aged receiving comparison

The [integrated-flow receipt](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/integrated-flow-receipt.json)
records one new fictional source through the actual capture handler, finite
runtime, account reconciliation, indexing and source-free native receiving. It
reuses the 303-record corpus. Tavi corrects seven lost readings to nine and asks
Ilex to notify Mira; the tool attempt fails with `permission_denied` and
`delivered=false`. A temporary terminal-color instruction is not selected.

The first run exposed an integration defect: source selection directly updated
an inferred account, replacing its source-support metadata with reported-source
metadata. Organization then falsely found no work. Capture now rejects such
updates and directs selection to the original source. Derived accounts retain
reconciliation ownership. Free-form selector link notes also remain in the exact
formation artifact instead of becoming unsupported canonical assertions; links
remain navigation associations to inspect against originals.

The corrected run updated original 301 to revision 4, retained failed action 304,
and reconciled account 303 to revision 3 with current support references. The
first native review supported every claim but required the full issue URL in the
account; one bounded revision supplied it and passed final review. Source bytes,
prior original/account revisions, all 300 distractors and SQLite integrity are
verified. Reported experience and inferred understanding retain separate modes.
No temporary preference was admitted as a record.

A second demonstrated wiring defect was an import-time default provider leaking
into navigation despite the selected runtime's valid embedding configuration.
`Reader.live_pool` now accepts that configured backend; the producer supplies the
same backend it uses for indexing. This preserves per-receiver provider/space
selection without changing global process configuration. The formation above
used the then-visible lexical fallback; it is not relabeled as healthy hybrid
formation. The corrected backend path has direct regression coverage, and both
receivers below use actual healthy hybrid retrieval with no backend errors.

Two fresh isolated Codex Sol 6.1 low receivers answered the identical question
under identical conditions: retrieval clock advanced ten years, all 300
unrelated records dated recently in the receiving copies, relevant timestamps
unchanged, native memory off and no source sessions or hidden rubric available.
Before capture: Mira and her ordering proposal, seven lost readings per Tavi's
old report, no confirmed delivery. After capture: the same person/proposal,
**nine** lost readings explicitly correcting seven, dated limited trial and
same-day rollback, plus the rejected comment and unconfirmed alternate contact.
Both distinguished Tavi's report from Ilex operating the canary. Direct inspection
found no unsupported final assertion. Stable identity and full world pointers
remain in the retained originals/account even when the conversational answer uses
names, handles and record citations.

The qualified receiver turns took 34.81 and 19.40 seconds; aggregate native usage
was 55,834 and 39,486 tokens respectively, including cached/context tokens. The
corrected formation/reconciliation path used seven model calls, 103,314 reported
tokens and 274.56 dispatch seconds. This includes source navigation and the one
review/revision cycle, not a per-turn operating charge. The retained failed
integration cost 42,983 tokens; its failure is not counted as success. Embedding
and query timings are recorded separately; USD billing remains unknown. These
are development/correction measurements, not a routine daily workload estimate.

46 focused checks passed after the backend fix, covering capture ownership,
source navigation, direct reader/backend routing, runtime and producer behavior.
The account-reconciliation checks also passed before that routing-only change.
This closes the identified new-source/correction/failed-action receiving case;
reuse it and the earlier qualified cases. Another broad formation, consolidation
or narrator comparison is not the next task.

Exact continuation toward deployment:

1. Connect the receiving launcher to the established credential facility and
   supervised batching/activation. This body's DeepSeek account is in its Hermes
   pool, not its embedding environment file. Use the existing supervisor and
   keep the processing state/notification distinction. Prepare any activation
   requiring additional authorization completely before requesting that decision.
2. Complete the coordinated merge and adoption on CompAII, Eko and Oliva, with
   each body's selected source bindings, backups, configuration rollback that
   preserves later writes and a small actual receiving check. Keep their separate
   existing pools and current memory access. No extra research branch or prompt
   comparison is required before this operational work.
3. Bind the deployed worker status to the established Alerts observer. Telegram
   and Sessions presentation remain owned by Telecodex #82; its fictional and
   installed read-only receiving evidence does not establish adoption of these
   real HMK bindings. Do not build an HMK notification transport.

Production remains unchanged. No old queues were resumed; no real conversations
were ingested. The earlier stock-hook and six-case producer evidence stays valid
for its original contract and is not relabeled as evidence for the new pipeline.

### Finite receiving supervision — 2026-10-13

The deployment path now renders a systemd oneshot and optional explicitly selected
calendar, pins an explicitly selected native reviewer executable, and supports
forward-only source admission by session creation time and original working
directory. Rendering changes no installed hook, service or timer. Native memory
remains off. Existing per-body embedding spaces and all live pools are retained.

33 focused capture/runtime/provider/supervision checks passed. An actual user
systemd invocation over the already-qualified fictional corpus completed idle in
545 ms with capture, account reconciliation and indexing all current; no proposer
ran. A deliberately absent fictional database produced safe launch failure and
systemd `Result=exit-code`, `ExecMainStatus=1`. No semantic battery was repeated.

The existing Alerts observer assumes a continuously active worker, which would
misclassify a successfully completed oneshot. The exact finite-worker contract
and required distinction were handed to its receiving owner in
[Telecodex #82](https://github.com/AlterMundi/telecodex/issues/82#issuecomment-6144870671).
Actual production observer binding is still pending; this handoff is not delivery
evidence. Receiving package preparation does not activate capture or learning.

Continue with selected credential/profile preparation, coordinated adoption and
the three receiving checks above. Do not reopen completed semantic qualification.
