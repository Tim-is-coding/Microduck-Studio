# Backend interface

`runtime/duckstudio/backends/base.py` defines `DuckBackend`, the only way the executor
touches a duck. Three implementations, one contract test suite
(`runtime/tests/backends/test_contract.py`):

| Kind | Talks to | Status |
| --- | --- | --- |
| `mock` | nothing; deterministic world model, injectable clock | M0, done |
| `sim` | upstream daemons from `duck-sim` over Unix sockets | M1 |
| `duck` | the robot's own sockets, forwarded by `ssh -L` (ADR-0006) | M4: code and contract tests done, hardware pending |

```python
class DuckBackend(Protocol):
    kind: str
    async def connect(self) -> None
    async def close(self) -> None
    async def health(self) -> Health          # battery 0..1, temperatures_c, ok, warnings
    async def state(self) -> RobotState       # 15 joints, imu, flags, optional pose
    async def frame(self) -> bytes            # one JPEG
    def tof(self) -> AsyncIterator[TofFrame]  # 8x8 distances in metres
    async def intent(self, name, **params)    # robot.* intent; NOT gated here
    async def behavior(self, name)            # sit | stand | getup | pickup | kick | quack
    async def stop(self)                      # never gated, never raises
```

Rules every backend must honour:

- No joint-level or servo-level methods exist on the protocol, and none may be added
  (`CLAUDE.md` §7). Tests assert this.
- `stop()` works before `connect()` and never raises.
- Backends do not clamp, gate or rate-limit. That is the `IntentGate`'s job
  (`runtime/duckstudio/executor/safety.py`), so it is tested once and cannot drift between
  backends.
- `sim` and `duck` refuse to connect while any upstream method they need is unverified
  (`upstream.require_verified`).

## Mock specifics

`MockBackend(clock=ManualClock())` moves only when a test calls `advance(dt)`; the API
server uses `time.monotonic`. The mock keeps a 2-D pose, a fake person at `person_xy`
visible in the ToF grid, a battery that drains faster while walking, and `push_over()` to
simulate a shove for fall-recovery tests. Every call is recorded in `calls`.
