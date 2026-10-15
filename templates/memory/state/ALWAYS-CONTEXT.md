# Legacy always-context compatibility note

This template is no longer installed by DMK bootstrap. It is retained only for
explicit standalone dialogue-plugin compatibility. DMK does not inject it.

Use native Hermes session history and goal state for the selected conversation.
Current human direction outranks historical summaries, quotes and engineering
notes. A fresh session, `/new`, explicit resume, compression successor and worker
are distinct events; do not infer conversation ownership from recency/platform.

Do not use shared DIALOGUE-HANDOFF.md or disabled native MEMORY.md/USER.md files
as authoritative re-entry sources. `continuityctl rehydrate` is deprecated and
returns guidance only. `continuityctl show` exposes optional engineering state,
not dialogue. `librarian` and `memoryctl hybrid-pack` supply durable curated recall;
keep `HMK_AGENT_MEMORY_BASE` configured and accept null retrieval.

Foundational identity belongs in the existing concise SOUL mechanism. Review any
old always-context material before retirement rather than promoting it wholesale
into another global store.
