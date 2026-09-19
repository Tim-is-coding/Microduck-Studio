"""`sim` backend: the real upstream daemons started by `scripts/duck-sim` (MuJoCo body).

Verified layout (docs/upstream-notes.md, "duck-sim"): JSON-RPC/NDJSON over Unix sockets under
`~/.cache/duck-sim/` (`DUCK_SIM_STATE`): `duck-a.sock` (robotd), `duck-a-tof.sock` (tofd);
mediad's console at `http://127.0.0.1:8080` serves `GET /frame` (PNG) when the duck has a
camera (`DUCK_SIM_CAMERAS=a`). Start it with `sim/up.sh`.
"""

from __future__ import annotations

import os

from .. import upstream
from .ipc_backend import IpcBackend


class SimBackend(IpcBackend):
    kind = "sim"

    def __init__(
        self,
        *,
        socket_dir: str | None = None,
        duck: str = upstream.SIM_DEFAULT_DUCK,
        console_url: str | None = upstream.SIM_CONSOLE_URL,
        state_hz: int = 10,
    ) -> None:
        state = os.path.expanduser(
            socket_dir or os.environ.get("DUCK_SIM_STATE", upstream.SIM_STATE_DIR)
        )
        self.socket_dir = state
        self.duck = duck
        super().__init__(
            robot_socket=os.path.join(state, upstream.SIM_SOCKETS["robot"].format(duck=duck)),
            tof_socket=os.path.join(state, upstream.SIM_SOCKETS["tof"].format(duck=duck)),
            console_url=console_url,
            state_hz=state_hz,
        )
