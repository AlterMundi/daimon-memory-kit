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
