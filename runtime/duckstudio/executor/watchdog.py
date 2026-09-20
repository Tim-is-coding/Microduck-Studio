"""Heartbeat watchdog (§7): runs in its own task; if the executor stops ticking while the
duck is being driven, the runtime stops the duck itself and ends the behavior.

Calibration: robotd's own deadman zeroes the velocity 500 ms after the last `robot.move`
(docs/upstream-notes.md), so a stricter timeout here only produces false alarms — a 0.5 s
hiccup of the Python event loop under load tripped a 350 ms watchdog in practice. At 1 s the
duck has already stopped physically; this watchdog adds the explicit `stop()`, the log line,
and the end of the behavior so the executor does not silently resume driving."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable

from ..events import EventBus


class Watchdog:
    def __init__(
        self,
        stop: Callable[[], Awaitable[None]],
        bus: EventBus,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout_s: float = 1.0,
        check_every_s: float = 0.1,
        on_trip: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._stop = stop
        self._on_trip = on_trip
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
        silent = self.clock() - self._last_pet
        if silent > self.timeout_s:
            self.tripped = True
            self._armed = False
            await self._stop()
            self.bus.emit(
                "watchdog.tripped",
                "Der Ablauf hat ausgesetzt: Ente angehalten.",
                level="error",
                silent_for_s=round(silent, 3),
            )
            if self._on_trip is not None:
                await self._on_trip(silent)
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
