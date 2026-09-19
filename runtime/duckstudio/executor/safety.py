"""IntentGate: the only path from executor to backend for intents and behaviors (§7).

Order of checks for every send:
  1. global battery floor (independent of the manifest),
  2. manifest `preconditions` against the snapshot,
  3. clamp every param to the manifest's `min`/`max`, refuse unknown params,
  4. rate limit (intents + behaviors together),
  5. hand over to the backend.
`stop()` skips all of it and goes straight to the backend.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..backends.base import DuckBackend, Health, RobotState
from ..common import Condition
from ..events import EventBus
from ..skills.manifest import SkillManifest
from .conditions import Snapshot, evaluate

DEFAULT_MIN_BATTERY = 0.15
DEFAULT_MAX_PER_SECOND = 20


@dataclass
class GateDecision:
    accepted: bool
    reason: str | None = None
    params: dict[str, float] = field(default_factory=dict)
    clamped: dict[str, tuple[float, float]] = field(default_factory=dict)  # requested -> sent
    failed: list[str] = field(default_factory=list)


class IntentGate:
    def __init__(
        self,
        backend: DuckBackend,
        *,
        min_battery: float = DEFAULT_MIN_BATTERY,
        max_per_second: int = DEFAULT_MAX_PER_SECOND,
        clock: Callable[[], float] = time.monotonic,
        bus: EventBus | None = None,
    ) -> None:
        self.backend = backend
        self.min_battery = min_battery
        self.max_per_second = max_per_second
        self.clock = clock
        self.bus = bus or EventBus()
        self.snapshot = Snapshot()
        self._sent_at: deque[float] = deque()

    # -- perception input (last-value-wins) ---------------------------------------------

    def observe(
        self,
        *,
        health: Health | None = None,
        state: RobotState | None = None,
        tof_min_m: float | None = None,
        person_distance_m: float | None = None,
    ) -> None:
        if health is not None:
            self.snapshot.health = health
        if state is not None:
            self.snapshot.state = state
        if tof_min_m is not None:
            self.snapshot.tof_min_m = tof_min_m
        if person_distance_m is not None:
            self.snapshot.person_distance_m = person_distance_m

    # -- gated sends --------------------------------------------------------------------

    async def send(self, skill: SkillManifest, params: Mapping[str, float]) -> GateDecision:
        if skill.intent is None:
            return self._refuse(skill, "skill_has_no_intent")
        gate = self._common_checks(skill)
        if gate is not None:
            return gate
        sent: dict[str, float] = {}
        clamped: dict[str, tuple[float, float]] = {}
        for key, requested in params.items():
            spec = skill.params.get(key)
            if spec is None:
                return self._refuse(skill, "unknown_param", failed=[key])
            value = float(requested)
            lo = spec.min if spec.min is not None else value
            hi = spec.max if spec.max is not None else value
            bounded = min(max(value, lo), hi)
            if bounded != value:
                clamped[key] = (value, bounded)
            sent[key] = bounded
        if self._rate_limited():
            return self._refuse(skill, "rate_limited")
        await self.backend.intent(skill.intent, **sent)
        self._sent_at.append(self.clock())
        if clamped:
            desc = ", ".join(f"{k} {req:g}→{got:g}" for k, (req, got) in clamped.items())
            self.bus.emit(
                "intent.clamped",
                f"{skill.name.de}: Werte begrenzt ({desc}).",
                level="warn",
                skill=skill.id,
                clamped={k: list(v) for k, v in clamped.items()},
            )
        self.bus.emit("intent.sent", f"{skill.name.de} gesendet.", skill=skill.id, params=sent)
        return GateDecision(accepted=True, params=sent, clamped=clamped)

    async def send_behavior(self, skill: SkillManifest) -> GateDecision:
        if skill.behavior is None:
            return self._refuse(skill, "skill_has_no_behavior")
        gate = self._common_checks(skill)
        if gate is not None:
            return gate
        if self._rate_limited():
            return self._refuse(skill, "rate_limited")
        await self.backend.behavior(skill.behavior)
        self._sent_at.append(self.clock())
        self.bus.emit("behavior.sent", f"{skill.name.de} gestartet.", skill=skill.id)
        return GateDecision(accepted=True)

    async def stop(self) -> None:
        """Emergency stop: no battery check, no preconditions, no rate limit. Ever."""
        await self.backend.stop()
        self.bus.emit("stop", "Notstopp: Ente angehalten.", level="warn")

    # -- internals ----------------------------------------------------------------------

    def _common_checks(self, skill: SkillManifest) -> GateDecision | None:
        health = self.snapshot.health
        if health is None:
            return self._refuse(skill, "no_health_snapshot")
        if health.battery < self.min_battery:
            return self._refuse(skill, "battery_low", failed=[f"battery {health.battery:.2f}"])
        failed = [
            c
            for c in skill.preconditions
            if evaluate(Condition.parse(c), self.snapshot) is not True
        ]
        if failed:
            return self._refuse(skill, "precondition_failed", failed=failed)
        return None

    def _rate_limited(self) -> bool:
        now = self.clock()
        while self._sent_at and now - self._sent_at[0] >= 1.0:
            self._sent_at.popleft()
        return len(self._sent_at) >= self.max_per_second

    def _refuse(
        self, skill: SkillManifest, reason: str, failed: list[str] | None = None
    ) -> GateDecision:
        failed = failed or []
        text = _REFUSAL_TEXT_DE.get(reason, "abgelehnt").format(
            skill=skill.name.de, detail=", ".join(failed)
        )
        self.bus.emit(
            "intent.refused", text, level="warn", skill=skill.id, reason=reason, failed=failed
        )
        return GateDecision(accepted=False, reason=reason, failed=failed)


_REFUSAL_TEXT_DE = {
    "no_health_snapshot": "{skill} nicht gesendet: noch keine Zustandsdaten von der Ente.",
    "battery_low": "{skill} nicht gesendet: Akku zu niedrig ({detail}).",
    "precondition_failed": "{skill} nicht gesendet: Voraussetzung nicht erfüllt ({detail}).",
    "unknown_param": "{skill} nicht gesendet: unbekannter Parameter ({detail}).",
    "rate_limited": "{skill} nicht gesendet: zu viele Befehle pro Sekunde.",
    "skill_has_no_intent": "{skill} ist kein Bewegungs-Intent.",
    "skill_has_no_behavior": "{skill} ist kein benanntes Verhalten.",
}
