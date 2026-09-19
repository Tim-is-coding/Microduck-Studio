"""`duck` backend: the real Microduck. Milestone M4, testable once the hardware arrives.

Verified 2026-09-19 (docs/upstream-notes.md): the inbound WebSocket path for agents that the
handover assumed is a deferred design item upstream, not code. The real remote transports
are (a) `ssh -L` tunnels to the Unix sockets (what microduck-mcp does; suggested in upstream
robotd-design.md §4.3) and (b) the WebRTC `control` datachannel through mediad. Camera:
`GET http://<duck>:8080/frame` returns PNG. Which transport we pick is an M4 ADR.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from .. import upstream
from .base import Health, RobotState, TofFrame


class RealDuckBackend:
    kind = "duck"

    def __init__(self, *, url: str = "") -> None:
        self.url = url  # ssh host or WebRTC signalling URL, decided in M4
        self.connected = False

    async def connect(self) -> None:
        upstream.require_verified(
            upstream.HELLO, upstream.ROBOT_MOVE, upstream.ROBOT_HEALTH, upstream.ROBOT_STOP
        )
        raise NotImplementedError("duck backend lands in M4 (CLAUDE.md §8)")

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
        yield  # pragma: no cover

    async def intent(self, name: str, **params: float) -> None:
        raise NotImplementedError

    async def behavior(self, name: str) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        return None
