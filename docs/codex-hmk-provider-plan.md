# HMK as the Codex memory provider

## Selected direction — 2026-10-11

The human prefers a complete HMK-backed replacement for native memory storage,
with normal Codex memory behavior and the additional durable being-level
capabilities already qualified in HMK. Two independently maintained active memory
authorities are not the target. This updates stage five under [issue #11](https://github.com/nicoechaniz/hermes-memory-kit/issues/11).
Stages 1–4 and the Eko/Oliva hosted rollout evidence remain valid.

Feasibility is supported by accessible source and separable read/formation paths;
implementation, feature parity, maintenance cost and upstream acceptance are not
yet demonstrated. The installed CLI checked today is 0.160.0. The existing source
checkout is `34f33e4ada8f417203d87f3b5858c97add8dad6b`; upstream main was independently
fetched at `cc7ba33601286a751477832b01de7b6f8de0dd9c` without replacing that checkout.
Relevant production read/write/state memory paths are unchanged between those commits;
the inspected config delta adds a TUI option and no memory provider selector.

## What already exists and what is missing

The [`MemoriesBackend` trait](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/ext/memories/src/backend.rs)
supports list, read, search and ad-hoc notes, with paths, line numbers, match modes,
pagination, limits and explicit errors. Its comment anticipates remote storage.
The [extension](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/ext/memories/src/extension.rs)
still constructs the local backend directly. Initial context reads a local summary
through [prompts](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/ext/memories/src/prompts.rs).

Formation uses a concrete SQLite [MemoryStore](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/state/src/runtime/memories.rs)
and separate [phase-one extraction](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/memories/write/src/phase1.rs)
and [phase-two consolidation](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/memories/write/src/phase2.rs).
Consolidation writes validated filesystem artifacts and disables MCP/plugins.
[Reset](https://github.com/openai/codex/blob/cc7ba33601286a751477832b01de7b6f8de0dd9c/codex-rs/app-server/src/request_processors/thread_processor.rs)
clears database memory data and file roots directly. Implementing only the four
trait methods or installing an MCP tool would leave these paths unredirected.
The [official memory controls](https://learn.chatgpt.com/docs/customization/memories)
describe generation/use and model settings, not a documented external provider.

## Proposed implementation boundary

Add a selectable provider boundary in the owning Codex components, retaining the
existing local implementation as its default. The HMK adapter should initially
use the existing local installation and supported APIs; no mandatory hosted
memory service is implied. Backend transport and the exact expanded interface
must follow the focused inventory, not an invented public API.

Codex may retain session history, job/lease bookkeeping and disposable working
files. These are not an independently authoritative memory corpus. The existing
consolidator can use a materialized workspace if its inputs and validated outputs
are loaded/committed through the provider, every original learned artifact is
preserved in HMK, and no authoritative write bypasses that commit path. If a
filesystem route cannot meet this contract, change that route rather than claiming
that file copying or a symlink completes the replacement.

| Coverage | Acceptance requirement |
|---|---|
| Configuration and scope | Preserve supported memory versions and modes, generation/use controls, source eligibility and selected body/project namespaces; bindings must not grant another being's authority. |
| Tools and initial context | Preserve exact path/line, lexical match, pagination, truncation and error semantics; retrieve context through the selected provider. Semantic recall is an additional capability, not a substitute for exact search. |
| Native notes and artifacts | Preserve original bytes, hierarchy, source/version, ownership and available history; preserve learned procedures/skills rather than reducing them to summaries. |
| Extraction and consolidation | Use actual native generation, source eligibility, no-op outcomes, retries, leases and validated publication; preserve committed inputs/outputs before cleanup. |
| Usage and citations | Resolve citations to retained source versions and account for usage without inventing a new encounter or independent support. |
| Corrections, pruning and reset | Preserve history and explicit source ownership; distinguish native workspace cleanup from a request to erase authorized content. A body-local reset must not silently erase the whole being pool. |
| Restart, replay and concurrent writing | Persist cursors/receipts, resume unfinished work and detect conflicting revisions; rollback must preserve subsequent legitimate memories. |
| Existing HMK behavior | Retain durable episodes, relationships, corrections, source attribution, portable preservation and cross-body recall. Native workflow learning remains part of the being's delta. |

Preserved native artifacts and selected enduring recall may have distinct record
roles within HMK. Preserving a native learning artifact does not automatically
classify every temporary detail as autobiography; applying the durable lens must
not silently discard the original artifact either.

## Smallest useful next delivery

Inventory the owning call sites and reuse existing backend, extension, state and
artifact tests. Establish the versioned provider contract and a configurable
selection point; exercise one real extraction → consolidation → committed HMK
artifact → fresh native recall path. Compare with native local on identical
fictional input in separate authorized contexts. An intermediate read-only
milestone must remain explicitly incomplete.

Then close the remaining parity rows with focused cases, source loss, aging,
corrections, replay, failure and copied-store new-writing/rollback witnesses.
Reuse the qualified fictional corpus; do not repeat valid HMK consolidations.
Record parity, durable selection, narrative fidelity, preservation and costs
separately. Propose reusable extension points upstream after a coherent working
change; acceptance by upstream is not a prerequisite for demonstrating our adapter.
Evaluate the actual patch size and upgrade burden before claiming a small fork.

The current request selects and documents this direction; no runtime is enabled
here. Production native memory remains disabled. Real-corpus formation, automatic
injection and any new background work require an explicit receiving scope under
the next implementation goal. Private sessions, other beings and signed Matrix
admission remain outside an adapter's authority.
