# Finite portable HMK producer

Experimental implementation for [HMK #12](https://github.com/nicoechaniz/hermes-memory-kit/issues/12), under [#11](https://github.com/nicoechaniz/hermes-memory-kit/issues/11). Production automatic learning remains disabled. The stock Codex hook adapter is described in [codex-hook-capture.md](codex-hook-capture.md).

## Ownership and invocation

Codex hooks only persist bounded source snapshots and event payloads. They do not run inference or a child expected to survive shutdown. The foreground operator, or an explicitly configured owning launcher, invokes `portable_producer.process_once` after capture and invokes it again to resume. One invocation processes at most one batch. There is no installed listener, background worker, timer, polling loop or source scan. This delivery qualifies the finite worker, not an unattended scheduler or production installation.

The portable processor accepts an existing `capture_inbox.Inbox`, the receiving HMK module, one persistent state directory, a caller-supplied stateless proposer and an explicit subject/body context. The current source normalizer understands Codex text response items; the coordinator, journal and writer are separate from that harness representation. Another harness needs its own source adapter and qualification.

For an isolated fictional profile, the reproducible DeepSeek transport wrapper is:

```bash
python research/agent-memory-2026-10-06/pilots/portable_producer_trial.py \
  --fictional-isolated-profile \
  --inbox /isolated/capture.sqlite \
  --binding /isolated/capture-binding.json \
  --context /isolated/context.json \
  --canon /isolated/agent-memory \
  --state-dir /isolated/producer \
  --limit 32 --output-token-limit 12000
```

The caller supplies `DEEPSEEK_API_KEY` in the process environment through its established credential facility. Never place a value in this command, repository or transcript. The wrapper neither discovers credentials nor installs itself. Context contains the matching `subject` and `source_instance`, with optional fictional lived name and paired human. The binding is the same immutable binding used to capture. The selected destination is explicit, not taken from incoming source content.

The model is `deepseek-flash`, reasoning low, stateless text-only JSON, no tools or inherited context. The wrapper's conservative default output ceiling is 6,000; the closing trial explicitly selects 12,000 after one 6,000-token request exhausted its reasoning allocation without an answer. A ceiling is not a fixed token charge. OpenAI Codex `gpt-6.1-sol` low is used separately for isolated receiving conversations. Embedding configuration is unchanged; new records can be lexically ready while embeddings remain pending. This trial does not claim semantic-index maintenance or search parity.

## Processing and recovery

An inbox is bound to one canonical destination and coordinator directory. A separate advisory lock permits capture to continue while preventing concurrent processors from owning independent cursors. A batch freezes observations, exact source revisions, code hash and context binding before inference. The latest captured revision of each selected source can support an earlier boundary event, including a prompt that had not yet reached its transcript; later observation cursors still remain pending until processed.

The processor reconstructs and checks exact source dependencies on every resume. It records the unmodified model proposal before validation. Existing `CaptureLedger` then commits selected records, links, the terminal decision and progress atomically; an existing preserved-artifact envelope stores exact originals and formation evidence with selected memory. A verified SQLite snapshot precedes canonical intake. Replay after an uncertain canonical commit uses the same frozen proposal and stable event, without calling the model again or duplicating writes. A lifecycle-only batch invokes no proposer. Omitted source payloads stay in the separate processing evidence rather than becoming permanent canonical artifact bundles.

The DeepSeek wrapper retains requests and dispatch receipts. A completed successful response is reused. A failed, unresolved or truncated response is not silently retried. An explicit `--retry-of HASH` can preserve that attempt and dispatch into a separate retry directory, optionally with a different output ceiling. Its additional cost is recorded. `--reprepare-reason TEXT` archives a **pre-stage** frozen job when a representation change or invalid proposal requires new preparation; its source cursor does not advance. It cannot replace an event already staged in CaptureLedger, including an uncertain successful commit. Resume such work with its original writer, or perform an attributed repair; never discard its journal to unblock a queue.

Incomplete sources, unsupported response items, oversized batches and missing early prompts remain visibly pending. This qualified native source profile is append-only: an out-of-order older snapshot or divergent rewrite cannot hide an intermediate acknowledged version or reset the novelty baseline. It defers until a complete reconciled capture covers the pending versions; original branches stay retained. Arbitrary destructive transcript rewrites need a separately qualified reconciliation adapter. Source capture is bounded to the binding's ceiling; processing budgets each invocation by observation count (up to 128) and complete source windows (64,000 bytes by default), retaining unfinished source progress. An indivisible causal closure remains pending with its required budget; no whole-history 1 MiB limit applies. The new navigation path removes the former 256-record / 512 KiB all-canon loading limit; its integrated qualification is tracked in [#113](integrated-memory-plan.md). Corpus size is no longer the prompt admission criterion. A blocked head is not skipped automatically. A missing/corrupt dependency must be recovered from preserved evidence, not marked complete. Abrupt death can prevent a lifecycle hook entirely; capture receipts prove observed captures, not that every possible unsignalled final byte was captured.

## Resumable canonical navigation (in qualification)

`process_once(..., navigation_steps=4, retrieval="hybrid")` permits at most four
additional selector dispatches per invocation. `selection_navigation` exposes
only the existing bound read API through a closed JSON lookup request; it grants
no model access to external tools, credentials or another pool. Search returns
navigation, never complete factual support. Read all original pages before an
update or a link to an existing record. Historical hits distinguish their old
revision from the current revision needed for a safe read.

Each request, successful response and lookup result is checkpointed. Exhausting
this invocation's step budget returns `state=pending`; reinvocation continues
without replaying successful calls or advancing the capture cursor prematurely.
An unread target is rejected. Read revisions are rechecked in the writer
transaction. A changed source after staging is preserved as failed pending work;
its reconciliation path is still being implemented and is a blocker for rollout.

Hybrid mode uses existing configured embeddings and ranking. The receiver's MCP
binding may explicitly set `retrieval: hybrid`; its default remains lexical.
Neither mode writes access counters or migrates the database while reading.
Unavailable embedding services are reported separately from lexical misses.
This does not yet implement index maintenance or prove semantic coverage.

## Selection, attribution and feedback

The model selects original source IDs and existing memory references, not generated factual summaries. `source_selection` reuses the qualified source-block writer. Exact quoted evidence retains speaker/channel, originating body, receipt timestamp and stable source identifiers. Every proposed title must be a recognition phrase present in its selected evidence. New records whose evidence is already covered by another selected record coalesce without losing aliases or source meaning. Existing memory source references accept the supplied local integer ID or stable UID; neither resolves unread external content. Native writers retain revisions, identity, provenance and links.

Normalization supplies causal dependencies: a tool reply retains its call and world pointer; a subsequent statement retains the turn's date/context and the preceding recalled memory where needed to interpret a correction or revisit. Retrieved memory has an explicit context channel and cannot be selected as new intake evidence. It may accompany a genuinely new source as attributed supporting context. Reading a record, or comparing revision numbers from different namespaces, does not justify a new episode or canonical update. The current known recall-tool names are `hmk_recall` and `mcp__hmk__hmk_recall`; other memory-returning tools require explicit adapter support before equivalent feedback protection can be claimed.

The source bundle preserves model rationale as generated decision evidence. That rationale is not a historical assertion or a verified summary: even a structurally valid selector can explain its decision inaccurately. Recall uses retained source blocks, not the rationale. Structural checks do not establish semantic quality; hidden receiving evaluation remains necessary.

`source_selection.READING_GUIDANCE` supplies the tested interpretation contract: preserve human reports, assistant claims, tool outcomes, other beings' experiences, date precision and current-body capability boundaries. Cite evidence while narrating meaning. `deep_recall` additionally renders exact UTC local-storage timestamps alongside original epochs, to avoid asking a language model to perform calendar conversion. Neither storage dates nor receipt timestamps replace occurrence dates.

## Preservation and rollback

The source inbox, frozen jobs, original dispatches, canonical history and artifact envelopes have distinct responsibilities. Removing a source session after verified capture does not remove retained evidence. Copying the inbox or an artifact neither admits Matrix events nor grants identity or capabilities. Existing authority boundaries remain unchanged.

To stop this isolated experiment, restore or disable only the selected hook/launcher configuration, retaining its prior version. Leave the inbox, pending jobs, canonical database and later writes in place. Restoring a pre-install memory database would discard later learning and is not a configuration rollback. The isolated stock proxy rollback probe verifies an empty hook listing and unchanged capture/canonical hashes after a real learned record existed. No production CompAII, Eko or Oliva configuration is changed by these commands or documentation.
