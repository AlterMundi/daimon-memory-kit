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

```sh
hmk memory_runtime.py run --profile /selected/worker.json
hmk memory_runtime.py status --profile /selected/worker.json
```

The wrapper must first contain this delivery. `run` exits 0 when its owned phases
are idle, 2 when work remains, and 1 on launch/configuration failure. Failures emit
only a safe error class, preserve the previous worker observation and must be
observed through the receiving supervisor's exit status as well as HMK's journal.
`status` exits 0 for a successful read even if processing is unhealthy: it does
not open the canonical pool, read credentials, dispatch models or resume work.

DeepSeek credentials are resolved lazily from the named process environment
variable. An idle run or successful dispatch replay needs no credential. The
receiving launcher must obtain it through its established secret facility;
`embedding_env_file` is HMK's existing embedding configuration, not a new DeepSeek
credential store. The current body's existing DeepSeek route is its Hermes pool,
not that embedding environment file. Connecting that receiving secret route and
supervisor is still adoption work, not evidence of a missing account or quota.

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

Source-block capture may update original reported records, retaining earlier
meaning and history. It cannot overwrite an inferred/generated account and erase
its support metadata; such accounts belong to the reviewed reconciliation phase.
Selector link prose remains in formation evidence. Canonical link notes identify
navigation associations, not independent factual support.

The runtime supplies its configured memory backend to navigation as well as
indexing. A reader imported before the private profile was selected must not use
an unrelated default credential environment. `Reader.live_pool(..., backend=...)`
provides this explicit binding; existing default-reader callers remain compatible.

The integrated fictional correction/failed-action case and ten-year-clock
receiving comparison are qualified in `integrated-memory-plan.md`. Receiving
supervision, secret routing and the three live installations remain the next
work; repeating that completed semantic case is unnecessary.
