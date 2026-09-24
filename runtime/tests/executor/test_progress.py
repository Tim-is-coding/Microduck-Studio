"""The duck is told to walk and does not get anywhere (duck-sim, microduck_rl#46): say so."""

from __future__ import annotations

from duckstudio.backends.base import Pose2D
from duckstudio.executor.progress import WINDOW_S, ProgressWatch

from .conftest import Harness

HERE = Pose2D(x=0.0, y=0.0, heading=0.0)
WALK = {"vx": 0.08, "vy": 0.0, "vyaw": 0.0}


def run(watch: ProgressWatch, poses: list[Pose2D], command: dict[str, float] | None, dt=0.1):
    changes = []
    for i, pose in enumerate(poses):
        change = watch.observe(i * dt, pose, command)
        if change:
            changes.append((round(i * dt, 1), change))
    return changes


def test_walking_on_the_spot_is_stuck_once() -> None:
    watch = ProgressWatch()
    changes = run(watch, [HERE] * 100, WALK)  # 10 s, not a millimetre
    assert changes == [(WINDOW_S, "stuck")]
    assert watch.stuck


def test_a_duck_that_walks_is_not_stuck() -> None:
    poses = [Pose2D(x=0.08 * 0.1 * i, y=0.0, heading=0.0) for i in range(100)]
    assert run(ProgressWatch(), poses, WALK) == []


def test_turning_counts_as_progress() -> None:
    poses = [Pose2D(x=0.0, y=0.0, heading=0.5 * 0.1 * i) for i in range(100)]
    assert run(ProgressWatch(), poses, {"vx": 0.0, "vy": 0.0, "vyaw": 0.5}) == []


def test_getting_going_again_is_said() -> None:
    watch = ProgressWatch()
    stuck = [HERE] * 40
    going = [Pose2D(x=0.08 * 0.1 * i, y=0.0, heading=0.0) for i in range(40)]
    assert [c for _, c in run(watch, stuck + going, WALK)] == ["stuck", "moving"]


def test_standing_still_on_purpose_is_no_verdict() -> None:
    watch = ProgressWatch()
    assert run(watch, [HERE] * 100, None) == []
    assert run(watch, [HERE] * 100, {"vx": 0.0, "vy": 0.0, "vyaw": 0.0}) == []
    # a crawl too slow to judge in one window says nothing either
    assert run(watch, [HERE] * 100, {"vx": 0.01, "vy": 0.0, "vyaw": 0.0}) == []


def test_no_odometry_no_verdict() -> None:
    assert run(ProgressWatch(), [None] * 100, WALK) == []  # type: ignore[list-item]


async def test_follow_me_says_the_duck_is_stepping_in_place(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    for _ in range(50):  # 5 s of walking that goes nowhere
        h.mock.pose = HERE
        h.see_person(distance=2.0)
        await h.tick()
    assert "progress.stuck" in h.kinds()
    assert any("tritt auf der Stelle" in t for t in h.texts())
    assert h.executor.status()["stuck"] is True
    assert h.executor.state == "running", "a hint, not a failure"


async def test_follow_me_on_a_walking_duck_says_nothing(h: Harness) -> None:
    h.see_person(distance=2.0)
    await h.start()
    for _ in range(50):
        h.see_person(distance=2.0)
        await h.tick()
    assert "progress.stuck" not in h.kinds()
    assert h.executor.status()["stuck"] is False
