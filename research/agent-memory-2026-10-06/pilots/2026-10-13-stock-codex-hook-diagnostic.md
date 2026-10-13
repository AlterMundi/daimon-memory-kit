# Stock Codex lifecycle capture: observed boundary

This is the first delivery of [HMK #12](https://github.com/nicoechaniz/hermes-memory-kit/issues/12), under #11. The human activated the portable-producer goal on 2026-10-13. The event boundary is demonstrated; durable delta intake, automatic selection, source-free HMK recall and full fault qualification are still pending. No production hook or native learner was enabled.

## Actual route and findings

The installed official `codex-cli 0.162.1` ran with OpenAI `gpt-6.1-sol`, low, in a persistent isolated home. Private homes, sessions, skills and memory were hidden by the existing bubblewrap receiver. Only a fixed fictional `message_send` tool was exposed; it always returned `authentication_failed`, `delivered=false`, no receipt, attempt `send-77`. Native memory use/generation were off. The resulting native memory database contained zero stage-one outputs and zero jobs.

The first stdio run established ordinary Stop and compaction snapshots. The second ran the stock App Server Unix listener through the **stock `app-server proxy` and WebSocket framing used by Telecodex**, not `codex exec`. It observed successful SessionStart, UserPromptSubmit, PostToolUse, Stop, PreCompact, PostCompact, Interrupt and SessionEnd hooks. After closing the owned process, a separate process resumed the same fictional thread and accurately reported the failed invitation and lack of a delivery receipt. This is session continuity evidence, not durable HMK recall.

- Stop's snapshot contained both the current human prompt and final answer.
- PostToolUse's snapshot contained the actual failing dynamic-tool result. This demonstrates this tool path, not universal coverage of nested tools or internal writers.
- UserPromptSubmit's snapshot did **not** yet contain that turn's prompt. The prompt was in the hook payload. A transcript-only capture here loses input.
- Compaction snapshots retained earlier original conversation items. Capture must distinguish originals from compacted/quoted context rather than treating summaries as new experiences.
- Explicit archive invoked SessionEnd. An abrupt kill cannot be assumed to run this hook; earlier durable capture and reconciliation remain necessary.
- All source bytes observed by the diagnostic were retained locally. The [public receipt](stock-hook-evidence/lifecycle-receipt.json) carries hashes, coverage observations, actual answers, event statuses and usage counters; it is a selected report, not the complete transcript archive.

The [official hook contract](https://learn.chatgpt.com/docs/hooks) and pinned `rust-v0.162.1` source support the lifecycle interface. This does not expose the separate native extractor's commit. Source inspection also established a protected physical socket behind a rendezvous symlink; the isolated proxy mounts its own short socket directory, never the production control socket. No daemon installation or bootstrap is performed. The receiver explicitly disables remote control for the experiment.

## Failed attempts and costs

The first stdio probe's UserPromptSubmit handler durably wrote its observation but exceeded its configured three-second timeout. The experiment driver then attempted to interrupt immediately after turn/start's acknowledgment and received `no active turn to interrupt`; shutdown subsequently produced Interrupt and SessionEnd observations. The corrected proxy probe waits for turn/started before interruption. Neither failure is hidden or counted as a passing full run.

Initial proxy startup attempts exposed namespace/symlink and Unix path-length assumptions in the test driver. They made no model calls. The corrected driver maps only its disposable physical socket directory and waits for that socket, reusing the persistent profile and stopping owned processes. The evidence directory and source histories were not replaced.

Observed hook durations ranged from 46 to 7,480 ms across both runs. The proxy run's handlers completed within their configured budgets (10 seconds for ordinary events, three for Interrupt/SessionEnd), but this is **not an efficient production overhead result**. The proposed durable handler must measure its own I/O separately from native dispatch overhead and avoid redundant work per tool or per turn.

Ordinary model usage counters total 8,895 tokens for the stdio turn and 27,334 cumulatively for the proxy conversation including restart (8,704 cached on the restart call). Compaction changed `last` counters without incrementing cumulative totals; those numbers are retained as observed and are not claimed as additional billed-token measurements. Billing and any unreported compaction/transport usage remain unknown. The capture handler itself made no inference calls.

## Reproduction and next step

Use `codex_hook_probe.py --out NEW_PRIVATE_DIRECTORY --binary STOCK_CODEX --catalog TOOL_DISABLED_MODEL_CATALOG`. It extends the previously qualified isolated receiver, discovers hooks, explicitly trusts their hashes **inside that home**, exercises the fictional dynamic tool and lifecycle, then restarts/resumes. It uses the existing authorized authentication file read-only; never publish credentials or the whole output directory. The model catalog must meet the existing isolation checks. The experiment root must be new to prevent overwriting evidence; do not rerun an already valid comparison.

A framed-I/O test covers masked client requests, fragmented responses and interleaved ping/pong. Actual model calls above qualify the native transport; passing the unit test alone would not.

Exact continuation: implement a quick durable delta/payload handoff with distinct capture and processing progress, then run the portable selector through existing CaptureLedger/writer APIs on the retained qualified sources. Measure native dispatch versus handler I/O, pending-work recovery, correction/replay and source-free spontaneous HMK recall. Reuse this event evidence; do not rerun broad lifecycle/model comparisons or native fork builds. Production CompAII/Eko/Oliva remains unchanged.
