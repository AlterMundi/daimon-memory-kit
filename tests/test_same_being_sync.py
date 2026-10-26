"""Real current DMK APIs: transaction recovery, attribution and live-write coexistence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import same_being_sync as sync  # noqa: E402 - resolve the selected source tree first


def load_memory(monkeypatch, path, name):
    path.mkdir()
    monkeypatch.setenv("HMK_AGENT_MEMORY_BASE", str(path))
    monkeypatch.setenv("HMK_DB_PATH", str(path / "library.db"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/memoryctl.py")
    memory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory)
    memory.init_db()
    return memory


@pytest.fixture
def pools(tmp_path, monkeypatch):
    return tuple(
        load_memory(monkeypatch, tmp_path / name, "sync_memory_" + name)
        for name in ("source", "target")
    )


def owner(body, being="same-being"):
    return dict(
        being_ref=being,
        body_ref=body,
        embodiment_id="embodiment:" + body,
        incarnation_id="incarnation:" + body,
        pool_lineage="native-" + body,
    )


def canonical_rows(memory):
    with memory.connect() as con:
        return [
            sync.record(con, r[0])
            for r in con.execute("select id from chapters order by id")
        ]


def packet(memory, body="source", **kwargs):
    return sync.export(memory.DB_PATH, owner(body), **kwargs)


def test_import_preserves_metadata_history_and_original_pool(pools):
    source, target = pools
    identifier = source.add_text(
        "episodes",
        "A remembered event",
        "older original wording",
        actor="Human report",
        event_ts=123,
        engram_type="episodic",
        location={"place": "fixture"},
        metadata={
            "source_instance": "original-body",
            "date_precision": "day",
            "mode": "reported",
        },
        summary="A chosen summary",
    )
    source.update_chapter(identifier, content="corrected original wording")
    before = canonical_rows(source)
    incoming = packet(source)
    result = sync.apply(target, incoming, owner("target"), operation_id="first")
    assert result["imported"] == 1 and result["models_started"] == 0
    imported = target.expand(result["entries"][0]["target_chapter_id"])
    assert imported["raw"] == "corrected original wording"
    assert imported["actor"] == "Human report" and imported["event_ts"] == 123
    assert imported["engram_type"] == "episodic"
    assert (
        json.loads(imported["source_metadata_json"])["source_instance"]
        == "original-body"
    )
    assert canonical_rows(source) == before
    with target.connect() as con:
        doc = json.loads(
            con.execute("select document from dmk_sync_origins").fetchone()[0]
        )
    assert doc["source_binding"] == dict(owner("source"), incarnation_id=None)
    with target.connect() as con:
        assert (
            json.loads(sync._history_rows(con, doc)[0]["snapshot_json"])["raw"]
            == "older original wording"
        )
    history = target.history(imported["id"])
    assert history[0]["raw"] == "older original wording"
    assert history[0]["same_being_native_origin"]["source_binding"] == dict(
        owner("source"), incarnation_id=None
    )
    assert history[-1]["raw"] == "corrected original wording"
    assert history[-1]["record_uid"] == doc["record"]["record_uid"]


def test_lost_response_and_new_receiving_query_additions_do_not_duplicate(pools):
    source, target = pools
    source.add_text("library", "source fact", "source factual content")
    incoming = packet(source)
    first = sync.apply(target, incoming, owner("target"), operation_id="stable")
    target.add_text("library", "independent work", "new independent work")
    target.expand(
        first["entries"][0]["target_chapter_id"]
    )  # access counters may change
    second = sync.apply(target, incoming, owner("target"), operation_id="stable")
    third = sync.apply(target, incoming, owner("target"), operation_id="another-cycle")
    assert second == dict(first, reused=True)
    assert third["imported"] == 0 and third["reused_origins"] == 1
    assert len(canonical_rows(target)) == 2


def test_failure_before_commit_rolls_back_canonical_writes_and_receipts(pools):
    source, target = pools
    source.add_text("library", "one", "first")
    source.add_text("library", "two", "second")
    incoming = packet(source)

    def interrupted(_):
        raise RuntimeError("synthetic lost worker")

    with pytest.raises(RuntimeError, match="synthetic lost worker"):
        sync.apply(
            target,
            incoming,
            owner("target"),
            operation_id="interrupted",
            after_effect=interrupted,
        )
    assert canonical_rows(target) == []
    with target.connect() as con:
        assert not sync.table(con, "dmk_sync_operations")
    assert (
        sync.apply(target, incoming, owner("target"), operation_id="interrupted")[
            "imported"
        ]
        == 2
    )


def test_reverse_export_reuses_origins_and_preserves_receiving_edits(pools):
    source, target = pools
    source.add_text("library", "one", "shared original")
    incoming = packet(source)
    result = sync.apply(target, incoming, owner("target"), operation_id="receive")
    reverse = packet(target, "target")
    assert reverse["records"] == incoming["records"]
    target.update_chapter(
        result["entries"][0]["target_chapter_id"], content="local distinct variant"
    )
    changed = packet(target, "target")
    doc = changed["records"][0]["document"]
    assert doc["prior_origins"] == [incoming["records"][0]["origin_hash"]]
    assert doc["source_binding"]["body_ref"] == "target"
    assert doc["record"]["raw"] == "local distinct variant"
    before = canonical_rows(target)
    with pytest.raises(ValueError, match="preserve local variant"):
        sync.apply(target, incoming, owner("target"), operation_id="receive")
    assert canonical_rows(target) == before


def test_changed_selection_or_other_being_fails_without_effect(pools):
    source, target = pools
    source.add_text("library", "one", "source")
    incoming = packet(source)
    with pytest.raises(ValueError, match="same-being"):
        sync.apply(
            target, incoming, owner("other", "another-being"), operation_id="other"
        )
    assert canonical_rows(target) == []
    sync.apply(target, incoming, owner("target"), operation_id="retained")
    changed = copy.deepcopy(incoming)
    changed["cursor"] += 1
    with pytest.raises(ValueError, match="selection changed"):
        sync.apply(target, changed, owner("target"), operation_id="retained")


def test_paginated_links_reconcile_after_all_endpoints_arrive(pools):
    source, target = pools
    first = source.add_text("library", "first", "first original")
    second = source.add_text("library", "second", "second original")
    source.add_link(first, second, "supports", weight=0.7, note="original edge")
    one = packet(source, limit=1)
    r1 = sync.apply(target, one, owner("target"), operation_id="page1")
    assert r1["links"]["pending"] == 1
    two = packet(source, after=one["cursor"], limit=1)
    r2 = sync.apply(target, two, owner("target"), operation_id="page2")
    assert r2["links"]["applied"] == 1
    with target.connect() as con:
        edges = con.execute("select * from chapter_links").fetchall()
        assert len(edges) == 1 and edges[0]["note"] == "original edge"


def test_access_only_change_does_not_generate_a_new_origin(pools):
    source, _ = pools
    identifier = source.add_text("library", "one", "remember this")
    before = packet(source)
    source.expand(identifier)
    assert packet(source)["records"] == before["records"]
    assert packet(source, known=[before["records"][0]["origin_hash"]])["records"] == []


def test_real_round_trip_does_not_reimport_the_original_native_record(pools):
    source, target = pools
    identifier = source.add_text("library", "original", "one shared memory")
    initial = packet(source)
    sync.apply(target, initial, owner("target"), operation_id="forward")
    reverse = packet(target, "target")
    result = sync.apply(source, reverse, owner("source"), operation_id="back")
    assert result["imported"] == 0
    assert result["entries"][0]["target_chapter_id"] == identifier
    assert len(canonical_rows(source)) == len(canonical_rows(target)) == 1
    assert packet(source)["records"] == initial["records"]


def test_reobserving_from_new_incarnation_does_not_reauthor_memory(pools):
    source, _ = pools
    source.add_text("library", "original", "stable memory")
    initial = packet(source)
    changed = owner("source")
    changed["incarnation_id"] = "incarnation:later"
    later = sync.export(source.DB_PATH, changed)
    assert initial["exporter"] != later["exporter"]
    assert initial["records"] == later["records"]
    assert later["records"][0]["document"]["source_binding"]["incarnation_id"] is None


def test_linear_source_correction_updates_untouched_mirror_with_both_histories(pools):
    source, target = pools
    identifier = source.add_text("library", "original", "first wording")
    first = sync.apply(target, packet(source), owner("target"), operation_id="first")
    mirror = first["entries"][0]["target_chapter_id"]
    old_uid = target.expand(mirror)["record_uid"]
    source.update_chapter(identifier, content="corrected wording")
    incoming = packet(source)
    second = sync.apply(target, incoming, owner("target"), operation_id="correction")
    assert second["entries"][0]["target_chapter_id"] == mirror
    assert len(canonical_rows(target)) == 1
    assert target.expand(mirror)["record_uid"] == old_uid
    history = target.history(mirror)
    assert any(
        r["raw"] == "first wording" and r.get("same_being_native_origin")
        for r in history
    )
    assert any(
        r["raw"] == "first wording" and not r.get("same_being_native_origin")
        for r in history
    )
    assert packet(target, "target")["records"] == incoming["records"]


def test_source_kind_correction_preserves_embedding_disable_policy(pools):
    source, target = pools
    identifier = source.add_text("library", "original", "same content")
    first = sync.apply(target, packet(source), owner("target"), operation_id="first")
    source.update_chapter(identifier, source_kind="config")
    second = sync.apply(
        target, packet(source), owner("target"), operation_id="classified"
    )
    assert (
        target.expand(second["entries"][0]["target_chapter_id"])["embed_disabled"] == 1
    )
    assert (
        first["entries"][0]["target_chapter_id"]
        == second["entries"][0]["target_chapter_id"]
    )


def test_retained_receipt_checks_actual_links_before_claiming_current_success(pools):
    source, target = pools
    a = source.add_text("library", "a", "first")
    b = source.add_text("library", "b", "second")
    source.add_link(a, b, "supports", note="original")
    incoming = packet(source)
    sync.apply(target, incoming, owner("target"), operation_id="links")
    with target.connect() as con:
        edge = con.execute("select * from chapter_links").fetchone()
    target.add_link(
        edge["src_chapter_id"], edge["dst_chapter_id"], "supports", note="local edit"
    )
    with pytest.raises(ValueError, match="edge effect changed"):
        sync.status(
            target, operation_id="links", packet=incoming, owner=owner("target")
        )
    assert len(canonical_rows(target)) == 2


def test_legacy_generated_rows_cannot_be_reauthored_as_the_exporting_body(pools):
    source, _ = pools
    source.add_text(
        "library",
        "old import",
        "old original",
        source_path="hmk-native-sync:v1:" + "a" * 64,
    )
    with pytest.raises(ValueError, match="existing selected sidecar adapter"):
        packet(source)


def test_source_kind_only_change_disables_existing_embedding(pools):
    source, _ = pools
    identifier = source.add_text("library", "policy", "ordinary memory")
    with source.connect() as con:
        con.execute(
            "INSERT INTO chapter_embeddings(chapter_id,provider,model,input_text_hash,dims,embedding_json,created_at,updated_at) VALUES(?,'fixture','fixture','x',2,'[0.0,1.0]',1,1)",
            (identifier,),
        )
    result = source.update_chapter(identifier, source_kind="config")
    assert result["content_changed"] is False
    assert result["embeddings_dropped"] == 1
    assert source.expand(identifier)["embed_disabled"] == 1


def test_cli_reuses_one_parent_checkpoint_and_does_not_expose_memory(pools, tmp_path):
    import os
    import subprocess

    source, target = pools
    source.add_text("library", "private fixture", "private original sentinel")
    incoming = packet(source)
    packet_path = tmp_path / "packet.json"
    packet_path.write_bytes(sync.wire(incoming))
    binding_path = tmp_path / "binding.json"
    binding_path.write_text(json.dumps(owner("target")))
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps(
            dict(
                database=str(target.DB_PATH),
                snapshots=dict(
                    directory=str(tmp_path / "checkpoints"),
                    max_count=3,
                    max_bytes=128 * 1024 * 1024,
                    min_free_bytes=1,
                    keep_latest=2,
                    pins=[],
                    retention_scope="database",
                ),
            )
        )
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("HMK_", "HERMES_", "AGENT_MEMORY_"))
    }
    env.update(
        HMK_AGENT_MEMORY_BASE=str(Path(target.DB_PATH).parent),
        HMK_DB_PATH=str(target.DB_PATH),
    )
    command = [
        sys.executable,
        str(ROOT / "scripts/same_being_sync.py"),
        "apply",
        "--binding",
        str(binding_path),
        "--packet",
        str(packet_path),
        "--packet-sha256",
        sync.digest(incoming),
        "--operation",
        "same-receipt",
        "--backup-config",
        str(backup),
        "--checkpoint-operation",
        "whole-integration",
    ]
    first = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
    snapshots = list((tmp_path / "checkpoints").glob("batch-*-before.sqlite"))
    assert len(snapshots) == 1
    before = snapshots[0].stat().st_mtime_ns
    second = subprocess.run(
        command, env=env, capture_output=True, text=True, check=True
    )
    assert (
        "private original sentinel"
        not in first.stdout + first.stderr + second.stdout + second.stderr
    )
    assert json.loads(second.stdout)["reused"] is True
    assert len(canonical_rows(target)) == 1
    assert len(list((tmp_path / "checkpoints").glob("batch-*-before.sqlite"))) == 1
    assert snapshots[0].stat().st_mtime_ns == before


def test_revision_content_is_reused_and_missing_closure_precedes_any_effect(pools):
    source, target = pools
    identifier = source.add_text("library", "original", "first original")
    source.update_chapter(identifier, content="second original")
    first_packet = packet(source)
    first = sync.apply(target, first_packet, owner("target"), operation_id="first")
    with target.connect() as con:
        hashes = [r[0] for r in con.execute("select sha256 from dmk_sync_content")]
    source.update_chapter(identifier, content="third original")
    second_packet = packet(source, known_content=hashes)
    assert len(second_packet["content"]) == 1
    assert len(second_packet["records"][0]["document"]["history"]) == 2
    missing = copy.deepcopy(second_packet)
    missing["content"] = []
    before = canonical_rows(target)
    with pytest.raises(ValueError, match="content unavailable"):
        sync.apply(target, missing, owner("target"), operation_id="missing")
    assert canonical_rows(target) == before
    second = sync.apply(target, second_packet, owner("target"), operation_id="second")
    assert (
        second["entries"][0]["target_chapter_id"]
        == first["entries"][0]["target_chapter_id"]
    )
    with target.connect() as con:
        assert con.execute("select count(*) from dmk_sync_content").fetchone()[0] == 2
        docs = [
            json.loads(r[0])
            for r in con.execute("select document from dmk_sync_origins")
        ]
        assert all("snapshot_json" not in ref for doc in docs for ref in doc["history"])
    assert [
        r["raw"]
        for r in target.history(second["entries"][0]["target_chapter_id"])
        if r.get("same_being_native_origin")
    ] == ["first original", "second original", "third original"]


def test_unreferenced_content_is_not_adopted_into_memory(pools):
    source, target = pools
    source.add_text("library", "original", "source original")
    incoming = packet(source)
    extra = dict(snapshot_json="{}")
    incoming["content"] = [dict(sync.content_ref(extra), value=extra)]
    with pytest.raises(ValueError, match="unselected native revision"):
        sync.apply(target, incoming, owner("target"), operation_id="extra")
    assert canonical_rows(target) == []


def legacy_fixture(source, target):
    """The old writer's actual columns, tags, digest and receiving sidecar format."""
    from legacy_native_sync import Legacy, original_hash, digest

    native = source.add_text(
        "episodes",
        "Original source memory",
        "old native wording",
        summary="original chosen summary",
    )
    with source.connect() as con:
        original = dict(sync.record(con, native), access_count=0, last_access=None)
    for key in (
        "record_uid",
        "revision",
        "engram_type",
        "source_metadata_json",
        "actor",
        "event_ts",
        "location_json",
    ):
        original.pop(key)
    key = original_hash("native-source", original)
    old = target.add_text(
        "episodes",
        "Sync " + key + " " + original["title"],
        original["raw"],
        tags=[
            *json.loads(original["tags_json"]),
            "legacy-sync",
            "source:native-source",
        ],
        importance=original["importance"],
        source_path="hmk-native-sync:v1:" + key,
        source_kind=original["book_source_kind"],
    )
    with target.connect() as con:
        receiving = dict(sync.record(con, old), access_count=0, last_access=None)
    receiving = {k: receiving[k] for k in original}
    state = dict(
        schema="compaii.private-native-sync/v1",
        origins={key: dict(source_label="native-source", original=original)},
        bindings={
            "native-target:" + key: dict(chapter_id=old, record_hash=digest(receiving)),
            "native-source:" + key: dict(
                chapter_id=native, record_hash=digest(original)
            ),
        },
        plans={},
        edges={},
    )
    return native, old, key, Legacy(state)


def test_legacy_import_and_original_share_one_origin_without_reimporting(pools):
    source, target = pools
    native, old, key, legacy = legacy_fixture(source, target)
    forward = packet(source, legacy=legacy)
    reverse = packet(target, "target", legacy=legacy)
    assert forward["records"] == reverse["records"]
    doc = forward["records"][0]["document"]
    assert doc["source_binding"] == dict(
        owner("source"), body_ref=None, embodiment_id=None, incarnation_id=None
    )
    assert doc["legacy_sources"][0]["origin_hash"] == key
    first = sync.apply(
        target, forward, owner("target"), operation_id="adopt-old", legacy=legacy
    )
    assert first["entries"][0]["target_chapter_id"] == old
    assert len(canonical_rows(target)) == 1
    # Recover the lost source summary through native revisions, not a SQL repair.
    assert target.expand(old)["spr"] == "original chosen summary"
    history = target.history(old)
    assert any(
        r["revision_reason"] == "retained-legacy-original" and r["id"] == native
        for r in history
    )
    assert any(not r.get("same_being_native_origin") for r in history)
    again = packet(target, "target", legacy=legacy)
    assert again["records"] == forward["records"]
    back = sync.apply(
        source, again, owner("source"), operation_id="return-old", legacy=legacy
    )
    assert back["entries"][0]["target_chapter_id"] == native
    assert len(canonical_rows(source)) == 1
    assert packet(source, legacy=legacy)["records"] == forward["records"]
    assert (
        sync.apply(
            target, forward, owner("target"), operation_id="adopt-old", legacy=legacy
        )["reused"]
        is True
    )


def test_selected_legacy_namespace_reuses_record_under_new_canonical_pool(pools):
    from legacy_native_sync import Legacy

    source, target = pools
    _, old, _, previous = legacy_fixture(source, target)
    retained = copy.deepcopy(previous.state)
    selected = Legacy(previous.state, receiving_lineage="native-target")
    renamed = dict(owner("target"), pool_lineage="canonical-target")
    incoming = packet(source, legacy=previous)
    reverse = sync.export(target.DB_PATH, renamed, legacy=selected)
    assert reverse["records"] == incoming["records"]
    first = sync.apply(
        target, incoming, renamed, operation_id="renamed-pool", legacy=selected
    )
    assert first["entries"][0]["target_chapter_id"] == old
    assert len(canonical_rows(target)) == 1
    assert target.expand(old)["spr"] == "original chosen summary"
    assert target.history(old)
    assert sync.apply(
        target, incoming, renamed, operation_id="renamed-pool", legacy=selected
    )["reused"]
    assert previous.state == retained


def test_selected_legacy_namespace_preserves_edited_receiving_variant(pools):
    from legacy_native_sync import Legacy

    source, target = pools
    _, old, key, previous = legacy_fixture(source, target)
    selected = Legacy(previous.state, receiving_lineage="native-target")
    renamed = dict(owner("target"), pool_lineage="canonical-target")
    target.update_chapter(old, content="later receiving correction")
    reverse = sync.export(target.DB_PATH, renamed, legacy=selected)
    doc = reverse["records"][0]["document"]
    assert doc["record"]["raw"] == "later receiving correction"
    assert doc["source_binding"]["pool_lineage"] == "canonical-target"
    assert doc["legacy_sources"][0]["origin_hash"] == key
    incoming = packet(source, legacy=previous)
    applied = sync.apply(
        target, incoming, renamed, operation_id="original-with-variant", legacy=selected
    )
    assert applied["entries"][0]["target_chapter_id"] != old
    assert target.expand(old)["raw"] == "later receiving correction"
    assert len(canonical_rows(target)) == 2


def test_selected_legacy_namespace_refuses_unknown_pool(pools):
    from legacy_native_sync import Legacy

    _, _, _, previous = legacy_fixture(*pools)
    before = copy.deepcopy(previous.state)
    with pytest.raises(ValueError, match="receiving lineage is absent or invalid"):
        Legacy(previous.state, receiving_lineage="unrecorded-local-pool")
    assert previous.state == before


def test_edited_legacy_copy_keeps_original_and_receiving_variant(pools):
    source, target = pools
    _, old, key, legacy = legacy_fixture(source, target)
    target.update_chapter(
        old, content="later local correction", actor="receiving human"
    )
    incoming = packet(source, legacy=legacy)
    edited = packet(target, "target", legacy=legacy)
    doc = edited["records"][0]["document"]
    assert doc["record"]["raw"] == "later local correction"
    assert doc["source_binding"]["body_ref"] == "target"
    assert doc["legacy_sources"][0]["origin_hash"] == key
    preserved = sync.apply(
        source, edited, owner("source"), operation_id="receiving-variant", legacy=legacy
    )
    assert len(canonical_rows(source)) == 2
    imported = preserved["entries"][0]["target_chapter_id"]
    history = source.history(imported)
    assert any(
        r["raw"] == "old native wording"
        and r.get("same_being_native_origin", {}).get("pool_lineage") == "native-source"
        for r in history
    )
    received = sync.apply(
        target, incoming, owner("target"), operation_id="original-also", legacy=legacy
    )
    assert received["entries"][0]["target_chapter_id"] != old
    assert len(canonical_rows(target)) == 2
    assert target.expand(old)["raw"] == "later local correction"
    own = sync.apply(
        target,
        edited,
        owner("target"),
        operation_id="same-local-variant",
        legacy=legacy,
    )
    assert own["entries"][0]["target_chapter_id"] == old
    assert len(canonical_rows(target)) == 2


def test_legacy_sidecar_digest_and_immutable_original_are_required(pools, tmp_path):
    from legacy_native_sync import load

    source, target = pools
    _, _, key, legacy = legacy_fixture(source, target)
    sidecar = tmp_path / "legacy.json"
    sidecar.write_bytes(sync.wire(legacy.state))
    sidecar.chmod(0o600)
    import hashlib

    fingerprint = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    assert load(sidecar, fingerprint).source(key) == legacy.source(key)
    assert load(
        sidecar, fingerprint, receiving_lineage="native-target"
    ).receiving_lineage == "native-target"
    sidecar.write_bytes(sidecar.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="selected legacy provenance changed"):
        load(sidecar, fingerprint)
    legacy.state["origins"][key]["original"]["raw"] = "changed original"
    with pytest.raises(ValueError, match="origin hash differs"):
        packet(target, "target", legacy=legacy)


def test_inventory_is_transport_knowledge_and_not_adoption_evidence(pools):
    source, target = pools
    identifier = source.add_text("library", "original", "first source wording")
    source.update_chapter(identifier, content="source correction")
    incoming = packet(source)
    assert sync.inventory(target.DB_PATH, owner("target"))["origins"] == []
    result = sync.apply(target, incoming, owner("target"), operation_id="known")
    known = sync.inventory(target.DB_PATH, owner("target"))
    assert known["origins"] == [incoming["records"][0]["origin_hash"]]
    assert len(known["content"]) == 1
    assert (
        packet(source, known=known["origins"], known_content=known["content"])[
            "records"
        ]
        == []
    )
    target.update_chapter(
        result["entries"][0]["target_chapter_id"], content="local variant"
    )
    assert sync.inventory(target.DB_PATH, owner("target")) == known
    with pytest.raises(ValueError, match="preserve local variant"):
        sync.status(
            target, operation_id="known", packet=incoming, owner=owner("target")
        )
    with pytest.raises(ValueError, match="belongs to another being"):
        sync.inventory(target.DB_PATH, owner("other", "another-being"))


@pytest.mark.parametrize('raw,summary', [
    ('\r\n historical text \t\n', '\r\n original summary \n'),
    ('', 'Summary of a historical empty record\n'),
    ('An original without a summary', ''),
])
def test_exact_text_import_history_and_retry(pools, raw, summary):
    source, target = pools
    identifier = source.add_text('episodes', 'Exact historical text', raw,
                                 summary=summary, preserve_text=True, source_kind='config')
    first_packet = packet(source)
    first = sync.apply(target, first_packet, owner('target'), operation_id='exact-text-first')
    target_id = first['entries'][0]['target_chapter_id']
    received = target.expand(target_id)
    assert (received['raw'], received['spr']) == (raw, summary)
    assert received['embed_disabled'] == 1
    retry = sync.apply(target, first_packet, owner('target'), operation_id='exact-text-first')
    assert retry == {**first, 'reused': True}
    assert len(canonical_rows(target)) == 1

    changed_raw, changed_summary = raw + '\r\nsecond version\n', summary + '\nsecond summary\n'
    # Exercise add_text's existing replacement path and its delegated update.
    source.add_text('episodes', 'Exact historical text', changed_raw,
                    summary=changed_summary, preserve_text=True, source_kind='config')
    assert source.expand(identifier)['raw'] == changed_raw
    second_packet = packet(source)
    second = sync.apply(target, second_packet, owner('target'), operation_id='exact-text-second')
    updated = target.expand(second['entries'][0]['target_chapter_id'])
    assert updated['id'] == target_id
    assert (updated['raw'], updated['spr']) == (changed_raw, changed_summary)
    with target.connect() as con:
        prior = json.loads(con.execute('SELECT snapshot_json FROM chapter_revisions WHERE chapter_id=? ORDER BY id',
                                      (target_id,)).fetchone()[0])
    assert (prior['raw'], prior['spr']) == (raw, summary)
    retry = sync.apply(target, second_packet, owner('target'), operation_id='exact-text-second')
    assert retry == {**second, 'reused': True}


def test_default_text_normalization_is_unchanged(pools):
    source, _ = pools
    identifier = source.add_text('episodes', 'Ordinary text', '\r\n text \n', summary=' summary \n')
    assert (source.expand(identifier)['raw'], source.expand(identifier)['spr']) == ('text', 'summary')
    source.update_chapter(identifier, content=' updated\r\ntext \n', summary=' updated summary \n')
    assert (source.expand(identifier)['raw'], source.expand(identifier)['spr']) == ('updated\ntext', 'updated summary')
    with pytest.raises(ValueError, match='boolean'):
        source.add_text('episodes', 'Bad flag', 'text', preserve_text=1)


def test_exact_text_requires_supported_api_before_write(pools, monkeypatch):
    source, target = pools
    source.add_text('episodes', 'Preserved summary', 'text', summary='', preserve_text=True)
    incoming = packet(source)
    actual_add = target.add_text

    def older_add(*args, _con=None, **kwargs):
        return actual_add(*args, _con=_con, **kwargs)

    monkeypatch.setattr(target, 'add_text', older_add)
    with pytest.raises(ValueError, match='exact-text import support'):
        sync.apply(target, incoming, owner('target'), operation_id='old-api-refused')
    assert canonical_rows(target) == []
    with target.connect() as con:
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='dmk_sync_origins'").fetchone() is None
