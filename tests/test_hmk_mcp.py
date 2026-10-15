# ruff: noqa: F811 -- pytest fixture injection
import json
import sqlite3
import asyncio
import sys
from pathlib import Path

import pytest

from tests.test_codex_projection import setup  # noqa: F401 -- pytest fixture


def test_real_stdio_protocol_and_readonly_annotation(setup, tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    mc, _ = setup
    cid = mc.add_text("library", "Protocol witness", "The invitation failed.")
    uid = mc._read_chapter(cid)["record_uid"]
    selected = tmp_path / "binding.json"
    selected.write_text(json.dumps(binding(mc)))
    selected.chmod(0o600)
    before = mc.DB_PATH.read_bytes()

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                str(Path(__file__).resolve().parents[1] / "scripts/dmk_mcp.py"),
                "--binding",
                str(selected),
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert "current human task" in initialized.instructions
                listing = await session.list_tools()
                assert [t.name for t in listing.tools] == ["dmk_recall", "hmk_recall"]
                assert listing.tools[0].annotations.readOnlyHint is True
                response = await session.call_tool(
                    "hmk_recall", dict(action="read", pool="main", record_uid=uid)
                )
                assert not response.isError
                payload = response.structuredContent or json.loads(
                    response.content[0].text
                )
                result = payload["pools"][0]["result"]
                assert result["raw"] == "The invitation failed."
                assert result["complete"] is True
                renamed = await session.call_tool(
                    "dmk_recall", dict(action="read", pool="main", record_uid=uid)
                )
                renamed_payload = renamed.structuredContent or json.loads(renamed.content[0].text)
                for value in (renamed_payload, payload):
                    for entry in value["pools"]:
                        entry["result"].pop("seconds", None)
                assert renamed_payload == payload
                checkpoint=await session.call_tool('hmk_recall',dict(action='checkpoint',pool='main',record_uid=uid))
                metadata=checkpoint.structuredContent or json.loads(checkpoint.content[0].text)
                assert metadata['pools'][0]['result']['content_loaded'] is False
                assert metadata['pools'][0]['result']['current_reference']['revision']==1

    asyncio.run(exercise())
    assert mc.DB_PATH.read_bytes() == before


def binding(mc):
    return dict(
        schema="hmk.deep-recall.binding/v1",
        being_ref="fixture:being:Ilex",
        body_ref="fixture:body:voice",
        pools=[dict(name="main", database=str(mc.DB_PATH))],
    )


def test_checkpoint_reads_only_revision_not_contents_and_sees_corrections(setup, monkeypatch):
    mc, _ = setup
    from deep_recall import Reader
    cid=mc.add_text('library','Private title','Private original content',metadata={'source_instance':'fixture:private-source'})
    uid=mc._read_chapter(cid)['record_uid']
    reader=Reader.live_pool(mc.DB_PATH,being_ref='fixture:being',body_ref='fixture:body',backend=mc)
    before=mc.DB_PATH.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(mc,'_read_chapter',lambda *_:pytest.fail('Checkpoint loaded original text'))
        result=reader.call(dict(action='checkpoint',query='',record_uid=uid,offset=0))
    assert result['status']=='ok' and result['current_reference']=={'record_uid':uid,'revision':1}
    assert result['metadata_only'] is True and result['content_loaded'] is False
    assert not any(key in result for key in ('record','raw','title','neighbors','applicability'))
    assert mc.DB_PATH.read_bytes()==before
    mc.update_chapter(cid,content='Corrected private content')
    changed=reader.call(dict(action='checkpoint',query='',record_uid=uid,offset=0))
    assert changed['current_reference']['revision']==2
    assert reader.call(dict(action='checkpoint',query='',record_uid='missing',offset=0))['status']=='not_in_selection'
    assert reader.call(dict(action='checkpoint',query='unused',record_uid=uid,offset=0))['status']=='invalid_request'


def test_checkpoint_pool_revision_guard_and_foreground_cli(setup, tmp_path):
    import subprocess
    mc, _ = setup
    from hmk_mcp import recall
    cid=mc.add_text('library','Fixture memory','Exact private fixture original')
    uid=mc._read_chapter(cid)['record_uid'];selected=binding(mc)
    result=recall(selected,action='checkpoint',pool='main',record_uid=uid)['pools'][0]['result']
    assert result['current_reference']['revision']==1 and 'raw' not in result
    assert recall(selected,action='checkpoint',pool='unselected',record_uid=uid)['status']=='invalid_request'
    assert recall(selected,action='checkpoint',pool='main',record_uid=uid,expected_revision=2)['pools'][0]['result']['status']=='revision_changed'
    file=tmp_path/'selected.json';file.write_text(json.dumps(selected));file.chmod(0o600)
    before=mc.DB_PATH.read_bytes()
    command=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/hmk_mcp.py'),'--binding',str(file),'--request-stdin']
    response=subprocess.run(command,input=json.dumps({'action':'checkpoint','pool':'main','record_uid':uid}),text=True,capture_output=True,check=True)
    assert json.loads(response.stdout)['pools'][0]['result']['current_reference']['revision']==1
    assert 'Exact private fixture original' not in response.stdout and mc.DB_PATH.read_bytes()==before
    denied=subprocess.run(command,input=json.dumps({'action':'checkpoint','pool':'main','record_uid':uid,'database':'another'}),text=True,capture_output=True)
    assert denied.returncode!=0


def test_live_reader_sees_later_writes_corrections_and_history_without_touching(setup):
    mc, _ = setup
    from hmk_mcp import recall

    b = binding(mc)
    assert (
        recall(b, action="search", query="invitation")["pools"][0]["result"]["status"]
        == "no_matches"
    )
    cid = mc.add_text(
        "episodes", "Invitation", "Invitation object created; delivery pending."
    )
    uid = mc._read_chapter(cid)["record_uid"]
    assert (
        recall(b, action="search", query="invitation")["pools"][0]["result"]["items"][
            0
        ]["record_uid"]
        == uid
    )
    mc.update_chapter(cid, content="Invitation delivery failed; no acceptance.")
    before = mc.DB_PATH.read_bytes()
    response = recall(b, action="read", pool="main", record_uid=uid)["pools"][0][
        "result"
    ]
    assert response["record"]["revision"] == 2 and "failed" in response["raw"]
    assert response["applicability"]["kind"] == "unknown"
    assert (
        recall(b, action="read", pool="main", record_uid=uid, expected_revision=1)[
            "pools"
        ][0]["result"]["status"]
        == "revision_changed"
    )
    old = recall(b, action="history", pool="main", record_uid=uid)["pools"][0]["result"]
    assert old["record"]["revision"] == 1 and "pending" in old["record"]["raw"]
    assert mc.DB_PATH.read_bytes() == before
    assert mc._read_chapter(cid)["access_count"] == 0


def test_pool_boundaries_unavailability_and_revision_safe_pages(setup, tmp_path):
    mc, _ = setup
    from hmk_mcp import recall

    cid = mc.add_text("library", "Memory", "Memory text.")
    uid = mc._read_chapter(cid)["record_uid"]
    b = binding(mc)
    b["pools"].append(dict(name="other", database=str(tmp_path / "missing.db")))
    result = recall(b, action="search", query="memory")
    assert [x["result"]["status"] for x in result["pools"]] == ["ok", "unavailable"]
    assert not (tmp_path / "missing.db").exists()
    assert recall(b, action="read", record_uid=uid)["status"] == "invalid_request"
    assert (
        recall(b, action="read", pool="/arbitrary/path", record_uid=uid)["status"]
        == "invalid_request"
    )
    assert (
        recall(b, action="read", pool="main", record_uid=uid, offset=1)["status"]
        == "invalid_request"
    )


def test_matrix_origin_read_is_not_native_admission_or_history(setup):
    mc, _ = setup
    from hmk_mcp import recall

    cid = mc.add_text("library", "Projected source", "Existing projected observation.")
    uid = mc._read_chapter(cid)["record_uid"]
    con = sqlite3.connect(mc.DB_PATH)
    con.execute("UPDATE books SET source_kind='daimon-projection'")
    con.commit()
    con.close()
    before = mc.DB_PATH.read_bytes()
    result = recall(binding(mc), action="read", pool="main", record_uid=uid)["pools"][
        0
    ]["result"]
    assert result["record"]["origin"]["kind"] == "daimon-projection"
    assert "no ledger freshness" in result["authority_note"]
    checkpoint=recall(binding(mc),action='checkpoint',pool='main',record_uid=uid)['pools'][0]['result']
    assert checkpoint['projection_ledger_freshness']=='unverified' and checkpoint['content_loaded'] is False
    assert (
        recall(binding(mc), action="history", pool="main", record_uid=uid)["pools"][0][
            "result"
        ]["status"]
        == "external_history"
    )
    assert before == mc.DB_PATH.read_bytes()


def test_binding_requires_owner_selected_unique_pools(setup, tmp_path):
    mc, _ = setup
    from hmk_mcp import load_binding

    p = tmp_path / "binding.json"
    p.write_text(json.dumps(binding(mc)))
    p.chmod(0o600)
    assert load_binding(p)["body_ref"] == "fixture:body:voice"
    p.chmod(0o666)
    with pytest.raises(ValueError, match="owned"):
        load_binding(p)
    p.chmod(0o600)
    b = binding(mc)
    b["pools"] *= 2
    p.write_text(json.dumps(b))
    with pytest.raises(ValueError, match="unique"):
        load_binding(p)
