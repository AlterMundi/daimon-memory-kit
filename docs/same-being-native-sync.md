# Selected same-being native-memory exchange

Development component of Matrix#376. The complete integration and real Legion
acceptance are unfinished. Do not select this branch as a production replacement
as an implicit production update. The native-memory component is implemented;
the cross-component integration and actual receiving adoption remain pending.

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
The receiver must first have the supported native revision schema. Upgrade an
older receiver through its owning native migration, reusing the parent's verified
pre-write checkpoint; retain original rows and the pending operation. Exporting
an older pool successfully does not establish its readiness to receive writes.
A return to the original pool reuses its native record. Unrelated additions,
access counters and queries do not require stopping consumers or replaying work.
An untouched mirror accepts an explicitly linked source correction through the
native revision API; local edits remain variants rather than being overwritten.

Historical text is preserved exactly in both the receiving record and its
attributed original. The native `add_text` and `update_chapter` APIs offer explicit
`preserve_text=True` for this purpose, including empty explicit summaries,
whitespace and line endings. Ordinary calls retain their existing normalization.
The importer requests this capability only when necessary, refuses unsupported
APIs before writing, and verifies the received raw text and summary. The option
does not bypass projection ownership, content scanning, embedding restrictions,
revision history, FTS or the transaction. Existing packet hashes are unchanged.

Source revisions are retained once as content-addressed JSON. Packets carry exact
SHA-256/byte references and only missing selected content; closure is checked
before canonical effects or a new backup checkpoint. A missing or changed blob
retains the selection instead of importing incomplete history. The read-only
`inventory` command lists known origin/content hashes. These mean transport
knowledge, not current adoption: `status` still checks actual owned effects.

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

## Existing unsigned native-sync imports

A caller may select its retained `compaii.private-native-sync/v1` provenance
sidecar through `--legacy-provenance` and `--legacy-provenance-sha256`. It must
be an owner-private regular file with the exact selected byte hash. This is a
read-only compatibility adapter, not a new shared authority or a peer-selected
local path. The old origin hash is verified using its original pool lineage,
chapter ID and complete original row.

If the canonical native owner's `pool_lineage` differs from the local receiving
namespace recorded by that sidecar, select the latter explicitly with
`--legacy-receiving-lineage` (or `Legacy`/`load`'s `receiving_lineage` keyword).
The selected namespace must exist in its retained receiving bindings. It only
chooses local historical lookups; canonical native ownership and original source
labels/hashes stay unchanged. Omission retains the existing behavior. Never
guess the local namespace from a sidecar containing several pools. A mismatch
can otherwise hide unchanged prior representations and create duplicate variants.

An unchanged old import exports its preserved original, not the generated
retrieval copy. The original pool lineage remains known; missing historical
body, embodiment and incarnation stay null. Original bytes use the same
content-addressed store. A receiving sidecar can reuse an unchanged old native
representation and restore its original summary/metadata through the current
native revision API, preserving receiving UID and history. A locally edited copy
remains a distinct variant, with the original retained through native `history`.
Ambiguous aliases never pick a winner by time. Missing provenance refuses a
generated-row export rather than inventing exporting-body authorship.

The command set is `export`, `inventory`, `apply` and read-only `status`. A parent
operation supplies the receiving binding and stable page operation IDs. It may
pass the receiver inventory's `origins` and `content` arrays as `--known` and
`--known-content` JSON files on later exports. Packet and inventory files are
private, exclusively created outputs. CLI stdout contains summaries/receipts,
not raw memory. No command completes the parent's checkpoint implicitly.

## Remaining integration

- Use the maintained Cluster same-being integration operator to connect exact
  references, local decisions and effect receipts with the selective Skills
  installer. Native event sync alone does not apply this content.
- Qualify the exact receiving package, real source/Legion incorporation and
  compatible rollback. Published source and a prepared binding do not prove
  receiving adoption or actual harness consumption.

Packets are bounded at sixteen MiB and at most128records per page. An oversized
selection is an explicit unresolved input, never an excuse to omit source
history or restore a whole database. Live package placement, selected bindings,
checkpoint lifecycle and receiving evidence belong to the owning private cockpit.
