"""§7: heartbeat runs in its own task; if the executor dies, the runtime stops the duck."""

from __future__ import annotations

import asyncio

from duckstudio.backends.mock import ManualClock, MockBackend
from duckstudio.events import EventBus
from duckstudio.executor import Watchdog


async def test_trips_when_ticks_stop_while_driving() -> None:
    clock = ManualClock()
    mock = MockBackend(clock=clock)
    await mock.connect()
    bus = EventBus()
    dog = Watchdog(mock.stop, bus, clock=clock, timeout_s=1.0)
    dog.pet(driving=True)
    clock.tick(0.6)  # a hiccup robotd's own 500 ms deadman already covers: not our alarm
    assert await dog.check() is False
    clock.tick(0.6)  # 1.2 s of silence
    assert await dog.check() is True
    assert mock.stopped and bus.history[-1].kind == "watchdog.tripped"


async def test_does_not_trip_when_not_driving() -> None:
    clock = ManualClock()
    mock = MockBackend(clock=clock)
    await mock.connect()
    dog = Watchdog(mock.stop, EventBus(), clock=clock)
    dog.pet(driving=False)
    clock.tick(10.0)
    assert await dog.check() is False and not mock.stopped


async def test_runs_as_its_own_task() -> None:
    mock = MockBackend()  # manual clock inside, but the task itself runs on real time
    await mock.connect()
    dog = Watchdog(mock.stop, EventBus(), timeout_s=0.05, check_every_s=0.01)
    dog.pet(driving=True)
    dog.start()
    await asyncio.sleep(0.15)
    assert dog.tripped and mock.stopped
    await dog.close()


async def test_trip_ends_the_running_behavior() -> None:
    from duckstudio import behaviors_dir, skills_dir
    from duckstudio.behaviors import load_behavior_packs
    from duckstudio.executor import Executor, IntentGate
    from duckstudio.skills import SkillRegistry

    clock = ManualClock(10.0)
    mock = MockBackend(clock=clock)
    await mock.connect()
    bus = EventBus()
    gate = IntentGate(mock, clock=clock, bus=bus)
    gate.observe(health=await mock.health(), state=await mock.state())
    packs = load_behavior_packs(behaviors_dir())
    ex = Executor(SkillRegistry.load(skills_dir()), gate, bus, packs=packs, clock=clock)
    await ex.start(packs["follow-me"])
    await ex._cancel_loop()
    ex.watchdog.pet(driving=True)
    clock.tick(1.5)
    assert await ex.watchdog.check() is True
    assert ex.state == "failed" and "ausgesetzt" in (ex.reason or "")
    assert mock.stopped
    await ex.close()
