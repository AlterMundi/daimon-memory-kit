# Explicit HMK-native projections into Codex memory

`scripts/codex_projection.py` builds a selected Codex memory-v1 view from an
existing HMK-native SQLite canon. It uses no model or embedding provider and
changes no native setting. This is a projection primitive, not a complete Codex
memory provider or signed Matrix admission adapter.

## Selection and publication

Select an authorized same-being database and explicit current record revisions.
For example, a fictional selection:

```json
{
  "schema": "hmk.codex-projection.selection/v1",
  "being_ref": "fixture:being:Ilex",
  "body_ref": "fixture:body:voice",
  "records": [{
    "record_uid": "93ebf3c5-a015-4749-889c-659c2e6f8555",
    "revision": 1,
    "applicability": {"kind": "being", "targets": []}
  }],
  "temporary_context": [{
    "key": "checkout",
    "text": "Temporary HarborMesh checkout status.",
    "expires_at": 1791684000,
    "applicability": {"kind": "project", "targets": ["HarborMesh"]}
  }]
}
```

Applicability can name `being`, `body`, `project` or `environment`; all except
being-wide scope require explicit targets. This is an attributed selection, not
proof of authorship, identity or runtime capabilities. Body of origin remains in
the original HMK metadata. Missing legacy attribution stays missing. Unknown
selection/source fields remain in inert original sidecars; only known fields have
implemented behavior.

Expired temporary entries are omitted from every active-view file, including the
manifest's selection copy. Preserve the original selection outside the view for
history; otherwise searching that copy would reintroduce expired context.

```bash
python3 scripts/codex_projection.py publish --database authorized/library.db \
  --selection selection.json --root isolated-codex-home/memories --writers-stopped
python3 scripts/codex_projection.py verify --root isolated-codex-home/memories \
  --database authorized/library.db
```

The destination must be new and its writers stopped. The projector does not
replace existing views or native-authored changes. It uses a coherent source
read transaction, checks dependent-source currency, builds privately and renames
the verified generation into place. Publication serializes cooperating projectors;
native writers do not share that lock. Restart after a completed publication
reuses the published manifest; an incomplete unpublished staging directory is not
an active view and can be removed after inspecting the stopped operation.

The view contains `memory_summary.md`, `MEMORY.md`, linked current-head originals
under `rollout_summaries/`, inert full original sidecars, and a content-hashed
`hmk-projection.json` manifest. Registry snippets are cropped navigation aids;
linked originals are complete. HMK UUIDs are not presented as original Codex
rollout identities. Historical revisions, links and canonical artifacts remain
in the HMK database; this selected view is not their portable backup.

## Consumer boundary

Before starting a receiver, verify view hashes, source revisions/support and
temporary expiry. Rebuild if expired or stale. This enforces freshness at that
boundary, not inside an already-open conversation. A live integration needs an
equivalent freshness boundary; no timer or hook is installed here.

Codex 0.160.0's `generate_memories=false` only excludes new sessions from native
formation. An observed isolated durable receiver still ran startup maintenance,
removed externally supplied rollout summaries and rewrote summary/registry files.
`verify` detects those changes; canonical HMK is unchanged. Do not use that setting
alone to protect a projection. Stock ephemeral receivers skip that startup path;
durable external-view use needs the separately qualified Codex startup-processing
control described in the [integration plan](codex-hmk-provider-plan.md). Explicit
notes and reset remain distinct operations, not implied read-only behavior.

Accepted Matrix projection records are refused by this generic projector: use
their existing verified owning adapter. This tool neither imports existing HMK
records into Matrix nor authenticates a supplied being/body label.

## Preserve and incorporate native learning

The Python API `learning_bundle` preserves exact selected producer bytes, logical
member names, source body/subject/event and inherited-projection provenance.
`restore_learning` checks its envelope and every member's bytes/hash. Callers must
actually observe the producer and choose authorized files; a manifest is not proof
that a model learned something or that its statements are true.

`incorporate` takes an explicit source-qualified selection and policy version. It
backs up SQLite with the existing verified backup API and reuses `CaptureLedger`
for pending deltas, expected-revision writes, cursor advancement and exact replay.
Original bytes commit with the selected records in a separate
`native_learning_artifacts` table; they are not noisy chapters or embedding inputs.
Selected records point back to the artifact by hash. Full SQLite preservation
retains this table alongside the existing originals/revisions/journal.

`load_learning` retrieves and verifies those originals. Artifact loss blocks a
successful replay claim. A failed record update leaves the source payload pending
and preserves legitimate current records. Different terminal selection bytes
require an attributed successor, not an overwrite of the previous decision.

Known `artifact:sha256:` evidence is a content dependency, unlike an ordinary
world reference. Publication and source verification require its canonical
envelope and member bytes to verify. The view retains its fingerprint but does
not expose original native sessions. Restore only selected learned assets into
the receiving workspace through `load_learning`; the complete archive remains
in canon.

Deciding whether meaning is genuinely new requires comparison against the source
and inherited projection. Reworded projected facts are not new experience or
independent support. This API deliberately does not declare semantic novelty,
grant another being's authorship, automatically publish private data or turn a
native file into a signed Matrix event.
