"""One contract for all backends (§6.3). `sim` and `duck` skip until they exist / are reachable."""

from __future__ import annotations

import os

import pytest

from duckstudio import upstream
from duckstudio.backends import make_backend
from duckstudio.backends.base import (
    JOINT_COUNT,
    TOF_SIZE,
    DuckBackend,
    Health,
    RobotState,
    TofFrame,
    UnknownBehavior,
    UnknownIntent,
)

KINDS = ["mock", "sim", "duck"]


@pytest.fixture(params=KINDS)
async def backend(request: pytest.FixtureRequest):
    kind = request.param
    if kind == "sim" and not os.environ.get("DUCKSTUDIO_SIM"):
        pytest.skip("set DUCKSTUDIO_SIM=1 with duck-sim running (M1)")
    if kind == "duck" and not os.environ.get("DUCKSTUDIO_DUCK_URL"):
        pytest.skip("set DUCKSTUDIO_DUCK_URL to a reachable duck (M4)")
    b = make_backend(kind)
    try:
        await b.connect()
    except NotImplementedError as e:
        pytest.skip(f"{kind}: {e}")
    yield b
    await b.close()


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
    data = await backend.frame()
    is_jpeg = data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"
    is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
    assert is_jpeg or is_png, "frame must be JPEG (mock) or PNG (mediad GET /frame)"


async def test_tof_is_8x8(backend: DuckBackend) -> None:
    frame = await anext(backend.tof())
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
async def test_named_behaviors_accepted(backend: DuckBackend, name: str) -> None:
    await backend.behavior(name)


async def test_unknown_behavior_rejected(backend: DuckBackend) -> None:
    with pytest.raises(UnknownBehavior):
        await backend.behavior("moonwalk")


async def test_stop_halts_motion(backend: DuckBackend) -> None:
    await backend.intent(upstream.ROBOT_MOVE.name, vx=0.1, vy=0.0, vyaw=0.0)
    await backend.stop()
    s = await backend.state()
    assert s.flags.moving is False


@pytest.mark.parametrize("kind", KINDS)
async def test_stop_never_raises_even_before_connect(kind: str) -> None:
    """§7: stop() bypasses every check, including 'are we connected'."""
    b = make_backend(kind)
    await b.stop()
