"""`duck` backend: the real Microduck over an SSH tunnel (M4, ADR-0006).

The duck runs the same daemons as duck-sim, on the same wire format, behind the same Unix
sockets (`docs/upstream-notes.md`: `/run/robotd.sock`, `/run/tofd/tof.sock`,
`/run/padd/pad.sock`, mediad's console on `:8080`). What is missing between us and them is
transport: upstream's WebSocket path for agents is a design note, not code (verified
2026-09-19), so the way in is `ssh -L`, forwarding those sockets to local ones.

That is the whole trick: with the sockets forwarded, the duck *is* an `IpcBackend` — the
same class the simulator uses, the same contract tests, the same clamps. This class only
knows where the local ends of the tunnel are and says something useful when they are missing.

`scripts/duck-tunnel.sh <host>` opens the tunnel; the runtime never spawns ssh itself, so a
behavior can never start a process on someone's laptop.
"""

from __future__ import annotations

import os

from .. import upstream
from .base import BackendError
from .ipc_backend import IpcBackend

# Where `scripts/duck-tunnel.sh` puts the local ends. One directory per duck, so two ducks
# never share a socket name.
DEFAULT_TUNNEL_DIR = "~/.cache/duckstudio/tunnel"
DEFAULT_CONSOLE_URL = "http://127.0.0.1:8080"

LOCAL_SOCKETS = {"robot": "robotd.sock", "tof": "tof.sock", "pad": "pad.sock"}

# `console_url=None` means "this duck has no camera, or the port is not forwarded", which is
# a different thing from "not given, take it from the environment".
FROM_ENV = "<from-env>"


class RealDuckBackend(IpcBackend):
    kind = "duck"

    def __init__(
        self,
        *,
        tunnel_dir: str | None = None,
        console_url: str | None = FROM_ENV,
        state_hz: int = 10,
        url: str = "",  # kept for the factory's old signature; a host name, informational
    ) -> None:
        directory = os.path.expanduser(
            tunnel_dir or os.environ.get("DUCKSTUDIO_DUCK_TUNNEL") or DEFAULT_TUNNEL_DIR
        )
        self.tunnel_dir = directory
        self.host = url or os.environ.get("DUCKSTUDIO_DUCK_HOST", "")
        console = (
            os.environ.get("DUCKSTUDIO_DUCK_CONSOLE", DEFAULT_CONSOLE_URL)
            if console_url == FROM_ENV
            else console_url
        )
        super().__init__(
            robot_socket=os.path.join(directory, LOCAL_SOCKETS["robot"]),
            tof_socket=os.path.join(directory, LOCAL_SOCKETS["tof"]),
            pad_socket=os.path.join(directory, LOCAL_SOCKETS["pad"]),
            console_url=console or None,
            state_hz=state_hz,
        )

    def tunnel_is_up(self) -> bool:
        """Is the local end of the tunnel there? Checked before connecting, so the error
        names the missing tunnel instead of a refused connection."""
        return os.path.exists(self.robot_socket)

    async def connect(self) -> None:
        upstream.require_verified(
            upstream.HELLO, upstream.ROBOT_MOVE, upstream.ROBOT_HEALTH, upstream.ROBOT_STOP
        )
        if not self.tunnel_is_up():
            host = self.host or "<duck>"
            raise BackendError(
                f"no tunnel at {self.robot_socket}: run scripts/duck-tunnel.sh {host}"
            )
        await super().connect()
