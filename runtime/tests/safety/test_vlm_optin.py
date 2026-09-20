"""§7: camera frames leave the runtime only for a behavior that opted in, and only to the
provider that behavior named. Everything else stays on the machine."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from duckstudio.backends.mock import MockBackend
from duckstudio.behaviors import BehaviorPack
from duckstudio.events import EventBus
from duckstudio.executor.conditions import Snapshot, VlmRequest
from duckstudio.perception import MockBarDetector, PerceptionService

from ..conftest import RecordingVlm

ASKS_FOR_ANTHROPIC = VlmRequest(question="Wo ist der Ball?", provider="anthropic", behavior_id="b")


async def run_service(vlm: RecordingVlm, request: VlmRequest | None) -> tuple[EventBus, Snapshot]:
    mock = MockBackend()
    await mock.connect()
    snap = Snapshot()
    snap.vlm_request = request
    bus = EventBus()
    svc = PerceptionService(mock, snap, detector=MockBarDetector(), vlm=vlm, vlm_hz=20.0, bus=bus)
    svc.start()
    try:
        await asyncio.sleep(0.4)
    finally:
        await svc.close()
    return bus, snap


async def test_a_frame_never_goes_to_a_provider_the_behavior_did_not_name() -> None:
    vlm = RecordingVlm(name="someone-else", sends_frames=True)
    bus, snap = await run_service(vlm, ASKS_FOR_ANTHROPIC)
    assert vlm.calls == []
    refused = next(e for e in bus.history if e.kind == "vlm.provider_mismatch")
    assert refused.level == "error" and "kein Bild" in refused.text.de
    assert snap.target is None


async def test_an_unconfigured_provider_sends_nothing_and_says_why() -> None:
    vlm = RecordingVlm(configured=False)
    bus, _ = await run_service(vlm, ASKS_FOR_ANTHROPIC)
    assert vlm.calls == []
    notice = next(e for e in bus.history if e.kind == "vlm.not_configured")
    assert notice.level == "warn" and "ANTHROPIC_API_KEY" in notice.text.de


async def test_a_local_stand_in_may_answer_and_the_log_says_no_picture_left() -> None:
    vlm = RecordingVlm(name="stub", sends_frames=False, pixel_x=20.0, pixel_y=24.0)
    bus, snap = await run_service(vlm, ASKS_FOR_ANTHROPIC)
    assert vlm.calls, "a provider that sends nothing anywhere may still answer"
    notice = next(e for e in bus.history if e.kind == "vlm.stub_stands_in")
    assert "verlässt kein Bild die Runtime" in notice.text.de
    assert not any(e.kind == "vlm.sending" for e in bus.history)
    assert snap.target is not None


async def test_no_question_no_frames() -> None:
    vlm = RecordingVlm()
    bus, _ = await run_service(vlm, None)
    assert vlm.calls == []
    assert not any(e.kind.startswith("vlm.") for e in bus.history)


def test_a_behavior_cannot_ask_a_vlm_without_opting_in() -> None:
    body = {
        "schema": "duckstudio.behavior/v0",
        "id": "sneaky",
        "name": {"de": "Heimlich"},
        "trigger": {"kind": "manual"},
        "steps": [{"perceive": "vlm.target", "question": {"de": "Wer ist da?"}}],
    }
    with pytest.raises(ValidationError, match="vlm"):
        BehaviorPack.model_validate(body)
    BehaviorPack.model_validate({**body, "vlm": {"provider": "anthropic"}})  # with the opt-in
