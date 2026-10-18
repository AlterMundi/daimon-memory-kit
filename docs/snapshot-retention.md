# Pre-write snapshot storage and retention

DMK #19 adds optional `snapshots` configuration to the existing finite worker
profile. No scheduler, source selection, model or memory owner changes. Without
this field, the legacy pre-write snapshot behavior remains available.

```json
"snapshots": {
  "directory": "/selected-data-volume/private-dmk-snapshots",
  "max_count": 12,
  "max_bytes": 2147483648,
  "min_free_bytes": 21474836480,
  "keep_latest": 2,
  "pins": []
}
```

Select an existing data filesystem and its actual headroom policy. The directory
is explicit, owner-bound and separate from producer control state. It must not
contain symlink components. Multiple owners cannot share one checkpoint directory.
The private manifest remains in producer state and records exact paths, byte and
schema hashes, operation names and retained/retired state. Keep it with the journals.
The live canonical database and signed/runtime paths do not move.

## Retention contract

The bounded working set covers `batch`, `embedding`, `organization` and
`embedding-organization` pre-write checkpoints. Limits count logical bytes, not
compressed physical allocation. `keep_latest` protects the newest checkpoints
**per class**; leave room in `max_count` for those classes and pending work.
`pins` lists exact checkpoint filenames required by actual outstanding rollbacks.
Review those references before adopting a policy; unknown requirements remain
protected, not inferred obsolete from age.

Retirement requires all of the following:

- The checkpoint is registered as managed, with unchanged verified bytes/schema.
- Its canonical owner-bound capture/organization event is applied or omitted.
- Both processing and corresponding embedding cursors have passed that operation.
- It is outside the retained recent checkpoints and explicit rollback pins.
- Retained recovery checkpoints pass verification before deletion.

Pending, failed, uncertain, unindexed and creating operations cannot be retired.
Each retirement records intent before unlinking and a terminal receipt afterward;
interruption resumes that same operation. Unknown files are not swept. Partial
SQLite snapshots are retained and consume the working-set budget; they require
explicit inspection rather than recursive cache cleanup. Small provenance and
retirement records remain even after a completed snapshot is removed.

Before selection/review calls, capacity is checked against count, bytes and free
headroom. Pre-write creation still occurs before canonical or embedding mutation.
An exhausted protected set raises `SnapshotCapacityError`; the worker records
`snapshot_capacity_exceeded` with pending phase work. The existing Alerts observer
classifies this as blocked processing, using its established recovery route.
Other I/O/verification errors remain visible phase failures. Completed model
responses and frozen jobs remain resumable; solving storage never authorizes
repeating an uncertain provider call.

Limits are enforced on subsequent pre-write work through the existing finite
worker, or explicitly with `snapshotctl.py maintain`. An unexpectedly larger
snapshot or retained partial can block the operation; it is preserved, never
truncated to fit. This does not guarantee space against other host writers.

## Existing archive, migration and restore

Use the installed owning interpreter and release:

```sh
python scripts/snapshotctl.py migrate --profile /private/worker.json
python scripts/snapshotctl.py maintain --profile /private/worker.json
python scripts/snapshotctl.py restore --profile /private/worker.json \
  --name batch-12-before.sqlite --destination /selected-data-volume/recovery.sqlite
```

These commands hold the existing worker and producer locks and dispatch no models.
Migration preserves existing snapshots as an explicit **fixed historical archive**,
separate from the bounded future working set. It does not automatically expire
old recovery evidence. Regular old files are copied to data storage, checked for
exact bytes/schema/integrity and atomically replaced by compatibility symlinks.
Already-relocated symlinks on that filesystem retain their destinations. Repeated
migration verifies receipts; interruption does not create an accepted partial copy.
The archive consumes filesystem space and is included in free-space planning;
`max_bytes` is the future working-set limit, not a claim that the historical archive
has disappeared or been compressed to that size.

Restore always writes to a new destination, verifies exact bytes, schema, SQLite
integrity and foreign keys, and refuses to overwrite an existing file. It never
replaces a live database. Any later canonical restore still requires its owning
recovery procedure and preservation of intervening writes. Keep the archive,
manifest and source journals within their existing private access boundary.

## Adoption and rollback

Inspect current jobs, authoritative ledgers, storage placement and actual rollback
references before migration. Preserve configuration and use the supported explicit
pending-job upgrade procedure if a code fingerprint changes; never silently reset
frozen navigation, completed calls or staged events. Select the new immutable
release and profile together under the existing worker lock. Reuse the existing
cadence; do not launch paid processing solely to test placement.

Rollback restores configuration references, not an old database over later work.
After new pending work exists, finish it with its selected writer or reconcile
through that writer's supported upgrade procedure before changing code. Retain
new snapshots and their manifest. Old binaries do not understand the new profile
field; removing it re-enables legacy root placement and is not a permanent storage
solution. Recovery can use the retained release's `snapshotctl.py` independently
of the active worker.

Qualification includes all four classes, exact restore, retained history migration,
partial publication and interrupted retirement, corrupt/missing recovery files,
count/byte limits, protected work, visible pre-model capacity failure and uncertain
commit replay without another generation call. Receiving adoption evidence is
recorded in #19; fictitious tests alone do not assert live adoption.
