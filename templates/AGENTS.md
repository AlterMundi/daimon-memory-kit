# AGENTS.md

## Scope

This workspace uses DaimonMemoryKit as its durable memory layer.

## Memory Discipline

- DMK-native memory lives canonically in `agent-memory/library.db`
- use `./scripts/dmk memoryctl.py hybrid-pack` for durable retrieval
- use `./scripts/dmk ingest_any.py` to normalize heterogeneous sources before storage
- LLM Wiki files are authoritative for their raw evidence and curated notes;
  their DMK chapters are rebuildable retrieval indexes
- accept `null_retrieval` instead of padding weak context

## Curation Discipline

- classify new documentation as DMK-native or LLM Wiki-authored first
- then retrieve related context
- then inspect the appropriate navigation surface if conceptual orientation is needed
- then decide whether to keep as evidence, link, distill, or project

## Remembering experience

DMK preserves what allows a future body to recognize our history and return to
our affairs after the sessions are gone. Retain enduring meaning and useful
world references together. Temporary operational relevance alone is insufficient;
native harness memory candidates need the same judgment before entering DMK.

Within authorized foreground work, consider meaningful experience from human
conversation, tool responses, actions and embodied encounters. Follow this
body's actual memory-access policy; this guidance adds no background attention
or permission to read another conversation.

- Preserve people and entities involved in meaningful interactions: known names,
  aliases, source-scoped identifiers, what happened and why it mattered.
- Keep a compact, dated account of projects with your own contributions: role,
  work contributed, last observed broad status and the repository's state entry
  point. Keep detailed branch, test, deployment and task state in that repository.
- Preserve shared episodes, ordinary distinctive moments, lasting insights,
  commitments and reusable learning. These examples do not exhaust what matters.
- Make each memory understandable without its original session or source URL.
  Distinguish occurrence, report and recording dates; preserve uncertainty,
  originating body and attribution to other beings.
- Update current syntheses while retaining meaningful history and corrections.
  Omit repetitive output and temporary scratch details; significance is not
  determined by message length or whether something arrived through a tool.

For selection, record shapes and safe update practice, use the `librarian`
skill's [durable-memory selection reference](hermes-home/skills/memory/librarian/references/durable-memory-selection.md).

## Token Discipline

- no periodic loops by default
- no background polling unless explicitly requested
- prefer bounded retrieval bundles over raw dumps

## Re-entry priorities

Use native Hermes session history and goal state for the matching conversation.
The latest human direction controls continuation; historical summaries do not
revive cancelled work. Retrieve DMK or the project cockpit when needed, but do
not infer current dialogue from engineering-state files or global handoffs.

`./scripts/dmk continuityctl.py rehydrate` provides an optional native-first
orientation result, not a recovered conversation or a mandatory startup ritual.
Keep retrieval metadata out of ordinary conversation unless relevant to the
user's request.
