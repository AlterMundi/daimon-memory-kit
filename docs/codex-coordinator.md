# Explicit, resumable Codex view renewal

`scripts/codex_coordinator.py` coordinates the existing projection and capture
APIs. It runs only when explicitly invoked, with native writers stopped. It does
not call a model, enable native memory, install a hook or admit memory into Matrix.
Persistence regression evidence is separate from receiving-model qualification.

## Request and invocation

Use an existing authorized same-being SQLite canon and a dedicated receiving home.
Keep the journal outside that home, on the same filesystem for atomic renames.
Database/home paths must be absolute. A receiving home binds to one journal;
another pending operation blocks renewal until explicitly resumed.

An illustrative fictional request, after observing a genuinely new native note:

```json
{
  "schema": "hmk.codex-coordinator.request/v1",
  "database": "/authorized-fictional-canon/library.db",
  "codex_home": "/isolated-fictional-receiver/codex-home",
  "selection": {
    "schema": "hmk.codex-projection.selection/v1",
    "being_ref": "fixture:being:ilex",
    "body_ref": "fixture:body:voice",
    "records": []
  },
  "evidence_files": {
    "observed-turn.json": "/selected-fictional-evidence/observed-turn.json"
  },
  "learning": {
    "source_event_id": "native-turn:actual-stable-id",
    "sequence": 1,
    "selection_version": "source-qualified-policy:v1",
    "reason": "Observed new local result, without a production effect.",
    "records": [{
      "key": "units", "operation": "add", "shelf": "library",
      "title": "Explicit sample units", "engram_type": "procedural",
      "raw": "The local check required explicit millivolt units."
    }],
    "support": {
      "units": [{"member": "extensions/ad_hoc/notes/units.md",
                 "text": "The local check required explicit millivolt units."}]
    },
    "applicability": {
      "units": {"kind": "environment", "targets": ["fixture:lab-beta"]}
    }
  }
}
```

```bash
python3 scripts/codex_coordinator.py --state-dir /selected-private-journal \
  --operation units --request request.json --writers-stopped
python3 scripts/codex_coordinator.py --state-dir /selected-private-journal \
  --operation units --writers-stopped
```

The second invocation resumes the immutable operation without its original input
file or evidence paths. A changed request cannot replace a pending/terminal one.
Stable producer event IDs, sequence and decision are required for CaptureLedger
replay; do not allocate another event ID to retry an uncertain commit.
For initial publication or a renewal selecting no new durable learning, use empty
`records`, `support` and `applicability`, retaining an explicit reason/event ID.
Exact native changes still remain in the operation archive. No omitted text is
silently promoted into ordinary canonical recall.

## Qualified capture and preservation boundary

Before canonical mutation the journal freezes exact memory-view bytes, including
available native Git/history files, selected original evidence and the inherited
projection manifest. Native sessions elsewhere in the receiving home remain in
place; only explicitly selected evidence files are copied into the archive.
Do not point evidence selection at private conversations, credentials or custody.
Archives are private source material, not public artifacts or receiving context.

Each selected record needs applicability and verbatim support from changed native
bytes. Decoded inert originals and unchanged projected content identify exact
copies that must not be promoted as new experience. Changed inert originals block
new intake until reconciled; their files remain preserved in the receiving home.
Hashes/support substrings do not establish semantic novelty or truth. The caller
must inspect every selected claim against actual producer actions, distinguish
new observations from recalled/rephrased projected experience, and supply the
explicit source-qualified decision. Semantic paraphrase detection is not claimed.

The coordinator reuses `learning_bundle`/`incorporate` and their verified SQLite
backup and CaptureLedger transaction. Only selected new records become chapters;
the exact artifact and ancestry remain separate source evidence. Corrections use
the existing expected-revision APIs; supply the resulting selected heads when
requesting renewal. Dependent support currency is checked by the projector.

## Resume and receiving gate

The durable phases are frozen → captured → built → archived → complete. An
uncertain capture result replays the same transaction receipt. An unpublished
expired candidate is retained and rebuilt with expired context removed. Corrupt
candidates and post-freeze native writer drift block activation while preserving
both pending work and canonical learning.

The previous native tree is renamed into the private journal before activating
the next verified generation at the same `codex-home/memories` path. A crash in
that two-rename window can temporarily leave no active directory. Resume the
selected operation before starting the receiver; the preserved previous tree and
candidate identify the recoverable state. The coordinator never restores an old
database over later canonical memories.

Before every receiving launch, invoke `codex_projection.py verify` with the canon
to check the active view, revisions/support and real-clock expiry. A completed
operation replay returns its receipt without overwriting subsequent native work;
it is not a new freshness check. Use a new explicitly selected operation to
preserve that work and renew the view. Keep startup processing disabled in the
qualified persistent build. No automatic lifecycle coverage follows from this
foreground procedure.

## Persistent receiving qualification

The [stage-six receiving report](../research/agent-memory-2026-10-06/pilots/2026-10-11-persistent-codex-coordinator.md)
qualifies the explicit coordinator with OpenAI Codex Sol6.1 low on the labelled
`0.160.0-hmk.1` fork. Actual process restart, new note capture, post-commit fault
and replay, source correction, real expiry, fresh-thread action, clean restoration
and configuration rollback pass. Production remains manual.

Use an accurate persistent binding: original historical/private sessions are
absent, but the isolated home's own native session history may remain. Their
presence grants neither current world-state evidence nor capabilities. Changing
resume parameters was not sufficient to correct the tested old binding claim;
start a fresh thread when changing that receiving definition. The rejected
review is retained separately from the effective correction.

The coordinator requires quiesced writers. It detects drift but does not merge
concurrent writes or replace immutable pending selections. If canon changes
while a frozen operation remains pending, preserve both states and reconcile it
explicitly; automatic replan/cancel and existing-thread context replacement are
not qualified. Do not start an unverified view as a fallback. An expired overlay
must be removed by a verified renewal before fresh receiving use.
