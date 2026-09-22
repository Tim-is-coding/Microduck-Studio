"""Evaluate condition strings ("battery > 0.15", "fallen") against a perception snapshot.

The snapshot is last-value-wins and never blocks (§6.4): perception tasks write whatever is
fresh, the executor reads what is there at tick time. Step context (elapsed time, time
budget, stop distance, what the current step is steering at) lives here too so `timeout` and
`target_reached` evaluate like any other signal.

Two subjects can be steered at: the person the local detector tracks, and the thing the VLM
was asked to find. They have different clocks — the detector runs on every frame, the VLM
twice a minute — so they have different freshness windows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..backends.base import Health, RobotState
from ..common import Condition, Text
from ..perception.base import PersonDetection, Sighting, TargetSighting
from ..perception.vlm import VlmAnswer

MOTOR_HOT_C = 70.0
PERSON_FRESH_S = 1.0
# Three missed answers at the default 0.5 Hz: a VLM sighting stays usable much longer than a
# detection, because nothing else is going to refresh it sooner (§4).
TARGET_FRESH_S = 6.0
# `steady`: standing without a break for this long. A duck that has just got up is upright
# before its head is: in duck-sim the neck is still curled at -90° when the trunk is level and
# takes another 1.1–1.3 s back to its rest pose, the head ToF looking at the floor at its feet
# all the while. A step resumed then ends on "obstacle too close" (docs/upstream-notes.md,
# "Falling over in duck-sim"). Re-measure on the real duck (docs/m4-hardware-checklist.md).
STEADY_S = 2.0


@dataclass(frozen=True)
class VlmRequest:
    """The standing question the perception service asks on the runtime's behalf.

    Set by the executor when a `vlm.*` step starts, cleared when the behavior ends. It
    carries the provider the behavior opted into (§7) so the service can refuse to send a
    frame anywhere the user did not agree to.
    """

    question: str  # what is sent to the model, in the behavior's first language
    text: Text  # the same question for the Studio, in every language the step has
    provider: str
    behavior_id: str


@dataclass
class Snapshot:
    now: float = 0.0
    health: Health | None = None
    state: RobotState | None = None
    tof_min_m: float | None = None
    tof_rows: list[list[float]] | None = None
    person: PersonDetection | None = None
    target: TargetSighting | None = None
    vlm: VlmAnswer | None = None  # the last answer, whatever it said
    vlm_request: VlmRequest | None = None
    speech: set[str] = field(default_factory=set)  # phrases heard since the last tick
    pad_active_at: float | None = None
    standing_since: float | None = None  # written by the executor each tick, for `steady`
    # per-step context, written by the executor before evaluating
    elapsed_s: float = 0.0
    budget_s: float | None = None
    stop_distance_m: float | None = None  # how close the step wants to get
    steering: str | None = None  # "person" | "target" | None

    def forget_duck(self) -> None:
        """Drop everything one duck told us, before another one is asked. A switch from the
        simulation to the real duck must not leave the sim's "standing, battery full" behind
        for a precondition to read."""
        self.health = self.state = None
        self.tof_min_m = self.tof_rows = None
        self.person = self.target = self.vlm = None
        self.pad_active_at = self.standing_since = None

    @property
    def person_fresh(self) -> PersonDetection | None:
        if self.person is None or self.now - self.person.timestamp > PERSON_FRESH_S:
            return None
        return self.person

    @property
    def target_fresh(self) -> TargetSighting | None:
        if self.target is None or self.now - self.target.timestamp > TARGET_FRESH_S:
            return None
        return self.target

    @property
    def person_distance_m(self) -> float | None:
        p = self.person_fresh
        return None if p is None else p.distance_m

    @property
    def subject(self) -> Sighting | None:
        """What the active step steers at: its target when it asked for one, else the person."""
        return self.target_fresh if self.steering == "target" else self.person_fresh


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
        case "steady":
            if snapshot.state is None:
                return None
            since = snapshot.standing_since
            return since is not None and snapshot.now - since >= STEADY_S
        case "tof_distance":
            return snapshot.tof_min_m
        case "person_found":
            return snapshot.person_fresh is not None
        case "person_distance":
            return snapshot.person_distance_m
        case "target_found":
            return snapshot.target_fresh is not None
        case "target_distance":
            t = snapshot.target_fresh
            return None if t is None else t.distance_m
        case "target_reached":
            subject = snapshot.subject
            if subject is None or subject.distance_m is None or snapshot.stop_distance_m is None:
                return None
            return subject.distance_m <= snapshot.stop_distance_m
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
