# Selected same-being native-memory exchange

Development component of Matrix#376. The complete integration and real Legion
acceptance are unfinished. Do not select this branch as a production replacement
until the retained-content closure and legacy-provenance adapters are complete.

`scripts/same_being_sync.py` uses the current initialized native API rather than
requiring an old Git checkout, a whole-database restore or stopped harnesses.
The receiving caller selects its existing owner/pool binding; peer text cannot
select another database, binding, policy or executable. Bindings and packets are
private inputs, not signed Matrix evidence or autobiographical authority.

A finite export reads a consistent SQLite page without changing source rows.
Native provenance, original fields and available revisions stay attributed.
Protected Matrix projections remain with their owning signed adapter. A packet
records the body/incarnation that observed export separately from the unknown
historical incarnation of an unsigned native record; a new observation never
re-authors old experience. Existing metadata attribution remains unchanged.

The native write API composes under one bounded SQLite transaction. Canonical
retrieval changes and the operation receipt commit together. An interrupted
transaction rolls back; an uncertain return reconciles the original operation.
A return to the original pool reuses its native record. Unrelated additions,
access counters and queries do not require stopping consumers or replaying work.
An untouched mirror accepts an explicitly linked source correction through the
native revision API; local edits remain variants rather than being overwritten.

Original source versions are available through the ordinary native `history`
reader, labelled with their unsigned source provenance and original UID/revision.
They are never renumbered as receiving edits or signed Matrix events. Native
receiving revisions remain independently available. Source kinds that disable
embedding retain that restriction, including a source-kind-only correction;
existing vectors are removed when that policy becomes more restrictive.

Links wait for their exact endpoints, retain conflicts and use the native API.
A repeated receipt verifies current owned records and applied links; it refuses
changed effects instead of silently recreating them. Historical result counts
and current link reconciliation are separate. Original packets, accepted
variants and source history survive code rollback; rollback never rewinds the
whole memory database or current signed authority.

The apply CLI joins one existing `backupctl` checkpoint for the parent
integration (`--backup-config`, `--checkpoint-operation`), not a full new snapshot
per record or page. The parent completes it only after all selected effects,
preserved history and retrieval are verified. A status/read does not dispatch
recovery or complete the checkpoint. No models, providers, hooks, inbox attention,
service controls or automatic retries are installed.

## Remaining before production use

- Deduplicate retained source revision bytes and carry exact content closure,
  reusing known content across corrected pages; the prototype currently embeds
  full source history in each origin document.
- Connect the existing legacy native-sync provenance sidecar. Generated legacy
  rows currently refuse export instead of acquiring the exporting body's origin.
  Preserve both the original import and subsequent receiving edits.
- Connect exact references, local decisions and effect receipts to the maintained
  Matrix/Weave integration and selective Skills installer under one operation.
- Qualify the exact receiving package, real source/Legion incorporation and
  compatible rollback. The old Legion baseline remains unchanged meanwhile.

Packets are bounded at sixteen MiB and at most128records per page. An oversized
selection is an explicit unresolved input, never an excuse to omit source
history or restore a whole database. Live package placement, selected bindings,
checkpoint lifecycle and receiving evidence belong to the owning private cockpit.
