# Native Codex extraction into HMK: bounded diagnostic

Date: 2026-10-12. Initial diagnostic: feasible implementation seam identified.
Follow-up: [real V1/V2 extraction gate](../research/agent-memory-2026-10-06/pilots/2026-10-12-native-producer-qualification.md) found V1 loses two required episodes and V2 preserves all four tested cases.
**Follow-up 2026-10-13: [bounded extraction-only delivery is qualified](../research/agent-memory-2026-10-06/pilots/2026-10-13-native-candidate-delivery.md).**
The original diagnosis below is historical; explicit selection and production
rollout remain separate. Reuse the closing report for current evidence and continuation.
The human requested this diagnosis before choosing a new implementation goal.
Production CompAII/Eko/Oliva configuration and memory remain unchanged.

## Conclusion and next decision

There is a real native producer to evaluate, but no ready integration hook was
identified in the inspected release. The proposed next goal should first test
that producer's usefulness on a few fictional experiences. Only if it preserves
the required meaning should we build reliable delivery to HMK. A durable delivery
queue cannot recover an experience that the extractor already discarded.

Use the existing HMK foreground MCP reader for recall. If the native producer is
useful, let it propose candidates while HMK owns selected durable records and
consolidation. This requires an extraction-only execution path as well as reliable
delivery; merely enabling native memories would also run native consolidation.
This proposed split does not claim full parity with native skill/artifact learning.

## Sources and version boundary

The currently observed shared daemon reports 0.162.1. This diagnosis fetched the
official `rust-v0.162.1` tag, commit
`092d3acd6bec3e3a14bdc7e7a2810ab628ab759d`, without switching or changing the existing
Codex checkout. Relevant extraction/storage/prompt semantics were checked against
that tag, rather than assuming the earlier `0.160.0-hmk.1` experiment represents
the installed official build.

Primary source entry points, all under that release:

- [Startup pipeline](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/memories/write/src/start.rs): eligible root startup runs pruning, quota checks, phase 1, then phase 2.
- [Extraction and committed result](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/memories/write/src/phase1.rs): structured model result followed by `mark_stage1_job_succeeded`; no-output uses a separate transition.
- [Extraction schema](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/memories/write/src/phase1_output.rs): V1 has raw memory and a rollout summary; V2 has a summary/slug, with summary truncation to 9,000 bytes.
- [Memory transactions](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/state/src/runtime/memories.rs) and [dedicated memory schema](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/state/memory_migrations/0001_memories.sql): mutable current outputs, job leases, phase-two scheduling and retention.
- [File rebuilding and pruning](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/memories/write/src/storage.rs): generated files are rebuilt from selected outputs; unselected summary files are removed.
- [Consolidator](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/memories/write/src/phase2.rs): internal agent has MCP, plugins and recursive memory use disabled.
- [App Server methods](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/app-server-protocol/src/protocol/common.rs) and [memory status](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/app-server-protocol/src/protocol/v2/memory.rs): mode changes, readiness counts and reset do not provide an extraction delivery/acknowledgment API.
- [Official memory controls](https://learn.chatgpt.com/docs/customization/memories) and [hooks](https://learn.chatgpt.com/docs/hooks), fetched on the diagnostic date: lifecycle hooks can trigger custom summarization, but their advertised events do not establish native extraction-commit delivery.

The earlier fork's `memories.startup_processing` switch is absent from the
official release's startup gate. Do not pass it to stock Codex and assume it
prevents background writes. `use_memories=false` controls consumption, while
`generate_memories=false` controls new-thread contribution; neither is a reliable
global stop for previously eligible inputs. Native generation must be diagnosed
in a separate fictional home, never enabled experimentally in a live cohort home.

## What is real, and what remains proposed

| Question | Observed answer | Consequence |
|---|---|---|
| Does Codex already extract learning? | Yes: phase 1 generates structured output from eligible rollout input. | Reusing it is a concrete option. |
| Can our MCP capture its writes? | The phase-two worker disables MCP; extraction commits through internal state APIs. | Installing a read/write MCP tool alone does not redirect the pipeline. |
| Is there a supported commit hook? | No such event or drain/ack API identified in the inspected hooks/App Server surface. | A lifecycle hook that runs our own summarizer is a different design. |
| Can we just poll SQLite/files? | Current results are overwritten, deleted on no-output, and pruned. Files reflect a bounded selection. | Useful for a quiesced diagnostic snapshot; not complete continuous capture. |
| Can we replace `MemoriesBackend`? | That interface covers native memory tool operations, not all phase-one transactions and phase-two filesystem output. | Replacing only it would leave a separate writer. |
| Is the producer appropriate for lifelong shared experience? | Not tested. Its policies prioritize future task usefulness. | Measure selection quality before building a production delivery mechanism. |

## Executed storage diagnostic

[Reproduction script](../research/agent-memory-2026-10-06/pilots/native_producer_storage_probe.py)
extracts the exact SQL from the pinned source and uses its actual memory schema
in an in-memory SQLite database with fictional content:

```sh
python3 research/agent-memory-2026-10-06/pilots/native_producer_storage_probe.py \
  --codex-repo /path/to/codex-with-the-pinned-commit
```

Five assertions passed: newer results replace earlier content; the **same source
timestamp can replace different content**; older timestamps are ignored;
no-output deletes the current row; retention deletes an old unselected row.
A reader that polls after these transitions cannot reconstruct lost intermediate
outputs. A timestamp cursor alone is insufficient to identify immutable events.

This executes upstream SQL, not the Rust worker or proposed adapter. There were
zero inference calls and no real memory/session reads. The runtime source SHA256
was `23a7930fae58616026e3b734aa082ea9dd810bfff4a8a4f44c09f8fb6bd75f1d`;
the migration SHA256 was
`5cf9a18faec0a71aae5c42d17fda97d2fc8ea018fde4729ab5e782ed44c6b706`.

## Smallest credible reliable adapter, if quality justifies it

1. Add an opt-in extraction-only mode, with no change to stock defaults. Reuse
   actual native source eligibility, sanitization, model invocation and leases.
   Do not run a second canonical consolidator beside HMK in this mode.
2. At the accepted native extraction transaction, persist an immutable candidate
   envelope in the same SQLite transaction. Include producer identity/version,
   memory schema version, stable sequence/event identity, source revision/hash,
   exact generated output and enough authorized source evidence to assess it.
   A path to a later-deleted rollout is not evidence preservation. Actual retained
   input scope and any truncation must be explicit. A failed or stale commit must
   not create a fictitious successful candidate.
3. Expose a versioned read/ack interface or explicit export command over that
   queue. Delivery can be at least once; reuse HMK `CaptureLedger` for idempotent
   intake and pending decisions. Acknowledge only after a durable receiving
   receipt. Preserve unacknowledged output across producer restart/pruning, with
   explicit storage limits and backpressure. A transient notification alone is
   insufficient.
4. Use existing selection/correction/consolidation APIs for HMK. Keep generated
   artifacts separate from selected autobiographical records. No-output and
   retention are producer lifecycle events, **not evidence that a lived event
   was retracted**. A correction needs its own attributed support.
5. Retain HMK recall through the already adopted MCP route. Check recalled source
   identifiers and actual new evidence so a retrieved memory is not promoted as
   another independent experience. A meaningful later revisit remains distinct.

This is a medium integration across native producer configuration, state/schema,
delivery API and an HMK consumer. It is not a one-line hook. Maintaining a fork
and native version adapters has a real cost; a generic upstreamable envelope is
preferable to embedding HMK-specific policy inside Codex. There is no estimate of
implementation time or upstream acceptance yet. Do not build the full queue
before the small quality gate below.

## First implementation goal: scope and exits

Use a separate fictional Codex home and explicit foreground control. Preserve
the live cohort setup. Reuse previous receiving/capture evidence; do not repeat
valid consolidation or broad provider comparisons.

First obtain real native extraction of selected fictional sessions containing:
a significant encounter with an interesting unadopted proposal; an unsuccessful
communication whose tool result contradicts an optimistic assistant statement;
a later correction; and previously retrieved HMK content alongside genuinely new
experience. Keep the assessment rubric outside receiver context. Inspect the
actual eligible input and any loss before judging output. Select a version
explicitly; V1 and V2 have different contracts. Native phase-one effort is low
in the inspected release; verify actual availability before choosing Sol 6.1.

Record retained meaning, lost meaning, invented claims, provenance, input scope,
calls, latency and actual known/unknown costs. These tests ask whether the native
producer contributes enough to justify its adapter, not whether a record exists.

If useful, implement the smallest versioned extraction delivery into existing
HMK APIs and qualify replay, producer/consumer interruption, correction,
no-output, retention, source loss and feedback prevention. Native temporary state
may remain, but durable canonical selection stays with HMK under existing Matrix
authority. Prove subsequent recall from HMK without the source sessions.

If the producer loses required experience, identify whether a bounded change to
its extraction contract can resolve it. If not, stop that route with evidence
and recommend a portable HMK-owned producer over authorized harness evidence.
Do not build a reliable transport for semantically inadequate output or declare
an incomplete learning cycle successful. Publishing this diagnosis does not
create a native goal, enable production learning or install hooks/timers.
