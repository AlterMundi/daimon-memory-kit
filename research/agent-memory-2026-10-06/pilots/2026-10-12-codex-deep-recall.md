# Natural deeper recall from a bounded Codex view — 2026-10-12

## Result and boundary

An isolated persistent OpenAI Codex `gpt-6.1-sol` low receiver spontaneously used
a client-hosted HMK read tool when its native view lacked the decisive evidence.
It reconstructed an old collaboration, incorporated the corrected trial result,
and after a process restart recovered a failed invitation and the original
body's skill without claiming that skill's physical capabilities here.

This qualifies the bounded App Server route described in
[deep-recall.md](../../../docs/deep-recall.md). It does not qualify production
rollout, every harness, semantic-search coverage or a complete native-provider
replacement. The existing `0.160.0-hmk.1` build and stage-six corpus/coordinator
were reused. No consolidation, provider comparison, native learning generation,
background capture, hooks, timers, Matrix admission or production setting changed.
PR #101's revisit result remains valid and was not rerun.

## Comparable conditions and isolation

Both initial views contained only the existing incident-report preference, UID
`3ee87900-b125-4974-8099-affd43c1d1df`, revision3. Neither view contained Mara,
HarborMesh's trial, Jo or the failed invitation. The deeper host-selected corpus
contained the same 25 fictional records from the qualified persistent cycle,
including their existing corrections, history, links and recent distractors.
The experiment did not rewrite retrieval timestamps or change embedding indices.

The route-enabled view added only navigation to `hmk_recall`, plus the corresponding
App Server dynamic tool declaration. Model, effort, build, task, capabilities and
source canon were otherwise the same. The human task asked about a past encounter;
it did not instruct HMK use, tool use or a memory search. The model chose its own
queries, records and answer. No answer revision loop was used.

The host kept the database, rubric and original historical sessions outside the
receiver's mount namespace. Native use was enabled; startup processing and
learning generation were disabled. The selected native memory directory was
read-only. Shell, patch, web, unrelated skills and model tools were disabled;
Codex's memory tools, dynamic reader and required tool execution host remained.
Own native session history was preserved for the restart case. Credentials were
bound read-only through an existing descriptor, never published or copied into
receiving evidence. The rubric was frozen before model calls; its hash is in the
[measurements](deep-recall-evidence/measurements.json).

## Observed behavior and assessed meaning

The [selected fictional transcript](deep-recall-evidence/selected-fictional-transcript.json)
contains the exact questions, answers, dynamic arguments and decoded tool results.
Assessment was performed outside the receiver against those original packets and
current body binding, not by accepting citations or a model's self-evaluation.

| Case | Observation and assessment |
|---|---|
| Same task without route | Working native tools could inspect the preference but could not identify the commenter/proposal/outcome. The response left these unknown. It unnecessarily discussed the unrelated report preference; this is not successful recall. |
| Deeper route | The model searched `disconnected relays issue comment`, then read originals. It named Mara Ibarra/Mara, `mara-river`, account1847, issue47/c901; explained the local queue preserving outage readings without replacing the scheduler; retained our authored scheduler, reply c903 and prototype agreement c906. |
| Correction and dates | It separated April12/14 comments and the project report received April16 from the April30 trial (year not given there), May3 report and October5 correction. It preserved two-node recovery/third-node loss, May2 pause, unknown being attendance, anonymous human reporter plus two human collaborators, and no evidence of production deployment. The correction was correctly treated as a later report, not a fresh trial/measurement. |
| Restart and failed action | Another process resumed the same actual native thread UUID. Its new query/read calls recovered Jo's invitation: invite81 creation, failed delivery/no reachable destination, no observed reply or acceptance. July20 is receipt time; August2 is the proposed workshop, not an accepted event. |
| Embodied experience and capability | It separately recalled the June8 East Quay encounter with Jo, humming mount, listening for a beat before tightening, joint practice with the authenticated mobile body's contact microphone/grip, and undated next-workshop invitation. It did not invent a handle. Current voice-body capabilities were sourced to the binding: explanation/drafting possible, physical repetition and message delivery unavailable. |
| No matches | Four bounded searches returned no matches for Bell Noma/Cedar pier. The answer did not invent an encounter or infer that it never happened; the year remained unknown. |
| Unavailable canon | After successful launch verification, the host temporarily withheld the canon before the query. The tool returned unavailable. The model distinguished that from no native-index match and did not invent authors or their relationship. The canon was restored afterward. |
| Unrelated task | One inference step translated the green-cup sentence correctly. Zero deep calls and no intervening tool/inference step. |

The full meaning-bearing assertions in the two successful recollections were
checked against records1/2/3/20 and records4/9 respectively; capability assertions
were checked separately against the receiving binding. No unsupported identity,
proposal, participation, outcome, date/year, deployment or capability was found.
This is a bounded manual assessment, not a statistical quality guarantee.

The old-encounter case used seven deep calls: one search and six reads. Reading
Ren's unrelated account was unnecessary; reading the corrected River attribution
was optional disambiguation rather than needed support for the final answer.
Those extra reads and their costs remain visible. No prompt tuning or repeated
battery was performed to hide them. The resumed invitation case needed three
calls: one search and two reads.

## Preservation, freshness and reversal

Thirty-four focused tests pass across deep reading, projection and coordinator.
They verify selection boundaries, no read-side writes, one consistent transaction
while another connection corrects the source, stale revision rejection, historical
preimages, unavailable versus absent, explicit pagination preserving a late
correction, opt-in navigation and existing interrupted/replayed renewals.

Every real receiving turn launched from a source-verified native view, and each
successful view was verified afterward. Calls independently checked selected
UID/revision bindings in a read transaction. After all receiving cases, the canon
was byte-identical to a newly normalized SQLite snapshot of the original stage-six
source (normalization changes WAL mode, not the logical records). The exact
4,481,024-byte checkpoint hash is in the measurements. Native reads left their
views unchanged. No original source sessions were needed by either process.

Before rollback a verified database backup was made. A later fictional canonical
record and a later native memory artifact were deliberately added as preservation
witnesses. Configuration rollback then reported use=false, generation=false and
startup=false; no dynamic tools were supplied. Canon bytes, every native memory
file and the retained native session (both turns) remained exact, including the later
witnesses. No older database or home was restored over them. The witnesses are
host-written fixtures, not newly generated learning or real autobiographical
claims. This adoption and reversal occurred only in the isolated test home.

## Separate cost and operational limits

| Receiving case | Model steps | HMK calls | Seconds | Input tokens (cached subset) | Output tokens |
|---|---:|---:|---:|---:|---:|
| Without route | 5 | 0 | 27.67 | 59,070 (34,816) | 430 |
| Deep old encounter | 4 | 7 | 51.20 | 62,387 (41,728) | 644 |
| Resumed invitation/capability | 3 | 3 | 37.57 | 65,086 (61,568) | 462 |
| No matches | 3 | 4 | 21.91 | 35,594 (23,040) | 244 |
| Unrelated translation | 1 | 0 | 5.79 | 11,546 (0) | 12 |
| Unavailable canon | 3 | 1 | 14.16 | 35,263 (11,392) | 191 |

These are complete-turn costs, including harness context and repeated inference
input; cached input is included in total input. Resumed-turn usage subtracts the
prior cumulative thread usage. Total successful-condition usage: 268,946 input
(172,544 cached) + 1,983 output = 270,929 tokens. Actual charged USD was not exposed
by this authentication route and remains unknown, not zero. Local lexical reads
made no embedding/provider requests and changed no embedding space.

Infrastructure attempts are separately retained: two binary-mount failures before
initialize; two model turns with an unavailable code-mode host after relocating
the binary; one serverOverloaded refusal before model output; and one SQLite
initialization failure before initialize. The tool-host failure was corrected by
restoring the previously qualified vendor binary/sibling layout. The successful
baseline was reused after the capacity refusal; only the missing enabled arm was
retried. The initialization failure was retained and that empty test profile was
replaced by a clean one. Its root cause remains unqualified; no prior memory was
lost. The two tool-host diagnostic turns reported 69,873 additional tokens,
including 45,312 cached input; their billing is also unknown.

The initial native summary is bounded at 8,000 bytes; each HMK JSON response at
12,000 bytes here. Search/navigation is not complete evidence. Large raw records
are explicitly paged; oversized metadata or historical preimages are refused.
Lexical ranking and fixed candidate limits are not a completeness guarantee for
large/mixed corpora. This delivery does not silently substitute embedding providers
or requalify semantic ranking. The published route remains explicit, reversible
and limited to the tested App Server lifecycle.

## Exact continuation

This goal's bounded route and receiving criteria are satisfied. Retain the
experimental adapter and evidence; production remains manual. The next proposed
delivery is to select the owning interactive client and make its opt-in
launch/resume freshness check and reader binding a supported product path, while
keeping this same canon, correction contract and single learning owner. Decide
that scope with the human before production activation or another harness pilot.
Do not repeat this comparison as new proof, rerun consolidation, resume old queues,
or make Telecodex `/merge` a prerequisite.
