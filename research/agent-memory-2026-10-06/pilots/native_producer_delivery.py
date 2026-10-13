"""Bounded delivery qualification on the two exact, already-qualified fictional sources.

This evaluator/selection policy stays outside the native receiver's namespace.
It does not generate candidates or infer an operator's authorization for real data.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import codex_candidates as candidates  # noqa: E402
from capturectl import CaptureLedger  # noqa: E402
from sqlite_snapshot import verified_snapshot  # noqa: E402

EVIDENCE = Path(__file__).parent / "native-producer-evidence"


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_memory(base):
    os.environ["HMK_AGENT_MEMORY_BASE"] = str(base)
    os.environ["HMK_DB_PATH"] = str(base / "library.db")
    spec = importlib.util.spec_from_file_location(
        "delivery_canon", REPO / "scripts/memoryctl.py"
    )
    memory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory)
    memory.init_db()
    return memory


def run(profile, out):
    producer = profile / "codex-home/memories_v2_1.sqlite"
    fixtures = {
        x["thread_id"]: x
        for x in json.loads((EVIDENCE / "source-manifest.json").read_text())
    }
    with sqlite3.connect(producer) as con:
        con.row_factory = sqlite3.Row
        rows = [
            dict(r)
            for r in con.execute(
                "SELECT * FROM memory_extraction_events ORDER BY sequence"
            )
        ]
    cases = {}
    for row in rows:
        fixture = fixtures[row["thread_id"]]
        envelope = json.loads(row["envelope_json"])
        assert (
            hashlib.sha256(envelope["source_rollout"].encode()).hexdigest()
            == fixture["sha256"]
        )
        cases[fixture["case"]] = row
    assert set(cases) == {"failed-communication", "revisit-new"}
    assert len(rows) == 2
    out.mkdir(parents=True, exist_ok=False)
    memory = load_memory(out / "canon")
    relay = memory.add_text(
        "episodes",
        "Mira relay proposal, June 18",
        "On 2024-06-18 Mira Solen (@mira-estuary, person:841) proposed retaining original relay "
        "timestamps and a local monotonic sequence, comparing both orders after reconnection. "
        "HarborMesh issue 37 comment c-904: https://forge.example/harbor/mesh/issues/37#c-904. "
        "Ilex reported supplying a two-node reconnect example. The proposal was not adopted or tested. "
        "Leto reviewed only the parser. This is the earlier experience represented by retrieved "
        "fixture record hmk:relay-37 revision 2, corrected 2024-08-02.",
        metadata=dict(
            mode="generated",
            source_instance="fixture:desk",
            subject="fixture:ilex",
            source_uri="fixture:hmk:relay-37@2",
        ),
    )
    invitation = memory.add_text(
        "episodes",
        "Jo Venn invitation account",
        "On 2024-06-19 the invitation to Jo Venn was delivered.",
        metadata=dict(
            mode="reported", source_instance="fixture:desk", subject="fixture:ilex"
        ),
    )
    relay_before = memory._read_chapter(relay)
    invitation_before = memory._read_chapter(invitation)
    verified_snapshot(memory.DB_PATH, out / "before-intake.sqlite")
    # Abrupt consumer termination after durable staging/preservation, before native ack.
    child = """import os,sys
sys.path.insert(0,sys.argv[1])
import codex_candidates as c
import memoryctl as m
def stop(point):
 if point=='before_ack':os._exit(77)
c.ingest(m,sys.argv[2],source_instance='fixture:desk',subject='fixture:ilex',_fault=stop)
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(REPO / "scripts"), str(producer)],
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 77
    with sqlite3.connect(producer) as con:
        assert (
            con.execute(
                "SELECT count(*) FROM memory_extraction_events WHERE acknowledged_receipt IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
    receipts = candidates.ingest(
        memory, producer, source_instance="fixture:desk", subject="fixture:ilex"
    )
    assert (
        candidates.ingest(
            memory, producer, source_instance="fixture:desk", subject="fixture:ilex"
        )
        == receipts
    )
    by_sequence = {x["sequence"]: x for x in receipts}
    ledger = CaptureLedger(memory)
    decisions = []
    for case, row in cases.items():
        receipt = by_sequence[row["sequence"]]
        artifact = "artifact:sha256:" + receipt["artifact_id"]
        if case == "failed-communication":
            records = [
                dict(
                    key="invite-correction",
                    operation="update",
                    chapter_id=invitation,
                    expected_revision=invitation_before["revision"],
                    raw="On 2024-06-19 Ilex attempted to invite Jo Venn (@jo-venn, person:552) "
                    "to compare sensor mounts with Tavi. message_send attempt send-77 returned "
                    "authentication_failed, delivered=false and no receipt. The assistant then "
                    "incorrectly said it was sent; no successful retry or acceptance is evidenced. "
                    "Tavi reported meeting Jo at Willow Workshop on June 3, where Jo taught the "
                    "rover body fixture:rover a two-hand clamp technique. The current desk body "
                    "fixture:desk has no gripper. Remembered rover skill is not a desk capability.",
                    metadata=dict(
                        mode="generated",
                        correction_of=invitation_before["record_uid"] + "@1",
                        evidence=[artifact],
                    ),
                )
            ]
        else:
            records = [
                dict(
                    key="human-meeting",
                    operation="add",
                    shelf="episodes",
                    title="Tavi reported meeting Leto at Reed Library",
                    raw="On 2024-08-03 Tavi reported meeting Leto Neri (@leto-n, person:992) alone "
                    "at Reed Library. Ilex did not attend. Leto offered to annotate reconnect "
                    "sketches next month; he did not promise an implementation. Tavi told him "
                    "about Mira’s idea. This is a new human-reported meeting, distinct from "
                    "the recalled June 18 HarborMesh issue 37 encounter with Mira.",
                    metadata=dict(mode="reported", actor="Tavi", evidence=[artifact]),
                ),
                dict(
                    key="new-interpretation",
                    operation="add",
                    shelf="episodes",
                    title="A new interpretation of the relay gaps",
                    raw="While discussing the library visit with Ilex on 2024-08-03, Tavi described "
                    "the gaps as something they could explain to people, not merely recover "
                    "from. Ilex recognized this as a new interpretation in their current "
                    "conversation. It is not a new meeting with Mira, a deployed change or "
                    "proof that the earlier proposal was adopted.",
                    metadata=dict(mode="inferred", evidence=[artifact]),
                ),
            ]
        decision = dict(
            outcome="applied",
            reason="Source-qualified explicit evaluator selection; "
            "retrieved relay history is already represented and is not selected again.",
            selection_version="native-producer-delivery-manual/v1",
            records=records,
            links=[],
        )
        applied = ledger.assess(receipt["event_key"], decision)
        assert ledger.assess(receipt["event_key"], decision) == applied
        decisions.append(
            dict(
                case=case,
                event_key=receipt["event_key"],
                decision=decision,
                receipt=applied,
            )
        )
    assert memory._read_chapter(relay) == relay_before
    assert memory._read_chapter(invitation)["revision"] == 2
    assert memory.history(invitation)[0]["raw"] == invitation_before["raw"]
    # Restore only the pre-intake copy as a rollback witness; retain later live writes.
    verified_snapshot(out / "before-intake.sqlite", out / "rollback-copy.sqlite")
    with sqlite3.connect(out / "rollback-copy.sqlite") as con:
        assert con.execute("SELECT count(*) FROM chapters").fetchone()[0] == 2
    with memory.connect() as con:
        assert con.execute("SELECT count(*) FROM chapters").fetchone()[0] == 4
        assert (
            con.execute("SELECT count(*) FROM native_learning_artifacts").fetchone()[0]
            == 2
        )
    source_dir = profile / "codex-home/sessions"
    source_dir.rename(profile / "withheld-sessions")
    for receipt in receipts:
        assert candidates.projection.load_learning(memory, receipt["artifact_id"])
    assert memory.search("authentication")[0]["id"] == invitation
    assert memory.search("Reed")
    assert memory.search("Mira")
    save(out / "selection-decisions.json", decisions)
    save(
        out / "delivery-receipt.json",
        dict(
            interrupted_exit_code=result.returncode,
            original_artifacts=2,
            selected_chapters=4,
            existing_relay_unchanged=True,
            invitation_revision=2,
            history_preserved=True,
            sources_withheld=True,
            lexical_recall_verified=True,
            native_conversational_recall="pending",
            receipts=receipts,
        ),
    )
    return memory.DB_PATH


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(run(args.profile.resolve(), args.out.resolve()))
