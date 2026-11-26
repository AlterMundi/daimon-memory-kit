# Sleep triage for missed conversation evidence

The existing sleep worker can optionally review authorized forward-capture
deltas for three independent destinations. DMK considers durable experiences,
people, dated encounters, first evidenced appearances of ideas and lessons.
The shared work map considers meaningful changes to shared work. Bitácora
considers source evidence that could support a story. A casual report inside a
technical session can qualify, and one source item can qualify for several
destinations. A proposal, an attributed report and an observed result remain
distinct. Routine traffic should score low for all three.

Examples are not admission categories. A memory candidate qualifies when it
helps the being understand its history, what changed, or where to resume years
later. Consider meaningful material outside any supplied list unless that list
is explicitly exhaustive.

Use the OpenAI [Decisions API](https://developers.openai.com/api/docs/guides/decisions)
with `gpt-6-luna` at `/v1/decisions`. This is the typed predicate endpoint.
The first request includes up to eight pieces of the human side of one
captured conversation range. It asks three independent destination questions and
a question about whether the assistant's side is materially needed. A context
probability of at least 0.8 opens at most one follow-up per page, covering only
the flagged items. The worker may include at most two assistant excerpts, each
at most 900 characters, from the current and preceding admitted range of that
conversation. Assistant excerpts clarify the human text and cannot become
independent candidates. Unknown context stays visible for review. This threshold
is provisional until measured against labeled examples.

The result is probabilities and exact source pointers. No generated prose,
tools, or second model is used. Usage is recorded when the service returns it.
Reconcile actual cost with [organization Decisions usage](https://developers.openai.com/api/docs/guides/decisions#monitor-usage)
and account billing before projecting cost. Low scores remain reviewable and
refused predicates remain unresolved during qualification.

The first profile reviews human dialogue from the selected forward inbox. Its separate
cursor starts at an explicit observation, walks forward through a fixed
high-water mark per invocation, and never reopens the original native logs. Long
dialogue is paged without dropping text. Pending pages retain their place. Scope
excludes back-catalog records outside the chosen boundary, legacy snapshots, raw
tool payloads, harness instructions, and non-text media semantics. Source-family
and exact offsets/checksums stay local. The local scanner honors the forward
binding's capture bound for a retained range, including a large indivisible
record. It filters out tool payloads before forming the dialogue pages. Model
input consists of selected dialogue and its limited attribution/date context,
which may still be private. Qualify
with fictional dialogue before choosing the authorized source scope.

Private proposals retain predicate results and source pointers. Existing
foreground curation may already have captured the same matter. Reconcile a
potential memory with native record/revision history, a work-map change with its
owner's selected source packet, and a Bitácora candidate with the existing
source packet and institutional intake. Carry corrections and attribution, and
keep private evidence private. A classifier result is neither a write receipt
nor authority to share. Preserve editorial discretion and Matrix receiving choice. The finite DMK review below
applies a selected memory or records its omission. Work-map and Bitácora
application remain with their owning surfaces.

## Worker entry point and recovery

Add this optional object only to the existing worker profile selected for this
work. Choose the starting observation from the already authorized forward
inbox; the example value is a placeholder, not a backfill instruction.

```json
{
  "sleep_triage": {
    "state_dir": "/selected/worker/state/sleep-triage",
    "initial_after": 123,
    "steps": 4,
    "credential_env": "OPENAI_API_KEY",
    "source_review_report": "/selected/matrix/source-review/report.json",
    "max_age_seconds": 93600
  }
}
```

The existing `memory_runtime.py run --profile ...` invokes it after the original
phases. The ordinary worker, authority and cadence remain the owners. Keep the
step count within the actual unit's time budget (up to two external
attempts of at most 30 seconds per step); no new scheduler is required. The isolated `sleep_triage.py --binding
... --state-dir ... --after ... --steps ...` entry point uses the same state
contract. Omit `--after` after the first run. Use an API project credential
through the launcher's existing environment route.

A completed receipt is reusable across an interruption, even without a current
credential. A started or uncertain attempt blocks new dispatch. For a confirmed
HTTP rejection, fix the cause and explicitly run the same state with
`--retry-request <retained hash> --reason '<observed correction>' --steps 1`.
The original rejection and reason remain in private state. Do not authorize a
second call after a timeout or ambiguous server result without reconciliation.
The worker projects retained provider failures through the existing DMK outbox.
The same outbox reports unreadable local input before a dispatch. A verified
scan can resolve that local incident even when there is no eligible dialogue.
Restoring the Decisions credential or provider access still requires a successful
classification to resolve the provider incident. A standalone run returns the
failure directly.

Each step uses at most 12,000 bytes of human dialogue packet and 32 initial
predicates, plus the bounded optional follow-up. There are at most 32 steps per
invocation and 30 seconds per attempt. Two active receipts, 2,048 result packets and
256 retained rejection records are hard limits; no whole request or raw dialogue
copy is retained by this stage. Retire or move a packet only after its owning
review or handoff has retained its receipt and source pointer. At capacity,
preserve the cursor and reconcile the existing packets before continuing.
The capture journal remains the owner of exact sources.

## Omit one reviewed page without a provider call

An operator who has inspected a complete pending page may pass its exact
scoped Decisions request hash to `sleep_triage.py --steps 1 --omit-page HASH
--reason "reason"`. The SHA-256 uses the normal serialized request including
its window scope. The worker refuses a different page and preserves existing
initial and follow-up dispatches. The private omitted packet keeps source
pointers and the decision reason without a provider receipt. If the process
stops after the packet is committed, the next run resumes from that receipt.

## Review a candidate for the canonical library

Use the same owner-selected worker profile. Inspect one item from a retained
packet, then search the canonical library and read the relevant existing records
and revisions. The review command reconstructs the exact human excerpt and only
the assistant context already selected for that page from the original capture
journal. Run it in the owner's private environment. The output may contain
private dialogue.

```bash
python scripts/sleep_memory_review.py --profile "$profile" --packet "$packet" --item 0
python scripts/sleep_memory_review.py --profile "$profile" --packet "$packet" --item 0 --decision "$selection"
```

The decision file contains the inspected `fingerprint` and a CaptureLedger
`decision` with an explicit `applied` or `omitted` outcome and reason. Apply at
most one memory per item. Use an expected revision for a correction and omit a
duplicate that adds no meaningful evidence. The original citation and attribution
come from the capture journal. Write a self-contained memory that preserves the
subject, uncertainty, time precision and actual outcome. High probabilities
only shortlist evidence. They do not assess meaning or authorize a write.

An exact reviewed replay returns the original receipt; a changed decision is
refused. Verify the canonical read and index separately. Use the existing
consolidation preview/apply contract for a derived account only when meaningful
synthesis is supported by the selected originals. The daily worker's account
reconciler still only updates existing accounts. This foreground command is
the operator path for reviewed Decisions admission.

## Verify on every configured cycle

`worker-status.json` reports the triage outcome and `sleep_health` alongside
ordinary phases. `sleep_health.py --worker-dir ... --source-review-report ...
--max-age-seconds ...` reads the same evidence independently without triggering
workers. A blocked selection, stale backup and stale or partial Source review
remain visible. A quiet inbox and a live timer do not establish a completed
source-to-memory journey.

Matrix Source review verifies discovery only. To establish cross-daimon
learning, use the existing owner path and require, for the same selected event,
actual receiving pull/admission and local decision, the relevant use receipt for
the receiving destination, and the stated observation time. An intentional
decline is distinct from failure or use. Retain the checks in the Matrix owning
checkpoint. This release does not turn a discovery report into a receiving
learning receipt. Rolling up those exact receipts and connecting operational
failures to the existing Matrix observer remain separate from DMK's local check.

## Qualification before selecting real dialogue

Use comparable fictional conversations and hidden per-item, per-destination
labels. Include casual group visits in technical threads, first ideas and later
restatements, uncertain dates, claims corrected by a later message, minor
updates, existing records and stories, and audience-sensitive evidence. Measure
false negatives for durable events and false positives for each destination,
refusals and downstream review effort. Exercise interruption, budget boundary,
and unchanged-input replay. Require real cost and latencies for the three
destinations together. Tests with a mock transport validate invariants and the
wire shape, not classifier quality or actual provider acceptance.

Version 2 pins the human-first request policy. Retained version 1 runs require
explicit reconciliation before adopting this version. Do not reinterpret their
in-flight pages as human-first or redispatch a retained attempt.

When the selected API project has a confirmed model-access denial, select
`"provider_blocked": "access_denied"` in the optional sleep profile. The
existing daily invocation reports one scoped access incident and leaves the
triage cursor and pending evidence untouched. It submits no dialogue and makes
no API request for the blocked phase. Qualify the restored project with a
fictional example and remove the block only after it returns typed answers.
The next successful classification resolves the incident. A quiet inbox never
proves that the model is accessible.

## Read Decisions usage

`worker-status.json` includes `completed_page_usage`, the known usage and
receipt counts for the pages completed during that run. A page completed after
recovery can consume an already received response.

Run `python scripts/sleep_usage.py --state-dir "$triage_state"` for a
content-free aggregate of retained typed responses and uncertain attempts,
grouped by receipt completion day in Buenos Aires. An active response and its
published copy count once. Older undated receipts contribute to a separate
undated total. Known zeros and missing usage are distinct, and cached input is
part of the input count. Windows cover retained Decisions receipts only. This
readout does not claim full memory-job cost or reconstruct retired receipts.

## New paired receivers without a forward capture worker

Use `paired_sleep.py enroll --profile "$profile"` on an authorized receiver.
The profile selects its owner-local Conversation registry (`conversation_db`),
Codex state store (`native_db`), rollout root (`source_root`), private
`state_dir`, exact `being_ref` and `body_ref`, and an optional observation path
recorded as `source_review_report`. Set `conversation_config` to the receiving
Gateway configuration when its `[interaction]` selects the general conversation.
DMK verifies the configuration's absolute `db_path` against `conversation_db`
and matches its owner, chat and topic against the active registry entry. Existing
direct General topic profiles can omit `conversation_config`; the already
verified owner and direct General entry supply the same original-journal scope.
An older pristine triage cursor may adopt original lookup in place. A cursor
with retained decisions, dispatches or rejection history requires explicit
reconciliation first. This policy preserves the enrolled source boundary.
Keep the profile
private. Authorize the
forward source before enrollment. The operator binds the paired human's active
general entry and records its current byte boundary. New input must carry that
human's authenticated ingress attribution. For Gateway originals with the
configured Conversation, DMK verifies the exact rendered input reference and
text against the retained owner, entry and native turn. Pending native linkage
blocks review of that range until it settles. Free-form native prompts and
peer inputs cannot supply this attribution. The original input reference is
retained in the private packet and canonical evidence and omitted from the
classification request. An unresolved replacement stops intake until the
source is explicitly reconciled.

On a receiver that already has a daily worker, first reconcile the preceding
Decisions backlog and retain its receipts. Then set `sleep_triage.paired_profile`
to the private absolute paired profile in that worker's configuration. The paired
source uses the same scheduled slot, page limit and Decisions credential.
Existing operational capture, organization, indexing and backups keep their
configured budgets. A retained initial or follow-up dispatch in the prior
Decisions directory blocks this switch until reconciled. Paired failures are
published through the supervised worker's existing Alerts outbox.

For a receiver without a daily worker, run
`paired_sleep.py run --profile "$profile"` from the selected receiving
service once daily at 08:00 America/Argentina/Buenos_Aires. Use the existing
systemd encrypted credential or its existing privileged delivery pipe into the
unprivileged worker. The operation captures one bounded range and classifies at
most four pages. It installs no Codex hook and sends no input to Codex. Its
receipts and outbox are in the selected private state directory. Set
`backup_profile` to the private absolute profile of the canonical owner's
existing periodic backup pool when this worker is the owner's daily service.
The same cycle maintains the one selected pool through the periodic backup
contract. A current unchanged database gets an audit when due, with no extra
copy or provider call. The safe backup state is retained alongside review;
a failed backup remains visible independently of Decisions. A suspended
service preserves its journal and checkpoint for later recovery. This receiver
performs source intake and classification. For canonical admission use the
existing review command. On a standalone paired worker use
`sleep_memory_review.py --paired-profile "$profile" --packet "$packet" --item 0`.
It opens only the already enrolled canonical library protected by the same
owner backup profile. For a receiver with a separate canonical worker, pass
`--profile "$canonical_profile"` as well. Both routes re-read the original
reference and use the same explicit review, optional `--decision` and idempotent
receipt.
