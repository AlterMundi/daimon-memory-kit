---
name: librarian
description: Query and curate durable experience and documents in the local DMK library, preserving history, attribution and the distinction between native records and authoritative-source retrieval indexes.
version: 2.1.0
author: Local System
license: MIT
metadata:
  hermes:
    tags: [Memory, Librarian, Retrieval, SQLite, FTS5, Local]
    related_skills: [codebase-inspection]
prerequisites:
  commands: [python3]
---

# Librarian

Use the local memory controller instead of bloating the live prompt with raw notes.

## Invocation idiom (v3 — workspace-relative)

All commands run from the **agent workspace root** (`$HMK_WORKSPACE_ROOT`, typically `~/agents/<agent-name>/`) using the `./scripts/hmk` wrapper. The wrapper cd's to the workspace, loads the agent's `.env`, and absolutizes `HMK_*` paths, so scripts never rely on hardcoded user-specific paths. Never call the underlying `.py` files directly with absolute paths — use `./scripts/hmk` always.

Paths referenced below (e.g. `agent-memory/state/NOW.md`, `wiki/index.md`) are **relative to the workspace root**. They resolve correctly for any agent bootstrapped from `hermes-memory-kit`, not just `hermes-prime`.

## When to Use

- User asks what we were previously working on
- You need legacy project roadmap or architecture context
- You need current memory-system status or design rationale
- You want to register a durable fact or document
- You are selecting meaningful experience from authorized foreground work
- You need to expand one stored item without loading everything

## Rules

- Prefer `hybrid-pack` before `expand`
- Accept `null_retrieval` when returned; do not pad with weak matches
- Never write to `$HERMES_HOME/SOUL.md` through memory maintenance flows
- Do not treat `MEMORY.md` as the hot write path
- Use `expand` only for items already selected as relevant
- Treat the workspace `wiki/` as a disposable DMK projection.
- Treat `$WIKI_PATH` as a separate, authoritative LLM Wiki for its raw and
  curated files. DMK copies of those files are retrieval indexes.
- For DMK-native records and precise continuity, use `library.db`.

## Selecting experience

Use [durable-memory-selection.md](references/durable-memory-selection.md) when
selecting or updating memories of people, projects, shared episodes, actions or
learning. It explains what to retain, what to omit, how to distinguish current
syntheses from history, and how to preserve body and source attribution. The
same selection applies to tool responses and embodied encounters as to dialogue.
Follow the receiving body's memory-access policy; this reference does not
authorize automatic prefetch, inbox attention or access to private sessions.

## Core Commands

### 1. Query a compact bundle

```bash
./scripts/dmk memoryctl.py hybrid-pack --query "USER_QUESTION" --budget 1800 --limit 4 --threshold 0.4
```

Use `--threshold 0.4` as the current pragmatic default. Raise it only when retrieval is noisy.
Fallback to plain `pack` only if the embeddings layer is unavailable or you explicitly want a lexical baseline.

### 2. Inspect raw ranked candidates

```bash
./scripts/dmk memoryctl.py search --query "USER_QUESTION" --limit 6
```

Use this when ranking looks suspicious and you need to inspect why.

### 3. Expand a stored item

```bash
./scripts/dmk memoryctl.py expand --id 17
```

This returns the full raw content plus linked neighbors.

### 4. Add a durable text memory

Use a unique episode title. Replacing a single native chapter under the same
shelf/title now preserves its ID, links and searchable prior revisions. Inspect
related records and use `--if-revision` for updates based on an observed revision;
a conflict means retrieve the current version before reconciling it. Replacing
a multi-chapter book requires explicit chapter updates.

Set `--type`, known `--event-ts` and attributed `--metadata-json` when available.
Unknown occurrence is not the recording date. Metadata describes the source and
whether a claim is observed, reported, inferred or generated; it grants no signed
authority. For past questions, use `history --id N` or `history-search --query
"past cue"` and qualify the returned revision as historical. Current retrieval
does not silently mix superseded accounts into present answers. Explicit native
deletion also removes that record's revisions; snapshots require separate handling.
Short selected memories retain their full text as SPR. For longer source records,
pass `--summary` with the participant, event, significance and uncertainty that
must survive recall. Automatic previews are marked incomplete; expand before
answering details absent from them. Lexical search covers the full source text.

When explicitly authorized to process a finite source delta, `capturectl.py`
can stage pending input, list a selected stream and apply/omit/defer a supplied
selection. It commits supported writes and the processing receipt together;
replay does not create another encounter. `consolidationctl.py preview --ids ...`
supplies full selected episodes; reviewed apply proposals retain those episodes
and versioned support. These commands install no automatic attention or triggers.
If a derived account has `support_status=needs_reconciliation`, inspect changed
or missing evidence before using it as a current conclusion. Version currency is
not a truth score. Selection quality still requires the isolated model pilot.

```bash
./scripts/dmk memoryctl.py add-text \
  --shelf episodes \
  --title "short-title" \
  --raw "durable fact or decision text" \
  --tags memory,decision \
  --importance 0.8
```

### 5. Add a file into the library

```bash
./scripts/dmk memoryctl.py add-file \
  --shelf plans \
  --path /path/to/file.md \
  --title "descriptive-title" \
  --tags plan,architecture \
  --importance 0.9
```

### 6. Check library stats

```bash
./scripts/dmk memoryctl.py stats
```

### 6b. Inspect embedding backend configuration

```bash
./scripts/dmk memoryctl.py embed-config
```

Use this when retrieval quality, provider selection, or portability of the memory stack is relevant.
Current architecture supports:
- `nvidia` as the active default
- `google` (`gemini-embedding-001`) when a Gemini/Google API key is present
- `local` as an optional backend for a compatible sentence-transformers stack

### 7. Ingest heterogeneous sources via the modular stack

```bash
./scripts/dmk ingest_any.py \
  --source /path/to/file.pdf \
  --shelf evidence \
  --title "descriptive-title" \
  --tags pdf,source \
  --importance 0.7
```

Use this for PDF, DOCX, HTML, URLs, or any source that should be normalized to markdown before entering `library.db`.

Current modular stack:
- `pdftotext` for PDF
- `trafilatura` for URLs and HTML
- `pandoc` for broad document conversion
- `mammoth` as DOCX fallback

### 8. Native session re-entry, separate from durable retrieval

Use Hermes `/resume` for the intended session, `session_search` for explicitly
selected history, and native `/goal` for the active mission. Native SQLite
session/goal persistence is distinct from the optional MEMORY.md/USER.md stores.
The kit defaults to DMK for durable memory with those native stores disabled.

`continuityctl.py rehydrate` is deprecated: it returns native re-entry guidance,
not recovered context, and reads no files or databases. Old retrieval/summary
flags are accepted but ignored. Use `memoryctl hybrid-pack`, `expand`, or the
`librarian` tool for explicit durable recall. `continuityctl show` and `update`
remain available for operator-maintained engineering notes only.

## Memory Topology (workspace-relative)

- `agent-memory/library.db`: curated durable DMK memory
- `agent-memory/state/NOW.md`, `ACTIVE-CONTEXT.md`: optional engineering notes
- `agent-memory/index/INDEX.md`, `plans/MEMORY-ARCHITECTURE.md`: navigation
- `hermes-home/state.db`: native sessions and goal state, managed by Hermes

These are bootstrap defaults. Follow the actual deployment paths and preserve
`HMK_AGENT_MEMORY_BASE`; do not invent another memory root to match the examples.

## Retrieval Strategy

1. Use `hybrid-pack` or `librarian` for durable knowledge.
2. For lost dialogue, select the native session/history rather than searching a
   shared handoff or assuming the latest same-platform conversation is yours.
3. For conceptual orientation, inspect the appropriate navigation surface.
4. Cite chapter IDs like `[mem:17]`, then `expand` selected IDs if needed.
5. Accept `null_retrieval`; missing recall does not activate native file stores.

Current user direction outranks historical summaries, quotations and engineering
notes. Do not promote a worker result, `/new` parent ID, or stale context into a
new human request. DMK automatic prefetch and `librarian` do not depend on the
optional dialogue plugin. Do not treat retrieved chapters as a conversation log.

## Ingestion Strategy

- use `./scripts/dmk memoryctl.py add-file` for clean markdown or text already in final form
- use `./scripts/dmk ingest_any.py` for heterogeneous formats
- normalize first, then store
- do not put binary formats directly into `library.db`
- do not rely on Python `MarkItDown` on pre-AVX CPUs; it crashes (SIGILL). The host stub at `~/.local/bin/markitdown-local` explains alternatives.

## Curation Workflow For New Documentation

When new documentation enters the system, classify its authority first.

DMK-native flow:

1. normalize the authorized source outside the canonical pool
2. retrieve related context with `hybrid-pack`
3. apply the durable selection policy; route operational detail to project state
4. persist only selected self-contained meaning and its evidence references
5. verify recall, follow the record's original sources

An explicitly requested source archive is a separate purpose. Availability of
`add-file` or `ingest_any` does not make every document durable autobiography.

LLM Wiki flow:

1. stage raw evidence and a curated note outside `$WIKI_PATH`
2. publish through `wiki_publish`
3. verify the DMK evidence/library indexes and `derived_from` edge
4. repair index drift from the authoritative wiki files, never the reverse

### Minimal curation loop

#### A. Select before ingesting

The command below stores an explicitly selected source. Normalize and inspect
it first; omit routine working state or keep it in the owning project.

```bash
./scripts/dmk ingest_any.py \
  --source /path/to/source \
  --shelf evidence \
  --title "descriptive-title" \
  --tags source,new \
  --importance 0.7
```

#### B. Retrieve related context

```bash
./scripts/dmk memoryctl.py hybrid-pack --query "topic of the new document" --budget 1800 --limit 4 --threshold 0.4
```

#### C. Inspect conceptual map if needed

```bash
sed -n '1,200p' wiki/index.md
sed -n '1,220p' wiki/maps/project-memory-system.md
```

#### D. Choose one or more outputs

- evidence only
- evidence + links
- evidence + distilled `library` note
- evidence + wiki update
- evidence + map note update
- evidence + pending-curation follow-up

### Hard rule

- `library.db` is authoritative for DMK-native records
- `$WIKI_PATH` is authoritative for LLM Wiki-authored records
- every artifact has one authority; follow the v1 memory ownership policy

Detailed contract: `agent-memory/plans/CURATION-PIPELINE.md` (if present in this agent)

## Anti-Patterns

- Dumping entire raw docs into the answer when SPR is enough
- Using `expand` on many items at once
- Writing scratch noise into the library
- Treating absence of results as failure instead of valid null retrieval
- Referencing absolute paths under `/home/<user>/agent-memory/...` — those are pre-v3 legacy and may not exist. Use workspace-relative paths always.
