# Foreground memory worker

`memory_worker.run` is the finite owner-facing coordinator for the existing
capture, organization and selected-index APIs. It does not launch itself, install
hooks/timers or create a detached child. The receiving launcher supplies the
configured proposer, receiving binding, canonical database and capture inbox.

Each invocation takes the inbox's worker lock, validates the persisted owner and
runs at most `max_steps` phase calls, round-robin. `capture_limit` and `index_limit`
bound each phase's selected work. Individual phases keep their
existing transaction/checkpoint contracts. A pending/deferred phase is held for
the rest of that invocation; successful independent work can continue. Idle
observations of downstream phases are invalidated when upstream work commits.
One completed source window does not imply the capture queue is empty.

The organization adapter is required for full-flow readiness. Its callable must
return `idle`, `complete`, `pending` or `deferred`, own its stable consolidation
receipts, preserve source/current-revision checks and perform the qualified
semantic assessment before applying generated prose. Missing configuration is
explicitly pending; do not substitute an always-idle adapter for a real account
backlog. `account_reconciliation.process_once` now supplies this adapter for
existing inferred native accounts. It uses a complete current manifest and target,
a retained model draft, the shared assertion reviewer and `consolidationctl.apply`.
Current source fields accompany the prose in review; source metadata is memory
provenance, not current body authority. Plain/mixed originals remain quotable.

An unsupported draft can receive at most one source-grounded revision, whose final
text is reviewed afresh. The next rejection remains pending. Successful dispatches,
failed reviews and prior candidates are retained; explicit `reprepare_review`
can select a different reviewer without reissuing the completed generation.
This never bypasses staged-event ownership. A proven concurrent source change
supersedes an uncommitted proposal while retaining its artifacts; after a failed
staged application, its ledger event is explicitly omitted before a fresh attempt.
Already committed work replays without model calls. A verified snapshot precedes
account mutation; no new summary is generated merely because a phase runs.

Index maintenance now consumes both owner-bound capture and organization streams
with separate checkpoints. Existing capture cursors retain their meaning;
`organization_indexed_through` reports the other stream. Neither cursor proves
that unrelated external writes have been indexed. The installable finite entrypoint
below connects the providers; receiving supervision, credential routing and
whole-flow qualification remain prerequisites to production adoption.

An HTTP 410 from the configured embedding model leaves pending index work and
one open incident for that provider/model in this inbox. Capture and organization
index attempts reuse it. A successful index commit through that exact model can
resolve the incident. A working alternate model alone cannot resolve it. Qualify
an authorized replacement as a separate embedding space, preserve the prior
vectors and bind the writer and reader to the same selected space. The worker
does not probe idle endpoints or change its selected model on failure.

`consolidationctl.py reconcile-plan --limit 32` discovers stale existing inferred
native accounts directly from the canonical support graph. It returns separate
ready and blocked hints/counts. Current child support must be reconciled before
its dependents; missing, cyclic or separately owned support stays blocked.
The result budget does not hide ready work behind earlier blocked accounts or
limit corpus discovery. This is read-only navigation, not a second queue or a
semantic verdict. Application still requires complete current originals and the
existing consolidation revision checks. Without an organization adapter, worker
status includes these two counts but remains pending even if both are zero.

Provider clients must reuse completed dispatch receipts and retain uncertain
requests. The worker never silently changes provider or resubmits a failed paid
request. `ProviderProblem` from organization enters the same durable incident
outbox used by capture/index. Resolution of a worker incident is scoped to its
phase; notifying the human does not resolve the failure. An unexpected exception
leaves the phase pending with a safe error class, not its message or source text.

## Observation

`worker-status.json` implements `hmk.worker-status/v1`, with an opaque owner ID,
start/update timestamps, current phase, completed step count, last phase states
and explicit remaining work. It contains no source text or private paths. It is
written before phase invocation and after each returned result. A killed process
can leave a `running` receipt: this is a last observation, **not a heartbeat or
proof of liveness**. Missing state returns `unobserved`, not idle. A successful
status read does not mean processing is healthy.

```text
hmk memory_worker.py status --state-dir /selected/private/producer
```

This read performs no source capture, provider lookup, model request or resume.
The caller must apply its own receiving authority and supervision/freshness
policy. [Telecodex #82](https://github.com/AlterMundi/telecodex/issues/82) owns
Telegram delivery, Sessions presentation and independent absence/stall detection.
The private journals remain the recovery source; do not expose them wholesale
through the Mini App.

## Isolated qualification

The existing `portable_producer_trial.py` accepts `--worker-steps N` with its
explicit fictional-profile/source bindings. It exits 2 while work or an adapter
remains pending. Add `--reconcile-accounts` to invoke account reconciliation.
`--reviewer codex-sol-low --review-catalog PATH` explicitly selects the existing
isolated native OpenAI reviewer; it retains DeepSeek Flash generation/revision.
The catalog must disable tools, and native memory remains off. Without that
selection, the reviewer stays DeepSeek; there is no implicit provider fallback.
This is a fictional qualification entrypoint, not production activation.
Its existing `--index-only` remains independently usable.

Reinvocation resumes retained phase work. Configuration rollback preserves the
capture inbox, canonical database, phase checkpoints and diagnostic evidence;
restoring an old code/config revision must not restore an old memory snapshot over
later writes. No production activation is included in this delivery.

## Installable invocation

`scripts/memory_runtime.py` uses only installed `scripts/` modules. The historical
research clients now delegate their transports to these same implementations;
current comparison fingerprints pin the implementation files. Existing frozen
results remain unchanged. The full capture binding (including source roots and
capture settings) stays separate from model context; subject and source instance
must agree, and the inbox still validates the complete immutable binding.

Create a private `hmk.worker-profile/v1` JSON file with absolute paths:

```json
{
  "schema": "hmk.worker-profile/v1",
  "database": "/selected/memory/library.db",
  "memory_base": "/selected/memory",
  "inbox": "/selected/capture.sqlite",
  "binding": "/selected/capture-binding.json",
  "context": {"subject": "fixture:ilex", "source_instance": "fixture:desk"},
  "state_dir": "/selected/producer",
  "source_scope": "fictional",
  "embedding_env_file": "/selected/embedding.env",
  "generation": {
    "provider": "deepseek", "model": "deepseek-flash", "effort": "low",
    "output_token_limit": 12000, "credential_env": "DEEPSEEK_API_KEY"
  },
  "review": {
    "provider": "openai-codex-native", "model": "gpt-6.1-sol", "effort": "low",
    "catalog": "/selected/tool-disabled-catalog.json"
  },
  "budgets": {
    "max_steps": 6, "capture_limit": 32, "index_limit": 32,
    "source_budget_bytes": 64000, "navigation_steps": 4
  }
}
```

The example selects fictional sources. Real receiving profiles require
`human-authorized-selected-context` and previously authorized source bindings;
setting this label does not itself grant access or import sessions. Database and
inbox must already exist. The launcher does not initialize a new canonical pool or
migrate its schema. The native catalog must disable tools; review is a fresh
ephemeral OpenAI Codex invocation with native memory, instructions and skills
suppressed by the established adapter. An optional `review.credential_file` may
select the receiver's existing auth file by reference. No credential value belongs
in this JSON. Historical fictional Nous comparison support is not a runtime route.

To use bounded native generation, select `openai-codex-native`, `gpt-6.2-sol`
and `low` in `generation`, retaining its existing `output_token_limit`. Omit
`generation.credential_env`. The review profile must select the same Sol model,
the receiving tool-disabled catalog, the pinned Codex binary and the existing
owner's auth file. Generation uses a separate tool-less ephemeral app server
with the provider-side token ceiling. The worker records its single reservation
before authorizing it and requires matching usage and terminal response evidence.
An unsupported native protocol fails closed. A failed bounded attempt retains
a fixed native failure code when available. Terminal failures can also retain
a known native error category and an HTTP status. The receipt omits raw error
messages. A reservation without matching usage or response remains unresolved,
even if the worker recorded a terminal error. Preserve that attempt and inspect
its existing evidence before any recovery.

A generation policy change can read an exact retained DeepSeek receipt under
its original budget. In-flight, failed and missing attempts remain owned by
their original journal. A new generation selection cannot use a missing old
receipt as permission to dispatch Sol or repeat the original call.

```sh
hmk memory_runtime.py run --profile /selected/worker.json
hmk memory_runtime.py status --profile /selected/worker.json
```

The wrapper must first contain this delivery. `run` exits 0 when its owned phases
are idle, 2 when work remains, and 1 on launch/configuration failure. Failures emit
only a safe error class, preserve the previous worker observation and must be
observed through the receiving supervisor's exit status as well as DMK's journal.
`status` exits 0 for a successful read even if processing is unhealthy: it does
not open the canonical pool, read credentials, dispatch models or resume work.

DeepSeek credentials are resolved lazily from the named process environment
variable. An idle run or successful dispatch replay needs no credential. The
receiving launcher must obtain it through its established secret facility;
`embedding_env_file` is DMK's existing embedding configuration, not a new DeepSeek
credential store. The current body's existing DeepSeek route is its Hermes pool,
not that embedding environment file. Connecting that receiving secret route and
supervisor is still adoption work, not evidence of a missing account or quota.

`review.binary` optionally selects an absolute path to the qualified Codex CLI.
Its content hash joins the durable model policy, so replacing the executable
cannot silently change a pending review. This does not update the receiving
body's everyday CLI. Keep the selected executable outside `CODEX_HOME`: native
review deliberately hides that directory in its private mount namespace, except
for its read-only authentication descriptor.

The configured review model can select Sol 6.1 or Sol 6.2. Sol 6.2 requires an
exact tool-disabled catalog entry that advertises low effort and a qualified
CLI for the same authorized account. The selected model is part of each new
request and receipt. A pending operation retains its original model policy. The successor can read
an exact retained Sol 6.1 operation receipt under the same generation and
review authority. It cannot dispatch a missing or failed request in that
operation. Reconcile unresolved work through the existing owner path.

Dispatch receipts pin request, provider/model settings, transport implementations
and the native catalog. Pending work rejects a silent model change. A missing
credential leaves an actionable authentication incident without a network attempt;
fix it and invoke `run` again. A retained failed, incomplete or uncertain paid
attempt requires explicit reconciliation before a transport retry:

```sh
hmk memory_runtime.py retry --profile /selected/worker.json \
  --request /selected/producer/OPERATION/requests/HASH.json \
  --reason 'Credit restored; retained failed attempt inspected.'
hmk memory_runtime.py run --profile /selected/worker.json
```

`retry` takes the same inbox worker lock, validates the established destination,
and records a decision bound to that exact receipt. It makes no network call.
The next run writes a separate attempt; it never overwrites the failure or retries
completed output. If that attempt fails, inspect and select its own retained
request. Unknown remote completion must remain explicit in the operator's decision.
Semantic rejection is different: transport retry does not bypass the existing
selection/reconciliation rules or authorize changing model policy.

A receiving supervisor may invoke this finite command explicitly. A successful
exit is a completed invocation, not a missing long-running daemon. Preserve inbox,
canonical pool, worker directory and private profile across process restarts and
configuration rollback. Do not add `Restart=always` to retry failed paid work.
This delivery installs no service, timer, hook or source capture binding.


## Source ownership and configured retrieval

Capture and nightly triage prioritize lived experiences, people, relationships,
places and events that help tell the paired biographies. A concise project
reference establishes that an effort exists or existed, and major milestones
record what the team achieved and why it mattered. Lasting decisions and
transferable lessons can qualify. Status, metrics and retry receipts stay in
operational records. Retained nightly requests keep the exact prior prompt
during recovery.

Source-block capture may update original reported records, retaining earlier
meaning and history. It cannot overwrite an inferred/generated account and erase
its support metadata; such accounts belong to the reviewed reconciliation phase.
New capture jobs carry forward already quoted source blocks verbatim on an
update. The frozen job selects the rendering so retained decisions replay with
their original bytes.
Selector link prose remains in formation evidence. Canonical link notes identify
navigation associations, not independent factual support.

Two successive lookup rounds with the same previously observed requests and
results end navigation. Distinct requests can advance the review for up to 32
completed lookup rounds per selection attempt, counting retained rounds across
worker invocations. The final request uses the retained source excerpts and
complete originals. It may explicitly defer if the evidence is insufficient.
For a low-cost daily run, use `max_steps: 3` to visit capture, organization
and indexing once, and `navigation_steps: 1` to limit capture selection to one
round. Retained lookups carry over to the next run. Sleep triage has its own
step budget and runs after the core phases.
If a paged lookup needs more source context and the final decision defers, the
worker retains the required byte count. Set a sufficient receiving source limit
to resume the exact blocked read. That preserves both previous responses and
uses a fresh selection request only after the missing context is available.

The runtime supplies its configured memory backend to navigation as well as
indexing. A reader imported before the private profile was selected must not use
an unrelated default credential environment. `Reader.live_pool(..., backend=...)`
provides this explicit binding; existing default-reader callers remain compatible.

The integrated fictional correction/failed-action case and ten-year-clock
receiving comparison are qualified in `integrated-memory-plan.md`. Receiving
supervision, secret routing and the three live installations remain the next
work; repeating that completed semantic case is unnecessary.

## Receiving supervision and forward-only capture

`memory_supervision.py` renders systemd units without installing or enabling
them. Supply the private worker profile, installed interpreter and selected
credential environment-file reference. No credential values enter the unit:

```sh
python3 scripts/memory_supervision.py --profile /selected/worker.json \
  --interpreter /selected/venv/bin/python \
  --environment-file /selected/provider.env --output /selected/rendered
```

An explicitly selected `--calendar daily` also renders a timer; rendering grants
no activation authority. The service is finite, has no automatic restart, and
terminates its process group on timeout. Budgets/checkpoints remain DMK-owned.
An invocation can end with pending work; neither the next timer tick nor an alert
retries a retained failed paid request without the explicit recovery above.

A completed oneshot normally becomes inactive. The receiving observer must use
service `Result`/`ExecMainStatus`, cadence and DMK timestamps to distinguish that
from failure or overdue work. `RemainAfterExit=yes` prevents subsequent scheduled
invocation and is not appropriate. An active timer alone does not prove worker
health. Integration is tracked in
[Telecodex #82](https://github.com/AlterMundi/telecodex/issues/82#issuecomment-6144870671).

For newly selected sessions, `hmk.codex-hook-binding/v2` retains all v1 fields and
requires a timezone-aware `sessions_started_at_or_after`. Admission checks the
transcript's session creation timestamp and original working directory, as well
as the hook working directory and exact session ID. A late event does not make
an older session eligible. Unselected sessions are skipped without creating an
inbox. If the source header cannot establish scope, the handler reports deferred
capture and does not journal potentially unauthorized prompt/answer payloads.
That report is a capture gap, not successful preservation. v1 retains its original
explicit selected-source behavior. Never silently change an existing inbox's
immutable binding; activate a newly selected binding separately.

Before selecting a replacement native executable, run
`native_generation_preflight.py --profile <profile> --binary <candidate>`
with the actual worker owner and its existing selected account. The synthetic
isolated request stops before acknowledging a provider reservation. It
qualifies the native admission protocol only. A real provider outcome still
needs its own receipt. The failure report includes a closed admission stage
and bounded RPC code without provider text or source content.

Bounded Codex generation uses the provider's strict structured-output subset.
The native adapter transports navigation alternatives inside a closed object
and represents optional fields by null. It decodes that transport back to the
existing DMK decision and then uses the ordinary source, scope, revision, and
admission checks. Retained receipts preserve the raw native response, the
provider schema hash, and the normalized decision separately. Do not retry a
previous reserved operation merely because a compatible schema is available.
