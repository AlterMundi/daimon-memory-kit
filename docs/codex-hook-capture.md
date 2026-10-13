# Opt-in source capture for stock Codex

Experimental delivery for [#12](https://github.com/nicoechaniz/hermes-memory-kit/issues/12). This is durable handoff, not automatic selection, a scheduled processor or production installation. The existing contextual HMK reader stays separate. Native memory remains disabled.

`capture_inbox.Inbox` stores caller-authorized source snapshots and event payloads in a local SQLite journal. An append stores only its suffix and a verified prefix dependency; a changed prefix starts a new full version while retaining earlier versions. Source bytes, head and event receipt commit together. Replay after an uncertain commit returns the same observation. Restoring checks every dependency's size/hash. Different sessions retain distinct source identities.

`codex_hook_capture.py` is the harness adapter. Its explicit local binding names the subject, body, selected source root and working directories, inbox path and source-size ceiling. The incoming hook cannot choose another receiving pool or identity. The adapter checks the transcript's session ID, preserves the event payload (needed before a prompt appears in the transcript), and exposes missing/changing/oversized sources as incomplete captures. Limits never produce a truncated successful receipt. A complete capture does not mean a complete turn or a selected memory.

Example binding for an **isolated fictional profile only**:

```json
{
  "schema": "hmk.codex-hook-binding/v1",
  "subject": "fixture:ilex",
  "source_instance": "fixture:desk",
  "source_root": "/isolated/codex-home",
  "allowed_cwds": ["/isolated/work"],
  "inbox": "/isolated/capture.sqlite",
  "max_source_bytes": 16777216
}
```

An explicitly enabled hook runs `python3 /selected/scripts/codex_hook_capture.py --binding /selected/binding.json`. Both Python modules must be available together. Hook discovery and trust are owned by the isolated receiving configuration; the command installs nothing. Successful stdout is `{}`: it neither blocks the turn nor injects memory prose. An incomplete capture emits a diagnostic; the durable observation retains its reason. Binding/path errors fail visibly. No source directory scan or model call occurs.

Stop is the primary evaluated capture boundary; the handler also accepts the lifecycle events from the diagnostic. It does not promise a hook on abrupt process death. A future coordinator must reconcile unfinished selected sessions, retain gaps and distinguish capture progress from semantic processing progress. It must not advance past incomplete evidence merely because a hook returned.

## Evidence and remaining work

The official 0.162.1 proxy invoked the actual handler at Stop and SessionEnd for a new fictional encounter. Two revisions were reconstructed exactly. A local replay of those actual snapshots then deleted its source copy and recovered both versions; duplicate intake did not duplicate observations. The [receipt](../research/agent-memory-2026-10-06/pilots/stock-hook-evidence/capture-replay-receipt.json) records 75,563 aggregate snapshot bytes represented by 38,123 stored delta bytes, plus journal metadata.

Nine focused tests cover commit interruption before/after durability, concurrent duplicates and distinct sessions, source rewrite/reversion, source loss, prompt-only pending input, bounded deferral, altered bytes and binding/scope rejection. An additional proxy framing test remains valid. No provider call is required by these tests or capture itself.

The observed native Stop took 1.577 seconds. Local first-use initialization initially took 1.877 seconds and a subsequent append 0.120 seconds. Schema initialization was subsequently grouped into one transaction, with the affected storage tests passing; these observations are not a production latency guarantee or measurements of the optimized first-use path. Native dispatch and writer I/O must continue to be accounted separately.

The inbox is temporary processing evidence, not ordinary HMK recall. This version does not automatically delete input, prune dependencies or mark it semantically processed. There is no infinite-storage guarantee: the caller owns capacity and an eventual explicit archive/retention policy. Do not purge originals that pending work or preserved history needs. Copy/transport of the inbox does not admit Matrix events or grant authority.

The subsequent [portable producer](portable-producer.md) now implements finite, explicitly owned processing through existing CaptureLedger and supported writers, with automatic selection and source-free recall qualified in the isolated corpus. Source capture and semantic processing remain separate. No automatic production worker, native learning, timer or cross-being pooling follows from either delivery.
