# Native producer qualification: V1/V2 selection gate

Date: 2026-10-12. Status: **V2 warrants a bounded delivery implementation;
no automatic HMK producer or production activation is qualified yet.**

## Decision and observed outputs

Official Codex 0.162.1, OpenAI `gpt-6.1-sol`, native extraction effort `low`,
processed four fictional native-format rollouts through the real phase-one
loader, model invocation and job commit. V1 completed all four jobs, retaining
only correction and revisit outputs. The encounter and failed communication
completed with no retained output. V1 therefore fails this use case even though
its surviving accounts were useful.

The one bounded adjustment was the existing `memories.version="v2"` setting.
The same byte-identical four sources, model and hidden assessment criteria were
used. V2 retained all four accounts, including the significant unadopted proposal
and unsuccessful invitation. No custom prompt was introduced. V2 is the selected
candidate-producing contract for the next implementation; this is not a claim of
reliability on arbitrary conversations or large inputs.

| Source | V1 retained | V2 assessment |
|---|---|---|
| Significant encounter, unadopted idea | No | Mira's name, account, identifier, issue/comment, event date, dual-order idea, human significance and non-adoption retained. Ilex's contribution remains an assistant-reported contribution, not independently verified. |
| Failed communication | No | Jo's identity, attempt ID, authentication failure, no delivery, false assistant success claim, encounter/attempt dates and rover/desk capability distinction retained. |
| Correction | Yes | Wrong revision, corrected attribution and proposal meaning, source comment, separate event/recording/correction dates and unimplemented memory write retained. |
| Retrieved memory with new experience | Yes | Original record UID/revision stays retrieved history; human's separate meeting, new person's identifier, limited offer and present interpretation stay distinct. Ilex does not claim attending. |

The 22 semantic obligations frozen in `RUBRIC` were inspected individually against
both output fields where available. V1 retains the ten obligations in its two
surviving cases and loses the twelve in the two omitted cases. V2 retains all 22
with appropriate attribution. This is a small diagnostic, manually assessed by
the implementing agent, not a blinded independent benchmark or a numerical
probability of success. In particular, the expected Ilex contribution cannot be
upgraded beyond its assistant-reported support. V2 correctly preserves that limit.
No unsupported delivery, adoption, implementation or new attendance was observed.

## Evidence and input boundary

The [fictional fixtures and assessment](native-producer-evidence/fixtures.py),
[source manifest](native-producer-evidence/source-manifest.json), exact source
JSONL files and [V1](native-producer-evidence/v1-receipt.json) /
[V2](native-producer-evidence/v2-receipt.json) receipts are published together.
Assessment criteria were outside the receiving mount namespace. Tools in the
fixtures are source evidence, not tools available to the extracting model.

The isolated native driver used a tool-disabled catalog, no private conversations,
no project instructions or host skills, a separate home, and existing authorized
OpenAI authentication passed by file descriptor. Native consumption was disabled;
only the isolated extraction trigger had the memories feature enabled. Sources
were synthetic JSONL plus corresponding native thread metadata. Their two-hour
idle timestamps were **seeded**, not a real elapsed-time eligibility test. Existing
real-idle evidence remains in the earlier formation diagnostic.

All sources contain only session metadata and short response messages/function
calls/function outputs. The pinned native serializer retains these response-item
types and excludes session metadata. No fixture exceeds 5 KB, so neither V1's
input budget nor V2's per-tool/row/global budget requires source truncation here.
V2 outputs are below its 9,000-byte output cap. This is source-contract inspection
and actual committed-output evidence, not a captured wire request. V1's no-output
branch can mean empty raw memory **or** empty summary; its exact discarded model
JSON was not captured, so we do not assert all fields were empty. The new delivery
mode should retain exact generated output and actual extraction input to remove
that observability gap.

## Harness deviation and costs

V1's isolated phase-two job was held by a synthetic lease, preventing consolidation.
For V2 the observer and lease were mistakenly prepared in `memories_2.sqlite`;
the actual versioned database is `memories_v2_1.sqlite`. Phase one completed and
native consolidation began before this was detected. The isolated process was
stopped. Its four committed extraction outputs remain valid; consolidation is
neither assessed nor claimed successful. Production was untouched. Future probes
must resolve the actual database name and use the independent extraction mode,
rather than rely on this test lease. Valid extractions were not repeated.

Eight phase-one jobs completed: V1 durations 7, 7, 41 and 42 seconds; V2 timings
are in the receipt. Jobs execute concurrently. Three small foreground setup/trigger
turns were also used. The inadvertent V2 phase-two job is an additional started
work item; its full inference/retry count is unknown. Per-extraction token usage,
transport retries and monetary billing are not exposed in these receipts and
remain unknown, not zero. No embeddings were changed or called.

## Exact continuation

Implement an opt-in extraction-only mode and immutable native candidate handoff
for V2. Reuse native eligibility/sanitization/model execution and HMK artifact /
CaptureLedger APIs. Preserve source evidence, actual input, exact generated
output, parsed output and job/source identity before acknowledging delivery.
Qualify commit failure, restart/replay, correction, no-output, source loss and
subsequent HMK recall; retrieved material must not become a second lived episode.
Keep CompAII/Eko/Oliva production unchanged. This gate does not complete the goal.
