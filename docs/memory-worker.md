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
backlog. This API is not yet a complete production organization adapter. The
current selected-index implementation consumes portable capture receipts;
indexing organization receipts remains part of that integration work.

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
remains pending. This entrypoint cannot yet qualify full organization or enable
production. Its existing `--index-only` remains independently usable.

Reinvocation resumes retained phase work. Configuration rollback preserves the
capture inbox, canonical database, phase checkpoints and diagnostic evidence;
restoring an old code/config revision must not restore an old memory snapshot over
later writes. No production activation is included in this delivery.
