"""Exercise pinned upstream memory SQL on fictional in-memory data, not a daemon.

No Codex home, sessions, providers or real memory databases are opened.
This diagnoses snapshot polling loss; it is not a native extraction quality test.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess

REVISION = "092d3acd6bec3e3a14bdc7e7a2810ab628ab759d"  # rust-v0.162.1
SOURCE = "codex-rs/state/src/runtime/memories.rs"
MIGRATION = "codex-rs/state/memory_migrations/0001_memories.sql"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-repo", required=True)
    args = parser.parse_args()

    def source(path):
        return subprocess.check_output(
            ["git", "-C", args.codex_repo, "show", f"{REVISION}:{path}"], text=True
        )

    text = source(SOURCE)
    migration = source(MIGRATION)
    queries = re.findall(r'r#"(.*?)"#', text, re.S)
    upsert = next(q for q in queries if "INSERT INTO stage1_outputs (" in q)
    delete = next(q for q in queries if q.strip() == "DELETE FROM stage1_outputs\nWHERE thread_id = ?")
    prune = next(q for q in queries if "DELETE FROM stage1_outputs" in q and "COALESCE(last_usage" in q)
    con = sqlite3.connect(":memory:")
    con.executescript(migration)

    def write(timestamp, raw):
        con.execute(upsert, ("fictional-thread", timestamp, raw, raw, "invitation", timestamp))

    def current():
        return con.execute("SELECT raw_memory FROM stage1_outputs").fetchall()

    write(10, "An invitation was prepared; delivery is unknown.")
    write(20, "Delivery failed; there was no acceptance.")
    assert current() == [("Delivery failed; there was no acceptance.",)]
    # Timestamp alone cannot identify immutable revisions: equal timestamps replace.
    write(20, "Delivery failed; the later repair remains unverified.")
    assert current() == [("Delivery failed; the later repair remains unverified.",)]
    write(10, "Older stale output")
    assert current() == [("Delivery failed; the later repair remains unverified.",)]
    con.execute(delete, ("fictional-thread",))
    assert current() == []
    write(30, "A significant unused encounter.")
    con.execute(prune, (100, 200))
    assert current() == []
    con.close()
    print(json.dumps({
        "schema": "hmk.native-producer-storage-diagnostic/v1",
        "upstream_commit": REVISION,
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "migration_sha256": hashlib.sha256(migration.encode()).hexdigest(),
        "witnesses": {
            "later_output_replaces_previous": True,
            "equal_timestamp_can_replace_content": True,
            "older_timestamp_is_ignored": True,
            "no_output_removes_current_row": True,
            "retention_removes_unselected_old_row": True,
        },
        "scope": "Exact upstream SQL and schema; no worker, inference or proposed adapter executed.",
        "inference_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
