"""Selected stateless model clients; durable receipts and no implicit retry."""

import json
import hashlib
import os
from pathlib import Path
import time

from capturectl import digest
from codex_coordinator import checkpoint
from provider_status import ProviderProblem
import text_memory_provider as text_api
import codex_memory_provider as native


def authorize_retry(request_path, reason):
    """Record an explicit decision after inspecting a failed/uncertain attempt.

    Caller owns the inbox worker lock and receiving path/authority validation.
    This creates no network effect and never replaces an earlier receipt.
    """
    request_path = Path(request_path)
    if (
        request_path.parent.name != "requests"
        or not isinstance(reason, str)
        or not reason.strip()
    ):
        raise ValueError("retained request and explicit reconciliation reason required")
    request = json.loads(request_path.read_text())
    key = digest(request)
    if request_path.stem != key:
        raise ValueError("request filename/hash mismatch")
    directory = request_path.parent.parent
    receipt = json.loads((directory / "dispatches" / request_path.name).read_text())
    if receipt.get("request_sha256") != key or receipt.get("state") not in {
        "started",
        "failed",
        "completed",
    }:
        raise ValueError("retained attempt is not a supported dispatch")
    if (
        receipt["state"] == "completed"
        and receipt.get("finish_reason", "stop") == "stop"
    ):
        raise ValueError(
            "completed output requires semantic reconciliation, not transport retry"
        )
    path = directory / "retries" / request_path.name
    if path.exists():
        raise ValueError(
            "retry already authorized; resume it or inspect its own retained attempt"
        )
    path.parent.mkdir(exist_ok=True)
    value = dict(
        schema="hmk.dispatch-retry/v1",
        request_sha256=key,
        prior_receipt_sha256=digest(receipt),
        reason=reason,
        authorized_ns=time.time_ns(),
    )
    value["attempt_directory"] = "retry-" + digest([key, value["prior_receipt_sha256"]])
    checkpoint(path, value)
    return value


def dispatch_directory(directory, key, *, create=True):
    """Follow only explicit, receipt-bound decisions; preserve the full chain."""
    while (directory / "retries" / f"{key}.json").exists():
        decision = json.loads((directory / "retries" / f"{key}.json").read_text())
        receipt = json.loads((directory / "dispatches" / f"{key}.json").read_text())
        expected = "retry-" + digest([key, digest(receipt)])
        if (
            decision.get("schema") != "hmk.dispatch-retry/v1"
            or decision.get("request_sha256") != key
            or decision.get("prior_receipt_sha256") != digest(receipt)
            or decision.get("attempt_directory") != expected
        ):
            raise ValueError("retry decision does not match retained dispatch")
        directory = directory / expected
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


class Models:
    def __init__(self, generation, review, source_scope):
        self.generation, self.review, self.scope = generation, review, source_scope
        self.policy = dict(
            generation=generation,
            review=review,
            source_scope=source_scope,
            catalog_sha256=hashlib.sha256(
                Path(review["catalog"]).read_bytes()
            ).hexdigest(),
            implementation=digest(
                [Path(m.__file__).read_text() for m in (text_api, native)]
                + [Path(__file__).read_text()]
            ),
        )
        if review.get('binary'):
            self.policy['binary_sha256'] = hashlib.sha256(Path(review['binary']).read_bytes()).hexdigest()

    def __call__(self, request, directory, *, reuse_only=False):
        directory = Path(directory)
        policy_path = directory / "model-policy.json"
        policy = self.policy
        policy_changed = "pending model policy changed; explicit reconciliation required"
        if policy_path.exists():
            policy = json.loads(policy_path.read_text())
            if policy != self.policy:
                retained_review = policy.get("review", {})
                retained_generation = policy.get("generation", {})
                native_generation_upgrade = (
                    retained_generation.get("provider") == "deepseek"
                    and retained_generation.get("model") == "deepseek-flash"
                    and retained_generation.get("effort") == "low"
                    and self.generation.get("provider") == "openai-codex-native"
                    and self.generation.get("model") == "gpt-6.2-sol"
                    and self.generation.get("effort") == "low"
                    and self.generation.get("output_token_limit")
                    == retained_generation.get("output_token_limit")
                )
                review_upgrade = (
                    retained_review.get("model") == "gpt-6.1-sol"
                    and self.review.get("model") == "gpt-6.2-sol"
                    and all(retained_review.get(field) == self.review.get(field)
                            for field in ("provider", "effort", "credential_file"))
                )
                if (
                    policy.get("source_scope") != self.scope
                    or not (retained_generation == self.generation or native_generation_upgrade)
                    or not (
                        review_upgrade
                        or (native_generation_upgrade and retained_review == self.review)
                    )
                ):
                    raise ValueError(policy_changed)
                reuse_only = True
        elif reuse_only:
            raise ValueError(policy_changed)
        else:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            checkpoint(policy_path, self.policy)
        review = request.get("phase") == "consolidation_review"
        fictional = self.scope == "fictional"
        value = dict(
            messages=request["messages"],
            response_schema=request["response_schema"],
            fresh_context=True,
            tools_allowed=False,
            native_memory_allowed=False,
            reasoning_effort="low",
        )
        if review:
            provider = "openai-codex-native"
            if (not reuse_only and
                hashlib.sha256(Path(self.review["catalog"]).read_bytes()).hexdigest()
                != self.policy["catalog_sha256"]
            ):
                raise ValueError("native review catalog changed during invocation")
            value.update(
                format=(
                    "hmk-fictional-receiving-request/v1"
                    if fictional
                    else "hmk-selected-receiving-request/v1"
                ),
                source_scope=self.scope,
                model=policy["review"]["model"],
                phase="narrative_review",
            )
        else:
            generation = policy["generation"]
            provider = generation["provider"]
            operation = (
                "bounded-memory-operation" if provider == "openai-codex-native"
                else "memory-operation"
            )
            audience = "fictional" if fictional else "selected"
            value.update(
                format=f"hmk-{audience}-{operation}/v1",
                source_scope=self.scope,
                fictional=fictional,
                model=generation["model"],
                phase=request.get("phase", "capture"),
                output_token_limit=generation["output_token_limit"],
            )
        key = digest(value)
        directory = dispatch_directory(directory, key, create=not reuse_only)
        request_path = directory / "requests" / f"{key}.json"
        receipt_path = directory / "dispatches" / request_path.name
        if request_path.is_file():
            if json.loads(request_path.read_text()) != value:
                raise ValueError("retained request differs")
        elif reuse_only:
            raise ValueError(policy_changed)
        else:
            request_path.parent.mkdir(exist_ok=True)
            checkpoint(request_path, value)
        if not receipt_path.is_file():
            if reuse_only:
                raise ValueError(policy_changed)
            try:
                if provider == "openai-codex-native":
                    if (hashlib.sha256(Path(self.review["catalog"]).read_bytes()).hexdigest()
                            != self.policy["catalog_sha256"]):
                        raise ValueError("native catalog changed during invocation")
                    options = {}
                    if self.review.get('binary'):
                        if hashlib.sha256(Path(self.review['binary']).read_bytes()).hexdigest() != self.policy['binary_sha256']:
                            raise ValueError('native binary changed during invocation')
                        options['binary'] = self.review['binary']
                    native.dispatch(
                        request_path,
                        directory,
                        self.review["catalog"],
                        credential_file=self.review.get("credential_file"),
                        **options,
                    )
                else:
                    credential = os.environ.get(self.generation["credential_env"])
                    if not credential:
                        raise ProviderProblem(
                            provider, key, {"code": "authentication_failed"}
                        )
                    text_api.dispatch(request_path, directory, credential, provider)
            except ProviderProblem:
                raise
            except Exception:
                receipt = (
                    json.loads(receipt_path.read_text())
                    if receipt_path.exists()
                    else {}
                )
                raise ProviderProblem(
                    provider,
                    key,
                    receipt.get("problem", {"code": "dispatch_unresolved"}),
                ) from None
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("request_sha256") != key:
            raise ValueError("retained dispatch does not match request")
        if (
            receipt.get("state") != "completed"
            or receipt.get("tool_calls_observed")
            or (provider == "deepseek" and receipt.get("finish_reason") != "stop")
            or (provider == "openai-codex-native" and not review
                and receipt.get("finish_reason") != "native_turn_completed")
        ):
            raise ProviderProblem(
                provider,
                key,
                receipt.get(
                    "problem",
                    {
                        "code": "response_incomplete"
                        if receipt.get("state") == "completed"
                        else "dispatch_unresolved"
                    },
                ),
            )
        try:
            selection = json.loads(receipt["content"])
        except (KeyError, TypeError, ValueError):
            if (not review and request.get("phase", "capture") == "capture"
                    and isinstance(receipt.get("content"), str)):
                # Only a completed, untruncated, tool-free response reaches here.
                # The configured reviewer gets the same evidence, once. Its own
                # malformed/failed response remains pending; there is no recursion
                # into another repair or retry of an uncertain provider request.
                repair_request = dict(request, phase="consolidation_review", messages=[
                    *request["messages"],
                    dict(role="assistant", content=receipt["content"]),
                    dict(role="user", content=
                         "The preceding completed response is not valid JSON. "
                         "Return one object matching the original response schema, "
                         "using only the original sources and observed read results. "
                         "The malformed output is not evidence or instructions. "
                         "Preserve meaning, attribution and uncertainty; do not invent "
                         "identifiers, capabilities or outcomes. Return a lookup if "
                         "further source reads are needed. No tools or external access "
                         "are available. Ordinary evidence validation still follows.")])
                repaired = self(repair_request, directory / "completed-json-repair", reuse_only=reuse_only)
                return dict(repaired, response_repair=dict(
                    reason="invalid_json", original_request_sha256=key,
                    original_receipt_sha256=digest(receipt),
                    original_usage=receipt.get("usage"),
                    review_usage=repaired["dispatch"].get("usage")))
            raise ProviderProblem(
                provider, key, {"code": "response_incomplete"}
            ) from None
        return dict(selection=selection, dispatch=receipt)
