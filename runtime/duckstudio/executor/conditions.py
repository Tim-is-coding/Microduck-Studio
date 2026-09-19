"""Evaluate condition strings ("battery > 0.15", "fallen") against a perception snapshot.

The snapshot is last-value-wins and never blocks (§6.4): whoever has fresh data writes it,
the executor reads whatever is there at tick time.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..backends.base import Health, RobotState
from ..common import Condition

MOTOR_HOT_C = 70.0


@dataclass
class Snapshot:
    health: Health | None = None
    state: RobotState | None = None
    tof_min_m: float | None = None
    person_distance_m: float | None = None
    elapsed_s: float = 0.0


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
        case "person_distance":
            return snapshot.person_distance_m
        case "elapsed":
            return snapshot.elapsed_s
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
