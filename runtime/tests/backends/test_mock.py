from __future__ import annotations

import math

from duckstudio import upstream
from duckstudio.backends.base import Pose2D
from duckstudio.backends.mock import ManualClock, MockBackend
from duckstudio.perception import MockBarDetector, fuse_distance


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


async def test_battery_charges_while_standing_still(mock: MockBackend) -> None:
    """A Studio left open overnight must not meet an empty practice duck in the morning."""
    mock.set_battery(0.0)
    mock.advance(12 * 3600.0)
    assert mock.battery == 1.0
    mock.set_battery(0.1)
    mock.advance(60.0)
    assert math.isclose(mock.battery, 0.2, abs_tol=1e-9)


async def test_camera_shows_the_person_where_she_is(mock: MockBackend) -> None:
    """The rendered room puts the fake person where the world has her: the local detector
    reads the true bearing and range off the picture, and loses her when the duck turns."""
    detector = MockBarDetector()
    mock.person_xy = (1.0, 0.8)
    mock.pose = Pose2D(x=-2.0, y=0.0, heading=0.0)
    seen = detector.detect(await mock.frame())
    assert seen is not None and seen.distance_m is not None
    assert math.isclose(seen.bearing_rad, math.atan2(0.8, 3.0), abs_tol=math.radians(0.5))
    assert math.isclose(seen.distance_m, math.hypot(0.8, 3.0), rel_tol=0.05)
    mock.pose = Pose2D(x=-2.0, y=0.0, heading=2.0)
    assert detector.detect(await mock.frame()) is None


async def test_a_fixed_frame_still_wins(clock: ManualClock) -> None:
    b = MockBackend(clock=clock, frame=b"picture")
    await b.connect()
    assert await b.frame() == b"picture"


async def test_perception_reads_the_tof_range_of_a_person_dead_ahead(mock: MockBackend) -> None:
    """The ToF zones and the camera agree: straight ahead used to fall between two zones."""
    seen = MockBarDetector().detect(await mock.frame())
    assert seen is not None
    fused = fuse_distance(seen, mock.tof_frame().distances_m)
    assert fused.distance_m == 1.0
