"""One contract for all backends (§6.3).

`sim` runs against the fake daemon in CI and against real duck-sim with `DUCKSTUDIO_SIM=1`
(start it with `sim/up.sh`). `duck` runs against the same fake daemon through the socket
layout `scripts/duck-tunnel.sh` creates (ADR-0006) — everything but the ssh hop — and against
a real duck when `DUCKSTUDIO_DUCK_TUNNEL` points at a live tunnel.
"""

from __future__ import annotations

import asyncio
import os
import shutil

import pytest

from duckstudio import upstream
from duckstudio.backends import make_backend
from duckstudio.backends.base import (
    JOINT_COUNT,
    TOF_SIZE,
    BehaviorRefused,
    DuckBackend,
    Health,
    NoCamera,
    RobotState,
    TofFrame,
    UnknownBehavior,
    UnknownIntent,
)
from duckstudio.backends.duck import LOCAL_SOCKETS, RealDuckBackend
from duckstudio.backends.sim import SimBackend

from .fake_robotd import FakeDuck, short_tmp_dir

KINDS = ["mock", "sim", "duck"]


@pytest.fixture(params=KINDS)
async def backend(request: pytest.FixtureRequest):
    kind = request.param
    fake: FakeDuck | None = None
    if kind == "sim" and not os.environ.get("DUCKSTUDIO_SIM"):
        fake = FakeDuck(short_tmp_dir())
        await fake.start()
        b: DuckBackend = SimBackend(socket_dir=str(fake.dir), console_url=None)
    elif kind == "duck" and not os.environ.get("DUCKSTUDIO_DUCK_TUNNEL"):
        # The duck backend is an IpcBackend pointed at the far end of an ssh tunnel. Give it
        # the same socket names the tunnel script creates, with the double behind them: the
        # only untested step is ssh itself.
        fake = FakeDuck(short_tmp_dir(), duck="tunnel")
        await fake.start()
        for name, target in (
            (LOCAL_SOCKETS["robot"], fake.robot_socket),
            (LOCAL_SOCKETS["tof"], fake.tof_socket),
        ):
            (fake.dir / name).symlink_to(target)
        b = RealDuckBackend(tunnel_dir=str(fake.dir), console_url=None)
    else:
        b = make_backend(kind)
    try:
        await b.connect()
    except NotImplementedError as e:
        pytest.skip(f"{kind}: {e}")
    try:
        yield b
    finally:
        await b.close()
        if fake is not None:
            await fake.stop()
            shutil.rmtree(fake.dir, ignore_errors=True)


async def test_satisfies_protocol(backend: DuckBackend) -> None:
    assert isinstance(backend, DuckBackend)
    assert backend.kind in KINDS


async def test_health(backend: DuckBackend) -> None:
    h = await backend.health()
    assert isinstance(h, Health)
    assert 0.0 <= h.battery <= 1.0


async def test_state(backend: DuckBackend) -> None:
    s = await backend.state()
    assert isinstance(s, RobotState)
    assert len(s.joints) == JOINT_COUNT
    assert isinstance(s.flags.standing, bool)


async def test_frame_is_an_encoded_image(backend: DuckBackend) -> None:
    try:
        data = await backend.frame()
    except NoCamera as e:
        pytest.skip(f"{backend.kind}: {e}")
    is_jpeg = data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
    assert is_jpeg or is_png, "frame must be JPEG (mock) or PNG (mediad GET /frame)"


async def test_tof_is_8x8(backend: DuckBackend) -> None:
    stream = backend.tof()
    try:
        frame = await asyncio.wait_for(anext(stream), 3.0)
    finally:
        await stream.aclose()
    assert isinstance(frame, TofFrame)
    assert len(frame.distances_m) == TOF_SIZE
    assert all(len(r) == TOF_SIZE for r in frame.distances_m)
    assert frame.min_distance >= 0.0


async def test_walk_intent_accepted(backend: DuckBackend) -> None:
    await backend.intent(upstream.ROBOT_MOVE.name, vx=0.05, vy=0.0, vyaw=0.0)


async def test_unknown_intent_rejected(backend: DuckBackend) -> None:
    with pytest.raises(UnknownIntent):
        await backend.intent("robot.does_not_exist", vx=0.0)


@pytest.mark.parametrize("name", sorted(upstream.BEHAVIORS))
async def test_named_behaviors_are_understood(backend: DuckBackend, name: str) -> None:
    """Every name in our vocabulary maps to an upstream call. The robot may still say no."""
    try:
        await backend.behavior(name)
    except BehaviorRefused:
        pass


async def test_unknown_behavior_rejected(backend: DuckBackend) -> None:
    with pytest.raises(UnknownBehavior):
        await backend.behavior("moonwalk")


async def test_stop_halts_motion(backend: DuckBackend) -> None:
    await backend.intent(upstream.ROBOT_MOVE.name, vx=0.1, vy=0.0, vyaw=0.0)
    await backend.stop()
    for _ in range(40):  # the state stream needs a tick or two to reflect it
        s = await backend.state()
        if not s.flags.moving:
            return
        await asyncio.sleep(0.05)
    pytest.fail("still moving 2 s after stop()")


@pytest.mark.parametrize("kind", KINDS)
async def test_stop_never_raises_even_before_connect(kind: str) -> None:
    """§7: stop() bypasses every check, including 'are we connected'."""
    b = make_backend(kind)
    await b.stop()
