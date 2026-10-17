"""Verified online SQLite snapshots, including committed WAL pages."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time
import uuid


def verified_snapshot(source, destination, *, timeout=30):
    """Create a new private snapshot; never overwrite an existing recovery file.

    SQLite's backup API reads a consistent database, including its journal.
    Only verified snapshots appear at destination. Failed/interrupted candidates
    remain under a distinct partial name, never mistaken for a usable backup by
    callers that resume when destination exists. This does not repair the source.
    """
    source, destination = Path(source), Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    candidate = destination.with_name('.'+destination.name+'.partial-'+uuid.uuid4().hex)
    fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    started = time.monotonic()

    def progress(status, remaining, total):
        if time.monotonic() - started > timeout:
            raise TimeoutError("SQLite snapshot exceeded its time budget")

    src = dst = None
    try:
        src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(candidate)
        src.backup(dst, pages=256, progress=progress, sleep=0.05)
        # A recovery snapshot is a standalone file. The source's WAL mode may
        # be copied by backup; normalize the destination before verifying it.
        if dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
            raise RuntimeError("SQLite snapshot could not become standalone")
        if dst.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RuntimeError("SQLite snapshot failed integrity verification")
        if dst.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("SQLite snapshot has foreign-key violations")
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()
    # Publish without overwriting a concurrent winner. A crash before this point
    # leaves only the private candidate; a crash afterward leaves a valid target.
    with candidate.open('rb') as verified:
        os.fsync(verified.fileno())
    os.link(candidate, destination)
    candidate.unlink()
    directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return destination
