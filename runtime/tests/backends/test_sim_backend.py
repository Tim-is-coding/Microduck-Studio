"""`SimBackend` mapping and behavior against the fake daemon (wire shapes from upstream-notes)."""

from __future__ import annotations

import asyncio
import shutil

import pytest

from duckstudio import upstream
from duckstudio.backends.base import BackendError, BehaviorRefused, NoCamera, NotConnected
from duckstudio.backends.ipc_backend import (
    health_from_upstream,
    state_from_upstream,
    tof_from_upstream,
)
from duckstudio.backends.sim import SimBackend

from .fake_robotd import FakeDuck, short_tmp_dir


@pytest.fixture
async def fake():
    duck = FakeDuck(short_tmp_dir())
    await duck.start()
    try:
        yield duck
    finally:
        await duck.stop()
        shutil.rmtree(duck.dir, ignore_errors=True)


@pytest.fixture
async def sim(fake: FakeDuck):
    b = SimBackend(socket_dir=str(fake.dir), console_url=None)
    await b.connect()
    try:
        yield b
    finally:
        await b.close()


async def test_connect_uses_three_connections_and_subscribes(
    sim: SimBackend, fake: FakeDuck
) -> None:
    hellos = [m for m in fake.received if m.get("method") == "hello"]
    assert len(hellos) == 3
    sub = next(m for m in fake.received if m.get("method") == "robot.subscribe")
    assert sub["params"] == {"hz": 10}
    assert sim.hello is not None and sim.hello["api_version"] == upstream.API_VERSION


async def test_battery_percent_becomes_fraction(sim: SimBackend, fake: FakeDuck) -> None:
    assert (await sim.health()).battery == pytest.approx(0.87)
    fake.battery_percent = None
    h = await sim.health()
    assert h.battery == 1.0 and "battery_not_reported" in h.warnings
    assert h.temperatures_c == {"servo_max": 41.0, "servo_mean": 38.5}


async def test_state_flags_follow_policy_and_safety(sim: SimBackend, fake: FakeDuck) -> None:
    s = await sim.state()
    assert s.flags.standing and not s.flags.fallen and not s.flags.sitting
    fake.push_over()
    await asyncio.sleep(0.25)
    s = await sim.state()
    assert s.flags.fallen and not s.flags.standing
    fake.fallen, fake.policy = False, "sit"
    await asyncio.sleep(0.25)
    s = await sim.state()
    assert s.flags.sitting and not s.flags.standing


async def test_move_is_a_notification_with_upstream_field_names(
    sim: SimBackend, fake: FakeDuck
) -> None:
    await sim.intent(upstream.ROBOT_MOVE.name, vx=0.05, vy=0.0, vyaw=0.3)
    await sim.health()  # round trip so the notification has been read
    move = next(m for m in fake.received if m.get("method") == "robot.move")
    assert "id" not in move and move["params"] == {"vx": 0.05, "vy": 0.0, "vyaw": 0.3}
    assert fake.invalid == []


async def test_look_is_a_request(sim: SimBackend, fake: FakeDuck) -> None:
    await sim.intent(upstream.ROBOT_LOOK.name, x=1.0, y=0.2, z=0.0)
    look = next(m for m in fake.received if m.get("method") == "robot.look")
    assert look["id"] is not None


async def test_sit_stand_check_before_toggling(sim: SimBackend, fake: FakeDuck) -> None:
    await sim.behavior("sit")
    assert fake.sitting is True
    await sim.behavior("sit")  # must not toggle back
    assert fake.sitting is True
    await sim.behavior("stand")
    assert fake.sitting is False
    toggles = [m for m in fake.received if m.get("method") == "robot.do"]
    assert len(toggles) == 2


async def test_refused_skill_raises_behavior_refused(sim: SimBackend, fake: FakeDuck) -> None:
    fake.skills.remove("kick_right")
    with pytest.raises(BehaviorRefused, match="kick_right"):
        await sim.behavior("kick")


async def test_quack_is_robot_sound_chirp(sim: SimBackend, fake: FakeDuck) -> None:
    await sim.behavior("quack")
    sound = next(m for m in fake.received if m.get("method") == "robot.sound")
    assert sound["params"] == {"tag": "chirp"}


async def test_getup_enables_the_policy(sim: SimBackend, fake: FakeDuck) -> None:
    fake.push_over()
    await sim.behavior("getup")
    assert fake.fallen is False


async def test_tof_frames_arrive_in_metres(sim: SimBackend) -> None:
    stream = sim.tof()
    try:
        frame = await asyncio.wait_for(anext(stream), 3.0)
    finally:
        await stream.aclose()
    assert frame.min_distance == pytest.approx(1.0)
    assert frame.distances_m[0][0] == pytest.approx(2.0)


async def test_no_camera_without_console(sim: SimBackend) -> None:
    with pytest.raises(NoCamera):
        await sim.frame()


async def test_stop_goes_out_even_while_a_call_is_pending(sim: SimBackend, fake: FakeDuck) -> None:
    await sim.intent(upstream.ROBOT_MOVE.name, vx=0.1)
    await sim.stop()
    assert fake.twist == [0.0, 0.0, 0.0]
    stop = next(m for m in fake.received if m.get("method") == "robot.stop")
    assert stop["id"] is not None


async def test_daemon_death_disconnects(sim: SimBackend, fake: FakeDuck) -> None:
    await fake.stop()
    await asyncio.sleep(0.1)
    assert sim.connected is False
    with pytest.raises(NotConnected):
        await sim.health()
    await sim.stop()  # still never raises


async def test_connect_fails_cleanly_without_sockets() -> None:
    b = SimBackend(socket_dir="/tmp/ds-nowhere", console_url=None)
    with pytest.raises(BackendError, match="cannot connect"):
        await b.connect()
    assert b.connected is False
    await b.stop()


def test_upright_gravity_is_zero_roll_and_pitch() -> None:
    s = state_from_upstream(
        {
            "joints": [0.0] * 15,
            "safety": {"fallen": False, "limp": False, "gravity": [0.0, 0.0, -1.0]},
        }
    )
    assert s.imu.roll == pytest.approx(0.0) and s.imu.pitch == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("label", "standing", "sitting"),
    [
        ("stand", True, False),
        ("walk", True, False),
        ("sit", False, True),
        ("rise", False, False),
        ("sitstand", False, False),
        ("homing", False, False),
        ("held", True, False),
    ],
)
def test_policy_label_to_flags(label: str, standing: bool, sitting: bool) -> None:
    s = state_from_upstream(
        {"joints": [0.0] * 15, "policy": label, "safety": {"fallen": False, "limp": False}}
    )
    assert (s.flags.standing, s.flags.sitting) == (standing, sitting)


def test_pure_mappings() -> None:
    h = health_from_upstream({"healthy": False, "degraded": True, "reason": "policy missing"})
    assert h.ok is False and h.warnings == ["battery_not_reported", "degraded", "policy missing"]
    with pytest.raises(BackendError, match="joints"):
        state_from_upstream({"joints": [0.0] * 14})
    with pytest.raises(BackendError, match="shape"):
        tof_from_upstream({"rows": 4, "cols": 4, "distance_mm": [1] * 16}, 8, 8)
    frame = tof_from_upstream({"distance_mm": [-1] + [1500] * 63}, 8, 8)
    assert frame.distances_m[0][0] == 0.0 and frame.distances_m[7][7] == 1.5
