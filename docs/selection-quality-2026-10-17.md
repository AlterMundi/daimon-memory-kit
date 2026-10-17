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

- A standalone Codex `environment_context` frame was treated as a human report
  and became the causal opener of later activity. It now has the same context-only
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

One stateless DeepSeek Flash low request received six fictional source reports,
without the rubric, tools, other conversations or private memory. The existing
policy omitted temporary pause, build-status and test/merge instructions. It kept
the introduction/proposal, failed contribution with its correction, and a specific
learned verification method. Source validation preserved the reports and linked
the failed contribution to its encounter. No policy change was warranted by this
bounded diagnostic. It does not explain all overly operational live selections.

The call used 4,595 reported tokens (1,932 prompt, 2,663 completion), took 13.82
seconds, and has unknown USD billing. Inputs, response, hidden evaluation criteria
and costs are in the [fictional evidence](../research/agent-memory-2026-10-06/pilots/2026-10-17-selection-quality-diagnostic.json).
Mechanism checks passed: 29 focused tests, including exact attribution, unchanged
raw reads, historical separation, scope, response budgets and source closure.

## Remaining acceptance

The live excess of operational selections needs its own frozen-packet comparison:
inspect one retained questionable decision and the complete context it actually
received, then change only a demonstrated cause. The six clean reports are not a
substitute for that receiving evidence. No new prompt variant, broad benchmark,
reindex, noise admission or repeated completed consolidation is justified here.

Pending producer jobs retain their original inputs and completed dispatches. An
upgrade requires the existing explicit navigation-preserving reconciliation;
it must not silently renormalize already frozen evidence or reset correction
budgets. Configuration rollback restores code references, not old databases over
later memories. Existing native sessions may retain their loaded reader until a
normal restart; installing a release alone does not establish receiving use.
