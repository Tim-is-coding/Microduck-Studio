"""Safety invariants from CLAUDE.md §7. Every bullet there has a test here (or a named skip)."""

from __future__ import annotations

import pytest

from duckstudio.backends.base import DuckBackend
from duckstudio.backends.mock import ManualClock, MockBackend
from duckstudio.events import EventBus
from duckstudio.executor import IntentGate
from duckstudio.skills import SkillRegistry


@pytest.fixture
async def gate(mock: MockBackend, clock: ManualClock) -> IntentGate:
    g = IntentGate(mock, clock=clock, bus=EventBus())
    g.observe(health=await mock.health(), state=await mock.state())
    return g


async def test_clamps_to_manifest_params(
    gate: IntentGate, mock: MockBackend, registry: SkillRegistry
) -> None:
    decision = await gate.send(registry.get("walk"), {"vx": 5.0, "vyaw": -3.0})
    assert decision.accepted
    assert mock.intents_sent()[-1].params == {"vx": 0.15, "vyaw": -1.0}
    assert decision.clamped == {"vx": (5.0, 0.15), "vyaw": (-3.0, -1.0)}
    assert any(e.kind == "intent.clamped" for e in gate.bus.history)


async def test_battery_gate_refuses_below_floor(
    gate: IntentGate, mock: MockBackend, registry: SkillRegistry
) -> None:
    mock.set_battery(0.10)
    gate.observe(health=await mock.health())
    decision = await gate.send(registry.get("walk"), {"vx": 0.05})
    assert not decision.accepted and decision.reason == "battery_low"
    assert mock.intents_sent() == []


async def test_no_intent_without_health_snapshot(
    mock: MockBackend, clock: ManualClock, registry: SkillRegistry
) -> None:
    gate = IntentGate(mock, clock=clock)
    decision = await gate.send(registry.get("walk"), {"vx": 0.05})
    assert not decision.accepted and decision.reason == "no_health_snapshot"
    assert mock.intents_sent() == []


async def test_manifest_preconditions_are_enforced(
    gate: IntentGate, mock: MockBackend, registry: SkillRegistry
) -> None:
    mock.push_over()
    gate.observe(state=await mock.state())
    decision = await gate.send(registry.get("walk"), {"vx": 0.05})
    assert not decision.accepted and decision.reason == "precondition_failed"
    assert decision.failed == ["standing"]
    assert mock.intents_sent() == []
    # ...and getup, whose precondition is `fallen`, is exactly what is allowed now
    assert (await gate.send_behavior(registry.get("getup"))).accepted


async def test_unknown_param_is_refused(
    gate: IntentGate, mock: MockBackend, registry: SkillRegistry
) -> None:
    decision = await gate.send(registry.get("walk"), {"joint_3": 1.0})
    assert not decision.accepted and decision.reason == "unknown_param"
    assert mock.intents_sent() == []


async def test_rate_limit(
    gate: IntentGate, mock: MockBackend, registry: SkillRegistry, clock: ManualClock
) -> None:
    walk = registry.get("walk")
    for _ in range(gate.max_per_second):
        assert (await gate.send(walk, {"vx": 0.05})).accepted
    refused = await gate.send(walk, {"vx": 0.05})
    assert not refused.accepted and refused.reason == "rate_limited"
    clock.tick(1.0)
    assert (await gate.send(walk, {"vx": 0.05})).accepted


async def test_stop_bypasses_every_check(
    gate: IntentGate, mock: MockBackend, registry: SkillRegistry
) -> None:
    mock.set_battery(0.0)
    mock.push_over()
    gate.observe(health=await mock.health(), state=await mock.state())
    for _ in range(gate.max_per_second):
        gate._sent_at.append(gate.clock())
    assert not (await gate.send(registry.get("walk"), {"vx": 0.05})).accepted
    await gate.stop()
    assert mock.calls[-1].kind == "stop" and mock.stopped


def test_backend_protocol_has_no_joint_level_commands() -> None:
    """§7: only intents and named behaviors, never joint commands. Not even for tests."""
    public = {n for n in dir(DuckBackend) if not n.startswith("_")}
    assert public >= {"intent", "behavior", "stop", "state", "health", "frame", "tof"}
    assert not any("joint" in n or "servo" in n or "motor" in n for n in public)


async def test_mock_rejects_intents_outside_the_known_set(mock: MockBackend) -> None:
    from duckstudio.backends.base import UnknownIntent

    with pytest.raises(UnknownIntent):
        await mock.intent("robot.set_joint", index=3, position=1.0)


@pytest.mark.skip(reason="M2: heartbeat task lands with the executor tick loop")
def test_heartbeat_runs_in_its_own_task_and_stops_duck_when_executor_dies() -> None: ...


@pytest.mark.skip(reason="M2: pad.input override lands with the executor")
def test_gamepad_input_preempts_executor_immediately() -> None: ...
