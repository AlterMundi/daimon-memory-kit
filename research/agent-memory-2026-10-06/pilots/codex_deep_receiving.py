"""Isolated persistent Codex receiver, derived from the qualified stage-six driver.

The caller owns freshness checks and supplies only fictional/authorized selections.
No automatic launch, capture, publication or production configuration changes.
"""

import json
import os
import pathlib
import selectors
import subprocess
import time


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


class Native:
    def __init__(
        self,
        root,
        binary,
        catalog,
        *,
        reader=None,
        model="gpt-6.1-sol",
        use_memory=True,
        startup_processing=False,
        memory_version="v1",
        max_rollouts=1,
        startup_switch_supported=True,
        extraction_only=False,
    ):
        selected = [
            m
            for m in json.loads(pathlib.Path(catalog).read_text())["models"]
            if m.get("slug") == model
        ]
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
            raise ValueError("receiver catalog must disable unrelated model tools")
        self.reader = reader
        from deep_recall import tool_spec

        self.dynamic_tools = [tool_spec()] if reader else []
        self.model = model
        self.root = pathlib.Path(root).resolve()
        self.root.mkdir(mode=0o700, exist_ok=True)
        home = self.root / "codex-home"
        home.mkdir(mode=0o700, exist_ok=True)
        work = self.root / "work"
        work.mkdir(mode=0o700, exist_ok=True)
        self.events = (
            json.loads((self.root / "events.json").read_text())
            if (self.root / "events.json").exists()
            else []
        )
        self.i = 0
        config = {
            "model": self.model,
            "model_provider": "openai",
            "model_reasoning_effort": "low",
            "forced_login_method": "chatgpt",
            "model_catalog_json": "/tmp/selected-model.json",
            "features.shell_tool": False,
            "tools.update_plan.enabled": False,
            "tools.experimental_request_user_input.enabled": False,
            "features.memories": use_memory or startup_processing,
            "memories.startup_processing": startup_processing,
            "memories.version": memory_version,
            "memories.dual_write": False,
            "memories.generate_memories": False,
            "memories.use_memories": use_memory,
            "memories.dedicated_tools": True,
            "memories.min_rollout_idle_hours": 1,
            "memories.max_rollouts_per_startup": max_rollouts,
            "memories.extract_model": self.model,
            "memories.consolidation_model": self.model,
            "project_doc_max_bytes": 0,
            "skills.include_instructions": False,
            "skills.bundled.enabled": False,
            "features.skip_host_skill_discovery": True,
            "cloud.skills.enabled": False,
            "orchestrator.mcp.enabled": False,
            "features.apps": False,
            "features.plugins": False,
            "features.hooks": False,
            "features.goals": False,
            "features.multi_agent": False,
            "features.multi_agent_v2": False,
            "features.code_mode": False,
            "features.code_mode_only": False,
            "features.code_mode_host": True,
            "features.browser_use": False,
            "features.browser_use_external": False,
            "web_search": "disabled",
            "analytics.enabled": False,
            "log_dir": "/home/debian/.codex/logs",
            "include_environment_context": False,
            "include_apps_instructions": False,
            "shell_environment_policy.inherit": "core",
        }
        if extraction_only:
            config["memories.extraction_only"] = True
        if not startup_switch_supported:
            config.pop("memories.startup_processing")
        argv = [
            "/usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex",
            "app-server",
            "--stdio",
        ]
        for k, v in config.items():
            argv += ["-c", k + "=" + json.dumps(v)]
        fd = os.open("/home/debian/.codex/auth.json", os.O_RDONLY)
        isolated = [
            "bwrap",
            "--die-with-parent",
            "--unshare-pid",
            "--ro-bind",
            "/",
            "/",
        ]
        for path in (
            "/home",
            "/root",
            "/tmp",
            "/var",
            "/run",
            "/mnt",
            "/media",
            "/srv",
            "/opt",
        ):
            if pathlib.Path(path).exists():
                isolated += ["--tmpfs", path]
        isolated += [
            "--ro-bind",
            str(pathlib.Path(binary).resolve()),
            "/usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex",
            "--ro-bind",
            str(pathlib.Path(catalog).resolve()),
            "/tmp/selected-model.json",
        ]
        isolated += [
            "--ro-bind",
            "/run/systemd/resolve",
            "/run/systemd/resolve",
            "--dir",
            "/home/debian",
            "--bind",
            str(home),
            "/home/debian/.codex",
            "--bind" if startup_processing else "--ro-bind",
            str(home / "memories"),
            "/home/debian/.codex/memories",
            "--ro-bind",
            f"/proc/self/fd/{fd}",
            "/home/debian/.codex/auth.json",
            "--bind",
            str(work),
            "/tmp/work",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--chdir",
            "/tmp/work",
            "--",
            *argv,
        ]
        env = {
            k: v
            for k, v in os.environ.items()
            if k in ("PATH", "HOME", "USER", "LANG", "SSL_CERT_FILE", "SSL_CERT_DIR")
        }
        err = open(self.root / "stderr.log", "a")
        self.proc = subprocess.Popen(
            isolated,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err,
            text=False,
            env=env,
            pass_fds=(fd,),
        )
        os.close(fd)
        err.close()
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.buffer = b""
        self.rpc(
            "initialize",
            {
                "clientInfo": {"name": "hmk-fictional-projection", "version": "0.1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.send({"method": "initialized"})

    def send(self, item):
        self.proc.stdin.write((json.dumps(item) + "\n").encode())
        self.proc.stdin.flush()

    def event(self, timeout=60):
        end = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            if not self.selector.select(max(0, end - time.monotonic())):
                raise TimeoutError("native response timeout")
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("native process ended")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        e = json.loads(line)
        self.events.append(e)
        save(self.root / "events.json", self.events)
        if "method" in e and "id" in e:
            if (
                e["method"] != "item/tool/call"
                or self.reader is None
                or e["params"]["tool"] != "hmk_recall"
                or e["params"]["threadId"] != self.tid
                or e["params"].get("namespace") is not None
            ):
                raise RuntimeError("unexpected native client request: " + e["method"])
            response = self.reader.app_server_response(e["params"]["arguments"])
            self.events.append(
                dict(
                    host_tool_response=dict(
                        call_id=e["params"]["callId"], response=response
                    )
                )
            )
            save(self.root / "events.json", self.events)
            self.send(dict(id=e["id"], result=response))
        return e

    def rpc(self, method, params):
        self.i += 1
        mid = self.i
        self.send({"id": mid, "method": method, "params": params})
        while True:
            e = self.event()
            if e.get("id") == mid and "method" not in e:
                if "error" in e:
                    raise RuntimeError(json.dumps(e["error"]))
                return e["result"]

    def start(self, binding=None, ephemeral=False):
        r = self.rpc(
            "thread/start",
            {
                "cwd": "/tmp/work",
                "model": self.model,
                "modelProvider": "openai",
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
                "ephemeral": ephemeral,
                "dynamicTools": self.dynamic_tools,
                **({"developerInstructions": binding} if binding else {}),
            },
        )
        self.tid = r["thread"]["id"]
        save(self.root / "thread.json", r)
        return r

    def resume(self, tid, binding):
        result = self.rpc(
            "thread/resume",
            dict(
                threadId=tid,
                cwd="/tmp/work",
                model=self.model,
                modelProvider="openai",
                approvalPolicy="never",
                sandbox="workspace-write",
                developerInstructions=binding,
            ),
        )
        self.tid = result["thread"]["id"]
        save(self.root / "resume.json", result)
        return result

    def turn(self, text):
        before = len(self.events)
        started = time.monotonic()
        r = self.rpc(
            "turn/start",
            {
                "threadId": self.tid,
                "input": [{"type": "text", "text": text}],
                "effort": "low",
            },
        )
        turn = r["turn"]["id"]
        while True:
            e = self.event()
            if (
                e.get("method") == "turn/completed"
                and e["params"]["turn"]["id"] == turn
            ):
                break
        receipt = {
            "turn_id": turn,
            "seconds": time.monotonic() - started,
            "events": self.events[before:],
        }
        save(self.root / f"turn-{turn}.json", receipt)
        if e["params"]["turn"]["status"] != "completed":
            raise RuntimeError("native turn did not complete")
        return receipt

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        self.selector.close()
