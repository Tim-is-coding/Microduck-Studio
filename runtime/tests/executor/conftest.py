from __future__ import annotations

import pytest

from duckstudio.backends.mock import ManualClock, MockBackend
from duckstudio.behaviors import BehaviorPack
from duckstudio.events import EventBus
from duckstudio.executor import Executor, IntentGate, Watchdog
from duckstudio.perception.base import PersonDetection
from duckstudio.skills import SkillRegistry


class Harness:
    """Executor + gate + mock duck on one manual clock. Tests drive ticks by hand."""

    def __init__(self, registry: SkillRegistry, packs: dict[str, BehaviorPack]) -> None:
        self.clock = ManualClock(1000.0)
        self.mock = MockBackend(clock=self.clock)
        self.bus = EventBus()
        self.gate = IntentGate(self.mock, clock=self.clock, bus=self.bus)
        self.watchdog = Watchdog(self.gate.stop, self.bus, clock=self.clock)
        self.executor = Executor(
            registry, self.gate, self.bus, packs=packs, clock=self.clock, watchdog=self.watchdog
        )
        self.registry = registry
        self.packs = packs

    async def connect(self) -> None:
        await self.mock.connect()
        await self.observe()

    async def observe(self) -> None:
        self.gate.observe(health=await self.mock.health(), state=await self.mock.state())

    def see_person(self, *, bearing: float = 0.0, distance: float | None = 1.5) -> None:
        self.executor.snapshot.person = PersonDetection(
            timestamp=self.clock(),
            bearing_rad=bearing,
            distance_m=distance,
            pixel_x=180.0,
            pixel_y=200.0,
            frame_width=360,
            frame_height=640,
            area_px=5000,
            confidence=0.9,
        )

    def see_nobody(self) -> None:
        self.executor.snapshot.person = None

    async def tick(self, n: int = 1, dt: float = 0.1) -> None:
        for _ in range(n):
            self.clock.tick(dt)
            await self.observe()
            await self.executor.tick()

    async def start(self, behavior_id: str = "follow-me") -> None:
        await self.executor.start(self.packs[behavior_id])
        # tests drive tick() by hand; the background loop would race the manual clock
        await self.executor._cancel_loop()

    def kinds(self) -> list[str]:
        return [e.kind for e in self.bus.history]

    def texts(self) -> list[str]:
        return [e.text.de for e in self.bus.history]


@pytest.fixture
async def h(registry: SkillRegistry, packs: dict[str, BehaviorPack]) -> Harness:
    harness = Harness(registry, packs)
    await harness.connect()
    yield harness
    await harness.executor.close()
