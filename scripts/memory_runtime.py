"""Explicit finite processing of an existing, selected HMK capture inbox.

No source scan, hook, scheduler, notification transport or native memory writer.
The receiving launcher supplies credentials in its process environment.
"""

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re

from capture_inbox import Inbox
import account_reconciliation
import memory_worker
from memory_models import Models, authorize_retry


def profile(path):
    value = json.loads(Path(path).read_text())
    required = {
        "schema",
        "database",
        "memory_base",
        "inbox",
        "binding",
        "context",
        "state_dir",
        "source_scope",
        "generation",
        "review",
        "budgets",
    }
    if set(value) - (required | {"embedding_env_file"}) or not required <= set(value):
        raise ValueError("worker profile has missing or unsupported fields")
    if value["schema"] != "hmk.worker-profile/v1" or value["source_scope"] not in {
        "fictional",
        "human-authorized-selected-context",
    }:
        raise ValueError("explicit supported source scope required")
    for field in (
        "database",
        "memory_base",
        "inbox",
        "binding",
        "state_dir",
        "embedding_env_file",
    ):
        if field in value and (
            not isinstance(value[field], str) or not Path(value[field]).is_absolute()
        ):
            raise ValueError("worker paths must be absolute")
    context = value["context"]
    if not isinstance(context, dict) or any(
        not isinstance(context.get(k), str) or not context[k]
        for k in ("subject", "source_instance")
    ):
        raise ValueError("explicit subject and source_instance required")
    generation, review = value["generation"], value["review"]
    if (
        set(generation)
        != {"provider", "model", "effort", "output_token_limit", "credential_env"}
        or generation["provider"] != "deepseek"
        or generation["model"] != "deepseek-flash"
        or generation["effort"] != "low"
        or type(generation["output_token_limit"]) is not int
        or not 1 <= generation["output_token_limit"] <= 32768
        or not isinstance(generation["credential_env"], str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", generation["credential_env"])
    ):
        raise ValueError("explicit DeepSeek Flash low generation profile required")
    if (
        set(review) - {"provider", "model", "effort", "catalog", "credential_file"}
        or not {"provider", "model", "effort", "catalog"} <= set(review)
        or review["provider"] != "openai-codex-native"
        or review["model"] != "gpt-6.1-sol"
        or review["effort"] != "low"
    ):
        raise ValueError("explicit native OpenAI Codex Sol low review profile required")
    for field in ("catalog", "credential_file"):
        if field in review and (
            not isinstance(review[field], str) or not Path(review[field]).is_absolute()
        ):
            raise ValueError("review paths must be absolute")
    budgets = value["budgets"]
    limits = {
        "max_steps": None,
        "capture_limit": 128,
        "index_limit": None,
        "source_budget_bytes": None,
        "navigation_steps": 32,
    }
    if set(budgets) != set(limits) or any(
        type(budgets[k]) is not int
        or budgets[k] < 1
        or (ceiling is not None and budgets[k] > ceiling)
        for k, ceiling in limits.items()
    ):
        raise ValueError("explicit positive supported invocation budgets required")
    return value


def load_memory(value):
    # Refuse a typo selecting an empty replacement pool. Schema adoption belongs
    # to the existing installer/migration procedure, not every worker invocation.
    database, base = Path(value["database"]), Path(value["memory_base"])
    if not database.is_file() or not base.is_dir():
        raise ValueError("existing canonical database and memory base required")
    os.environ["HMK_AGENT_MEMORY_BASE"] = str(base)
    os.environ["HMK_DB_PATH"] = str(database)
    if "embedding_env_file" in value:
        os.environ["HMK_ENV_FILE"] = value["embedding_env_file"]
    spec = importlib.util.spec_from_file_location(
        "worker_memory", Path(__file__).with_name("memoryctl.py")
    )
    memory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory)
    return memory


def run(value):
    if not Path(value["inbox"]).is_file():
        raise ValueError("existing capture inbox required")
    binding = json.loads(Path(value["binding"]).read_text())
    if any(
        binding.get(k) != value["context"][k] for k in ("subject", "source_instance")
    ):
        raise ValueError("capture binding differs from worker context")
    if (
        "inbox" in binding
        and Path(binding["inbox"]).resolve() != Path(value["inbox"]).resolve()
    ):
        raise ValueError("capture binding selects another inbox")
    memory = load_memory(value)
    inbox = Inbox(value["inbox"], binding)
    models = Models(value["generation"], value["review"], value["source_scope"])

    def organize():
        return account_reconciliation.process_once(
            memory,
            inbox,
            value["state_dir"],
            models,
            value["context"],
            model_policy=models.policy,
            source_budget_bytes=value["budgets"]["source_budget_bytes"],
        )

    return memory_worker.run(
        memory,
        inbox,
        value["state_dir"],
        models,
        value["context"],
        organize=organize,
        **value["budgets"],
    )


def retry(value, request_path, reason):
    request_path = Path(request_path).absolute()
    state = Path(value["state_dir"]).resolve()
    if (
        not request_path.is_relative_to(state)
        or request_path.resolve() != request_path
        or not Path(value["inbox"]).is_file()
    ):
        raise ValueError(
            "retry must select a retained request inside this worker state"
        )
    binding = json.loads(Path(value["binding"]).read_text())
    inbox = Inbox(value["inbox"], binding)
    with open(str(inbox.path) + ".worker.lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with inbox.connect() as con:
            row = con.execute("SELECT value FROM producer_owner").fetchone()
            owner = json.loads(row[0]) if row else {}
        if (
            owner.get("state_dir") != str(state)
            or owner.get("context") != value["context"]
            or owner.get("database") != str(Path(value["database"]).resolve())
        ):
            raise ValueError(
                "retry destination differs from established producer owner"
            )
        decision = authorize_retry(request_path, reason)
    return dict(
        schema="hmk.worker-retry/v1",
        state="authorized",
        request_sha256=decision["request_sha256"],
        network_invoked=False,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "status", "retry"])
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument(
        "--request",
        type=Path,
        help="Retained requests/HASH.json for explicit transport retry",
    )
    parser.add_argument(
        "--reason", help="Private record of reconciliation before retrying"
    )
    args = parser.parse_args(argv)
    if (args.command == "retry") != bool(args.request and args.reason) or (
        args.command != "retry" and (args.request or args.reason)
    ):
        parser.error(
            "retry requires --request and --reason; other commands accept neither"
        )
    try:
        value = profile(args.profile)
        if args.command == "status":
            result = memory_worker.observe(value["state_dir"])
        elif args.command == "retry":
            result = retry(value, args.request, args.reason)
        else:
            result = run(value)["status"]
    except Exception as error:
        # Launch failure is distinct from a phase receipt; no private exception
        # text, context, paths or credentials enter the supervisor's stdout.
        print(
            json.dumps(
                dict(
                    schema="hmk.worker-launch/v1",
                    state="failed",
                    error_type=type(error).__name__,
                )
            )
        )
        return 1
    print(json.dumps(result))
    return 0 if args.command != "run" or result["state"] == "idle" else 2


if __name__ == "__main__":
    raise SystemExit(main())
