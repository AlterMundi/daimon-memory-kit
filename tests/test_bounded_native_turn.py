"""Verify narrow host accounting and the one-attempt native generation contract."""

import time
from uuid import uuid4

import pytest

from bounded_native_turn import run_turn


class Exchange:
    def __init__(self, condition):
        self.condition = condition
        self.sent = []
        self.retained = []
        self.frames = self.exchange()

    def send(self, packet):
        if packet.get("result", {}).get("authorized"):
            assert len(self.retained) == 1
        if packet.get("result", {}).get("recorded"):
            assert len(self.retained) == 2
        self.sent.append(packet)

    def receive(self):
        return next(self.frames)

    def retain(self, key, value):
        if self.condition == "journal-write-failure":
            raise OSError("simulated durable write failure")
        self.retained.append((key, value))

    def exchange(self):
        yield {"id": 1, "result": {}}
        yield {"id": 2, "result": {
            "thread": {"id": "own-ephemeral"},
            "model": "gpt-6.2-sol", "modelProvider": "openai",
        }}
        start = self.sent[-1]
        assert start["method"] == "turn/startBoundedIfIdle"
        params = start["params"]
        assert params["providerMaxOutputTokens"] == 50
        assert params["hostRestrictions"]["tools"] == []
        assert params["turn"]["effort"] == "low"
        assert params["allowance"]["maxProviderAttempts"] == 1
        reservation = dict(
            threadId="own-ephemeral", cycleId=params["providerReservationCycleId"],
            attemptId=str(uuid4()), ordinal=1,
            maxRequestBytes=params["allowance"]["maxRequestBytes"],
            deadlineUnixMs=params["allowance"]["deadlineUnixMs"],
        )
        if self.condition == "wrong-ceiling":
            reservation["maxRequestBytes"] -= 1
        yield {"id": 70, "method": "turn/providerAttempt/reserve", "params": reservation}
        if self.condition == "second-reservation":
            yield {"id": 71, "method": "turn/providerAttempt/reserve",
                   "params": dict(reservation, attemptId=str(uuid4()))}
        if self.condition != "no-usage":
            usage = {k: v for k, v in reservation.items() if k not in ("deadlineUnixMs", "maxRequestBytes")}
            usage.update(
                model=None, responseId="receipt-1",
                tokenUsage={"inputTokens": 100, "outputTokens": 51 if self.condition == "over-cap" else 2,
                            "totalTokens": 102},
            )
            yield {"id": 72, "method": "turn/providerAttempt/usage", "params": usage}
        yield {"id": 3, "result": {"turn": {"id": "own-turn"}}}
        yield {"method": "item/completed", "params": {
            "threadId": "own-ephemeral", "turnId": "own-turn",
            "item": {"type": "commandExecution" if self.condition == "tool" else "agentMessage", "text": "{}"},
        }}
        yield {"method": "turn/completed", "params": {
            "threadId": "own-ephemeral", "turn": {"id": "own-turn", "status": "completed"},
        }}


def run_fixture(wire):
    return run_turn(
        wire, model="gpt-6.2-sol", cwd="/unused", text="Fictional data only.",
        schema={"type": "object"}, output_limit=50,
        deadline_ms=int(time.time() * 1000) + 12000, retain=wire.retain,
    )


def test_capped_native_turn_requires_retained_reservation_and_usage():
    wire = Exchange("ordinary")
    content, usage = run_fixture(wire)
    assert content == "{}" and usage == {
        "prompt_tokens": 100, "completion_tokens": 2, "total_tokens": 102,
    }
    assert [key for key, _ in wire.retained] == ["provider_reservation", "provider_usage"]
    assert wire.retained[1][1]["observed_model"] is None
    assert len([p for p in wire.sent if p.get("result", {}).get("authorized")]) == 1


@pytest.mark.parametrize(("condition", "reason"), [
    ("wrong-ceiling", "reservation"),
    ("second-reservation", "reservation"),
    ("over-cap", "outside the ceiling"),
    ("no-usage", "lacks a matched"),
    ("tool", "attempted a tool"),
])
def test_native_turn_fails_closed(condition, reason):
    wire = Exchange(condition)
    with pytest.raises(ValueError, match=reason):
        run_fixture(wire)
    assert len([p for p in wire.sent if p.get("result", {}).get("authorized")]) <= 1
    if condition == "over-cap":
        assert wire.retained[-1][1]["usage"]["completion_tokens"] == 51


def test_no_ack_if_reservation_was_not_retained():
    wire = Exchange("journal-write-failure")
    with pytest.raises(OSError, match="durable"):
        run_fixture(wire)
    assert not any(p.get("result", {}).get("authorized") for p in wire.sent)
