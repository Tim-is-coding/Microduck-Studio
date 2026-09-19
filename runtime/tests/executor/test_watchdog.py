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
    dog = Watchdog(mock.stop, bus, clock=clock, timeout_s=0.35)
    dog.pet(driving=True)
    clock.tick(0.2)
    assert await dog.check() is False
    clock.tick(0.2)  # 0.4 s of silence
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
