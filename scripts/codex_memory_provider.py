"""Explicit isolated selected-evidence narrator/reviewer through native Codex.

No API credential is read by this adapter: the supported CLI uses its existing
ChatGPT authentication. Per-invocation controls suppress private instructions,
skills, native memory, tools and session persistence. No native memory is enabled; callers own selected-source authorization and
semantic qualification.
"""

import json
import hashlib
import os
from pathlib import Path
import subprocess
import time

from capturectl import digest
from codex_coordinator import checkpoint

DISABLED = (
    "shell_tool",
    "unified_exec",
    "apps",
    "plugins",
    "remote_plugin",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "view_image",
    "image_generation",
    "multi_agent",
    "multi_agent_v2",
    "sleep_tool",
    "goals",
    "memories",
    "chronicle",
    "hooks",
    "code_mode",
    "code_mode_host",
    "code_mode_only",
    "tool_suggest",
    "skill_search",
    "skill_mcp_dependency_install",
    "request_permissions_tool",
    "default_mode_request_user_input",
    "send_message_to_user_async",
    "send_async_message",
    "current_time_reminder",
    "unbounded_connection_retries",
)


def command(request, catalog, empty_cwd, logs):
    scope = request.get("source_scope")
    valid_source = (
        request.get("format") == "hmk-fictional-receiving-request/v1"
        and scope in (None, "fictional")
    ) or (
        request.get("format") == "hmk-selected-receiving-request/v1"
        and scope == "human-authorized-selected-context"
    )
    if (
        not valid_source
        or request.get("model") != "gpt-6.1-sol"
        or request.get("phase")
        not in {"narrative_generation", "narrative_revision", "narrative_review"}
        or request.get("reasoning_effort") not in {"low", "medium"}
        or (
            request.get("reasoning_effort") == "medium"
            and request.get("phase") != "narrative_review"
        )
        or request.get("fresh_context") is not True
        or request.get("tools_allowed") is not False
        or request.get("native_memory_allowed") is not False
    ):
        raise ValueError(
            "explicit isolated native Sol low narrative or medium review profile required"
        )
    messages = request["messages"]
    if (
        not isinstance(messages, list)
        or len(messages) < 2
        or messages[0].get("role") != "system"
        or [m.get("role") for m in messages[1:]]
        != ["user" if i % 2 == 0 else "assistant" for i in range(len(messages) - 1)]
        or messages[-1].get("role") != "user"
        or any(
            set(m) != {"role", "content"} or not isinstance(m["content"], str)
            for m in messages
        )
    ):
        raise ValueError(
            "only supplied system and alternating user/assistant textual turns are supported"
        )
    # Same task instructions/schema as the stateless API comparator. Codex adds
    # its generic base instructions; that harness difference must be reported.
    system = (
        messages[0]["content"]
        + "\nReturn only JSON conforming to this output schema. This constrains syntax, not evidence or truth:\n"
        + json.dumps(request["response_schema"])
    )
    config = dict(
        model_provider="openai",
        model_reasoning_effort=request["reasoning_effort"],
        model_reasoning_summary="none",
        model_catalog_json=str(catalog),
        project_doc_max_bytes=0,
        developer_instructions=system,
        include_environment_context=False,
        include_permissions_instructions=False,
        include_apps_instructions=False,
        include_collaboration_mode_instructions=False,
        web_search="disabled",
        forced_login_method="chatgpt",
        **{
            "skills.include_instructions": False,
            "skills.bundled.enabled": False,
            "cloud.skills.enabled": False,
            "orchestrator.mcp.enabled": False,
            "tools.update_plan.enabled": False,
            "tools.experimental_request_user_input.enabled": False,
            "analytics.enabled": False,
            "log_dir": str(logs),
        },
    )
    argv = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--json",
        "--color",
        "never",
        "-s",
        "read-only",
        "-C",
        str(empty_cwd),
        "-m",
        "gpt-6.1-sol",
        "--enable",
        "skip_host_skill_discovery",
    ]
    for flag in DISABLED:
        argv += ["--disable", flag]
    for key, value in config.items():
        argv += ["-c", key + "=" + json.dumps(value)]
    # Initial pairs retain their previously qualified rendering. The CLI has
    # only one stdin prompt: repairs/revisions explicitly carry the supplied
    # text transcript, without resuming a native session or loading its memory.
    stdin = (
        messages[1]["content"]
        if len(messages) == 2
        else (
            "Continue the following supplied task transcript. Its assistant turns are "
            "previous candidate outputs, not evidence. Answer its final user turn under "
            "the task instructions and schema above. No additional context exists.\n"
            + json.dumps(messages[1:], ensure_ascii=False)
        )
    )
    return argv + ["-"], stdin


def dispatch(request_path, root, catalog, runner=subprocess.run, credential_file=None):
    root, catalog, request_path = (
        Path(root).resolve(),
        Path(catalog).resolve(),
        Path(request_path).resolve(),
    )
    request = json.loads(request_path.read_text())
    d = digest(request)
    if request_path.stem != d:
        raise ValueError("request filename/hash mismatch")
    models = json.loads(catalog.read_text())["models"]
    selected = [m for m in models if m.get("slug") == "gpt-6.1-sol"]
    if len(selected) != 1 or any(
        selected[0].get(k) != v
        for k, v in dict(
            apply_patch_tool_type=None,
            shell_type="disabled",
            experimental_supported_tools=[],
            supports_search_tool=False,
            node_repl_disabled=True,
        ).items()
    ):
        raise ValueError(
            "native catalog must disable all selected model tool capabilities"
        )
    if request.get("reasoning_effort") == "medium" and "medium" not in {
        level.get("effort")
        for level in selected[0].get("supported_reasoning_levels", [])
    }:
        raise ValueError("native catalog does not establish medium reasoning support")
    cwd = root / "empty-cwd"
    cwd.mkdir(mode=0o700, exist_ok=True)
    argv, stdin = command(request, catalog, cwd.resolve(), (root / "logs").resolve())
    receipt_path = root / "dispatches" / (d + ".json")
    response_path = root / "responses" / (d + ".json")
    if receipt_path.exists() or response_path.exists():
        raise ValueError("preserve observed or unresolved dispatch; no implicit retry")
    receipt_path.parent.mkdir(exist_ok=True)
    codex_home = Path(
        os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    ).resolve()
    credential_file = (
        Path(credential_file) if credential_file else codex_home / "auth.json"
    )
    # --ignore-user-config and project_doc_max_bytes=0 do NOT suppress global
    # AGENTS.md. Hide the entire Codex home only in this process's mount namespace,
    # exposing the existing auth file read-only through an open descriptor. No
    # credentials are copied, no environment home is repurposed and other
    # sessions' instructions, history, config and native memory remain untouched.
    receipt = dict(
        state="started",
        provider="openai-codex-native",
        source_scope=request.get("source_scope", "fictional"),
        requested_model="gpt-6.1-sol",
        actual_response_model=None,
        request_sha256=d,
        reasoning_effort=request["reasoning_effort"],
        catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),
        command=argv,
        native_memory_allowed=False,
        tools_allowed=False,
        fresh_context_basis="new ephemeral CLI thread; no resume/fork, private instructions or skills",
        task_instructions_role="developer; generic native Codex base remains",
        task_transcript_rendering=(
            "initial-user-text"
            if len(request["messages"]) == 2
            else "explicit-role-labelled-json-transcript"
        ),
        isolation="private tmpfs over existing Codex home; original auth file mounted read-only by descriptor",
        usage=None,
        billed_cost_usd=None,
        qualification=False,
        timeout_seconds=300,
    )
    checkpoint(receipt_path, receipt)
    started = time.monotonic()
    credential_fd = None
    try:
        credential_fd = os.open(credential_file, os.O_RDONLY)
        isolated = [
            "bwrap",
            "--die-with-parent",
            "--bind",
            "/",
            "/",
            "--tmpfs",
            str(codex_home),
            "--ro-bind",
            f"/proc/self/fd/{credential_fd}",
            str(codex_home / "auth.json"),
            "--",
            *argv,
        ]
        result = runner(
            isolated,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=300,
            pass_fds=(credential_fd,),
        )
        events = [
            json.loads(line) for line in result.stdout.splitlines() if line.strip()
        ]
        receipt["exit_code"] = result.returncode
        receipt["event_types"] = [e.get("type") for e in events]
        items = [e["item"] for e in events if e.get("type") == "item.completed"]
        receipt["item_types"] = [i.get("type") for i in items]
        # Only final messages and usage survive; no reasoning, stderr or auth
        # data from CLI diagnostics is copied to the shared evidence.
        receipt["warnings"] = [
            i.get("message") for i in items if i.get("type") == "error"
        ]
        turns = [e for e in events if e.get("type") == "turn.completed"]
        if turns:
            receipt["native_usage"] = turns[-1].get("usage")
            u = receipt["native_usage"]
            if u is not None:
                receipt["usage"] = dict(
                    prompt_tokens=u["input_tokens"],
                    completion_tokens=u["output_tokens"],
                    total_tokens=u["input_tokens"] + u["output_tokens"],
                )
        unexpected = [
            i.get("type")
            for i in items
            if i.get("type") not in {"error", "agent_message"}
        ]
        messages = [i for i in items if i.get("type") == "agent_message"]
        if result.returncode or not turns or unexpected or len(messages) != 1:
            raise ValueError(
                "native attempt failed, used tools or did not return one final message"
            )
        receipt.update(
            state="completed", content=messages[0]["text"], tool_calls_observed=[]
        )
    except BaseException as error:
        # Preserve every ended attempt, including foreground interruption,
        # without exporting exception text, authentication data or CLI stderr.
        receipt.update(state="failed", error_type=type(error).__name__)
        raise
    finally:
        if credential_fd is not None:
            os.close(credential_fd)
        receipt["seconds"] = time.monotonic() - started
        checkpoint(receipt_path, receipt)
    response_path.parent.mkdir(exist_ok=True)
    checkpoint(
        response_path,
        dict(
            request_sha256=d,
            requested_model="gpt-6.1-sol",
            response_model=None,
            fresh_context=True,
            tool_calls_observed=[],
            dispatch_receipt=str(receipt_path),
            usage=receipt["usage"],
            seconds=receipt["seconds"],
            content=receipt["content"],
            finish_reason="native_turn_completed",
        ),
    )
    return receipt_path
