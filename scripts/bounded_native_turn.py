"""Run one isolated Codex turn with a durable reservation and provider token ceiling."""

import json
import os
import select
import subprocess
import time
from uuid import UUID, uuid4

MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_FRAMES = 4096
MAX_WIRE_BYTES = 16 * 1024 * 1024


class Stdio:
    def __init__(self, process, deadline):
        self.process = process
        self.deadline = deadline
        self.buffer = bytearray()
        self.read_bytes = 0
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)

    def wait(self, *, reading=False):
        source = [self.process.stdout] if reading else []
        destination = [] if reading else [self.process.stdin]
        remaining = max(0, self.deadline - time.monotonic())
        readable, writable, _ = select.select(source, destination, [], remaining)
        if not (readable or writable):
            raise TimeoutError("bounded native I/O deadline")

    def send(self, packet):
        data = (json.dumps(packet, ensure_ascii=False) + "\n").encode()
        if len(data) > MAX_REQUEST_BYTES:
            raise ValueError("bounded native input exceeds its transport limit")
        while data:
            self.wait()
            try:
                sent = os.write(self.process.stdin.fileno(), data)
            except BlockingIOError:
                continue
            data = data[sent:]

    def receive(self):
        while True:
            end = self.buffer.find(b"\n")
            if end >= 0:
                if end > MAX_FRAME_BYTES:
                    raise ValueError("oversize native response frame")
                packet = json.loads(self.buffer[:end])
                del self.buffer[:end + 1]
                if not isinstance(packet, dict):
                    raise ValueError("invalid native response frame")
                return packet
            if len(self.buffer) > MAX_FRAME_BYTES:
                raise ValueError("oversize native response frame")
            self.wait(reading=True)
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise EOFError("native observer closed before the terminal receipt")
            self.read_bytes += len(chunk)
            if self.read_bytes > MAX_WIRE_BYTES:
                raise ValueError("native response exceeds the observation limit")
            self.buffer.extend(chunk)


def valid_identifier(value):
    try:
        return str(UUID(value)) == value
    except (TypeError, ValueError, AttributeError):
        return False


def run_turn(wire, *, model, cwd, text, schema, output_limit, deadline_ms, retain):
    """Consume a private stdio exchange, reserving at most one physical attempt.

    retain must durably write the exact reservation before it can be authorized.
    A caller must persist its dispatch intent before entering this function.
    """
    if model != "gpt-6.2-sol" or type(output_limit) is not int or not 1 <= output_limit <= 32768:
        raise ValueError("expected Sol 6.2 with an explicit bounded output budget")
    if not 0 < deadline_ms - int(time.time() * 1000) <= 300000:
        raise ValueError("invalid native generation deadline")

    cycle = str(uuid4())
    allowance = {
        "maxProviderAttempts": 1,
        "maxRequestBytes": MAX_REQUEST_BYTES,
        "deadlineUnixMs": deadline_ms,
    }
    thread = turn_id = completed_turn = None
    attempt = None
    usage = None
    final = None
    observed_turn = None
    step = 1
    wire.send({"id": step, "method": "initialize", "params": {
        "clientInfo": {"name": "dmk-bounded-generation", "version": "1"},
        "capabilities": {"experimentalApi": True},
    }})
    for _ in range(MAX_FRAMES):
        packet = wire.receive()
        if time.time() * 1000 >= deadline_ms:
            raise TimeoutError("bounded native turn deadline")
        method = packet.get("method")
        packet_id = packet.get("id")
        params = packet.get("params", {})
        if method is None:
            if packet_id != step or "error" in packet or not isinstance(packet.get("result"), dict):
                raise ValueError("native admission refused or unconfirmed")
            result = packet["result"]
            if step == 1:
                wire.send({"method": "initialized"})
                step += 1
                wire.send({"id": step, "method": "thread/start", "params": {
                    "model": model, "modelProvider": "openai", "cwd": cwd,
                    "approvalPolicy": "never", "sandbox": "read-only", "ephemeral": True,
                    "dynamicTools": [], "serviceName": "dmk-bounded-generation",
                }})
            elif step == 2:
                thread = result["thread"]["id"]
                if not isinstance(thread, str) or not thread or len(thread) > 200:
                    raise ValueError("invalid ephemeral thread identity")
                if result.get("model") != model or result.get("modelProvider") != "openai":
                    raise ValueError("native model or provider differs from the selected route")
                step += 1
                wire.send({"id": step, "method": "turn/startBoundedIfIdle", "params": {
                    "turn": {"threadId": thread, "input": [{"type": "text", "text": text}],
                             "model": model, "effort": "low", "outputSchema": schema},
                    "allowance": allowance,
                    "hostRestrictions": {
                        "permissions": ":read-only", "tools": [], "environment": {},
                        "codeModeLimits": {"maxHeapSizeBytes": 32 * 1024 * 1024,
                                           "maxYieldTimeMs": 1000},
                    },
                    "providerReservationCycleId": cycle,
                    "providerUsageObservations": True,
                    "providerMaxOutputTokens": output_limit,
                }})
            elif step == 3 and turn_id is None:
                turn_id = result["turn"]["id"]
                if not isinstance(turn_id, str) or not turn_id or len(turn_id) > 200:
                    raise ValueError("invalid bounded turn identity")
            else:
                raise ValueError("unexpected native response")
        elif packet_id is not None:
            common = {
                "cycleId": params.get("cycleId", ""),
                "attemptId": params.get("attemptId", ""),
            }
            matching = thread is not None and params.get("threadId") == thread and common["cycleId"] == cycle
            if method == "turn/providerAttempt/reserve":
                authorized = (
                    matching and step == 3 and completed_turn is None and attempt is None
                    and type(params.get("ordinal")) is int and params["ordinal"] == 1
                    and valid_identifier(common["attemptId"])
                    and params.get("maxRequestBytes") == allowance["maxRequestBytes"]
                    and params.get("deadlineUnixMs") == deadline_ms
                )
                if authorized:
                    attempt = {**common, "ordinal": 1}
                    retain("provider_reservation", {
                        **attempt, "max_request_bytes": MAX_REQUEST_BYTES,
                        "max_output_tokens": output_limit, "deadline_unix_ms": deadline_ms,
                    })
                wire.send({"id": packet_id, "result": {**common, "authorized": authorized}})
                if not authorized:
                    raise ValueError("unexpected or repeated provider reservation")
            elif method == "turn/providerAttempt/usage":
                observed = params.get("tokenUsage")
                response_id = params.get("responseId")
                observed_model = params.get("model")
                recorded = (
                    matching and attempt is not None and usage is None
                    and params.get("ordinal") == attempt["ordinal"]
                    and common["attemptId"] == attempt["attemptId"]
                    and isinstance(response_id, str) and 0 < len(response_id) <= 200
                    and (observed_model is None
                         or isinstance(observed_model, str) and 0 < len(observed_model) <= 200)
                    and isinstance(observed, dict)
                    and all(type(observed.get(k)) is int and observed[k] >= 0
                            for k in ("inputTokens", "outputTokens", "totalTokens"))
                )
                if recorded:
                    usage = {"prompt_tokens": observed["inputTokens"],
                             "completion_tokens": observed["outputTokens"],
                             "total_tokens": observed["totalTokens"]}
                    retain("provider_usage", {**attempt, "usage": usage,
                                              "response_id": response_id,
                                              "observed_model": observed_model})
                wire.send({"id": packet_id, "result": {**common, "recorded": recorded}})
                if not recorded:
                    raise ValueError("provider usage absent or mismatched")
                if observed_model not in (None, model) or usage["completion_tokens"] > output_limit:
                    raise ValueError("provider response model or usage outside the ceiling")
            else:
                raise ValueError("unexpected native approval or tool request")
        elif thread is not None and params.get("threadId") == thread:
            if method in ("item/started", "item/completed"):
                item = params["item"]
                if item.get("type") not in ("userMessage", "agentMessage", "reasoning"):
                    raise ValueError("isolated native turn attempted a tool or other operation")
                item_turn = params.get("turnId")
                if not isinstance(item_turn, str) or (observed_turn and item_turn != observed_turn):
                    raise ValueError("item belongs to another native turn")
                observed_turn = item_turn
                if method == "item/completed" and item["type"] == "agentMessage":
                    if final is not None or not isinstance(item.get("text"), str) or not item["text"]:
                        raise ValueError("expected exactly one final native message")
                    final = item["text"]
            elif method == "turn/completed":
                ended = params["turn"]
                if ended.get("status") != "completed" or ended.get("error") is not None:
                    raise ValueError("bounded native turn did not complete successfully")
                completed_turn = ended["id"]
                if not isinstance(completed_turn, str) or not completed_turn:
                    raise ValueError("invalid terminal native turn identity")
        if turn_id and completed_turn:
            if turn_id != completed_turn or observed_turn != turn_id or not (attempt and usage and final):
                raise ValueError("bounded native completion lacks a matched reservation, usage or message")
            json.loads(final)
            return final, usage
    raise ValueError("too many native frames")


def execute(argv, *, credential_fd, timeout=300, **request):
    """Run only the caller's isolated child. Never attach to a shared daemon."""
    deadline = time.monotonic() + timeout
    deadline_ms = int(time.time() * 1000) + timeout * 1000
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, pass_fds=(credential_fd,)) as process:
        try:
            return run_turn(Stdio(process, deadline), deadline_ms=deadline_ms, **request)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
