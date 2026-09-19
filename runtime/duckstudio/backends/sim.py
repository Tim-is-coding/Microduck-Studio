"""`sim` backend: the real upstream daemons started by `scripts/duck-sim` (MuJoCo body).
Milestone M1.

Verified transport (docs/upstream-notes.md, microduck@344925c): plain JSON-RPC 2.0 NDJSON over
Unix sockets under `~/.cache/duck-sim/` (`duck-a.sock` robotd, `duck-a-tof.sock` tofd,
`duck-a-frame.sock` mediad), console `http://127.0.0.1:8080` with `GET /frame` (PNG).
Streams (`robot.subscribe`, `tof.stream`) own their connection: one socket per stream,
another for request/response calls. `robot.move` is a notification resent at 10 Hz
(deadman 500 ms). Not implemented yet; the contract test skips it until it is.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from .. import upstream
from .base import Health, RobotState, TofFrame


class SimBackend:
    kind = "sim"

    def __init__(
        self,
        *,
        socket_dir: str | None = None,
        console_url: str = upstream.SIM_CONSOLE_URL,
    ) -> None:
        self.socket_dir = os.path.expanduser(
            socket_dir or os.environ.get("DUCK_SIM_STATE", upstream.SIM_STATE_DIR)
        )
        self.console_url = console_url
        self.connected = False

    def socket_path(self, which: str) -> str:
        return os.path.join(self.socket_dir, upstream.SIM_SOCKETS[which])

    async def connect(self) -> None:
        upstream.require_verified(
            upstream.HELLO,
            upstream.ROBOT_MOVE,
            upstream.ROBOT_HEALTH,
            upstream.ROBOT_SUBSCRIBE,
            upstream.ROBOT_STOP,
            upstream.ROBOT_DO,
            upstream.ROBOT_SOUND,
            upstream.TOF_STREAM,
        )
        raise NotImplementedError("sim backend lands in M1 (CLAUDE.md §8)")

    async def close(self) -> None:
        self.connected = False

    async def health(self) -> Health:
        raise NotImplementedError

    async def state(self) -> RobotState:
        raise NotImplementedError

    async def frame(self) -> bytes:
        raise NotImplementedError

    async def tof(self) -> AsyncIterator[TofFrame]:
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator

    async def intent(self, name: str, **params: float) -> None:
        raise NotImplementedError

    async def behavior(self, name: str) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        # Must never raise (§7). Nothing is connected yet, so nothing to stop.
        return None
