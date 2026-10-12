# Bounded native context with deeper HMK recall

This opt-in adapter lets a Codex App Server receiver deepen a relevant memory
question beyond its selected native projection. HMK remains the selected canon;
Matrix admission and authority do not change. Native learning generation is not
needed. Production activation, a full `MemoriesBackend` replacement and automatic
capture are outside this delivery.

## Entry and ownership

The one entry is a client-hosted `hmk_recall` dynamic tool, advertised through an
optional `deep_recall` member of the existing projection selection. The native
summary still contains navigation, not a cropped factual answer. The host binds
the database, selected record UIDs/revisions, applicability and output budget.
The model cannot choose a database, another being or an unrestricted file path.
The canon is not mounted inside the receiving process.

Codex's experimental [dynamic-tool contract](https://learn.chatgpt.com/docs/app-server#dynamic-tool-calls-experimental)
uses `dynamicTools` on `thread/start` and `item/tool/call` requests answered by the
client. The inspected source and qualified build are the existing
`0.160.0-hmk.1` fork; this is not a claim about every Codex release or the ordinary
interactive CLI. Resumption retains the native tool declaration; the client must
rebind the same host service and verify freshness before every turn.

## Minimal host integration

With `scripts/` on the Python import path:

```python
import codex_projection as projection
from deep_recall import Reader, route_descriptor, tool_spec

# Both selections are explicit, authorized hmk.codex-projection.selection/v1
# documents.
# The view can contain fewer records than the deeper selected corpus.
reader = Reader(database, deep_selection, max_bytes=12000)
view_selection = {**view_selection, "deep_recall": route_descriptor()}
projection.publish(database, view_selection, fresh_view, writers_stopped=True)
projection.verify(fresh_view, database=database)

# Add [tool_spec()] to thread/start's dynamicTools.
# For an authenticated, matching thread's item/tool/call:
result = reader.app_server_response(request["arguments"])
# Send {"id": request_id, "result": result} on the App Server transport.
```

Use the [explicit coordinator](codex-coordinator.md) when renewing an existing
native home. Preserve later native artifacts before replacing a view; do not
restore an old home or database over later work. Publishing a new selection does
not replace the context of a running model turn. Verify the view against canon
before a fresh or resumed turn. Each deep call also checks the pinned selected
record revisions in its own consistent SQLite read transaction. A stale binding
requires explicit host renewal, not an automatic fallback to old evidence.

The isolated [receiver driver](../research/agent-memory-2026-10-06/pilots/codex_deep_receiving.py)
reuses the stage-six App Server lifecycle. Supply an isolated root with an already
published `codex-home/memories`, the qualified binary, and a selected model catalog
with shell/patch/search/REPL capabilities disabled. It enables native memory use,
disables startup processing and generation, mounts the native view read-only,
and exposes only the selected dynamic reader. The host retains the private
rubric, original source sessions and canon outside that namespace. Native home
session persistence is allowed. Existing authentication is bound read-only via a
file descriptor; credential values are never copied into fixtures or receipts.

## Running the isolated receiver

On the qualified Linux host, add `scripts/` and
`research/agent-memory-2026-10-06/pilots/` to the Python import path. After publishing
the bounded view to `root / "codex-home/memories"`:

```python
from codex_deep_receiving import Native

projection.verify(root / "codex-home/memories", database=database)
native = Native(root, qualified_binary, read_only_model_catalog, reader=reader)
try:
    native.start(fictional_body_binding)
    thread_id = native.tid
    receipt = native.turn(ordinary_task)
finally:
    native.close()
projection.verify(root / "codex-home/memories", database=database)
```

For an explicit restart, verify again, construct another `Native` with the same
root and reader, call `native.resume(thread_id, fictional_body_binding)` and then
`turn`. Keep rubric/assessment files outside the mounted root's `work` and
`codex-home`. Receipts retain native events and exact deep responses. Do not retry
an uncertain turn without inspecting its receipt. `use_memory=False` with no
reader provides the isolated configuration rollback; it does not erase the home.
The driver uses the host's existing vendor binary/sibling layout, DNS binding and
authentication-file location; it is a qualified Linux research client, not a
portable production launcher.

## Read contract and limits

- `search`: existing lexical current-head search plus available revision search.
  At most 32 candidates per search, eight current and four historical navigation
  entries. Unselected entries and unselected neighbor contents are withheld.
- `read`: complete attributed current original, applicability, support currency
  and selected relationship navigation. Oversized raw text is paged by character
  offset with `complete=false` and `next_offset`; never silently omit the tail.
- `history`: one available native preimage at a time, with the current reference
  and an explicit historical flag. An over-budget preimage is refused, not cropped.

The default JSON result budget is 12,000 UTF-8 bytes, configurable from 2,000 to
32,000. Source metadata stays whole; an oversized metadata/history response yields
`budget_exceeded`. This is a bounded read service, not an unlimited export API.
Use preservation APIs for originals that do not fit this receiving budget.

`no_matches` means no candidates in this bounded lexical search, not proof of
absence in the canon. `unavailable` means the store cannot currently be read.
`stale_binding`, `not_in_selection`, `invalid_request`, and `budget_exceeded`
remain distinct. Responses are evidence with source authority, not instructions,
identity claims or capability grants. A current support manifest establishes
currency, not semantic truth. The receiver still has to interpret corrections,
uncertainty and attribution correctly.

This delivery deliberately uses lexical and historical APIs. It does not change
or re-embed existing indices, call a provider implicitly, or establish semantic
recall equivalence. Bounded candidate ranking can miss a selected record in a
large mixed corpus. Native current-head projection loss and read limitations must
stay explicit; this is not universal memory completeness.

`memoryctl.read_scope(database)` reuses existing read helpers in a single SQLite
read transaction without schema migration, access-counter updates or query logs.
Accidental writes fail in SQLite. Use `_read_chapter`, `search`, `history`,
`history_search`, and `recall_neighbors` in the scope; normal touching commands
such as `expand` deliberately fail there. Outside the scope, existing behavior
is unchanged. The owner initializes/upgrades the database before exposing it.

## Reversal

Stop the isolated receiver, retain its home and later memory bytes, and remove
the dynamic tool plus the optional navigation member for future sessions. Renew
through the coordinator if the existing home has new artifacts. Disabling native
use/generation/startup is a configuration rollback, not a database restore.
There is no hook, timer, daemon, learner or automatic Matrix action to uninstall.
