"""Interruption and replay against real receiving APIs, with fictional native rows."""

import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setenv("HMK_AGENT_MEMORY_BASE", str(tmp_path / "canon"))
    monkeypatch.setenv("HMK_DB_PATH", str(tmp_path / "canon/library.db"))
    spec = importlib.util.spec_from_file_location(
        "candidate_memory_fixture", SCRIPTS / "memoryctl.py"
    )
    memory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory)
    memory.init_db()
    import codex_candidates as candidates

    source = tmp_path / "producer.sqlite"
    con = sqlite3.connect(source)
    con.executescript("""
      CREATE TABLE memory_extraction_stream(singleton INTEGER PRIMARY KEY,stream_id TEXT);
      INSERT INTO memory_extraction_stream VALUES(1,'fixture-stream');
      CREATE TABLE memory_extraction_events(sequence INTEGER PRIMARY KEY,event_id TEXT,
       thread_id TEXT,source_updated_at INTEGER,envelope_json TEXT,created_at INTEGER,
       acknowledged_receipt TEXT);
    """)
    envelope = dict(
        schema=candidates.SCHEMA,
        disposition="candidate",
        producer_version="fixture",
        memory_version="v2",
        model="fixture",
        reasoning_effort="low",
        source_path="/lost/source",
        source_rollout="original fictional source",
        input_messages=[{"content": "evidence"}],
        base_instructions="fixture",
        output_schema={},
        generated_output='{"rollout_summary":"failed"}',
        parsed_output={"rollout_summary": "failed"},
        token_usage=None,
    )
    con.execute(
        "INSERT INTO memory_extraction_events VALUES(1,?,?,?,?,?,NULL)",
        ("event-1", "thread-1", 10, json.dumps(envelope), 20),
    )
    con.commit()
    con.close()
    return memory, candidates, source


def intake(setup, **kwargs):
    memory, candidates, source = setup
    return candidates.ingest(
        memory, source, source_instance="fixture:desk", subject="fixture:ilex", **kwargs
    )


def ack(source):
    with sqlite3.connect(source) as con:
        return con.execute(
            "SELECT acknowledged_receipt FROM memory_extraction_events"
        ).fetchone()[0]


@pytest.mark.parametrize("point", ["after_stage", "before_ack"])
def test_interrupted_receipt_replays_without_memory_or_evidence_duplication(
    setup, point
):
    memory, candidates, source = setup

    def crash(at):
        if at == point:
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        intake(setup, _fault=crash)
    assert ack(source) is None
    receipts = intake(setup)
    assert intake(setup) == receipts
    assert ack(source) is not None
    con = memory.connect()
    assert con.execute("SELECT count(*) FROM chapters").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM capture_events").fetchone()[0] == 1
    assert (
        con.execute("SELECT count(*) FROM native_learning_artifacts").fetchone()[0] == 1
    )
    con.close()
    source.unlink()
    originals = candidates.projection.load_learning(memory, receipts[0]["artifact_id"])
    assert (
        json.loads(originals["extraction.json"])["source_rollout"]
        == "original fictional source"
    )


def test_source_mutation_cannot_receive_a_receipt_for_other_bytes(setup):
    _, _, source = setup

    def mutate(at):
        if at == "before_ack":
            with sqlite3.connect(source) as con:
                con.execute("UPDATE memory_extraction_events SET source_updated_at=999")

    with pytest.raises(ValueError, match="changed during intake"):
        intake(setup, _fault=mutate)
    assert ack(source) is None


def test_ack_is_not_selection_and_pagination_does_not_lose_corrections(setup):
    memory, candidates, source = setup
    first = intake(setup)[0]
    with sqlite3.connect(source) as con:
        payload = json.loads(
            con.execute(
                "SELECT envelope_json FROM memory_extraction_events"
            ).fetchone()[0]
        )
        payload["disposition"] = "no_output"
        payload["generated_output"] = '{"rollout_summary":""}'
        payload["parsed_output"] = {"rollout_summary": ""}
        con.execute(
            "INSERT INTO memory_extraction_events VALUES(2,?,?,?,?,?,NULL)",
            ("event-2", "thread-1", 11, json.dumps(payload), 21),
        )
    later = intake(setup, after_sequence=1)
    assert len(later) == 1 and later[0]["sequence"] == 2
    assert first["artifact_id"] != later[0]["artifact_id"]
    ledger = candidates.CaptureLedger(memory)
    assert len(ledger.pending("codex-extraction:fixture:desk:fixture-stream")) == 2
    assert len(intake(setup)) == 2
    con = memory.connect()
    assert con.execute("SELECT count(*) FROM chapters").fetchone()[0] == 0
    con.close()


def test_explicit_correction_preserves_history_and_source_free_recall(setup):
    memory, candidates, source = setup
    original = memory.add_text(
        "episodes",
        "Invitation to Jo",
        "The invitation was delivered.",
        metadata={"mode": "reported", "source_instance": "fixture:desk"},
    )
    before = memory._read_chapter(original)
    receipt = intake(setup)[0]
    ledger = candidates.CaptureLedger(memory)
    decision = dict(
        outcome="applied",
        reason="Tool evidence contradicts the earlier success claim.",
        selection_version="fixture-reviewed/v1",
        records=[
            dict(
                key="correction",
                operation="update",
                chapter_id=original,
                expected_revision=1,
                raw="The invitation to Jo Venn failed authentication; it was not delivered. No acceptance is known.",
                metadata=dict(
                    mode="generated",
                    correction_of=before["record_uid"] + "@1",
                    evidence=["artifact:sha256:" + receipt["artifact_id"]],
                ),
            )
        ],
        links=[],
    )
    applied = ledger.assess(receipt["event_key"], decision)
    assert ledger.assess(receipt["event_key"], decision) == applied
    assert intake(setup)[0]["state"] == "applied"
    source.unlink()
    assert memory.search("authentication")[0]["id"] == original
    assert memory.history(original)[0]["raw"] == "The invitation was delivered."
    assert memory._read_chapter(original)["revision"] == 2
    assert candidates.projection.load_learning(memory, receipt["artifact_id"])
    with memory.connect() as con:
        assert con.execute("SELECT count(*) FROM chapters").fetchone()[0] == 1
