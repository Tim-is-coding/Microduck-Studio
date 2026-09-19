"""Perception service: keeps the executor's Snapshot fresh from the backend, at its own rates
(§4: local detectors 10–30 Hz, never blocking the tick). One task per source:

  frames  → person detector → `snapshot.person` (5 Hz by default; camera frames are pulled)
  tof     → `snapshot.tof_rows` / `tof_min_m` (the sensor's rate)
  state   → `snapshot.state`, plus `snapshot.health` once a second
  pad     → any stick/button frame from padd preempts the executor (§7), when the backend has it

Every task survives a backend that comes and goes: it waits and retries.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from ..backends.base import BackendError, DuckBackend, NoCamera, NotConnected
from .base import PersonDetection
from .person_local import fuse_distance

if TYPE_CHECKING:  # the executor imports perception types; keep the cycle out of runtime
    from ..executor.conditions import Snapshot

log = logging.getLogger(__name__)

RETRY_S = 1.0
NO_CAMERA_RETRY_S = 3.0


class PersonDetector(Protocol):
    def detect(self, frame: bytes, timestamp: float | None = None) -> PersonDetection | None: ...


class PerceptionService:
    def __init__(
        self,
        backend: DuckBackend,
        snapshot: Snapshot,
        *,
        detector: PersonDetector,
        clock: Callable[[], float] = time.monotonic,
        frame_hz: float = 5.0,
        state_hz: float = 10.0,
        on_pad_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.backend = backend
        self.snapshot = snapshot
        self.detector = detector
        self.clock = clock
        self.frame_hz = frame_hz
        self.state_hz = state_hz
        self.on_pad_activity = on_pad_activity
        self.camera_available: bool | None = None
        self.frames_seen = 0
        self.tof_frames_seen = 0
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._tasks:
            return
        loops = [self._frames, self._tof, self._state]
        if getattr(self.backend, "pad_socket", None):
            loops.append(self._pad)
        self._tasks = [asyncio.create_task(fn(), name=f"perception-{fn.__name__}") for fn in loops]

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._tasks = []

    def _connected(self) -> bool:
        return bool(getattr(self.backend, "connected", False))

    async def _frames(self) -> None:
        while True:
            if not self._connected():
                await asyncio.sleep(RETRY_S)
                continue
            try:
                frame = await self.backend.frame()
            except NoCamera:
                self.camera_available = False
                self.snapshot.person = None
                await asyncio.sleep(NO_CAMERA_RETRY_S)
                continue
            except (BackendError, NotConnected):
                await asyncio.sleep(RETRY_S)
                continue
            self.camera_available = True
            self.frames_seen += 1
            try:
                detection = self.detector.detect(frame, timestamp=self.clock())
            except Exception as e:  # noqa: BLE001 - a bad frame must not kill perception
                log.warning("detector failed on a frame: %s", e)
                detection = None
            if detection is not None:
                detection = fuse_distance(detection, self.snapshot.tof_rows)
            self.snapshot.person = detection
            await asyncio.sleep(1.0 / self.frame_hz)

    async def _tof(self) -> None:
        while True:
            if not self._connected():
                await asyncio.sleep(RETRY_S)
                continue
            try:
                async for frame in self.backend.tof():
                    self.tof_frames_seen += 1
                    self.snapshot.tof_rows = frame.distances_m
                    # "in front": the central columns, ignoring the top row (sky) and bottom (floor)
                    front = [row[c] for row in frame.distances_m[1:-1] for c in (3, 4)]
                    self.snapshot.tof_min_m = min(front) if front else frame.min_distance
            except (BackendError, NotConnected) as e:
                log.debug("tof stream ended: %s", e)
            await asyncio.sleep(RETRY_S)

    async def _state(self) -> None:
        n = 0
        while True:
            if not self._connected():
                await asyncio.sleep(RETRY_S)
                continue
            try:
                self.snapshot.state = await self.backend.state()
                if n % max(1, int(self.state_hz)) == 0:
                    self.snapshot.health = await self.backend.health()
            except (BackendError, NotConnected):
                await asyncio.sleep(RETRY_S)
                continue
            n += 1
            await asyncio.sleep(1.0 / self.state_hz)

    async def _pad(self) -> None:
        pad_activity = getattr(self.backend, "pad_activity", None)
        if pad_activity is None:
            return
        while True:
            if not self._connected():
                await asyncio.sleep(RETRY_S)
                continue
            try:
                async for frame in pad_activity():
                    self.snapshot.pad_active_at = self.clock()
                    if self.on_pad_activity is not None:
                        self.on_pad_activity(frame)
            except (BackendError, NotConnected) as e:
                log.debug("pad stream ended: %s", e)
            await asyncio.sleep(RETRY_S)
