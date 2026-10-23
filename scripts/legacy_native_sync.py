"""Read-only decoder for the retained compaii.private-native-sync/v1 sidecar.

This preserves unsigned pool lineage. It cannot supply a missing historical
body/incarnation, create a native event, or authorize a receiving operation.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "compaii.private-native-sync/v1"
PREFIX = "hmk-native-sync:v1:"


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def original_hash(label, original):
    # Exact existing Matrix owner_sync.native_reconcile.origin_key contract.
    return digest(
        dict(pool_lineage=label, native_chapter_id=original["id"], revision=original)
    )


class Legacy:
    def __init__(self, state):
        if (
            not isinstance(state, dict)
            or set(state) != {"schema", "origins", "bindings", "plans", "edges"}
            or state["schema"] != SCHEMA
        ):
            raise ValueError("exact retained native provenance sidecar required")
        self.state = state
        self.by_chapter = {}
        for key, value in state["bindings"].items():
            lineage, origin = key.rsplit(":", 1)
            self.by_chapter.setdefault((lineage, value["chapter_id"]), []).append(
                (origin, value)
            )

    def source(self, key):
        value = self.state["origins"].get(key)
        if (
            not isinstance(value, dict)
            or set(value) != {"source_label", "original"}
            or original_hash(value["source_label"], value["original"]) != key
        ):
            raise ValueError("retained native source origin hash differs")
        return dict(
            origin_hash=key,
            pool_lineage=value["source_label"],
            original=value["original"],
        )

    def inspect(self, row, lineage):
        candidates = self.by_chapter.get((lineage, row["id"]), [])
        path = row.get("book_source_path") or ""
        if path.startswith(PREFIX):
            key = path[len(PREFIX) :]
            if not re.fullmatch("[0-9a-f]{64}", key):
                raise ValueError("exact legacy native source reference required")
            self.source(key)
            candidates = [v for v in candidates if v[0] == key]
            if not candidates:
                return dict(sources=[self.source(key)], unchanged=False)
        sources = []
        verified = []
        for origin, position in candidates:
            source = self.source(origin)
            original = source["original"]
            # Old imports started with unused access counters; old reused native
            # rows could retain the source counters. Neither is new authorship.
            shadow = {k: row.get(k) for k in original}
            for counters in (
                {"access_count": 0, "last_access": None},
                {k: original.get(k) for k in ("access_count", "last_access")},
            ):
                candidate = dict(shadow, **counters)
                if digest(candidate) == position["record_hash"]:
                    verified.append(origin)
                    break
            sources.append(source)
        # Added native-revision fields are receiving migration defaults only
        # until a local edit actually changes them; preserve such edits too.
        changed = (
            row.get("revision", 1) != 1
            or json.loads(row.get("source_metadata_json") or "{}")
            or any(
                row.get(k) is not None for k in ("actor", "event_ts", "location_json")
            )
        )
        return dict(
            sources=sorted(sources, key=lambda v: v["origin_hash"]),
            unchanged=len(sources) == 1 and len(verified) == 1 and not changed,
        )

    def receiving(self, con, source_hash, lineage):
        matches = []
        for (label, chapter), positions in self.by_chapter.items():
            if label != lineage or not any(key == source_hash for key, _ in positions):
                continue
            row = con.execute(
                "SELECT c.*,b.title AS book_title,b.slug AS book_slug,"
                "b.source_path AS book_source_path,b.source_kind AS book_source_kind,"
                "s.name AS shelf_name FROM chapters c JOIN books b ON b.id=c.book_id "
                "JOIN shelves s ON s.id=b.shelf_id WHERE c.id=?",
                (chapter,),
            ).fetchone()
            if row is not None:
                found = self.inspect(dict(row), lineage)
                if (
                    found["unchanged"]
                    and found["sources"][0]["origin_hash"] == source_hash
                ):
                    matches.append(chapter)
        if len(matches) > 1:
            raise ValueError(
                "ambiguous legacy receiving representation; preserve variants"
            )
        return matches[0] if matches else None


def load(path, expected_sha256):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("legacy provenance aliases require local reconciliation")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("owner-private native provenance required")
        raw = stream.read(64 * 1024 * 1024 + 1)
    if (
        len(raw) > 64 * 1024 * 1024
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise ValueError("selected legacy provenance changed")
    return Legacy(json.loads(raw))
