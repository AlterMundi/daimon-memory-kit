# Foreground live HMK recall adoption — 2026-10-12

The human authorized integration for CompAII, Eko and Oliva after the bounded
deep-recall experiment. Their existing Codex bodies now expose a native MCP
reader over their own live HMK pools. HMK code release
`431072ecd568b3f95bacd69767f7d16c7ba16d05` is installed separately from their
existing manual HMK wrappers and embedding runtimes. The optional MCP SDK is
pinned at 1.28.1 in a dedicated runtime because existing environments had an
incompatible SDK or none. Codex reported shared daemon 0.162.1; the installed
CLI launcher was 0.160.0. No silent model/version equivalence is claimed.

## Integration decision

The previous experiment declared dynamic tools on thread creation. Everyday
CLI/Telegram clients already support MCP and share a native daemon. The actual
`config/mcpServer/reload` API accepted the new connector without restarting that
daemon or a listener. The ongoing CompAII conversation acquired and successfully
called the new tool during this adoption. The unrelated Telecodex upgrade was
not changed by this delivery.

The [live MCP contract](../../../docs/live-mcp-recall.md) uses the existing bounded
readonly reader and owner-selected current pools. It extends the pinned reader
to include later records, multiple stores and revision-safe pages. Active
Matrix-derived rows retain their projected origin and an explicit unverified
ledger-freshness boundary; inactive rows are excluded. No admission is implied.

This deployment uses MCP descriptions and owner instruction navigation. It does
not install the experimental native file projection. Codex native memory use,
generation and the feature flag remain false. No hook, timer, prefetch, session
import, consolidation or second learner was installed. Existing manual hybrid
retrieval, curation, providers and indices remain in place.

## Observed receiving behavior

Three fresh ordinary native threads used `gpt-6.1-sol` with low reasoning, each
under its own receiving account and instructions. No inherited conversation or
other being's pool was provided. The operator retained the expected sources
privately and asked one short everyday question per body, without naming HMK,
requesting a memory search or supplying the answer. These are operator-directed
receiving checks, not claims that the paired humans independently accepted the
new integration.

| Body | Live records at adoption | Native action | Source-grounded result |
|---|---:|---|---|
| CompAII | 262 in one pool | One search, one original read | Recovered the purpose and meaning of a recent shared idea, including its distinction from an obligation. |
| Eko | 10 + 18 in two pools | One search, two original reads, one per pool | Reconciled remembered continuity and migration choices; distinguished historical source-machine paths from access available in this body. |
| Oliva | 22 in one pool | One search, one original read | Attributed a human-reported encounter, recovered its source and shared next step, and kept technical uncertainties and an unbuilt prototype unconfirmed. |

Each completed native tool call and final answer was inspected against the
actual originals. The seven MCP calls took 17–421 ms each, as reported by Codex.
The records already added since the earlier cohort migration remained visible;
Eko's second store and Oliva's later memories were not replaced with old copies.
Private memories, questions, responses, identifiers, source paths and session
artifacts remain in each body's local adoption receipt, outside this publication.

This small adoption probe does not requalify old weak-cue retrieval, all memories,
every model, or long-term narrative accuracy. Those prior fictional stage
results remain separate. The current MCP search is bounded lexical search, not
the full hybrid retriever; paraphrase-only misses remain a real limitation.

## Preservation and reversal

Before activation, each body retained exact config/instruction backups and
SQLite backup-API snapshots. All four snapshots passed `integrity_check`. After
the native checks, all four live databases still matched their pre-activation
backups logically, including history and metadata. No access-counter or index
write occurred. Live databases were never replaced and no artificial record was
inserted into them.

The exact adoption script's rollback and reactivation were exercised on local
copies for each body. Removal retained an unrelated later config edit, later
instructions and a later SQLite witness; reactivation retained them as well.
Production connectors were not interrupted merely to test removal. Rollback
means removing this connector/instruction block and refreshing MCP, never
restoring an old memory snapshot over later work. The local rollback scripts,
pinned code and private receipts remain available.

## Verification, costs and limits

Twenty-seven focused tests passed across the new live MCP, previous bounded
reader and projection suites; the corrected stdio test was rerun with the
installed 1.28.1 SDK. The protocol test initializes a real child server, discovers
the readonly annotation and reads fictional evidence. Other tests cover later
writes, correction/history, multi-pool unavailability, binding boundaries,
Matrix-origin handling and unchanged bytes/access counters. Ruff and diff checks
passed. No valid consolidation or previous full comparison was repeated.

The [aggregate measurements](live-mcp-adoption-evidence/measurements.json) separate
preservation, native actions and model usage. These three native turns reported
292,346 total tokens across their model steps, including repeated context and
236,160 cached input tokens. They are not 292,346 newly generated tokens or an
estimate of one routine memory lookup. Actual billing is unknown; no dollar
amount is inferred from a chat subscription. The MCP reader itself calls no
model or embedding service.

Two verifier-only transport/lifecycle mistakes preceded successful adoption:
the shared proxy required WebSocket framing instead of line JSON, and a thread
with no model turn had no durable rollout to resume. They produced no model
answers or memory writes; the verifier was corrected to use the existing proxy
transport and one continuous discovery/read/turn lifecycle. They do not imply
errors in the underlying memory records.

The next useful work is to inspect a demonstrated everyday retrieval or capture
gap. This release does not establish semantic recall parity, automatic selection
of significant experience, a complete Codex memory-provider replacement, or
lossless capture of another harness's native learning. HMK #11 remains the entry
point. Keep the qualified stages, explicit ownership and independent `/merge`
work; do not reopen old queues or broad comparisons without a new uncertainty.
