# Forward capture across session ages

An old session can still contain new work. Optional `dmk.forward-capture/v1`
selects new turns independently of session creation date and original directory.
The existing hook binding, being, inbox, configured working directories and worker
remain authoritative. Activation is explicit; importing this module enables nothing.

## Boundary and scope

Activation snapshots the existing inbox and inventories regular JSONL files under
its configured source root once. It records paths, file identity, EOF offsets and
small boundary hashes, not historical conversation bodies. Existing unadmitted
sessions begin at the next `task_started` boundary after this inventory; an
in-flight turn at activation is deliberately outside that new coverage. New
sessions can start at their first turn. An old file introduced after the inventory
fails visibly rather than being mistaken for a new session.

Both the current hook directory and each admitted turn's `turn_context.cwd` must
be selected. Changing the directory later does not import intervening unselected
turns. A partial or unverified turn context stays pending. Previously captured
legacy streams retain their admitted prefix and pending observations.

Each receiving body activates against its own binding and inbox. This neither
combines beings nor imports earlier sessions into canonical memory. Capturing a
source remains separate from selecting lasting meaning, writing memory and indexing.

## Bounded capture and preserved source

A hook seeks to its durable cursor and reads at most its configured forward
`read_budget_bytes` (default 4 MiB, bounded by `max_source_bytes`). This budget
limits one operation, not total session history. Complete
JSONL records form per-turn source segments. Larger backlogs retain their cursor
and report `capture_deferred`; repeated explicit capture can continue without
models. `drain --binding ... --payload ... --max-steps 32` performs bounded
catch-up with an explicitly selected native payload; it stops on completion, no
progress or its step budget and invokes no models. An individual record exceeding
the read budget remains a visible failure; select an adequate explicit budget
before activation when unusually large individual records are expected.
Incomplete records, replacement, truncation and a changed cursor boundary never
silently advance. Concurrent appends beyond the observed size wait for the next
capture. Native rollouts are append-only inputs: this detects identity/boundary
changes, not arbitrary rewrites of all previously read source bytes.

The inbox retains original session headers and exact selected record bytes,
original file ranges, hashes and session/turn attribution. The reconstructed
segment is a projection, not a claim to have captured the entire original session.
The source cursor, revisions, observations and range provenance commit together.
Replay after an uncertain commit creates no duplicate observation. Existing
producer normalization, selection and source-window APIs consume these segments;
no new worker or provider is needed. Reconstructing a current turn in the inbox
is separate from rereading the whole original session file.

## Activation and rollback

Resolve the installed capture release from the actual hook command. Use its Python
interpreter and scripts, rather than assuming the separately installed reader is
at the same release:

```sh
python /selected-release/scripts/forward_capture.py activate \
  --binding /receiving/capture-binding.json --backup /receiving/before-forward.sqlite
python /selected-release/scripts/forward_capture.py status \
  --binding /receiving/capture-binding.json
```

Install/trust the compatible handler and explicitly hot-reload native configuration
as described in [the receiving procedure](dmk-naming.md#hot-reload-correction).
Keep the binding unchanged. Activation changes no scheduler, model configuration,
worker cadence or canonical pool and invokes no paid processing.

`pause` and `resume` use the same `--binding`. Pause preserves cursors and pending
work and reports deferred capture instead of silently falling back to full-session
intake. This is the supported operational rollback. Do not replace a live inbox
with its older snapshot or revert to an unaware capture handler after new ranges
exist: that would lose progress or duplicate later capture. The unchanged producer
can still consume retained observations. Keep the verified pre-activation snapshot
as recovery evidence, alongside later journals and history.

Qualification includes large old sources, new sessions, per-turn scope, actual
source loss, concurrent hooks, interruption before/after commit, bounded catch-up
with tool dependencies, safe pause/resume, source alteration and one fictional
end-to-end selection through the existing producer. Production rollout and the
next actual native turn are reported separately; no paid fixture is required.
