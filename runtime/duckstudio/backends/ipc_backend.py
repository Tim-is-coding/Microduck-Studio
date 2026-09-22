"""A duck reached over upstream's JSON-RPC sockets: robotd (+ tofd, + mediad's console).

`SimBackend` is this class pointed at duck-sim's socket directory. The real duck (M4) can
reuse it through `ssh -L` tunnels, which is what microduck-mcp does.

Connections (upstream serves one request at a time per socket, streams own theirs):
  - `_ctl`  request/response: robot.health, robot.do, robot.sound, robot.look, ...
  - `_sub`  `robot.subscribe {hz}` → `robot.state` notifications, last value kept
  - `_halt` dedicated to `robot.stop`, so an emergency stop never queues behind a slow call
  - one more per `tof()` iterator (`tof.stream` → `tof.frame`)

Mapping to our value types lives in the pure functions at the bottom (tested against a fake
daemon in tests/backends/fake_robotd.py and against duck-sim with DUCKSTUDIO_SIM=1).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .. import upstream
from .base import (
    JOINT_COUNT,
    TOF_SIZE,
    BackendError,
    BehaviorRefused,
    Flags,
    Health,
    Imu,
    NoCamera,
    NotConnected,
    Pose2D,
    RobotState,
    TofFrame,
    UnknownBehavior,
    UnknownIntent,
)
from .ipc import Connection

log = logging.getLogger(__name__)

STATE_WAIT_S = 2.0
FRAME_TIMEOUT_S = 3.0


class IpcBackend:
    kind = "ipc"

    def __init__(
        self,
        *,
        robot_socket: str,
        tof_socket: str | None = None,
        pad_socket: str | None = None,
        console_url: str | None = None,
        state_hz: int = 10,
    ) -> None:
        self.robot_socket = robot_socket
        self.tof_socket = tof_socket
        self.pad_socket = pad_socket
        self.console_url = console_url.rstrip("/") if console_url else None
        self.state_hz = state_hz
        self.connected = False
        self.hello: dict[str, Any] | None = None
        self.subscription: dict[str, Any] | None = None
        self._ctl: Connection | None = None
        self._halt: Connection | None = None
        self._sub: Connection | None = None
        self._state_task: asyncio.Task[None] | None = None
        self._last_state: dict[str, Any] | None = None
        self._state_ready: asyncio.Event | None = None

    # -- lifecycle ----------------------------------------------------------------------

    async def connect(self) -> None:
        upstream.require_verified(
            upstream.HELLO,
            upstream.ROBOT_MOVE,
            upstream.ROBOT_HEALTH,
            upstream.ROBOT_SUBSCRIBE,
            upstream.ROBOT_STATE,
            upstream.ROBOT_STOP,
            upstream.ROBOT_DO,
            upstream.ROBOT_SOUND,
            upstream.ROBOT_POLICIES,
        )
        await self.close()
        try:
            self._ctl = await Connection.open(self.robot_socket)
            self._halt = await Connection.open(self.robot_socket)
            self._sub = await Connection.open(self.robot_socket)
            self.hello = self._ctl.hello
            result = await self._sub.call(upstream.ROBOT_SUBSCRIBE.name, {"hz": self.state_hz})
            self.subscription = result if isinstance(result, dict) else {}
            if not self.subscription.get("accepted", False):
                raise BackendError(
                    f"robot.subscribe refused: {self.subscription.get('unavailable', '?')}"
                )
        except BackendError:
            await self.close()
            raise
        self._last_state = None
        self._state_ready = asyncio.Event()
        self._state_task = asyncio.create_task(self._pump_state(), name=f"{self.kind}-state")
        self.connected = True

    async def _pump_state(self) -> None:
        assert self._sub is not None and self._state_ready is not None
        try:
            async for msg in self._sub.notifications():
                if msg.get("method") == upstream.ROBOT_STATE.name:
                    self._last_state = msg.get("params") or {}
                    self._state_ready.set()
        finally:
            if self.connected:
                log.warning("%s: robot.state stream ended — daemon gone?", self.kind)
            self.connected = False

    async def close(self) -> None:
        self.connected = False
        if self._state_task is not None:
            self._state_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._state_task
            self._state_task = None
        for conn in (self._sub, self._halt, self._ctl):
            if conn is not None:
                await conn.close()
        self._sub = self._halt = self._ctl = None

    def _ctl_conn(self) -> Connection:
        if not self.connected or self._ctl is None:
            raise NotConnected(f"{self.kind}: not connected to {self.robot_socket}")
        return self._ctl

    # -- DuckBackend --------------------------------------------------------------------

    async def health(self) -> Health:
        raw = await self._ctl_conn().call(upstream.ROBOT_HEALTH.name)
        return health_from_upstream(raw if isinstance(raw, dict) else {})

    async def state(self) -> RobotState:
        self._ctl_conn()
        if self._last_state is None:
            assert self._state_ready is not None
            try:
                await asyncio.wait_for(self._state_ready.wait(), STATE_WAIT_S)
            except TimeoutError as e:
                raise BackendError(f"no robot.state within {STATE_WAIT_S}s") from e
        assert self._last_state is not None
        return state_from_upstream(self._last_state)

    async def frame(self) -> bytes:
        self._ctl_conn()
        if not self.console_url:
            raise NoCamera(f"{self.kind}: no mediad console configured")
        url = f"{self.console_url}/frame"
        try:
            async with httpx.AsyncClient(timeout=FRAME_TIMEOUT_S) as client:
                r = await client.get(url)
        except httpx.HTTPError as e:
            raise NoCamera(f"camera unreachable at {url}: {e}") from e
        if r.status_code == 503:
            raise NoCamera("camera snapshot unavailable (mediad answered 503)")
        if r.status_code != 200:
            raise BackendError(f"GET {url} -> HTTP {r.status_code}")
        return r.content

    async def tof(self) -> AsyncIterator[TofFrame]:
        self._ctl_conn()
        if not self.tof_socket:
            raise BackendError(f"{self.kind}: no tof socket configured")
        # tofd answers tof.stream and head_imu.stream and nothing else — no `hello`
        # (verified against duck-sim 0.14.1 and 0.14.4; docs/upstream-notes.md).
        conn = await Connection.open(self.tof_socket, hello=False)
        try:
            result = await conn.call(upstream.TOF_STREAM.name)
            result = result if isinstance(result, dict) else {}
            if not result.get("accepted", False):
                raise BackendError(f"tof.stream refused: {result.get('unavailable', '?')}")
            if result.get("sensor") is None:
                raise BackendError("this duck reports no ToF sensor (tof.stream sensor=null)")
            rows, cols = int(result.get("rows", TOF_SIZE)), int(result.get("cols", TOF_SIZE))
            async for msg in conn.notifications():
                if msg.get("method") == upstream.TOF_FRAME.name:
                    yield tof_from_upstream(msg.get("params") or {}, rows, cols)
        finally:
            await conn.close()

    async def pad_activity(self) -> AsyncIterator[dict[str, Any]]:
        """Yield `pad.report` frames from padd (`{"report": "frame", "events": [...]}`).

        padd is not part of duck-sim, so this is exercised against the fake daemon only until
        hardware arrives. Any frame with events means a human holds the sticks (§7).
        """
        self._ctl_conn()
        if not self.pad_socket:
            raise BackendError(f"{self.kind}: no pad socket configured")
        conn = await Connection.open(self.pad_socket, hello=False)
        try:
            result = await conn.call(upstream.PAD_INPUT.name)
            if isinstance(result, dict) and result.get("accepted") is False:
                raise BackendError(f"pad.input refused: {result.get('reason', '?')}")
            async for msg in conn.notifications():
                if msg.get("method") != upstream.PAD_REPORT.name:
                    continue
                params = msg.get("params") or {}
                if params.get("report") == "frame" and params.get("events"):
                    yield params
        finally:
            await conn.close()

    async def intent(self, name: str, **params: float) -> None:
        ctl = self._ctl_conn()
        if name not in upstream.INTENTS:
            raise UnknownIntent(name)
        payload = {k: float(v) for k, v in params.items()}
        if name == upstream.ROBOT_LOOK.name:
            await ctl.call(name, payload)  # answers LookResult{head, clamped}
        else:
            await ctl.notify(name, payload)  # continuous intents travel as notifications

    async def behavior(self, name: str) -> None:
        ctl = self._ctl_conn()
        spec = upstream.BEHAVIOR_CALLS.get(name)
        if spec is None:
            raise UnknownBehavior(name)
        method, params = spec
        if name in ("sit", "stand"):
            # sit_toggle flips; ask the robot which way it is before flipping the wrong way
            policies = await ctl.call(upstream.ROBOT_POLICIES.name)
            sitting = policies.get("sitting") if isinstance(policies, dict) else None
            if sitting is not None and bool(sitting) == (name == "sit"):
                return
        result = await ctl.call(method.name, dict(params))
        if isinstance(result, dict) and result.get("accepted") is False:
            raise BehaviorRefused(f"{name}: {result.get('reason') or 'refused by robot'}")

    async def stop(self) -> None:
        """robot.stop on its own connection. Never raises."""
        if self._halt is None:
            return
        try:
            await self._halt.call(upstream.ROBOT_STOP.name, timeout=1.0)
        except Exception as e:  # noqa: BLE001 - stop must never raise
            log.error("%s: robot.stop failed: %s", self.kind, e)


# -- mapping upstream payloads to our value types -------------------------------------------


def health_from_upstream(raw: dict[str, Any]) -> Health:
    """HealthResult → Health. Battery percent is 0–100 upstream; absent means unknown."""
    warnings: list[str] = []
    battery = raw.get("battery")
    if isinstance(battery, dict) and battery.get("percent") is not None:
        level = max(0.0, min(1.0, float(battery["percent"]) / 100.0))
    else:
        level = 1.0
        warnings.append("battery_not_reported")
    temps: dict[str, float] = {}
    motors = raw.get("motors")
    if isinstance(motors, dict):
        if motors.get("max_c") is not None:
            temps["servo_max"] = float(motors["max_c"])
        if motors.get("mean_c") is not None:
            temps["servo_mean"] = float(motors["mean_c"])
    degraded = bool(raw.get("degraded", False))
    if degraded:
        warnings.append("degraded")
    if raw.get("reason"):
        warnings.append(str(raw["reason"]))
    # v33: reported, never judged upstream. Same rule as CpuThrottle::throttled(): the governor
    # wound the level up, or something pinned the ceiling below the board's maximum.
    throttle = raw.get("cpu_throttle")
    if isinstance(throttle, dict):
        step, khz, max_khz = (int(throttle.get(k) or 0) for k in ("level", "khz", "max_khz"))
        if step > 0 or (max_khz > 0 and khz < max_khz):
            warnings.append("cpu_throttled")
    return Health(
        battery=level,
        temperatures_c=temps,
        ok=bool(raw.get("healthy", False)) and not degraded,
        warnings=warnings,
    )


NOT_STANDING_LABELS = frozenset({"sit", "limp_fall", "limp_pose"}) | upstream.TRANSITION_LABELS


def state_from_upstream(raw: dict[str, Any]) -> RobotState:
    """robot.state notification → RobotState."""
    joints = [float(j) for j in raw.get("joints") or []]
    if len(joints) != JOINT_COUNT:
        raise BackendError(f"robot.state carries {len(joints)} joints, expected {JOINT_COUNT}")
    safety = raw.get("safety") or {}
    fallen = bool(safety.get("fallen", False))
    limp = bool(safety.get("limp", False))
    policy = str(raw.get("policy", ""))
    sitting = policy == "sit"
    applied = (raw.get("move") or {}).get("applied") or [0.0, 0.0, 0.0]
    moving = any(abs(float(v)) > 1e-3 for v in applied)
    standing = not fallen and not limp and policy not in NOT_STANDING_LABELS
    # Projected gravity in the trunk frame (x forward, y left, z up), ≈ [0, 0, -1] upright.
    # Roll > 0 is right side down, pitch > 0 is nose down (REP-103), the same signs as
    # `robot.pose` {roll, pitch}. Verified 2026-09-22 on duck-sim 0.14.4 against the IMU quat
    # (docs/upstream-notes.md, "Roll and pitch"); the real duck's mounting is an M4 check.
    gx, gy, gz = (list(safety.get("gravity") or [0.0, 0.0, -1.0]) + [0.0, 0.0, 0.0])[:3]
    odom = raw.get("odom") or {}
    position = list(odom.get("position") or [0.0, 0.0, 0.0])
    yaw = float(odom.get("yaw", 0.0))
    return RobotState(
        timestamp=float(raw.get("t", 0.0)),
        joints=joints,
        imu=Imu(roll=math.atan2(-gy, -gz), pitch=math.atan2(gx, math.hypot(gy, gz)), yaw=yaw),
        flags=Flags(standing=standing, fallen=fallen, sitting=sitting, moving=moving),
        pose=Pose2D(x=float(position[0]), y=float(position[1]), heading=yaw),
    )


TOF_STATUS_VALID = {5, 9}  # ST VL53L8CX: 5 = valid, 9 = valid but merged; sim sends 5
TOF_NO_TARGET_M = 4.0  # the sensor's range; what a zone without a valid target reads as


def tof_from_upstream(raw: dict[str, Any], rows: int, cols: int) -> TofFrame:
    """tof.frame (millimetres + status byte, row-major) → TofFrame (metres, 8x8).

    A zone whose status is not "valid" (no target, or a failed measurement) reads as
    `TOF_NO_TARGET_M`, never as 0 m: the simulated sensor sends distance 0 with status 255
    for empty sky, and 0 m would trip every "too close" rule at once.
    """
    rows = int(raw.get("rows") or rows)
    cols = int(raw.get("cols") or cols)
    mm = raw.get("distance_mm") or []
    status = raw.get("status") or []
    if rows != TOF_SIZE or cols != TOF_SIZE or len(mm) != rows * cols:
        raise BackendError(f"unexpected ToF shape {rows}x{cols} with {len(mm)} values")

    def zone(i: int) -> float:
        if status and (i >= len(status) or int(status[i]) not in TOF_STATUS_VALID):
            return TOF_NO_TARGET_M
        d = float(mm[i]) / 1000.0
        return TOF_NO_TARGET_M if d <= 0.0 else d

    grid = [[zone(r * cols + c) for c in range(cols)] for r in range(rows)]
    return TofFrame(timestamp=float(raw.get("at_us", 0)) / 1e6, distances_m=grid)
