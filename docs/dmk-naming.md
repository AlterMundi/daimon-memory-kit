# DaimonMemoryKit naming and receiving update

The maintained project is **DaimonMemoryKit (DMK)** at
https://github.com/AlterMundi/daimon-memory-kit. The shared skill is
`daimon-memory-kit`; use `dmk` and `dmk_recall` for new integrations.

Compatibility identifiers remain deliberate: `hmk`, `HMK_*`, `hmk-memory`,
`hmk_recall`, versioned `hmk.*` schemas, existing service names, immutable release
paths and source bindings. They do not create a parallel memory system. Changing
these identifiers requires a compatible implementation, not text substitution.

Keep historical memories, signed projections, original receipts, prior issue/PR
URLs and archived releases unchanged. Add an attributed naming decision so older
HMK references remain understandable. Update active instructions and tool help.
Do not rewrite a participant's past words or renumber another repository's issues.

The Obsidian exporter and generated vault templates are removed from this version.
`--with-wiki-templates` remains an explicitly ignored compatibility option. No
existing notes, independently authored Wiki sources or memory databases are deleted.
The portable archive and native/Matrix projections are separate and remain intact.

Receiving updates preserve preimages outside skill discovery. Install the new
shared skill from its pinned package, then retire the old skill directory to that
backup. Preserve edited receiving instructions and update only naming references.
The MCP alias uses the same binding, pools, read-only annotations and implementation.
New/resumed harness processes pick up configured changes; already-running sessions
may retain their original tool names, which remain compatible. No global Stop is
needed and no new capture scope, scheduler or native memory provider is enabled.


## Receiving adoption — 2026-10-15

CompAII, Eko and Oliva have the pinned `daimon-memory-kit` shared skill,
`dmk` command, updated active guidance and the new MCP entry point. Actual
read-only receiving probes found the same owner-bound pools (one, two and one,
respectively), equal results through both recall names, and unchanged existing
chapter IDs, revisions and raw content. Each body has a verified pre-update
SQLite snapshot and an attributed naming record; historical records retain
original names. Private configuration preimages and retired skills are retained
outside discovery. Already-running sessions may still expose the old tool alias.

The code and guidance update is [PR #3](https://github.com/AlterMundi/daimon-memory-kit/pull/3);
the shared package is [Skills #68](https://github.com/AlterMundi/Skills/pull/68).
Current Field cards and open issue descriptions were updated while original URLs,
comments, signed data and dated evidence remain intact. Current cross-repository
references use the maintained project; the old repository remains historical.

A separate capture fix, [PR #4](https://github.com/AlterMundi/daimon-memory-kit/pull/4),
is installed in the existing trusted capture hooks on all three bodies. It reads
the bounded session header before applying the full-source size limit. Selected
sources still require exact complete capture; oversized selected sources remain
visible failures. No source is truncated or admitted merely to clear an alert.

Twelve CompAII failures belonged to one old session outside the selected scope.
New matching receipts verified its exclusion under the unchanged binding; the
supported exclusion control reconciled the retained failures. Alerts confirmed
all twelve resolved at a higher revision, with `work_preserved: false`. This is
verified exclusion, not source capture. There were no new inbox observations or
revisions for this source, no worker invocation and no paid model calls. See the
[sanitized receipt](../evidence/dmk-naming-2026-10-15/capture-resolution.json).
This does not resolve unrelated unidentified historical capture attempts.

Validation: 75 focused naming/upgrade/MCP tests, bootstrap smoke, shared-skill
catalog/package checks, actual three-body MCP probes, and 19 capture-inbox tests
including oversized selected/excluded sources. These updates add no scheduler,
expand no capture scope and enable no native memory provider.


### Hot reload correction

The first hook adoption updated `hooks.json` and wrote trust hashes through
`config/value/write`. That saved configuration and `hooks/list` verified its
current contents, but did not reload already-loaded hook runtimes. Two later
Stop/SessionEnd attempts repeated the old size error on the same excluded source.
The original twelve resolutions remain valid; they did not prove runtime reload.

On the installed Codex 0.162.1, explicitly request `config/batchWrite` with
`{"edits": [], "reloadUserConfig": true}` after configuration/trust adoption.
The supported batch path reloads loaded threads and refreshes their hooks;
`config/value/write` alone does not. The three receiving daemons accepted the
reload with `status: ok`, with configuration bytes unchanged and no native model
turns, thread stops or worker invocations. Do not replace immutable release files
to compensate for a cached command.

The two additional retained failures were reconciled through fresh matching
exclusion receipts, preserving the original attempts and scope. Confirm the next
naturally occurring native hook separately: a successful reload RPC or direct
supervisor invocation is not itself observation of that hook. No global restart
or synthetic paid turn is required merely to obtain that observation.
