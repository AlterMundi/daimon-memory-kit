"""Explicit finite processing of an existing, selected HMK capture inbox.

No source scan, hook, scheduler, notification transport or native memory writer.
The receiving launcher supplies credentials in its process environment.
"""

import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from capture_inbox import Inbox
from codex_memory_provider import NATIVE_REVIEW_MODELS
import account_reconciliation
import memory_worker
from memory_models import Models, authorize_retry
import snapshot_store


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
    if set(value) - (required | {"embedding_env_file", "snapshots", "sleep_triage"}) or not required <= set(value):
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
    generation_fields = {"provider", "model", "effort", "output_token_limit"}
    legacy_generation = (
        set(generation) == generation_fields | {"credential_env"}
        and generation["provider"] == "deepseek"
        and generation["model"] == "deepseek-flash"
        and isinstance(generation["credential_env"], str)
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", generation["credential_env"])
    )
    native_generation = (
        set(generation) == generation_fields
        and generation["provider"] == "openai-codex-native"
        and generation["model"] == "gpt-6.2-sol"
        and review.get("model") == "gpt-6.2-sol"
        and bool(review.get("credential_file")) and bool(review.get("binary"))
    )
    if (
        not (legacy_generation or native_generation)
        or generation["effort"] != "low"
        or type(generation["output_token_limit"]) is not int
        or not 1 <= generation["output_token_limit"] <= 32768
    ):
        raise ValueError("explicit supported low-effort bounded generation profile required")
    if (
        set(review) - {"provider", "model", "effort", "catalog", "credential_file", "binary"}
        or not {"provider", "model", "effort", "catalog"} <= set(review)
        or review["provider"] != "openai-codex-native"
        or not isinstance(review["model"], str)
        or review["model"] not in NATIVE_REVIEW_MODELS
        or review["effort"] != "low"
    ):
        raise ValueError("explicit native OpenAI Codex Sol low review profile required")
    for field in ("catalog", "credential_file", "binary"):
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
    if set(budgets) - (set(limits) | {"source_max_bytes", "source_page_bytes"}) or not set(limits) <= set(budgets) or any(
        type(budgets[k]) is not int
        or budgets[k] < 1
        or (ceiling is not None and budgets[k] > ceiling)
        for k, ceiling in limits.items()
    ):
        raise ValueError("explicit positive supported invocation budgets required")
    ceiling = budgets.get("source_max_bytes", budgets["source_budget_bytes"])
    if type(ceiling) is not int or ceiling < budgets["source_budget_bytes"]:
        raise ValueError("source_max_bytes must cover source_budget_bytes")
    if "source_page_bytes" in budgets:
        page_bytes = budgets["source_page_bytes"]
        if type(page_bytes) is not int or not 4096 <= page_bytes <= min(32768, budgets["source_budget_bytes"]):
            raise ValueError("source_page_bytes must be between 4096 and 32768 and fit the ordinary window")
    if "snapshots" in value:
        snapshot_store.policy(value["snapshots"])
        routine=value['snapshots'].get('routine_backup')
        if routine and routine['subject'] != context['subject']:
            raise ValueError('periodic backup subject differs from receiving owner')
    if "sleep_triage" in value:
        settings = value["sleep_triage"]
        if (not isinstance(settings, dict)
                or set(settings) - {"provider_blocked", "paired_profile", "foreground_profile"} != {
                    "state_dir", "initial_after", "steps", "credential_env",
                    "source_review_report", "max_age_seconds"}
                or ("provider_blocked" in settings and settings["provider_blocked"] != "access_denied")
                or {"paired_profile", "foreground_profile"} <= set(settings)
                or any(key in settings and (not isinstance(settings[key], str)
                                            or not Path(settings[key]).is_absolute())
                       for key in ("paired_profile", "foreground_profile"))
                or any(not isinstance(settings[k], str) or not Path(settings[k]).is_absolute()
                       for k in ("state_dir", "source_review_report"))
                or not Path(settings["state_dir"]).resolve().is_relative_to(Path(value["state_dir"]).resolve())
                or Path(settings["state_dir"]).resolve() == Path(value["state_dir"]).resolve()
                or type(settings["initial_after"]) is not int or settings["initial_after"] < 0
                or type(settings["steps"]) is not int or not 1 <= settings["steps"] <= 32
                or type(settings["max_age_seconds"]) is not int or settings["max_age_seconds"] < 1
                or not isinstance(settings["credential_env"], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", settings["credential_env"])):
            raise ValueError("explicit bounded sleep triage profile required")
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
            source_budget_bytes=value["budgets"].get("source_max_bytes", value["budgets"]["source_budget_bytes"]),
            snapshot_policy=value.get("snapshots"),
        )

    result = memory_worker.run(
        memory,
        inbox,
        value["state_dir"],
        models,
        value["context"],
        organize=organize,
        snapshot_policy=value.get("snapshots"),
        **value["budgets"],
    )
    if 'routine_backup' in value.get('snapshots',{}):
        refresh_backup(value,inbox,result)
    if value.get("sleep_triage", {}).get("paired_profile"):
        run_paired_sleep(value, inbox, result)
    elif "sleep_triage" in value:
        run_sleep_triage(value, inbox, binding, result)
    return result


def run_paired_sleep(value, inbox, result):
    """Use the current worker's single Decisions allowance on its paired Conversation."""
    from codex_coordinator import checkpoint
    import paired_sleep
    from provider_status import ACTIONS, Alerts, ProviderProblem
    import sleep_health

    settings = value["sleep_triage"]
    primary = Path(value["state_dir"]) / "worker-status.json"
    alerts = Alerts(inbox)
    operation = "sleep-triage:paired-conversation"
    with open(str(inbox.path) + ".worker.lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if json.loads(primary.read_text()) != result["status"]:
            raise ValueError("another worker advanced; preserve its status")
        try:
            legacy = Path(settings["state_dir"])
            if any((legacy / filename).exists() for filename in ("dispatch.json", "context-dispatch.json")):
                raise ValueError("legacy triage dispatch requires reconciliation")
            profile_path = Path(settings["paired_profile"])
            if profile_path.is_symlink() or profile_path.stat().st_uid != os.getuid() or profile_path.stat().st_mode & 0o077:
                raise ValueError("private paired profile required")
            paired = json.loads(profile_path.read_bytes())
            root = Path(paired["state_dir"])
            if (root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077
                    or paired["being_ref"] != value["context"]["subject"]
                    or paired["body_ref"] != value["context"]["source_instance"]):
                raise ValueError("paired Conversation owner differs from the supervised worker")
            with (root / "paired.lock").open("ab") as source_lock:
                fcntl.flock(source_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                outcome = paired_sleep.run(paired, root, worker_settings=settings)
                checkpoint(root / "receiving.json", outcome)
        except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
            outcome = dict(state="blocked", reason_code="observation_unreadable")

        receipt = dict(outcome.get("triage", {}), state=outcome["state"],
                       source="paired_conversation", capture_complete=outcome.get("capture_complete") is True)
        if outcome["state"] == "blocked":
            code = receipt.get("reason_code", outcome.get("reason_code"))
            code = code if code in ACTIONS else "observation_unreadable"
            incident = operation + ":source" if code == "observation_unreadable" else operation
            failure = ProviderProblem("dmk", incident, dict(code=code))
            receipt["reason_code"] = code
            receipt["alert_id"] = alerts.report(incident, "selection", failure, reopen=True)
            result["status"]["state"] = "pending"
        else:
            if receipt["capture_complete"]:
                alerts.resolve(operation + ":source")
            if receipt.get("classified_pages"):
                alerts.resolve(operation)
        result["status"].update(sleep_triage=receipt, updated_ns=time.time_ns())
        result["status"]["sleep_health"] = sleep_health.health(
            value["state_dir"], settings["source_review_report"],
            max_age_seconds=settings["max_age_seconds"], worker=result["status"],
        )
        checkpoint(primary, result["status"])


def run_sleep_triage(value, inbox, binding, result, *, gateway_original=None,
                     telegram_text=False, voice_transcripts=False, foreground_voice_transcripts=False,
                     foreground_direct_inputs=False):
    from codex_coordinator import checkpoint
    from provider_status import ACTIONS, Alerts, ProviderProblem
    import sleep_health
    import sleep_triage

    settings = value["sleep_triage"]
    root = Path(settings["state_dir"])
    path = Path(value["state_dir"]) / "worker-status.json"
    with open(str(inbox.path) + ".worker.lock", "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if json.loads(path.read_text()) != result["status"]:
            raise ValueError("another worker advanced; preserve its status")
        operation = "sleep-triage:" + result["status"]["owner"]
        local_operation = operation + ":input"
        alerts = Alerts(inbox)
        after = None if (root / "cursor.json").exists() else settings["initial_after"]
        blocked = settings.get("provider_blocked")
        if blocked:
            failure = ProviderProblem("openai-decisions", operation, {"code": blocked})
            receipt = dict(state="blocked", reason_code=blocked,
                           alert_id=alerts.report(operation, "selection", failure))
        else:
            try:
                with ExitStack() as stack:
                    foreground = {}
                    remaining = False
                    if profile_path := settings.get("foreground_profile"):
                        import paired_sleep

                        profile, selected, human, exclude = stack.enter_context(
                            paired_sleep.supervised_foreground(profile_path, binding))
                        cutoff = profile["native_observation_after"]
                        cursor = json.loads((root / "cursor.json").read_text())
                        if (cursor.get("foreground_after", cutoff) != cutoff
                                or ("foreground_after" not in cursor and (
                                    cursor["after"] != cutoff or cursor["page"] or any(
                                        (root / name).exists() for name in ("dispatch.json", "context-dispatch.json"))))):
                            raise ValueError("Avatar source requires the settled preceding review")
                        remaining = paired_sleep.capture_foreground(profile, selected, human, inbox,
                                                                     after=cursor["after"])
                        foreground.update(foreground_after=cutoff, foreground_filter=exclude)
                    receipt = sleep_triage.run(binding, root, after=after, steps=settings["steps"],
                                               api_key=os.environ.get(settings["credential_env"]),
                                               human_id=settings.get("human_id"), gateway_original=gateway_original,
                                               telegram_text=telegram_text, voice_transcripts=voice_transcripts,
                                               foreground_voice_transcripts=foreground_voice_transcripts,
                                               foreground_direct_inputs=foreground_direct_inputs, **foreground)
                    if remaining:
                        receipt["state"] = "pending"
            except (ValueError, KeyError, IndexError, OSError, sqlite3.Error) as error:
                attempt = None
                for name in ("context-dispatch.json", "dispatch.json"):
                    try:
                        retained = json.loads((root / name).read_text())
                    except FileNotFoundError:
                        continue
                    except (OSError, ValueError):
                        attempt = dict(problem={"code": "dispatch_unresolved"})
                        break
                    if not isinstance(retained, dict):
                        attempt = dict(problem={"code": "dispatch_unresolved"})
                        break
                    if retained.get("state") != "complete":
                        attempt = retained
                        break
                if attempt is not None:
                    problem = attempt.get("problem")
                    if not isinstance(problem, dict) or problem.get("code") not in ACTIONS:
                        problem = {"code": "dispatch_unresolved"}
                    failure = ProviderProblem("openai-decisions", attempt.get("request_sha256", operation), problem)
                    incident = operation
                elif isinstance(error, sleep_triage.CredentialRequired):
                    failure = ProviderProblem("openai-decisions", operation, {"code": "authentication_failed"})
                    incident = operation
                else:
                    failure = ProviderProblem("dmk", local_operation, {"code": "observation_unreadable"})
                    incident = local_operation
                receipt = dict(state="blocked", reason_code=failure.problem["code"],
                               error_type=type(error).__name__,
                               alert_id=alerts.report(incident, "selection", failure, reopen=True))
            else:
                alerts.resolve(local_operation)
                if receipt["classified_pages"]:
                    alerts.resolve(operation)
        if receipt["state"] == "blocked":
            result["status"]["state"] = "pending"
        result["status"]["sleep_triage"] = receipt
        result["status"]["updated_ns"] = time.time_ns()
        result["status"]["sleep_health"] = sleep_health.health(
            value["state_dir"], settings["source_review_report"],
            max_age_seconds=settings["max_age_seconds"], worker=result["status"],
        )
        checkpoint(path, result["status"])

def refresh_backup(value,inbox,result):
    """One model-free backup maintenance step after the finite worker phases."""
    from periodic_backups import Baselines
    from codex_coordinator import checkpoint
    path=Path(value['state_dir'])/'worker-status.json'
    with open(str(inbox.path)+'.worker.lock','a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if json.loads(path.read_text()) != result['status']:
            raise ValueError('another worker advanced; preserve its status')
        checkpoint(path,dict(result['status'],state='running',phase='backup',updated_ns=time.time_ns()))
        pool=Baselines(value['database'],value['snapshots'])
        try:
            backup=pool.refresh()
        except (OSError,ValueError,KeyError,TypeError) as error:
            backup=dict(state='failed',reason_code='backup_state_unreadable',error_type=type(error).__name__)
        safe=backup_notice(value,inbox,backup)
        result['backup']=safe; result['status']['backup']=safe
        if backup['state']=='failed':
            result['status']['state']='pending'
        result['status'].update(phase=None,updated_ns=time.time_ns())
        checkpoint(path,result['status'])


def backup_notice(value,inbox,backup):
    """Use the established durable producer outbox, including explicit refresh."""
    from provider_status import Alerts, ProviderProblem
    from capturectl import digest
    binding=json.loads(inbox.binding)
    if (value['context']['subject'] != value['snapshots']['routine_backup']['subject'] or
            any(binding[k]!=value['context'][k] for k in ('subject','source_instance'))):
        raise ValueError('backup notification owner differs')
    alerts=Alerts(inbox)
    operation='periodic-backup:'+digest(dict(database=str(Path(value['database']).resolve()),subject=value['context']['subject']))
    safe={k:v for k,v in backup.items() if k not in {'snapshot','sha256'}}
    if backup['state']=='failed':
        with inbox.connect() as con:
            prior=con.execute("SELECT id FROM operational_alerts WHERE operation_key=? AND phase='backup' AND state='open' LIMIT 1",(operation,)).fetchone()
        if prior:alert_id=prior[0]
        else:
            failure=ProviderProblem('dmk-backup',backup.get('episode',str(time.time_ns())),
                dict(code='storage_pressure' if backup.get('reason_code')=='backup_capacity' else 'provider_error'))
            alert_id=alerts.report(operation,'backup',failure)
        safe['alert_id']=alert_id
    elif backup['state']=='current':alerts.resolve(operation)
    return safe


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
