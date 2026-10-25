# Production and development resource lifecycle

DMK keeps durable memory and its provenance. Full working copies, pre-write
recovery points and executable releases are not additional autobiographical
history. Give each resource its owning lifecycle rather than applying recursive
age-based deletion to a being's state.

## Worker recovery points

Use the explicit database-wide policy in [snapshot retention](snapshot-retention.md).
Keep two recent verified recovery points, plus checkpoints protecting pending,
failed, unindexed or explicitly pinned operations. Include migrated copies in the
same limits. For growing production stores, use the documented `database_copies`
budget with two retained points plus creation margin; a fixed byte ceiling alone
will eventually strand rotation. Capacity blocks work visibly before new model calls; solve the
storage condition and resume the existing journal instead of resetting a job.

## Manual pre-write operations

Use `backupctl.py` through the receiving DMK wrapper. Its private profile defaults
to `~/.config/daimon-memory-kit/backup.json`. Configure an existing canonical
`database` and a dedicated `snapshots` policy on the receiving data filesystem.
The snapshots object has the same fields as the worker example, with
`retention_scope: database`, `keep_latest: 2`, measured count/byte/headroom limits
and explicit rollback `pins`. It uses its own owner-bound directory; never point
it at the worker's store or another being's backups. The CLI checks the receiving
`HMK_DB_PATH` binding when present.

Before changing memory:

```sh
dmk backupctl.py begin --operation correction-20261018-unique \
  --reason 'Before the authorized correction'
```

Retry an interrupted begin with the same operation ID **and the original reason**;
the journal rejects changed reasons. An interruption can leave a protected
`.partial-*` candidate as well as a reserved checkpoint. Retrying does not reclaim
that candidate and can fail the capacity check. Inspect the operation journal,
manifest, candidate and actual writer state before retrying; repeated polling or
new operation IDs do not recover it. Preserve failed candidates until their
recovery or explicit disposition is verified. A process waiting for I/O alone
does not establish the cause of the delay. Continue the authorized memory task
after repairing the checkpoint path; reporting the error is not completion.
Keep the returned snapshot and receipt. Perform the authorized write using the existing native API,
then verify the intended result and preserved history. Only afterward release the
operation's protection:

```sh
dmk backupctl.py complete --operation correction-20261018-unique \
  --reason 'Correction and preserved history verified'
```

Completion is explicit, not inferred from age, a session ending or a model
response. An unresolved operation remains protected even if the capacity limit
blocks another begin. A completed operation ID cannot be reused for a new write.
The snapshot journal retains its reason, hashes and retirement receipts. Keep a
concrete outstanding rollback pinned even after the operation is marked complete.

Restore into a new file, never over current memory:

```sh
dmk backupctl.py restore --operation correction-20261018-unique \
  --destination /selected-data-volume/restored-copy.sqlite
dmk backupctl.py maintain
```

This reuses the worker's byte-verified snapshots, retirement and restore code.
It installs no timer and invokes no models. The curator's begin/complete calls
perform retention; there is no need for a separate housekeeping service.

Old ad hoc backups must be inspected separately before adoption. They have no
completion journal: a filename or old date is insufficient to release a genuine
rollback. Preserve any unique historical material, select verified recovery
points and record retirement of redundant copies. Do not silently enroll
unqualified files as completed operations.

## Captures and development evidence

Captured source revisions, native histories, canonical revision history and
uncertain provider attempts are original evidence, not cache. Keep their existing
ownership and privacy. Do not clear them to make capacity numbers look healthy.
Their eventual compaction must preserve reconstructible bytes and references.

If capture repeatedly fails after an interrupted write, inspect the inbox's
SQLite journal before blaming permissions or the provider. A hot rollback journal
requires SQLite's native write-capable recovery even for a policy SELECT. The
forward-capture policy probe opens an existing inbox with `mode=rw` for that
reason; it must not create a missing inbox. Never delete the journal. For manual
diagnosis, preserve the database and journal together with no active writer,
verify recovery on a copy, then let SQLite recover the original. Recover retained
selected sources through the capture path and resolve their matching supervisor
attempts only after successful capture receipts; database integrity alone does
not establish source coverage. Capture recovery invokes no models.

Run large qualification copies on the data filesystem. At the end of a completed
experiment, retain its inputs or reconstructible source references, implementation
version, outputs, costs and acceptance evidence. Remove proven disposable working
copies and failed qualification partials after recording their disposition; keep
actual pending experiments and rollback dependencies. Never sweep another active
writer's directory. Reuse fixtures and completed evidence instead of creating a
new full corpus for each check. Compact required cold evidence with a verified
restore route; report remaining durable growth separately from overhead.

Runtime packages contain executable code and necessary resources, not research
corpora. Retain active readers/writers, a compatible rollback and code needed to
recover pending journals. Retire other package copies after checking actual
references; published source history remains available. Remove transport bundles
when installation verification finishes. Never trim a selected immutable release
in place.

Installation-specific locations, references and before/after measurements belong
in the private receiving runbook. #23 tracks adoption and residual limitations.

## Compact legacy history within the budget

If old snapshots contain history or source metadata absent from the current
canonical revision history, preserve those original bytes before retiring full
working copies. A private, lossless `tar.zst` capsule can hold the selected cold
files and their metadata, with a manifest of original paths, byte hashes and
sizes. Long-distance Zstandard matching can avoid paying repeatedly for similar
SQLite pages. This is original historical evidence, not an extra online database.

Use a finite source inventory and the data filesystem. Verify every archived
member against its recorded hash, ensure sources did not change, and verify a
selected restoration before removing any source copy. Preserve active rollback
paths separately; retain new or changed files. Leave the manifest/restore pointer
at the old location. Never publish a private capsule or raw memory manifest.

A capsule must not become another quota exemption. The snapshot policy accepts
optional `retained_files`, for example:

```json
"retained_files": [
  {"name": "history.tar.zst", "bytes": 12345, "sha256": "<actual 64-character lowercase SHA256>"}
]
```

Each name identifies a regular file directly inside the selected snapshot
storage directory. Register the actual measured size and hash, including a
separate manifest when it is retained there. These files count toward the same
`max_bytes` as snapshots and partials. Missing, modified or redirected files
block maintenance; they are never silently expired. `retained_file_bytes` reports
their contribution separately. The snapshot count limit continues to apply to
recovery checkpoints. History preservation is bounded by actual compressed bytes,
not hidden in an unlimited archive directory. New manual operations use the
normal begin/complete rotation instead of appending full copies to this capsule.

Standard restoration uses `zstd -dc` and `tar` into a new private directory on
the data volume, selecting the manifest's exact relative member name. Check its
SHA256 and SQLite integrity before using it. Do not extract over a live pool,
follow untrusted archive links, or replace later memory with an older database.

For development evidence, use a separate owning data directory and an explicit
compressed-byte budget (the receiving qualification capsule uses 1 GiB). Keep a
manifest and restore pointer with the original experiment; source/model outputs
remain evidence, not a new memory input. A capsule over its budget blocks source
retirement until its owner selects a suitable preservation plan. Do not solve
capacity by dropping evidence or by duplicating it into runtime installations.

## Completed malformed selection responses

Selection uses the configured native reviewer once when a completed,
untruncated, tool-free generation response contains invalid JSON. The reviewer
receives the original selected evidence and the malformed output, which is not
treated as evidence. Both immutable dispatch receipts and separate usage records
are retained. Reinvocation reuses the review receipt; a failed or malformed review
remains visibly pending. Transport failures, uncertain requests, truncated output
and tool execution are not automatically retried by this path.

The repaired response still passes ordinary navigation, schema and evidence
validation before any canonical write. For an existing unresolved operation on
an older model policy, use `repair_selection_response.py` with its original
profile/request and an explicit reason, then resume normal validation. Do not
overwrite the retained model-policy receipt to force an upgrade through pending
work. Upgrade future model dispatch only after reconciling that work.
