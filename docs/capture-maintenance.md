# Capture maintenance: retained work, title conflicts and opaque sources

The October 17 receiving inspection reproduced Eko's write failure on a verified
isolated canonical snapshot with networking disabled: an add reused an existing
book title. Selection shape was valid, but the transactional writer correctly
refused a duplicate. The failed source event and all subsequent input survived.

Selection now checks actual add-title collisions before admitting a decision and
returns navigation handles for the existing originals. The selector must read
and reconcile them; it must not rename a duplicate to evade the guard. The writer
still checks inside its transaction for concurrent races. A typed failed collision
can refresh evidence with bounded reconciliation; originals and prior attempts
remain. Repeated invalid responses stay visibly pending.

For an older retained generic failure, the explicit Python API
`portable_producer.reconcile_failed_title(memory, inbox, state_dir)` verifies the
established owner, frozen inputs, restored source hashes, failed ledger event and
matching decision, and demonstrates a current title collision. It archives the
exact old job and prepares reconciliation of that same event. It advances no
cursor and invokes no model. Pending/uncertain and terminal events are refused.
Use the installed release and owner-bound loader, after a verified canonical and
inbox snapshot. Configuration rollback must retain later memories, source input,
failed attempts and current producer state; never restore an old inbox over them.
A code rollback cannot silently reinterpret a prepared job's fingerprint.

Oliva's earlier read-only SQLite error no longer reproduced on October 17: its
normal SQLite writer had recovered the rollback journal before this inspection.
Both consistent snapshots passed integrity and foreign-key checks. No corruption
or source loss was established and no stale database was restored. Its independent
processing stall came from native image-containing messages and agent messages,
including mixed plaintext/encrypted parts, unsupported by the old text normalizer.

The normalizer now preserves known native forms. Readable text remains attributed;
opaque image/audio/encrypted parts become explicit uninterpreted markers with
source record, content index and hash. Exact original parts remain in retained
source bytes and, when selected, their learning artifact. External references do
not guarantee external content availability. No image/audio interpretation or
ciphertext decryption is claimed. A dependent selection must retain uncertainty
or defer if it requires inaccessible meaning. Agent author/recipient labels are
native attribution, never signed being identity or tool-success evidence. Unknown
forms still stop processing visibly; original source bytes remain intact.

Tests cover pre-write conflicts, failed-event recovery and replay, refusal to reset
uncertain work, opaque-source attribution/preservation and unknown-type refusal.
Receiving recovery, positive learning/recall and Alerts resolution must be recorded
separately after actual execution. Passing these tests alone does not close them.

## Explicit malformed-response repair

A real Oliva receiving call completed with `finish_reason=stop`, but returned DSML
markup rather than the required JSON. Its one explicit fresh semantic selection
also returned an invalid response. A completed response is not a transport failure;
transport retry is intentionally refused. Neither markup nor model text is executed.

`repair_selection_response.py --profile ... --request ... --reason ...` verifies the
current frozen job, owner, original source hashes and exact completed malformed
response. It invokes the already-configured native OpenAI Codex review adapter once
on those same selected messages plus the invalid response, without tools or native
memory. The native adapter retains its qualified review transport label; the outer
receipt identifies this as selection-response repair, not consolidation acceptance.

This is an explicit operator repair, not automatic fallback for all future calls.
It preserves the original request, response, authorization and job, stores a separate
repair receipt, and resumes normal schema/source validation and navigation. Repeated
invocation reuses the retained repair. Valid JSON, uncertain/unfinished dispatches,
observed tool execution and foreign requests are refused. Failure stays pending;
no unbounded prompt/provider retries or silent provider substitution is authorized.

## Interrupted pre-write snapshots

A subsequent live batch completed model selection but timed out during its SQLite
pre-write snapshot, before staging a canonical event. The old helper created the
final backup filename before completing or verifying it; a later invocation could
mistake that partial file for the required checkpoint. New snapshots retain any
failed/interrupted candidate under a unique `.partial-` name and publish the final
name only after integrity/foreign-key verification and durable file flush, using a
non-overwriting atomic link. Existing recovery files and concurrent winners are
never replaced. Timeout does not authorize retrying an already-completed model call.

For a retained failure from the older helper, preserve the candidate and journal
companions, inspect it and the unchanged current job, and explicitly create a fresh
verified checkpoint before resuming. The helper's existing timeout argument can
bound that operator recovery independently of model/selection budgets. Never delete
or silently accept an uncertain old backup merely because its pathname exists.

## Halted source-selection titles

A valid JSON selection can exhaust its ordinary corrections because a proposed
recognition title is not a literal phrase in that record's selected sources.
Current validation identifies the record index and explains the exact substring
requirement. Inspect the retained selection; do not clear its halt or keep
invoking the generator. Transport retry does not repair a completed decision.

For this specific failure, use the installed worker runtime and its original
profile/model implementation:

```
python scripts/repair_selection_titles.py --profile <receiving-profile> \
  --sequence <current-batch> --reason 'Repair unsupported recognition titles only'
```

This explicit operation uses the configured native reviewer once, without tools
or native memory. It verifies the owner, unchanged source revisions, producer
implementation and current complete canonical evidence. Only unsupported titles
may change; sources, record count/order, valid titles, decisions and links must
remain identical. Dropping work or changing interpretation fails validation.
The complete repaired proposal must pass the ordinary evidence contract and
canonical-title collision check. Original navigation, halt, proposal, sources and
review receipts remain retained, including unsuccessful results and costs.

The command does not write canonical memory or advance the source cursor. Resume
the same producer explicitly; it validates and admits the retained proposal using
the normal checkpoint, event and indexing path. Replaying the command reuses the
same review result. A rejected review remains pending without another model call;
uncertain dispatches follow the existing no-implicit-retry transport contract.
Other semantic failures require their own diagnosis; this is not a general
permission to rewrite a failed selection. Record real admission and alert
resolution separately from successful title repair.

For a pending job pinned to an older producer, compose only the new repair command
with that original runtime. Changing validator/navigation source changes its code
identity; adopt the clearer validator diagnostic after the pending job completes,
not by overwriting its code hash. Code rollback preserves newer journals and
canonical memory.
