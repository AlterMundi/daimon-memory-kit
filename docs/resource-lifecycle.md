# Production and development resource lifecycle

DMK keeps durable memory and its provenance. Full working copies, pre-write
recovery points and executable releases are not additional autobiographical
history. Give each resource its owning lifecycle rather than applying recursive
age-based deletion to a being's state.

## Worker recovery points

Use the explicit database-wide policy in [snapshot retention](snapshot-retention.md).
Keep two recent verified recovery points, plus checkpoints protecting pending,
failed, unindexed or explicitly pinned operations. Include migrated copies in the
same limits. Capacity blocks work visibly before new model calls; solve the
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

A stable operation ID makes an interrupted begin resumable. Keep the returned
snapshot and receipt. Perform the authorized write using the existing native API,
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
