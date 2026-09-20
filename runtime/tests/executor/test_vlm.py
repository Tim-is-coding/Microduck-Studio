"""The VLM adapter: what leaves the runtime, what comes back, and what it turns into.

No network anywhere — the Claude provider is exercised against a fake client so the request
shape is pinned by a test instead of by memory (CLAUDE.md §10).
"""

from __future__ import annotations

import io
import json
import math
from base64 import standard_b64decode
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from duckstudio.common import Text
from duckstudio.perception import MagentaPersonDetector, StubVlm
from duckstudio.perception.vlm import (
    ANSWER_SCHEMA,
    AnthropicVlm,
    VlmAnswer,
    VlmError,
    frame_size,
    make_vlm,
    media_type,
    sighting_from_answer,
    vlm_hz,
)


def png(width: int = 360, height: int = 640, marker: tuple[int, int] | None = None) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[..., 2] = 110
    if marker is not None:
        x, y = marker
        img[y - 30 : y + 30, x - 20 : x + 20] = (230, 0, 230)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


class FakeMessages:
    def __init__(self, reply: object) -> None:
        self.reply = reply
        self.calls: list[dict] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeClient:
    def __init__(self, reply: object) -> None:
        self.messages = FakeMessages(reply)


def reply(text: str, model: str = "claude-opus-5") -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        stop_reason="end_turn",
    )


def answer_json(found: bool = True, x: float = 90.0, y: float = 300.0) -> str:
    return json.dumps({"found": found, "x": x, "y": y, "answer": "Der Ball liegt links."})


# -- what we send ---------------------------------------------------------------------------


async def test_request_carries_the_frame_the_question_and_the_schema() -> None:
    client = FakeClient(reply(answer_json()))
    vlm = AnthropicVlm(client=client, model="claude-opus-5")
    frame = png()
    await vlm.look(frame, "Wo ist der rote Ball?")

    (call,) = client.messages.calls
    assert call["model"] == "claude-opus-5"
    image, text = call["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/png"
    assert standard_b64decode(image["source"]["data"]) == frame
    assert "Wo ist der rote Ball?" in text["text"] and "360x640" in text["text"]
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": ANSWER_SCHEMA}
    assert call["output_config"]["effort"] == "low"
    assert call["max_tokens"] <= 1024


async def test_jpeg_frames_are_declared_as_jpeg() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 10, 10)).save(buf, format="JPEG")
    client = FakeClient(reply(answer_json(found=False, x=-1, y=-1)))
    await AnthropicVlm(client=client).look(buf.getvalue(), "Was siehst du?")
    image, _ = client.messages.calls[0]["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/jpeg"
    assert media_type(buf.getvalue()) == "image/jpeg"


# -- what comes back ------------------------------------------------------------------------


async def test_answer_is_parsed_and_timed() -> None:
    vlm = AnthropicVlm(client=FakeClient(reply(answer_json(x=90, y=300))))
    answer = await vlm.look(png(), "Wo ist der rote Ball?", timestamp=17.0)
    assert answer.found and answer.pixel_x == 90 and answer.pixel_y == 300
    assert answer.answer == "Der Ball liegt links."
    assert answer.provider == "anthropic" and answer.model == "claude-opus-5"
    assert answer.timestamp == 17.0 and answer.latency_s >= 0.0


async def test_not_found_drops_the_coordinates() -> None:
    vlm = AnthropicVlm(client=FakeClient(reply(answer_json(found=False, x=-1, y=-1))))
    answer = await vlm.look(png(), "Wo ist die Katze?")
    assert answer.found is False and answer.pixel_x is None and answer.pixel_y is None


async def test_garbage_and_provider_errors_are_one_kind_of_failure() -> None:
    with pytest.raises(VlmError):
        await AnthropicVlm(client=FakeClient(reply("not json"))).look(png(), "Wo?")
    with pytest.raises(VlmError):
        await AnthropicVlm(client=FakeClient(RuntimeError("503 overloaded"))).look(png(), "Wo?")
    empty = SimpleNamespace(content=[], model="m", stop_reason="refusal")
    with pytest.raises(VlmError):
        await AnthropicVlm(client=FakeClient(empty)).look(png(), "Wo?")


# -- from a pixel to a bearing ---------------------------------------------------------------


def target(x: float, y: float = 300.0, found: bool = True) -> VlmAnswer:
    return VlmAnswer(
        timestamp=1.0,
        question="Wo ist der rote Ball?",
        found=found,
        answer="",
        pixel_x=x,
        pixel_y=y,
        provider="anthropic",
        model="claude-opus-5",
        latency_s=0.5,
    )


def test_pixel_becomes_a_bearing_like_the_local_detector() -> None:
    left = sighting_from_answer(target(90.0), width=360, height=640, label=Text(de="Ball"))
    right = sighting_from_answer(target(270.0), width=360, height=640, label=Text(de="Ball"))
    centre = sighting_from_answer(target(180.0), width=360, height=640, label=Text(de="Ball"))
    assert left is not None and right is not None and centre is not None
    assert left.bearing_rad > 0.15  # left of centre = positive, like robot.move vyaw
    assert right.bearing_rad < -0.15
    assert math.isclose(centre.bearing_rad, 0.0, abs_tol=1e-6)
    assert left.label.de == "Ball" and left.source == "anthropic"


def test_nothing_found_or_off_frame_is_no_sighting() -> None:
    assert (
        sighting_from_answer(target(90.0, found=False), width=360, height=640, label=Text(de="x"))
        is None
    )
    assert sighting_from_answer(target(900.0), width=360, height=640, label=Text(de="x")) is None
    assert sighting_from_answer(target(-5.0), width=360, height=640, label=Text(de="x")) is None


def test_tof_supplies_the_range_for_a_vlm_target() -> None:
    rows = [[3.9] * 8 for _ in range(8)]
    rows[4][4] = 1.2  # centre of the image, a bit below the horizon → middle zone
    sighting = sighting_from_answer(
        target(180.0, y=320.0), width=360, height=640, label=Text(de="Ball"), tof_rows=rows
    )
    assert sighting is not None and sighting.distance_m == 1.2


# -- the stub and the factory ----------------------------------------------------------------


async def test_stub_answers_from_the_local_detector_without_sending_anything() -> None:
    stub = StubVlm(MagentaPersonDetector())
    assert stub.sends_frames is False and stub.configured is True
    found = await stub.look(png(marker=(90, 300)), "Wo ist der rote Ball?")
    assert found.found and found.pixel_x is not None and found.pixel_x < 180
    nothing = await stub.look(png(), "Wo ist der rote Ball?")
    assert nothing.found is False


def test_defaults_are_local_and_the_rate_stays_in_its_band() -> None:
    assert isinstance(make_vlm(), StubVlm)  # never a paid service by accident
    assert isinstance(make_vlm("nonsense"), StubVlm)
    assert make_vlm("anthropic").name == "anthropic"
    assert vlm_hz(0.5) == 0.5
    assert vlm_hz(50) == 2.0  # §4: never faster than 2 Hz
    assert vlm_hz(0) == 0.5
    assert vlm_hz("nonsense") == 0.5


def test_frame_size_reads_the_header() -> None:
    assert frame_size(png(360, 640)) == (360, 640)
