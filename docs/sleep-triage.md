# Sleep triage for missed conversation evidence

The existing sleep worker can optionally review authorized forward-capture
deltas for three independent destinations. DMK considers durable experiences,
people, dated encounters, first evidenced appearances of ideas and lessons.
The shared work map considers meaningful changes to shared work. Bitácora
considers source evidence that could support a story. A casual report inside a
technical session can qualify, and one source item can qualify for several
destinations. A proposal, an attributed report and an observed result remain
distinct. Routine traffic should score low for all three.

Use the OpenAI [Decisions API](https://developers.openai.com/api/docs/guides/decisions)
with `gpt-6-luna` at `/v1/decisions`. This is the typed predicate endpoint.
Each request includes up to eight dialogue pieces from one captured conversation
range and three independent questions per piece. Their shared evidence is sent
once. The result is probabilities and exact source pointers. No generated
prose, tools, or second model is used by this step. Usage is recorded when the
service returns it. Reconcile actual cost with [organization Decisions usage](https://developers.openai.com/api/docs/guides/decisions#monitor-usage)
and account billing before projecting cost. Low scores remain reviewable during
qualification; refused predicates remain explicitly unresolved.

The first profile reviews dialogue from the selected forward inbox. Its separate
cursor starts at an explicit observation, walks forward through a fixed
high-water mark per invocation, and never reopens the original native logs. Long
dialogue is paged without dropping text. Pending pages retain their place. Scope
excludes back-catalog records outside the chosen boundary, legacy snapshots, raw
tool payloads, harness instructions, and non-text media semantics. Source-family
and exact offsets/checksums stay local. Model input consists of selected dialogue
and its limited attribution/date context, which may still be private. Qualify
with fictional dialogue before choosing the authorized source scope.

Private proposals retain predicate results and source pointers. Existing
foreground curation may already have captured the same matter. Reconcile a
potential memory with native record/revision history, a work-map change with its
owner's selected source packet, and a Bitácora candidate with the existing
source packet and institutional intake. Carry corrections and attribution, and
keep private evidence private. A classifier result is neither a write receipt
nor authority to share. Preserve editorial discretion and Matrix receiving
choice. These destination applications and their deduplication still need
receiving qualification.

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
step count within the actual unit's time budget (30 seconds maximum per external
attempt); no new scheduler is required. The isolated `sleep_triage.py --binding
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
A standalone run returns the failure directly.

Each step uses at most 12,000 bytes of dialogue packet and 24 predicates, with
at most 32 steps per invocation. One active receipt, 2,048 result packets and
256 retained rejection records are hard limits; no whole request or raw dialogue
copy is retained by this stage. Retire or move a packet only after its owning
review or handoff has retained its receipt and source pointer. At capacity,
preserve the cursor and reconcile the existing packets before continuing.
The capture journal remains the owner of exact sources.

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
