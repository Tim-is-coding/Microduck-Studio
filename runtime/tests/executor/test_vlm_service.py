"""The VLM task inside the perception service: it asks only while someone is asking, at its
own slow rate, and it never blocks the rest of perception (§4, §6.4)."""

from __future__ import annotations

import asyncio

from duckstudio.backends.mock import MockBackend
from duckstudio.common import Text
from duckstudio.events import EventBus
from duckstudio.executor.conditions import Snapshot, VlmRequest
from duckstudio.perception import MockBarDetector, PerceptionService
from duckstudio.perception.vlm import VlmError

from ..conftest import RecordingVlm

REQUEST = VlmRequest(
    question="Wo ist der rote Ball?",
    text=Text(de="Wo ist der rote Ball?", en="Where is the red ball?"),
    provider="anthropic",
    behavior_id="demo",
)


async def service(
    vlm: RecordingVlm, *, snapshot: Snapshot | None = None, hz: float = 20.0, max_calls: int = 200
) -> tuple[PerceptionService, Snapshot, EventBus, MockBackend]:
    mock = MockBackend()
    await mock.connect()
    snap = snapshot or Snapshot()
    bus = EventBus()
    svc = PerceptionService(
        mock,
        snap,
        detector=MockBarDetector(),
        vlm=vlm,
        vlm_hz=hz,
        vlm_max_calls=max_calls,
        bus=bus,
    )
    return svc, snap, bus, mock


async def settle(check, timeout: float = 2.0) -> bool:
    for _ in range(int(timeout / 0.02)):
        await asyncio.sleep(0.02)
        if check():
            return True
    return False


async def test_a_standing_question_is_asked_and_becomes_a_target() -> None:
    vlm = RecordingVlm(pixel_x=20.0, pixel_y=24.0)  # the mock's camera frame is 64x48
    svc, snap, bus, _ = await service(vlm)
    snap.vlm_request = REQUEST
    svc.start()
    try:
        assert await settle(lambda: snap.target is not None), [e.text.de for e in bus.history]
        assert vlm.calls and vlm.calls[0][1] == "Wo ist der rote Ball?"
        assert snap.vlm is not None and snap.vlm.found
        assert snap.target is not None and snap.target.bearing_rad > 0  # left of centre
        kinds = [e.kind for e in bus.history]
        assert "vlm.sending" in kinds and "vlm.answer" in kinds
        sending = next(e for e in bus.history if e.kind == "vlm.sending")
        assert sending.level == "warn" and "gesendet" in sending.text.de
    finally:
        await svc.close()


async def test_nothing_is_asked_without_a_question() -> None:
    vlm = RecordingVlm()
    svc, snap, _, _ = await service(vlm)
    svc.start()
    try:
        await asyncio.sleep(0.3)
        assert vlm.calls == []
        assert snap.target is None and snap.vlm is None
    finally:
        await svc.close()


async def test_the_question_stops_being_asked_when_it_is_withdrawn() -> None:
    vlm = RecordingVlm()
    svc, snap, _, _ = await service(vlm)
    snap.vlm_request = REQUEST
    svc.start()
    try:
        assert await settle(lambda: len(vlm.calls) >= 1)
        snap.vlm_request = None
        await asyncio.sleep(0.15)
        asked = len(vlm.calls)
        await asyncio.sleep(0.3)
        assert len(vlm.calls) == asked
    finally:
        await svc.close()


async def test_the_call_budget_ends_the_asking() -> None:
    vlm = RecordingVlm()
    svc, snap, bus, _ = await service(vlm, max_calls=3)
    snap.vlm_request = REQUEST
    svc.start()
    try:
        assert await settle(lambda: any(e.kind == "vlm.budget_spent" for e in bus.history))
        await asyncio.sleep(0.2)
        assert len(vlm.calls) == 3
        spent = next(e for e in bus.history if e.kind == "vlm.budget_spent")
        assert spent.level == "warn"
    finally:
        await svc.close()


async def test_the_rate_is_the_slow_one() -> None:
    vlm = RecordingVlm()
    svc, snap, _, _ = await service(vlm, hz=5.0)
    snap.vlm_request = REQUEST
    svc.start()
    try:
        await asyncio.sleep(0.6)
        assert 1 <= len(vlm.calls) <= 5  # ~3 at 5 Hz, never one per frame
    finally:
        await svc.close()


async def test_a_failing_provider_is_logged_and_perception_carries_on() -> None:
    vlm = RecordingVlm(error=VlmError("503 overloaded"))
    svc, snap, bus, _ = await service(vlm)
    snap.vlm_request = REQUEST
    svc.start()
    try:
        assert await settle(lambda: any(e.kind == "vlm.failed" for e in bus.history))
        assert snap.target is None
        assert await settle(lambda: snap.person is not None)  # the local detector keeps running
        failed = next(e for e in bus.history if e.kind == "vlm.failed")
        assert failed.level == "warn" and "503" in failed.text.de
    finally:
        await svc.close()


async def test_the_log_stays_readable_when_the_answer_does_not_change() -> None:
    vlm = RecordingVlm()
    svc, snap, bus, _ = await service(vlm)
    snap.vlm_request = REQUEST
    svc.start()
    try:
        assert await settle(lambda: len(vlm.calls) >= 5)
        answers = [e for e in bus.history if e.kind == "vlm.answer"]
        assert len(answers) == 1  # five identical answers, one line
    finally:
        await svc.close()
