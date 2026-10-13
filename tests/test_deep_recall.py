# ruff: noqa: F811 -- pytest fixture injection reuses the fixture name.
import json
import sqlite3

import pytest

from tests.test_codex_projection import setup, select  # noqa: F401 -- shared pytest fixture


def args(action="search", query="invitation", uid="", offset=0):
    return dict(action=action, query=query, record_uid=uid, offset=offset)


def test_scoped_read_reuses_apis_without_mutation_and_excludes_other_records(setup):
    mc, p = setup
    import deep_recall as d

    cid = mc.add_text(
        "episodes",
        "Failed invitation",
        "The invitation object existed; delivery failed.",
    )
    other = mc.add_text("episodes", "Private invitation", "Unselected private outcome.")
    mc.add_link(cid, other, "related")
    selection = select(mc, p, [cid])
    uid = selection["records"][0]["record_uid"]
    reader = d.Reader(mc.DB_PATH, selection)
    before = mc.DB_PATH.read_bytes()
    found = reader.call(args())
    assert len(found["items"]) == 1
    result = reader.call(args("read", "", uid))
    assert result["complete"] and result["raw"].endswith("delivery failed.")
    assert result["neighbors"] == []
    assert "Unselected" not in json.dumps(found) + json.dumps(result)
    assert (
        reader.call(args("read", "", mc._read_chapter(other)["record_uid"]))["status"]
        == "not_in_selection"
    )
    assert mc.DB_PATH.read_bytes() == before
    assert mc._read_chapter(cid)["access_count"] == 0
    import memoryctl as m

    with m.read_scope(mc.DB_PATH):
        assert m.search("invitation")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            m.touch_access(cid)


def test_transaction_is_consistent_and_context_restores_after_failure(setup):
    mc, p = setup
    import memoryctl as m

    cid = mc.add_text("episodes", "Trial", "Initial report.")
    with m.read_scope(mc.DB_PATH):
        assert m._read_chapter(cid)["revision"] == 1
        mc.update_chapter(cid, content="Corrected report.")
        assert m._read_chapter(cid)["revision"] == 1
    with m.read_scope(mc.DB_PATH):
        assert m._read_chapter(cid)["revision"] == 2
    assert m._READ_CONNECTION.get() is None


def test_correction_stale_binding_history_and_unavailable_are_distinct(setup, tmp_path):
    mc, p = setup
    import deep_recall as d

    cid = mc.add_text("episodes", "Trial", "All nodes recovered.")
    reader = d.Reader(mc.DB_PATH, select(mc, p, [cid]))
    uid = mc._read_chapter(cid)["record_uid"]
    mc.update_chapter(cid, content="Correction: the third node lost readings.")
    assert reader.call(args(query="Trial"))["status"] == "stale_binding"
    reader = d.Reader(mc.DB_PATH, select(mc, p, [cid]))
    assert "third node lost" in reader.call(args("read", "", uid))["raw"]
    past = reader.call(args("history", "", uid))
    assert past["historical"] and past["record"]["raw"] == "All nodes recovered."
    assert past["current_reference"]["revision"] == 2
    assert reader.call(args(query="zzyzx"))["status"] == "no_matches"
    mc.DB_PATH.rename(tmp_path / "withheld.db")
    assert reader.call(args(query="Trial"))["status"] == "unavailable"
    assert not mc.DB_PATH.exists()


def test_page_boundary_cannot_silently_omit_late_correction(setup):
    mc, p = setup
    import deep_recall as d

    raw = "Earlier observation. " * 800 + "\nCorrection: delivery failed; no receipt."
    cid = mc.add_text("episodes", "Long record", raw)
    reader = d.Reader(mc.DB_PATH, select(mc, p, [cid]), max_bytes=3000)
    uid = mc._read_chapter(cid)["record_uid"]
    offset, parts = 0, []
    while True:
        result = reader.call(args("read", "", uid, offset))
        assert result["status"] == "ok"
        assert len(json.dumps(result, ensure_ascii=False).encode()) <= 3000
        parts.append(result["raw"])
        if result["next_offset"] is None:
            break
        assert not result["complete"]
        assert result["next_offset"] > offset
        offset = result["next_offset"]
    assert "".join(parts) == raw


def test_opt_in_projection_navigation_is_verified_and_rollback_is_plain_selection(
    setup, tmp_path
):
    mc, p = setup
    import deep_recall as d

    cid = mc.add_text("library", "Navigation", "A retained project entry.")
    baseline = select(mc, p, [cid])
    enabled = {**baseline, "deep_recall": d.route_descriptor()}
    p.publish(mc.DB_PATH, enabled, tmp_path / "enabled", writers_stopped=True)
    p.verify(tmp_path / "enabled", database=mc.DB_PATH)
    assert "hmk_recall" in (tmp_path / "enabled/memory_summary.md").read_text()
    p.publish(mc.DB_PATH, baseline, tmp_path / "baseline", writers_stopped=True)
    assert "hmk_recall" not in (tmp_path / "baseline/memory_summary.md").read_text()
    with pytest.raises(ValueError, match="unsupported"):
        p.render(mc.DB_PATH, {**baseline, "deep_recall": {"tool": "arbitrary"}})


def test_epoch_storage_time_is_rendered_exactly_without_changing_event_time(setup):
    mc, p = setup
    import deep_recall as d
    cid=mc.add_text('episodes','Dated report','Event occurred on 2024-06-18.')
    with mc.connect() as con:
        con.execute('UPDATE chapters SET created_at=?,updated_at=? WHERE id=?',(1791863777,1791863778,cid))
    selection=select(mc,p,[cid]);uid=selection['records'][0]['record_uid']
    result=d.Reader(mc.DB_PATH,selection).call(args('read','',uid))
    assert result['local_storage_time_utc']=={'created_at':'2026-10-13T03:56:17Z','updated_at':'2026-10-13T03:56:18Z'}
    assert result['record']['created_at']==1791863777
    assert result['raw']=='Event occurred on 2024-06-18.'
