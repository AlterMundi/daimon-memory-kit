"""Scoped index maintenance preserves current text and resumes successful batches."""

# ruff: noqa: F811
import pytest
from tests.test_durable_memory_foundation import mc  # noqa: F401


def config(mc, monkeypatch):
    monkeypatch.setenv("HERMES_EMBED_PROVIDER", "local")
    monkeypatch.setenv("HERMES_EMBED_MODEL", "fixture")
    monkeypatch.setattr(mc, "default_embed_output_dimensionality", lambda *_: None)
    calls = []

    def embed(provider, texts, **kwargs):
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(mc, "embed_texts", embed)
    return calls


def test_scoped_refresh_preserves_other_spaces_and_skips_successful_work(
    mc, monkeypatch
):
    calls = config(mc, monkeypatch)
    selected = mc.add_text("episodes", "Mira", "Mira proposed replay; not adopted.")
    other = mc.add_text("episodes", "Other", "An unrelated encounter.")
    uid = mc.expand(selected)["record_uid"]
    selected_text = mc.embed_input_text(mc.expand(selected))
    other_text = mc.embed_input_text(mc.expand(other))
    with mc.connect() as con:
        mc.upsert_embedding(con, other, "local", "fixture", other_text, [0.0, 1.0])
        mc.upsert_embedding(
            con, selected, "local", "previous-model", selected_text, [1.0]
        )
        before = [
            tuple(r)
            for r in con.execute(
                "SELECT * FROM chapter_embeddings ORDER BY chapter_id,model"
            )
        ]
    assert mc.backfill_embeddings(record_uids=[uid])["processed"] == 1
    assert mc.backfill_embeddings(record_uids=[uid])["processed"] == 0
    assert len(calls) == 1
    with mc.connect() as con:
        after = [
            tuple(r)
            for r in con.execute(
                "SELECT * FROM chapter_embeddings WHERE chapter_id=? OR model=? ORDER BY chapter_id,model",
                (other, "previous-model"),
            )
        ]
    assert after == before
    assert mc.embedding_candidates(record_uids=[]) == []


def test_correction_during_http_does_not_publish_old_vector(mc, monkeypatch):
    config(mc, monkeypatch)
    cid = mc.add_text("episodes", "Mira", "Mira adopted the proposal.")
    uid = mc.expand(cid)["record_uid"]

    def concurrent(provider, texts, **kwargs):
        mc.update_chapter(cid, content="Mira proposed it but it was not adopted.")
        return [[1.0, 0.0]]

    monkeypatch.setattr(mc, "embed_texts", concurrent)
    result = mc.backfill_embeddings(record_uids=[uid])
    assert result["processed"] == 0 and result["changed_during_embedding"] == [uid]
    assert mc.embedding_candidates(record_uids=[uid])[0]["revision"] == 2
    monkeypatch.setattr(mc, "embed_texts", lambda *a, **k: [[1.0, 0.0]])
    assert mc.backfill_embeddings(record_uids=[uid])["processed"] == 1
    assert "not adopted" in mc.semantic_search("proposal")[0]["raw"]
    assert len(mc.history(cid)) == 1


def test_partial_provider_failure_resumes_only_remaining_records(mc, monkeypatch):
    calls = config(mc, monkeypatch)
    for name in ["Mira", "Jo"]:
        mc.add_text("episodes", name, name + " proposed a useful change.")

    def fail_second(provider, texts, **kwargs):
        calls.append(texts)
        if len(calls) == 2:
            raise mc.EmbeddingBackendError("fixture outage")
        return [[1.0, 0.0]]

    monkeypatch.setattr(mc, "embed_texts", fail_second)
    with pytest.raises(mc.EmbeddingBackendError):
        mc.backfill_embeddings(batch_size=1)
    assert len(mc.embedding_candidates()) == 1
    assert mc.backfill_embeddings(batch_size=1)["processed"] == 1
    assert len(calls) == 3 and calls[2] == calls[1] and calls[2] != calls[0]


def test_stale_legacy_vector_not_used_and_repaired_before_limit(mc, monkeypatch):
    config(mc, monkeypatch)
    first = mc.add_text("episodes", "First", "One episode.")
    second = mc.add_text("episodes", "Mira", "Mira did not adopt the proposal.")
    with mc.connect() as con:
        mc.upsert_embedding(
            con,
            first,
            "local",
            "fixture",
            mc.embed_input_text(mc.expand(first)),
            [1.0, 0.0],
        )
        mc.upsert_embedding(
            con, second, "local", "fixture", "obsolete content", [1.0, 0.0]
        )
    assert [r["id"] for r in mc.semantic_search("Mira")] == [first]
    assert [r["id"] for r in mc.embedding_candidates(limit=1)] == [second]
    assert mc.backfill_embeddings(limit=1)["processed"] == 1
    assert set(r["id"] for r in mc.semantic_search("Mira")) == {first, second}


@pytest.mark.parametrize(
    "vectors", [[], [[float("nan")]], [[1.0], [1.0]], [[1.0, False]]]
)
def test_invalid_provider_vectors_leave_input_pending(mc, monkeypatch, vectors):
    config(mc, monkeypatch)
    mc.add_text("episodes", "Mira", "Mira proposed replay.")
    monkeypatch.setattr(mc, "embed_texts", lambda *a, **kw: vectors)
    with pytest.raises(mc.EmbeddingBackendError):
        mc.backfill_embeddings()
    assert len(mc.embedding_candidates()) == 1


from tests.test_portable_producer import setup  # noqa: E402,F401
from portable_producer import process_once, maintain_index_once  # noqa: E402
from provider_status import Alerts  # noqa: E402


def test_capture_index_resumes_after_commit_without_selecting_or_reembedding(
    setup, monkeypatch
):
    memory, inbox, state, propose, binding, selection_calls, _ = setup
    embedding_calls = config(memory, monkeypatch)
    receipt = process_once(memory, inbox, state, propose, binding)
    assert receipt["receipt"]["records"]["jo"]["embedding_status"] == "pending"

    def crash(point):
        assert point == "after_embedding_commit"
        raise RuntimeError("fixture crash")

    with pytest.raises(RuntimeError):
        maintain_index_once(memory, inbox, state, _fault=crash)
    import json

    assert json.loads((state / "embedding-index.json").read_text())["after"] == 0
    assert maintain_index_once(memory, inbox, state)["state"] == "complete"
    assert maintain_index_once(memory, inbox, state)["state"] == "idle"
    assert len(selection_calls) == 1 and len(embedding_calls) == 1
    assert (state / "embedding-1-before.sqlite").is_file()
    monkeypatch.setenv("HERMES_EMBED_MODEL", "other-space")
    with pytest.raises(ValueError, match="space"):
        maintain_index_once(memory, inbox, state)


def test_embedding_credit_failure_visible_and_does_not_replay_selection(
    setup, monkeypatch
):
    import io
    import urllib.error

    memory, inbox, state, propose, binding, selection_calls, _ = setup
    config(memory, monkeypatch)
    process_once(memory, inbox, state, propose, binding)

    def no_credit(*args, **kwargs):
        try:
            raise urllib.error.HTTPError(
                "https://private.invalid", 402, "secret", {}, io.BytesIO(b"secret")
            )
        except Exception as cause:
            raise memory.EmbeddingBackendError("provider unavailable") from cause

    monkeypatch.setattr(memory, "embed_texts", no_credit)
    status = maintain_index_once(memory, inbox, state)
    assert (
        status["state"] == "pending"
        and status["provider_problem"]["code"] == "payment_required"
    )
    assert status["notification_pending"]
    monkeypatch.setenv("HERMES_EMBED_MODEL", "changed-space")
    with pytest.raises(ValueError, match="space"):
        maintain_index_once(memory, inbox, state)
    monkeypatch.setenv("HERMES_EMBED_MODEL", "fixture")
    assert Alerts(inbox).status()["alerts"][0]["phase"] == "embedding"
    assert process_once(memory, inbox, state, propose, binding)["state"] == "idle"
    config(memory, monkeypatch)
    assert maintain_index_once(memory, inbox, state)["state"] == "complete"
    assert Alerts(inbox).status()["healthy"] and len(selection_calls) == 1
