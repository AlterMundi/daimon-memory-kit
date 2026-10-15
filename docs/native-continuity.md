# Native-first continuity and DMK

DMK remains the durable curated memory provider, including automatic prefetch and
`librarian`. Native Hermes session history, routing, compression lineage and goal
state own conversational continuity. Native MEMORY.md/USER.md stores are a
separate feature and need not be enabled to resume sessions.

## New workspace defaults

```yaml
memory:
  provider: hmk-memory
  memory_enabled: false
  user_profile_enabled: false
plugins:
  enabled: [hmk-memory]
  disabled: [dialogue-handoff]
```

Bootstrap installs DMK and librarian, but no dialogue plugin, handoff,
always-context or native memory placeholders. Keep foundational identity in the
existing SOUL mechanism rather than a second global context file.

Bootstrap and `--upgrade` preserve existing configuration verbatim. They do not
parse/rewrite YAML or infer consent from directory presence. Existing native
memory files, legacy handoffs and independently installed dialogue plugins are
left alone. An opted-in user's plugin continues to be configured as before, but
DMK no longer upgrades that separately maintained component. The pinned vendor
remains available as an explicit compatibility artifact; see
[dialogue-handoff.md](dialogue-handoff.md).

This policy avoids both reinstalling an explicitly disabled plugin and
accidentally downgrading a newer standalone repair. Existing installations are
**not automatically disabled**: set `plugins.disabled: [dialogue-handoff]` and
remove the name from `plugins.enabled` when choosing native-only continuity.
Retain other enabled/disabled entries. Modern Hermes honors explicit disablement;
verify the actual runtime version and loaded hooks during deployment. Backups
belong outside active plugin discovery.

## Manual re-entry

`continuityctl.py rehydrate` is now a deprecated compatibility entry point. It
returns JSON with `mode: native-first`, `continuity.restored: false`, native
re-entry guidance, empty `meta_context`/`exact_memories`, and null
`query`/`retrieval`. It emits a deprecation notice on stderr. Old CLI
retrieval/summary flags are accepted but ignored; they cannot restore the old
reader. The `identity`, `state`, `episode_handoff` and `dialogue_handoff` output
fields are retired. It does not read files, import memoryctl, access any database,
run inference, or choose/restore a session. It works without DMK path variables.

Use Hermes `/resume` for the intended conversation, `session_search` for selected
historical context, and native `/goal` for the active mission. Do not choose the
latest same-platform session, or assume any parent ID authorizes inheritance.
A `/new` reset, explicit resume, compression successor and delegated worker are
not interchangeable. Current human direction outranks historical summaries.

Use `continuityctl show` / `update` only for optional engineering notes; they
still require the configured DMK base. Use `memoryctl hybrid-pack`, `expand`, or
`librarian` for explicit durable recall. Neither engineering state nor retrieved
chapters becomes a dialogue transcript.

## Scoped migration of an existing deployment

1. Record source/deployed provenance for each artifact separately. No memoryctl
   upgrade or schema migration is required for this change.
2. Keep `memory.provider: hmk-memory`, both native-store flags false when already
   selected, and the memory toolset available. Preserve `HMK_AGENT_MEMORY_BASE`,
   `HMK_MEMORYCTL_PATH` and embedding configuration. Removing dialogue-specific
   aliases is not permission to remove DMK's actual database root.
3. Deploy only the revised continuityctl and librarian instructions where needed;
   update root/nested re-entry instructions to native selection, not shared
   handoff reads. Do not replace identity files wholesale from generic templates.
4. Explicitly disable dialogue hooks; archive old mixed handoffs outside active
   consumption rather than importing them into DMK or deleting evidence. Review
   any essential ALWAYS-CONTEXT content for the existing identity floor, without
   duplicating it or enabling native file stores.
5. Verify isolated native resume/goal/routing and DMK recall before activation.
   Process reload/restart safety is deployment-specific; changing files alone
   does not prove loaded behavior changed.

Do not run broad bootstrap `--upgrade` merely to retire continuity: that command
still refreshes all kit scripts, including memoryctl, and other DMK tooling.

## Offline regression checks

```bash
python -m pytest tests/test_native_continuity.py \
  tests/test_bootstrap_continuity.py tests/test_native_continuity_provider.py \
  tests/test_hmk_memory_provider.py -q
```

Test dependencies: pytest and PyYAML (only tests; no new runtime dependency).
The provider regression uses a real temporary SQLite library with stubbed
embedding computation, both dialogue configuration states, null retrieval and
backend failure. It tests DMK independence, not Hermes plugin loading or
model-level behavior. To verify an older memoryctl artifact without deployment:

```bash
HMK_TEST_MEMORYCTL_PATH=/tmp/reviewed-memoryctl.py \
  python -m pytest tests/test_native_continuity_provider.py -q
```

No new global store or native-history adapter is introduced. Hermes lifecycle
acceptance belongs to the runtime integration, not a second implementation in DMK.
