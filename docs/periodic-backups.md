# Routine memory protection and critical recovery points

Ordinary memory writes use the supported atomic DMK APIs, retained originals and
native revision history. They do not require a full-database copy, full-file hash
or integrity scan first. Routine embedding/index updates follow the same rule.
Do not call `backupctl begin` for every ordinary memory update.

The receiving policy explicitly opts into one shared periodic baseline pool per
canonical database. The existing finite worker refreshes it after processing,
without another scheduler or model call. Initial production selection is a24-hour
interval when changed and two retained baselines; an unchanged database receives
an audit instead of another copy. Two is a retention target, not a claim that a
newly initialized pool already contains two snapshots. The old defaults remain
compatible for profiles without this field.

```json
"routine_backup": {
  "directory": "/selected-data-volume/private-periodic-baselines",
  "subject": "<receiving-being-reference>",
  "interval_seconds": 86400
}
```

Add this inside the existing `snapshots` object, keeping its existing critical
checkpoint directory and policy. Manual and worker profiles for the same
explicitly authorized database select this same periodic directory/subject.
Its owner-bound manifest prevents another database/being from reusing it. No
physical placement or being authority is inferred from a similar filename.

## Actual protection and failure semantics

SQLite transactions protect local commit atomicity. Native history supports the
corrections actually implemented by its APIs. Neither the live WAL nor history
inside the same file is an independent disaster backup. This delivery does not
claim universal delta replay or zero data loss after storage/database loss.
Recovery from a baseline reaches its snapshot state; later changes require a
separately qualified source/replay route. At a healthy daily cadence, exposure is
approximately the changes since the last daily baseline; missed invocations and
backup failures increase it. It is not a hard24-hour guarantee during an outage.
External source resources and whole-body configuration need their owning backup
contract; a SQLite baseline is not a complete being archive.

The normal write path is independent of the space reserve for a full backup. A
failed refresh becomes a durable `backup` incident through the existing producer
outbox/Alerts observer. Worker receipts distinguish completed memory/indexing from
failed backup protection. An already committed write must not be repeated because
its subsequent backup failed. Real database/journal space or commit failures still
fail the write; do not report such a write as saved.

Periodic creation enforces physical headroom, count and byte limits. A failed
attempt is retained; automatic invocations do not start repeated replacement
copies. Restore never overwrites a live database. Original operation checkpoints,
manual journals, rollback pins and captured sources remain separate and protected.

## Operate and recover

Use the selected worker runtime and existing profile. These commands invoke no
model and perform no memory ingestion:

```sh
python scripts/periodic_backups.py status --profile <worker-profile>
python scripts/periodic_backups.py refresh --profile <worker-profile>
python scripts/periodic_backups.py refresh --recover --profile <worker-profile>
python scripts/periodic_backups.py restore --profile <worker-profile> \
  --name <exact-baseline-name> --destination <new-private-file>
```

`--recover` is an explicit continuation after inspecting the retained attempt. A
published verified candidate is reused; an incomplete unpublished partial is not
a valid backup and needs explicit inspection/disposition before retry. It is not
silently removed or repeatedly recopied. Changed/missing baselines are detected.
Explicit recovery can quarantine damaged points without deleting their bytes;
quarantined bytes continue to consume the budget. Keep those receipts and address
the actual source/storage failure. Refresh with a worker profile publishes backup
failure/resolution through its existing outbox; a manual-only profile reports its
result locally. Service acceptance and human notification are separate evidence.

For schema migrations, destructive bulk transformations, corruption repair or a
concrete non-replayable operation, retain a dedicated point:

```sh
dmk backupctl.py begin --critical --operation <stable-id> --reason '<reason>'
# Perform the authorized operation; verify originals, history and outcome.
dmk backupctl.py complete --operation <stable-id> --reason '<verified outcome>'
```

Repeat critical `begin` with the same reason and `--critical`; completion retains
its existing explicit lifecycle. Ordinary `begin/complete` remains a compatibility
route for older callers and reports `recovery_scope=periodic_database`, without
pretending that it made a pre-operation restore point. Existing pending manual
operations keep their original snapshot contract after adoption.

## Adoption and rollback

Install the qualified executable modules before enabling the field. Preserve
existing private profiles/selectors and all pending work. The change leaves the
producer/model implementation fingerprints intact; do not reset navigation or
resume old experiments to exercise the backup path. Verify a real baseline and
restore, unchanged canonical records, the ordinary/critical routing and observer
publication on each current receiver. Eko is native on MEDUSA; its disabled source
container is not an update target.

Keep obsolete per-write guidance out of actually loaded instructions and shared
skills. Roll controls back together using a compatible retained implementation;
never restore an old canonical database over newer writes. Legacy operation-bound
points and quarantined/failed artifacts must retain their own proven disposition,
not be swept because a new periodic pool exists.
