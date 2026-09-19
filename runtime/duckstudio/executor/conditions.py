"""Evaluate condition strings ("battery > 0.15", "fallen") against a perception snapshot.

The snapshot is last-value-wins and never blocks (§6.4): perception tasks write whatever is
fresh, the executor reads what is there at tick time. Step context (elapsed time, time
budget, target distance) lives here too so `timeout` and `target_reached` evaluate like any
other signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..backends.base import Health, RobotState
from ..common import Condition
from ..perception.base import PersonDetection

MOTOR_HOT_C = 70.0
PERSON_FRESH_S = 1.0


@dataclass
class Snapshot:
    now: float = 0.0
    health: Health | None = None
    state: RobotState | None = None
    tof_min_m: float | None = None
    tof_rows: list[list[float]] | None = None
    person: PersonDetection | None = None
    speech: set[str] = field(default_factory=set)  # phrases heard since the last tick
    pad_active_at: float | None = None
    # per-step context, written by the executor before evaluating
    elapsed_s: float = 0.0
    budget_s: float | None = None
    target_distance_m: float | None = None

    @property
    def person_fresh(self) -> PersonDetection | None:
        if self.person is None or self.now - self.person.timestamp > PERSON_FRESH_S:
            return None
        return self.person

    @property
    def person_distance_m(self) -> float | None:
        p = self.person_fresh
        return None if p is None else p.distance_m


def signal_value(snapshot: Snapshot, signal: str) -> float | bool | None:
    """Look up a signal by name. None means "unknown right now", which never passes."""
    match signal:
        case "battery":
            return None if snapshot.health is None else snapshot.health.battery
        case "motor_hot":
            if snapshot.health is None:
                return None
            return any(t > MOTOR_HOT_C for t in snapshot.health.temperatures_c.values())
        case "standing" | "fallen" | "sitting" | "moving":
            if snapshot.state is None:
                return None
            return getattr(snapshot.state.flags, signal)
        case "tof_distance":
            return snapshot.tof_min_m
        case "person_found":
            return snapshot.person_fresh is not None
        case "person_distance":
            return snapshot.person_distance_m
        case "target_reached":
            d = snapshot.person_distance_m
            if d is None or snapshot.target_distance_m is None:
                return None
            return d <= snapshot.target_distance_m
        case "elapsed":
            return snapshot.elapsed_s
        case "timeout":
            if snapshot.budget_s is None:
                return False
            return snapshot.elapsed_s >= snapshot.budget_s
        case _:
            return None


def evaluate(condition: Condition | str, snapshot: Snapshot) -> bool | None:
    """True/False when the signal is known, None when it is not."""
    cond = Condition.parse(condition) if isinstance(condition, str) else condition
    value = signal_value(snapshot, cond.signal)
    if value is None:
        return None
    if cond.op is None:
        return bool(value)
    assert cond.value is not None
    v = float(value)
    match cond.op:
        case "<":
            return v < cond.value
        case "<=":
            return v <= cond.value
        case ">":
            return v > cond.value
        case ">=":
            return v >= cond.value
        case "==":
            return v == cond.value
        case "!=":
            return v != cond.value
    return None  # pragma: no cover
