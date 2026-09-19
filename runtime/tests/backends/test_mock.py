from __future__ import annotations

import math

from duckstudio import upstream
from duckstudio.backends.mock import ManualClock, MockBackend


async def test_deterministic_walk(mock: MockBackend, clock: ManualClock) -> None:
    await mock.intent(upstream.ROBOT_MOVE.name, vx=0.1, vy=0.0, vyaw=0.0)
    mock.advance(2.0)
    s = await mock.state()
    assert s.pose is not None
    assert math.isclose(s.pose.x, 0.2, abs_tol=1e-9)
    assert s.flags.moving is True


async def test_nothing_moves_without_time(mock: MockBackend) -> None:
    await mock.intent(upstream.ROBOT_MOVE.name, vx=0.1)
    s = await mock.state()
    assert s.pose is not None and s.pose.x == 0.0


async def test_tof_sees_the_fake_person(mock: MockBackend) -> None:
    frame = mock.tof_frame()
    assert math.isclose(frame.min_distance, 1.0, abs_tol=1e-6)
    mock.pose = mock.pose.model_copy(update={"heading": math.pi})  # turn away
    assert mock.tof_frame().min_distance == MockBackend.TOF_MAX_M


async def test_push_over_and_getup(mock: MockBackend) -> None:
    mock.push_over()
    assert (await mock.state()).flags.fallen is True
    await mock.intent(upstream.ROBOT_MOVE.name, vx=0.1)
    mock.advance(1.0)
    assert (await mock.state()).pose.x == 0.0, "a fallen duck must not walk"
    await mock.behavior("getup")
    assert (await mock.state()).flags.standing is True


async def test_battery_drains_while_walking(mock: MockBackend) -> None:
    start = mock.battery
    await mock.intent(upstream.ROBOT_MOVE.name, vx=0.1)
    mock.advance(60.0)
    assert mock.battery < start
