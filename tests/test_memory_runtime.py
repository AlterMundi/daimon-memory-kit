"""Production invocation: selected bindings, paid-call reuse and safe failures."""

# ruff: noqa: F811
import json
from pathlib import Path

import pytest

from tests.test_portable_producer import setup  # noqa: F401
from capture_inbox import Inbox
from codex_coordinator import checkpoint
from memory_models import Models, authorize_retry
import memory_models
import memory_runtime
from provider_status import ProviderProblem


def configuration(tmp_path, memory, inbox, state, context):
    catalog = tmp_path / "catalog.json"
    checkpoint(catalog, {"models": []})  # No native dispatch in these tests.
    binding = tmp_path / "binding.json"
    checkpoint(binding, json.loads(inbox.binding))
    return dict(
        schema="hmk.worker-profile/v1",
        database=str(memory.DB_PATH),
        memory_base=str(memory.BASE_DIR),
        inbox=str(inbox.path),
        binding=str(binding),
        context=context,
        state_dir=str(state),
        source_scope="fictional",
        generation=dict(
            provider="deepseek",
            model="deepseek-flash",
            effort="low",
            output_token_limit=6000,
            credential_env="HMK_TEST_DEEPSEEK_KEY",
        ),
        review=dict(
            provider="openai-codex-native",
            model="gpt-6.1-sol",
            effort="low",
            catalog=str(catalog),
        ),
        budgets=dict(
            max_steps=6,
            capture_limit=32,
            index_limit=32,
            source_budget_bytes=64000,
            navigation_steps=4,
        ),
    )


def test_real_capture_binding_accepts_minimal_model_context_and_restarts(
    setup, tmp_path, monkeypatch
):
    memory, _, state, propose, context, calls, raw = setup
    binding = dict(
        context,
        schema="hmk.codex-hook-binding/v1",
        source_root=str(tmp_path / "sources"),
        allowed_cwds=[str(tmp_path)],
        inbox=str(tmp_path / "full.sqlite"),
        max_source_bytes=2000000,
    )
    inbox = Inbox(binding["inbox"], binding)
    inbox.observe("fixture", {"hook_event_name": "Stop"}, raw)
    value = configuration(tmp_path, memory, inbox, state, context)
    monkeypatch.setattr(memory_runtime, "load_memory", lambda _: memory)
    monkeypatch.setattr(
        memory,
        "embeddings_runtime_config",
        lambda **kw: dict(
            provider="local", model="fixture", output_dimensionality=None
        ),
    )
    embedded = []
    monkeypatch.setattr(
        memory,
        "embed_texts",
        lambda provider, texts, **kw: (
            embedded.extend(texts) or [[1.0, 0.0] for _ in texts]
        ),
    )
    monkeypatch.setenv("HMK_TEST_DEEPSEEK_KEY", "TEST_SECRET")

    def dispatch(path, root, credential, provider):
        assert credential == "TEST_SECRET" and provider == "deepseek"
        request = json.loads(path.read_text())
        result = propose(request, root)
        receipt = dict(
            state="completed",
            request_sha256=path.stem,
            content=json.dumps(result["selection"]),
            finish_reason="stop",
            tool_calls_observed=[],
        )
        (root / "dispatches").mkdir(exist_ok=True)
        checkpoint(root / "dispatches" / path.name, receipt)

    monkeypatch.setattr(memory_models.text_api, "dispatch", dispatch)
    first = memory_runtime.run(value)
    assert first["status"]["state"] == "idle" and len(calls) == len(embedded) == 1
    # Restart does not need credentials, repeat selection or charge for indexing.
    monkeypatch.delenv("HMK_TEST_DEEPSEEK_KEY")
    assert memory_runtime.run(value)["status"]["state"] == "idle"
    assert len(calls) == len(embedded) == 1
    assert "TEST_SECRET" not in "".join(p.read_text() for p in state.rglob("*.json"))
    assert "source_root" not in json.dumps(calls)


def test_missing_credential_is_actionable_and_does_not_advance_capture(
    setup, tmp_path, monkeypatch
):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    monkeypatch.delenv("HMK_TEST_DEEPSEEK_KEY", raising=False)
    result = memory_runtime.run(value)
    assert result["status"]["state"] == "pending"
    assert (
        result["status"]["phases"]["capture"]["reason_code"] == "authentication_failed"
    )
    assert not (state / "index.json").exists()
    assert list(state.rglob("requests/*.json"))
    assert not list(state.rglob("dispatches/*.json"))


def test_status_reads_without_database_catalog_or_credentials(setup, tmp_path, capsys):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    value["database"] = str(tmp_path / "absent.sqlite")
    value["review"]["catalog"] = str(tmp_path / "absent-catalog.json")
    path = tmp_path / "profile.json"
    checkpoint(path, value)
    assert memory_runtime.main(["status", "--profile", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "unobserved"
    assert not state.exists() and not Path(value["database"]).exists()


def test_launch_failure_keeps_old_observation_and_has_nonzero_exit(
    setup, tmp_path, capsys
):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    value["database"] = str(tmp_path / "SECRET-absent.sqlite")
    state.mkdir()
    checkpoint(
        state / "worker-status.json",
        dict(schema="hmk.worker-status/v1", state="pending", phase=None),
    )
    before = (state / "worker-status.json").read_bytes()
    path = tmp_path / "profile.json"
    checkpoint(path, value)
    assert memory_runtime.main(["run", "--profile", str(path)]) == 1
    result = capsys.readouterr().out
    assert "SECRET" not in result and json.loads(result)["state"] == "failed"
    assert (state / "worker-status.json").read_bytes() == before


def test_selected_scope_paid_receipt_reuse_policy_change_and_no_fallback(
    setup, tmp_path, monkeypatch
):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    model = Models(
        value["generation"], value["review"], "human-authorized-selected-context"
    )
    request = dict(
        messages=[
            dict(role="system", content="Selected evidence."),
            dict(role="user", content="Facts."),
        ],
        response_schema={"type": "object"},
    )
    monkeypatch.setenv("HMK_TEST_DEEPSEEK_KEY", "TEST_SECRET")
    calls = []

    def dispatch(path, root, credential, provider):
        supplied = json.loads(path.read_text())
        assert supplied["source_scope"] == "human-authorized-selected-context"
        assert (
            memory_models.text_api.parameters(supplied, provider)["model"]
            == "deepseek-flash"
        )
        calls.append(supplied)
        (root / "dispatches").mkdir(exist_ok=True)
        checkpoint(
            root / "dispatches" / path.name,
            dict(
                request_sha256=path.stem,
                state="completed",
                content="{}",
                finish_reason="stop",
                tool_calls_observed=[],
            ),
        )

    monkeypatch.setattr(memory_models.text_api, "dispatch", dispatch)
    first = model(request, state)
    monkeypatch.delenv("HMK_TEST_DEEPSEEK_KEY")
    assert model(request, state) == first and len(calls) == 1
    changed = Models(
        dict(value["generation"], output_token_limit=7000), value["review"], model.scope
    )
    with pytest.raises(ValueError, match="policy changed"):
        changed(request, state)
    # A failed request is never implicitly sent again, even after credentials recover.
    receipt = next((state / "dispatches").glob("*.json"))
    data = json.loads(receipt.read_text())
    data.update(state="failed", problem={"code": "payment_required"})
    checkpoint(receipt, data)
    with pytest.raises(ProviderProblem, match="payment_required"):
        model(request, state)
    assert len(calls) == 1


def test_native_review_route_uses_selected_evidence_and_reuses_receipt(
    setup, tmp_path, monkeypatch
):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    model = Models(
        value["generation"], value["review"], "human-authorized-selected-context"
    )
    request = dict(
        phase="consolidation_review",
        messages=[
            dict(role="system", content="Review."),
            dict(role="user", content="Evidence."),
        ],
        response_schema={"type": "object"},
    )
    calls = []

    def dispatch(path, root, catalog, credential_file=None):
        supplied = json.loads(path.read_text())
        calls.append(supplied)
        assert (
            supplied["model"] == "gpt-6.1-sol"
            and supplied["format"] == "hmk-selected-receiving-request/v1"
        )
        assert supplied["source_scope"] == "human-authorized-selected-context"
        assert (
            supplied["native_memory_allowed"] is False
            and supplied["tools_allowed"] is False
        )
        (root / "dispatches").mkdir(exist_ok=True)
        checkpoint(
            root / "dispatches" / path.name,
            dict(
                request_sha256=path.stem,
                state="completed",
                content="{}",
                tool_calls_observed=[],
            ),
        )

    monkeypatch.setattr(memory_models.native, "dispatch", dispatch)
    monkeypatch.setattr(
        memory_models.text_api,
        "dispatch",
        lambda *a, **k: pytest.fail("wrong provider"),
    )
    assert model(request, state) == model(request, state) and len(calls) == 1


def test_profile_rejects_silent_model_substitution_and_unsupported_budgets(
    setup, tmp_path
):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    path = tmp_path / "profile.json"
    checkpoint(path, value)
    assert memory_runtime.profile(path) == value
    value["review"]["provider"] = "nous"
    checkpoint(path, value)
    with pytest.raises(ValueError, match="native OpenAI"):
        memory_runtime.profile(path)
    value["review"]["provider"] = "openai-codex-native"
    value["budgets"]["navigation_steps"] = 33
    checkpoint(path, value)
    with pytest.raises(ValueError, match="budgets"):
        memory_runtime.profile(path)


def test_explicit_credit_recovery_preserves_failure_and_retries_only_once(
    setup, tmp_path, monkeypatch
):
    memory, inbox, state, _, context, _, _ = setup
    value = configuration(tmp_path, memory, inbox, state, context)
    monkeypatch.setenv("HMK_TEST_DEEPSEEK_KEY", "TEST_SECRET")
    attempts = []

    def dispatch(path, root, credential, provider):
        attempts.append(path)
        (root / "dispatches").mkdir(exist_ok=True)
        receipt = dict(
            request_sha256=path.stem,
            state="failed",
            problem={"code": "payment_required"},
        )
        if len(attempts) > 1:
            receipt = dict(
                request_sha256=path.stem,
                state="completed",
                content="{}",
                finish_reason="stop",
                tool_calls_observed=[],
            )
        checkpoint(root / "dispatches" / path.name, receipt)

    monkeypatch.setattr(memory_models.text_api, "dispatch", dispatch)
    # Real worker establishes owner, leaves selected source pending and exposes credit failure.
    result = memory_runtime.run(value)
    assert result["status"]["phases"]["capture"]["reason_code"] == "payment_required"
    request_path = attempts[0]
    failed = request_path.parent.parent / "dispatches" / request_path.name
    original = failed.read_bytes()
    receipt = memory_runtime.retry(
        value, request_path, "Credit restored; failed call inspected."
    )
    assert receipt["network_invoked"] is False and len(attempts) == 1
    with pytest.raises(ValueError, match="already authorized"):
        memory_runtime.retry(value, request_path, "Accidental repeated command")
    model = Models(value["generation"], value["review"], "fictional")
    request = json.loads(request_path.read_text())
    first = model(request, request_path.parent.parent)
    assert model(request, request_path.parent.parent) == first
    assert len(attempts) == 2 and failed.read_bytes() == original
    with pytest.raises(ValueError, match="completed output"):
        authorize_retry(attempts[1], "Do not repeat successful paid work")
    # Altering the failure after authorization cannot silently select another attempt.
    checkpoint(failed, dict(request_sha256=request_path.stem, state="started"))
    with pytest.raises(ValueError, match="retry decision"):
        model(request, request_path.parent.parent)
