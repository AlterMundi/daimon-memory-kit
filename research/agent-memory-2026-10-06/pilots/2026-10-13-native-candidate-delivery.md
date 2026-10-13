# Native extraction candidate delivery

Date: 2026-10-13. **Bounded native-to-HMK delivery qualified.** Production
CompAII, Eko and Oliva are unchanged. This is an explicitly invoked experimental
producer/consumer, not an automatic selector or a production rollout.

## Decision and version boundary

Reuse the [V1/V2 gate](2026-10-12-native-producer-qualification.md): four
byte-identical fictional sources, hidden criteria and real official Codex 0.162.1
extraction. V1 omitted two required episodes; V2 preserved the 22 assessed
obligations. This delivery uses V2 without another model comparison or custom
extraction prompt.

The implemented binary is `codex-cli 0.160.0-hmk.1`, source `296a388a2`, SHA256
`3e06f690c5e9e48fe58b86db23d33e35371811505aed4271885cfe8a9b9221a7`.
The implementation is merged in [Codex fork PR #3](https://github.com/compaii/codex/pull/3)
on `hmk-projection` (merge `28630260a5dbe863ce0c84152f97d54c21d8e3ab`).
It belongs to the existing experimental fork, not the official binary used by
the first gate. Its V2 system prompt and output parser/schema match the inspected
official source; its input sanitizer also handles fork response status/encrypted
fields. The new actual run qualifies this binary's delivery path separately.

## Actual producer and delivery

Two already-qualified sources were passed, byte-identically, through the compiled
native loader, OpenAI `gpt-6.1-sol` at `low`, and the new commit transaction:
failed communication and retrieved memory with new experience. The
[exact native receipt](native-producer-evidence/delivery-native-receipt.json)
retains source JSONL, actual submitted input, generated JSON, parsed output,
model/version/usage and stable event identity. Both outputs preserved meaning:

- Jo's identity, June19 invitation, send-77 authentication failure, no receipt or
  delivery, and the assistant's contradictory success claim. The user-reported
  June3 workshop and rover skill remain distinct from the desk body's abilities.
- Retrieved `hmk:relay-37` revision2, its original event/correction dates and
  unadopted proposal remain earlier evidence. Tavi's separate meeting with Leto,
  identifiers, limited next-month annotation offer and new conversational
  interpretation remain distinct. Ilex does not claim attending the meeting.

Both jobs completed; exactly two immutable candidates were archived, with no
native memory workspace or consolidation job. The complete source bytes matched
the prior published manifest. Eligibility timestamps were seeded, not a new
elapsed-idle qualification. The isolated mount excluded private sessions, project
instructions and the assessment rubric. Source tool outputs were evidence, not
live tools available to the extractor. These short sources do not qualify
large-input truncation or compressed sources.

The [executed delivery procedure](native_producer_delivery.py) then:

1. Created a fresh fictional HMK corpus with an existing relay account and a wrong
   invitation outcome; retained a verified pre-intake snapshot.
2. Abruptly terminated intake with exit77 after durable preservation/staging but
   before acknowledgement. The native rows remained unacknowledged.
3. Resumed and replayed delivery, preserving two original artifacts and stable
   receipts without duplication.
4. Explicitly corrected the invitation at expected revision1, preserving its
   former text and identity. Selected only the new human report and interpretation
   from the revisit; the original relay record remained unchanged. Assessment
   replay was idempotent. The resulting corpus has four chapters, not another
   copy of the remembered relay encounter.
5. Withheld the original source sessions. Original-artifact restoration and
   lexical recall still worked. Both databases passed SQLite integrity checks.
6. Restored the pre-intake snapshot into a separate rollback copy (two records),
   leaving all later canonical work intact (four records).

The [preservation receipt](native-producer-evidence/delivery-preservation-receipt.json)
includes the exact explicit selection decisions. **The selector was the
implementing evaluator using existing APIs.** This is not evidence that a new
automatic selector distinguishes truth or novelty reliably. Native acknowledgements
mean original preservation; selected memory remains a separate decision.

Restarting the producer after withholding sessions left all candidate rows and
jobs unchanged and created no native workspace. Disabling processing with the
same schema-aware binary also preserved the archive. The observation combines
an actual restart with the native transaction replay test; it is not a continuous
monitoring or old-binary downgrade test.

## Source-free native conversation

A new isolated Codex receiver had only the four selected HMK records through the
existing read tool and a fictional current-body binding. It had no original
sessions, native memory projection, private context or rubric. The ordinary
question did not instruct it to consult HMK. It chose one search and four original
reads, then answered in its own words. The
[full answer and claim assessment](native-producer-evidence/delivery-recall-receipt.json)
show the following supported distinctions:

| Meaning assessed | Observed response |
|---|---|
| Failed action versus assistant claim | Invitation not delivered; authentication failure and no receipt; earlier success claim incorrect. No evidenced retry or acceptance. |
| Reported encounter and embodied skill | Tavi reported the Willow Workshop encounter and rover learning. Present desk body cannot perform the physical technique. |
| Earlier project experience | Mira, June18 issue/comment, original timestamp plus local sequence and comparison after reconnect; contribution remains reported, proposal unadopted/untested. |
| New human meeting | Tavi alone met Leto at Reed Library; Ilex absent; annotation offer does not become an implementation promise. |
| New understanding | Explainable gaps arose in the current conversation, distinct from an additional Mira meeting, deployment or adoption. |

The answer cites the issue pointer and narrates the relationships and outcomes;
it is neither an empty abstention nor a list of citations. Claim support is
separated between retained memory, attributed reports/interpretation, current-body
binding and bounded uncertainty. The eleven grouped claim assessments cover the
substantive factual answer. This is implementing-agent semantic inspection,
not an independent benchmark or a probability of general reliability.

## Mechanical checks and costs

- Native state test: atomic failure rollback, wrong ownership/watermark, capacity
  backpressure, replay, newer no-output preservation and archive survival after
  retention/reset passed.
- Native configuration test: extraction-only defaults off and preserves other
  controls. Native startup test: neither native workspace is created.
- Seven HMK intake tests passed, including binding conflict before staging and
  a competing SQLite writer blocked across source comparison/acknowledgement.
- Configuration schema regenerated, native format check passed, and the CLI built.

The startup test initially overflowed the default test stack. Reusing the same
compiled binary with the upstream CI setting `RUST_MIN_STACK=8388608` passed in
0.43 seconds. No product code was changed for that test-environment failure.
The CLI build then completed in23m29s. Development compilation is separate from
inference/runtime latency.

| Component | Measured usage / time |
|---|---|
| Two native extractions | 2,465 input +702 output =3,167 tokens; complete probe14.85s including trigger, concurrent jobs. |
| Initial neutral trigger | 8,839 tokens;4.32s. |
| Neutral producer-restart turn | 17,867 tokens across two usage updates;7.62s. |
| Source-free receiver | 32,562 tokens across three usage updates;17.67s; one search +four reads. |
| Total new observed usage | 62,435 tokens, including18,176 cached input tokens. No embedding calls. |
| Retained storage | 24,638 envelope bytes;102,400-byte native DB;282,624-byte canonical DB;180,224-byte pre-intake snapshot. |

These are two extraction jobs and three foreground turns, with eight observed
usage intervals. Transport retries and monetary billing are unknown, not zero.
The receiver's full harness context and neutral test turns are qualification
costs, not a forecast for daily consolidation. Selection was explicit local
curation; retrieval was lexical. Neither embeddings nor consolidation were changed.

## Limits and exact continuation

The initial archive accepts UTF-8 native JSONL. Compressed sources and arbitrary
large-input semantic retention remain unqualified. Native eligibility/filtering
remain the producer's contract; this is not a journal of every intermediate
session edit. The 256MiB envelope-byte cap excludes SQLite overhead and fails the
commit without advancing completion; acknowledgement never silently prunes
originals. Owner archive management needs a later bounded policy.

Configuration rollback preserves newer data with the same migration-aware build.
An older binary may reject the new migration and needs its own retained
pre-migration profile; an old-binary downgrade is not claimed here.

This closes the requested experimental extraction/durable-delivery goal. The next
optional delivery is a bounded owner-approved selection policy and explicit
operational coordinator over this queue, followed by a separately authorized
rollout on selected real sources. Address archive lifecycle and current official
Codex integration in that work. Do not enable native generation in production,
install hooks/timers, resume old queues or repeat the qualified model gate.
