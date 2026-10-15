# DaimonMemoryKit

Durable local memory and portable continuity for daimons across agent harnesses.
Maintained by [AlterMundi](https://github.com/AlterMundi/daimon-memory-kit).

[![license](https://img.shields.io/github/license/AlterMundi/daimon-memory-kit)](LICENSE)

## What it does

- Preserves original memories, revisions, corrections, links and provenance in SQLite.
- Retrieves older experiences from partial cues using lexical and semantic search,
  with bounded navigation through originals and history.
- Selects meaningful experience from authorized sources, consolidates supported
  understanding and reconciles accounts when their evidence changes.
- Resumes interrupted processing without losing pending inputs or repeating committed
  work. Provider failures remain visible through operational status and Alerts.
- Exposes memory to Hermes and Codex while distinguishing remembered skills from
  the current body's tools and capabilities.
- Supports portable preservation and qualified harness projections without turning
  a copy into identity, authority or a new experience.

Memory stays in local files. Embeddings and model providers are configurable;
records and queries must use the same embedding space. Native session history,
project status and durable memory retain their separate purposes.

## Start here

```bash
git clone https://github.com/AlterMundi/daimon-memory-kit.git
cd daimon-memory-kit
python3 scripts/bootstrap_agent.py ~/agents/my-daimon --name my-daimon
cd ~/agents/my-daimon
# Configure .env and your harness before enabling integrations.
./scripts/dmk memoryctl.py init
./scripts/dmk memoryctl.py add-text --shelf library --title "An encounter" \
  --raw "A selected, attributed experience worth remembering." --tags encounter
./scripts/dmk memoryctl.py hybrid-pack --query "the encounter" --budget 1500 --limit 5
```

The workspace scaffold is optional and includes Hermes integration. For an
existing installation, use its actual owner-bound command and memory pool;
do not initialize a second database. See [installation](docs/install.md).

The CLI core uses Python and SQLite. Optional ingestion, embedding and MCP
packages have separate requirements files. `memoryctl.py embed-config` shows
the selected embedding backend; preserve an existing deployment's selection.

## Harness integration

**Hermes:** the provider plugin supports retrieval through the harness's memory
surface. [Provider configuration](docs/memory-provider.md).

**Codex:** the owner-bound MCP reader exposes `dmk_recall` for contextual search,
originals, history and revision checkpoints. [MCP setup](docs/live-mcp-recall.md).
Authorized lifecycle capture and the finite worker provide a separate learning
path. Installing a reader does not enable capture or native Codex learning.

**Daimon Matrix:** signed personal-memory events keep their Matrix authority;
DMK can maintain attributed retrieval views. Native DMK records remain distinct.
[Ownership](docs/memory-ownership-contract.md) · [Matrix adapter](docs/daimon-projection.md).

## Components

| Component | Purpose |
|---|---|
| `scripts/dmk` | Workspace-aware CLI entry point |
| `memoryctl.py` | Durable records, revisions, links and hybrid retrieval |
| `dmk_mcp.py` | Owner-bound, read-only contextual recall |
| `capturectl.py`, `capture_inbox.py` | Preserved sources and idempotent intake |
| `portable_producer.py`, `memory_worker.py` | Resumable selection and finite processing |
| `consolidationctl.py`, `account_reconciliation.py` | Supported organization and reconciliation |
| `daimon_projection.py` | Attributed Matrix retrieval views |
| `codex_projection.py`, `codex_coordinator.py` | Qualified native-projection experiments |
| `sqlite_snapshot.py` | Verified snapshots including committed WAL data |
| `publish_collective.py` | Explicitly reviewed downstream publication |

The Obsidian exporter and generated vault templates have been retired. Existing
local notes are preserved; the independently authored LLM Wiki is separate.
Portable archives, Matrix projections and harness projections remain supported.

## Current work and evidence

[Continuation issue](https://github.com/AlterMundi/daimon-memory-kit/issues/1)

- [Integrated operation and receiving evidence](docs/integrated-memory-plan.md)
- [Durable recall roadmap](docs/durable-recall-plan.md)
- [Canonical memory and harness projection roadmap](docs/codex-hmk-provider-plan.md)
- [Finite worker and recovery](docs/memory-worker.md)
- [Capture and selection](docs/foreground-capture.md)
- [Architecture](docs/architecture.md)

Evidence distinguishes implemented, qualified and deployed behavior. A successful
export or matching record alone does not prove conversational continuity.

## Compatibility

DMK is the current project name. Existing `hmk` commands, `HMK_*` environment
variables, `hmk-memory` plugin IDs, `hmk_recall` calls and versioned `hmk.*` schemas
remain supported. These identifiers still address the same memory, not a second
system. Existing database paths and captured-source identities do not change.
See [the naming and receiving update](docs/dmk-naming.md).

## Contributing

Open issues and PRs in this repository. Reuse existing APIs and tests, preserve
originals and source authority, and validate the behavior being changed. The base
smoke test covers bootstrap, retrieval and upgrade preservation; actual harness
integration requires its own receiving evidence.

## License and origin

[MIT](LICENSE) — Copyright (c) 2026 Asociación Civil AlterMundi.

Based on [Hermes Memory Kit](https://github.com/Mar-IA-no/hermes-memory-kit) by
Mariano Fernández Méndez. Earlier issues and PRs remain in the
[previous repository](https://github.com/nicoechaniz/hermes-memory-kit);
Git history retains the project's development.
