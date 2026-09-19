"""Deterministic stand-in for a duck (§6.3 `mock`).

Used by tests and by the Studio when no simulation is running. Time is injected: with the
default `ManualClock` nothing moves unless a test calls `advance()`; `make_backend("mock")`
uses `time.monotonic` so the Studio sees a duck that walks when told to.

The mock records every call in `calls`, so tests can assert that the IntentGate clamped a
value before it reached the backend. It does NOT clamp or gate anything itself.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from .. import upstream
from ._mock_frame import MOCK_FRAME_JPEG
from .base import (
    JOINT_COUNT,
    TOF_SIZE,
    Flags,
    Health,
    Imu,
    NotConnected,
    Pose2D,
    RobotState,
    TofFrame,
    UnknownBehavior,
    UnknownIntent,
)


class ManualClock:
    """A clock that only moves when told to. Default for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def tick(self, dt: float) -> None:
        self.now += dt


@dataclass
class Call:
    kind: str  # "intent" | "behavior" | "stop"
    name: str
    params: dict[str, float] = field(default_factory=dict)
    t: float = 0.0


class MockBackend:
    kind = "mock"

    TOF_MAX_M = 2.0
    TOF_FOV_RAD = 0.6  # half-angle of the 8x8 sensor's field of view (approximation)
    SERVO_HOT_C = 70.0

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        battery: float = 0.9,
        known_intents: set[str] | None = None,
        known_behaviors: set[str] | None = None,
        person_xy: tuple[float, float] = (1.0, 0.0),
        frame: bytes = MOCK_FRAME_JPEG,
        tof_hz: float = 10.0,
    ) -> None:
        self.clock: Callable[[], float] = clock or ManualClock()
        self.connected = False
        self.battery = battery
        self.known_intents = (
            set(known_intents) if known_intents is not None else set(upstream.INTENTS)
        )
        self.known_behaviors = (
            set(known_behaviors) if known_behaviors is not None else set(upstream.BEHAVIORS)
        )
        self.pose = Pose2D(x=0.0, y=0.0, heading=0.0)
        self.velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)  # vx, vy, vyaw
        self.flags = Flags(standing=True, fallen=False, sitting=False, moving=False)
        self.person_xy = person_xy
        self.servo_temp_c = 38.0
        self.calls: list[Call] = []
        self.stopped = False
        self._frame = frame
        self._tof_hz = tof_hz
        self._last_t = self.clock()

    # -- DuckBackend --------------------------------------------------------------------

    async def connect(self) -> None:
        self.connected = True
        self._last_t = self.clock()

    async def close(self) -> None:
        self.connected = False

    async def health(self) -> Health:
        self.advance()
        warnings = []
        if self.battery < 0.15:
            warnings.append("battery_low")
        if self.servo_temp_c > self.SERVO_HOT_C:
            warnings.append("motor_hot")
        return Health(
            battery=max(0.0, min(1.0, self.battery)),
            temperatures_c={"servo_max": self.servo_temp_c},
            ok=self.connected and not warnings,
            warnings=warnings,
        )

    async def state(self) -> RobotState:
        self._require_connected()
        self.advance()
        return RobotState(
            timestamp=self.clock(),
            joints=[0.0] * JOINT_COUNT,
            imu=Imu(roll=math.pi / 2 if self.flags.fallen else 0.0, yaw=self.pose.heading),
            flags=self.flags,
            pose=self.pose,
        )

    async def frame(self) -> bytes:
        self._require_connected()
        return self._frame

    async def tof(self) -> AsyncIterator[TofFrame]:
        self._require_connected()
        pace = 0.0 if isinstance(self.clock, ManualClock) else 1.0 / self._tof_hz
        while self.connected:
            self.advance()
            yield self.tof_frame()
            await asyncio.sleep(pace)

    async def intent(self, name: str, **params: float) -> None:
        self._require_connected()
        if name not in self.known_intents:
            raise UnknownIntent(name)
        self.advance()
        if name == upstream.ROBOT_MOVE.name:
            if self.flags.standing and not self.flags.fallen:
                self.velocity = (
                    float(params.get("vx", 0.0)),
                    float(params.get("vy", 0.0)),
                    float(params.get("vyaw", 0.0)),
                )
        self.calls.append(Call("intent", name, dict(params), self.clock()))
        self.stopped = False

    async def behavior(self, name: str) -> None:
        self._require_connected()
        if name not in self.known_behaviors:
            raise UnknownBehavior(name)
        self.advance()
        self.velocity = (0.0, 0.0, 0.0)
        if name == "sit":
            self.flags = Flags(standing=False, fallen=False, sitting=True, moving=False)
        elif name in ("stand", "getup"):
            self.flags = Flags(standing=True, fallen=False, sitting=False, moving=False)
        self.calls.append(Call("behavior", name, {}, self.clock()))

    async def stop(self) -> None:
        # Never raises, even before connect(): §7 says stop() bypasses every check.
        self.velocity = (0.0, 0.0, 0.0)
        self.stopped = True
        self.flags = self.flags.model_copy(update={"moving": False})
        self.calls.append(Call("stop", "stop", {}, self.clock()))

    # -- simulation of the world (deterministic) ----------------------------------------

    def advance(self, dt: float | None = None) -> None:
        """Integrate pose and battery up to `clock()` (or by `dt`, ticking a ManualClock)."""
        if dt is not None:
            if isinstance(self.clock, ManualClock):
                self.clock.tick(dt)
            else:
                raise ValueError("advance(dt) needs a ManualClock")
        now = self.clock()
        dt = max(0.0, now - self._last_t)
        self._last_t = now
        if dt == 0.0:
            return
        vx, vy, yaw = self.velocity
        moving = any(abs(v) > 1e-9 for v in self.velocity)
        if moving and self.flags.standing and not self.flags.fallen:
            h = self.pose.heading + yaw * dt
            x = self.pose.x + (vx * math.cos(h) - vy * math.sin(h)) * dt
            y = self.pose.y + (vx * math.sin(h) + vy * math.cos(h)) * dt
            self.pose = Pose2D(x=x, y=y, heading=h)
        self.flags = self.flags.model_copy(update={"moving": moving})
        # ~1 %/min while walking, ~0.1 %/min idle
        self.battery = max(0.0, self.battery - dt * (0.01 if moving else 0.001) / 60.0)

    def tof_frame(self) -> TofFrame:
        """8x8 grid: `TOF_MAX_M` everywhere, a nearer column where the fake person stands."""
        rows = [[self.TOF_MAX_M] * TOF_SIZE for _ in range(TOF_SIZE)]
        dx = self.person_xy[0] - self.pose.x
        dy = self.person_xy[1] - self.pose.y
        dist = math.hypot(dx, dy)
        bearing = math.atan2(dy, dx) - self.pose.heading
        bearing = (bearing + math.pi) % (2 * math.pi) - math.pi
        if abs(bearing) < self.TOF_FOV_RAD and dist < self.TOF_MAX_M:
            col = int(round((1.0 - (bearing / self.TOF_FOV_RAD + 1.0) / 2.0) * (TOF_SIZE - 1)))
            for r in range(2, TOF_SIZE - 1):
                rows[r][col] = round(dist, 3)
        return TofFrame(timestamp=self.clock(), distances_m=rows)

    # -- test helpers -----------------------------------------------------------------

    def push_over(self) -> None:
        """Simulated shove: the duck is on the ground until `getup`."""
        self.velocity = (0.0, 0.0, 0.0)
        self.flags = Flags(standing=False, fallen=True, sitting=False, moving=False)

    def set_battery(self, level: float) -> None:
        self.battery = level

    def set_servo_temp(self, celsius: float) -> None:
        self.servo_temp_c = celsius

    def intents_sent(self) -> list[Call]:
        return [c for c in self.calls if c.kind == "intent"]

    def _require_connected(self) -> None:
        if not self.connected:
            raise NotConnected("mock backend: call connect() first")
