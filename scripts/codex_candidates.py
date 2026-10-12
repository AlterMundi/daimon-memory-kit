#!/usr/bin/env python3
"""Explicit intake of versioned native extraction candidates; never automatic selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import time

from capturectl import CaptureLedger, wire
import codex_projection as projection
from sqlite_snapshot import verified_snapshot

SCHEMA = "codex.extraction-candidate/v1"


def candidate_event(row, stream, *, source_instance, subject):
    """Transport exact originals; attribution is supplied by the receiving binding."""
    content = json.loads(row["envelope_json"])
    if content.get("schema") != SCHEMA:
        raise ValueError("unsupported native candidate schema")
    if content.get("disposition") not in {"candidate", "no_output"}:
        raise ValueError("invalid candidate disposition")
    required = {
        "producer_version",
        "memory_version",
        "model",
        "reasoning_effort",
        "source_path",
        "source_rollout",
        "input_messages",
        "base_instructions",
        "output_schema",
        "generated_output",
        "parsed_output",
        "token_usage",
    }
    if not required.issubset(content):
        raise ValueError("incomplete extraction evidence")
    if not isinstance(content["source_rollout"], str) or not isinstance(
        content["input_messages"], list
    ):
        raise ValueError("invalid source evidence")
    if not isinstance(content["generated_output"], str) or not isinstance(
        content["parsed_output"], dict
    ):
        raise ValueError("invalid output evidence")
    if (
        not isinstance(stream, str)
        or not stream
        or type(row["sequence"]) is not int
        or row["sequence"] <= 0
    ):
        raise ValueError("invalid stream sequence")
    original = {
        k: row[k]
        for k in (
            "sequence",
            "event_id",
            "thread_id",
            "source_updated_at",
            "created_at",
        )
    }
    original["stream_id"] = stream
    bundle = projection.learning_bundle(
        {
            "extraction.json": row["envelope_json"].encode(),
            "delivery.json": wire(original).encode(),
        },
        source_instance=source_instance,
        subject=subject,
        source_event_id=row["event_id"],
    )
    event = dict(
        stream_id=f"codex-extraction:{source_instance}:{stream}",
        sequence=row["sequence"],
        event_id=row["event_id"],
        source_version=bundle["artifact_id"],
        content=wire(bundle),
        metadata=dict(
            mode="generated",
            subject=subject,
            source_instance=source_instance,
            source_uri="artifact:sha256:" + bundle["artifact_id"],
        ),
    )
    return event, bundle


def ingest(
    memory,
    producer_db,
    *,
    source_instance,
    subject,
    limit=32,
    after_sequence=0,
    _fault=None,
):
    """Durably stage originals before acknowledging; selected memory stays unchanged.

    All events are replayed, including acknowledged ones, so restoration into a
    receiving copy cannot silently skip data. Acknowledgement records durable
    receiving preservation, not factual acceptance or Matrix admission.
    """
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError("limit must be 1..128")
    if type(after_sequence) is not int or after_sequence < 0:
        raise ValueError("after_sequence must be a nonnegative integer")
    path = Path(producer_db).resolve(strict=True)
    if path == Path(memory.DB_PATH).resolve():
        raise ValueError("producer and canonical database must be separate")
    source = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=30)
    source.row_factory = sqlite3.Row
    try:
        stream_row = source.execute(
            "SELECT stream_id FROM memory_extraction_stream WHERE singleton=1"
        ).fetchone()
        if stream_row is None:
            return []
        stream = stream_row["stream_id"]
        # Validate every selected envelope before touching the receiving database.
        rows = [
            dict(r)
            for r in source.execute(
                "SELECT * FROM memory_extraction_events WHERE sequence>? ORDER BY sequence LIMIT ?",
                (after_sequence, limit),
            )
        ]
        prepared = [
            (
                r,
                *candidate_event(
                    r, stream, source_instance=source_instance, subject=subject
                ),
            )
            for r in rows
        ]
        memory.init_db()
        verified_snapshot(
            memory.DB_PATH,
            str(memory.DB_PATH) + ".bak.candidates." + str(time.time_ns()),
        )
        ledger = CaptureLedger(memory)
        receipts = []
        for row, event, bundle in prepared:
            staged = ledger.stage(event)
            if _fault:
                _fault("after_stage")
            con = memory.connect()
            try:
                con.execute("BEGIN IMMEDIATE")
                con.execute(
                    "CREATE TABLE IF NOT EXISTS native_learning_artifacts ("
                    "artifact_id TEXT PRIMARY KEY, envelope_json TEXT NOT NULL)"
                )
                con.execute(
                    "INSERT OR IGNORE INTO native_learning_artifacts VALUES(?,?)",
                    (bundle["artifact_id"], wire(bundle)),
                )
                old = con.execute(
                    "SELECT envelope_json FROM native_learning_artifacts WHERE artifact_id=?",
                    (bundle["artifact_id"],),
                ).fetchone()[0]
                if old != wire(bundle):
                    raise ValueError("preserved candidate differs")
                con.commit()
            finally:
                con.close()
            if projection.load_learning(
                memory, bundle["artifact_id"]
            ) != projection.restore_learning(bundle):
                raise ValueError("candidate artifact verification failed")
            if _fault:
                _fault("before_ack")
            receipt = wire(
                dict(
                    schema="hmk.candidate-preserved/v1",
                    event_key=staged["event_key"],
                    artifact_id=bundle["artifact_id"],
                    source_instance=source_instance,
                    subject=subject,
                )
            )
            # A concurrent changed source must not acquire a receipt for other bytes.
            with source:
                current = source.execute(
                    "SELECT * FROM memory_extraction_events WHERE event_id=?",
                    (row["event_id"],),
                ).fetchone()
                if current is None or any(
                    current[k] != row[k] for k in row if k != "acknowledged_receipt"
                ):
                    raise ValueError("native candidate changed during intake")
                if current["acknowledged_receipt"] not in (None, receipt):
                    raise ValueError(
                        "candidate already acknowledged for another receiving binding"
                    )
                source.execute(
                    "UPDATE memory_extraction_events SET acknowledged_receipt=? WHERE event_id=?",
                    (receipt, row["event_id"]),
                )
            receipts.append(
                dict(
                    event_key=staged["event_key"],
                    artifact_id=bundle["artifact_id"],
                    sequence=row["sequence"],
                    state=staged["state"],
                )
            )
        return receipts
    finally:
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-db", type=Path, required=True)
    parser.add_argument("--source-instance", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--after-sequence", type=int, default=0)
    args = parser.parse_args()
    import memoryctl

    print(
        json.dumps(
            ingest(
                memoryctl,
                args.producer_db,
                source_instance=args.source_instance,
                subject=args.subject,
                limit=args.limit,
                after_sequence=args.after_sequence,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
