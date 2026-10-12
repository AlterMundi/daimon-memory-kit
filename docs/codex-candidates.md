# Native extraction candidate intake (experimental)

This contract separates candidate preservation from selected memory. The native
producer patch is under qualification; stock Codex has no such outbox. The live
CompAII/Eko/Oliva installations do not enable it. See the
[V1/V2 quality gate](../research/agent-memory-2026-10-06/pilots/2026-10-12-native-producer-qualification.md)
and [producer diagnosis](codex-native-producer-diagnostic.md).

## Native side

The experimental fork adds `memories.extraction_only=true`, default false. With
startup processing and the memories feature enabled, this mode reuses native
eligibility, model invocation and source filtering but skips native workspace
creation, pruning and consolidation. The qualified extraction contract is V2;
consumption remains disabled. Generation eligibility is a separate setting.
This is a proposed opt-in producer, not an extraction-complete lifecycle hook.

An accepted owned job commits an immutable `codex.extraction-candidate/v1`
envelope and its completion watermark in one transaction. Native
`stage1_outputs` and consolidation jobs are not changed. A candidate contains
source rollout text, actual submitted input messages/instructions/schema, exact
generated JSON, parsed output, model/version/effort and available token usage.
Native output truncation remains visible beside the unmodified generated JSON.
Malformed source items or a source changed during extraction cause failure rather
than a silently partial committed candidate. This initial source-preservation
path accepts UTF-8 JSONL; compressed rollouts are not yet qualified.

The versioned memory database contains:

- `memory_extraction_stream`: stable stream UUID in singleton row 1.
- `memory_extraction_events`: monotonically increasing sequence, immutable event
  UUID, thread ID, source watermark, envelope JSON and creation time. The only
  mutable delivery field is `acknowledged_receipt`.

The V2 database name is `memories_v2_1.sqlite`, not `memories_2.sqlite`. An isolated
home and selected eligible sources are required during qualification. A 256 MiB
candidate-envelope cap stops new commits instead of pruning evidence. Receipt
acknowledgement does not delete originals or reclaim that capacity; owner archive
management is outside this first delivery. Full original source evidence can
contain private material: it stays in the authorized local stores and must not
be published with public experiment results.

## Receiving side

Run explicitly against the receiving pool binding and an authorized native
producer database:

```sh
HMK_AGENT_MEMORY_BASE=/path/to/fictional-canon \
  python scripts/codex_candidates.py \
  --producer-db /path/to/isolated-home/memories_v2_1.sqlite \
  --source-instance fixture:desk --subject fixture:ilex
```

The receiver validates the envelope, creates a verified SQLite backup, stages a
stable event through `CaptureLedger`, and retains exact bytes in existing native
learning artifacts. Only after verifying those artifacts does it acknowledge the
native row. The receipt proves preservation, not truth, novelty, canonical
selection, identity, authority or Matrix admission. The supplied being/body
binding is the caller's responsibility; native text cannot grant it.

Intake is finite: default 32 events, maximum 128 per invocation. Continue with
`--after-sequence N` using the last returned sequence. Start at zero to replay or
restore a receiving copy: acknowledged candidates are still offered and existing
events are idempotent. A receipt for another binding or changed source bytes
fails visibly. Interruption after staging or immediately before acknowledgement
leaves preserved pending work that can be replayed.

Use existing `capturectl.py pending` and `assess` to make a source-qualified
selection. No new automatic selector is installed. Check original tool outcomes,
participants, dates and current-body applicability. Generated candidates remain
generated evidence. Correct existing records by expected revision; keep their
history. Retrieved/projected material is evidence for the earlier episode, not
another independent event. Select only an actual new encounter, attributed report,
correction or meaningful later interpretation. A no-output candidate is a native
producer result, never a retraction of canonical experience.

## Qualification still required

Receiving unit checks cover interrupted delivery, replay, source mutation,
pagination, explicit correction/history and source-free lexical recall. These use
synthetic envelopes and do not substitute for a built native transaction test or
a model-backed end-to-end handoff. Complete those before claiming the bridge is
qualified. Do not activate production, hooks, timers or autonomous attention.
