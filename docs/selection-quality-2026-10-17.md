# Bounded selection and navigation diagnosis — October 17

Continuation of [#11](https://github.com/AlterMundi/daimon-memory-kit/issues/11).
This separates a corrected test interpretation from demonstrated product changes.

## Comparable retrieval did not justify an index change

The retained null query was logged at epoch 1792200367. The later relevant proposal
record was created at 1792200530, 163 seconds later. The earlier encounter existed,
but the later named-query result included evidence unavailable to the first query.
The original miss remains evidence; comparing those queries is not a controlled
before/after retrieval test.

On one verified later corpus, the same weak query, clock, provider/model, 0.4
threshold and token budget returned the later episode both before and after a
candidate quoted embedding projection. Its score was 0.4444 in both conditions.
Only the earlier record's vector changed on an isolated copy. Two embedding calls
(one shared query, one candidate passage) took 0.26 and 0.32 seconds; billing is
unknown. No retrieval benefit was established. The candidate was **not adopted**.
Canon, existing embeddings, ranking and thresholds remain unchanged.

## Demonstrated corrections

- Standalone Codex `environment_context` and goal-lifecycle receipt frames were treated as human reports
  and could become the causal opener of later activity. They now have the same context-only
  treatment as the existing framed instruction message. Originals stay in the
  captured source. Ordinary prose discussing the frame remains selectable.
- Search previously offered a generic quoted title without useful recognition
  context. Native navigation now optionally includes one contiguous, decoded
  dialogue excerpt with its exact original header, offset and omission flags.
  This is navigation, not a summary or proof. An assistant statement stays an
  assistant statement. Unknown/mixed formats and tool payloads are not interpreted;
  full reads and revision checks remain required. Optional excerpts are removed
  when they would exceed the existing response budget. Historical hits never
  receive current text.

For the retained 27,002-byte encounter, the excerpt exposes the attributed
434-character explanation of proposal versus inspected deployment state, instead
of escaped envelope fragments. This improves recognition, not the ranking score.
No canonical raw text, summary, UID, revision or history is rewritten.

## Selection and costs

The existing policy correctly distinguished six simple fictional reports: it
omitted temporary pause, build-status and test/merge instructions, and retained
an introduction/proposal, a failed contribution with its correction, and a concrete
file-save lesson. That did not explain the live excessive selection.

The retained real decision showed the cause: the selector called a changed goal
and its full execution checklist a durable scope decision. On its exact frozen
packet (including the same previous read results), changing only the policy to
ask what remains useful after the task closes produced omission. The policy keeps
enduring preferences, meaningful contributions, consequential decisions and lessons
grounded in events; these are examples, not a closed list. Calling a new workflow
an improvement does not by itself establish a lasting lesson.

The same six fictional reports under the changed policy still retained all three
meaningful reports and omitted all three temporary ones. Their hidden evaluation
criteria were never supplied to the model. Source validation preserved participants,
uncertainty, reported provenance, the failed result and the specific learned action.
This is one real correction and one bounded contrast, not corpus-wide acceptance.
Existing operational records remain preserved; no retrospective deletion occurred.

Three new DeepSeek Flash low calls used 18,432 reported tokens: baseline fictional
4,595 (13.82 seconds), real candidate 9,950 (5.19 seconds), fictional candidate
3,887 (10.05 seconds). The real baseline was reused from its original retained
completed response, not rerun. USD billing is unknown. Inputs and fictional results,
plus safe real comparison counters, are in the
[diagnostic evidence](../research/agent-memory-2026-10-06/pilots/2026-10-17-selection-quality-diagnostic.json).
Mechanism checks passed: 42 focused tests, including pending-producer preservation,
exact attribution, unchanged raw reads, historical separation, scope, response
budgets and source closure.

## Receiving and remaining limits

The selected real packet and six fictional reports support this bounded correction.
Future meaningful decisions can still be missed or over-selected; a concrete new
example warrants investigation, not an automatic broad benchmark. Retrieval on
the original earlier corpus remains a recorded miss. No reindex, threshold change,
noise admission or repeated completed consolidation is justified by this evidence.

Pending producer jobs retain their original inputs and completed dispatches. An
upgrade requires the existing explicit navigation-preserving reconciliation;
it must not silently renormalize already frozen evidence or reset correction
budgets. Configuration rollback restores code references, not old databases over
later memories. Existing native sessions may retain their loaded reader until a
normal restart; installing a release alone does not establish receiving use.

## Adopted receiving release

[PR #14](https://github.com/AlterMundi/daimon-memory-kit/pull/14) is merged.
Source `04b59a9a84e96dbe44d93675fd631f354a7a1cec` is selected for the existing
worker and native reader on CompAII, Eko and Oliva. Each configured foreground
reader returned a real source excerpt whose quotation, header, UID and revision
were checked against the unchanged original. These are actual receiving calls;
already-running sessions can still retain their loaded older reader until normal
restart. CLI and capture-handler references remain unchanged.

Eko's prepared batch retained all 16 completed navigation steps, its frozen inputs,
source order and cursor. The existing explicit `preserve_navigation` procedure
archived its prior job before reconciling the implementation hash. No worker was
started or model dispatch repeated by adoption. The other two had no prepared job
to reconcile. Configuration backups and reverse substitutions preserve independent
later settings. For worker rollback, inspect any current pending job first: use
the same supported pre-stage reconciliation with the selected previous release;
staged work must finish through its owning writer. Never restore an old database
or archived job over later memories or progress.

Existing reconciliation checks additionally passed: one pre-stage upgrade test
reused retained lookups/proposals, and three revision-conflict/preservation checks
passed. The shared resource catalog points to this release and report.

## Closing weak-cue route check

The automatic-context pack and native navigation have different existing
contracts. On the verified earlier snapshot restricted to the 34 records existing
at the original query time, with that clock and the retained query vector, the
0.4 pack still returned no records. Native navigation offered the relevant earlier
encounter at rank 6, within its existing eight-candidate page. No new embeddings,
threshold change or noise admission were used for this check.

A stateless receiver given that native candidate page chose the correct encounter.
A second call received its complete retained record, not the source session. Its
answer distinguished the proposal, the attributed assistant assessment, actual
returned evidence and unproven implementation. All 18 statements had matching
source content on inspection after decoding transport text; incidental status/PR
facts made the answer longer than the question needed. This is evidence of useful
navigation, not a complete natural-narration acceptance or improved automatic-pack
admission. The strict raw-string citation gate failed on three quotations whose
line wrapping was normalized. That failed gate remains recorded; whitespace
matching is not substituted for semantic validation. Future narration qualification
must reuse the existing passage-based contract rather than repeat this ad hoc
raw-citation adapter.

The two receiver calls used 19,472 reported tokens (1,943 selection, 17,529 answer)
and took 5.99 and 39.04 seconds. Together with the three selection diagnostics,
there were five new DeepSeek calls and 37,904 reported tokens; USD billing remains
unknown. Receiving reader probes used the existing embedding configuration and
have unknown billed cost. No generation call was repeated during recovery or
adoption. Raw receiving packets, responses, failed gate and assessment are private.

**Exact remaining scope for #11:** the original automatic-context pack miss remains
unresolved. Before another experiment, identify the owning consumer that needs
automatic admission for this case; the native read-and-assess route already finds
it. Do not lower admission thresholds, widen the corpus, replay completed jobs,
rerun the rejected embedding projection, or treat a candidate as proof. A further
ranking/relevance change requires a controlled relevant/irrelevant comparison and
an actual benefit for that consumer. Current operational repairs and the bounded
selection/navigation delivery are adopted; full #11 closure is not asserted.


## Navigation CLI and bounded first-account diagnostic

[PR #16](https://github.com/AlterMundi/daimon-memory-kit/pull/16) exposes the
existing unassessed hybrid navigation through `memoryctl.py hybrid-search`, with
stable-record scope and read-only database access. It does not alter ranking or
pack admission. Eight navigation tests passed, including a below-threshold
candidate that remains rejected by the pack while available for inspection.
[Skills #88](https://github.com/AlterMundi/Skills/pull/88) corrects the portable
recall guidance: an empty automatic context pack is not proof of absent memory.
The exact versioned package passed describe/prepare/apply/status qualification.

A query-independent, complete paragraph projection of the earlier encounter
required two embedding calls (12 passages, 1.16 and 0.44 seconds). Its best cosine
was 0.2035; the actual proposal passage scored 0.1938. This does not establish
admission at the unchanged 0.4 threshold. Neither vectors nor projection were
adopted. This closes that diagnostic; do not keep trying projection variants.

Inspection also confirmed that automatic account reconciliation updates existing
inferred accounts; it does not create their first selected account. The existing
explicit consolidation API already supports that operation with source manifests,
revision guards, support links and idempotent application. No new summary sweep
was enabled.

A private first-account diagnostic supplied only the selected complete original,
without the weak query or hidden criteria. DeepSeek Flash generation and native
OpenAI Codex Sol 6.1 low assertion review reused the existing passage protocol.
The first candidate was supported but retained incidental operational inventory:
support alone did not qualify selection. One evidence-grounded revision removed
much of that inventory but retained procedural detail; its review found no
unsupported claims and identified three missing groups of detail. It therefore
failed acceptance. Both candidates, requests and receipts remain retained; neither
was incorporated, indexed or used to manufacture a retrieval pass.

These four calls used 115,303 reported tokens; USD billing remains unknown. They
expose an unresolved selection/completeness boundary for first accounts, not proof
that the existing correction reviewer should discard its preservation guarantees.
Do not retry the same generation or replace the failed verdict with a pass.

**Next bounded implementation:** distinguish the selected meaning of a new account
from preserving all still-supported meaning of an existing account. Reuse the
qualified source/assertion protocol and native consolidation APIs. Account selection
and review must agree on the encounter's purpose while independently checking
participants, contribution, provenance, meaningful results and uncertainty. Test
that useful meaning survives and incidental inventory can be omitted; retain the
original evidence separately. Inspect overlapping existing accounts before adding
one. Only an accepted account warrants the same earlier-corpus, clock, weak-query
and 0.4 admission comparison, with irrelevant controls. No completed consolidation
or producer queue should be replayed. #11 and its native goal remain open.
