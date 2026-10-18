# Pre-write snapshot storage and retention

DMK #19 adds optional `snapshots` configuration to the existing finite worker
profile. No scheduler, source selection, model or memory owner changes. Without
this field, the legacy pre-write snapshot behavior remains available.

```json
"snapshots": {
  "directory": "/selected-data-volume/private-dmk-snapshots",
  "retention_scope": "database",
  "max_count": 6,
  "max_bytes": 1073741824,
  "min_free_bytes": 21474836480,
  "keep_latest": 2,
  "timeout_seconds": 300,
  "pins": []
}
```

Select an existing data filesystem and its actual headroom policy.
`timeout_seconds` is optional (legacy default: 30); select a measured copy budget
for the receiving host. A timed-out partial stays retained and cannot be mistaken
for a verified checkpoint. Raising the budget resumes pending work without
repeating completed model calls. The directory
is explicit, owner-bound and separate from producer control state. It must not
contain symlink components. Multiple owners cannot share one checkpoint directory.
The private manifest remains in producer state and records exact paths, byte and
schema hashes, operation names and retained/retired state. Keep it with the journals.
The live canonical database and signed/runtime paths do not move. Optional
`retained_files` places verified compact historical artifacts inside the same byte
budget; see [resource lifecycle](resource-lifecycle.md#compact-legacy-history-within-the-budget).

## Retention contract

The bounded working set covers `batch`, `embedding`, `organization` and
`embedding-organization` pre-write checkpoints. Limits count logical bytes, not
compressed physical allocation. With explicit `retention_scope: database`,
`keep_latest` protects the newest recovery points across the entire database,
ordered by snapshot creation time rather than unrelated stream sequence numbers.
Completed older copies are retired on maintenance even before reaching the hard
count/byte limits. Historical migrated checkpoints participate in this same
budget and retention; they do not form an indefinitely exempt archive.
The example keeps two recent points and leaves room for pending operations;
actual count/byte/headroom limits must fit the receiving database and workload.
Without this field (or with `class`), legacy per-class retention and separate
archive behavior remain unchanged for compatibility.
`pins` lists exact checkpoint filenames required by actual outstanding rollbacks.
Review those references before adopting a policy; unknown requirements remain
protected, not inferred obsolete from age.

Retirement requires all of the following:

- The checkpoint is registered under the selected retention policy, with unchanged
  verified bytes/schema.
- Its canonical owner-bound capture/organization event is applied or omitted.
- Both processing and corresponding embedding cursors have passed that operation.
- It is outside the retained recent checkpoints and explicit rollback pins.
- Retained recovery checkpoints match their previously verified byte hashes before
  deletion. Their integrity/schema proof is reusable only for those exact bytes;
  every newly created snapshot and restored database receives full SQLite checks.

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
Migration registers existing snapshots with their original paths, hashes and
compatibility links. Database-wide policy makes those registered snapshots
eligible for retirement only after their operation is proven complete, including
its indexing cursor, and they are outside recent recovery points and explicit
pins. A missing or redirected compatibility link blocks deletion. Interrupted
retirement finishes removing that same copy and its link, retaining its manifest
receipt. Without database-wide policy, imports remain a fixed historical archive;
that compatibility mode is not a complete production retention policy. Regular old files are copied to data storage, checked for
exact bytes/schema/integrity and atomically replaced by compatibility symlinks.
Already-relocated symlinks on that filesystem retain their destinations. Repeated
migration verifies receipts; interruption does not create an accepted partial copy.
All retained archive bytes count under database-wide policy. Under legacy
class policy, archive bytes are separate from `max_bytes` but still consume
filesystem space. No policy removes unknown files or unique source history.

Restore always writes to a new destination, verifies exact bytes, schema, SQLite
integrity and foreign keys, and refuses to overwrite an existing file. It never
replaces a live database. Any later canonical restore still requires its owning
recovery procedure and preservation of intervening writes. Keep the archive,
manifest and source journals within their existing private access boundary.

## Adoption and rollback

Inspect current jobs, authoritative ledgers, storage placement and actual rollback
references before migration or enabling database-wide retention. Register any
checkpoint needed by an outstanding rollback in `pins`; do not infer that a
historical reference is an unresolved rollback merely because its filename is
mentioned in a completed test report. Run `maintain` explicitly after policy
adoption; subsequent worker preflights continue the same retention automatically. Preserve configuration and use the supported explicit
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

## Runtime packaging

Install the executable runtime, not the repository's retained research corpus.
A deployment archive can be built from the published commit with `git archive`,
selecting `scripts`, `schemas`, `templates`, `policies`, `vectors`, `docs`,
`LICENSE`, `README.md`, `.env.template`, `.env.example`,
`.continuity-plugin-version`, `bootstrap-docs.example.json`, and the four
`requirements*.txt` files. Keep research, fixtures and test outputs in their owning
development/evidence storage. Record the commit and selected paths in the private
installation receipt; remove transport archives after installation verification.
Do not modify an already selected immutable release to trim it. Select a separate
qualified runtime package and retire the old package only after checking live,
pending-writer and rollback references.
