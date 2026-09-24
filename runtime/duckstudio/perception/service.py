"""Perception service: keeps the executor's Snapshot fresh from the backend, at its own rates
(§4: local detectors 10–30 Hz, never blocking the tick). One task per source:

  frames  → person detector → `snapshot.person` (5 Hz by default; camera frames are pulled)
  tof     → `snapshot.tof_rows` / `tof_min_m` (the sensor's rate)
  state   → `snapshot.state`, plus `snapshot.health` once a second
  pad     → any stick/button frame from padd preempts the executor (§7), when the backend has it
  vlm     → `snapshot.target` / `snapshot.vlm`, 0.5–2 Hz, only while a behavior is asking

Every task survives a backend that comes and goes: it waits and retries. The VLM task is the
slow one and the only one that may leave the machine; it asks nothing unless the running
behavior opted in by provider name (§7) and stops after its call budget is spent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from .. import texts
from ..backends.base import BackendError, DuckBackend, NoCamera, NotConnected
from ..events import EventBus
from .base import PersonDetection
from .person_local import fuse_distance
from .vendors import VlmRouter
from .vlm import (
    DEFAULT_HZ,
    VlmError,
    VlmProvider,
    frame_size,
    sighting_from_answer,
)

if TYPE_CHECKING:  # the executor imports perception types; keep the cycle out of runtime
    from ..executor.conditions import Snapshot, VlmRequest

log = logging.getLogger(__name__)

RETRY_S = 1.0
NO_CAMERA_RETRY_S = 3.0
# How many questions one behavior run may ask. A VLM call costs money and a walk can last
# ten minutes; 200 answers at 0.5 Hz is roughly seven minutes of looking (ADR-0004).
DEFAULT_MAX_CALLS = 200


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
        vlm: VlmProvider | VlmRouter | None = None,
        vlm_hz: float = DEFAULT_HZ,
        vlm_max_calls: int = DEFAULT_MAX_CALLS,
        bus: EventBus | None = None,
    ) -> None:
        self.backend = backend
        self.snapshot = snapshot
        self.detector = detector
        self.clock = clock
        self.frame_hz = frame_hz
        self.state_hz = state_hz
        self.on_pad_activity = on_pad_activity
        self.vlm = vlm
        self.vlm_hz = vlm_hz
        self.vlm_max_calls = vlm_max_calls
        self.bus = bus
        self.camera_available: bool | None = None
        self.frames_seen = 0
        self.tof_frames_seen = 0
        self.vlm_calls = 0
        self._vlm_notices: set[tuple[str, str]] = set()
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._tasks:
            return
        loops = [self._frames, self._tof, self._state]
        if getattr(self.backend, "pad_socket", None):
            loops.append(self._pad)
        if self.vlm is not None:
            loops.append(self._vlm)
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

    def _emit(self, kind: str, text: texts.Bilingual, *, level: str = "info", **data: Any) -> None:
        if self.bus is not None:
            self.bus.emit(kind, *text, level=level, **data)  # type: ignore[arg-type]

    async def _frames(self) -> None:
        while True:
            if not self._connected():
                await asyncio.sleep(RETRY_S)
                continue
            seen_from = self._pose()  # where the duck is as the frame is taken
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
                now = self.clock()
                if getattr(self.detector, "runs_in_thread", False):
                    # A neural net takes tens of ms; the executor ticks on this loop (§6.4).
                    detection = await asyncio.to_thread(self.detector.detect, frame, now)
                else:
                    detection = self.detector.detect(frame, timestamp=now)
            except Exception as e:  # noqa: BLE001 - a bad frame must not kill perception
                log.warning("detector failed on a frame: %s", e)
                detection = None
            if detection is not None:
                detection = fuse_distance(detection, self.snapshot.tof_rows)
                detection = detection.model_copy(update={"seen_from": seen_from})
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

    # -- the slow one ------------------------------------------------------------------

    def _pose(self) -> tuple[float, float, float] | None:
        """The duck's odometry right now, from the last state (10 Hz), for `seen_from`."""
        state = self.snapshot.state
        pose = state.pose if state is not None else None
        return None if pose is None else (pose.x, pose.y, pose.heading)

    def _provider_for(self, request: VlmRequest) -> VlmProvider:
        """The vendor the behavior named, through the router when there is one (ADR-0009)."""
        vlm = self.vlm
        assert vlm is not None
        return vlm.resolve(request.provider) if isinstance(vlm, VlmRouter) else vlm

    def _vlm_allowed(self, request: VlmRequest, provider: VlmProvider) -> bool:
        """§7: a frame leaves the runtime only for the provider the behavior named.

        A provider that answers on this machine is always allowed — it cannot break a
        promise about where pictures go — but the log says it stood in for the real one.
        """
        if provider.sends_frames and provider.name != request.provider:
            self._notice(
                "provider_mismatch",
                request,
                texts.vlm_provider_mismatch(request.provider, provider.name),
                level="error",
            )
            return False
        if not provider.configured:
            self._notice(
                "not_configured", request, texts.vlm_not_configured(provider.name), level="warn"
            )
            return False
        if not provider.sends_frames and provider.name != request.provider:
            self._notice(
                "stub_stands_in", request, texts.vlm_stub_stands_in(request.provider), level="warn"
            )
        elif provider.sends_frames:
            self._notice(
                "sending",
                request,
                texts.vlm_sending(provider.name, request.question),
                level="warn",
                model=provider.model,
            )
        return True

    def _notice(
        self,
        kind: str,
        request: VlmRequest,
        text: texts.Bilingual,
        *,
        level: str = "info",
        **data: Any,
    ) -> None:
        """One line per behavior run and reason, not one per question."""
        key = (kind, f"{request.behavior_id}:{request.question}")
        if key in self._vlm_notices:
            return
        self._vlm_notices.add(key)
        self._emit(f"vlm.{kind}", text, level=level, question=request.question, **data)

    async def _vlm(self) -> None:
        assert self.vlm is not None
        period = 1.0 / max(0.01, self.vlm_hz)
        last_said: str | None = None
        while True:
            request = self.snapshot.vlm_request
            if request is None:
                self._vlm_notices.clear()
                self.vlm_calls = 0
                last_said = None
                await asyncio.sleep(RETRY_S)
                continue
            provider = self._provider_for(request)  # a key typed in mid-run counts at once
            if not self._connected() or not self._vlm_allowed(request, provider):
                await asyncio.sleep(RETRY_S)
                continue
            if self.vlm_calls >= self.vlm_max_calls:
                self._notice(
                    "budget_spent",
                    request,
                    texts.vlm_budget_spent(self.vlm_max_calls),
                    level="warn",
                )
                await asyncio.sleep(RETRY_S)
                continue
            try:
                seen_from = self._pose()
                frame = await self.backend.frame()
            except NoCamera:
                self.camera_available = False
                await asyncio.sleep(NO_CAMERA_RETRY_S)
                continue
            except (BackendError, NotConnected):
                await asyncio.sleep(RETRY_S)
                continue
            self.vlm_calls += 1
            try:
                answer = await provider.look(frame, request.question, timestamp=self.clock())
            except VlmError as e:
                self._emit(
                    "vlm.failed", texts.vlm_failed(str(e)), level="warn", provider=provider.name
                )
                await asyncio.sleep(period)
                continue
            except Exception as e:  # noqa: BLE001 - a broken provider must not kill perception
                log.warning("vlm provider failed: %r", e)
                await asyncio.sleep(period)
                continue
            self.snapshot.vlm = answer
            if answer.found:
                width, height = frame_size(frame)
                sighting = sighting_from_answer(
                    answer,
                    width=width,
                    height=height,
                    label=request.text,
                    tof_rows=self.snapshot.tof_rows,
                )
                if sighting is not None:
                    self.snapshot.target = sighting.model_copy(update={"seen_from": seen_from})
            if answer.answer != last_said:  # only when the picture changed, not every ask
                last_said = answer.answer
                self._emit(
                    "vlm.answer",
                    texts.vlm_answer(answer.answer, answer.found, stub=not provider.sends_frames),
                    found=answer.found,
                    provider=answer.provider,
                    model=answer.model,
                    latency_s=round(answer.latency_s, 2),
                )
            await asyncio.sleep(period)
