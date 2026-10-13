"""Opt-in stdio MCP access to an owner's existing HMK pools; no writer/learner."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Literal

from deep_recall import Reader

BINDING = "hmk.deep-recall.binding/v1"
INSTRUCTIONS = (
    "HMK is this being's durable memory. Consult hmk_recall when past encounters, "
    "relationships, projects, decisions or lessons would help the current human task, "
    "without waiting for an explicit memory-search request. Skip self-contained tasks. "
    "Search is navigation: read originals and all pages before factual claims. "
    "Preserve source attribution, corrections, dates, uncertainty and failed outcomes. "
    "Use the latest revision; remember that historical abilities are not current capabilities. "
    "No matches are not proof of absence; unavailable memory is not forgotten memory. "
    "This tool reads existing owner-bound live pools, including new records. "
    "It does not import private sessions, generate learning, grant authority or write memory."
)


def load_binding(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("binding must be a regular owner-local file")
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise ValueError("binding must be owned by caller and not writable by others")
    binding = json.loads(path.read_text())
    if (
        binding.get("schema") != BINDING
        or not all(
            isinstance(binding.get(k), str) and binding[k]
            for k in ("being_ref", "body_ref")
        )
        or not isinstance(binding.get("pools"), list)
        or not 1 <= len(binding["pools"]) <= 8
    ):
        raise ValueError("explicit versioned being/body/pool binding required")
    if binding.get('retrieval', 'lexical') not in {'lexical','hybrid'}:
        raise ValueError('unsupported receiving retrieval mode')
    names, paths = set(), set()
    for pool in binding["pools"]:
        name, database = pool.get("name"), pool.get("database")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name)
            or name in names
        ):
            raise ValueError("unique short pool name required")
        if (
            not isinstance(database, str)
            or not Path(database).is_absolute()
            or database in paths
        ):
            raise ValueError("unique absolute owner-selected database path required")
        names.add(name)
        paths.add(database)
    return binding


def recall(
    binding,
    *,
    action,
    query="",
    record_uid="",
    pool="",
    offset=0,
    expected_revision=None,
):
    pools = binding["pools"]
    if pool:
        pools = [p for p in pools if p["name"] == pool]
    if not pools or (action != "search" and len(pools) != 1):
        return dict(
            status="invalid_request",
            detail="Read/history needs a known pool name from search.",
        )
    if expected_revision is not None and (
        type(expected_revision) is not int or expected_revision < 1
    ):
        return dict(
            status="invalid_request",
            detail="expected_revision must be a positive integer or null",
        )
    if action == "read" and offset > 0 and expected_revision is None:
        return dict(
            status="invalid_request",
            detail="Further pages require the first page revision.",
        )
    budget = max(2000, (24000 - 1500) // len(pools))
    responses = []
    for selected in pools:
        reader = Reader.live_pool(
            selected["database"],
            being_ref=binding["being_ref"],
            body_ref=binding["body_ref"],
            max_bytes=budget,
            retrieval=binding.get('retrieval','lexical'),
        )
        result = reader.call(
            dict(action=action, query=query, record_uid=record_uid, offset=offset)
        )
        current = (
            result.get("record")
            if action == "read"
            else result.get("current_reference")
        )
        if (
            expected_revision is not None
            and current
            and current["revision"] != expected_revision
        ):
            result = dict(
                status="revision_changed",
                current_revision=current["revision"],
                detail="Restart the read from offset zero; do not join pages from different revisions.",
            )
        responses.append(dict(pool=selected["name"], result=result))
    result = dict(
        being_ref=binding["being_ref"], body_ref=binding["body_ref"], pools=responses
    )
    if len(json.dumps(result, ensure_ascii=False).encode()) > 24000:
        return dict(
            status="budget_exceeded",
            detail="Query one named pool; no evidence was truncated.",
        )
    return result


def server(binding):
    # Optional dependency; ordinary HMK commands remain stdlib-only.
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    app = FastMCP("HMK durable recall", instructions=INSTRUCTIONS, log_level="WARNING")

    @app.tool(
        name="hmk_recall",
        description=INSTRUCTIONS,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def hmk_recall(
        action: Literal["search", "read", "history"],
        query: str = "",
        record_uid: str = "",
        pool: str = "",
        offset: int = 0,
        expected_revision: int | None = None,
    ) -> dict:
        """Search all pools or one named pool; read/history use its name and UID.

        Search with concrete words, names or places; refinement is lexical.
        Pass expected_revision from search/first page when reading more pages.
        Unknown applicability remains unknown. Matrix-origin history is external.
        """
        return recall(
            binding,
            action=action,
            query=query,
            record_uid=record_uid,
            pool=pool,
            offset=offset,
            expected_revision=expected_revision,
        )

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    args = parser.parse_args()
    server(load_binding(args.binding)).run(transport="stdio")


if __name__ == "__main__":
    main()
