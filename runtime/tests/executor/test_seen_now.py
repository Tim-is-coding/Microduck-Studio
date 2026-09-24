"""A model's answer is old by the time the duck steers by it (§4): make up for the walk since."""

from __future__ import annotations

import math

import pytest

from duckstudio.backends.base import Flags, Imu, Pose2D, RobotState
from duckstudio.common import Condition, Text
from duckstudio.executor.conditions import Snapshot, evaluate
from duckstudio.perception.base import PersonDetection, TargetSighting


def target(bearing: float, distance: float | None, seen_from=(0.0, 0.0, 0.0)) -> TargetSighting:
    return TargetSighting(
        timestamp=10.0,
        bearing_rad=bearing,
        distance_m=distance,
        pixel_x=100.0,
        pixel_y=100.0,
        frame_width=360,
        frame_height=640,
        label=Text(de="Ball"),
        source="google",
        seen_from=seen_from,
    )


def at(x: float, y: float, heading: float) -> RobotState:
    return RobotState(
        timestamp=11.0,
        joints=[0.0] * 15,
        imu=Imu(roll=0.0, pitch=0.0, yaw=heading),
        flags=Flags(standing=True, fallen=False, sitting=False, moving=True),
        pose=Pose2D(x=x, y=y, heading=heading),
    )


def test_turned_towards_it_means_it_is_ahead_now() -> None:
    now = target(0.3, 2.0).seen_now(0.0, 0.0, 0.3)
    assert now.bearing_rad == pytest.approx(0.0, abs=1e-9)
    assert now.distance_m == pytest.approx(2.0)


def test_walked_towards_it_means_it_is_closer() -> None:
    now = target(0.0, 2.0).seen_now(0.5, 0.0, 0.0)
    assert now.distance_m == pytest.approx(1.5) and now.bearing_rad == pytest.approx(0.0)


def test_passed_it_on_the_left_means_it_is_behind_on_the_left() -> None:
    now = target(math.radians(30), 1.0).seen_now(1.0, 0.0, 0.0)
    assert now.bearing_rad > math.radians(90), "left and behind"


def test_without_a_range_only_the_turn_is_made_up_for() -> None:
    now = target(0.3, None).seen_now(5.0, 5.0, 0.1)
    assert now.bearing_rad == pytest.approx(0.2) and now.distance_m is None


def test_without_odometry_nothing_changes() -> None:
    t = target(0.3, 2.0, seen_from=None)
    assert t.seen_now(1.0, 1.0, 1.0) is t


def test_the_executor_steers_and_stops_by_where_the_thing_is_now() -> None:
    snap = Snapshot(now=11.0, steering="target", stop_distance_m=0.5)
    snap.target = target(0.3, 1.0)
    snap.state = at(0.0, 0.0, 0.0)
    assert snap.subject.bearing_rad == pytest.approx(0.3)
    reached = Condition.parse("target_reached")
    assert evaluate(reached, snap) is False
    # the duck turned and walked 60 cm towards it; the answer has not changed
    snap.state = at(0.6 * math.cos(0.3), 0.6 * math.sin(0.3), 0.3)
    assert snap.subject.bearing_rad == pytest.approx(0.0, abs=1e-6)
    assert snap.subject.distance_m == pytest.approx(0.4, abs=1e-6)
    assert evaluate(reached, snap) is True, "the old answer alone would walk it past"


def test_the_person_is_seen_now_too() -> None:
    snap = Snapshot(now=10.5, steering="person")
    snap.person = PersonDetection(
        timestamp=10.0,
        bearing_rad=0.2,
        distance_m=None,
        pixel_x=1,
        pixel_y=1,
        frame_width=360,
        frame_height=640,
        seen_from=(0.0, 0.0, 0.0),
    )
    snap.state = at(0.0, 0.0, 0.2)
    assert snap.subject.bearing_rad == pytest.approx(0.0, abs=1e-9)
