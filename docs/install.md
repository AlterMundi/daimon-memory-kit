# Install

## Minimum Requirements

- Python 3.11+
- SQLite with FTS5
- `pdftotext` for PDFs
- `pandoc` recommended for heterogeneous formats

## Base Setup

```bash
git clone https://github.com/AlterMundi/daimon-memory-kit.git
cd daimon-memory-kit
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Workspace bootstrap

```bash
python3 scripts/bootstrap_workspace.py --workspace /path/to/workspace --with-wiki-templates
```

## Variables

The workspace gets its own `.env`. Copy the example and edit:

```bash
cd /path/to/workspace
cp .env.example .env
$EDITOR .env
```

The default `.env.example` uses paths relative to the workspace root (e.g. `HMK_BASE_DIR=./agent-memory`). That works out of the box — you only need to edit if you want to point any path elsewhere.

Paths you can set:

- `HMK_BASE_DIR` — where memory state / DB live (default: `./agent-memory`)
- `HMK_DB_PATH` — the SQLite library (default: `./agent-memory/library.db`)
- `HMK_WORKSPACE_ROOT` — resolved automatically by the wrapper; override if you need to
- `HMK_HERMES_HOME` — your Hermes Agent home (only relevant if you use the optional plugin)
- `HMK_AGENT_MEMORY_BASE` — alias for `HMK_BASE_DIR`, used by the plugin
- `HMK_SESSIONS_DIR` — overrides `$HMK_HERMES_HOME/sessions`
- `HMK_DIALOGUE_HANDOFF_PATH` — direct path to the handoff file (rarely needed)

## Running the tooling

Use `dmk`; `hmk` remains a compatible alias with the same `HMK_*` configuration:

```bash
./scripts/dmk memoryctl.py init
./scripts/dmk memoryctl.py add-text --shelf library --title foo --raw "content" --tags t1
./scripts/dmk memoryctl.py hybrid-pack --query "something" --budget 1800
./scripts/dmk continuityctl.py show  # engineering notes only, not dialogue
```

The wrapper loads `.env`, absolutizes any relative `HMK_*` paths against the workspace root, and `cd`s to the workspace before executing the target Python script. That makes invocation from any cwd predictable.

## Dependencies

Install once from the repo:

```bash
cd /path/to/daimon-memory-kit
pip install -r requirements.txt
# for local embeddings (optional):
pip install -r requirements-local-embeddings.txt
```

## Native continuity and optional dialogue compatibility

New workspaces select `hmk-memory`, native file stores disabled, and explicit
`plugins.disabled: [dialogue-handoff]`. Use Hermes `/resume`, selected native
history and `/goal` for conversational re-entry. No dialogue plugin is needed
for DMK prefetch or librarian. See [native-continuity.md](native-continuity.md)
for targeted migration and deprecated `rehydrate` behavior.

Existing standalone dialogue opt-ins are preserved, but no longer installed or
upgraded by DMK bootstrap. [dialogue-handoff.md](dialogue-handoff.md) describes
explicit compatibility installation. Do not blindly restart a shared gateway
or overwrite an independently repaired plugin as part of DMK setup.

## Smoke test

Before relying on a fresh install, run the smoke test once from the repo:

```bash
./scripts/smoke-test.sh
```

It exercises bootstrap → init → add-text → search → pack → upgrade, in a throwaway temp workspace.

## Initialization

From the workspace, or after exporting the required variables:

```bash
python3 scripts/memoryctl.py init
python3 scripts/memoryctl.py stats
python3 scripts/memoryctl.py embed-config
```

## Optional Local Embeddings

```bash
pip install -r requirements-local-embeddings.txt
```

Do not assume CPU compatibility without testing it.
