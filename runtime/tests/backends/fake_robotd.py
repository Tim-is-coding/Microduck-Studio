"""An in-memory robotd + tofd that speak the verified wire format (docs/upstream-notes.md).

This is a protocol double, not a physics simulation: it exists so the `sim` backend's contract
runs in CI without MuJoCo. Every params struct upstream is `deny_unknown_fields`, so this
fake refuses unknown members too (-32602 on requests; notifications with bad params are
recorded in `invalid`). The truth is still duck-sim: run `DUCKSTUDIO_SIM=1 pytest` against it.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

API_VERSION = 31
SOUND_TAGS = {"alarm", "greet", "inquire", "peck", "chirp", "coo", "wheee"}
PARAMS: dict[str, set[str]] = {
    "hello": {"api_version"},
    "robot.move": {"vx", "vy", "vyaw"},
    "robot.head": {"neck_pitch", "head_pitch", "head_yaw", "head_roll"},
    "robot.look": {"x", "y", "z", "neck_pitch"},
    "robot.pose": {"z", "roll", "pitch", "active"},
    "robot.do": {"skill"},
    "robot.sound": {"tag", "hold"},
    "robot.enable": {"on", "toggle"},
    "robot.subscribe": {"hz"},
}


def short_tmp_dir() -> Path:
    """Unix socket paths are capped at ~104 bytes on macOS; pytest's tmp_path is too long."""
    return Path(tempfile.mkdtemp(prefix="ds-", dir="/tmp"))


class FakeDuck:
    def __init__(
        self,
        directory: Path,
        *,
        duck: str = "duck-a",
        battery_percent: float | None = 87.0,
        skills: tuple[str, ...] = ("ground_pick", "sit_toggle", "kick_right"),
        tof: bool = True,
    ) -> None:
        self.dir = directory
        self.robot_socket = directory / f"{duck}.sock"
        self.tof_socket = directory / f"{duck}-tof.sock"
        self.battery_percent = battery_percent
        self.skills = list(skills)
        self.has_tof = tof
        # robot state
        self.twist = [0.0, 0.0, 0.0]
        self.policy = "stand"
        self.fallen = False
        self.limp = False
        self.sitting = False
        self.enabled = True
        self.position = [0.0, 0.0, 0.0]
        self.yaw = 0.0
        self._t0 = time.monotonic()
        # what clients sent
        self.received: list[dict[str, Any]] = []
        self.invalid: list[dict[str, Any]] = []
        self._servers: list[asyncio.base_events.Server] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self._servers.append(
            await asyncio.start_unix_server(self._serve_robot, path=str(self.robot_socket))
        )
        if self.has_tof:
            self._servers.append(
                await asyncio.start_unix_server(self._serve_tof, path=str(self.tof_socket))
            )

    async def stop(self) -> None:
        """Close listening sockets AND every accepted connection: Python 3.12's
        `Server.wait_closed()` waits for active connections, so they must go first."""
        for t in list(self._tasks):
            t.cancel()
        for w in list(self._writers):
            w.close()
        for s in self._servers:
            s.close()
            await s.wait_closed()
        self._servers.clear()
        self._writers.clear()

    # -- helpers ------------------------------------------------------------------------

    def push_over(self) -> None:
        self.fallen = True
        self.policy = "limp_fall"
        self.twist = [0.0, 0.0, 0.0]

    def state_payload(self) -> dict[str, Any]:
        t = time.monotonic() - self._t0
        return {
            "t": t,
            "move": {"requested": list(self.twist), "applied": list(self.twist), "limited_by": []},
            "head": [0.0, 0.0, 0.0, 0.0],
            "policy": self.policy,
            "safety": {
                "fallen": self.fallen,
                "limp": self.limp,
                "gravity": [0.0, 0.0, -9.81],
                "gain": None,
            },
            "loop": {"hz": 50.0, "missed": 0},
            "joints": [0.0] * 15,
            "targets": [0.0] * 15,
            "odom": {"position": list(self.position), "yaw": self.yaw},
            "t_ns": int(t * 1e9),
            "imu": {"gyro": [0.0, 0.0, 0.0], "quat": [1.0, 0.0, 0.0, 0.0]},
        }

    # -- robotd -------------------------------------------------------------------------

    async def _serve_robot(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        stream: asyncio.Task[None] | None = None
        self._writers.add(writer)
        try:
            while line := await reader.readline():
                msg = json.loads(line)
                self.received.append(msg)
                rid = msg.get("id")
                method = msg.get("method")
                params = msg.get("params") or {}
                if method in PARAMS and (unknown := set(params) - PARAMS[method]):
                    if rid is None:
                        self.invalid.append(msg)
                        continue
                    _write(writer, _error(rid, -32602, f"unknown field `{sorted(unknown)[0]}`"))
                    continue
                result: Any
                match method:
                    case "hello":
                        result = {
                            "api_version": API_VERSION,
                            "daemon_version": "0.14.1",
                            "revision": None,
                        }
                    case "robot.health":
                        result = {
                            "healthy": True,
                            "motors": {"hottest": "left_knee", "max_c": 41.0, "mean_c": 38.5},
                        }
                        if self.battery_percent is not None:
                            result["battery"] = {"volts": 7.8, "percent": self.battery_percent}
                    case "robot.subscribe":
                        result = {
                            "accepted": True,
                            "walk": "alpha_walking.onnx",
                            "stand": "alpha_stand.onnx",
                            "skills": self.skills,
                        }
                        stream = asyncio.create_task(
                            self._push_state(writer, float(params.get("hz") or 50))
                        )
                        self._tasks.add(stream)
                    case "robot.move":
                        if not self.fallen and self.enabled:
                            self.twist = [
                                float(params.get("vx", 0)),
                                float(params.get("vy", 0)),
                                float(params.get("vyaw", 0)),
                            ]
                        if rid is None:
                            continue
                        result = {"accepted": True}
                    case "robot.head" | "robot.pose":
                        if rid is None:
                            continue
                        result = {"accepted": True}
                    case "robot.look":
                        result = {
                            "head": {
                                "neck_pitch": 0.0,
                                "head_pitch": -0.1,
                                "head_yaw": 0.2,
                                "head_roll": 0.0,
                            },
                            "clamped": False,
                        }
                    case "robot.stop":
                        self.twist = [0.0, 0.0, 0.0]
                        result = {"accepted": True}
                    case "robot.do":
                        skill = params.get("skill")
                        if skill not in self.skills:
                            result = {
                                "accepted": False,
                                "reason": f"unknown skill {skill!r}; the robot knows {self.skills}",
                            }
                        else:
                            if skill == "sit_toggle":
                                self.sitting = not self.sitting
                                self.policy = "sit" if self.sitting else "stand"
                            result = {"accepted": True}
                    case "robot.sound":
                        if params.get("tag") not in SOUND_TAGS:
                            _write(
                                writer,
                                _error(rid, -32602, f"unknown variant `{params.get('tag')}`"),
                            )
                            continue
                        result = {"accepted": True}
                    case "robot.enable":
                        self.enabled = bool(params.get("on", True))
                        if self.enabled and self.fallen:
                            self.fallen = False  # velstand recovers once enabled
                            self.policy = "stand"
                        result = {"accepted": True}
                    case "robot.policies":
                        result = {
                            "mode": "walk",
                            "enabled": self.enabled,
                            "slots": [{"slot": "walk", "path": "alpha_walking.onnx"}],
                            "skills": self.skills,
                            "homed": True,
                            "sitting": self.sitting,
                        }
                    case _:
                        if rid is not None:
                            _write(writer, _error(rid, -32601, f"unknown method `{method}`"))
                        continue
                if rid is not None:
                    _write(writer, {"jsonrpc": "2.0", "id": rid, "result": result})
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            if stream is not None:
                stream.cancel()
            self._writers.discard(writer)
            writer.close()

    async def _push_state(self, writer: asyncio.StreamWriter, hz: float) -> None:
        try:
            while True:
                await asyncio.sleep(1.0 / hz)
                _write(
                    writer,
                    {"jsonrpc": "2.0", "method": "robot.state", "params": self.state_payload()},
                )
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass

    # -- tofd ---------------------------------------------------------------------------

    async def _serve_tof(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while line := await reader.readline():
                msg = json.loads(line)
                self.received.append(msg)
                rid = msg.get("id")
                match msg.get("method"):
                    case "tof.stream":
                        _write(
                            writer,
                            {
                                "jsonrpc": "2.0",
                                "id": rid,
                                "result": {
                                    "accepted": True,
                                    "sensor": "VL53L8CX",
                                    "rows": 8,
                                    "cols": 8,
                                    "hz": 15,
                                },
                            },
                        )
                        seq = 0
                        while True:
                            await asyncio.sleep(1 / 15)
                            seq += 1
                            mm = [2000] * 64
                            for r in range(2, 7):
                                mm[r * 8 + 3] = 1000  # something one metre ahead, slightly left
                            _write(
                                writer,
                                {
                                    "jsonrpc": "2.0",
                                    "method": "tof.frame",
                                    "params": {
                                        "seq": seq,
                                        "at_us": int(time.time() * 1e6),
                                        "t_ns": 0,
                                        "rows": 8,
                                        "cols": 8,
                                        "distance_mm": mm,
                                        "status": [5] * 64,
                                    },
                                },
                            )
                            await writer.drain()
                    case _:  # the real tofd refuses even `hello` this way
                        _write(
                            writer,
                            _error(
                                rid,
                                -32601,
                                "tofd serves tof.stream and head_imu.stream and nothing else",
                            ),
                        )
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()


def _write(writer: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    writer.write(json.dumps(obj, separators=(",", ":")).encode() + b"\n")


def _error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}
