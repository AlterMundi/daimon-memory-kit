"""Bounded, selected HMK reads for client-hosted harness tools.

The host supplies the database and selection; model arguments cannot change them.
No native learner, capture, admission, migration or access-counter writes occur.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import sqlite3
import time

import codex_projection as projection
import memoryctl as memory
import memory_navigation

TOOL = "hmk_recall"
ROUTE = "hmk.deep-recall.route/v1"
RESULT = "hmk.deep-recall.result/v1"


def tool_spec():
    return dict(
        name=TOOL,
        description=(
            "Read selected durable being memory beyond the bounded native view. "
            "Use for relevant past encounters, project contributions, outcomes or lessons "
            "when the view is insufficient. Search returns navigation, not complete evidence; "
            "Candidates may be unrelated; read originals and assess relevance before factual claims. "
            "Do not recite unrelated memories when the question lacks support. "
            "No matches do not establish canon absence. "
            "Remembered abilities do not grant current tools. Unrelated tasks need no recall."
        ),
        inputSchema=dict(
            type="object",
            properties={
                "action": dict(type="string", enum=["search", "read", "history"]),
                "query": dict(
                    type="string", description="Search words; empty for read/history."
                ),
                "record_uid": dict(
                    type="string",
                    description="Stable UID from search; empty for search.",
                ),
                "offset": dict(
                    type="integer",
                    minimum=0,
                    description="Raw-text character offset for read; revision index for history; zero for search.",
                ),
            },
            required=["action", "query", "record_uid", "offset"],
            additionalProperties=False,
        ),
    )


def route_descriptor():
    return dict(schema=ROUTE, tool=TOOL)


def navigation(route):
    if route != route_descriptor():
        raise ValueError("unsupported deep recall route")
    return (
        "\nThe native files are a bounded selection, not the whole canon. "
        "When a relevant memory question needs more evidence, use hmk_recall "
        "to search deeper and read current originals or their history. A native "
        "miss does not establish canonical absence. Search results and links are "
        "navigation; read complete evidence, including corrections. An unavailable "
        "route means unknown availability, not forgotten experience. Skip recall "
        "for tasks where past experience adds nothing.\n"
    )


class Reader:
    """One host-bound selection, checked against current revisions on every call.

    Lexical navigation is the default. The host may explicitly select hybrid
    retrieval using the configured embedding space and ranking services.
    """

    def __init__(self, database, selection, *, max_bytes=12000, retrieval='lexical'):
        if type(max_bytes) is not int or not 2000 <= max_bytes <= 32000:
            raise ValueError("max_bytes must be 2000..32000")
        # Reuse the projection's authority, applicability and source validation.
        projection.load_sources(database, selection)
        self.database = database
        self.selection = copy.deepcopy(selection)
        self.entries = {r["record_uid"]: r for r in self.selection["records"]}
        self.max_bytes = max_bytes
        if retrieval not in {'lexical','hybrid'}:
            raise ValueError('unsupported retrieval mode')
        self.retrieval = retrieval

    @classmethod
    def live_pool(cls, database, *, being_ref, body_ref, max_bytes=12000, retrieval='lexical'):
        """One request against an owner-selected live pool, including later writes.

        Applicability stays unknown unless retained explicitly. Matrix rows keep
        their projection origin and do not become HMK-native canonical records.
        """
        if type(max_bytes) is not int or not 2000 <= max_bytes <= 32000:
            raise ValueError("max_bytes must be 2000..32000")
        if not all(isinstance(x, str) and x for x in (being_ref, body_ref)):
            raise ValueError("explicit owner/body binding required")
        result = cls.__new__(cls)
        result.database = database
        result.selection = dict(being_ref=being_ref, body_ref=body_ref)
        result.entries = {}
        result.max_bytes = max_bytes
        if retrieval not in {'lexical','hybrid'}:
            raise ValueError('unsupported retrieval mode')
        result.retrieval = retrieval
        result.live = True
        return result

    def _result(self, status, **fields):
        return dict(
            schema=RESULT,
            status=status,
            being_ref=self.selection["being_ref"],
            body_ref=self.selection["body_ref"],
            retrieval=self.retrieval,
            coverage="owner-selected-live-pool"
            if getattr(self, "live", False)
            else "host-selected-records-only",
            **fields,
        )

    def _navigation(self, row):
        result = dict(
            record_uid=row["record_uid"],
            revision=row["revision"],
            title=row["title"],
            relevance='unassessed; candidate navigation is not factual support',
            reference=f"mem:{row['record_uid']}@{row['revision']}",
            applicability=self.entries.get(row["record_uid"], {}).get("applicability",
                row.get('applicability', {"kind":"unknown","targets":[]})),
        )
        if row.get('historical'):
            result.update(historical=True, current_revision=row.get('current_revision'))
        return result

    def call(self, arguments):
        started = time.monotonic()
        try:
            if (
                not isinstance(arguments, dict)
                or set(arguments) != {"action", "query", "record_uid", "offset"}
                or arguments["action"] not in {"search", "read", "history"}
                or any(
                    not isinstance(arguments[k], str) for k in ("query", "record_uid")
                )
                or len(arguments["query"]) > 1000
                or type(arguments["offset"]) is not int
                or arguments["offset"] < 0
            ):
                raise ValueError("invalid read request")
            with memory.read_scope(self.database):
                con = memory.connect()
                live = getattr(self, "live", False)
                ids = {}
                # A live read checks only its requested record. A search ranks
                # over the bound pool without loading its full metadata into RAM.
                if live:
                    uid = arguments['record_uid']
                    if uid:
                        row = con.execute("SELECT c.id,c.revision,c.source_metadata_json FROM chapters c "
                            "LEFT JOIN daimon_projections p ON p.chapter_id=c.id "
                            "WHERE c.record_uid=? AND (p.active IS NULL OR p.active=1)",(uid,)).fetchone()
                        if row:
                            ids[uid] = row['id']
                            self.entries[uid] = dict(revision=row['revision'],applicability=
                                json.loads(row['source_metadata_json'] or '{}').get('applicability',{'kind':'unknown','targets':[]}))
                else:
                    for uid, entry in self.entries.items():
                        row = con.execute('SELECT id,revision FROM chapters WHERE record_uid=?',(uid,)).fetchone()
                        if row is None or row['revision'] != entry['revision']:
                            return self._result('stale_binding', detail='Refresh the host selection before use.')
                        ids[uid] = row['id']
                action = arguments["action"]
                if action == "search":
                    if (
                        not memory.tokenize_query(arguments["query"])
                        or arguments["offset"]
                    ):
                        raise ValueError("search requires words and offset zero")
                    found = memory_navigation.search(memory, arguments['query'], mode=self.retrieval,
                        record_uids=None if live else list(ids), limit=8)
                    selected = [self._navigation(r) for r in found['items']]
                    history = [self._navigation(r) for r in found['historical_matches']]
                    result = self._result('ok' if selected or history else
                        'unavailable' if found['retrieval_status']=='unavailable' else 'no_matches',
                        items=selected, historical_matches=history, navigation_only=True,
                        retrieval_status=found['retrieval_status'],backend_errors=found['backend_errors'],
                        detail=found['coverage'])
                else:
                    uid = arguments["record_uid"]
                    if uid not in ids:
                        return self._result("not_in_selection")
                    current = memory._read_chapter(ids[uid])
                    projected = current["origin"]["kind"] == "daimon-projection"
                    if projected and not getattr(self, "live", False):
                        return self._result(
                            "unavailable",
                            detail="Requires the verified owning Matrix adapter.",
                        )
                    if action == "history":
                        if projected:
                            return self._result(
                                "external_history",
                                origin=current["origin"],
                                detail="Accepted Matrix history belongs to its owning adapter; no native preimages or ledger freshness are asserted.",
                            )
                        history = memory.history(ids[uid])
                        index = arguments["offset"]
                        if index >= len(history):
                            result = self._result(
                                "end_of_available_history",
                                current_reference=self._navigation(current),
                                detail="Only available HMK-native preimages; no claim that unavailable history never existed.",
                            )
                        else:
                            result = self._result(
                                "ok",
                                current_reference=self._navigation(current),
                                historical=True,
                                record=history[index],
                                next_offset=index + 1
                                if index + 1 < len(history)
                                else None,
                            )
                    else:
                        offset = arguments["offset"]
                        raw = current.pop("raw")
                        if offset > len(raw):
                            raise ValueError("offset exceeds original")
                        # Page only raw text and explicitly mark incompleteness. Metadata stays whole.
                        current.pop("spr", None)
                        current.pop("last_access", None)
                        current.pop("access_count", None)
                        neighbors = [
                            self._navigation(r)
                            for r in memory.recall_neighbors(ids[uid], record_uids=None if live else list(ids))
                        ]
                        result = self._result(
                            "ok",
                            record=current,
                            applicability=self.entries[uid]["applicability"],
                            neighbors=neighbors,
                            raw_offset=offset,
                            raw=raw[offset:],
                            next_offset=None,
                            complete=offset == 0,
                        )
                        if projected:
                            result["authority_note"] = (
                                "Existing Matrix retrieval projection; origin retained, no ledger freshness verification or new admission."
                            )
                        while (
                            len(json.dumps(result, ensure_ascii=False).encode())
                            > self.max_bytes - 200
                            and result["raw"]
                        ):
                            result["raw"] = result["raw"][: len(result["raw"]) // 2]
                            result["next_offset"] = offset + len(result["raw"])
                            result["complete"] = False
            if isinstance(result.get("record"), dict):
                # Preserve original epoch fields and supply their exact calendar
                # representation; these are local storage times, not event dates.
                record = result["record"]
                storage = {}
                for field in ("created_at", "updated_at", "changed_at"):
                    value = record.get(field)
                    if type(value) in {int, float}:
                        try:
                            storage[field] = datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
                        except (OverflowError, OSError, ValueError):
                            pass
                result["local_storage_time_utc"] = storage
            result["seconds"] = round(time.monotonic() - started, 6)
            if len(json.dumps(result, ensure_ascii=False).encode()) > self.max_bytes:
                return self._result(
                    "budget_exceeded",
                    detail="No truncated evidence returned. Host must select a larger bounded budget.",
                )
            return result
        except (sqlite3.Error, OSError):
            return self._result(
                "unavailable",
                detail="Canon cannot currently be read; this is not absence.",
            )
        except ValueError as exc:
            # Missing canon and invalid model requests are distinct states.
            if str(exc).startswith("read scope needs"):
                return self._result(
                    "unavailable",
                    detail="Canon cannot currently be read; this is not absence.",
                )
            return self._result("invalid_request", detail=str(exc))

    def app_server_response(self, arguments):
        result = self.call(arguments)
        return dict(
            contentItems=[
                dict(type="inputText", text=json.dumps(result, ensure_ascii=False))
            ],
            success=result["status"]
            in {"ok", "no_matches", "end_of_available_history", "not_in_selection"},
        )
