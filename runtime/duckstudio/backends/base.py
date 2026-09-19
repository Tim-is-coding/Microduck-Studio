"""Backend interface (CLAUDE.md §6.3) and the value types every backend returns.

Three implementations share one contract test suite (`tests/backends/test_contract.py`):
`mock` (deterministic), `sim` (duck-sim Unix sockets, M1) and `duck` (real robot, M4).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from pydantic import Field, field_validator

from ..common import Strict

JOINT_COUNT = 15
TOF_SIZE = 8


class Imu(Strict):
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class Flags(Strict):
    standing: bool
    fallen: bool
    sitting: bool
    moving: bool


class Pose2D(Strict):
    """Ground-plane pose. Only mock/sim can know it; the real duck has no odometry yet."""

    x: float
    y: float
    heading: float


class Health(Strict):
    battery: float = Field(ge=0.0, le=1.0)  # upstream reports percent 0–100; backends divide by 100
    temperatures_c: dict[str, float] = Field(default_factory=dict)
    ok: bool
    warnings: list[str] = Field(default_factory=list)


class RobotState(Strict):
    timestamp: float
    joints: list[float] = Field(min_length=JOINT_COUNT, max_length=JOINT_COUNT)
    imu: Imu
    flags: Flags
    pose: Pose2D | None = None


class TofFrame(Strict):
    timestamp: float
    distances_m: list[list[float]]

    @field_validator("distances_m")
    @classmethod
    def _shape(cls, rows: list[list[float]]) -> list[list[float]]:
        if len(rows) != TOF_SIZE or any(len(r) != TOF_SIZE for r in rows):
            raise ValueError(f"ToF frame must be {TOF_SIZE}x{TOF_SIZE}")
        if any(d < 0 for r in rows for d in r):
            raise ValueError("ToF distances must be >= 0")
        return rows

    @property
    def min_distance(self) -> float:
        return min(d for r in self.distances_m for d in r)


class BackendError(Exception):
    pass


class NotConnected(BackendError):
    pass


class UnknownIntent(BackendError):
    pass


class UnknownBehavior(BackendError):
    pass


@runtime_checkable
class DuckBackend(Protocol):
    """What the executor may do with a duck. Intents and named behaviors only, never joints."""

    kind: str

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def health(self) -> Health: ...

    async def state(self) -> RobotState: ...

    async def frame(self) -> bytes:
        """One encoded image from the head camera: JPEG (mock) or PNG (mediad GET /frame)."""
        ...

    def tof(self) -> AsyncIterator[TofFrame]:
        """Stream of 8x8 depth frames in metres (upstream `tof.frame` sends millimetres)."""
        ...

    async def intent(self, name: str, **params: float) -> None:
        """Send a `robot.*` intent (e.g. robot.move vx/vy/vyaw). Clamping and gating happen in
        the executor's IntentGate; upstream clamps nothing and refuses unknown params."""
        ...

    async def behavior(self, name: str) -> None:
        """Run a named upstream behavior: sit, stand, getup, pickup, kick, quack."""
        ...

    async def stop(self) -> None:
        """Emergency stop. Never gated, never rate-limited, never raises."""
        ...
