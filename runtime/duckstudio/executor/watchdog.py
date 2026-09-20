"""Heartbeat watchdog (§7): runs in its own task; if the executor stops ticking while the
duck is being driven, the runtime stops the duck itself. Upstream's deadman (500 ms without
`robot.move`) is the second line; this one fires first and says so in the log."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

from .. import texts
from ..events import EventBus


class Watchdog:
    def __init__(
        self,
        stop: Callable[[], Awaitable[None]],
        bus: EventBus,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout_s: float = 0.35,
        check_every_s: float = 0.05,
    ) -> None:
        self._stop = stop
        self.bus = bus
        self.clock = clock
        self.timeout_s = timeout_s
        self.check_every_s = check_every_s
        self._last_pet: float | None = None
        self._armed = False
        self.tripped = False
        self._task: asyncio.Task[None] | None = None

    def pet(self, *, driving: bool) -> None:
        """Called once per executor tick. `driving` = a movement intent went out this tick."""
        self._last_pet = self.clock()
        self._armed = driving
        if driving:
            self.tripped = False

    def disarm(self) -> None:
        self._armed = False

    async def check(self) -> bool:
        """One check; True if it tripped. Public so tests can drive it with a manual clock."""
        if not self._armed or self._last_pet is None or self.tripped:
            return False
        if self.clock() - self._last_pet > self.timeout_s:
            self.tripped = True
            self._armed = False
            await self._stop()
            self.bus.emit(
                "watchdog.tripped",
                *texts.watchdog_tripped(),
                level="error",
                silent_for_s=round(self.clock() - self._last_pet, 3),
            )
            return True
        return False

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="watchdog")

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.check_every_s)
            await self.check()

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
