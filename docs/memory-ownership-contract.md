# Memory ownership contract v1

This contract removes the ambiguous claim that either `library.db` or “the
wiki” is universally canonical. Authority belongs to one store per artifact
class. Other copies are indexes or projections and must be rebuildable from
that authority.

The machine-readable policy is
[`policies/memory-ownership.v1.json`](../policies/memory-ownership.v1.json).

## The two wiki surfaces

They are different products and must never share a target directory:

| Surface | Typical path | Owner | Purpose |
|---|---|---|---|
| LLM Wiki | `$WIKI_PATH`, normally `~/wiki` | Human/agent curation workflow | Authoritative raw evidence and long-form curated knowledge |

## Authority by artifact

| Artifact | Authority | Other surface |
|---|---|---|
| Raw LLM Wiki evidence | File under `$WIKI_PATH/**/raw/` | DMK `evidence` chapter is a retrieval index |
| Curated LLM Wiki note | File under `$WIKI_PATH` | DMK `library` chapter is a retrieval index |
| DMK-native identity/state/plan/episode/atomic note | `library.db` | Native records retain their own source history |
| Live project branch/blocker/task state | Project `MEMORY.md` and GitHub | May be linked, never copied as durable wiki truth |
| Dialogue continuity | The originating harness's native session/goal history (Hermes `state.db`; Codex thread history and compaction state) | DMK retrieval may supplement it; shared handoffs are attributed project context, not the original history |
| Daimon `/me` personal memory | Daimon Matrix signed/evented memory ledger | DMK `daimon-projection` row is a disposable retrieval view |

A DMK `library` shelf can therefore contain both authoritative DMK-native
records and rebuildable indexes of LLM Wiki notes. Shelf alone does not decide
authority. The record's origin does:

- a record created directly through `librarian`/`memoryctl` has
  `origin=native`;
- a record created by `wiki_publish` has a wiki source path and content hash
  in its publication receipt and is an index of that file.
- a record created by `daimon_projection.py` has explicit Matrix source,
  subject/author, memory/head, classification, checkpoint and projector fields;
  its projection history is audit evidence but Matrix remains authoritative.

Codex also has a separate local cross-session memory lifecycle. Its generated
summaries, source resources and learned procedures must not be confused with
native dialogue continuity or automatically treated as DMK-native records.
The [Codex integration review](codex-native-memory-review.md) compares explicit
ownership under coexistence with a full backend/writer adapter. No receiving
adapter or additional machine-readable ownership class is activated by this
documentation; the existing policy file remains scoped to its declared paths.

Until DMK persists origin fields directly, the verified `wiki_publish` receipt,
source path, file hash, tags, and `derived_from` edge are the provenance
boundary. The DMK→collective-memory adapter must carry that origin explicitly
rather than infer it from shelf or title.

## Write paths

### DMK-native memory

Write through `librarian` or `memoryctl`; never through raw SQL. Back up before
schema, provider, bulk rewrite, or destructive maintenance. The retired Obsidian exporter is no longer shipped.

### LLM Wiki publication

Write drafts under the configured staging directory and publish through
`wiki_publish`. Its transaction:

1. validates frontmatter, taxonomy, links, and raw-body hash;
2. snapshots the DMK database;
3. atomically writes raw/note/index files;
4. creates DMK retrieval-index chapters and the `derived_from` edge;
5. appends the wiki log and verifies the chain;
6. restores both file and database state if any step fails.

The files are authoritative. A failed or missing DMK index is repaired from the
files; it is not a reason to overwrite the files with an older DB chapter.

### Daimon personal-memory projection

Write only through the closed `daimon_projection.py` API. Generic DMK ingest,
update, delete, linking and collective publication reject projection-managed
chapters. Correction/retraction follows Matrix event predecessors; rebuild is
limited to one exact source/subject/projector namespace. See
[the Daimon projection contract](daimon-projection.md).

## Drift resolution

| Drift | Resolution |
|---|---|
| Wiki file hash differs from its declared raw hash | Stop; preserve both versions and investigate source mutation |
| Wiki file differs from its indexed DMK chapter | Re-index DMK from the wiki file after a verified DB snapshot |
| DMK-native record differs from projection note | Rebuild the projection from DMK |
| Daimon projection differs from Matrix source head | Stop retrieval for that namespace and rebuild it from Matrix; never write the DMK value back as source truth |
| Project `MEMORY.md` disagrees with Git branch/runtime | Git/runtime wins for mechanical state; repair `MEMORY.md` |
| Publication receipt or provenance edge is missing | Treat DMK copy as untrusted index; rebuild the full chain through the gate |

Never “merge both” automatically. The authoritative side replaces its replica
after preservation and validation.

## Recovery

- LLM Wiki recovery uses its Git/Obsidian history plus raw-body checksums. DMK
  is not a backup of the wiki.
- DMK recovery uses a SQLite backup API snapshot with integrity and
  foreign-key checks. A wiki index is not a database backup.
- Daimon projection recovery verifies its receipts/checkpoint and atomically
  rebuilds one namespace from Matrix.
- Project operational recovery reconciles GitHub, Git, runtime, then
  `MEMORY.md` in that order.

## Publication boundary for collective memory

Collective memory is a downstream publication surface, not another authority.
The adapter publishes immutable, provenance-bearing versions:

- wiki-origin records cite the authoritative wiki path/hash and their evidence
  edge;
- DMK-native records cite the DMK record ID, content hash, and memory policy;
- updates create a new version and supersession edge;
- deletions become tombstones, never silent disappearance.

Daimon projection rows are excluded from the current DMK-native publication
adapter. Publication, if later designed, must be a distinct reviewed derivation
that preserves Matrix provenance and consent.
